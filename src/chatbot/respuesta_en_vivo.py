"""Respuesta en vivo: los fragmentos de la síntesis de MedGemma llegan a la
interfaz mientras se generan (evento SSE `token`, ver
specs/003-progreso-chat/contracts/eventos.md).

    with escuchar_tokens(lambda texto: enviar(traductor.token(texto))):
        result = engine.process(pregunta)

`escuchar_tokens` usa una ContextVar (como `llm_gate.ui_progress`): vale para
las llamadas de ESTE hilo y lo lee `RAGAnswerEngine`, así el backend recibe los
tokens sin tocar el motor de chat. Fuera del bloque no hay streaming.

Lo transmitido es un BORRADOR: la respuesta final (limpieza, salvaguarda de
cifras de src/rag/grounding.py, truncado) lo reemplaza. `FiltroBorrador`
evita el salto más visible: retiene el comienzo mientras pueda ser la frase de
«sin evidencia» (que nunca se muestra) o una muletilla inicial («Claro, …»)
que el post-proceso quitará. Decisión completa en
specs/009-experiencia-espera/plan.md.
"""
import contextvars
from contextlib import contextmanager

_OYENTE = contextvars.ContextVar("respuesta_en_vivo_oyente", default=None)

# Caracteres a reunir antes de decidir si el comienzo se transmite.
MIN_DECIDIR = 24


@contextmanager
def escuchar_tokens(on_token):
    """Durante el bloque, la síntesis documental de este hilo avisa cada
    fragmento a `on_token(texto)` (None = sin streaming)."""
    token = _OYENTE.set(on_token)
    try:
        yield
    finally:
        _OYENTE.reset(token)


def oyente_tokens():
    """`on_token` del bloque `escuchar_tokens` activo en este hilo, o None."""
    return _OYENTE.get()


def _plano(texto):
    return " ".join(str(texto or "").split()).lower()


class FiltroBorrador:
    """Callable que recibe los fragmentos crudos del modelo y reenvía a
    `on_token` el borrador visible. Nunca lanza.

    - `retenidas`: frases que no se transmiten si la respuesta empieza por
      ellas (p. ej. NO_EVIDENCE_ANSWER); mientras el comienzo pueda serlo, se
      espera.
    - `relleno_inicial`: regex (anclada al inicio) de muletillas que el
      post-proceso quita; se quitan antes de transmitir y la primera letra
      pasa a mayúscula, como en AnswerSynthesizer._strip_filler."""

    def __init__(self, on_token, retenidas=(), relleno_inicial=None):
        self._on_token = on_token
        self._retenidas = [_plano(frase) for frase in retenidas if frase]
        self._relleno = relleno_inicial
        self._inicio = ""
        self._abierto = False
        self._descartado = False

    def __call__(self, texto):
        if not texto or self._descartado:
            return
        if self._abierto:
            self._enviar(texto)
            return
        self._inicio += texto
        self._decidir()

    def _decidir(self):
        plano = _plano(self._inicio)
        for frase in self._retenidas:
            if plano.startswith(frase):
                self._descartado = True
                return
            if frase.startswith(plano):
                return  # todavía puede ser la frase retenida
        if len(self._inicio.strip()) < MIN_DECIDIR and "\n" not in self._inicio.strip():
            return
        visible = self._inicio.lstrip()
        coincidencia = self._relleno.match(visible) if self._relleno else None
        if coincidencia:
            visible = visible[coincidencia.end():]
            visible = visible[:1].upper() + visible[1:]
        self._abierto = True
        self._enviar(visible)

    def _enviar(self, texto):
        if not texto:
            return
        try:
            self._on_token(texto)
        except Exception:
            pass  # la vista en vivo nunca tumba la síntesis

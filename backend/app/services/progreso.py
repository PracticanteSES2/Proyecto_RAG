"""Progreso en vivo de un turno, sobre las APIs reales de otros módulos:

- `src/chatbot/progreso.py`: `TraductorProgreso` traduce las trazas del motor a
  eventos `progreso`/`espera`/`cola`/`aviso` (uno por turno).
- `src/llm/llm_gate.py`: `ui_progress(on_queue=…)` hace que las llamadas a
  MedGemma del turno esperen hueco hasta MEDGEMMA_QUEUE_WAIT_UI (30 s) en vez
  de caer enseguida al resumen extractivo, y avisa en vivo la posición en la
  fila del LLM (evento `cola`).
"""
from __future__ import annotations

import logging
import threading

from src.chatbot.progreso import TraductorProgreso, evento_cola
from src.llm.llm_gate import ui_progress

LOG = logging.getLogger(__name__)


def nuevo_traductor(recientes=None) -> TraductorProgreso:
    return TraductorProgreso(recientes=recientes)


def contexto_cola_llm(on_queue):
    return ui_progress(on_queue=on_queue)

class EmisorTurno:
    """Publica los eventos de UN turno. El traductor no es seguro entre hilos
    (lo llaman el hilo del motor, el del reloj y el de la puerta del LLM): todo
    pasa por un candado. Nunca lanza."""

    def __init__(self, publicar, traductor, diagnostico: bool = False):
        self._publicar = publicar
        self.traductor = traductor
        self.diagnostico = diagnostico
        self._candado = threading.Lock()

    def emitir(self, sobres):
        for sobre in sobres or []:
            try:
                self._publicar(sobre["evento"], sobre["datos"])
            except Exception:
                LOG.warning("No se pudo publicar el evento %s", sobre.get("evento"), exc_info=True)

    def _llamar(self, metodo, *args):
        with self._candado:
            try:
                sobres = getattr(self.traductor, metodo)(*args)
            except Exception:
                sobres = []
            self.emitir(sobres)

    def iniciar(self):
        self._llamar("iniciar")

    def traducir(self, evento_motor):
        self._llamar("traducir", evento_motor)

    def tic(self):
        self._llamar("tic")

    def finalizar(self):
        self._llamar("finalizar")

    def aviso(self, result):
        self._llamar("aviso", result)

    def cola_llm(self, evento):
        """`on_queue` de llm_gate: {"position", "in_flight", "done", …}. Solo el
        evento `cola` (la interfaz lo muestra únicamente en modo diagnóstico:
        nunca se le habla al usuario de filas ni de otras consultas)."""
        if not self.diagnostico or not isinstance(evento, dict) or evento.get("done"):
            return
        self.evento("cola", evento_cola(evento.get("position") or 0, evento.get("in_flight") or 0)["datos"])

    def token(self, texto):
        """Trozo de la redacción en streaming (evento `token` {texto}). Lo llama
        el hilo del motor. Pasa por el traductor: tras el primer token, `tic()`
        deja de rotar frases y de emitir esperas (la respuesta ya avanza)."""
        if texto:
            self._llamar("token", str(texto))

    def evento(self, nombre, datos):
        with self._candado:
            self.emitir([{"evento": nombre, "datos": datos}])

    @property
    def recientes(self):
        return list(getattr(self.traductor, "recientes", None) or [])


class Reloj:
    """Hilo que llama `tic()` cada `intervalo_s` mientras el motor trabaja."""

    def __init__(self, emisor: EmisorTurno, intervalo_s: float = 1.0):
        self._emisor = emisor
        self._intervalo = intervalo_s
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._correr, name="reloj-turno", daemon=True)

    def _correr(self):
        while not self._parar.wait(self._intervalo):
            self._emisor.tic()

    def __enter__(self):
        self._hilo.start()
        return self

    def __exit__(self, *exc):
        self._parar.set()
        self._hilo.join(timeout=2)
        return False

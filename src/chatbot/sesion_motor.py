"""
Sesión y turno del motor (spec 008): el QueryEngine no guarda estado de
conversación en sus atributos.

Los atributos históricos del motor (`_pending_query_plan`, `_last_success`,
`conversation_memory`...) siguen existiendo para el código del motor y las
pruebas, pero son descriptores que leen y escriben:

- en la `EstadoConversacion` del turno en curso (lo que dura entre turnos);
- en el `_Turno` en curso (lo que vale solo dentro del turno: razonamiento,
  interpretación, mensaje del turno...).

El turno en curso vive en un ContextVar: cada hilo o tarea ve el suyo, de modo
que dos turnos simultáneos de conversaciones distintas no se pisan. Sin
`sesion=` (pruebas, scripts, arneses) se usa la sesión y el turno propios del
motor: el comportamiento de siempre, de un solo usuario.
"""
import contextvars
import functools
from contextlib import contextmanager

from src.chatbot.estado_conversacion import EstadoConversacion, en_sesion

_TURNO = contextvars.ContextVar("turno_motor", default=None)
_ESCUCHA = contextvars.ContextVar("escucha_progreso_motor", default=None)


class _Turno:
    """Datos que valen solo dentro de un turno (nunca se serializan)."""

    __slots__ = ("applying_deferred", "intent_llm_turn", "motor", "range_choice", "sesion", "trace",
                 "turn_interpretation", "turn_message")

    def __init__(self, motor, sesion):
        self.motor = motor
        self.sesion = sesion
        self.trace = None
        self.turn_interpretation = None
        self.turn_message = None
        self.range_choice = None
        self.intent_llm_turn = None
        self.applying_deferred = None


class _DeSesion:
    """Atributo del motor guardado en la EstadoConversacion del turno."""

    def __init__(self, campo):
        self.campo = campo

    def __get__(self, motor, tipo=None):
        if motor is None:
            return self
        return getattr(motor._sesion_actual(), self.campo)

    def __set__(self, motor, valor):
        setattr(motor._sesion_actual(), self.campo, valor)


class _DelTurno(_DeSesion):
    """Atributo del motor que vale solo dentro del turno en curso."""

    def __get__(self, motor, tipo=None):
        if motor is None:
            return self
        return getattr(motor._turno_actual(), self.campo)

    def __set__(self, motor, valor):
        setattr(motor._turno_actual(), self.campo, valor)


def con_sesion(metodo):
    """Agrega `sesion=` y `progreso=` a un punto de entrada del motor. Con
    `sesion` el turno lee y escribe solo esa conversación y, al terminar, la
    deja lista para el siguiente (EstadoConversacion.cerrar_turno)."""

    @functools.wraps(metodo)
    def envuelto(self, *args, sesion=None, progreso=None, **kwargs):
        escucha = _ESCUCHA.set((self, progreso)) if progreso is not None else None
        if progreso is not None:
            self._enganchar_powerbi()
        try:
            with self._turno(sesion) as (turno, nuevo):
                cerrar = nuevo and sesion is not None
                try:
                    resultado = metodo(self, *args, **kwargs)
                except Exception:  # como app.py: un aborto de Streamlit (BaseException) no cierra
                    if cerrar:
                        turno.sesion.cerrar_turno({"status": "error"})
                    raise
                if cerrar:
                    turno.sesion.cerrar_turno(resultado)
                return resultado
        finally:
            if escucha is not None:
                _ESCUCHA.reset(escucha)

    return envuelto


class SesionMotorMixin:
    """Estado de conversación y de turno del QueryEngine, fuera del motor."""

    # Entre turnos: EstadoConversacion.
    conversation_memory = _DeSesion("memoria")
    _last_success = _DeSesion("seguimiento")
    _pending_master_metric = _DeSesion("indicador_pendiente")
    _pending_query_plan = _DeSesion("plan_pendiente")
    _pending_dashboard_clarification = _DeSesion("tablero_pendiente")
    _deferred_context_message = _DeSesion("mensaje_aplazado")
    last_reasoning = _DeSesion("ultimo_razonamiento")
    # Dentro del turno.
    _trace = _DelTurno("trace")
    _turn_interpretation = _DelTurno("turn_interpretation")
    _turn_message = _DelTurno("turn_message")
    _range_choice = _DelTurno("range_choice")
    _intent_llm_turn = _DelTurno("intent_llm_turn")
    _applying_deferred = _DelTurno("applying_deferred")

    # ------------------------------------------------------------------
    # Sesión y turno en curso
    # ------------------------------------------------------------------

    def _sesion_legado(self):
        """Sesión propia del motor (modo legado, sin `sesion=`)."""
        sesion = self.__dict__.get("_sesion_propia")
        if sesion is None:
            sesion = self.__dict__["_sesion_propia"] = EstadoConversacion(id="legado")
        return sesion

    def _turno_legado(self):
        turno = self.__dict__.get("_turno_propio")
        if turno is None:
            turno = self.__dict__["_turno_propio"] = _Turno(self, self._sesion_legado())
        return turno

    def _turno_actual(self):
        turno = _TURNO.get()
        return turno if turno is not None and turno.motor is self else self._turno_legado()

    def _sesion_actual(self):
        return self._turno_actual().sesion

    @contextmanager
    def _turno(self, sesion=None):
        """Abre el turno (o se une al que ya está en curso: turnos anidados).
        Entrega (turno, nuevo)."""
        activo = _TURNO.get()
        if activo is not None and activo.motor is self:
            if sesion is not None and sesion is not activo.sesion:
                raise RuntimeError("turno anidado con otra conversación")
            yield activo, False
            return
        if sesion is None:
            turno, candado = self._turno_legado(), None
        else:
            if not isinstance(sesion, EstadoConversacion):
                raise TypeError("sesion debe ser una EstadoConversacion")
            turno, candado = _Turno(self, sesion), sesion.candado
        if candado is not None:
            candado.acquire()  # un turno a la vez por conversación
        token = _TURNO.set(turno)
        try:
            # El ConversationManager compartido lee esta sesión (None = la suya propia).
            with en_sesion(sesion):
                yield turno, True
        finally:
            _TURNO.reset(token)
            if candado is not None:
                candado.release()

    # ------------------------------------------------------------------
    # API histórica (compatibilidad)
    # ------------------------------------------------------------------

    def reset(self, full=False, sesion=None):
        """Limpia las contrapreguntas pendientes. Con full=True («Nueva
        conversación») también olvida el contexto de seguimiento y la memoria
        de la conversación. Sin `sesion` actúa sobre la del turno en curso o la
        propia del motor (modo legado)."""
        estado = sesion if sesion is not None else self._sesion_actual()
        estado.olvidar_contrapreguntas()
        if full:
            estado.seguimiento = None
            estado.memoria.clear()

    def conversation_history(self, limit=6, sesion=None):
        """Últimos `limit` turnos como mensajes [{"role": "user"|"assistant",
        "text": str, "meta": {...}}] (cada turno aporta dos mensajes). Lo usa
        la redacción de respuestas (RAGAnswerEngine / AnswerSynthesizer)."""
        estado = sesion if sesion is not None else self._sesion_actual()
        return estado.memoria.history(limit)

    # ------------------------------------------------------------------
    # Progreso en vivo (por contexto: cada hilo o tarea ve su escucha)
    # ------------------------------------------------------------------

    @property
    def progress_listener(self):
        actual = _ESCUCHA.get()
        return actual[1] if actual is not None and actual[0] is self else None

    @progress_listener.setter
    def progress_listener(self, listener):
        _ESCUCHA.set((self, listener) if listener is not None else None)

    def set_progress_listener(self, listener):
        """Función que recibe en vivo los pasos del turno (o None), para el
        hilo o tarea que llama. También engancha las consultas DAX del
        proveedor de Power BI, incluidas las de exploración de valores que hace
        el Query Plan."""
        self.progress_listener = listener
        if listener is not None:
            self._enganchar_powerbi()

    def _enganchar_powerbi(self):
        # El proveedor es compartido: sus avisos van al turno del hilo que
        # consulta, y solo si ese turno tiene escucha (si no, se ignoran).
        provider = getattr(self, "powerbi_provider", None)
        if provider is not None and hasattr(provider, "query_listener"):
            provider.query_listener = self._on_powerbi_query
        if provider is not None and hasattr(provider, "activity_listener"):
            # Aperturas/reconexiones (posible ventana de inicio de sesión).
            provider.activity_listener = self._on_powerbi_activity

    def _on_powerbi_query(self, semantic_model, dax):
        if self.progress_listener is not None:
            from src.chatbot.reasoning_trace import short

            self._activity(f"Consultando Power BI ({semantic_model or 'modelo por defecto'})",
                           short(" ".join(str(dax or "").split()), 160))

    def _on_powerbi_activity(self, title, *lines):
        if self.progress_listener is not None:
            self._activity(title, *lines)

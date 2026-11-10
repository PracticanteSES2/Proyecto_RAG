"""
Puerta única para las llamadas al LLM (MedGemma) desde el chatbot.

  * Tiempo límite REAL: se pasa `timeout` al proveedor, que lo aplica a nivel
    HTTP (MedGemmaProvider). Al vencer se cierra la conexión y Ollama deja de
    generar. Antes se usaba un hilo daemon + join(timeout): la petición seguía
    abierta (hasta MEDGEMMA_TIMEOUT=180 s) y el servidor seguía generando y
    ocupando un hueco; esas llamadas abandonadas se acumulaban.
  * Concurrencia acotada y JUSTA: como mucho MEDGEMMA_MAX_CONCURRENT (3)
    llamadas a la vez; las demás esperan en una fila FIFO (`FifoLine` de
    src/chatbot/runtime_stats.py): entra la primera en llegar. Si no hay hueco
    en `queue_wait` segundos, la llamada no se hace y se devuelve
    status="llm_saturated" para degradar rápido (p. ej. resumen extractivo en
    la síntesis RAG).
  * Contadores para el diagnóstico (src/chatbot/runtime_stats.py).

API para la UI de progreso (app.py / src/ui/progreso.py)
--------------------------------------------------------
`queue_state(ident=None)` → {"capacity", "in_flight", "waiting", "position",
"ahead"} de la fila de MedGemma para el hilo `ident` (por defecto el actual).
`position` 1 = la siguiente en entrar, None = ese hilo no espera; `ahead` =
in_flight + position - 1 («hay N consultas antes que la tuya»). También en
`runtime_stats.queue_snapshot()["llm"]`.

`ui_progress(on_queue=None, queue_wait=None)` — gestor de contexto que la UI
pone alrededor del turno cuando PUEDE mostrar progreso:

    with llm_gate.ui_progress(on_queue=mostrar):
        engine.process(texto)

Dentro, las llamadas SIN `queue_wait` explícito (síntesis RAG, descripción de
opciones si corre en ese hilo) esperan hueco hasta `queue_wait` o
MEDGEMMA_QUEUE_WAIT_UI (30 s) en lugar de MEDGEMMA_QUEUE_WAIT (3 s), y esa
espera NO le resta presupuesto a la generación (recibe su `timeout` completo:
el usuario está viendo su posición). Las que pasan `queue_wait` explícito
(reescritura contextual, intención LLM: 1 s, son opcionales) no cambian.
`on_queue(evento)` se llama en el MISMO hilo que abrió el contexto (el de la
sesión de Streamlit; nunca desde hilos auxiliares) mientras espera, cada
~0,5 s, con:

    {"purpose", "capacity", "in_flight", "waiting", "position", "ahead",
     "waited_s", "done": False}

y una vez al terminar la espera (solo si hubo espera):

    {"purpose", "waited_s", "done": True, "acquired": bool}

Si `on_queue` lanza, se ignora. El contexto es por hilo (ContextVar): no se
filtra a otras sesiones. Sin `ui_progress` el comportamiento es el de siempre.

Contrato de `call_llm` (sin cambios): nunca lanza; devuelve el dict del
proveedor o {"status": "llm_saturated" | "llm_timeout" | "llm_error",
"answer": None, ...}.
"""
import contextvars
import inspect
import threading
import time
from contextlib import contextmanager

from src.chatbot.runtime_stats import STATS, FifoLine, env_float, env_int

_ABANDON_LOCK = threading.Lock()
_PROGRESS = contextvars.ContextVar("llm_gate_ui_progress", default=None)
_TICK_S = 0.5


def max_concurrent():
    return env_int("MEDGEMMA_MAX_CONCURRENT", 3)


def default_queue_wait():
    """Segundos que una llamada espera un hueco antes de rendirse."""
    return env_float("MEDGEMMA_QUEUE_WAIT", 3.0)


def default_ui_queue_wait():
    """Espera de hueco cuando la UI muestra el progreso (ui_progress)."""
    return env_float("MEDGEMMA_QUEUE_WAIT_UI", 30.0)


class _FairGate:
    """Semáforo justo: capacidad leída en cada llamada (MEDGEMMA_MAX_CONCURRENT)
    y fila FIFO para las que esperan."""

    def __init__(self):
        self.line = FifoLine("medgemma")
        self.in_flight = 0

    def acquire(self, wait_s, owner=None, on_tick=None):
        capacity = max_concurrent()

        def ready():  # se evalúa con el candado de la fila tomado
            if self.in_flight < capacity:
                self.in_flight += 1
                return True
            return False

        with self.line.cond:
            if self.line.is_empty_locked() and ready():
                return True
        ticket = self.line.join(owner=owner)
        return self.line.wait_turn(
            ticket, ready, deadline=time.monotonic() + max(0.0, float(wait_s)),
            poll_s=_TICK_S if on_tick else 0.25, on_tick=on_tick,
        )

    def release(self):
        with self.line.cond:
            self.in_flight = max(0, self.in_flight - 1)
            self.line.cond.notify_all()

    def state(self, ident=None):
        capacity = max_concurrent()
        position = self.line.position(ident) if ident != -1 else None
        in_flight = self.in_flight
        return {
            "capacity": capacity,
            "in_flight": in_flight,
            "waiting": self.line.waiting(),
            "position": position,
            "ahead": (in_flight + position - 1) if position else None,
        }


_GATE = _FairGate()
STATS.set_queue_source("llm", _GATE.state)


def queue_state(ident=None):
    """Estado de la fila de MedGemma para el hilo `ident` (ver el módulo)."""
    return _GATE.state(ident)


@contextmanager
def ui_progress(on_queue=None, queue_wait=None):
    """Modo «la UI muestra el progreso» para las llamadas de este hilo (ver
    el docstring del módulo)."""
    token = _PROGRESS.set({
        "owner": threading.get_ident(),
        "on_queue": on_queue,
        "queue_wait": float(queue_wait) if queue_wait is not None else default_ui_queue_wait(),
    })
    try:
        yield
    finally:
        _PROGRESS.reset(token)


def current_progress():
    """Contexto de ui_progress activo en este hilo (dict) o None."""
    return _PROGRESS.get()


def _accepted_kwargs(provider, kwargs):
    """Solo los argumentos que acepta `provider.chat` (los dobles de prueba
    antiguos no reciben `timeout` ni `think`)."""
    method = getattr(provider, "chat", None)
    try:
        params = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in params}


def _notify(progress, event):
    callback = progress.get("on_queue") if progress else None
    if callback is None or threading.get_ident() != progress.get("owner"):
        return
    try:
        callback(event)
    except Exception:
        pass  # la UI nunca tumba la llamada


def call_llm(provider, messages, purpose="otro", timeout=None, queue_wait=None, **kwargs):
    """Llama a `provider.chat(messages=..., **kwargs)` con fila justa, tiempo
    límite y contadores. Nunca lanza: devuelve el dict del proveedor o
    {"status": "llm_saturated" | "llm_timeout" | "llm_error", "answer": None, ...}.

    `timeout` (s) es el presupuesto total (espera del hueco + llamada), salvo
    dentro de `ui_progress` sin `queue_wait` explícito: ahí la espera en fila
    no descuenta y la llamada recibe `timeout` completo.
    `queue_wait` (s) es la espera máxima de un hueco (MEDGEMMA_QUEUE_WAIT por
    defecto, MEDGEMMA_QUEUE_WAIT_UI dentro de `ui_progress`; nunca más que
    `timeout`).

    Si el proveedor declara `enforces_timeout = True` (MedGemmaProvider) recibe
    `timeout` y lo aplica él (cierra la conexión al vencer). Si no, se espera
    en un hilo y, al vencer, la llamada queda abandonada (como antes)."""
    progress = _PROGRESS.get()
    ui_mode = progress is not None and queue_wait is None
    started = time.perf_counter()
    if queue_wait is None:
        queue_wait = progress["queue_wait"] if ui_mode else default_queue_wait()
    if timeout:
        queue_wait = min(float(queue_wait), float(timeout))

    ticked = {"any": False}

    def on_tick():
        ticked["any"] = True
        event = dict(_GATE.state(), purpose=purpose, done=False,
                     waited_s=round(time.perf_counter() - started, 2))
        _notify(progress, event)

    STATS.llm_waiting(+1)
    try:
        acquired = _GATE.acquire(
            queue_wait, owner=progress.get("owner") if progress else None,
            on_tick=on_tick if ui_mode and progress.get("on_queue") else None,
        )
    except Exception:  # nunca debería pasar; el contrato es no lanzar
        acquired = False
    finally:
        STATS.llm_waiting(-1)
    waited = round(time.perf_counter() - started, 2)
    if ticked["any"]:
        _notify(progress, {"purpose": purpose, "waited_s": waited, "done": True, "acquired": acquired})
    if not acquired:
        STATS.llm_saturated(purpose)
        return {
            "status": "llm_saturated",
            "answer": None,
            "waited_s": waited,
            "error": (
                f"MedGemma saturado: {max_concurrent()} llamadas en curso y no hubo hueco "
                f"en {waited:.1f} s"
            ),
        }

    call_kwargs = dict(kwargs, messages=messages)
    if not timeout:
        budget = None
    elif ui_mode:
        budget = float(timeout)
    else:
        budget = max(min(1.0, float(timeout)), float(timeout) - waited)
    native = bool(getattr(provider, "enforces_timeout", False))
    if budget is not None and native:
        call_kwargs["timeout"] = budget
    call_kwargs = _accepted_kwargs(provider, call_kwargs)
    STATS.llm_begin(purpose)
    call_started = time.perf_counter()
    box = {}

    def run():
        status = "llm_error"
        try:
            try:
                result = provider.chat(**call_kwargs)
            except Exception as error:  # el proveedor normalmente no lanza
                result = {"status": "llm_error", "answer": None,
                          "error": f"{type(error).__name__}: {error}"}
            if not isinstance(result, dict):
                result = {"status": "llm_error", "answer": None,
                          "error": f"respuesta inesperada: {result!r}"}
            status = result.get("status") or "llm_error"
            box["result"] = result
        finally:
            with _ABANDON_LOCK:
                abandoned = box.get("abandoned", False)
                box["done"] = True
            STATS.llm_end(purpose, None if abandoned else status,
                          time.perf_counter() - call_started, abandoned=abandoned)
            _GATE.release()

    if budget is None or native:
        # El proveedor aplica el tiempo límite (MedGemmaProvider: a nivel HTTP,
        # cerrando la conexión) o no hay límite: llamada directa.
        run()
    else:
        # Proveedor sin tiempo límite propio (dobles de prueba, otros LLM): se
        # espera en un hilo. Si vence, la llamada sigue viva hasta terminar;
        # conserva su hueco en la puerta y cuenta como «abandonada».
        worker = threading.Thread(target=run, name="llm-sin-limite", daemon=True)
        worker.start()
        worker.join(budget)
        with _ABANDON_LOCK:
            if not box.get("done"):
                box["abandoned"] = True
        if box.get("abandoned"):
            STATS.llm_abandoned(purpose)
            return {"status": "llm_timeout", "answer": None, "timeout_seconds": budget,
                    "error": f"sin respuesta en {budget:.1f} s (llamada abandonada: el proveedor "
                             "no admite tiempo límite propio)"}

    result = box.get("result") or {"status": "llm_error", "answer": None}
    if waited >= 0.5:
        result.setdefault("queue_wait_s", waited)
    return result

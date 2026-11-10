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

Backend de coordinación (enchufable, src/llm/gate_backends.py)
--------------------------------------------------------------
    LLM_GATE_BACKEND=memoria   (por defecto) fila FIFO dentro del proceso.
    LLM_GATE_BACKEND=redis     semáforo distribuido y justo entre procesos y
                               réplicas (REDIS_URL, por defecto
                               redis://localhost:6379/0): tickets FIFO,
                               préstamos con TTL (LLM_GATE_LEASE_S; el de cada
                               llamada = timeout + espera + 30 s) para que un
                               proceso caído no deje huecos ocupados, latido de
                               los que esperan (LLM_GATE_WAITER_TTL_S, 10 s).
Si Redis no responde al elegirlo, se usa memoria con una advertencia en el log
(logger "llm_gate") y se reintenta cada 30 s; si falla a mitad de una llamada,
esa llamada sigue en memoria. `MEDGEMMA_MAX_CONCURRENT` es la capacidad
GLOBAL con Redis (todas las réplicas deben usar el mismo valor).
`set_backend(b)` fija uno a mano (pruebas); `backend_name()` dice cuál rige.

API para la UI de progreso y el API (FastAPI: eventos SSE `cola`)
-----------------------------------------------------------------
`STATS.llm_pressure()` (runtime_stats) → {"in_flight", "waiting", "capacity",
"saturated_recent"} para el indicador de presión. `add_queue_observer(fn)`
recibe toda espera de hueco con un "titulo" que empieza por «LLM en cola»
(para registrar la actividad en la traza sin acoplar la puerta al motor).
`evento_cola(estado)` convierte `queue_state()` o un evento de `on_queue` en
{"posicion", "en_curso", "en_espera", "antes", "capacidad"} para el SSE.
En FastAPI la llamada al LLM corre en un hilo del threadpool: abre
`ui_progress(on_queue=cb)` en ESE hilo y en `cb` reenvía al bucle async con
`loop.call_soon_threadsafe(cola_sse.put_nowait, evento_cola(evento))`.

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
import logging
import os
import threading
import time
from contextlib import contextmanager

from src.chatbot.runtime_stats import STATS, env_float, env_int
from src.llm.gate_backends import MemoriaBackend, RedisBackend, redis_desde_entorno

LOG = logging.getLogger("llm_gate")
_ABANDON_LOCK = threading.Lock()
_PROGRESS = contextvars.ContextVar("llm_gate_ui_progress", default=None)


def max_concurrent():
    return env_int("MEDGEMMA_MAX_CONCURRENT", 3)


def default_queue_wait():
    """Segundos que una llamada espera un hueco antes de rendirse."""
    return env_float("MEDGEMMA_QUEUE_WAIT", 3.0)


def default_ui_queue_wait():
    """Espera de hueco cuando la UI muestra el progreso (ui_progress)."""
    return env_float("MEDGEMMA_QUEUE_WAIT_UI", 30.0)


# ----------------------------------------------------------------------
# Backend de coordinación (LLM_GATE_BACKEND=memoria|redis, REDIS_URL)
# ----------------------------------------------------------------------

_MEMORIA = MemoriaBackend(max_concurrent)
_BACKEND = {"instance": None, "key": None, "forced": False, "retry_at": 0.0}
_BACKEND_LOCK = threading.Lock()
REDIS_RETRY_S = 30.0


def _configured():
    name = str(os.getenv("LLM_GATE_BACKEND") or "memoria").strip().lower()
    return name if name in ("memoria", "redis") else "memoria", os.getenv("REDIS_URL", "")


def _backend():
    """Backend vigente. Con LLM_GATE_BACKEND=redis y Redis inalcanzable se
    usa memoria (advertencia en el log) y se reintenta cada 30 s."""
    with _BACKEND_LOCK:
        if _BACKEND["forced"]:
            return _BACKEND["instance"]
        key = _configured()
        current = _BACKEND["instance"]
        if current is not None and _BACKEND["key"] == key and (
                current.name == key[0] or time.monotonic() < _BACKEND["retry_at"]):
            return current
        instance = _MEMORIA
        if key[0] == "redis":
            try:
                instance = RedisBackend(redis_desde_entorno(), capacity_fn=max_concurrent)
            except Exception as error:
                LOG.warning("llm_gate: Redis no disponible (%s: %s); se usa la cola en memoria "
                            "(solo coordina este proceso)", type(error).__name__, error)
                _BACKEND["retry_at"] = time.monotonic() + REDIS_RETRY_S
        _BACKEND.update(instance=instance, key=key)
        return instance


def set_backend(backend):
    """Fija el backend (pruebas o arranque del API). None = volver al del entorno."""
    with _BACKEND_LOCK:
        _BACKEND.update(instance=backend, forced=backend is not None, key=None, retry_at=0.0)


def backend_name():
    return _backend().name


def _fallback(error, where):
    """Redis falló a mitad de camino: esta llamada sigue en memoria y se
    reintenta Redis más tarde (nunca se lanza al chatbot)."""
    LOG.warning("llm_gate: fallo de Redis en %s (%s: %s); esta llamada usa la cola en memoria",
                where, type(error).__name__, error)
    with _BACKEND_LOCK:
        if not _BACKEND["forced"]:
            _BACKEND.update(instance=_MEMORIA, retry_at=time.monotonic() + REDIS_RETRY_S)
    return _MEMORIA


def queue_state(ident=None):
    """Estado de la fila de MedGemma para el hilo `ident` (ver el módulo).
    Nunca lanza; incluye "backend" ("memoria" | "redis")."""
    backend = _backend()
    try:
        return backend.state(ident)
    except Exception as error:
        return _fallback(error, "state").state(ident)


STATS.set_queue_source("llm", queue_state)


def evento_cola(state):
    """Evento SSE `cola` para el API (FastAPI): {"posicion", "en_curso",
    "en_espera", "antes", "capacidad"} a partir de queue_state() o de un
    evento de `on_queue`. `posicion` 1 = la siguiente en entrar (None = ya no
    espera); `antes` = consultas antes que la suya."""
    return {
        "posicion": state.get("position"),
        "en_curso": state.get("in_flight"),
        "en_espera": state.get("waiting"),
        "antes": state.get("ahead"),
        "capacidad": state.get("capacity"),
    }


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


def _with_tokens(provider, call_kwargs, on_token, box):
    """Streaming opcional: si hay `on_token` y el proveedor acepta `stream` y
    `on_token` (MedGemmaProvider), se le pide streaming con un reenvío
    protegido: si `on_token` lanza se ignora, y tras abandonar la llamada por
    tiempo (`box["abandoned"]`) ya no se reenvía nada. Si el proveedor no los
    acepta, la llamada es la de siempre (sin tokens)."""
    if not callable(on_token):
        return call_kwargs
    accepted = _accepted_kwargs(provider, dict(call_kwargs, stream=True, on_token=on_token))
    if "stream" not in accepted or "on_token" not in accepted:
        return call_kwargs

    def forward(text):
        # Bajo el candado del abandono: ningún token llega después del
        # llm_timeout (el reenvío debe ser rápido, p. ej. poner en una cola).
        with _ABANDON_LOCK:
            if box.get("abandoned"):
                return
            try:
                on_token(text)
            except Exception:
                pass  # la vista en vivo nunca tumba la llamada

    return dict(call_kwargs, stream=True, on_token=forward)


_OBSERVERS = []


def add_queue_observer(fn):
    """Observador de proceso de las esperas de hueco (cualquier llamada, con o
    sin ui_progress). Recibe los mismos eventos que `on_queue`, en el hilo que
    espera, más "titulo" («LLM en cola: posición N, M en curso» / «LLM en cola:
    entró tras X s» / «… sin hueco tras X s»). Sirve para que el módulo de
    progreso registre una actividad de traza que empiece por «LLM en cola» sin
    acoplar la puerta al motor. Devuelve una función para quitarlo."""
    _OBSERVERS.append(fn)

    def remove():
        try:
            _OBSERVERS.remove(fn)
        except ValueError:
            pass
    return remove


def _titulo(event):
    if event.get("done"):
        return (f"LLM en cola: entró tras {event.get('waited_s', 0):.1f} s" if event.get("acquired")
                else f"LLM en cola: sin hueco tras {event.get('waited_s', 0):.1f} s")
    return (f"LLM en cola: posición {event.get('position') or '?'}, "
            f"{event.get('in_flight', 0)} en curso")


def _notify(progress, event):
    event = dict(event, titulo=_titulo(event))
    for observer in list(_OBSERVERS):
        try:
            observer(dict(event))
        except Exception:
            pass
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
    en un hilo y, al vencer, la llamada queda abandonada (como antes).

    `on_token(texto)` (opcional): streaming de la respuesta (ver `_with_tokens`).
    No cambia el contrato: nunca lanza, mismos status, mismo tiempo límite, y
    el dict devuelto trae el texto completo."""
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
        event = dict(queue_state(), purpose=purpose, done=False,
                     waited_s=round(time.perf_counter() - started, 2))
        _notify(progress, event)

    # Préstamo en Redis: dura lo que la llamada como mucho más un margen (si
    # el proceso muere, el hueco se recupera al vencer).
    lease_s = (float(timeout) + float(queue_wait) + 30.0) if timeout else None
    acquire_kwargs = dict(owner=progress.get("owner") if progress else None,
                          on_tick=on_tick if (_OBSERVERS or (ui_mode and progress.get("on_queue"))) else None,
                          lease_s=lease_s)
    STATS.llm_waiting(+1)
    permit = None
    try:
        backend = _backend()
        try:
            permit = backend.acquire(queue_wait, **acquire_kwargs)
        except Exception as error:
            if backend is _MEMORIA:
                raise
            remaining = max(0.0, float(queue_wait) - (time.perf_counter() - started))
            permit = _fallback(error, "acquire").acquire(remaining, **acquire_kwargs)
    except Exception:  # nunca debería pasar; el contrato es no lanzar
        permit = None
    finally:
        STATS.llm_waiting(-1)
    acquired = permit is not None
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

    on_token = kwargs.pop("on_token", None)
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
    box = {}
    call_kwargs = _with_tokens(provider, _accepted_kwargs(provider, call_kwargs), on_token, box)
    STATS.llm_begin(purpose)
    call_started = time.perf_counter()

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
            try:
                permit.release()
            except Exception:
                pass  # Redis: el préstamo vence solo

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

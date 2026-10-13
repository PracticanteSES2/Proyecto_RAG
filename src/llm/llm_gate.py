"""
Puerta única para las llamadas al LLM (MedGemma) desde el chatbot.

  * Tiempo límite REAL: se pasa `timeout` al proveedor, que lo aplica a nivel
    HTTP (MedGemmaProvider). Al vencer se cierra la conexión y Ollama deja de
    generar. Antes se usaba un hilo daemon + join(timeout): la petición seguía
    abierta (hasta MEDGEMMA_TIMEOUT=180 s) y el servidor seguía generando y
    ocupando un hueco; esas llamadas abandonadas se acumulaban.
  * Concurrencia acotada: semáforo de proceso (MEDGEMMA_MAX_CONCURRENT, 3 por
    defecto). Si no hay hueco en `queue_wait` segundos, la llamada no se hace
    y se devuelve status="llm_saturated" para degradar rápido (p. ej. resumen
    extractivo en la síntesis RAG).
  * Contadores para el diagnóstico (src/chatbot/runtime_stats.py).
"""
import inspect
import threading
import time

from src.chatbot.runtime_stats import STATS, env_float, env_int

_SEMAPHORE = None
_SEMAPHORE_SIZE = None
_SEMAPHORE_LOCK = threading.Lock()
_ABANDON_LOCK = threading.Lock()


def max_concurrent():
    return env_int("MEDGEMMA_MAX_CONCURRENT", 3)


def default_queue_wait():
    """Segundos que una llamada espera un hueco antes de rendirse."""
    return env_float("MEDGEMMA_QUEUE_WAIT", 3.0)


def _semaphore():
    global _SEMAPHORE, _SEMAPHORE_SIZE
    size = max_concurrent()
    with _SEMAPHORE_LOCK:
        if _SEMAPHORE is None or _SEMAPHORE_SIZE != size:
            # Cambiar el tamaño solo afecta a las llamadas nuevas (pruebas).
            _SEMAPHORE = threading.BoundedSemaphore(size)
            _SEMAPHORE_SIZE = size
        return _SEMAPHORE


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


def call_llm(provider, messages, purpose="otro", timeout=None, queue_wait=None, **kwargs):
    """Llama a `provider.chat(messages=..., **kwargs)` con semáforo, tiempo
    límite y contadores. Nunca lanza: devuelve el dict del proveedor o
    {"status": "llm_saturated" | "llm_error", "answer": None, ...}.

    `timeout` (s) es el presupuesto total (espera del hueco + llamada).
    `queue_wait` (s) es la espera máxima de un hueco (MEDGEMMA_QUEUE_WAIT por
    defecto, nunca más que `timeout`).

    Si el proveedor declara `enforces_timeout = True` (MedGemmaProvider) recibe
    `timeout` y lo aplica él (cierra la conexión al vencer). Si no, se espera
    en un hilo y, al vencer, la llamada queda abandonada (como antes)."""
    semaphore = _semaphore()
    started = time.perf_counter()
    if queue_wait is None:
        queue_wait = default_queue_wait()
    if timeout:
        queue_wait = min(float(queue_wait), float(timeout))

    STATS.llm_waiting(+1)
    try:
        acquired = semaphore.acquire(timeout=max(0.0, float(queue_wait)))
    finally:
        STATS.llm_waiting(-1)
    waited = round(time.perf_counter() - started, 2)
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
    budget = max(min(1.0, float(timeout)), float(timeout) - waited) if timeout else None
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
            semaphore.release()

    if budget is None or native:
        # El proveedor aplica el tiempo límite (MedGemmaProvider: a nivel HTTP,
        # cerrando la conexión) o no hay límite: llamada directa.
        run()
    else:
        # Proveedor sin tiempo límite propio (dobles de prueba, otros LLM): se
        # espera en un hilo. Si vence, la llamada sigue viva hasta terminar;
        # conserva su hueco del semáforo y cuenta como «abandonada».
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

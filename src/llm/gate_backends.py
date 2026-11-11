"""
Backends de coordinación de la puerta del LLM (src/llm/llm_gate.py).

Un backend implementa un semáforo JUSTO (FIFO) con posición en fila
consultable (`GateBackend`). Aquí vive solo el de memoria:

  * `MemoriaBackend` — dentro de un proceso (hilos). Es el de siempre.

El distribuido entre procesos y réplicas (`RedisBackend`: tickets FIFO con
INCR + ZSET, préstamos con TTL, latido de los que esperan, reloj de Redis)
vive en la capa de infraestructura del API,
`backend/app/services/puerta_llm_redis.py`, porque `src` no importa `redis`
(docs/ARQUITECTURA.md §4). El API lo registra al arrancar
(`puerta_llm_redis.instalar(url)` → `llm_gate.registrar_backend("redis", …)`)
y la puerta lo usa con LLM_GATE_BACKEND=redis.

Interfaz común (`GateBackend`):

    permiso = backend.acquire(wait_s, owner=None, on_tick=None, lease_s=None)
    permiso.release()            # si permiso no es None
    backend.state(ident=None)    # {"capacity","in_flight","waiting","position","ahead","backend"}

`acquire` y `state` pueden lanzar (Redis caído); quien llama (llm_gate) cae a
memoria y nunca deja que una excepción llegue al chatbot.
"""
import time
from typing import Callable, Protocol

from src.comun.entorno import env_int
from src.comun.estadisticas import FifoLine



def capacidad():
    return env_int("MEDGEMMA_MAX_CONCURRENT", 3)


class Permiso(Protocol):
    def release(self) -> None: ...


class GateBackend(Protocol):
    """Lo único que la puerta sabe de un backend (memoria o el de Redis del API)."""

    name: str

    def acquire(self, wait_s: float, owner=None, on_tick: Callable[[], None] | None = None,
                lease_s: float | None = None) -> Permiso | None: ...

    def state(self, ident=None) -> dict: ...


def estado_fila(capacity, in_flight, waiting, position, backend):
    """Dict de `state()` (común a todos los backends)."""
    return {
        "capacity": capacity,
        "in_flight": in_flight,
        "waiting": waiting,
        "position": position,
        "ahead": (in_flight + position - 1) if position else None,
        "backend": backend,
    }


class PermisoSimple:
    """Permiso que libera una sola vez (común a todos los backends)."""

    __slots__ = ("_release", "_done", "backend")

    def __init__(self, release, backend):
        self._release = release
        self._done = False
        self.backend = backend

    def release(self):
        if self._done:
            return
        self._done = True
        self._release()


# ======================================================================
# memoria
# ======================================================================

class MemoriaBackend:
    """Semáforo justo de proceso: capacidad leída en cada llamada
    (MEDGEMMA_MAX_CONCURRENT) y fila FIFO para las que esperan."""

    name = "memoria"

    def __init__(self, capacity_fn=capacidad):
        self.capacity_fn = capacity_fn
        self.line = FifoLine("medgemma")
        self.in_flight = 0

    def acquire(self, wait_s, owner=None, on_tick=None, lease_s=None, poll_s=None):
        capacity = self.capacity_fn()

        def ready():  # con el candado de la fila tomado
            if self.in_flight < capacity:
                self.in_flight += 1
                return True
            return False

        with self.line.cond:
            if self.line.is_empty_locked() and ready():
                return PermisoSimple(self._release, self.name)
        ticket = self.line.join(owner=owner)
        ok = self.line.wait_turn(
            ticket, ready, deadline=time.monotonic() + max(0.0, float(wait_s)),
            poll_s=poll_s or (0.5 if on_tick else 0.25), on_tick=on_tick,
        )
        return PermisoSimple(self._release, self.name) if ok else None

    def _release(self):
        with self.line.cond:
            self.in_flight = max(0, self.in_flight - 1)
            self.line.cond.notify_all()

    def state(self, ident=None):
        position = self.line.position(ident) if ident != -1 else None
        return estado_fila(self.capacity_fn(), self.in_flight, self.line.waiting(), position, self.name)

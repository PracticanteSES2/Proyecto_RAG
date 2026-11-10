"""
Backends de coordinación de la puerta del LLM (src/llm/llm_gate.py).

Ambos implementan un semáforo JUSTO (FIFO) con posición en fila consultable:

  * `MemoriaBackend` — dentro de un proceso (hilos). Es el de siempre.
  * `RedisBackend`   — entre procesos y réplicas (varios workers de la API,
    varias máquinas) contra un mismo servidor de MedGemma. Usa:

        <prefijo>:seq        contador de tickets (INCR → orden de llegada)
        <prefijo>:fila       ZSET ticket → nº de llegada (la fila FIFO)
        <prefijo>:vivos      ZSET ticket → vence (latido de los que esperan)
        <prefijo>:prestamos  ZSET ticket → vence (huecos ocupados, con TTL)

    Entrar = ser el primero de `fila` y que haya menos de `capacidad`
    préstamos vigentes; se hace con WATCH/MULTI (sin Lua: funciona igual con
    fakeredis en las pruebas). Los préstamos tienen TTL (`lease_s`): si un
    proceso muere con un hueco ocupado, el hueco se recupera al vencer. Quien
    espera renueva su latido; si muere esperando, su ticket se purga y no
    bloquea la fila. Los tiempos de vencimiento usan el reloj del servidor
    Redis (TIME), no el de cada máquina.

Interfaz común:

    permiso = backend.acquire(wait_s, owner=None, on_tick=None, lease_s=None)
    permiso.release()            # si permiso no es None
    backend.state(ident=None)    # {"capacity","in_flight","waiting","position","ahead","backend"}

`acquire` y `state` pueden lanzar (Redis caído); quien llama (llm_gate) cae a
memoria y nunca deja que una excepción llegue al chatbot.
"""
import logging
import os
import socket
import threading
import time
import uuid

from src.chatbot.runtime_stats import FifoLine, env_float, env_int

LOG = logging.getLogger("llm_gate")


def capacidad():
    return env_int("MEDGEMMA_MAX_CONCURRENT", 3)


def _state(capacity, in_flight, waiting, position, backend):
    return {
        "capacity": capacity,
        "in_flight": in_flight,
        "waiting": waiting,
        "position": position,
        "ahead": (in_flight + position - 1) if position else None,
        "backend": backend,
    }


class _Permiso:
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
                return _Permiso(self._release, self.name)
        ticket = self.line.join(owner=owner)
        ok = self.line.wait_turn(
            ticket, ready, deadline=time.monotonic() + max(0.0, float(wait_s)),
            poll_s=poll_s or (0.5 if on_tick else 0.25), on_tick=on_tick,
        )
        return _Permiso(self._release, self.name) if ok else None

    def _release(self):
        with self.line.cond:
            self.in_flight = max(0, self.in_flight - 1)
            self.line.cond.notify_all()

    def state(self, ident=None):
        position = self.line.position(ident) if ident != -1 else None
        return _state(self.capacity_fn(), self.in_flight, self.line.waiting(), position, self.name)


# ======================================================================
# redis
# ======================================================================

class RedisBackend:
    name = "redis"

    def __init__(self, client, prefix="llm_gate:medgemma", capacity_fn=capacidad,
                 lease_s=None, waiter_ttl_s=None, poll_s=None, process_id=None):
        self.r = client
        self.prefix = prefix
        self.capacity_fn = capacity_fn
        self.lease_s = float(lease_s or env_float("LLM_GATE_LEASE_S", 120.0))
        self.waiter_ttl_s = float(waiter_ttl_s or env_float("LLM_GATE_WAITER_TTL_S", 10.0))
        self.poll_s = float(poll_s or env_float("LLM_GATE_POLL_S", 0.2))
        self.process_id = process_id or f"{socket.gethostname()}:{os.getpid()}"
        self._local = {}  # ticket -> (ident, owner) de los que esperan en ESTE proceso
        self._local_lock = threading.Lock()
        self.k_seq = f"{prefix}:seq"
        self.k_fila = f"{prefix}:fila"
        self.k_vivos = f"{prefix}:vivos"
        self.k_prestamos = f"{prefix}:prestamos"

    # ------------------------------------------------------------------
    def _now(self):
        seconds, micros = self.r.time()
        return float(seconds) + float(micros) / 1e6

    def _purge(self, now):
        """Quita préstamos vencidos (procesos caídos con hueco) y tickets de
        espera sin latido (procesos caídos esperando)."""
        self.r.zremrangebyscore(self.k_prestamos, "-inf", now)
        dead = self.r.zrangebyscore(self.k_vivos, "-inf", now)
        if dead:
            pipe = self.r.pipeline()
            pipe.zrem(self.k_fila, *dead)
            pipe.zrem(self.k_vivos, *dead)
            pipe.execute()

    def _try_enter(self, ticket, capacity, lease_s):
        import redis

        with self.r.pipeline() as pipe:
            try:
                pipe.watch(self.k_fila, self.k_prestamos)
                head = pipe.zrange(self.k_fila, 0, 0)
                busy = pipe.zcard(self.k_prestamos)
                if not head or _text(head[0]) != ticket or busy >= capacity:
                    pipe.unwatch()
                    return False
                seconds, micros = pipe.time()
                now = float(seconds) + float(micros) / 1e6
                pipe.multi()
                pipe.zrem(self.k_fila, ticket)
                pipe.zrem(self.k_vivos, ticket)
                pipe.zadd(self.k_prestamos, {ticket: now + lease_s})
                pipe.execute()
                return True
            except redis.WatchError:
                return False

    def acquire(self, wait_s, owner=None, on_tick=None, lease_s=None, poll_s=None):
        capacity = self.capacity_fn()
        lease_s = float(lease_s or self.lease_s)
        poll_s = float(poll_s or self.poll_s)
        ticket = f"{self.process_id}:{uuid.uuid4().hex[:12]}"
        deadline = time.monotonic() + max(0.0, float(wait_s))
        seq = self.r.incr(self.k_seq)
        now = self._now()
        pipe = self.r.pipeline()
        pipe.zadd(self.k_vivos, {ticket: now + self.waiter_ttl_s})
        pipe.zadd(self.k_fila, {ticket: seq})
        pipe.execute()
        with self._local_lock:
            self._local[ticket] = (threading.get_ident(), owner)
        entered = False
        last_tick = None
        try:
            while True:
                now = self._now()
                self._purge(now)
                if self._try_enter(ticket, capacity, lease_s):
                    entered = True
                    return _Permiso(lambda: self._release(ticket), self.name)
                if time.monotonic() >= deadline:
                    return None
                # Latido: sigo esperando (si este proceso muere, el ticket vence).
                self.r.zadd(self.k_vivos, {ticket: now + self.waiter_ttl_s}, xx=True)
                if on_tick is not None and (last_tick is None or time.monotonic() - last_tick >= 0.5):
                    last_tick = time.monotonic()
                    try:
                        on_tick()
                    except Exception:
                        pass
                time.sleep(max(0.0, min(poll_s, deadline - time.monotonic())))
        finally:
            with self._local_lock:
                self._local.pop(ticket, None)
            if not entered:
                try:
                    pipe = self.r.pipeline()
                    pipe.zrem(self.k_fila, ticket)
                    pipe.zrem(self.k_vivos, ticket)
                    pipe.execute()
                except Exception:
                    pass  # el latido vencerá solo

    def _release(self, ticket):
        try:
            self.r.zrem(self.k_prestamos, ticket)
        except Exception as error:  # el préstamo vencerá solo (TTL)
            LOG.warning("llm_gate: no se pudo liberar el hueco en Redis (%s); vencerá en %.0f s",
                        error, self.lease_s)

    def _local_ticket(self, ident):
        with self._local_lock:
            for ticket, (thread, owner) in self._local.items():
                if thread == ident or owner == ident:
                    return ticket
        return None

    def state(self, ident=None):
        ident = threading.get_ident() if ident is None else ident
        now = self._now()
        pipe = self.r.pipeline()
        pipe.zcount(self.k_prestamos, now, "+inf")
        pipe.zcard(self.k_fila)
        in_flight, waiting = pipe.execute()
        position = None
        ticket = self._local_ticket(ident) if ident != -1 else None
        if ticket is not None:
            rank = self.r.zrank(self.k_fila, ticket)
            position = None if rank is None else int(rank) + 1
        return _state(self.capacity_fn(), int(in_flight), int(waiting), position, self.name)


def _text(value):
    return value.decode() if isinstance(value, bytes) else str(value)


def redis_desde_entorno():
    """Cliente Redis de REDIS_URL (redis://localhost:6379/0 por defecto) o
    excepción si no responde."""
    import redis

    url = os.getenv("REDIS_URL", "").strip() or "redis://localhost:6379/0"
    client = redis.Redis.from_url(url, socket_timeout=2.0, socket_connect_timeout=2.0)
    client.ping()
    return client

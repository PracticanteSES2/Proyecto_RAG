"""Semáforo justo de MedGemma entre procesos y réplicas, sobre Redis.

Adaptador de infraestructura de la puerta del LLM (src/llm/llm_gate.py): `src`
no importa `redis` (docs/ARQUITECTURA.md §4) y solo conoce el `Protocol`
`GateBackend` (src/llm/gate_backends.py). El API lo instala al arrancar:

    from backend.app.services import puerta_llm_redis
    puerta_llm_redis.instalar(ajustes.redis_url)      # + LLM_GATE_BACKEND=redis

`instalar` registra una fábrica en la puerta; la puerta la usa cuando
LLM_GATE_BACKEND=redis y, si Redis no responde, sigue en memoria con una
advertencia y reintenta cada 30 s (como antes). Con un cliente ya creado
(pruebas, fakeredis): `llm_gate.set_backend(RedisBackend(cliente, ...))`.

Claves (`<prefijo>` = llm_gate:medgemma):

    <prefijo>:seq        contador de tickets (INCR → orden de llegada)
    <prefijo>:fila       ZSET ticket → nº de llegada (la fila FIFO)
    <prefijo>:vivos      ZSET ticket → vence (latido de los que esperan)
    <prefijo>:prestamos  ZSET ticket → vence (huecos ocupados, con TTL)

Entrar = ser el primero de `fila` y que haya menos de `capacidad` préstamos
vigentes; se hace con WATCH/MULTI (sin Lua: funciona igual con fakeredis). Los
préstamos tienen TTL (`lease_s`): si un proceso muere con un hueco ocupado, el
hueco se recupera al vencer. Quien espera renueva su latido; si muere
esperando, su ticket se purga y no bloquea la fila. Los vencimientos usan el
reloj del servidor Redis (TIME). Variables: LLM_GATE_LEASE_S (120),
LLM_GATE_WAITER_TTL_S (10), LLM_GATE_POLL_S (0,2).
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid

import redis

from src.chatbot.runtime_stats import env_float
from src.llm import llm_gate
from src.llm.gate_backends import PermisoSimple, capacidad, estado_fila

LOG = logging.getLogger("llm_gate")


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

    def _join(self, ticket, owner):
        seq = self.r.incr(self.k_seq)
        now = self._now()
        pipe = self.r.pipeline()
        pipe.zadd(self.k_vivos, {ticket: now + self.waiter_ttl_s})
        pipe.zadd(self.k_fila, {ticket: seq})
        pipe.execute()
        with self._local_lock:
            self._local[ticket] = (threading.get_ident(), owner)

    def _leave(self, ticket, entered):
        with self._local_lock:
            self._local.pop(ticket, None)
        if entered:
            return
        try:
            pipe = self.r.pipeline()
            pipe.zrem(self.k_fila, ticket)
            pipe.zrem(self.k_vivos, ticket)
            pipe.execute()
        except Exception as error:  # el latido vencerá solo
            LOG.debug("llm_gate: no se pudo salir de la fila en Redis (%s); el ticket vencerá", error)

    def _tick(self, on_tick, last_tick):
        """Avisa a quien espera cada ~0,5 s; devuelve el instante del último aviso."""
        if on_tick is None or (last_tick is not None and time.monotonic() - last_tick < 0.5):
            return last_tick
        try:
            on_tick()
        except Exception as error:  # la UI nunca tumba la espera
            LOG.debug("llm_gate: on_tick falló (%s)", error)
        return time.monotonic()

    def acquire(self, wait_s, owner=None, on_tick=None, lease_s=None, poll_s=None):
        capacity = self.capacity_fn()
        lease_s = float(lease_s or self.lease_s)
        poll_s = float(poll_s or self.poll_s)
        ticket = f"{self.process_id}:{uuid.uuid4().hex[:12]}"
        deadline = time.monotonic() + max(0.0, float(wait_s))
        self._join(ticket, owner)
        entered = False
        last_tick = None
        try:
            while True:
                now = self._now()
                self._purge(now)
                if self._try_enter(ticket, capacity, lease_s):
                    entered = True
                    return PermisoSimple(lambda: self._release(ticket), self.name)
                if time.monotonic() >= deadline:
                    return None
                # Latido: sigo esperando (si este proceso muere, el ticket vence).
                self.r.zadd(self.k_vivos, {ticket: now + self.waiter_ttl_s}, xx=True)
                last_tick = self._tick(on_tick, last_tick)
                time.sleep(max(0.0, min(poll_s, deadline - time.monotonic())))
        finally:
            self._leave(ticket, entered)

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
        return estado_fila(self.capacity_fn(), int(in_flight), int(waiting), position, self.name)


def _text(value):
    return value.decode() if isinstance(value, bytes) else str(value)


def cliente_desde_url(url: str | None = None):
    """Cliente Redis (redis://localhost:6379/0 por defecto) o excepción si no responde."""
    client = redis.Redis.from_url(url or "redis://localhost:6379/0", socket_timeout=2.0,
                                  socket_connect_timeout=2.0)
    client.ping()
    return client


def instalar(url: str | None = None, prefix: str = "llm_gate:medgemma") -> None:
    """Registra el backend Redis en la puerta (lo usa con LLM_GATE_BACKEND=redis).
    La conexión se abre al elegirlo, no aquí: si Redis no responde, la puerta
    sigue en memoria y reintenta."""
    llm_gate.registrar_backend(
        "redis", lambda capacity_fn: RedisBackend(cliente_desde_url(url), prefix=prefix, capacity_fn=capacity_fn),
    )

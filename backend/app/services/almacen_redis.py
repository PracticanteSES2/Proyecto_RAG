"""Almacén en Redis (producción: API con varios procesos + un trabajador).

- `AlmacenRedis`: lado API, `redis.asyncio` (no bloquea el ciclo de eventos;
  el SSE espera con XREAD BLOCK).
- `AlmacenTrabajadorRedis`: lado trabajador, `redis` síncrono (hilos).

Estructuras y claves: ver `claves.py` y specs/006-api-backend/plan.md.
Requiere Redis >= 6.2 (Streams con grupos y XAUTOCLAIM).
"""
from __future__ import annotations

import json
import time
import uuid

from redis.exceptions import ResponseError

from backend.app.services.almacen import (
    ESTADOS_FINALES,
    a_json,
    ahora_iso,
    turno_a_hash,
    turno_de_hash,
)
from backend.app.services.claves import GRUPO_MOTORES, Claves

MAXLEN_COLA = 10_000
MAXLEN_EVENTOS = 2_000


def _txt(valor):
    return valor.decode("utf-8") if isinstance(valor, (bytes, bytearray)) else valor


def _json(valor, defecto=None):
    valor = _txt(valor)
    if not valor:
        return defecto
    try:
        return json.loads(valor)
    except ValueError:
        return defecto


def _ms() -> int:
    return int(time.time() * 1000)


# Libera el candado de la conversación solo si sigue siendo de ese turno.
_LIBERAR_SI_ES_MIO = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""


class AlmacenRedis:
    """Lado API (asíncrono)."""

    modo = "redis"

    def __init__(self, cliente, claves: Claves):
        self.r = cliente
        self.k = claves

    async def ping(self) -> bool:
        try:
            return bool(await self.r.ping())
        except Exception:
            return False

    async def cerrar(self) -> None:
        try:
            await self.r.aclose()
        except Exception:
            pass

    async def crear_conversacion(self, conversacion_id: str, ttl_s: int) -> None:
        ahora = ahora_iso()
        clave = self.k.conversacion(conversacion_id)
        async with self.r.pipeline(transaction=True) as tubo:
            tubo.hset(clave, mapping={"creada": ahora, "actualizada": ahora, "opciones": "[]", "frases": "[]"})
            tubo.expire(clave, ttl_s)
            await tubo.execute()

    async def conversacion(self, conversacion_id: str) -> dict | None:
        async with self.r.pipeline(transaction=False) as tubo:
            tubo.hgetall(self.k.conversacion(conversacion_id))
            tubo.lrange(self.k.mensajes(conversacion_id), 0, -1)
            tubo.get(self.k.activo(conversacion_id))
            meta, mensajes, activo = await tubo.execute()
        if not meta:
            return None
        meta = {_txt(k): _txt(v) for k, v in meta.items()}
        return {
            "conversacion_id": conversacion_id,
            "creada": meta.get("creada"), "actualizada": meta.get("actualizada"),
            "opciones": _json(meta.get("opciones"), []), "frases": _json(meta.get("frases"), []),
            "mensajes": [m for m in (_json(x) for x in mensajes) if isinstance(m, dict)],
            "turno_activo": _txt(activo),
        }

    async def reservar_turno(self, conversacion_id: str, turno_id: str, ttl_s: int) -> bool:
        return bool(await self.r.set(self.k.activo(conversacion_id), turno_id, nx=True, ex=ttl_s))

    async def liberar_reserva(self, conversacion_id: str, turno_id: str) -> None:
        clave = self.k.activo(conversacion_id)
        if _txt(await self.r.get(clave)) == turno_id:
            await self.r.delete(clave)

    async def encolar_turno(self, turno: dict, cola_max: int, ttl_s: int) -> bool:
        if await self.r.zcard(self.k.espera) >= cola_max:
            return False
        turno_id = turno["turno_id"]
        async with self.r.pipeline(transaction=True) as tubo:
            tubo.hset(self.k.turno(turno_id), mapping=turno_a_hash(turno))
            tubo.expire(self.k.turno(turno_id), ttl_s)
            tubo.zadd(self.k.espera, {turno_id: turno.get("creado_ms") or _ms()})
            tubo.xadd(self.k.cola, {"turno_id": turno_id}, maxlen=MAXLEN_COLA, approximate=True)
            await tubo.execute()
        return True

    async def turno(self, turno_id: str) -> dict | None:
        return turno_de_hash(await self.r.hgetall(self.k.turno(turno_id)))

    async def leer_eventos(self, turno_id: str, desde: str, bloqueo_ms: int) -> list[tuple[str, str, dict]]:
        argumentos = {"streams": {self.k.eventos(turno_id): desde or "0"}, "count": 100}
        if bloqueo_ms > 0:
            argumentos["block"] = bloqueo_ms
        respuesta = await self.r.xread(**argumentos)
        eventos = []
        for _, entradas in respuesta or []:
            for evento_id, campos in entradas:
                campos = {_txt(k): _txt(v) for k, v in campos.items()}
                eventos.append((_txt(evento_id), campos.get("evento") or "", _json(campos.get("datos"), {})))
        return eventos

    async def eventos_existen(self, turno_id: str) -> bool:
        return bool(await self.r.exists(self.k.eventos(turno_id)))

    async def posicion(self, turno_id: str) -> tuple[int, int]:
        async with self.r.pipeline(transaction=False) as tubo:
            tubo.zrank(self.k.espera, turno_id)
            tubo.zcard(self.k.en_curso)
            rango, en_curso = await tubo.execute()
        return (int(rango) + 1 if rango is not None else 0), int(en_curso or 0)

    async def resumen_cola(self) -> dict:
        async with self.r.pipeline(transaction=False) as tubo:
            tubo.zcard(self.k.espera)
            tubo.zcard(self.k.en_curso)
            espera, en_curso = await tubo.execute()
        return {"en_espera": int(espera or 0), "en_curso": int(en_curso or 0)}

    async def registrar_peticion(self, cliente: str, limite: int, ventana_s: int) -> float | None:
        """Ventana deslizante con un ZSET de marcas de tiempo. None = permitido;
        si no, segundos hasta que se libere un hueco."""
        clave = self.k.limite(cliente)
        ahora = time.time()
        miembro = f"{ahora:.6f}:{uuid.uuid4().hex[:8]}"
        async with self.r.pipeline(transaction=True) as tubo:
            tubo.zremrangebyscore(clave, 0, ahora - ventana_s)
            tubo.zadd(clave, {miembro: ahora})
            tubo.zcard(clave)
            tubo.expire(clave, ventana_s + 1)
            _, _, cuenta, _ = await tubo.execute()
        if cuenta <= limite:
            return None
        await self.r.zrem(clave, miembro)
        primero = await self.r.zrange(clave, 0, 0, withscores=True)
        mas_viejo = float(primero[0][1]) if primero else ahora
        return max(0.0, mas_viejo + ventana_s - ahora)

    async def marcar_calificacion(self, turno_id: str, calificacion: dict) -> bool:
        clave = self.k.turno(turno_id)
        if _json(await self.r.hget(clave, "calificacion")) == calificacion:
            return False
        await self.r.hset(clave, "calificacion", a_json(calificacion))
        return True

    async def leer_motor(self, nombre: str) -> dict | None:
        return _json(await self.r.get(self.k.motor(nombre)))


class AlmacenTrabajadorRedis:
    """Lado trabajador (síncrono, usado desde hilos: redis-py es seguro entre
    hilos con su pool de conexiones)."""

    modo = "redis"

    def __init__(self, cliente, claves: Claves, turno_ttl_s: int = 24 * 3600):
        self.r = cliente
        self.k = claves
        self.turno_ttl_s = turno_ttl_s
        self._liberar = self.r.register_script(_LIBERAR_SI_ES_MIO) if _admite_lua(cliente) else None
        self.asegurar_grupo()

    def asegurar_grupo(self) -> None:
        try:
            self.r.xgroup_create(self.k.cola, GRUPO_MOTORES, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    def _con_entrada(self, entrada_id, campos):
        campos = {_txt(k): _txt(v) for k, v in (campos or {}).items()}
        turno = turno_de_hash(self.r.hgetall(self.k.turno(campos.get("turno_id") or "")))
        if turno is None:  # expiró antes de atenderse
            self.r.xack(self.k.cola, GRUPO_MOTORES, entrada_id)
            self.r.zrem(self.k.espera, campos.get("turno_id") or "")
            return None
        turno["_entrada"] = _txt(entrada_id)
        return turno

    def tomar_turno(self, consumidor: str, bloqueo_ms: int) -> dict | None:
        try:
            respuesta = self.r.xreadgroup(GRUPO_MOTORES, consumidor, {self.k.cola: ">"}, count=1,
                                          block=max(1, bloqueo_ms))
        except ResponseError as error:
            if "NOGROUP" in str(error):  # la cola se borró (p. ej. FLUSHDB): se recrea
                self.asegurar_grupo()
                return None
            raise
        for _, entradas in respuesta or []:
            for entrada_id, campos in entradas:
                return self._con_entrada(entrada_id, campos)
        return None

    def confirmar(self, turno: dict) -> None:
        entrada = turno.get("_entrada")
        if entrada:
            self.r.xack(self.k.cola, GRUPO_MOTORES, entrada)
            self.r.xdel(self.k.cola, entrada)

    def recuperar_huerfanos(self, consumidor: str, inactivo_ms: int) -> list[dict]:
        """Turnos entregados a un trabajador que murió sin confirmarlos."""
        huerfanos, inicio = [], "0-0"
        while True:
            respuesta = self.r.xautoclaim(self.k.cola, GRUPO_MOTORES, consumidor, inactivo_ms,
                                          start_id=inicio, count=100)
            siguiente, entradas = _txt(respuesta[0]), respuesta[1]
            for entrada_id, campos in entradas:
                if campos is None:
                    continue
                turno = self._con_entrada(entrada_id, campos)
                if turno is not None:
                    huerfanos.append(turno)
            if not entradas or siguiente in ("0-0", inicio):
                return huerfanos
            inicio = siguiente

    def iniciar_turno(self, turno_id: str) -> None:
        with self.r.pipeline(transaction=True) as tubo:
            tubo.zrem(self.k.espera, turno_id)
            tubo.zadd(self.k.en_curso, {turno_id: _ms()})
            tubo.hset(self.k.turno(turno_id), mapping={"estado": "procesando", "iniciado_ms": str(_ms())})
            tubo.execute()

    def publicar_evento(self, turno_id: str, evento: str, datos: dict, ttl_s: int | None = None) -> str:
        clave = self.k.eventos(turno_id)
        with self.r.pipeline(transaction=True) as tubo:
            tubo.xadd(clave, {"evento": evento, "datos": a_json(datos)}, maxlen=MAXLEN_EVENTOS, approximate=True)
            tubo.expire(clave, ttl_s or self.turno_ttl_s)
            evento_id, _ = tubo.execute()
        return _txt(evento_id)

    def terminar_turno(self, turno: dict, campos: dict, eventos_ttl_s: int) -> None:
        turno_id = turno["turno_id"]
        campos = dict(campos)
        campos.setdefault("terminado_ms", _ms())
        with self.r.pipeline(transaction=True) as tubo:
            tubo.hset(self.k.turno(turno_id), mapping=turno_a_hash(campos))
            tubo.zrem(self.k.en_curso, turno_id)
            tubo.zrem(self.k.espera, turno_id)
            tubo.expire(self.k.eventos(turno_id), eventos_ttl_s)
            tubo.execute()
        if campos.get("estado") in ESTADOS_FINALES:
            self._liberar_activo(turno["conversacion_id"], turno_id)

    def _liberar_activo(self, conversacion_id, turno_id):
        clave = self.k.activo(conversacion_id)
        if self._liberar is not None:
            self._liberar(keys=[clave], args=[turno_id])
        elif _txt(self.r.get(clave)) == turno_id:
            self.r.delete(clave)

    def meta_conversacion(self, conversacion_id: str) -> dict:
        opciones, frases, creada = self.r.hmget(self.k.conversacion(conversacion_id), "opciones", "frases", "creada")
        return {"opciones": _json(opciones, []), "frases": _json(frases, []), "existe": creada is not None}

    def guardar_conversacion(self, conversacion_id: str, opciones: list, frases: list,
                             mensajes: list, estado_motor: bytes | None, ttl_s: int) -> None:
        conv = self.k.conversacion(conversacion_id)
        lista = self.k.mensajes(conversacion_id)
        motor = self.k.estado_motor(conversacion_id)
        with self.r.pipeline(transaction=True) as tubo:
            tubo.hsetnx(conv, "creada", ahora_iso())
            tubo.hset(conv, mapping={"opciones": a_json(opciones), "frases": a_json(frases),
                                     "actualizada": ahora_iso()})
            if mensajes:
                tubo.rpush(lista, *[a_json(m) for m in mensajes])
            if estado_motor is None:
                tubo.delete(motor)
            else:
                tubo.set(motor, estado_motor, ex=ttl_s)
            for clave in (conv, lista):
                tubo.expire(clave, ttl_s)
            tubo.execute()

    def cargar_estado_motor(self, conversacion_id: str) -> bytes | None:
        return self.r.get(self.k.estado_motor(conversacion_id))

    def cache_leer(self, clave: str) -> dict | None:
        return _json(self.r.get(self.k.cache(clave)))

    def cache_guardar(self, clave: str, valor: dict, ttl_s: int) -> None:
        self.r.set(self.k.cache(clave), a_json(valor), ex=ttl_s)

    def publicar_motor(self, nombre: str, datos: dict, ttl_s: int | None) -> None:
        self.r.set(self.k.motor(nombre), a_json(datos), ex=ttl_s or None)

    def estado_cola(self) -> dict:
        return {"en_espera": int(self.r.zcard(self.k.espera)), "en_curso": int(self.r.zcard(self.k.en_curso))}


def _admite_lua(cliente) -> bool:
    try:
        cliente.eval("return 1", 0)
        return True
    except Exception:
        return False  # fakeredis sin `lupa`: se usa GET + DEL

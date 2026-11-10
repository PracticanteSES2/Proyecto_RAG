"""Arma los servicios del backend según la configuración.

- Con `REDIS_URL` y Redis respondiendo: almacén Redis. El motor corre en el
  proceso trabajador (`python -m backend.worker`) salvo `MOTOR_MODO=embebido`.
- Sin `REDIS_URL` (o Redis caído al arrancar): almacén en memoria y el motor
  en hilos de la misma API (un solo proceso uvicorn), con advertencia.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from backend.app.core.config import RAIZ_REPO, Ajustes
from backend.app.services.claves import Claves

LOG = logging.getLogger(__name__)


@dataclass
class Servicios:
    ajustes: Ajustes
    almacen: object                     # AlmacenAPI
    almacen_trabajador: object | None   # AlmacenTrabajador (solo si el motor va embebido o en el trabajador)
    modo: str                           # "redis" | "memoria"
    embebido: bool
    trabajador: object | None = None
    version: str = ""


def _redis_disponible(url: str) -> bool:
    import redis

    try:
        cliente = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        cliente.ping()
        cliente.close()
        return True
    except Exception as error:
        LOG.warning("Redis no responde en REDIS_URL (%s); se usa el modo en memoria", type(error).__name__)
        return False


def crear_almacenes(ajustes: Ajustes, redis_api=None, redis_trabajador=None):
    """(almacén API, almacén trabajador, modo). Los clientes Redis se pueden
    inyectar (pruebas con fakeredis)."""
    if redis_api is not None or (ajustes.redis_url and _redis_disponible(ajustes.redis_url)):
        import redis
        import redis.asyncio

        from backend.app.services.almacen_redis import AlmacenRedis, AlmacenTrabajadorRedis

        claves = Claves(ajustes.redis_prefijo)
        redis_api = redis_api or redis.asyncio.Redis.from_url(ajustes.redis_url)
        redis_trabajador = redis_trabajador or redis.Redis.from_url(ajustes.redis_url)
        return (AlmacenRedis(redis_api, claves),
                AlmacenTrabajadorRedis(redis_trabajador, claves, ajustes.turno_ttl_s), "redis")
    from backend.app.services.almacen_memoria import AlmacenMemoria

    if not ajustes.redis_url:
        LOG.warning("REDIS_URL no definido: modo en memoria (un solo proceso; solo para desarrollo o un servidor "
                    "sin Redis). Con varios procesos uvicorn cada uno tendría su propio estado.")
    memoria = AlmacenMemoria()
    return memoria, memoria, "memoria"


def crear_trabajador(ajustes: Ajustes, almacen_trabajador, fabrica_piscina: Callable | None = None):
    """Construye la piscina de motores (lento) y el trabajador. `fabrica_piscina`
    permite inyectar un motor doble en pruebas."""
    from backend.app.services import cache as reglas_cache
    from backend.app.services.motor import SerializadorEstado, construir_piscina_real
    from backend.app.services.trabajador import Trabajador
    from backend.app.services.turnos import ProcesadorTurnos

    raiz = ajustes.rag_raiz_datos
    if fabrica_piscina is None:
        def fabrica_piscina():
            return construir_piscina_real(raiz, ajustes.motor_instancias)

    piscina = fabrica_piscina()
    # Precalienta el vocabulario del normalizador (el mismo que usa el motor):
    # el primer turno no paga su construcción (segundos con docs_tableros).
    reglas_cache.normalizar_pregunta("hola", raiz)
    huella = reglas_cache.Huella(raiz, RAIZ_REPO)
    procesador = ProcesadorTurnos(almacen_trabajador, piscina, SerializadorEstado(ajustes.backend_secreto), ajustes,
                                  huella=huella, raiz_datos=raiz)
    return Trabajador(almacen_trabajador, procesador, piscina, ajustes, version=huella.version, huella=huella)


def crear_servicios(ajustes: Ajustes, redis_api=None, redis_trabajador=None) -> Servicios:
    almacen, almacen_trabajador, modo = crear_almacenes(ajustes, redis_api, redis_trabajador)
    embebido = modo == "memoria" or ajustes.modo_embebido
    if modo == "memoria" and ajustes.motor_modo == "externo":
        # Con varios procesos uvicorn, embeber el motor en cada uno chocaría con
        # el candado de Qdrant: mejor no arrancar y que el servicio reintente.
        raise RuntimeError("MOTOR_MODO=externo requiere Redis y REDIS_URL no responde: la API no arranca")
    return Servicios(ajustes=ajustes, almacen=almacen, almacen_trabajador=almacen_trabajador, modo=modo,
                     embebido=embebido)

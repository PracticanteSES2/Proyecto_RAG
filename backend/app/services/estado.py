"""Salud, capacidades y diagnóstico vistos desde la API (lee lo que el
trabajador publica en el almacén; nunca toca el motor ni expone secretos)."""
from __future__ import annotations

import time
from datetime import datetime

CAPACIDADES_VACIAS = {"listo": False, "tableros_datos": [], "tableros_documentacion": [], "ejemplos": []}


async def capacidades(almacen) -> dict:
    datos = await almacen.leer_motor("capacidades")
    return dict(datos, listo=True) if datos else dict(CAPACIDADES_VACIAS)


def _hace_s(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return round(max(0.0, time.time() - datetime.fromisoformat(iso).timestamp()), 1)
    except ValueError:
        return None


EXTERNOS = ("medgemma", "powerbi", "indice")
COLA_VACIA = {"en_espera": 0, "en_curso": 0}


def _estado_redis(modo: str, redis_ok: bool | None, configurado_redis: bool) -> str:
    if modo == "redis":
        return "ok" if redis_ok else "caido"
    return "degradado" if configurado_redis else "no_configurado"


def _componentes_motor(latido: dict | None, embebido: bool) -> dict:
    """Motor y servicios externos SEGÚN EL ÚLTIMO LATIDO: el trabajador los
    chequea en segundo plano y con tiempo límite; aquí nunca se hace un ping."""
    if not latido:
        componentes = {"motor": {"estado": "iniciando" if embebido else "caido"}}
        componentes.update({nombre: {"estado": "desconocido"} for nombre in EXTERNOS})
        return componentes
    componentes = {"motor": {"estado": "ok", "instancias": latido.get("instancias"),
                             "ocupadas": latido.get("ocupadas"),
                             "latido_hace_s": _hace_s(latido.get("publicado"))}}
    componentes.update({nombre: dict(latido.get(nombre) or {"estado": "desconocido"}) for nombre in EXTERNOS})
    return componentes


def _estado_general(listo: bool, componentes: dict) -> str:
    if not listo:
        return "caido"
    sanos = all(c.get("estado") in ("ok", "no_configurado") for c in componentes.values())
    return "ok" if sanos else "degradado"


async def salud(almacen, modo: str, configurado_redis: bool, embebido: bool) -> dict:
    """`listo` = almacén accesible + motor con latido + índice no caído. No
    depende de MedGemma ni de Power BI (si caen, el estado es «degradado»)."""
    redis_ok = await almacen.ping() if modo == "redis" else None
    accesible = redis_ok is not False
    latido = await almacen.leer_motor("latido") if accesible else None
    cola = await almacen.resumen_cola() if accesible else dict(COLA_VACIA)
    componentes = {"redis": {"estado": _estado_redis(modo, redis_ok, configurado_redis)}}
    componentes.update(_componentes_motor(latido, embebido))
    listo = accesible and bool(latido) and componentes["indice"]["estado"] != "caido"
    return {"estado": _estado_general(listo, componentes), "listo": listo, "modo": modo,
            "componentes": componentes, "cola": cola, "version": (latido or {}).get("version")}


async def diagnostico(almacen) -> dict:
    datos = await almacen.leer_motor("diagnostico")
    if not datos:
        return {"disponible": False, "cola": await almacen.resumen_cola()}
    return dict(datos, disponible=True)

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


async def salud(almacen, modo: str, configurado_redis: bool, embebido: bool) -> dict:
    redis_ok = await almacen.ping() if modo == "redis" else None
    latido = await almacen.leer_motor("latido") if redis_ok is not False else None
    cola = await almacen.resumen_cola() if redis_ok is not False else {"en_espera": 0, "en_curso": 0}
    componentes = {
        "redis": {"estado": "ok" if redis_ok else ("caido" if modo == "redis" else
                                                   ("degradado" if configurado_redis else "no_configurado"))},
    }
    if latido:
        componentes["motor"] = {"estado": "ok", "instancias": latido.get("instancias"),
                                "ocupadas": latido.get("ocupadas"),
                                "latido_hace_s": _hace_s(latido.get("publicado"))}
        for nombre in ("medgemma", "powerbi", "indice"):
            componentes[nombre] = dict(latido.get(nombre) or {"estado": "desconocido"})
    else:
        estado_motor = "iniciando" if embebido else "caido"
        componentes["motor"] = {"estado": estado_motor}
        for nombre in ("medgemma", "powerbi", "indice"):
            componentes[nombre] = {"estado": "desconocido"}
    listo = redis_ok is not False and bool(latido) and componentes["indice"]["estado"] != "caido"
    if not listo:
        general = "caido"
    elif any(c.get("estado") not in ("ok", "no_configurado") for c in componentes.values()):
        general = "degradado"
    else:
        general = "ok"
    return {"estado": general, "listo": listo, "modo": modo, "componentes": componentes, "cola": cola,
            "version": (latido or {}).get("version")}


async def diagnostico(almacen) -> dict:
    datos = await almacen.leer_motor("diagnostico")
    if not datos:
        return {"disponible": False, "cola": await almacen.resumen_cola()}
    return dict(datos, disponible=True)

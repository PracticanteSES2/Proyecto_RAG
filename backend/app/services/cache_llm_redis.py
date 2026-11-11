"""Almacén Redis de la caché de llamadas al LLM del motor (src/chatbot/cache_llm.py).

`src` no importa `redis` (docs/ARQUITECTURA.md §4): el motor solo conoce el
`Protocol` `AlmacenCache`; el API instala este adaptador al arrancar, con el
mismo cliente síncrono que usan sus trabajadores:

    from backend.app.services import cache_llm_redis
    cache_llm_redis.instalar(cliente_redis, prefijo=ajustes.redis_prefijo)

Claves: `<prefijo>:llm:<sha256>` con TTL (SET EX). El valor es JSON con la
respuesta CRUDA del LLM (status, answer, model, done_reason…): nunca la
pregunta en claro ni datos de pacientes. La caché de RESPUESTAS completas del
API (`<prefijo>:cache:<huella>`) es otra y vive en `services/cache.py`.
"""
from __future__ import annotations

import json

from src.chatbot import cache_llm


class AlmacenRedis:
    nombre = "redis"

    def __init__(self, cliente, prefijo: str = "rag"):
        self.r = cliente
        self.prefijo = prefijo.rstrip(":")

    def _clave(self, clave: str) -> str:
        return f"{self.prefijo}:llm:{clave}"

    def leer(self, clave: str) -> dict | None:
        crudo = self.r.get(self._clave(clave))
        if crudo is None:
            return None
        valor = json.loads(crudo.decode("utf-8") if isinstance(crudo, bytes) else crudo)
        return valor if isinstance(valor, dict) else None

    def guardar(self, clave: str, valor: dict, ttl_s: float) -> None:
        self.r.set(self._clave(clave), json.dumps(valor, ensure_ascii=False), ex=max(1, int(ttl_s)))


def instalar(cliente, prefijo: str = "rag") -> AlmacenRedis:
    """Hace que la caché del motor use Redis (compartida por todos los workers)."""
    almacen = AlmacenRedis(cliente, prefijo=prefijo)
    cache_llm.configurar_almacen(almacen)
    return almacen

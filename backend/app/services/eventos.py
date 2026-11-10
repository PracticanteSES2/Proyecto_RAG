"""Flujo SSE de un turno (lado API, asíncrono).

Lee los eventos que el trabajador publica en el almacén (Redis Streams o
memoria) a partir de `desde` (Last-Event-ID), así que funciona aunque la API
tenga varios procesos y aunque el navegador se reconecte. Mientras el turno
espera en la fila emite `cola` (calculada aquí, sin id). Si el turno ya
terminó y sus eventos expiraron, reconstruye `respuesta`/`error` + `fin` del
estado final guardado.
"""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from backend.app.services.almacen import ESTADOS_FINALES

ERROR_EXPIRADO = {"mensaje": "Esa consulta ya no está disponible. Vuelve a enviarla, por favor.",
                  "codigo": "expirado"}
REINTENTO_MS = 3000


def formatear(evento: str, datos: dict, evento_id: str | None = None) -> str:
    lineas = [f"id: {evento_id}"] if evento_id else []
    lineas.append(f"event: {evento}")
    lineas.append("data: " + json.dumps(datos, ensure_ascii=False, default=str))
    return "\n".join(lineas) + "\n\n"


def _reconstruir(turno: dict) -> list[str]:
    if turno.get("respuesta"):
        salida = [formatear("respuesta", turno["respuesta"])]
    else:
        salida = [formatear("error", turno.get("error") or ERROR_EXPIRADO)]
    return salida + [formatear("fin", {})]


class _Cola:
    """Evento `cola` mientras el turno espera en la fila. Solo `cola` (sin la
    etapa «en_cola»): la interfaz lo muestra únicamente en modo diagnóstico."""

    def __init__(self):
        self._ultima = None

    def eventos(self, posicion: int, en_curso: int) -> list[str]:
        if posicion <= 0 or (posicion, en_curso) == self._ultima:
            return []
        self._ultima = (posicion, en_curso)
        return [formatear("cola", {"posicion": posicion, "en_curso": en_curso})]

async def flujo_eventos(almacen, turno_id: str, desde: str | None, desconectado: Callable[[], Awaitable[bool]],
                        bloqueo_ms: int = 1000, ping_s: float = 15.0) -> AsyncIterator[str]:
    yield f"retry: {REINTENTO_MS}\n\n"
    ultimo = desde or "0"
    cola = _Cola()
    ultimo_ping = time.monotonic()
    while not await desconectado():
        eventos = await almacen.leer_eventos(turno_id, ultimo, bloqueo_ms)
        for evento_id, nombre, datos in eventos:
            ultimo = evento_id
            yield formatear(nombre, datos, evento_id)
            if nombre == "fin":
                return
        if eventos:
            continue
        trozos, terminar = await _mientras_no_hay_eventos(almacen, turno_id, cola)
        for trozo in trozos:
            yield trozo
        if terminar:
            return
        if time.monotonic() - ultimo_ping >= ping_s:
            ultimo_ping = time.monotonic()
            yield ": ping\n\n"


async def _mientras_no_hay_eventos(almacen, turno_id: str, cola: _Cola) -> tuple[list[str], bool]:
    """(trozos SSE, terminar) cuando el stream no trae nada nuevo."""
    turno = await almacen.turno(turno_id)
    if turno is None:
        return [formatear("error", ERROR_EXPIRADO), formatear("fin", {})], True
    if turno.get("estado") in ESTADOS_FINALES and not await almacen.eventos_existen(turno_id):
        return _reconstruir(turno), True
    # `cola` solo en modo diagnóstico: en modo normal el primer evento visible es
    # `progreso` (la interfaz nunca habla de filas ni de otras consultas).
    if turno.get("estado") == "en_cola" and turno.get("diagnostico"):
        return cola.eventos(*await almacen.posicion(turno_id)), False
    return [], False

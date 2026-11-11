"""Compatibilidad: el estado de ejecución vive en ``src/comun/estadisticas.py``.

Se movió a la capa base para que ``src.providers`` y ``src.llm`` no importen ``src.chatbot``
(capa invertida, docs/ARQUITECTURA.md fase 1). Este módulo reexporta los mismos objetos
(``STATS``, ``TURN_LOCK``, ``TURN_LINE`` son los mismos, no copias). Código nuevo: importar de
``src.comun.estadisticas`` (o ``src.comun.entorno`` para ``env_int``/``env_float``).
"""
from src.comun.entorno import env_float, env_int
from src.comun.estadisticas import (
    _CACHE_EVENTS,
    _COST_FIELDS,
    CHARS_PER_TOKEN,
    RECENT_LATENCIES,
    STATS,
    TURN_LINE,
    TURN_LOCK,
    FifoLine,
    RuntimeStats,
    TurnBusy,
    _duration,
    _empty_queue_state,
    _Ticket,
    _turn_queue_state,
    degradation_lines,
    diagnostics_lines,
    open_connections,
    queue_snapshot,
    status_line,
    turn_lock_busy,
    turn_slot,
    turn_wait_limit,
)

__all__ = [
    "CHARS_PER_TOKEN", "_CACHE_EVENTS", "_COST_FIELDS", "RECENT_LATENCIES", "STATS", "TURN_LINE", "TURN_LOCK", "FifoLine", "RuntimeStats", "TurnBusy",
    "_Ticket", "_duration", "_empty_queue_state", "_turn_queue_state", "degradation_lines",
    "diagnostics_lines", "env_float", "env_int", "open_connections", "queue_snapshot", "status_line",
    "turn_lock_busy", "turn_slot", "turn_wait_limit",
]

"""Variables de entorno numéricas (destino de la fase 3, docs/ARQUITECTURA.md §10-§11).

`src.chatbot.runtime_stats` las reexporta con sus nombres de siempre. Un valor
vacío, inválido o no positivo vale `default`.
"""
import os


def env_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)
    return value if value > 0 else float(default)


def env_int(name: str, default: int) -> int:
    try:
        value = int(float(os.getenv(name, default)))
    except (TypeError, ValueError):
        return int(default)
    return value if value > 0 else int(default)

"""Lectura tolerante de variables de entorno numéricas (docs/ARQUITECTURA.md §11).

Un valor ausente, ilegible, cero o negativo vale ``default``: así un ``.env`` con un error de tipeo
no tumba el motor ni deja un límite en cero.
"""
from __future__ import annotations

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

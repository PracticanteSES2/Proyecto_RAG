"""Utilidades pequeñas sobre colecciones (docs/ARQUITECTURA.md §11)."""
from __future__ import annotations


def como_lista(valor) -> list:
    """``None`` → ``[]``; una lista se devuelve tal cual (la misma, no una copia); cualquier otro valor → ``[valor]``."""
    if valor is None:
        return []
    if isinstance(valor, list):
        return valor
    return [valor]

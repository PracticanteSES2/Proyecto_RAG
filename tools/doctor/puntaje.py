"""Puntaje 0-100 por categoría y por perfil.

Por categoría: P = Σ_(regla, severidad) peso_severidad · √n  y  puntaje = 100 · E / (E + P),
con E = `escala` de la categoría. La raíz hace que arreglar una regla entera valga más que
quitar una ocurrencia, pero cualquier hallazgo nuevo baja el puntaje (lo ve el trinquete).
"""
from __future__ import annotations

import math
from collections import Counter

from tools.doctor.modelo import Hallazgo


def penalizacion(hallazgos: list[Hallazgo], pesos: dict[str, float]) -> dict[str, float]:
    grupos = Counter((h.categoria, h.regla, h.severidad) for h in hallazgos)
    salida: dict[str, float] = {}
    for (cat, _, sev), n in grupos.items():
        salida[cat] = salida.get(cat, 0.0) + pesos[sev] * math.sqrt(n)
    return salida


def calcular(hallazgos: list[Hallazgo], categorias: dict[str, dict], pesos: dict[str, float],
             omitidas=()) -> tuple[dict[str, float], float | None]:
    p = penalizacion(hallazgos, pesos)
    puntajes = {}
    for cat, cfg in categorias.items():
        if cat in omitidas:
            continue
        e = float(cfg["escala"])
        puntajes[cat] = round(100.0 * e / (e + p.get(cat, 0.0)), 4)
    total = sum(categorias[c]["peso"] for c in puntajes)
    if not total:
        return puntajes, None
    return puntajes, round(sum(categorias[c]["peso"] * v for c, v in puntajes.items()) / total, 4)


def global_(perfiles: dict[str, float | None], pesos: dict[str, float]) -> float | None:
    presentes = {p: v for p, v in perfiles.items() if v is not None}
    total = sum(pesos.get(p, 0) for p in presentes)
    if not total:
        return None
    return round(sum(pesos.get(p, 0) * v for p, v in presentes.items()) / total, 4)

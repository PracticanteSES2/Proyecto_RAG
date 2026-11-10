"""Rutas canónicas del proyecto: la raíz, los datos locales y las carpetas efímeras de ``var/``.

Es la ÚNICA definición de la raíz (``Path(__file__).parents[...]``): el código nuevo la importa de
aquí en vez de recalcularla. ``var/`` está ignorada por git y se puede borrar entera en cualquier
momento (ver docs/ARQUITECTURA.md, «Lugares para lo efímero»):

    var/out/<suite>/...   salidas de evaluadores, bancos y regresiones (informes, resultados.json)
    var/logs/             logs de procesos y tareas programadas
    var/tmp/              temporales (copias de trabajo, sondeos de un uso)

``PROYECTO_VAR_DIR`` cambia la carpeta base (p. ej. para una corrida aislada). Las funciones solo
calculan rutas: no crean carpetas (quien escribe hace ``mkdir(parents=True, exist_ok=True)``).
"""
from __future__ import annotations

import os
from pathlib import Path, PurePath

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
DATOS = RAIZ_PROYECTO / "data"


def raiz_var() -> Path:
    propia = os.environ.get("PROYECTO_VAR_DIR")
    return Path(propia) if propia else RAIZ_PROYECTO / "var"


def _dentro(base: Path, partes: tuple[str, ...]) -> Path:
    for parte in partes:
        p = PurePath(str(parte))
        if p.is_absolute() or p.drive or p.root or ".." in p.parts:
            raise ValueError(f"parte de ruta no permitida en var/: {parte!r}")
    return base.joinpath(*map(str, partes))


def ruta_salida(*partes: str) -> Path:
    """``var/out/<partes>``: salidas de evaluadores y bancos."""
    return _dentro(raiz_var() / "out", partes)


def ruta_log(*partes: str) -> Path:
    """``var/logs/<partes>``: logs de procesos."""
    return _dentro(raiz_var() / "logs", partes)


def ruta_tmp(*partes: str) -> Path:
    """``var/tmp/<partes>``: temporales que se pueden borrar sin aviso."""
    return _dentro(raiz_var() / "tmp", partes)

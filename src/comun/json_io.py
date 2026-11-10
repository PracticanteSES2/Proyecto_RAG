"""Leer y escribir JSON del proyecto (UTF-8, ``ensure_ascii=False``, sangría 2): una sola implementación.

    leer_json(ruta)                     -> contenido; FileNotFoundError si no existe
    leer_json(ruta, None)               -> None si no existe (cualquier valor por defecto sirve)
    leer_json(ruta, bom=True)           -> tolera el BOM de UTF-8 (archivos de Power BI Desktop/PBIP)
    escribir_json(datos, ruta)          -> crea las carpetas y escribe (sin línea final, como siempre)
    escribir_json(datos, ruta, atomico=True)  -> temporal en la misma carpeta + os.replace

Ver docs/ARQUITECTURA.md §11. Las salidas son idénticas byte a byte a las de los lectores/escritores
que reemplaza (``tests/comun/test_json_io.py``).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

_SIN_DEFECTO = object()


def leer_json(ruta, defecto=_SIN_DEFECTO, *, bom: bool = False):
    """Contenido JSON de ``ruta``. Si se da ``defecto`` y el archivo no existe, devuelve ``defecto``."""
    ruta = Path(ruta)
    if defecto is not _SIN_DEFECTO and not ruta.exists():
        return defecto
    return json.loads(ruta.read_text(encoding="utf-8-sig" if bom else "utf-8"))


def _texto(datos, default) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=2, default=default)


def escribir_json(datos, ruta, *, atomico: bool = False, default=None) -> None:
    """Escribe ``datos`` en ``ruta`` creando las carpetas. ``default`` se pasa a ``json.dumps`` (p. ej. ``str``)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = _texto(datos, default)
    if not atomico:
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write(texto)
        return
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as archivo:
            archivo.write(texto)
        os.replace(tmp, ruta)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

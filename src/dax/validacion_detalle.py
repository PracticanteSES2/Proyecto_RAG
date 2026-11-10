"""Validación de la consulta DAX del listado de detalle (TOPN + SUMMARIZECOLUMNS).

Vivía en ``src/semantic/detail_list.py``; está en ``src/dax`` porque la usa ``DAXValidator`` y así ``src.dax``
no importa ``src.semantic`` (ciclo ``semantic ↔ dax``, docs/ARQUITECTURA.md fase 4). ``detail_list`` la
reexporta con los mismos nombres.
"""
import re

from src.comun.texto import llave

FORBIDDEN_PATTERNS = (r"\bDEFINE\b", r"\bINFO\.", r"\bEVALUATEANDLOG\b")


def mismo_nombre(a, b) -> bool:
    """Igualdad de nombres de tabla/columna sin tildes, mayúsculas ni separadores."""
    return llave(a) == llave(b)


def columnas_de_tabla(technical_catalog, table) -> list:
    """Columnas con nombre de ``table`` en el catálogo técnico ([] si la tabla no está)."""
    for item in (technical_catalog or {}).get("tables") or []:
        if mismo_nombre(item.get("name"), table):
            return [c for c in item.get("columns") or [] if c.get("name")]
    return []


def validate_detail_dax(dax, columns, technical_catalog, limit):
    """Validación de la consulta del listado (estructura fija generada por
    QueryPlanDAXGenerator.generate_detail): EVALUATE + TOPN con el tope,
    sin construcciones prohibidas y con columnas que existen en el modelo."""
    errors = []
    text = str(dax or "").strip()
    if not text.upper().startswith("EVALUATE"):
        errors.append("La consulta DAX debe comenzar con EVALUATE.")
    if not re.search(r"\bTOPN\s*\(\s*" + str(int(limit)) + r"\s*,", text):
        errors.append("La consulta del listado debe limitar las filas con TOPN.")
    if not re.search(r"\bSUMMARIZECOLUMNS\s*\(", text):
        errors.append("La consulta del listado no usa SUMMARIZECOLUMNS.")
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            errors.append(f"La consulta contiene una construcción no permitida: {pattern}")
    if technical_catalog:
        for column in columns or []:
            if not any(mismo_nombre(c.get("name"), column.get("column"))
                       for c in columnas_de_tabla(technical_catalog, column.get("table"))):
                errors.append(f"La columna {column.get('table')}[{column.get('column')}] no existe en el modelo.")
    if not columns:
        errors.append("El listado no tiene columnas.")
    return {"valid": not errors, "errors": errors, "dax": dax}

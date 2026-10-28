"""
Conversión de la documentación .md al JSON normalizado del RAG.

Un .md (formato.py) ya trae las secciones separadas y una entrada por hecho,
así que NO pasa por las heurísticas de document_normalizer (confunden títulos
como «CONSULTAS REALIZADAS» con secciones SQL): cada `Documento` se convierte
directamente al esquema de `normalize_dashboard`:

    name                 <- metadato «pagina» (o el título)
    description          <- nombre funcional + Propósito
    data_sources, indicators, visuals, business_rules, definitions, notes
                         <- una cadena «Nombre: texto» por entrada
    other_sections       <- Historial de cambios (una por entrada) y secciones
                            no estándar
    documented_measures  <- medidas citadas como [Medida] en Indicadores/Visuales

Así el chunk_builder produce un chunk por entrada de lista.
"""

from __future__ import annotations

import re

from .formato import (
    SECCION_HISTORIAL,
    Documento,
    normalizar_nombre,
)

ARCHIVO_GENERAL = "_general.md"
HEADING_HISTORIAL = SECCION_HISTORIAL

# Sección del .md -> campo del JSON normalizado (claves sin tildes ni mayúsculas).
SECCION_A_CAMPO = {
    normalizar_nombre("Fuentes de datos"): "data_sources",
    normalizar_nombre("Indicadores"): "indicators",
    normalizar_nombre("Visuales"): "visuals",
    normalizar_nombre("Reglas de negocio"): "business_rules",
    normalizar_nombre("Definiciones"): "definitions",
    normalizar_nombre("Observaciones"): "notes",
}

# Secciones donde una referencia [Medida] se toma como medida documentada.
SECCIONES_CON_MEDIDAS = {"indicators", "visuals"}

# «[Medida]» suelto: no precedido de nombre de tabla («TABLA[COLUMNA]» y
# «'TABLA'[COLUMNA]» son columnas, no medidas).
_MEDIDA_RE = re.compile(r"(?<![\w\]'\"])\[(?P<nombre>[^\[\]\n]{2,80})\]")


def _limpiar(texto) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def es_general(doc: Documento, archivo: str | None = None) -> bool:
    """Bloque General (`_general.md`): describe el tablero completo."""
    return doc.meta.get("bloque") == "General" or (archivo or "").lower() == ARCHIVO_GENERAL


def _entrada_como_texto(entrada) -> str:
    nombre = _limpiar(entrada.nombre)
    texto = _limpiar(entrada.texto)
    if nombre and texto:
        return f"{nombre}: {texto}"
    return nombre or texto


def _descripcion(doc: Documento) -> str:
    proposito = _limpiar(doc.proposito)
    funcional = _limpiar(doc.meta.get("nombre_funcional"))
    if funcional and normalizar_nombre(funcional) not in normalizar_nombre(proposito):
        funcional = funcional if funcional.endswith((".", "?", "!")) else funcional + "."
        return _limpiar(f"{funcional} {proposito}")
    return proposito


def medidas_citadas(texto: str) -> list[str]:
    """Nombres de medida citados como [Medida] (sin tabla delante)."""
    nombres = []
    for match in _MEDIDA_RE.finditer(str(texto or "")):
        nombre = _limpiar(match.group("nombre"))
        if nombre and nombre not in nombres:
            nombres.append(nombre)
    return nombres


def documento_a_tablero(
    doc: Documento,
    nombre: str | None = None,
    aliases: list | None = None,
    source_file: str | None = None,
) -> dict:
    """Tablero normalizado (mismo esquema que document_normalizer.normalize_dashboard)."""
    nombre = _limpiar(nombre) or _limpiar(doc.pagina)
    tablero = {
        "name": nombre,
        "aliases": [
            alias
            for alias in dict.fromkeys(_limpiar(a) for a in (aliases or []))
            if alias and normalizar_nombre(alias) != normalizar_nombre(nombre)
        ],
        "source_file": source_file,
        "description": _descripcion(doc),
        "sql_queries": [],
        "documented_measures": [],
        "calculated_columns": [],
        "filters": [],
        "visuals": [],
        "indicators": [],
        "business_rules": [],
        "definitions": [],
        "data_sources": [],
        "notes": [],
        "other_sections": [],
        # Metadatos del .md (versión, bloque, tablas...): no los usa el RAG,
        # pero quedan a mano para la interfaz y el diagnóstico.
        "md_metadata": dict(doc.meta),
    }

    historial = []
    vistas = set()
    for seccion, entradas in doc.secciones.items():
        clave = normalizar_nombre(seccion)
        if clave == normalizar_nombre(SECCION_HISTORIAL):
            historial.extend(entradas)
            continue
        campo = SECCION_A_CAMPO.get(clave)
        for entrada in entradas:
            texto = _entrada_como_texto(entrada)
            if not texto:
                continue
            if campo is None:
                # Sección no estándar: se conserva con su título.
                tablero["other_sections"].append({
                    "section": "other",
                    "heading": _limpiar(seccion),
                    "text": texto,
                })
                continue
            tablero[campo].append(texto)
            if campo in SECCIONES_CON_MEDIDAS:
                for medida in medidas_citadas(entrada.texto):
                    llave = normalizar_nombre(medida)
                    if llave in vistas:
                        continue
                    vistas.add(llave)
                    tablero["documented_measures"].append({
                        "table": None,
                        "name": medida,
                        "expression": None,
                        "description": texto,
                    })

    for entrada in historial:
        texto = _entrada_como_texto(entrada)
        if texto:
            tablero["other_sections"].append({
                "section": "history",
                "heading": HEADING_HISTORIAL,
                "text": texto,
            })

    return tablero

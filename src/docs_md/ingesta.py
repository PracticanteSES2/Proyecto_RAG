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

El diccionario de variables (bloque Diccionario, `_diccionario*.md`) usa el
mismo esquema pero con entradas estructuradas: Medidas -> documented_measures
(table, name, expression, description), Columnas calculadas -> calculated_columns,
Tablas -> data_sources, Columnas clave y Relaciones -> other_sections (con su
encabezado). El tablero lleva `is_dictionary: True` para que el enrutador y el
resolvedor de métricas no lo traten como una página.
"""

from __future__ import annotations

import re

from .formato import (
    SECCION_HISTORIAL,
    Documento,
    es_diccionario,
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

# Diccionario de variables: sección -> campo (las columnas clave y las
# relaciones, que no tienen campo propio, caen en other_sections con su título).
SECCION_DICCIONARIO_A_CAMPO = {
    normalizar_nombre("Tablas"): "data_sources",
    normalizar_nombre("Medidas"): "documented_measures",
    normalizar_nombre("Columnas calculadas"): "calculated_columns",
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


_MARCADOR_RE = re.compile(r"(?:(?<=\s)|^)(Unidad|Tabla|Clase|Tipo|Valores|Cálculo|Se usa en):\s")
_NOMBRE_COLUMNA_RE = re.compile(r"^(?P<tabla>[^\[\]]+)\[(?P<columna>[^\[\]]+)\]$")
_NOMBRE_MEDIDA_RE = re.compile(r"^\[(?P<medida>[^\[\]]+)\]$")
_CLAVE_CAMPO = {"Unidad": "unidad", "Tabla": "tabla", "Clase": "clase", "Tipo": "tipo", "Valores": "valores",
               "Cálculo": "calculo", "Se usa en": "se_usa_en"}


def nombre_diccionario(doc: Documento) -> str:
    """Nombre del «tablero» que representa al diccionario en el RAG:
    «DICCIONARIO <TABLERO>» (o «DICCIONARIO <TEMA> <TABLERO>»)."""
    return _limpiar(f"{doc.pagina} {doc.meta.get('tablero') or ''}")


def campos_entrada_diccionario(texto: str) -> dict:
    """Campos de una entrada de Medidas / Columnas calculadas:
    {descripcion, unidad, tabla, clase, tipo, valores, calculo, se_usa_en}. El DAX va entre comillas
    invertidas y puede contener cualquier texto; lo desconocido es None."""
    texto = _limpiar(texto)
    # Los marcadores se buscan con el DAX enmascarado (puede traer «Tabla: ...»).
    enmascarado = re.sub(r"`[^`]*`", lambda m: "x" * len(m.group(0)), texto)
    marcas = [(m.start(), m.end(), m.group(1)) for m in _MARCADOR_RE.finditer(enmascarado)]
    campos = {"descripcion": texto, **{v: None for v in _CLAVE_CAMPO.values()}}
    if not marcas:
        return campos
    campos["descripcion"] = texto[: marcas[0][0]].strip()
    for i, (_, fin, clave) in enumerate(marcas):
        valor = texto[fin: marcas[i + 1][0] if i + 1 < len(marcas) else len(texto)].strip()
        if clave == "Cálculo":
            m = re.match(r"`(.*)`\.?$", valor)
            valor = (m.group(1) if m else valor.rstrip(".")).strip()
            if valor.casefold().startswith("por confirmar"):
                valor = ""
        else:
            valor = valor.rstrip(".").strip()
        campos[_CLAVE_CAMPO[clave]] = valor or None
    return campos


def _descripcion_estructurada(campos: dict) -> str:
    """Descripción para el RAG: lo que mide, la unidad y dónde se usa (la tabla
    y el cálculo van en sus propios campos)."""
    partes = [campos["descripcion"]]
    for clave, etiqueta in (("unidad", "Unidad"), ("clase", "Clase"), ("tipo", "Tipo"), ("valores", "Valores"),
                            ("se_usa_en", "Se usa en")):
        if campos[clave]:
            partes.append(f"{etiqueta}: {campos[clave]}.")
    return _limpiar(" ".join(p for p in partes if p))


def _medida_diccionario(entrada) -> dict:
    nombre = _limpiar(entrada.nombre)
    m = _NOMBRE_MEDIDA_RE.match(nombre)
    campos = campos_entrada_diccionario(entrada.texto)
    return {
        "table": campos["tabla"],
        "name": m.group("medida").strip() if m else nombre,
        "expression": campos["calculo"],
        "description": _descripcion_estructurada(campos),
    }


def _columna_diccionario(entrada) -> dict:
    nombre = _limpiar(entrada.nombre)
    m = _NOMBRE_COLUMNA_RE.match(nombre)
    campos = campos_entrada_diccionario(entrada.texto)
    return {
        "table": m.group("tabla").strip() if m else campos["tabla"],
        "name": m.group("columna").strip() if m else nombre,
        "expression": campos["calculo"],
        "description": _descripcion_estructurada(campos),
    }


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
    diccionario = es_diccionario(doc.meta)
    if diccionario:
        tablero["is_dictionary"] = True

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
            if diccionario and clave in SECCION_DICCIONARIO_A_CAMPO:
                destino = SECCION_DICCIONARIO_A_CAMPO[clave]
                if destino == "documented_measures":
                    tablero[destino].append(_medida_diccionario(entrada))
                elif destino == "calculated_columns":
                    tablero[destino].append(_columna_diccionario(entrada))
                else:
                    tablero[destino].append(texto)
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

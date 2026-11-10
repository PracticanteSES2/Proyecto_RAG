"""
Agregaciones implícitas documentadas («suma de LAVANDERIA[Peso]»).

Un modelo sin medidas (p. ej. Tablero_lavanderia) muestra sus totales
agregando una columna en cada visual. Si el informe local no trae esos
visuales, la única evidencia es la documentación: el diccionario de variables
y las páginas de `docs_tableros/<tablero>/md/` (ingeridas en
`data/semantic_documents`). Este módulo extrae de esos textos las
agregaciones explícitas de una columna:

    «Peso: Peso total de ropa registrado: suma de LAVANDERIA[Peso] ...»
    «los totales se obtienen sumando LAVANDERIA[Peso]»
    «LAVANDERIA[Peso]: ... PESO TOTAL por Mes (suma de la columna)»

Solo se aceptan verbos de agregación explícitos (suma/sumando/promedio) junto a
una referencia `Tabla[Columna]`; la validación contra el modelo (columna
numérica que no es un identificador) la hace quien llama. Nada se inventa: sin
esa frase no hay indicador.
"""
import re

from src.comun.texto import normalizar

# Tabla entre comillas ('CAMAS DISPONIBLES') o sin comillas en mayúsculas o
# sin espacios (LAVANDERIA, ENPROCESO_FACTURACION, Calendario): «promedio
# mensual de FACTURACION[X]» no toma «mensual de» como parte de la tabla.
_TABLE = (
    r"(?:'(?P<qtable>[^'\[\]]+)'"
    r"|(?P<table>[A-ZÑ_][A-ZÑ0-9_]*(?:\s[A-ZÑ_][A-ZÑ0-9_]*)*|[A-Za-z_][A-Za-z0-9_]*))"
)
_REF = _TABLE + r"\s*\[(?P<column>[^\]\[]+)\]"
_COLUMN_WORD = r"(?:(?:de\s+)?(?:la\s+)?columna\s+)?"

AGGREGATION_PATTERNS = (
    (re.compile(
        r"(?<![A-Za-z])(?i:suma|sumando|sumar|sumatoria)\s+(?i:de\s+)?(?i:" + _COLUMN_WORD + r")" + _REF,
    ), "Sum"),
    (re.compile(
        r"(?<![A-Za-z])(?i:promedio|promediando|media)\s+(?i:de\s+)?(?i:" + _COLUMN_WORD + r")" + _REF,
    ), "Average"),
)
# Entrada del diccionario «T[C]: ... (suma de la columna)».
_ENTRY_RE = re.compile(r"^\s*" + _REF + r"\s*:\s*(?P<text>.+)$", re.DOTALL)


def _table_of(match):
    return (match.group("qtable") or match.group("table") or "").strip()
_SELF_AGGREGATION = (
    (re.compile(r"(?<![A-Za-z])(?:suma|sumando)\s+(?:de\s+)?(?:la\s+)?(?:propia\s+)?columna(?![A-Za-z])",
                re.IGNORECASE), "Sum"),
    (re.compile(r"(?<![A-Za-z])promedio\s+(?:de\s+)?(?:la\s+)?columna(?![A-Za-z])", re.IGNORECASE), "Average"),
)
# Nombre de un indicador documentado: «Nombre: descripción».
_NAME_RE = re.compile(r"^\s*(?P<name>[^:\[\]]{2,60}?)\s*:\s+")

# Campos de un tablero documentado donde se describen indicadores o columnas.
TEXT_FIELDS = (
    "description", "indicators", "other_sections", "notes", "business_rules",
    "definitions", "visuals", "data_sources",
)

DAX_FUNCTION = {"Sum": "SUM", "Average": "AVERAGE"}


def _normalize(value):
    return normalizar(value, "%")


def _texts(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _texts(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _texts(item)]
    return []


def aggregations_in_text(text):
    """[(tabla, columna, agregación)] explícitas de un texto."""
    text = " ".join(str(text or "").split())
    found = []
    for pattern, aggregation in AGGREGATION_PATTERNS:
        for match in pattern.finditer(text):
            found.append((_table_of(match), match.group("column").strip(), aggregation))
    entry = _ENTRY_RE.match(text)
    if entry:
        for pattern, aggregation in _SELF_AGGREGATION:
            if pattern.search(entry.group("text")):
                found.append((_table_of(entry), entry.group("column").strip(), aggregation))
    return list(dict.fromkeys(found))


def indicator_name(text, table, column):
    """«Peso total mensual» de «Peso total mensual: Suma de LAVANDERIA[Peso]...».
    None si el texto no empieza con un nombre o el nombre es la referencia."""
    match = _NAME_RE.match(" ".join(str(text or "").split()))
    if not match:
        return None
    return match.group("name").strip()


def documented_aggregations(documents):
    """Agregaciones implícitas documentadas por modelo.

    documents: documentos semánticos (dicts con «semantic_model» y
    «dashboards»). Devuelve [{model, model_norm, table, column, aggregation,
    names, pages, texts}] (una entrada por modelo + tabla + columna + agregación).
    """
    found = {}
    for document in documents or []:
        if not isinstance(document, dict):
            continue
        model = document.get("semantic_model")
        model_norm = _normalize(model)
        if not model_norm:
            continue
        for dashboard in document.get("dashboards") or []:
            if not isinstance(dashboard, dict):
                continue
            page = None if dashboard.get("is_dictionary") else (dashboard.get("name") or None)
            for field in TEXT_FIELDS:
                for text in _texts(dashboard.get(field)):
                    for table, column, aggregation in aggregations_in_text(text):
                        key = (model_norm, _normalize(table), _normalize(column), aggregation)
                        entry = found.setdefault(key, {
                            "model": model, "model_norm": model_norm, "table": table, "column": column,
                            "aggregation": aggregation, "names": [], "pages": [], "texts": [],
                        })
                        if field == "indicators":
                            name = indicator_name(text, table, column)
                            if name and name not in entry["names"]:
                                entry["names"].append(name)
                        if page and field in ("indicators", "visuals") and page not in entry["pages"]:
                            entry["pages"].append(page)
                        if text not in entry["texts"]:
                            entry["texts"].append(text)
    return list(found.values())


def aggregation_dax(table, column, aggregation):
    """Misma forma que el catálogo de visuales: SUM('LAVANDERIA'[Peso])."""
    escaped = str(table).replace("'", "''")
    return f"{DAX_FUNCTION[aggregation]}('{escaped}'[{column}])"


def friendly_label(aggregation, column):
    return f"{'Suma' if aggregation == 'Sum' else 'Promedio'} de {column}"


def text_cites_title(texts, title):
    """¿Algún texto documentado nombra tal cual el título de un visual?"""
    title_norm = _normalize(title)
    if len(title_norm) < 4:
        return False
    pattern = re.compile(r"(?<![a-z0-9])" + re.escape(title_norm) + r"(?![a-z0-9])")
    return any(pattern.search(_normalize(text)) for text in texts or [])

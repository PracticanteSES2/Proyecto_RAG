"""
Listado de detalle («total + listado») de un indicador que cuenta entidades.

«¿Cuántas camas hay disponibles en hospitalización general?» pide el total Y
la lista de esas camas (servicio y código de cama). Este módulo decide, con el
plan ya armado (indicador, filtros), si el indicador permite listar y con qué
columnas; ``QueryPlanDAXGenerator.generate_detail`` arma la consulta y
``QueryEngine`` la ejecuta (una sola consulta extra, después del total).

Reglas de columnas (en orden):

1. Entidad contada: la columna de COUNT / COUNTA / DISTINCTCOUNT de la medida
   ('CAMAS DISPONIBLES'[HCACODIGO] -> «CAMA») si parece un identificador o
   código (texto o nombre tipo código) y no es un dato de persona.
2. Con catálogo visual (``detail_tables`` del catálogo o, sin reconstruirlo,
   derivado de ``pages[].visuals[].fields`` que ya trae el catálogo actual):
   la tabla de detalle (tableEx) de ese modelo que muestra la entidad contada
   (o, para COUNTROWS, la tabla de la medida) aporta sus columnas simples con
   sus nombres de negocio (nativeQueryRef: «CAMA», «SERVICIO», «ASEGURADORA»).
3. Sin esa tabla (respaldo por reglas, sin reconstruir catálogos): una columna
   descriptiva de ubicación/servicio de la misma tabla (SERVICIOS, HSUNOMBRE,
   PISO, SEDE, UNIDAD...), las columnas filtradas con varios valores y la
   entidad. Una columna filtrada con un único valor no se repite (el valor ya
   está en la frase inicial), salvo la de ubicación.
4. Nunca: datos que identifican pacientes o personas (documento, cédula,
   nombres, teléfonos, ingreso...; ``PRIVATE_DETAIL_COLUMN_PARTS``), columnas
   técnicas (RowNumber, OID, columnas de orden sin nombre visible).

Mostrar datos de pacientes es una decisión del propietario del sistema: la
lista por defecto los excluye. ``POWERBI_DETAIL_ALLOWED_COLUMNS`` («TABLA[COL],
COL») permite columnas concretas y ``POWERBI_DETAIL_PRIVATE_COLUMNS`` agrega
partes de nombre a excluir. ``POWERBI_DETAIL_MAX_ROWS`` (50 por defecto) es el
tope de filas de la lista.
"""
import os
import re
import unicodedata

from src.semantic.answer_shape import detail_request

DEFAULT_MAX_ROWS = 50
DEFAULT_TIMEOUT_S = 30
MAX_DETAIL_COLUMNS = 6

# Partes del nombre (compacto: sin tildes, espacios ni signos) de columnas que
# identifican a una persona. Mostrarlas es decisión del propietario
# (POWERBI_DETAIL_ALLOWED_COLUMNS); por defecto nunca salen en un listado.
PRIVATE_DETAIL_COLUMN_PARTS = (
    "numdoc", "nrodoc", "documento", "cedula", "identif", "pacnom", "gpanom",
    "nombrepaciente", "pacientenombre", "nombrecomp", "nomcomp", "apellido",
    "telefon", "celular", "direccion", "correo", "email", "historia",
    "adningreso", "numingreso", "noingreso", "nroingreso", "paciente",
)
# Nombres completos (compactos) que también identifican a una persona.
PRIVATE_DETAIL_COLUMN_NAMES = {"ingreso", "nombre", "nombres", "usuario", "responsable", "cc", "tipodoc"}
# Columnas técnicas: nunca se listan.
_TECHNICAL_RE = re.compile(r"^(?:rownumber.*|oid.*|.*oid|id|orden.*|order.*|sort.*|indice|index)$")
# Columna de ubicación / servicio para el respaldo por reglas.
_LOCATION_WORDS = (
    "servicio", "servicios", "hsunombre", "unidad", "piso", "sede", "area", "ubicacion",
    "pabellon", "sala", "bloque",
)
# Nombre de columna con aspecto de código o identificador de la entidad.
_CODE_RE = re.compile(r"cod|codigo|numero|^num|nro|consec|^id|id$|cama|placa|serial|ingreso|radicado|folio")
_COUNT_RE = re.compile(
    r"\b(?P<function>DISTINCTCOUNTNOBLANK|DISTINCTCOUNT|COUNTA|COUNT)\s*\(\s*"
    r"(?:'(?P<qtable>(?:[^']|'')+)'|(?P<table>[A-Za-z_][\w ]*?))?\s*\[(?P<column>[^\]]+)\]\s*\)",
    re.IGNORECASE,
)
_COUNTROWS_RE = re.compile(
    r"\bCOUNTROWS\s*\(\s*(?:FILTER\s*\(\s*)?(?:'(?P<qtable>(?:[^']|'')+)'|(?P<table>[A-Za-z_][\w]*))",
    re.IGNORECASE,
)
_DETAIL_VISUAL_TYPES = {"tableex", "table"}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _fold(value):
    text = unicodedata.normalize("NFD", str(value or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def compact(value):
    return re.sub(r"[^a-z0-9]+", "", _fold(value))


def words(value):
    return set(re.sub(r"[^a-z0-9]+", " ", _fold(value)).split())


def _env_int(name, default, minimum=1):
    raw = os.getenv(name)
    try:
        return max(minimum, int(str(raw).strip())) if raw and str(raw).strip() else default
    except ValueError:
        return default


def detail_max_rows():
    """Tope de filas de la lista (POWERBI_DETAIL_MAX_ROWS, 50 por defecto)."""
    return _env_int("POWERBI_DETAIL_MAX_ROWS", DEFAULT_MAX_ROWS)


def detail_timeout_s():
    return _env_int("POWERBI_DETAIL_TIMEOUT_S", DEFAULT_TIMEOUT_S)


def _env_list(name):
    return [item.strip() for item in str(os.getenv(name) or "").split(",") if item.strip()]


def _allowed(table, column):
    for item in _env_list("POWERBI_DETAIL_ALLOWED_COLUMNS"):
        match = re.match(r"^'?(?P<table>[^'\[]*)'?\[(?P<column>[^\]]+)\]$", item)
        if match:
            if compact(match.group("table")) == compact(table) and compact(match.group("column")) == compact(column):
                return True
        elif compact(item) == compact(column):
            return True
    return False


def is_private_column(column, header=None, table=None):
    """¿La columna (o su nombre visible) identifica a una persona?

    Documento, cédula, nombres de paciente o usuario, teléfono, dirección,
    número de ingreso... Mostrarla es decisión del propietario: solo con
    POWERBI_DETAIL_ALLOWED_COLUMNS.
    """
    if _allowed(table, column):
        return False
    parts = tuple(PRIVATE_DETAIL_COLUMN_PARTS) + tuple(
        compact(item) for item in _env_list("POWERBI_DETAIL_PRIVATE_COLUMNS")
    )
    for name in (column, header):
        key = compact(name)
        if not key:
            continue
        if key in PRIVATE_DETAIL_COLUMN_NAMES or any(part and part in key for part in parts):
            return True
    return False


def is_technical_column(column, header=None):
    key = compact(column)
    if not key or _TECHNICAL_RE.match(key):
        return True
    return header is not None and not str(header).strip()


def _same(a, b):
    return compact(a) == compact(b)


# ---------------------------------------------------------------------------
# Entidad que cuenta la medida
# ---------------------------------------------------------------------------

def counted_entity(expression):
    """{"function", "table", "column"} de lo que cuenta la medida, o None.

    COUNT('CAMAS DISPONIBLES'[HCACODIGO]) -> HCACODIGO; CALCULATE(DISTINCTCOUNT(
    T[C]), FILTER(...)) -> C; COUNTROWS('T') -> tabla sin columna.
    """
    text = str(expression or "")
    match = _COUNT_RE.search(text)
    if match:
        table = match.group("qtable") or match.group("table")
        return {
            "function": match.group("function").upper(),
            "table": table.replace("''", "'").strip() if table else None,
            "column": match.group("column").strip(),
        }
    match = _COUNTROWS_RE.search(text)
    if match:
        table = match.group("qtable") or match.group("table")
        return {"function": "COUNTROWS", "table": table.replace("''", "'").strip(), "column": None}
    return None


def identifier_like(column, column_type=None, function=None):
    """¿La columna puede identificar cada registro contado? Sí: nombre de
    código (código, número de cama, folio, consecutivo...) o un DISTINCTCOUNT
    de texto (cuenta entidades distintas). No: una fecha, una cifra o un
    COUNT de una columna descriptiva (COUNT(T[ASEGURADOR]) cuenta filas, no
    aseguradoras: listar por ella no daría una fila por registro)."""
    if not column or column_type == "date":
        return False
    if _CODE_RE.search(compact(column)):
        return True
    return str(function or "").upper().startswith("DISTINCTCOUNT") and column_type in (None, "text")


# ---------------------------------------------------------------------------
# Catálogo visual: tablas de detalle y nombres de negocio
# ---------------------------------------------------------------------------

def detail_tables_from_pages(pages):
    """Tablas de detalle (tableEx/table) de un informe: columnas simples con su
    nombre visible (nativeQueryRef). Igual que ``detail_tables`` del catálogo
    visual nuevo, pero derivado del catálogo actual (sin reconstruirlo)."""
    tables = []
    for page in pages or []:
        for visual in page.get("visuals") or []:
            if compact(visual.get("visual_type")) not in _DETAIL_VISUAL_TYPES:
                continue
            columns = []
            for field in visual.get("fields") or []:
                if field.get("kind") != "column" or not field.get("column"):
                    continue
                header = field.get("native_query_ref")
                if header is None:
                    header = field.get("display_name")
                columns.append({
                    "table": field.get("table"), "column": field.get("column"),
                    "header": header if header is not None else field.get("column"),
                })
            if len(columns) >= 2:
                tables.append({
                    "page_name": page.get("page_name"),
                    "page_display_name": page.get("page_display_name"),
                    "visual_id": visual.get("visual_id"),
                    "visual_title": visual.get("visual_title"),
                    "visual_type": visual.get("visual_type"),
                    "columns": columns,
                })
    return tables


def _reports_of_model(visual_catalog, semantic_model):
    reports = (visual_catalog or {}).get("reports") or []
    if not reports and (visual_catalog or {}).get("pages"):
        reports = [visual_catalog]
    return [r for r in reports if _same(r.get("semantic_model"), semantic_model)]


def model_detail_tables(visual_catalog, semantic_model):
    """Tablas de detalle del modelo: ``detail_tables`` si el catálogo ya las
    trae (catálogo reconstruido) o derivadas de sus páginas."""
    tables = []
    for report in _reports_of_model(visual_catalog, semantic_model):
        found = report.get("detail_tables")
        if found is None:
            found = detail_tables_from_pages(report.get("pages"))
        for item in found or []:
            tables.append({**item, "report": report.get("report")})
    return tables


def business_names(visual_catalog, semantic_model):
    """{(tabla, columna): nombre visible} y {columna: nombre visible} de las
    columnas que algún visual del modelo muestra con nombre de negocio."""
    by_table, by_column = {}, {}
    for report in _reports_of_model(visual_catalog, semantic_model):
        for page in report.get("pages") or []:
            for visual in page.get("visuals") or []:
                preferred = compact(visual.get("visual_type")) in _DETAIL_VISUAL_TYPES
                for field in visual.get("fields") or []:
                    if field.get("kind") != "column" or not field.get("column"):
                        continue
                    header = str(field.get("native_query_ref") or field.get("display_name") or "").strip()
                    if not header or _same(header, field.get("column")):
                        continue
                    key = (compact(field.get("table")), compact(field.get("column")))
                    if key not in by_table or preferred:
                        by_table[key] = header
                    if compact(field.get("column")) not in by_column or preferred:
                        by_column[compact(field.get("column"))] = header
    return by_table, by_column


def readable_header(table, column, names, fallback=None):
    by_table, by_column = names
    header = by_table.get((compact(table), compact(column))) or by_column.get(compact(column))
    if header:
        return header
    if fallback:
        return str(fallback).upper()
    return str(column).replace("_", " ").strip().upper()


# ---------------------------------------------------------------------------
# Plan del listado
# ---------------------------------------------------------------------------

def _table_columns(technical_catalog, table):
    for item in (technical_catalog or {}).get("tables") or []:
        if _same(item.get("name"), table):
            return [c for c in item.get("columns") or [] if c.get("name")]
    return []


def _is_location(column, header):
    found = words(column) | words(header) | {compact(column)}
    return any(word in found for word in _LOCATION_WORDS)


def _column_type(builder, model, table, column):
    getter = getattr(builder, "_column_type", None)
    try:
        return getter(model, table, column) if callable(getter) else None
    except Exception:
        return None


def _technical_catalog(builder, model):
    getter = getattr(builder, "_technical_catalog", None)
    try:
        return getter(model) if callable(getter) else {}
    except Exception:
        return {}


def metric_expression(metric):
    return str(metric.get("model_expression") or metric.get("expression") or metric.get("dax_expression") or "")


_SUM_RE = re.compile(
    r"^\s*SUM\s*\(\s*(?:'(?P<qtable>(?:[^']|'')+)'|(?P<table>[A-Za-z_][\w ]*?))\s*\[(?P<column>[^\]]+)\]\s*\)\s*$",
    re.IGNORECASE,
)
COUNT_FUNCTIONS = {"COUNT", "COUNTA", "DISTINCTCOUNT", "DISTINCTCOUNTNOBLANK", "COUNTROWS"}


def listable_entity(metric, builder=None, counting_only=False):
    """Entidad que permite listar el indicador, o None.

    - Conteo de un código (COUNT/DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO])):
      {"function", "table", "column"}; la columna se muestra.
    - Conteo de un identificador técnico (DISTINCTCOUNT(T[OID_SOLICITUD])) o
      COUNTROWS(T): cuenta registros de T, pero el identificador no se muestra
      ("hidden": True); las columnas visibles salen de la tabla de detalle del
      catálogo.
    - SUM(T[c]) simple (PRODUCTOS VENCIDOS = SUM(cantidad)): con
      ``counting_only=False`` es listable por filas de T con su cantidad
      ("aggregate": True); solo con una lista pedida explícitamente y con tabla
      de detalle en el catálogo (lo decide plan_detail).
    """
    expression = metric_expression(metric)
    entity = counted_entity(expression)
    if not entity:
        match = None if counting_only else _SUM_RE.match(expression)
        if not match:
            return None
        table = (match.group("qtable") or match.group("table") or "").replace("''", "'").strip()
        return {"function": "SUM", "table": table or metric.get("table"), "column": None,
                "value_column": match.group("column").strip(), "aggregate": True}
    model = metric.get("semantic_model")
    table = entity.get("table") or metric.get("table")
    entity = {**entity, "table": table}
    if entity["column"] is None:
        return entity
    if is_technical_column(entity["column"]):
        # OID / consecutivo técnico: identifica cada registro aunque no se muestre.
        return {**entity, "hidden": True} if entity["function"].startswith("DISTINCTCOUNT") else None
    if not identifier_like(entity["column"], _column_type(builder, model, table, entity["column"]),
                           entity.get("function")):
        return None
    return entity


def entity_matches_metric(entity_word, metric):
    """«camas» nombra al indicador: su etiqueta, su tabla o sus alias contienen
    la palabra (singular o plural)."""
    from src.semantic.request_phrases import singular

    word = _fold(entity_word)
    if not word:
        return False
    forms = {word, singular(word)}
    texts = [metric.get("label"), metric.get("table"), metric.get("measure"), *(metric.get("aliases") or [])]
    found = set()
    for text in texts:
        for token in words(text):
            found |= {token, singular(token)}
    return bool(forms & found)


def _filter_columns(plan, table):
    """Filtros categóricos (no temporales) de la consulta sobre `table`."""
    result = []
    for item in plan.get("filters") or []:
        if item.get("type") != "categorical" or item.get("temporal"):
            continue
        if str(item.get("source") or "") == "query_plan_temporal" or not item.get("column"):
            continue
        if table and not _same(item.get("table"), table):
            continue
        values = item.get("values") if item.get("value") in (None, "") else [item.get("value")]
        result.append({**item, "_values": [v for v in values or [] if v not in (None, "")]})
    return result


def _pick_catalog_table(tables, entity):
    """Tabla de detalle del catálogo que muestra la entidad contada (o, con
    COUNTROWS, la que tiene más columnas de la tabla de la medida)."""
    best, best_score = None, 0
    for item in tables:
        columns = item.get("columns") or []
        same_table = [c for c in columns if _same(c.get("table"), entity["table"])]
        if entity.get("column") and not entity.get("hidden"):
            if not any(_same(c.get("column"), entity["column"]) for c in same_table):
                continue
        score = len(same_table) * 2 - (len(columns) - len(same_table))
        if score > best_score:
            best, best_score = item, score
    return best


def plan_detail(plan, builder=None, visual_catalog=None, question=None):
    """Columnas del listado para un plan escalar, o {"status": ..., "reason"}.

    Devuelve {"status": "ready", "entity": {...}, "columns": [{"table",
    "column", "header", "role"}], "source": "catalogo"|"reglas", "visual":
    título/página o None, "excluded_private": [nombres], "request": {...}}.
    """
    request = detail_request(question if question is not None else plan.get("question"))
    if not request:
        return {"status": "not_requested"}
    if plan.get("mode") != "scalar" or plan.get("group_by") or plan.get("ranking") or plan.get("temporal_buckets"):
        return {"status": "not_requested", "reason": "grouped"}
    metric = plan.get("metric") or {}
    entity = listable_entity(metric, builder)
    if entity and entity.get("aggregate") and request.get("strength") != "explicit":
        # «¿Cuántas unidades … hay?» con una suma: el total basta.
        return {"status": "not_requested", "reason": "sum_without_explicit_list"}
    if not entity:
        return {"status": "not_listable", "reason": "measure_without_entity", "request": request}
    model = plan.get("semantic_model") or metric.get("semantic_model")
    catalog = visual_catalog if visual_catalog is not None else getattr(builder, "visual_catalog", None)
    names = business_names(catalog, model)
    technical = _technical_catalog(builder, model)
    excluded = []
    columns = []

    def add(table, column, role, header=None, hidden=False):
        if not table or not column:
            return
        if any(_same(c["table"], table) and _same(c["column"], column) for c in columns):
            return
        header = header if header not in (None, "") else readable_header(table, column, names)
        if is_private_column(column, header, table):
            if header not in excluded:
                excluded.append(str(header))
            return
        if is_technical_column(column, header) and not hidden:
            return
        item = {"table": table, "column": column, "header": str(header).strip(), "role": role}
        if hidden:
            # Identificador técnico: una fila por registro, pero no se muestra.
            item["hidden"] = True
        columns.append(item)

    filters = _filter_columns(plan, entity["table"])
    source, visual = "reglas", None
    chosen = _pick_catalog_table(model_detail_tables(catalog, model), entity)
    if chosen is not None:
        source = "catalogo"
        visual = " › ".join(str(p) for p in (
            chosen.get("report"), chosen.get("page_display_name"), chosen.get("visual_title"),
        ) if p)
        for column in chosen.get("columns") or []:
            if len(columns) >= MAX_DETAIL_COLUMNS:
                break
            # Columnas de fecha/hora del visual sí se listan; las de otra
            # tabla también (el visual ya las relaciona con la entidad).
            add(column.get("table"), column.get("column"), "visual", column.get("header"))
        for item in filters:
            if len(item["_values"]) > 1:
                add(item["table"], item["column"], "filter", item.get("concept"))
        if entity.get("column"):
            add(entity["table"], entity["column"], "entity", hidden=bool(entity.get("hidden")))
    else:
        if entity.get("column") is None or entity.get("hidden"):
            return {"status": "not_listable", "reason": "entity_without_detail_visual", "request": request}
        location = next((
            item for item in filters
            if _is_location(item["column"], readable_header(item["table"], item["column"], names, item.get("concept")))
        ), None)
        if location is not None:
            add(location["table"], location["column"], "location", location.get("concept"))
        else:
            for column in _table_columns(technical, entity["table"]):
                name = column.get("name")
                header = readable_header(entity["table"], name, names)
                if _same(name, entity["column"]) or not _is_location(name, header):
                    continue
                if is_private_column(name, header, entity["table"]) or is_technical_column(name):
                    continue
                if _column_type(builder, model, entity["table"], name) not in (None, "text"):
                    continue
                add(entity["table"], name, "location", header)
                break
        for item in filters:
            if len(item["_values"]) > 1:
                add(item["table"], item["column"], "filter", item.get("concept"))
        add(entity["table"], entity["column"], "entity")
    if not any(not c.get("hidden") for c in columns):
        return {"status": "not_listable", "reason": "only_private_columns", "excluded_private": excluded,
                "request": request}
    entity_header = None
    if entity.get("column"):
        entity_header = readable_header(entity["table"], entity["column"], names)
    return {
        "status": "ready", "request": request, "entity": {**entity, "header": entity_header},
        "columns": columns, "source": source, "visual": visual, "excluded_private": excluded,
        "entity_shown": any(
            _same(c["table"], entity["table"]) and _same(c["column"], entity.get("column")) and not c.get("hidden")
            for c in columns
        ),
    }


# ---------------------------------------------------------------------------
# Validación de la consulta del listado
# ---------------------------------------------------------------------------

FORBIDDEN_PATTERNS = (r"\bDEFINE\b", r"\bINFO\.", r"\bEVALUATEANDLOG\b")


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
            if not any(_same(c.get("name"), column.get("column"))
                       for c in _table_columns(technical_catalog, column.get("table"))):
                errors.append(f"La columna {column.get('table')}[{column.get('column')}] no existe en el modelo.")
    if not columns:
        errors.append("El listado no tiene columnas.")
    return {"valid": not errors, "errors": errors, "dax": dax}


# ---------------------------------------------------------------------------
# Filas del resultado
# ---------------------------------------------------------------------------

def _row_cell(row, table, column):
    """Valor de T[C] en una fila de ADOMD («CAMAS DISPONIBLES[HCACODIGO]»)."""
    suffix = "[" + compact(column) + "]"
    fallback = None
    for key, value in (row or {}).items():
        key_text = str(key)
        if "__value" in key_text.lower():
            continue
        head, _, tail = key_text.rpartition("[")
        if "[" + compact(tail.rstrip("]")) + "]" != suffix:
            continue
        if not head or _same(head.strip("'"), table):
            return value
        fallback = value if fallback is None else fallback
    return fallback


def _row_count(row):
    for key, value in (row or {}).items():
        if "__value" in str(key).lower():
            return value
    return None


def _number(value):
    try:
        return float(str(value).replace(",", ".")) if value not in (None, "") else None
    except ValueError:
        return None


def detail_rows(rows, columns, cap):
    """(filas como listas de celdas, cantidades por fila, recortada)."""
    cells, counts = [], []
    for row in rows or []:
        cells.append([_row_cell(row, c["table"], c["column"]) for c in columns])
        counts.append(_number(_row_count(row)))
    truncated = len(cells) > cap
    return cells[:cap], counts[:cap], truncated, counts


def consistency(total, counts, truncated, function):
    """Coherencia del listado con el total: "ok" | "mismatch" | "constant" | "unknown".

    Sin recortar, la suma de las cantidades por fila de un conteo aditivo
    (COUNT/COUNTA/COUNTROWS, o DISTINCTCOUNT con la entidad en la fila) es el
    total. Si todas las filas valen el total, la medida no responde al detalle
    (p. ej. usa ALL): el listado no sería coherente.
    """
    total = _number(total)
    values = [c for c in counts if c is not None]
    if total is None or not values:
        return "unknown"
    if len(values) > 1 and all(abs(v - total) < 1e-9 for v in values) and total > 1:
        return "constant"
    if truncated:
        return "unknown"
    return "ok" if abs(sum(values) - total) < 1e-6 else "mismatch"

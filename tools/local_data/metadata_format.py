"""
Formato de data/model_metadata/<slug>/ tal como lo deja Power BI.

Representación intermedia común (dicts) de un modelo semántico y escritura de
tables.csv / columns.csv / measures.csv / relationships.csv con las MISMAS
columnas y convenciones que EVALUATE INFO.VIEW.TABLES()/COLUMNS()/MEASURES()/
RELATIONSHIPS() (referencia: commit 3bf7b9f,
data/model_metadata/tablero_de_atenciones_institucionales/*.csv):

- separador ';', cabecera sin comillas, fin de línea CRLF (también dentro de
  los valores multilínea), UTF-8 sin BOM;
- textos siempre entre comillas dobles (comillas internas duplicadas),
  booleanos True/False y enteros sin comillas (vacío si no hay valor);
- cada tabla trae su columna oculta RowNumber-2662979B-...;
- IsUnique=True (e IsNullable=False) solo en RowNumber y en las columnas del
  lado "uno" de alguna relación; las relaciones 1:1 aparecen dos veces
  (una por sentido) con el mismo ID;
- LocalDateTable_* / DateTableTemplate_* se exportan (ocultas) como hace
  INFO.VIEW; no se filtran.

Los lectores del proyecto (catalog_utils.load_csv, visual_catalog_builder.
read_csv_rows) aceptan tanto este formato como el CSV con comas/BOM que
escribe sync_powerbi_metadata.write_csv.
"""
import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# NOMBRES / SLUGS (idénticos a sync_powerbi_metadata.py)
# ============================================================

def normalize_text(value):
    value = str(value or "").strip().lower()
    value = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def slugify(value):
    """Misma regla que sync_powerbi_metadata.slugify (carpeta del modelo)."""
    text = normalize_text(value)
    return text.replace(" ", "_") or "sin_nombre"


# ============================================================
# COLUMNAS DE INFO.VIEW (orden y tipo de cada campo)
# ============================================================

INFO_VIEW_SCHEMA = {
    "tables.csv": [
        ("ID", "int"), ("Name", "str"), ("Model", "str"),
        ("DataCategory", "str"), ("Description", "str"),
        ("IsHidden", "bool"), ("StorageMode", "str"),
        ("TableStorage", "str"), ("Expression", "str"),
        ("ShowAsVariationOnly", "bool"), ("IsPrivate", "bool"),
        ("CalculationGroupPrecedence", "int"), ("LineageTag", "str"),
    ],
    "columns.csv": [
        ("ID", "int"), ("Name", "str"), ("Table", "str"),
        ("DataType", "str"), ("DataCategory", "str"),
        ("Description", "str"), ("IsHidden", "bool"),
        ("IsUnique", "bool"), ("IsKey", "bool"), ("IsNullable", "bool"),
        ("Alignment", "str"), ("SummarizeBy", "str"),
        ("ColumnStorage", "str"), ("Type", "str"),
        ("SourceColumn", "str"), ("Expression", "str"),
        ("FormatString", "str"), ("IsAvailableInMDX", "bool"),
        ("SortByColumn", "str"), ("GroupingBehavior", "str"),
        ("SourceProviderType", "str"), ("DisplayFolder", "str"),
        ("AlternateOf", "str"), ("LineageTag", "str"),
    ],
    "measures.csv": [
        ("ID", "int"), ("Name", "str"), ("Table", "str"),
        ("Description", "str"), ("DataType", "str"),
        ("Expression", "str"), ("FormatString", "str"),
        ("IsHidden", "bool"), ("State", "str"), ("KPIID", "int"),
        ("IsSimpleMeasure", "bool"), ("DisplayFolder", "str"),
        ("DetailRowsDefinition", "str"), ("DataCategory", "str"),
        ("FormatStringDefinition", "str"), ("LineageTag", "str"),
    ],
    "relationships.csv": [
        ("ID", "int"), ("Name", "str"), ("Relationship", "str"),
        ("Model", "str"), ("IsActive", "bool"),
        ("CrossFilteringBehavior", "str"),
        ("RelyOnReferentialIntegrity", "bool"),
        ("FromTable", "str"), ("FromColumn", "str"),
        ("FromCardinality", "str"), ("ToTable", "str"),
        ("ToColumn", "str"), ("ToCardinality", "str"),
        ("State", "str"), ("SecurityFilteringBehavior", "str"),
    ],
}

METADATA_FILES = tuple(INFO_VIEW_SCHEMA)

# Nombre fijo que Power BI da a la columna interna de cada tabla.
ROW_NUMBER_COLUMN = "RowNumber-2662979B-1795-4F74-8F37-6A1BA8059B61"

# Primer ID asignado (los reales son enteros internos del motor; aquí solo
# se garantiza que sean únicos y estables entre ejecuciones).
FIRST_OBJECT_ID = 12


# ============================================================
# CONSTRUCTORES DEL MODELO INTERMEDIO
# ============================================================

def new_model(name):
    return {
        "name": name,
        "tables": [],
        "relationships": [],
    }


def new_table(name, **values):
    table = {
        "name": name,
        "description": "",
        "data_category": "Regular",
        "is_hidden": False,
        "is_private": False,
        "show_as_variations_only": False,
        "storage_mode": "Import",
        "expression": "",
        "lineage_tag": "",
        "columns": [],
        "measures": [],
    }
    table.update(values)
    return table


def new_column(name, **values):
    column = {
        "name": name,
        "data_type": "Text",
        "data_category": "Regular",
        "description": "",
        "is_hidden": False,
        "is_key": False,
        "is_nullable": None,
        "summarize_by": "None",
        "type": "Data",
        "source_column": name,
        "expression": "",
        "format_string": "",
        "is_available_in_mdx": True,
        "sort_by_column": "",
        "display_folder": "",
        "lineage_tag": "",
    }
    column.update(values)
    return column


def new_measure(name, **values):
    measure = {
        "name": name,
        "description": "",
        "data_type": "Number",
        "expression": "",
        "format_string": "",
        "format_string_definition": "",
        "is_hidden": False,
        "state": "Valid",
        "display_folder": "",
        "lineage_tag": "",
    }
    measure.update(values)
    return measure


def new_relationship(name, from_table, from_column, to_table, to_column, **values):
    relationship = {
        "name": name,
        "from_table": from_table,
        "from_column": from_column,
        "from_cardinality": "Many",
        "to_table": to_table,
        "to_column": to_column,
        "to_cardinality": "One",
        "cross_filtering": "OneDirection",
        "is_active": True,
        "rely_on_referential_integrity": False,
        "security_filtering": "Single",
    }
    relationship.update(values)
    return relationship


def find_table(model, name):
    key = str(name or "").casefold()
    for table in model["tables"]:
        if table["name"].casefold() == key:
            return table
    return None


def find_column(table, name):
    key = str(name or "").casefold()
    for column in table["columns"]:
        if column["name"].casefold() == key:
            return column
    return None


def find_measure(model, name):
    key = str(name or "").casefold()
    for table in model["tables"]:
        for measure in table["measures"]:
            if measure["name"].casefold() == key:
                return table, measure
    return None, None


# ============================================================
# INFERENCIA DE TIPOS (cuando la fuente no los declara)
# ============================================================

_DAX_COMMENT_RE = re.compile(r"(--|//)[^\n]*")


def _strip_dax_comments(expression):
    return _DAX_COMMENT_RE.sub(" ", str(expression or ""))


def infer_measure_data_type(expression, format_string=""):
    """
    Heurística calibrada contra measures.csv real (≈85 % de acierto):
    porcentajes/decimales/divisiones -> Number; formato '0' o conteos ->
    Integer; texto concatenado sin formato -> Text.
    """
    # Sin comentarios ni literales: "/" dentro de un texto no es división.
    expr = re.sub(r'"[^"]*"', '""', _strip_dax_comments(expression)).upper()
    fmt = str(format_string or "").strip().strip('"')

    if "%" in fmt or re.search(r"0[.,]0", fmt):
        return "Number"
    if not fmt and re.search(
        r"(^|\bRETURN)\s*(CONCATENATEX|FORMAT|CONCATENATE)\s*\(", expr.strip()
    ):
        return "Text"
    if re.search(r"\bDIVIDE\s*\(|/|\bAVERAGEX?\s*\(", expr):
        return "Number"
    if fmt == "0" or fmt.startswith("#,0"):
        return "Integer"
    if re.search(
        r"\b(COUNT|COUNTA|COUNTAX|COUNTX|COUNTROWS|DISTINCTCOUNT|"
        r"DISTINCTCOUNTNOBLANK|COUNTBLANK)\s*\(",
        expr,
    ):
        return "Integer"
    if not fmt and re.search(
        r"\b(FORMAT|CONCATENATEX|CONCATENATE|UPPER|LOWER|LEFT|RIGHT)\s*\(|&",
        expr,
    ):
        return "Text"
    if re.search(r"\b(MIN|MAX|FIRSTDATE|LASTDATE)\s*\(", expr) and re.search(
        r"FECHA|DATE|HORA", expr
    ):
        return "Date"
    return "Number"


def infer_calculated_column_data_type(expression, format_string=""):
    expr = _strip_dax_comments(expression).upper()
    fmt = str(format_string or "").strip()

    if fmt in {"0", "#,0"}:
        return "Integer"
    if "%" in fmt or re.search(r"0[.,]0", fmt):
        return "Number"
    if re.search(r"DATE|TIME|FECHA", fmt.upper()) or fmt in {
        "General Date", "Short Date", "Long Date",
    }:
        return "Date"

    stripped = expr.strip()
    if re.match(r"^(YEAR|MONTH|DAY|WEEKDAY|WEEKNUM|QUARTER|HOUR|MINUTE|INT|"
                r"DATEDIFF|LEN|COUNTROWS|ROUNDDOWN|ROUNDUP)\s*\(", stripped):
        return "Integer"
    if re.match(r"^(DATE|TODAY|NOW|EOMONTH|EDATE|DATEVALUE)\s*\(", stripped):
        return "Date"
    if re.search(r"\b(FORMAT|UPPER|LOWER|CONCATENATE|LEFT|RIGHT|MID|TRIM|"
                 r"SUBSTITUTE)\s*\(|&|\"", expr):
        return "Text"
    if re.search(r"\bDIVIDE\s*\(|/", expr):
        return "Number"
    return "Integer"


_DATE_NAME_RE = re.compile(r"(^|_)(FEC|FECHA|DATE|HORA|DIA_HORA)|FECHA|DATE$", re.I)
_INT_NAME_RE = re.compile(
    r"(^|_)(OID|ID|CANT|CANTIDAD|TOTAL|NUM|NRO|EDAD|DIAS|ANIO|ANO|MES|"
    r"CONTEO|VALOR|SUMA|PESO|COSTO|PRECIO|MINUTOS|HORAS|TIEMPO)($|_)",
    re.I,
)


def infer_column_data_type_from_name(name):
    text = str(name or "")
    if _DATE_NAME_RE.search(text):
        return "Date"
    if _INT_NAME_RE.search(normalize_text(text).replace(" ", "_").upper()):
        return "Integer"
    return "Text"


# ============================================================
# ESCRITURA
# ============================================================

def storage_name(name):
    """'LocalDateTable_93fa-..' -> 'LocalDateTable 93fa ..' (convención real)."""
    return re.sub(r"[\W_]", " ", str(name))


def model_guid(model_name):
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "proyecto-rag/local-model/" + normalize_text(model_name),
        )
    )


def _crlf(value):
    text = str(value)
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")


def format_value(value, kind):
    if kind == "int":
        if value is None or value == "":
            return ""
        return str(int(value))

    if kind == "bool":
        return "True" if bool(value) else "False"

    text = "" if value is None else _crlf(value)
    return '"' + text.replace('"', '""') + '"'


def render_csv(filename, rows):
    schema = INFO_VIEW_SCHEMA[filename]
    lines = [";".join(name for name, _ in schema)]

    for row in rows:
        lines.append(
            ";".join(
                format_value(row.get(name), kind)
                for name, kind in schema
            )
        )

    return "\r\n".join(lines) + "\r\n"


def _relationship_text(rel):
    def symbol(cardinality):
        return "1" if cardinality == "One" else "*"

    arrow = "[<->]" if rel["cross_filtering"] == "BothDirections" else "[<-]"
    from_table = rel["from_table"].replace("'", "''")
    to_table = rel["to_table"].replace("'", "''")

    return (
        f"'{from_table}'[{rel['from_column']}] "
        f"{symbol(rel['from_cardinality'])}{arrow}"
        f"{symbol(rel['to_cardinality'])} "
        f"'{to_table}'[{rel['to_column']}]"
    )


def build_info_view_rows(model):
    """Convierte el modelo intermedio en las filas de los cuatro INFO.VIEW."""
    guid = model_guid(model["name"])
    next_id = [FIRST_OBJECT_ID]

    def take_id():
        value = next_id[0]
        next_id[0] += 1
        return value

    unique_columns = set()
    for rel in model["relationships"]:
        if rel["to_cardinality"] == "One":
            unique_columns.add((rel["to_table"].casefold(), rel["to_column"].casefold()))
        if rel["from_cardinality"] == "One":
            unique_columns.add((rel["from_table"].casefold(), rel["from_column"].casefold()))

    tables_rows = []
    columns_rows = []
    measures_rows = []
    relationships_rows = []

    for table in model["tables"]:
        table_id = take_id()
        table_storage = f"{storage_name(table['name'])} ({table_id})"

        tables_rows.append({
            "ID": table_id,
            "Name": table["name"],
            "Model": guid,
            "DataCategory": table.get("data_category") or "Regular",
            "Description": table.get("description") or "",
            "IsHidden": table.get("is_hidden", False),
            "StorageMode": table.get("storage_mode") or "Import",
            "TableStorage": table_storage,
            "Expression": table.get("expression") or "",
            "ShowAsVariationOnly": table.get("show_as_variations_only", False),
            "IsPrivate": table.get("is_private", False),
            "CalculationGroupPrecedence": None,
            "LineageTag": table.get("lineage_tag") or "",
        })

        row_number_id = take_id()
        columns_rows.append({
            "ID": row_number_id,
            "Name": ROW_NUMBER_COLUMN,
            "Table": table["name"],
            "DataType": "Integer",
            "DataCategory": "RowNumber",
            "Description": "",
            "IsHidden": True,
            "IsUnique": True,
            "IsKey": True,
            "IsNullable": False,
            "Alignment": "Default",
            "SummarizeBy": "Default",
            "ColumnStorage": (
                f"{table_storage}${storage_name(ROW_NUMBER_COLUMN)} "
                f"({row_number_id})"
            ),
            "Type": "RowNumber",
            "SourceColumn": ROW_NUMBER_COLUMN,
            "Expression": "",
            "FormatString": "",
            "IsAvailableInMDX": True,
            "SortByColumn": "",
            "GroupingBehavior": "GroupOnValue",
            "SourceProviderType": "",
            "DisplayFolder": "",
            "AlternateOf": "",
            "LineageTag": "",
        })

        for column in table["columns"]:
            column_id = take_id()
            is_unique = (
                (table["name"].casefold(), column["name"].casefold())
                in unique_columns
            )
            is_nullable = column.get("is_nullable")
            if is_nullable is None:
                is_nullable = not is_unique

            columns_rows.append({
                "ID": column_id,
                "Name": column["name"],
                "Table": table["name"],
                "DataType": column.get("data_type") or "Text",
                "DataCategory": column.get("data_category") or "Regular",
                "Description": column.get("description") or "",
                "IsHidden": column.get("is_hidden", False),
                "IsUnique": is_unique,
                "IsKey": column.get("is_key", False),
                "IsNullable": is_nullable,
                "Alignment": "Default",
                "SummarizeBy": column.get("summarize_by") or "Default",
                "ColumnStorage": (
                    f"{table_storage}${storage_name(column['name'])} ({column_id})"
                ),
                "Type": column.get("type") or "Data",
                "SourceColumn": column.get("source_column") or "",
                "Expression": column.get("expression") or "",
                "FormatString": column.get("format_string") or "",
                "IsAvailableInMDX": column.get("is_available_in_mdx", True),
                "SortByColumn": column.get("sort_by_column") or "",
                "GroupingBehavior": "GroupOnValue",
                "SourceProviderType": "",
                "DisplayFolder": column.get("display_folder") or "",
                "AlternateOf": "",
                "LineageTag": column.get("lineage_tag") or "",
            })

    for table in model["tables"]:
        for measure in table["measures"]:
            format_definition = measure.get("format_string_definition") or ""
            if not format_definition and measure.get("format_string"):
                # INFO.VIEW.MEASURES publica el formato estático como literal
                # DAX en FormatStringDefinition y deja FormatString vacío.
                format_definition = '"' + measure["format_string"].replace('"', '""') + '"'

            measures_rows.append({
                "ID": take_id(),
                "Name": measure["name"],
                "Table": table["name"],
                "Description": measure.get("description") or "",
                "DataType": measure.get("data_type") or "Number",
                "Expression": measure.get("expression") or "",
                "FormatString": "",
                "IsHidden": measure.get("is_hidden", False),
                "State": measure.get("state") or "Valid",
                "KPIID": None,
                "IsSimpleMeasure": False,
                "DisplayFolder": measure.get("display_folder") or "",
                "DetailRowsDefinition": "",
                "DataCategory": "",
                "FormatStringDefinition": format_definition,
                "LineageTag": measure.get("lineage_tag") or "",
            })

    for rel in model["relationships"]:
        rel_id = take_id()
        directions = [rel]

        if rel["from_cardinality"] == "One" and rel["to_cardinality"] == "One":
            # INFO.VIEW.RELATIONSHIPS lista las 1:1 en ambos sentidos.
            directions.append({
                **rel,
                "from_table": rel["to_table"],
                "from_column": rel["to_column"],
                "to_table": rel["from_table"],
                "to_column": rel["from_column"],
            })

        for item in directions:
            relationships_rows.append({
                "ID": rel_id,
                "Name": rel["name"],
                "Relationship": _relationship_text(item),
                "Model": guid,
                "IsActive": item.get("is_active", True),
                "CrossFilteringBehavior": item.get("cross_filtering") or "OneDirection",
                "RelyOnReferentialIntegrity": item.get("rely_on_referential_integrity", False),
                "FromTable": item["from_table"],
                "FromColumn": item["from_column"],
                "FromCardinality": item["from_cardinality"],
                "ToTable": item["to_table"],
                "ToColumn": item["to_column"],
                "ToCardinality": item["to_cardinality"],
                "State": "Ready",
                "SecurityFilteringBehavior": item.get("security_filtering") or "Single",
            })

    return {
        "tables.csv": tables_rows,
        "columns.csv": columns_rows,
        "measures.csv": measures_rows,
        "relationships.csv": relationships_rows,
    }


def save_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_sync_info(model_name, model_dir, row_counts, *, source, extra=None):
    """
    _metadata_sync.json con la forma de sync_powerbi_metadata.export_model
    más los campos 'source' / 'inferred' que indican de dónde salió.
    """
    model_dir = Path(model_dir)
    payload = {
        "semantic_model": model_name,
        "status": "success",
        "files": {
            filename: {
                "status": "success",
                "rows": row_counts.get(filename, 0),
                "path": str(model_dir / filename),
            }
            for filename in METADATA_FILES
        },
        "errors": [],
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "inferred": source.startswith("inferred"),
    }
    payload.update(extra or {})
    save_json(payload, model_dir / "_metadata_sync.json")
    return payload


def write_model_metadata(model, model_dir, *, source, extra=None):
    """Escribe los cuatro CSV + _metadata_sync.json. Devuelve conteos."""
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    rows = build_info_view_rows(model)
    for filename, file_rows in rows.items():
        (model_dir / filename).write_bytes(
            render_csv(filename, file_rows).encode("utf-8")
        )

    counts = {filename: len(file_rows) for filename, file_rows in rows.items()}
    write_sync_info(model["name"], model_dir, counts, source=source, extra=extra)
    return counts

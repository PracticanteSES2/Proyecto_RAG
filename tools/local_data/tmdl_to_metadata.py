"""
Convierte un modelo semántico guardado como PBIP/TMDL
(<Nombre>.SemanticModel/definition) en data/model_metadata/<slug>/ con el mismo
formato que exporta sync_powerbi_metadata.py vía INFO.VIEW.

Uso:
    python -m tools.local_data.tmdl_to_metadata \
        "tableros/ASIGNACION DE CITAS/ASIGNACION DE CITAS.SemanticModel" \
        --output-root data/model_metadata

No lee .pbi/cache.abf (datos): solo los .tmdl de definition/.
"""
import argparse
import re
import sys
from pathlib import Path

from tools.local_data.metadata_format import (
    find_column,
    find_table,
    infer_calculated_column_data_type,
    infer_measure_data_type,
    new_column,
    new_measure,
    new_model,
    new_relationship,
    new_table,
    slugify,
    write_model_metadata,
)


# TMDL -> nombres que devuelve INFO.VIEW
DATA_TYPES = {
    "string": "Text",
    "int64": "Integer",
    "double": "Number",
    "decimal": "Decimal",
    "datetime": "Date",
    "boolean": "True/False",
    "binary": "Binary",
    "variant": "Variant",
}

SUMMARIZE_BY = {
    "none": "None",
    "sum": "Sum",
    "count": "Count",
    "average": "Average",
    "min": "Min",
    "max": "Max",
    "distinctcount": "DistinctCount",
    "default": "Default",
}

STORAGE_MODES = {
    "import": "Import",
    "directquery": "DirectQuery",
    "dual": "Dual",
    "directlake": "DirectLake",
}

CARDINALITY = {"one": "One", "many": "Many"}

# Tipos de las columnas de LocalDateTable/DateTableTemplate (siempre iguales).
DATE_TEMPLATE_TYPES = {
    "Date": "Date",
    "Año": "Integer",
    "NroMes": "Integer",
    "Mes": "Text",
    "NroTrimestre": "Integer",
    "Trimestre": "Text",
    "Día": "Integer",
}


# ============================================================
# PARSER GENÉRICO DE TMDL (indentación por tabuladores)
# ============================================================

def _indent(line):
    return len(line) - len(line.lstrip("\t"))


def _split_name(rest):
    """
    "'Mi tabla' = expr"  -> ("Mi tabla", "expr")
    "%PENDIENTE = CALC"  -> ("%PENDIENTE", "CALC")
    "moda_AMB ="         -> ("moda_AMB", "")
    "CITAS"              -> ("CITAS", None)
    """
    rest = rest.strip()

    if rest.startswith("'"):
        index = 1
        name = []
        while index < len(rest):
            char = rest[index]
            if char == "'":
                if index + 1 < len(rest) and rest[index + 1] == "'":
                    name.append("'")
                    index += 2
                    continue
                index += 1
                break
            name.append(char)
            index += 1
        remainder = rest[index:].strip()
        if remainder.startswith("="):
            return "".join(name), remainder[1:].strip()
        return "".join(name), None

    match = re.match(r"^(.*?)\s*(?:=\s*(.*))?$", rest, re.DOTALL)
    name = match.group(1).strip()
    value = match.group(2)
    if value is None and rest.endswith("="):
        value = ""
    return name, (value.strip() if value is not None else None)


def _collect_expression(lines, start, indent, first):
    """
    Lee una expresión que empieza tras 'xxx =' en la línea start-1.
    - first == '```' : bloque literal hasta la línea '```'.
    - first == ''    : líneas con indentación >= indent+2 (o vacías).
    Devuelve (texto con CRLF, índice siguiente).
    """
    body_indent = indent + 2
    collected = []
    index = start

    if first == "```":
        while index < len(lines):
            line = lines[index]
            index += 1
            if line.strip() == "```":
                break
            collected.append(line)
    else:
        while index < len(lines):
            line = lines[index]
            if line.strip() == "" or _indent(line) >= body_indent:
                collected.append(line)
                index += 1
                continue
            break

    # Las líneas vacías finales separan del siguiente bloque, no son DAX.
    while collected and collected[-1].strip() == "":
        collected.pop()

    dedented = []
    for line in collected:
        prefix = "\t" * body_indent
        if line.startswith(prefix):
            line = line[len(prefix):]
        elif line.strip() == "":
            line = line.strip("\t")
        dedented.append(line.rstrip("\r"))

    return "\r\n".join(dedented), index


def parse_tmdl(text):
    """
    Devuelve una lista de nodos {'indent','keyword','name','value','props',
    'children','description'} con la estructura del archivo TMDL.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    root = {"indent": -1, "children": []}
    stack = [root]
    pending_doc = []
    index = 0

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        index += 1

        if not stripped:
            continue

        indent = _indent(raw)

        if stripped.startswith("///"):
            pending_doc.append(stripped[3:].strip())
            continue

        while stack and stack[-1]["indent"] >= indent:
            stack.pop()
        parent = stack[-1]

        # Propiedad "clave: valor"
        prop = re.match(r"^([A-Za-z][A-Za-z0-9]*)\s*:\s*(.*)$", stripped)
        if prop and " = " not in stripped.split(":", 1)[0]:
            parent.setdefault("props", {})[prop.group(1)] = prop.group(2).strip()
            continue

        parts = stripped.split(None, 1)
        keyword = parts[0]
        rest = parts[1] if len(parts) > 1 else ""

        if keyword in {"source", "changedProperty", "formatStringDefinition",
                       "detailRowsDefinition", "linguisticMetadata",
                       "expression"} and rest.startswith("="):
            name, value = keyword, rest[1:].strip()
        elif "=" not in stripped and " " not in stripped:
            # Bandera sin valor: isHidden, isKey, isDefault...
            parent.setdefault("props", {})[stripped] = True
            continue
        else:
            name, value = _split_name(rest)

        if value in ("", "```"):
            value, index = _collect_expression(lines, index, indent, value)

        node = {
            "indent": indent,
            "keyword": keyword,
            "name": name,
            "value": value,
            "props": {},
            "children": [],
            "description": "\r\n".join(pending_doc),
        }
        pending_doc = []
        parent["children"].append(node)
        stack.append(node)

    return root["children"]


def _children(node, keyword):
    return [child for child in node.get("children", []) if child["keyword"] == keyword]


def _prop(node, name, default=None):
    return node.get("props", {}).get(name, default)


def _flag(node, name):
    value = _prop(node, name)
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _unquote(value):
    value = str(value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def parse_column_reference(value):
    """"'MATRIZ 2024'.Ingreso" -> ("MATRIZ 2024", "Ingreso")."""
    value = str(value or "").strip()

    if value.startswith("'"):
        index = 1
        while index < len(value):
            if value[index] == "'":
                if index + 1 < len(value) and value[index + 1] == "'":
                    index += 2
                    continue
                break
            index += 1
        table = value[1:index].replace("''", "'")
        column = value[index + 2:]
    else:
        table, _, column = value.partition(".")

    return table.strip(), _unquote(column)


# ============================================================
# TMDL -> MODELO INTERMEDIO
# ============================================================

def _definition_dir(path):
    path = Path(path)
    if (path / "definition").is_dir():
        return path / "definition"
    if path.name == "definition" and path.is_dir():
        return path
    raise FileNotFoundError(
        f"No encontré la carpeta TMDL 'definition' en {path}"
    )


def _model_name_from_path(path):
    path = Path(path)
    for candidate in (path, path.parent):
        if candidate.name.lower().endswith(".semanticmodel"):
            return candidate.name[: -len(".SemanticModel")]
    return path.name


def _convert_table(node):
    name = node["name"]
    partitions = _children(node, "partition")
    is_calculated = False
    expression = ""
    storage_mode = "Import"

    for partition in partitions:
        kind = str(partition.get("value") or "").strip().lower()
        mode = str(_prop(partition, "mode", "import")).lower()
        storage_mode = STORAGE_MODES.get(mode, "Import")
        if kind == "calculated":
            is_calculated = True
            sources = _children(partition, "source")
            if sources:
                expression = sources[0]["value"] or ""

    table = new_table(
        name,
        description=node.get("description") or _prop(node, "description", "") or "",
        data_category=_prop(node, "dataCategory") or "Regular",
        is_hidden=_flag(node, "isHidden"),
        is_private=_flag(node, "isPrivate"),
        show_as_variations_only=_flag(node, "showAsVariationsOnly"),
        storage_mode=storage_mode,
        expression=expression,
        lineage_tag=_prop(node, "lineageTag", "") or "",
    )
    is_date_template = name.startswith(("LocalDateTable_", "DateTableTemplate_"))

    for column_node in _children(node, "column"):
        column_name = column_node["name"]
        column_expression = column_node.get("value")
        source_column = _prop(column_node, "sourceColumn", "") or ""
        format_string = _prop(column_node, "formatString", "") or ""
        tmdl_type = str(_prop(column_node, "dataType", "") or "").lower()

        if column_expression is not None:
            column_type = "Calculated"
            source_column = ""
        elif is_calculated:
            column_type = "CalculatedTableColumn"
            source_column = source_column.strip()
            if source_column.startswith("[") and source_column.endswith("]"):
                source_column = source_column[1:-1]
        else:
            column_type = "Data"

        if tmdl_type:
            data_type = DATA_TYPES.get(tmdl_type, tmdl_type)
        elif is_date_template and column_name in DATE_TEMPLATE_TYPES:
            data_type = DATE_TEMPLATE_TYPES[column_name]
        elif column_type == "Calculated":
            data_type = infer_calculated_column_data_type(
                column_expression, format_string
            )
        elif column_type == "CalculatedTableColumn":
            data_type = (
                "Date"
                if re.search(r"CALENDAR", expression, re.I) and column_name == "Date"
                else infer_calculated_column_data_type("", format_string)
                if format_string
                else "Text"
            )
        else:
            data_type = "Text"

        summarize = str(_prop(column_node, "summarizeBy", "default")).lower()

        table["columns"].append(new_column(
            column_name,
            data_type=data_type,
            data_category=_prop(column_node, "dataCategory") or "Regular",
            description=column_node.get("description") or "",
            is_hidden=_flag(column_node, "isHidden"),
            is_key=_flag(column_node, "isKey"),
            is_nullable=(
                False
                if str(_prop(column_node, "isNullable", "")).lower() == "false"
                else None
            ),
            summarize_by=SUMMARIZE_BY.get(summarize, "Default"),
            type=column_type,
            source_column=source_column,
            expression=column_expression or "",
            format_string=format_string,
            is_available_in_mdx=(
                str(_prop(column_node, "isAvailableInMdx", "true")).lower() != "false"
            ),
            sort_by_column=_unquote(_prop(column_node, "sortByColumn", "") or ""),
            display_folder=_unquote(_prop(column_node, "displayFolder", "") or ""),
            lineage_tag=_prop(column_node, "lineageTag", "") or "",
        ))

    for measure_node in _children(node, "measure"):
        measure_expression = measure_node.get("value") or ""
        format_string = _prop(measure_node, "formatString", "") or ""
        format_definition = ""
        for child in _children(measure_node, "formatStringDefinition"):
            format_definition = child.get("value") or ""
        tmdl_type = str(_prop(measure_node, "dataType", "") or "").lower()

        table["measures"].append(new_measure(
            measure_node["name"],
            description=measure_node.get("description") or "",
            data_type=(
                DATA_TYPES.get(tmdl_type, tmdl_type)
                if tmdl_type
                else infer_measure_data_type(measure_expression, format_string)
            ),
            expression=measure_expression,
            format_string=format_string,
            format_string_definition=format_definition,
            is_hidden=_flag(measure_node, "isHidden"),
            display_folder=_unquote(_prop(measure_node, "displayFolder", "") or ""),
            lineage_tag=_prop(measure_node, "lineageTag", "") or "",
        ))

    return table


def load_tmdl_model(semantic_model_path, model_name=None):
    """Lee un *.SemanticModel (o su definition/) y devuelve el modelo intermedio."""
    definition = _definition_dir(semantic_model_path)
    model = new_model(model_name or _model_name_from_path(semantic_model_path))

    # Orden de tablas: el de model.tmdl (ref table ...) cuando existe.
    order = []
    model_file = definition / "model.tmdl"
    if model_file.exists():
        for line in model_file.read_text(encoding="utf-8-sig").splitlines():
            match = re.match(r"^ref table (.+)$", line.strip())
            if match:
                order.append(_unquote(match.group(1)))

    table_nodes = {}
    for path in sorted((definition / "tables").glob("*.tmdl")):
        for node in parse_tmdl(path.read_text(encoding="utf-8-sig")):
            if node["keyword"] == "table":
                table_nodes[node["name"]] = node

    ordered_names = [name for name in order if name in table_nodes]
    ordered_names += [name for name in table_nodes if name not in ordered_names]

    for name in ordered_names:
        model["tables"].append(_convert_table(table_nodes[name]))

    relationships_file = definition / "relationships.tmdl"
    if relationships_file.exists():
        for node in parse_tmdl(relationships_file.read_text(encoding="utf-8-sig")):
            if node["keyword"] != "relationship":
                continue
            from_table, from_column = parse_column_reference(_prop(node, "fromColumn"))
            to_table, to_column = parse_column_reference(_prop(node, "toColumn"))
            cross = str(_prop(node, "crossFilteringBehavior", "oneDirection")).lower()
            security = str(_prop(node, "securityFilteringBehavior", "oneDirection")).lower()

            model["relationships"].append(new_relationship(
                node["name"],
                from_table,
                from_column,
                to_table,
                to_column,
                from_cardinality=CARDINALITY.get(
                    str(_prop(node, "fromCardinality", "many")).lower(), "Many"
                ),
                to_cardinality=CARDINALITY.get(
                    str(_prop(node, "toCardinality", "one")).lower(), "One"
                ),
                cross_filtering=(
                    "BothDirections" if cross == "bothdirections" else "OneDirection"
                ),
                is_active=str(_prop(node, "isActive", "true")).lower() != "false",
                rely_on_referential_integrity=_flag(node, "relyOnReferentialIntegrity"),
                security_filtering=(
                    "BothDirections" if security == "bothdirections" else "Single"
                ),
            ))

    return model


def validate_model(model):
    """Avisos de coherencia (relaciones hacia columnas inexistentes...)."""
    warnings = []
    for rel in model["relationships"]:
        for table_name, column_name in (
            (rel["from_table"], rel["from_column"]),
            (rel["to_table"], rel["to_column"]),
        ):
            table = find_table(model, table_name)
            if table is None:
                warnings.append(f"Relación {rel['name']}: no existe la tabla {table_name}")
            elif find_column(table, column_name) is None:
                warnings.append(
                    f"Relación {rel['name']}: no existe {table_name}[{column_name}]"
                )
    return warnings


def convert(semantic_model_path, output_root, model_name=None, folder_name=None):
    model = load_tmdl_model(semantic_model_path, model_name=model_name)
    folder = folder_name or slugify(model["name"])
    model_dir = Path(output_root) / folder
    warnings = validate_model(model)

    counts = write_model_metadata(
        model,
        model_dir,
        source="tmdl",
        extra={
            "source_details": {
                "semantic_model_path": str(Path(semantic_model_path)),
                "note": (
                    "Metadata real del modelo (definición TMDL del PBIP). "
                    "IDs, Model y TableStorage/ColumnStorage son sintéticos; "
                    "DataType de columnas calculadas sin dataType en TMDL se "
                    "infiere."
                ),
                "warnings": warnings,
            },
        },
    )

    return {
        "semantic_model": model["name"],
        "semantic_model_key": folder,
        "model_dir": model_dir,
        "counts": counts,
        "warnings": warnings,
        "model": model,
    }


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(
        description=(
            "Convierte un *.SemanticModel (TMDL) en "
            "data/model_metadata/<slug>/ con formato INFO.VIEW."
        )
    )
    parser.add_argument("semantic_model", help="Carpeta *.SemanticModel o su definition/")
    parser.add_argument("--output-root", required=True, help="Carpeta data/model_metadata")
    parser.add_argument("--model-name", default=None, help="Nombre del modelo semántico")
    args = parser.parse_args(argv)

    result = convert(args.semantic_model, args.output_root, model_name=args.model_name)
    print("Modelo:", result["semantic_model"])
    print("Carpeta:", result["model_dir"])
    for filename, count in result["counts"].items():
        print(f"  {filename}: {count} filas")
    for warning in result["warnings"]:
        print("  [!]", warning)


if __name__ == "__main__":
    main()

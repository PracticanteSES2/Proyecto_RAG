"""
Metadata INFERIDA para modelos semánticos de los que no hay TMDL ni export
real de INFO.VIEW.

Fuentes (en este orden de confianza):
  1. Reporte PBIR (*.Report/definition/**.json): cada referencia
     Entity/Property de visuales, filtros y formato condicional da una
     tabla/columna (Column, Aggregation, HierarchyLevel,
     PropertyVariationSource) o una medida (Measure). Los literales de filtros
     y las agregaciones dan pistas de tipo.
  2. Documentación normalizada (data/semantic_documents, salida de
     document_normalizer): medidas y columnas calculadas con su DAX, y
     referencias Tabla[Columna] dentro de ese DAX.
  3. Consultas SQL de la documentación: los alias del SELECT se agregan como
     columnas a la tabla con la que más se solapan (o, si no hay ninguna,
     a una tabla sintetizada con el nombre del tablero).

Limitaciones (quedan en _metadata_sync.json):
  - sin relaciones (no aparecen en reportes ni documentos);
  - DataType/SummarizeBy/FormatString son heurísticos;
  - las medidas vistas solo en visuales no tienen expresión DAX;
  - IDs, LineageTag, Model y *Storage son sintéticos;
  - sin LocalDateTable_* (la jerarquía automática de fechas no se reconstruye).
"""
import json
import re
from collections import Counter, OrderedDict
from pathlib import Path

from tools.local_data.metadata_format import (
    find_column,
    find_measure,
    find_table,
    infer_calculated_column_data_type,
    infer_column_data_type_from_name,
    infer_measure_data_type,
    new_column,
    new_measure,
    new_model,
    new_table,
    normalize_text,
    write_model_metadata,
)


NUMERIC_AGGREGATIONS = {0: "Integer", 1: "Number", 3: None, 4: None, 6: "Number",
                        7: "Number", 8: "Number"}

MEASURE_FUNCTION_RE = re.compile(
    r"\b(CALCULATE|CALCULATETABLE|SUM|SUMX|COUNT|COUNTA|COUNTAX|COUNTX|"
    r"COUNTROWS|DISTINCTCOUNT|DISTINCTCOUNTNOBLANK|AVERAGE|AVERAGEX|MIN|MINX|"
    r"MAX|MAXX|DIVIDE|SELECTEDVALUE|HASONEVALUE|ISFILTERED|TOTALYTD|"
    r"SAMEPERIODLASTYEAR|DATESYTD|MEDIAN|MEDIANX|RANKX|CONCATENATEX|"
    r"PERCENTILEX?\.INC|FIRSTNONBLANK|LASTNONBLANK|ALLSELECTED)\s*\(",
    re.IGNORECASE,
)

# Tabla[Columna] o 'Tabla con espacios'[Columna]
DAX_REFERENCE_RE = re.compile(
    r"(?<![\w\]'])('(?:[^']|'')+'|[A-Za-z_À-ÿ][\wÀ-ÿ]*)\s*\[([^\]\[]+)\]"
)

DAX_FUNCTION_NAMES = {
    "sum", "count", "calculate", "filter", "all", "values", "max", "min",
    "average", "related", "distinctcount", "countrows", "selectedvalue",
}


# ============================================================
# UTILIDADES DAX / SQL
# ============================================================

def dax_references(expression):
    """[(tabla, columna)] referenciadas como Tabla[Columna] en un DAX."""
    text = re.sub(r'"[^"]*"', '""', str(expression or ""))
    text = re.sub(r"(--|//)[^\n]*", " ", text)
    result = []
    for table, column in DAX_REFERENCE_RE.findall(text):
        table = table.strip()
        if table.startswith("'"):
            table = table[1:-1].replace("''", "'")
        if not table or table.lower() in DAX_FUNCTION_NAMES:
            continue
        result.append((table, column.strip()))
    return result


DAX_COMPARISON_RE = re.compile(
    r"(?<![\w\]'])('(?:[^']|'')+'|[A-Za-z_À-ÿ][\wÀ-ÿ]*)\s*\[([^\]\[]+)\]\s*"
    r"(?:=|<>|==|>=|<=|>|<)\s*(\"|-?\d)"
)


def dax_comparison_hints(expression):
    """
    [(tabla, columna, tipo)] de comparaciones con literales en un DAX:
    LAVANDERIA[Turno]=1 -> Integer (y no Text: el simulador, como Power BI,
    fallaría al comparar texto con número); T[C] = "X" -> Text.
    """
    text = re.sub(r"(--|//)[^\n]*", " ", str(expression or ""))
    hints = []
    for table, column, first in DAX_COMPARISON_RE.findall(text):
        table = table.strip()
        if table.startswith("'"):
            table = table[1:-1].replace("''", "'")
        if table.lower() in DAX_FUNCTION_NAMES:
            continue
        hints.append((table, column.strip(), "Text" if first == '"' else "Integer"))
    return hints


def looks_like_measure(expression):
    return bool(MEASURE_FUNCTION_RE.search(str(expression or "")))


def _strip_sql_comments(sql):
    sql = re.sub(r"/\*.*?\*/", " ", str(sql or ""), flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def _select_lists(sql):
    """Listas de columnas de cada SELECT (de fuera hacia dentro)."""
    text = _strip_sql_comments(sql)
    lists = []

    for match in re.finditer(r"\bSELECT\b", text, re.IGNORECASE):
        start = match.end()
        depth = 0
        index = start
        end = None
        while index < len(text):
            char = text[index]
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    end = index
                    break
                depth -= 1
            elif depth == 0 and re.match(r"\bFROM\b", text[index:index + 5], re.IGNORECASE) \
                    and (index == 0 or not (text[index - 1].isalnum() or text[index - 1] == "_")):
                end = index
                break
            index += 1
        if end is not None:
            lists.append(text[start:end])

    return lists


def _split_top_level(text):
    parts, depth, current, quote = [], 0, [], None
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _clean_identifier(value):
    value = value.strip()
    if len(value) >= 2 and value[0] in "['\"" and value[-1] in "]'\"":
        value = value[1:-1]
    return value.strip()


def sql_select_aliases(sql):
    """Alias de salida del primer SELECT útil (ignora SELECT *)."""
    for select_list in _select_lists(sql):
        select_list = re.sub(
            r"^\s*(DISTINCT\s+)?(TOP\s*\(?\s*\d+\s*\)?\s*(PERCENT\s+)?)?",
            "",
            select_list,
            flags=re.IGNORECASE,
        )
        aliases = []

        for item in _split_top_level(select_list):
            item = " ".join(item.split())
            if not item or item == "*" or item.endswith(".*"):
                continue

            match = re.search(
                r"\bAS\s+(\[[^\]]+\]|'[^']+'|\"[^\"]+\"|[\w]+)\s*$",
                item,
                re.IGNORECASE,
            )
            if match:
                alias = _clean_identifier(match.group(1))
            elif re.fullmatch(r"[\w\[\]]+(\.[\w\[\]]+)+", item):
                # A.OID / dbo.T.COL -> OID / COL
                alias = _clean_identifier(item.split(".")[-1])
            else:
                match = re.match(r"^(\[[^\]]+\]|'[^']+'|[\w]+)\s*=\s*.+$", item)
                if match and not item.upper().startswith("CASE"):
                    alias = _clean_identifier(match.group(1))
                else:
                    match = re.search(r"(?:^|[\s)])(\[[^\]]+\]|'[^']+'|[A-Za-z_]\w*)\s*$", item)
                    if not match:
                        continue
                    alias = _clean_identifier(match.group(1))
                    if alias.upper() in {"END", "NULL", "AS"}:
                        continue

            if alias and alias not in aliases:
                aliases.append(alias)

        if aliases:
            return aliases

    return []


def synthesized_table_name(text):
    value = normalize_text(text).upper().replace(" ", "_")
    return value or "TABLA_DOCUMENTADA"


# ============================================================
# CONSTRUCTOR
# ============================================================

class InferredModelBuilder:

    def __init__(self, model_name):
        self.model = new_model(model_name)
        self.type_hints = {}
        self.origins = {}
        self.stats = Counter()
        self.synthesized_tables = []
        self.report_paths = []
        self.document_files = []
        # Texto SQL -> tabla donde quedaron sus alias (para ubicar los
        # valores CASE ... THEN 'X' documentados).
        self.sql_tables = {}

    # ------------------------------------------------------------------
    # Altas
    # ------------------------------------------------------------------

    def table(self, name):
        name = str(name or "").strip()
        if not name:
            return None
        table = find_table(self.model, name)
        if table is None:
            table = new_table(name)
            self.model["tables"].append(table)
        return table

    def add_column(self, table_name, column_name, *, hint=None, origin="report"):
        table = self.table(table_name)
        column_name = str(column_name or "").strip()
        if table is None or not column_name:
            return None

        column = find_column(table, column_name)
        if column is None:
            # Si ya existe una medida con ese nombre en la tabla, no se duplica.
            if any(m["name"].casefold() == column_name.casefold() for m in table["measures"]):
                return None
            column = new_column(column_name)
            table["columns"].append(column)
            self.origins[(table["name"], column["name"])] = origin
            self.stats[f"columns_from_{origin}"] += 1

        if hint:
            self.type_hints.setdefault((table["name"], column["name"]), Counter())[hint] += 1
        return column

    def add_measure(self, table_name, name, *, expression="", description="", origin="report"):
        name = str(name or "").strip()
        if not name:
            return None

        owner, measure = find_measure(self.model, name)
        if measure is None:
            table = self.table(table_name or "MEDIDAS")
            # Una columna calculada documentada que el reporte usa como medida.
            existing = find_column(table, name)
            if existing is not None and existing["type"] != "Data":
                table["columns"].remove(existing)
            measure = new_measure(name)
            table["measures"].append(measure)
            self.stats[f"measures_from_{origin}"] += 1

        if expression and not measure["expression"]:
            measure["expression"] = expression
            self.stats["measures_with_dax"] += 1
        if description and not measure["description"]:
            measure["description"] = description
        return measure

    def add_calculated_column(self, table_name, name, expression, *, description="", origin="docs"):
        table = self.table(table_name)
        if table is None or not name:
            return None
        if any(m["name"].casefold() == name.casefold() for m in table["measures"]):
            return None
        column = self.add_column(table["name"], name, origin=origin)
        if column is None:
            return None
        column.update({
            "type": "Calculated",
            "source_column": "",
            "expression": expression or column["expression"],
        })
        if description and not column["description"]:
            column["description"] = description
        self.stats["calculated_columns"] += 1
        return column

    # ------------------------------------------------------------------
    # Reporte PBIR
    # ------------------------------------------------------------------

    def _entity(self, node, aliases):
        if not isinstance(node, dict):
            return None
        source_ref = node.get("SourceRef")
        if isinstance(source_ref, dict):
            return source_ref.get("Entity") or aliases.get(source_ref.get("Source"))
        for value in node.values():
            if isinstance(value, dict):
                entity = self._entity(value, aliases)
                if entity:
                    return entity
        return None

    @staticmethod
    def _literal_hint(literal):
        value = str((literal or {}).get("Value", ""))
        if value.startswith("datetime'"):
            return "Date"
        if value.startswith("'"):
            return "Text"
        if re.fullmatch(r"-?\d+L", value):
            return "Integer"
        if re.fullmatch(r"-?\d+(\.\d+)?D", value):
            return "Number"
        if value in {"true", "false"}:
            return "True/False"
        return None

    def _column_of(self, node, aliases):
        if isinstance(node, dict):
            if isinstance(node.get("Column"), dict):
                column = node["Column"]
                return self._entity(column.get("Expression"), aliases), column.get("Property")
            if isinstance(node.get("Aggregation"), dict):
                return self._column_of(node["Aggregation"].get("Expression"), aliases)
        return None, None

    def _walk_report(self, node, aliases):
        if isinstance(node, list):
            for item in node:
                self._walk_report(item, aliases)
            return
        if not isinstance(node, dict):
            return

        if isinstance(node.get("From"), list):
            aliases = dict(aliases)
            for item in node["From"]:
                if isinstance(item, dict) and item.get("Name") and item.get("Entity"):
                    aliases[item["Name"]] = item["Entity"]

        measure = node.get("Measure")
        if isinstance(measure, dict) and measure.get("Property"):
            self.add_measure(
                self._entity(measure.get("Expression"), aliases),
                measure["Property"],
                origin="report",
            )

        column = node.get("Column")
        if isinstance(column, dict) and column.get("Property"):
            self.add_column(
                self._entity(column.get("Expression"), aliases),
                column["Property"],
            )

        aggregation = node.get("Aggregation")
        if isinstance(aggregation, dict):
            table, column_name = self._column_of(aggregation.get("Expression"), aliases)
            hint = NUMERIC_AGGREGATIONS.get(aggregation.get("Function"))
            if table and column_name:
                self.add_column(table, column_name, hint=hint)

        variation = node.get("PropertyVariationSource")
        if isinstance(variation, dict) and variation.get("Property"):
            self.add_column(
                self._entity(variation.get("Expression"), aliases),
                variation["Property"],
                hint="Date",
            )

        level = node.get("HierarchyLevel")
        if isinstance(level, dict):
            hierarchy = (level.get("Expression") or {}).get("Hierarchy") or {}
            hierarchy_expression = hierarchy.get("Expression") or {}
            if "PropertyVariationSource" not in hierarchy_expression:
                table = self._entity(hierarchy_expression, aliases)
                if table and level.get("Level"):
                    self.add_column(table, level["Level"])

        condition = node.get("In")
        if isinstance(condition, dict):
            columns = [
                self._column_of(expression, aliases)
                for expression in condition.get("Expressions", []) or []
            ]
            for row in condition.get("Values", []) or []:
                for position, value in enumerate(row or []):
                    if position < len(columns) and isinstance(value, dict):
                        table, column_name = columns[position]
                        hint = self._literal_hint(value.get("Literal"))
                        if table and column_name and hint:
                            self.add_column(table, column_name, hint=hint)

        comparison = node.get("Comparison")
        if isinstance(comparison, dict):
            table, column_name = self._column_of(comparison.get("Left"), aliases)
            right = comparison.get("Right") or {}
            hint = self._literal_hint(right.get("Literal")) if isinstance(right, dict) else None
            if right.get("DateSpan") or right.get("DateAdd"):
                hint = "Date"
            if table and column_name and hint:
                self.add_column(table, column_name, hint=hint)

        for value in node.values():
            if isinstance(value, (dict, list)):
                self._walk_report(value, aliases)

    def ingest_report(self, report_path):
        report_path = Path(report_path)
        definition = report_path / "definition" if (report_path / "definition").is_dir() else report_path
        files = sorted(definition.rglob("*.json"))
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                self.stats["report_files_unreadable"] += 1
                continue
            self._walk_report(payload, {})
        self.stats["report_json_files"] += len(files)
        self.stats["report_visuals"] += sum(1 for path in files if path.name == "visual.json")
        self.report_paths.append(str(report_path))

    # ------------------------------------------------------------------
    # Documentación normalizada
    # ------------------------------------------------------------------

    def _resolve_table(self, explicit, expression):
        if explicit:
            return explicit
        referenced = Counter(table for table, _ in dax_references(expression))
        if referenced:
            return referenced.most_common(1)[0][0]
        return None

    def _register_references(self, expression):
        for table, column in dax_references(expression):
            # Las referencias a medidas con tabla (Tabla[Medida]) se ignoran.
            if find_measure(self.model, column)[1] is not None:
                continue
            self.add_column(table, column, origin="docs")
        for table, column, hint in dax_comparison_hints(expression):
            if find_measure(self.model, column)[1] is not None:
                continue
            self.add_column(table, column, hint=hint, origin="docs")

    def ingest_documents(self, documents):
        """documents: dicts de data/semantic_documents (schema_version 2)."""
        sql_by_dashboard = []

        for document in documents:
            self.document_files.append(document.get("relative_path") or document.get("source_file"))

            for dashboard in document.get("dashboards", []) or []:
                expressions = []

                for item in dashboard.get("documented_measures", []) or []:
                    name = re.sub(r"s*=s*$", "", str(item.get("name") or "")).strip()
                    expression = str(item.get("expression") or "").strip()
                    if not name:
                        continue
                    table = self._resolve_table(item.get("table"), expression)
                    owner, existing_measure = find_measure(self.model, name)
                    existing_column = None
                    for candidate in self.model["tables"]:
                        existing_column = existing_column or find_column(candidate, name)

                    if existing_measure is not None or (
                        existing_column is None and looks_like_measure(expression)
                    ):
                        self.add_measure(
                            table, name, expression=expression,
                            description=item.get("description") or "", origin="docs",
                        )
                    else:
                        self.add_calculated_column(
                            table or "MEDIDAS", name, expression,
                            description=item.get("description") or "",
                        )
                    expressions.append(expression)

                for item in dashboard.get("calculated_columns", []) or []:
                    name = re.sub(r"s*=s*$", "", str(item.get("name") or "")).strip()
                    expression = str(item.get("expression") or "").strip()
                    if not name:
                        continue
                    owner, existing_measure = find_measure(self.model, name)
                    if existing_measure is not None:
                        if expression and not existing_measure["expression"]:
                            existing_measure["expression"] = expression
                        continue
                    table = self._resolve_table(item.get("table"), expression)
                    if table is None:
                        continue
                    self.add_calculated_column(
                        table, name, expression,
                        description=item.get("description") or "",
                    )
                    expressions.append(expression)

                for expression in expressions:
                    self._register_references(expression)

                sql_by_dashboard.append((dashboard, expressions))

        # Las columnas de SQL se reparten al final, cuando ya se conocen las
        # tablas del reporte y del DAX documentado.
        for dashboard, expressions in sql_by_dashboard:
            referenced_tables = Counter(
                table for expression in expressions for table, _ in dax_references(expression)
            )
            for sql in dashboard.get("sql_queries", []) or []:
                aliases = sql_select_aliases(sql)
                if not aliases:
                    continue
                table_name = self._table_for_sql(aliases, referenced_tables, dashboard)
                if table_name is None:
                    self.stats["sql_queries_skipped"] += 1
                    continue
                for alias in aliases:
                    self.add_column(table_name, alias, origin="sql")
                self.sql_tables[sql] = table_name
                self.stats["sql_queries_used"] += 1

    def _table_for_sql(self, aliases, referenced_tables, dashboard):
        """
        Tabla destino de los alias de un SELECT documentado. Con reporte PBIR
        solo se acepta un solapamiento claro (>=2 columnas y >=50 % de los
        alias): validado contra la metadata real de Atenciones
        Institucionales, el resto de reglas asigna más columnas a tablas
        equivocadas que a la correcta. Sin reporte (solo documentación) se
        usa además la única tabla citada por el DAX del tablero o una tabla
        sintetizada con el nombre del tablero.
        """
        wanted = {alias.casefold() for alias in aliases}
        best, best_score = None, 0

        for table in self.model["tables"]:
            names = {column["name"].casefold() for column in table["columns"]}
            score = len(wanted & names)
            if score > best_score:
                best, best_score = table["name"], score

        if best and best_score >= 2 and best_score >= 0.5 * len(wanted):
            return best

        if self.report_paths:
            return None

        if len(referenced_tables) == 1:
            return next(iter(referenced_tables))

        name = synthesized_table_name(dashboard.get("name"))
        if name not in self.synthesized_tables:
            self.synthesized_tables.append(name)
        return name

    # ------------------------------------------------------------------
    # Cierre
    # ------------------------------------------------------------------

    def finalize(self):
        for table in self.model["tables"]:
            for column in table["columns"]:
                hints = self.type_hints.get((table["name"], column["name"]), Counter())

                if column["type"] == "Calculated":
                    data_type = infer_calculated_column_data_type(column["expression"])
                elif hints.get("Date"):
                    data_type = "Date"
                elif hints.get("Text"):
                    data_type = "Text"
                elif hints.get("Number"):
                    data_type = "Number"
                elif hints.get("Integer"):
                    data_type = "Integer"
                elif hints.get("True/False"):
                    data_type = "True/False"
                else:
                    data_type = infer_column_data_type_from_name(column["name"])

                column["data_type"] = data_type
                column["summarize_by"] = "Sum" if data_type in {"Integer", "Number"} else "None"
                column["format_string"] = {
                    "Integer": "0",
                    "Date": "General Date",
                }.get(data_type, "")

            for measure in table["measures"]:
                measure["data_type"] = infer_measure_data_type(measure["expression"])

        # Tablas sin columnas ni medidas (alias de filtros que no resolvieron).
        self.model["tables"] = [
            table for table in self.model["tables"]
            if table["columns"] or table["measures"]
        ]
        return self.model

    def summary(self):
        return {
            "report_paths": self.report_paths,
            "documents": [item for item in self.document_files if item],
            "stats": dict(self.stats),
            "synthesized_tables": self.synthesized_tables,
        }


LIMITATIONS = [
    "Metadata inferida: no proviene de INFO.VIEW ni de TMDL.",
    "Sin relaciones entre tablas (relationships.csv solo trae la cabecera).",
    "DataType, SummarizeBy y FormatString son heurísticos.",
    "Medidas vistas solo en el reporte quedan sin expresión DAX.",
    "IDs, LineageTag, Model y TableStorage/ColumnStorage son sintéticos.",
    "No se reconstruyen LocalDateTable_* ni jerarquías automáticas de fecha.",
]


def build_inferred_metadata(model_name, model_dir, *, report_paths=(), documents=(),
                            infer_report=None):
    """
    infer_report (por defecto: solo si no hay reporte PBIR) reconstruye de la
    documentación los indicadores y visuales del tablero (ver infer_visuals):
    agrega medidas/columnas respaldadas por el docx y devuelve las páginas en
    result["inferred_report"] para escribir un PBIR mínimo.
    """
    from tools.local_data.documented_values import DocumentedValues
    from tools.local_data.infer_visuals import infer_documented_report

    documents = list(documents)
    builder = InferredModelBuilder(model_name)

    for report_path in report_paths:
        builder.ingest_report(report_path)

    builder.ingest_documents(documents)
    model = builder.finalize()

    values = DocumentedValues().ingest_documents(documents, builder.sql_tables).ingest_model(model)

    if infer_report is None:
        infer_report = not report_paths
    inferred_report = None
    if infer_report and documents:
        inference = infer_documented_report(
            model, documents,
            origins=builder.origins,
            documented_values=values.by_table_column(model),
        )
        if inference.pages:
            inferred_report = {"pages": inference.pages, "summary": inference.summary()}

    if report_paths and documents:
        source = "inferred_from_report_and_documentation"
    elif report_paths:
        source = "inferred_from_report"
    else:
        source = "inferred_from_documentation"

    summary = builder.summary()
    limitations = list(LIMITATIONS)
    if summary["synthesized_tables"]:
        limitations.append(
            "Tablas sintetizadas desde SQL documentado (nombre = tablero): "
            + ", ".join(summary["synthesized_tables"])
        )
    extra = {"source_details": summary, "limitations": limitations}
    if inferred_report:
        report_summary = inferred_report["summary"]
        extra["inferred_report"] = {
            key: report_summary[key]
            for key in ("origin", "pages", "visuals", "added_measures", "added_columns")
        }
        limitations.append(
            "Indicadores y visuales reconstruidos de la documentación "
            "(inferred_from_documentation): medidas en DisplayFolder "
            "'inferred_from_documentation' y PBIR mínimo en data/pbir; no es el reporte real."
        )

    counts = write_model_metadata(model, model_dir, source=source, extra=extra)
    values.save(model_name, Path(model_dir))
    return {
        "semantic_model": model_name,
        "model_dir": Path(model_dir),
        "source": source,
        "counts": counts,
        "summary": summary,
        "model": model,
        "inferred_report": inferred_report,
    }

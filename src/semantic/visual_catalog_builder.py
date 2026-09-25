import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


PBIR_AGGREGATIONS = {
    0: "Sum",
    1: "Average",
    2: "DistinctCount",
    3: "Min",
    4: "Max",
    5: "Count",
    6: "Median",
    7: "StandardDeviation",
    8: "Variance",
}

DAX_AGGREGATIONS = {
    "Sum": "SUM",
    "Average": "AVERAGE",
    "DistinctCount": "DISTINCTCOUNT",
    "Min": "MIN",
    "Max": "MAX",
    "Count": "COUNT",
    "Median": "MEDIAN",
}


def normalize_text(value):
    value = str(value or "").strip().lower()

    value = "".join(
        char
        for char in unicodedata.normalize(
            "NFD",
            value,
        )
        if unicodedata.category(char) != "Mn"
    )

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def safe_read_json(path):
    try:
        return json.loads(
            Path(path).read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def clean_literal(value):
    """
    Convierte valores literales comunes de PBIR a Python.
    Conserva como string aquello que no pueda interpretar
    con seguridad.
    """
    if value is None:
        return None

    value = str(value).strip()

    if (
        len(value) >= 2
        and value[0] == "'"
        and value[-1] == "'"
    ):
        return (
            value[1:-1]
            .replace("''", "'")
        )

    lower = value.lower()

    if lower == "true":
        return True

    if lower == "false":
        return False

    numeric = value

    if numeric.endswith(
        ("L", "D", "M")
    ):
        numeric = numeric[:-1]

    try:
        if "." in numeric:
            return float(numeric)

        return int(numeric)

    except Exception:
        return value


class ModelMetadataIndex:
    """
    Índice flexible sobre los CSV generados con:
    INFO.VIEW.TABLES()
    INFO.VIEW.COLUMNS()
    INFO.VIEW.MEASURES()
    INFO.VIEW.RELATIONSHIPS()
    """

    def __init__(
        self,
        metadata_dir=None,
    ):
        self.metadata_dir = (
            Path(metadata_dir)
            if metadata_dir
            else None
        )

        self.tables = set()
        self.columns = set()
        self.measures = set()
        self.measure_rows = []

        if (
            self.metadata_dir
            and self.metadata_dir.exists()
        ):
            self._load()

    def _canonical_key(
        self,
        value,
    ):
        return re.sub(
            r"[^a-z0-9]",
            "",
            normalize_text(value),
        )

    def _canonical_row(
        self,
        row,
    ):
        return {
            self._canonical_key(key):
                value
            for key, value in row.items()
        }

    def _read_csv(
        self,
        filename,
    ):
        path = (
            self.metadata_dir
            / filename
        )

        if not path.exists():
            return []

        with open(
            path,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            return list(
                csv.DictReader(file)
            )

    def _get(
        self,
        row,
        *names,
    ):
        canonical = (
            self._canonical_row(row)
        )

        for name in names:
            value = canonical.get(
                self._canonical_key(name)
            )

            if (
                value is not None
                and str(value).strip()
            ):
                return str(value).strip()

        return None

    def _load(self):
        for row in self._read_csv(
            "tables.csv"
        ):
            table = self._get(
                row,
                "Name",
                "Table",
                "TableName",
            )

            if table:
                self.tables.add(
                    normalize_text(table)
                )

        for row in self._read_csv(
            "columns.csv"
        ):
            table = self._get(
                row,
                "Table",
                "TableName",
                "Entity",
            )

            column = self._get(
                row,
                "Name",
                "Column",
                "ColumnName",
            )

            if table and column:
                self.columns.add(
                    (
                        normalize_text(table),
                        normalize_text(column),
                    )
                )

        for row in self._read_csv(
            "measures.csv"
        ):
            table = self._get(
                row,
                "Table",
                "TableName",
                "Entity",
            )

            measure = self._get(
                row,
                "Name",
                "Measure",
                "MeasureName",
            )

            if measure:
                self.measures.add(
                    (
                        normalize_text(
                            table
                        ),
                        normalize_text(
                            measure
                        ),
                    )
                )

                self.measure_rows.append(
                    {
                        "table": table,
                        "measure": measure,
                        "expression":
                            self._get(
                                row,
                                "Expression",
                                "DAX",
                            ),
                        "description":
                            self._get(
                                row,
                                "Description",
                            ),
                    }
                )

    def has_table(
        self,
        table,
    ):
        if not self.tables:
            return None

        return (
            normalize_text(table)
            in self.tables
        )

    def has_column(
        self,
        table,
        column,
    ):
        if not self.columns:
            return None

        return (
            normalize_text(table),
            normalize_text(column),
        ) in self.columns

    def has_measure(
        self,
        table,
        measure,
    ):
        if not self.measures:
            return None

        candidate = (
            normalize_text(table),
            normalize_text(measure),
        )

        if candidate in self.measures:
            return True

        # Algunas exportaciones no incluyen la tabla
        # de la medida de forma consistente.
        measure_norm = (
            normalize_text(measure)
        )

        return any(
            stored_measure
            == measure_norm
            for _, stored_measure
            in self.measures
        )


class PBIRVisualCatalogBuilder:

    def __init__(
        self,
        report_path,
        metadata_dir=None,
        semantic_model=None,
    ):
        self.report_path = Path(
            report_path
        )

        self.definition_dir = (
            self._resolve_definition_dir(
                self.report_path
            )
        )

        self.pages_dir = (
            self.definition_dir
            / "pages"
        )

        self.semantic_model = (
            semantic_model
        )

        self.model_index = (
            ModelMetadataIndex(
                metadata_dir
            )
        )

    # ========================================================
    # RUTAS
    # ========================================================

    def _resolve_definition_dir(
        self,
        path,
    ):
        path = Path(path)

        if (
            path.name == "definition"
            and (path / "pages").exists()
        ):
            return path

        candidate = (
            path
            / "definition"
        )

        if (
            candidate.exists()
            and (candidate / "pages").exists()
        ):
            return candidate

        raise FileNotFoundError(
            "No encontré la carpeta PBIR "
            "'definition/pages'. Guarda el reporte "
            "como proyecto PBIP usando formato PBIR "
            "y pasa la ruta de la carpeta *.Report "
            "o de su carpeta definition."
        )

    # ========================================================
    # EXPRESIONES DE CAMPOS
    # ========================================================

    def _find_source_entity(
        self,
        node,
    ):
        if isinstance(
            node,
            dict,
        ):
            source_ref = node.get(
                "SourceRef"
            )

            if isinstance(
                source_ref,
                dict,
            ):
                entity = (
                    source_ref.get(
                        "Entity"
                    )
                    or
                    source_ref.get(
                        "Source"
                    )
                )

                if entity:
                    return entity

            for value in node.values():
                result = (
                    self._find_source_entity(
                        value
                    )
                )

                if result:
                    return result

        elif isinstance(
            node,
            list,
        ):
            for value in node:
                result = (
                    self._find_source_entity(
                        value
                    )
                )

                if result:
                    return result

        return None

    def _column_from_node(
        self,
        node,
    ):
        if not isinstance(
            node,
            dict,
        ):
            return None, None

        if (
            "Column" in node
            and isinstance(
                node["Column"],
                dict,
            )
        ):
            column = node[
                "Column"
            ]

            return (
                self._find_source_entity(
                    column
                ),
                column.get(
                    "Property"
                ),
            )

        for value in node.values():
            if isinstance(
                value,
                (dict, list),
            ):
                table, column = (
                    self._column_from_node(
                        value
                    )
                    if isinstance(
                        value,
                        dict,
                    )
                    else (None, None)
                )

                if table and column:
                    return (
                        table,
                        column,
                    )

        return None, None

    def _build_aggregation_dax(
        self,
        aggregation,
        table,
        column,
    ):
        function = (
            DAX_AGGREGATIONS.get(
                aggregation
            )
        )

        if not function:
            return None

        safe_table = str(
            table
        ).replace(
            "'",
            "''",
        )

        safe_column = str(
            column
        ).replace(
            "]",
            "]]",
        )

        return (
            f"{function}("
            f"'{safe_table}'"
            f"[{safe_column}])"
        )

    def _parse_field(
        self,
        field,
    ):
        if not isinstance(
            field,
            dict,
        ):
            return {
                "kind": "unknown",
            }

        # ---------------- Measure ----------------

        measure = field.get(
            "Measure"
        )

        if isinstance(
            measure,
            dict,
        ):
            table = (
                self._find_source_entity(
                    measure
                )
            )

            name = measure.get(
                "Property"
            )

            exists = (
                self.model_index
                .has_measure(
                    table,
                    name,
                )
            )

            return {
                "kind":
                    "measure",
                "table":
                    table,
                "measure":
                    name,
                "dax_expression":
                    (
                        f"[{name}]"
                        if name
                        else None
                    ),
                "model_valid":
                    exists,
            }

        # ---------------- Aggregation ----------------

        aggregation_node = (
            field.get(
                "Aggregation"
            )
        )

        if isinstance(
            aggregation_node,
            dict,
        ):
            function_id = (
                aggregation_node.get(
                    "Function"
                )
            )

            aggregation = (
                PBIR_AGGREGATIONS.get(
                    function_id,
                    f"Unknown_{function_id}",
                )
            )

            table, column = (
                self._column_from_node(
                    aggregation_node.get(
                        "Expression",
                        aggregation_node,
                    )
                )
            )

            column_exists = (
                self.model_index
                .has_column(
                    table,
                    column,
                )
            )

            dax_expression = (
                self._build_aggregation_dax(
                    aggregation,
                    table,
                    column,
                )
                if table and column
                else None
            )

            valid = (
                column_exists
                is not False
                and dax_expression
                is not None
            )

            return {
                "kind":
                    "aggregation",
                "table":
                    table,
                "column":
                    column,
                "aggregation_id":
                    function_id,
                "aggregation":
                    aggregation,
                "dax_expression":
                    dax_expression,
                "model_valid":
                    column_exists,
                "auto_executable":
                    bool(valid),
            }

        # ---------------- Column ----------------

        column_node = field.get(
            "Column"
        )

        if isinstance(
            column_node,
            dict,
        ):
            table = (
                self._find_source_entity(
                    column_node
                )
            )

            column = column_node.get(
                "Property"
            )

            return {
                "kind":
                    "column",
                "table":
                    table,
                "column":
                    column,
                "model_valid":
                    self.model_index
                    .has_column(
                        table,
                        column,
                    ),
            }

        # ---------------- Hierarchy ----------------

        hierarchy = field.get(
            "HierarchyLevel"
        )

        if isinstance(
            hierarchy,
            dict,
        ):
            return {
                "kind":
                    "hierarchy_level",
                "table":
                    self._find_source_entity(
                        hierarchy
                    ),
                "level":
                    hierarchy.get(
                        "Level"
                    ),
            }

        return {
            "kind": "unknown",
            "raw_keys":
                list(field.keys()),
        }

    # ========================================================
    # TÍTULO DEL VISUAL
    # ========================================================

    def _literal_value(
        self,
        node,
    ):
        if isinstance(
            node,
            dict,
        ):
            literal = node.get(
                "Literal"
            )

            if isinstance(
                literal,
                dict,
            ):
                value = literal.get(
                    "Value"
                )

                if value is not None:
                    return clean_literal(
                        value
                    )

            for value in node.values():
                result = (
                    self._literal_value(
                        value
                    )
                )

                if result not in (
                    None,
                    "",
                ):
                    return result

        elif isinstance(
            node,
            list,
        ):
            for value in node:
                result = (
                    self._literal_value(
                        value
                    )
                )

                if result not in (
                    None,
                    "",
                ):
                    return result

        return None

    def _visual_title(
        self,
        visual_json,
    ):
        visual = (
            visual_json.get(
                "visual",
                {},
            )
            or {}
        )

        objects = (
            visual.get(
                "visualContainerObjects",
                {},
            )
            or {}
        )

        title_items = (
            objects.get(
                "title",
                [],
            )
            or []
        )

        for item in title_items:

            properties = (
                item.get(
                    "properties",
                    {},
                )
                or {}
            )

            text_property = (
                properties.get(
                    "text",
                    {},
                )
                or {}
            )

            expr = (
                text_property.get(
                    "expr",
                    {},
                )
                or {}
            )

            literal = (
                expr.get(
                    "Literal",
                    {},
                )
                or {}
            )

            value = literal.get(
                "Value"
            )

            if value is None:
                continue

            value = clean_literal(
                value
            )

            if (
                isinstance(
                    value,
                    str,
                )
                and value.strip()
            ):
                return value.strip()

        return None

    # ========================================================
    # FILTROS
    # ========================================================

    def _extract_literals(
        self,
        node,
    ):
        values = []

        if isinstance(
            node,
            dict,
        ):
            literal = node.get(
                "Literal"
            )

            if isinstance(
                literal,
                dict,
            ):
                if (
                    "Value"
                    in literal
                ):
                    values.append(
                        clean_literal(
                            literal.get(
                                "Value"
                            )
                        )
                    )

            for value in node.values():
                values.extend(
                    self._extract_literals(
                        value
                    )
                )

        elif isinstance(
            node,
            list,
        ):
            for value in node:
                values.extend(
                    self._extract_literals(
                        value
                    )
                )

        return values

    def _parse_filters(
        self,
        owner_json,
        scope,
    ):
        config = (
            owner_json.get(
                "filterConfig",
                {},
            )
            or {}
        )

        output = []

        for item in config.get(
            "filters",
            [],
        ) or []:
            field = (
                self._parse_field(
                    item.get(
                        "field",
                        {},
                    )
                )
            )

            values = (
                self._extract_literals(
                    item.get(
                        "filter",
                        {},
                    )
                )
            )

            output.append(
                {
                    "scope":
                        scope,
                    "name":
                        item.get(
                            "name"
                        ),
                    "type":
                        item.get(
                            "type"
                        ),
                    "field":
                        field,
                    "values":
                        values,
                    "has_condition":
                        bool(
                            item.get(
                                "filter"
                            )
                        ),
                }
            )

        return output

    # ========================================================
    # ALIASES
    # ========================================================

    def _metric_aliases(
        self,
        title,
        native_ref,
        query_ref,
        parsed_field,
    ):
        aliases = []

        for value in [
            title,
            native_ref,
            query_ref,
            parsed_field.get(
                "measure"
            ),
            parsed_field.get(
                "column"
            ),
        ]:
            if (
                value
                and value not in aliases
            ):
                aliases.append(
                    str(value)
                )

        # "PACIENTES OBSERVADOS POR MES"
        # -> "PACIENTES OBSERVADOS"
        if title:
            title_text = str(
                title
            ).strip()

            match = re.split(
                r"\s+por\s+",
                title_text,
                maxsplit=1,
                flags=re.IGNORECASE,
            )

            if (
                len(match) > 1
                and len(
                    match[0].strip()
                ) >= 4
            ):
                prefix = (
                    match[0].strip()
                )

                if prefix not in aliases:
                    aliases.append(
                        prefix
                    )

        aggregation = (
            parsed_field.get(
                "aggregation"
            )
        )

        column = (
            parsed_field.get(
                "column"
            )
        )

        if aggregation and column:
            alias = (
                f"{aggregation} de "
                f"{column}"
            )

            if alias not in aliases:
                aliases.append(alias)

        return aliases

    # ========================================================
    # VISUAL
    # ========================================================

    def _parse_visual(
        self,
        visual_path,
        page_name,
        page_display_name,
        inherited_filters,
    ):
        visual_json = (
            safe_read_json(
                visual_path
            )
        )

        visual = (
            visual_json.get(
                "visual",
                {},
            )
            or {}
        )

        query = (
            visual.get(
                "query",
                {},
            )
            or {}
        )

        query_state = (
            query.get(
                "queryState",
                {},
            )
            or {}
        )

        title = (
            self._visual_title(
                visual_json
            )
        )

        visual_type = (
            visual.get(
                "visualType"
            )
        )

        fields = []
        metrics = []

        for role, role_data in (
            query_state.items()
        ):
            projections = (
                (
                    role_data
                    or {}
                ).get(
                    "projections",
                    [],
                )
                or []
            )

            for projection in projections:
                parsed = (
                    self._parse_field(
                        projection.get(
                            "field",
                            {},
                        )
                    )
                )

                entry = {
                    "role":
                        role,
                    "query_ref":
                        projection.get(
                            "queryRef"
                        ),
                    "native_query_ref":
                        projection.get(
                            "nativeQueryRef"
                        ),
                    "display_name":
                        projection.get(
                            "displayName"
                        ),
                    **parsed,
                }

                fields.append(entry)

                if parsed.get(
                    "kind"
                ) in (
                    "measure",
                    "aggregation",
                ):
                    metric = {
                        "page_name":
                            page_name,
                        "page_display_name":
                            page_display_name,
                        "visual_id":
                            visual_json.get(
                                "name"
                            ),
                        "visual_type":
                            visual_type,
                        "visual_title":
                            title,
                        "role":
                            role,
                        "query_ref":
                            projection.get(
                                "queryRef"
                            ),
                        "native_query_ref":
                            projection.get(
                                "nativeQueryRef"
                            ),
                        "aliases":
                            self._metric_aliases(
                                title,
                                projection.get(
                                    "nativeQueryRef"
                                ),
                                projection.get(
                                    "queryRef"
                                ),
                                parsed,
                            ),
                        **parsed,
                    }

                    if (
                        parsed.get(
                            "kind"
                        )
                        == "measure"
                    ):
                        metric[
                            "validation_status"
                        ] = (
                            "approved"
                            if parsed.get(
                                "model_valid"
                            )
                            is not False
                            else
                            "needs_review"
                        )

                    else:
                        metric[
                            "validation_status"
                        ] = (
                            "approved"
                            if parsed.get(
                                "auto_executable"
                            )
                            else
                            "needs_review"
                        )

                    metrics.append(
                        metric
                    )

        visual_filters = (
            self._parse_filters(
                visual_json,
                "visual",
            )
        )

        return {
            "page_name":
                page_name,
            "page_display_name":
                page_display_name,
            "visual_id":
                visual_json.get(
                    "name"
                ),
            "visual_type":
                visual_type,
            "visual_title":
                title,
            "is_hidden":
                bool(
                    visual_json.get(
                        "isHidden",
                        False,
                    )
                ),
            "position":
                visual_json.get(
                    "position",
                    {},
                ),
            "fields":
                fields,
            "metrics":
                metrics,
            "filters": {
                "inherited":
                    inherited_filters,
                "visual":
                    visual_filters,
            },
            "source_file":
                str(visual_path),
        }

    # ========================================================
    # BUILD
    # ========================================================

    def build(self):
        if not self.pages_dir.exists():
            raise FileNotFoundError(
                f"No existe: "
                f"{self.pages_dir}"
            )

        report_json = (
            safe_read_json(
                self.definition_dir
                / "report.json"
            )
        )

        report_filters = (
            self._parse_filters(
                report_json,
                "report",
            )
        )

        pages = []
        all_metrics = []

        for page_dir in sorted(
            self.pages_dir.iterdir()
        ):
            if not page_dir.is_dir():
                continue

            page_json_path = (
                page_dir
                / "page.json"
            )

            if not page_json_path.exists():
                continue

            page_json = (
                safe_read_json(
                    page_json_path
                )
            )

            page_name = (
                page_json.get(
                    "name"
                )
                or page_dir.name
            )

            display_name = (
                page_json.get(
                    "displayName"
                )
                or page_name
            )

            page_filters = (
                self._parse_filters(
                    page_json,
                    "page",
                )
            )

            visuals = []

            visuals_dir = (
                page_dir
                / "visuals"
            )

            if visuals_dir.exists():
                for visual_dir in sorted(
                    visuals_dir.iterdir()
                ):
                    if not visual_dir.is_dir():
                        continue

                    visual_path = (
                        visual_dir
                        / "visual.json"
                    )

                    if not visual_path.exists():
                        continue

                    parsed_visual = (
                        self._parse_visual(
                            visual_path=
                                visual_path,
                            page_name=
                                page_name,
                            page_display_name=
                                display_name,
                            inherited_filters={
                                "report":
                                    report_filters,
                                "page":
                                    page_filters,
                            },
                        )
                    )

                    visuals.append(
                        parsed_visual
                    )

                    all_metrics.extend(
                        parsed_visual[
                            "metrics"
                        ]
                    )

            pages.append(
                {
                    "page_name":
                        page_name,
                    "page_display_name":
                        display_name,
                    "filters":
                        page_filters,
                    "visuals":
                        visuals,
                }
            )

        approved = sum(
            1
            for metric in all_metrics
            if metric.get(
                "validation_status"
            )
            == "approved"
        )

        needs_review = (
            len(all_metrics)
            - approved
        )

        return {
            "semantic_model":
                self.semantic_model,
            "report_definition_dir":
                str(
                    self.definition_dir
                ),
            "stats": {
                "pages":
                    len(pages),
                "visuals":
                    sum(
                        len(
                            page["visuals"]
                        )
                        for page in pages
                    ),
                "metric_bindings":
                    len(all_metrics),
                "approved_metric_bindings":
                    approved,
                "needs_review":
                    needs_review,
            },
            "report_filters":
                report_filters,
            "pages":
                pages,
            "metrics":
                all_metrics,
        }

    def save(
        self,
        output_path,
    ):
        catalog = self.build()

        output_path = Path(
            output_path
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path.write_text(
            json.dumps(
                catalog,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return catalog

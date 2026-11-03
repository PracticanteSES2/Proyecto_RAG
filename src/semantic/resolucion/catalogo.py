"""Catálogo del motor (carga): enriquecimiento de las métricas al construir QueryPlanBuilder.

Agregaciones documentadas (r2: lavandería «suma de LAVANDERIA[Peso]»), páginas inferidas de la
documentación, formatos de dinero, títulos de tabla como etiqueta, y accesos al catálogo
(_metric_names/_metric_reports/_metric_pages, _dedupe_metrics). Mixin de QueryPlanBuilder: los
métodos se movieron sin cambios desde query_plan_builder.py (ver src/semantic/README_motor.md).
"""
import json
import re

from pathlib import Path
from src.semantic.resolucion.texto import _unique_strings, normalize_text


class CatalogoMixin:


    @staticmethod
    def _with_table_title_labels(metrics):
        """Indicadores de visual cuya etiqueta es el título de una tabla o
        matriz que no nombra el valor que agregan: la etiqueta pasa a ser la
        agregación («Suma de PACIENTE ACOSTADO») y el título deja de ser alias
        (queda en `table_titles`, solo como contexto)."""
        from src.semantic.table_titles import friendly_label, is_table_visual, title_names_value

        result = []
        for metric in metrics:
            appearances = metric.get("appearances") or []
            label = normalize_text(metric.get("label"))
            if (
                metric.get("source_type") != "visual_aggregation" or not label
                or not any(is_table_visual(item.get("visual_type")) for item in appearances)
            ):
                result.append(metric)
                continue
            titles = {
                normalize_text(item.get("visual_title")): item.get("visual_title")
                for item in appearances
                if item.get("visual_title") and not title_names_value(
                    item.get("visual_type"), item.get("visual_title"),
                    metric.get("aggregation"), metric.get("column"),
                )
            }
            if not titles:
                result.append(metric)
                continue
            new_label = metric.get("label")
            if label in titles:
                new_label = friendly_label(metric.get("aggregation"), metric.get("column"), metric.get("aliases"))
            if not new_label:
                result.append(metric)
                continue
            result.append({
                **metric,
                "label": new_label,
                "aliases": [
                    alias for alias in metric.get("aliases") or []
                    if normalize_text(alias) not in titles
                ],
                "table_titles": list(titles.values()),
            })
        return result

    # ---------------- agregaciones implícitas documentadas ----------------
    _ID_COLUMN_RE = re.compile(r"(?:^|[ _])(?:oid|id|cod|codigo|key|rownumber)(?:[ _]|$)|^oid|oid$", re.IGNORECASE)

    def _semantic_document_payloads(self):
        """Documentos semánticos de data/semantic_documents (páginas y diccionario)."""
        root = self.project_root / "data" / "semantic_documents"
        try:
            paths = sorted(root.rglob("*.json")) if root.exists() else []
        except OSError:
            paths = []
        for path in paths:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(document, dict):
                yield document

    def _inferred_pages(self):
        """{(informe normalizado, página normalizada)} de páginas reconstruidas
        de la documentación (marca de tools/local_data/complete_reports.py)."""
        cached = self.__dict__.get("_inferred_pages_cache")
        if cached is not None:
            return cached
        pages = set()
        for report in self.reports:
            directory = report.get("report_definition_dir")
            if not directory:
                continue
            try:
                marker = self._load_json(Path(directory) / "_completed_from_documentation.json", None)
            except (OSError, ValueError):
                marker = None
            if not isinstance(marker, dict):
                continue
            for page in marker.get("inferred_pages") or []:
                pages.add((normalize_text(report.get("report")), normalize_text(page)))
        self._inferred_pages_cache = pages
        return pages

    def _inferred_appearance(self, metric, appearance):
        """¿La aparición es de un visual reconstruido de la documentación?"""
        if appearance.get("inferred"):
            return True
        report = normalize_text(appearance.get("report") or metric.get("report"))
        return (report, normalize_text(appearance.get("page_display_name"))) in self._inferred_pages()

    def _technical_column_name(self, semantic_model, table, column):
        """(tabla, columna) con el nombre exacto del catálogo técnico, o None."""
        for table_item in self._technical_catalog(semantic_model).get("tables", []) or []:
            if normalize_text(table_item.get("name")) != normalize_text(table):
                continue
            for column_item in table_item.get("columns", []) or []:
                if normalize_text(column_item.get("name")) == normalize_text(column):
                    return table_item.get("name"), column_item.get("name")
        return None

    def _with_documented_aggregations(self, metrics):
        """Indicadores de agregación implícita respaldados por la documentación.

        Regla: la documentación (páginas o diccionario de variables) dice
        explícitamente «suma de T[C]» / «sumando T[C]» / «promedio de T[C]» y
        T[C] es una columna numérica (no un identificador) del modelo. Entonces:
        - si un visual RECONSTRUIDO de la documentación, cuyo título cita ese
          mismo texto, agrega otra cosa (PESO TOTAL por Mes =
          DISTINCTCOUNT(OID)), manda la documentación y el visual pasa a esa
          agregación;
        - si ya hay un indicador con esa misma agregación, solo gana los
          nombres documentados como alias;
        - si no, se agrega como indicador del modelo (en las páginas que la
          documentación nombra). Sin esa frase no se crea nada."""
        from src.semantic.documented_aggregations import (
            aggregation_dax, documented_aggregations, friendly_label, text_cites_title,
        )

        try:
            entries = documented_aggregations(self._semantic_document_payloads())
        except Exception:
            return metrics
        if not entries:
            return metrics
        model_names = {}
        for metric in metrics:
            if metric.get("semantic_model"):
                model_names.setdefault(normalize_text(metric.get("semantic_model")), metric.get("semantic_model"))
        reports = {}
        for report in self.reports:
            key = normalize_text(report.get("semantic_model"))
            if key:
                reports.setdefault(key, report)
                model_names.setdefault(key, report.get("semantic_model"))
        result = list(metrics)
        for entry in entries:
            model = model_names.get(entry["model_norm"])
            if not model:
                continue
            names = self._technical_column_name(model, entry["table"], entry["column"])
            if not names or self._column_type(model, *names) != "number":
                continue
            table, column = names
            if self._ID_COLUMN_RE.search(str(column)):
                continue
            aggregation = entry["aggregation"]
            dax = aggregation_dax(table, column, aggregation)
            dax_key = normalize_text(dax)
            model_key = normalize_text(model)
            evidence = entry["texts"][:3]

            for index, metric in enumerate(result):
                if (
                    normalize_text(metric.get("semantic_model")) != model_key
                    or metric.get("source_type") != "visual_aggregation"
                    or normalize_text(metric.get("table")) != normalize_text(table)
                    or normalize_text(metric.get("dax_expression")) == dax_key
                ):
                    continue
                appearances = metric.get("appearances") or []
                if not appearances or not all(self._inferred_appearance(metric, item) for item in appearances):
                    continue
                if not any(text_cites_title(entry["texts"], item.get("visual_title")) for item in appearances):
                    continue
                result[index] = {
                    **metric, "column": column, "aggregation": aggregation, "dax_expression": dax,
                    "aliases": [
                        alias for alias in metric.get("aliases") or []
                        if normalize_text(metric.get("column")) not in normalize_text(alias).split()
                    ],
                    "documented_correction": {
                        "previous_dax": metric.get("dax_expression"), "evidence": evidence,
                    },
                }

            aliases = [
                name for name in entry["names"]
                if not re.search(r"(?<![a-z0-9])(?:por|x|segun)(?![a-z0-9])", normalize_text(name))
            ]
            aliases += [column, friendly_label(aggregation, column)]
            same = [
                index for index, metric in enumerate(result)
                if normalize_text(metric.get("semantic_model")) == model_key
                and normalize_text(metric.get("dax_expression")) == dax_key
            ]
            if same:
                for index in same:
                    metric = result[index]
                    result[index] = {
                        **metric, "aliases": _unique_strings([*(metric.get("aliases") or []), *aliases]),
                    }
                continue

            report = reports.get(model_key) or {}
            pages = {
                normalize_text(page.get("page_display_name") or page.get("page_name")): page
                for page in report.get("pages", []) or []
            }
            appearances = []
            for page_name in entry["pages"]:
                page = pages.get(normalize_text(page_name))
                if page is None:
                    continue
                appearances.append({
                    "report": report.get("report"), "source_group": report.get("source_group"),
                    "page_name": page.get("page_name"), "page_display_name": page.get("page_display_name"),
                    "visual_id": None, "visual_title": None, "visual_type": "documented",
                    "role": "Values", "query_ref": None, "documented": True,
                })
            result.append({
                "metric_id": "doc_" + re.sub(r"[^a-z0-9]+", "_", f"{model_key} {dax_key}").strip("_")[:80],
                "label": aliases[0] if aliases else column,
                "aliases": _unique_strings(aliases),
                "source_type": "documented_aggregation",
                "semantic_model": model,
                "report": report.get("report"),
                "source_group": report.get("source_group"),
                "table": table, "measure": None, "column": column, "aggregation": aggregation,
                "dax_expression": dax, "model_expression": None,
                "description": " ".join(evidence)[:400],
                "validation_status": "approved",
                "reports": [report.get("report")] if report.get("report") else [],
                "source_groups": [report.get("source_group")] if report.get("source_group") else [],
                "appearances": appearances,
            })
        return result

    # ---------------- formato del valor (dinero) ----------------
    _MONEY_NAME_RE = re.compile(
        r"(?<![a-z])(?:monto|montos|valor|valores|costo|costos|precio|precios|pago|pagos|tarifa|tarifas|"
        r"facturado|facturada|facturados|recaudo|recaudado|cartera|glosa|glosado|presupuesto|"
        r"pesos|dinero|subtotal|iva|copago|cuota)(?![a-z])"
    )
    _NOT_MONEY_LABEL_RE = re.compile(
        r"(?<![a-z])(?:dia|dias|tiempo|tiempos|hora|horas|minuto|minutos|cantidad|cantidades|numero|"
        r"unidades|unidad|porcentaje|promedio|conteo|recuento|pacientes|registros|casos)(?![a-z])|%"
    )
    _SUM_EXPRESSION_RE = re.compile(r"^\s*(?:CALCULATE\s*\(\s*)?SUMX?\s*\(", re.IGNORECASE)

    def _is_money_metric(self, metric):
        """¿El indicador es una suma de dinero? Por su formato de Power BI
        («$#,0») o por ser SUM/SUMX de una columna de dinero (MONTO_FACTURADO,
        VALOR, COSTO...) sin palabras de otra unidad en su nombre."""
        fmt = str(metric.get("format_string") or "")
        if "$" in fmt or "€" in fmt or "currency" in fmt.lower():
            return True
        if fmt:
            return False
        label = normalize_text(f"{metric.get('label') or ''} {metric.get('measure') or ''}")
        if self._NOT_MONEY_LABEL_RE.search(label):
            return False
        expression = str(
            metric.get("model_expression") or metric.get("base_dax_expression") or metric.get("dax_expression") or ""
        )
        if not self._SUM_EXPRESSION_RE.search(expression):
            return False
        columns = " ".join(re.findall(r"\[([^\]]+)\]", expression))
        names = normalize_text(columns.replace("_", " "))
        return bool(self._MONEY_NAME_RE.search(names))

    def _with_value_formats(self, metrics):
        result = []
        for metric in metrics:
            if not metric.get("format") and self._is_money_metric(metric):
                metric = {**metric, "format": "currency"}
            result.append(metric)
        return result

    def _load_json(self, path, default):
        if not Path(path).exists():
            return default
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def _normalize_reports(self, catalog):
        reports = list(catalog.get("reports", []) or [])
        if reports:
            return reports
        if catalog.get("semantic_model"):
            return [{
                "report": catalog.get("report") or catalog.get("semantic_model"),
                "semantic_model": catalog.get("semantic_model"),
                "source_group": catalog.get("source_group"),
                "pages": catalog.get("pages", []),
                "metrics": catalog.get("metrics", []),
            }]
        return []

    # ---------------- metrics ----------------
    def _metric_names(self, metric):
        values = [metric.get("label"), metric.get("measure")]
        values.extend(metric.get("aliases", []) or [])
        # Título de una tabla que no nombra el valor (ver _with_table_title_labels).
        table_titles = {normalize_text(title) for title in metric.get("table_titles") or []}
        for appearance in metric.get("appearances", []) or []:
            title = appearance.get("visual_title")
            values.extend([
                None if normalize_text(title) in table_titles else title,
                appearance.get("native_query_ref"),
            ])
        return _unique_strings(values)

    def _metric_reports(self, metric):
        values = [metric.get("report")]
        values.extend(metric.get("reports", []) or [])
        for appearance in metric.get("appearances", []) or []:
            values.append(appearance.get("report"))
        return _unique_strings(values)

    def _metric_pages(self, metric):
        values = [metric.get("dashboard")]
        for appearance in metric.get("appearances", []) or []:
            values.append(appearance.get("page_display_name"))
        return _unique_strings(values)

    def _metric_visual_ids(self, metric):
        return {
            str(appearance.get("visual_id"))
            for appearance in metric.get("appearances", []) or []
            if appearance.get("visual_id")
        }

    def _dedupe_metrics(self, metrics):
        result = []
        seen = set()
        for metric in metrics:
            reports = metric.get("reports", []) or []
            key = (
                normalize_text(metric.get("semantic_model")),
                normalize_text(metric.get("report") or (reports[0] if reports else None)),
                normalize_text(metric.get("label")),
                normalize_text(metric.get("dax_expression")),
            )
            if key in seen:
                continue
            result.append(metric)
            seen.add(key)
        return result

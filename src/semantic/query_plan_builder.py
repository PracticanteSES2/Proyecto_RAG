import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

GENERIC_QUERY_WORDS = {
    "cuanto", "cuantos", "cuantas", "cual", "cuales", "es", "son",
    "hay", "hubo", "tiene", "tienen", "total", "valor", "cantidad",
    "numero", "dame", "muestra", "mostrar", "del", "de", "la", "el",
    "los", "las", "un", "una", "en", "al", "para", "por",
    "corresponden", "correspondiente", "correspondientes", "tablero",
    "informe", "hospitalario", "institucionales",
}

DESCRIPTIVE_PATTERNS = (
    "que significa", "que es", "que quiere decir", "como se calcula",
    "como se define", "definicion de", "explica",
)

DIMENSION_SYNONYMS = {
    "servicio": {"servicio", "servicios", "unidad", "unidades", "area", "areas"},
    "aseguradora": {"asegurador", "aseguradora", "aseguradoras", "eps", "pagador", "pagadores"},
    "especialidad": {"especialidad", "especialidades"},
    "cirujano": {"cirujano", "cirujanos", "medico", "medicos"},
    "estado": {"estado", "estados", "situacion"},
    "causa": {"causa", "causas", "motivo", "motivos"},
    "modalidad": {"modalidad", "modalidades", "tipo atencion", "tipo de atencion"},
    "sexo": {"sexo", "genero"},
    "clasificacion": {"clasificacion", "triage"},
    "tipo": {"tipo", "tipos"},
}


def normalize_text(value):
    value = str(value or "").lower().strip()
    value = "".join(
        char for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    value = re.sub(r"[^a-z0-9%]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_token(token):
    token = normalize_text(token)
    if not token:
        return ""
    if token.endswith("iones") and len(token) > 6:
        return token[:-5] + "ion"
    if token.endswith("ales") and len(token) > 5:
        return token[:-2]
    if token.endswith("ares") and len(token) > 5:
        return token[:-2]
    if token.endswith("ores") and len(token) > 5:
        return token[:-2]
    if token.endswith("s") and len(token) > 4:
        return token[:-1]
    return token


def canonical_tokens(value):
    result = []
    for token in normalize_text(value).split():
        item = canonical_token(token)
        if item:
            result.append(item)
    return result


def _token_similarity(left, right):
    if left == right:
        return 1.0
    if len(left) >= 5 and len(right) >= 5 and (
        left.startswith(right[:5]) or right.startswith(left[:5])
    ):
        return 0.90
    return SequenceMatcher(None, left, right).ratio()


def _phrase_score(question, candidate):
    q = normalize_text(question)
    c = normalize_text(candidate)
    if not q or not c:
        return 0.0

    if re.search(r"(?<![a-z0-9])" + re.escape(c) + r"(?![a-z0-9])", q):
        specificity = min(len(c.split()), 6)
        return min(1.20, 1.00 + 0.03 * specificity)

    q_tokens = canonical_tokens(q)
    c_tokens = canonical_tokens(c)
    if not q_tokens or not c_tokens:
        return 0.0

    matched = []
    for candidate_token in c_tokens:
        best = max(
            (_token_similarity(candidate_token, question_token) for question_token in q_tokens),
            default=0.0,
        )
        matched.append(best)

    coverage = sum(1 for value in matched if value >= 0.82) / len(c_tokens)
    if coverage < 0.60:
        return 0.0

    average = sum(matched) / len(matched)
    precision = min(len(c_tokens), len(q_tokens)) / max(len(c_tokens), len(q_tokens))
    return min(0.99, 0.68 * coverage + 0.24 * average + 0.08 * precision)


def _unique_strings(values):
    result = []
    seen = set()
    for value in values:
        if not value:
            continue
        key = normalize_text(value)
        if key and key not in seen:
            result.append(str(value))
            seen.add(key)
    return result


class QueryPlanBuilder:
    """Planificador determinista: métrica -> modelo -> dimensiones -> DAX."""

    def __init__(
        self,
        master_metrics_path,
        visual_catalog_path,
        source_router,
        powerbi_provider,
        project_root=None,
        min_metric_score=0.74,
        ambiguity_margin=0.055,
        max_implicit_dimensions=6,
    ):
        self.master_metrics_path = Path(master_metrics_path)
        self.visual_catalog_path = Path(visual_catalog_path)
        self.source_router = source_router
        self.powerbi_provider = powerbi_provider
        self.project_root = Path(
            project_root or self.master_metrics_path.resolve().parents[2]
        ).resolve()
        self.min_metric_score = float(min_metric_score)
        self.ambiguity_margin = float(ambiguity_margin)
        self.max_implicit_dimensions = int(max_implicit_dimensions)
        self.master = self._load_json(self.master_metrics_path, {})
        self.visual_catalog = self._load_json(self.visual_catalog_path, {})
        self.metrics = list(self.master.get("metrics", []) or [])
        self.value_cache = {}
        self.domain_errors = {}  # Fallos temporales XMLA: nunca cachear como dominio vacío.
        self.reports = self._normalize_reports(self.visual_catalog)
        self.dimension_fields = self._build_dimension_index()
        self.static_values = self._build_static_value_index()

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
        for appearance in metric.get("appearances", []) or []:
            values.extend([
                appearance.get("visual_title"),
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

    def _source_context(self, question, dashboard=None):
        try:
            return self.source_router.resolve(question=question, dashboard=dashboard)
        except Exception as error:
            return {
                "status": "error",
                "routing_strength": "none",
                "error": f"{type(error).__name__}: {error}",
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

    def _metric_business_question(self, question, source_context):
        text = normalize_text(question)

        removals = [
            source_context.get("report"),
            source_context.get("semantic_model"),
            source_context.get("source_group"),
        ]

        for value in removals:
            normalized = normalize_text(value)
            if normalized:
                text = re.sub(
                    r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])",
                    " ",
                    text,
                )

        text = re.sub(r"\b(?:tablero|informe|modelo semantico)\b", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _resolve_metric(self, question, source_context, selected_metric_id=None):
        business_question = self._metric_business_question(question, source_context)
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        model_hint = source_context.get("semantic_model") if strong else None
        report_hint = source_context.get("report") if strong else None
        candidates = []

        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            metric_model = metric.get("semantic_model")
            metric_reports = self._metric_reports(metric)
            if model_hint and normalize_text(metric_model) != normalize_text(model_hint):
                continue
            if report_hint and metric_reports and not any(
                normalize_text(value) == normalize_text(report_hint)
                for value in metric_reports
            ):
                continue

            # Una selección realizada durante una aclaración manda por ID,
            # no por el texto de la respuesta del usuario.
            if selected_metric_id is not None:
                if str(metric.get("metric_id")) != str(selected_metric_id):
                    continue
                return {
                    "status": "resolved", "metric": metric,
                    "matched_name": metric.get("label"), "score": 10.0,
                    "candidates": [{"metric": metric, "score": 10.0,
                                    "business_score": 10.0,
                                    "matched_name": metric.get("label")}],
                }

            primary_label = metric.get("label") or ""
            primary_score = _phrase_score(business_question, primary_label)
            label_is_exact = bool(
                normalize_text(primary_label)
                and re.search(
                    r"(?<![a-z0-9])" + re.escape(normalize_text(primary_label))
                    + r"(?![a-z0-9])",
                    normalize_text(business_question),
                )
            )

            aliases = [
                item for item in self._metric_names(metric)
                if normalize_text(item) != normalize_text(primary_label)
            ]
            best_alias = max(
                ((_phrase_score(business_question, name), name) for name in aliases),
                key=lambda pair: pair[0], default=(0.0, None),
            )
            # El título propio y exacto de EGRESOS debe ganar frente a
            # medidas AÑO ACTUAL / AÑO ANTERIOR que solo heredan el alias
            # visual genérico EGRESOS. Alias siguen siendo utilizables cuando
            # no aparece el nombre principal.
            if label_is_exact:
                best_name = primary_label
                best_name_score = primary_score
                name_priority = 0.32
            elif best_alias[0] > primary_score:
                best_name = best_alias[1]
                best_name_score = best_alias[0]
                name_priority = 0.0
            else:
                best_name = primary_label
                best_name_score = primary_score
                name_priority = 0.0

            if best_name_score <= 0:
                continue
            score = best_name_score + name_priority
            if model_hint:
                score += 0.15
            if report_hint:
                score += 0.10
            page_score = max(
                (_phrase_score(question, page) for page in self._metric_pages(metric)),
                default=0.0,
            )
            score += min(0.06, 0.045 * page_score)
            candidates.append({
                "metric": metric,
                "score": round(score, 4),
                "business_score": round(best_name_score, 4),
                "matched_name": best_name,
                "exact_primary_label": label_is_exact,
            })

        candidates.sort(key=lambda item: item["score"], reverse=True)
        if not candidates:
            return {"status": "not_found", "candidates": []}
        best = candidates[0]
        if best["business_score"] < self.min_metric_score:
            return {"status": "not_found", "candidates": candidates[:8]}
        if len(candidates) > 1:
            second = candidates[1]
            bm, sm = best["metric"], second["metric"]
            same_logic = (
                normalize_text(bm.get("semantic_model")) == normalize_text(sm.get("semantic_model"))
                and normalize_text(bm.get("dax_expression")) == normalize_text(sm.get("dax_expression"))
                and normalize_text(bm.get("label")) == normalize_text(sm.get("label"))
            )
            if not same_logic and best["score"] - second["score"] < self.ambiguity_margin:
                return {"status": "ambiguous", "candidates": candidates[:8]}

        return {
            "status": "resolved", "metric": best["metric"],
            "matched_name": best["matched_name"], "score": best["score"],
            "candidates": candidates[:8],
        }

    # ---------------- dimension index ----------------
    def _physical_column(self, field):
        if field.get("column"):
            return field.get("column")
        if field.get("kind") == "hierarchy_level":
            parts = [part for part in str(field.get("query_ref") or "").split(".") if part]
            if len(parts) >= 2:
                return parts[1]
        return None

    def _field_aliases(self, field):
        values = [
            field.get("display_name"), field.get("native_query_ref"),
            field.get("column"), field.get("level"), field.get("query_ref"),
        ]
        aliases = _unique_strings(values)
        normalized_aliases = {normalize_text(alias) for alias in aliases}
        for synonyms in DIMENSION_SYNONYMS.values():
            if any(any(synonym in alias for synonym in synonyms) for alias in normalized_aliases):
                aliases.extend(sorted(synonyms))
        return _unique_strings(aliases)

    def _build_dimension_index(self):
        fields = []
        for report in self.reports:
            report_name = report.get("report") or report.get("semantic_model")
            semantic_model = report.get("semantic_model")
            source_group = report.get("source_group")
            for page in report.get("pages", []) or []:
                page_name = page.get("page_display_name") or page.get("page_name")
                for visual in page.get("visuals", []) or []:
                    for field in visual.get("fields", []) or []:
                        if field.get("kind") not in ("column", "hierarchy_level"):
                            continue
                        table = field.get("table")
                        column = self._physical_column(field)
                        if not table or not column:
                            continue
                        fields.append({
                            "semantic_model": semantic_model,
                            "report": report_name,
                            "source_group": source_group,
                            "page": page_name,
                            "visual_id": visual.get("visual_id"),
                            "visual_type": visual.get("visual_type"),
                            "role": field.get("role"),
                            "kind": field.get("kind"),
                            "table": table,
                            "column": column,
                            "level": field.get("level"),
                            "query_ref": field.get("query_ref"),
                            "aliases": self._field_aliases(field),
                        })
        return fields

    def _iter_filters(self, value):
        if isinstance(value, list):
            for item in value:
                yield from self._iter_filters(item)
        elif isinstance(value, dict):
            if "field" in value and isinstance(value.get("field"), dict):
                yield value
            for item in value.values():
                yield from self._iter_filters(item)

    def _build_static_value_index(self):
        result = {}
        for report in self.reports:
            semantic_model = report.get("semantic_model")
            for page in report.get("pages", []) or []:
                for filter_item in self._iter_filters(page.get("filters", {})):
                    field = filter_item.get("field", {})
                    table = field.get("table")
                    column = field.get("column")
                    if not table or not column:
                        continue
                    key = (normalize_text(semantic_model), normalize_text(table), normalize_text(column))
                    result.setdefault(key, [])
                    for value in filter_item.get("values", []) or []:
                        if value is not None and str(value) not in result[key]:
                            result[key].append(str(value))
        return result

    def _relevant_dimensions(self, metric):
        semantic_model = metric.get("semantic_model")
        reports = {normalize_text(value) for value in self._metric_reports(metric)}
        pages = {normalize_text(value) for value in self._metric_pages(metric)}
        visual_ids = self._metric_visual_ids(metric)
        candidates = {}

        for field in self.dimension_fields:
            if normalize_text(field.get("semantic_model")) != normalize_text(semantic_model):
                continue
            if reports and normalize_text(field.get("report")) not in reports:
                continue

            score = 10
            if str(field.get("visual_id")) in visual_ids:
                score += 110
            if normalize_text(field.get("page")) in pages:
                score += 65
            if normalize_text(field.get("visual_type")) == "slicer":
                score += 35
            if normalize_text(field.get("role")) in {
                "category", "group", "rows", "legend", "series", "values"
            }:
                score += 15

            key = (
                normalize_text(field.get("table")),
                normalize_text(field.get("column")),
                normalize_text(field.get("level")),
            )
            item = {**field, "relevance_score": score}
            if key not in candidates or score > candidates[key]["relevance_score"]:
                candidates[key] = item

        values = list(candidates.values())
        values.sort(key=lambda item: item["relevance_score"], reverse=True)
        return values

    def _dimension_match_score(self, text, field):
        return max((_phrase_score(text, alias) for alias in field.get("aliases", [])), default=0.0)

    def _best_dimension(self, text, candidates, exclude_temporal=False):
        scored = []
        for field in candidates:
            if exclude_temporal and self._is_temporal_field(field):
                continue
            score = self._dimension_match_score(text, field)
            if score <= 0:
                continue
            score += min(0.12, field.get("relevance_score", 0) / 1000.0)
            scored.append((score, field))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1] if scored else None

    # ---------------- actual dimension values ----------------
    def _table_ref(self, table):
        return "'" + str(table).replace("'", "''") + "'"

    def _column_ref(self, column):
        return "[" + str(column).replace("]", "]]" ) + "]"

    def _get_values(self, semantic_model, table, column):
        key = (semantic_model, table, column)
        if key in self.value_cache:
            return self.value_cache[key]

        static_key = (normalize_text(semantic_model), normalize_text(table), normalize_text(column))
        values = list(self.static_values.get(static_key, []) or [])
        dax = f'''EVALUATE\nTOPN(\n    2500,\n    FILTER(\n        SELECTCOLUMNS(\n            VALUES({self._table_ref(table)}{self._column_ref(column)}),\n            "Value", {self._table_ref(table)}{self._column_ref(column)}\n        ),\n        NOT ISBLANK([Value])\n    ),\n    [Value], ASC\n)'''
        try:
            result = self.powerbi_provider.execute_dax(dax=dax, semantic_model=semantic_model)
        except Exception as exc:
            result = {"status": "error", "error": str(exc)}

        if result.get("status") != "success":
            self.domain_errors[key] = {
                "status": result.get("status"),
                "error_type": result.get("error_type"),
                "message": str(result.get("error") or result.get("message") or "Sin detalle")[:300],
            }
            # No afirmar que un filtro fue verificado si XMLA falló,
            # aunque el PBIR tenga valores estáticos potencialmente antiguos.
            # El siguiente intento consultará de nuevo el dominio.
            return None

        self.domain_errors.pop(key, None)
        for row in result.get("rows", []) or []:
            if not row:
                continue
            value = next(iter(row.values()), None)
            if value is not None and str(value) not in values:
                values.append(str(value))
        self.value_cache[key] = values
        return values

    def _value_match_score(self, question, value, value_hint=None):
        q = normalize_text(value_hint or question)
        v = normalize_text(value)
        if not q or not v:
            return 0.0
        if v in q:
            return 1.10

        q_tokens = [
            token for token in canonical_tokens(q)
            if len(token) >= 2 and token not in GENERIC_QUERY_WORDS
        ]
        v_tokens = set(canonical_tokens(v))
        if not q_tokens:
            return 0.0
        exact = [token for token in q_tokens if token in v_tokens]
        coverage = len(exact) / len(q_tokens)
        if coverage == 1.0:
            return min(1.05, 0.94 + min(len(q_tokens), 4) * 0.02)
        if coverage >= 0.60:
            return 0.72 + 0.22 * coverage
        return min(0.80, SequenceMatcher(None, q, v).ratio())

    def _resolve_value(self, question, field, semantic_model, value_hint=None):
        values = self._get_values(semantic_model, field["table"], field["column"])
        if values is None:
            return None
        scored = []
        for value in values:
            score = self._value_match_score(question, value, value_hint=value_hint)
            if score > 0:
                scored.append((score, value))
        scored.sort(key=lambda item: (item[0], len(normalize_text(item[1]))), reverse=True)
        if not scored or scored[0][0] < 0.84:
            return None
        return {"value": scored[0][1], "score": round(scored[0][0], 4)}

    # ---------------- group / filter parsing ----------------
    def _clean_tail(self, value, metric):
        text = normalize_text(value)
        removals = self._metric_reports(metric) + [metric.get("semantic_model")]
        for removal in removals:
            normalized = normalize_text(removal)
            if normalized:
                text = re.sub(r"\ben\s+(?:el|la)?\s*" + re.escape(normalized) + r"\b.*$", "", text)
        text = re.sub(r"\ben\s+20\d{2}\b", "", text)
        for month in MONTHS:
            text = re.sub(r"\ben\s+" + re.escape(month) + r"(?:\s+de\s+20\d{2})?\b", "", text)
        return re.sub(r"\s+", " ", text).strip()

    def _detect_group_or_dimension_filter(self, question, metric, candidates):
        normalized = normalize_text(question)
        match = re.search(
            r"\b(?:por|segun|agrupado por|agrupada por|desglosado por|desglosada por)\s+(?:el|la|los|las)?\s*(.+)$",
            normalized,
        )
        if not match:
            return {"group_by": [], "explicit_filters": []}

        tail = self._clean_tail(match.group(1), metric)
        if not tail:
            return {"group_by": [], "explicit_filters": []}

        best = self._best_dimension(tail, candidates, exclude_temporal=True)
        if not best:
            return {"group_by": [], "explicit_filters": []}

        matched_alias = None
        aliases = sorted(best.get("aliases", []), key=lambda value: len(normalize_text(value)), reverse=True)
        for alias in aliases:
            alias_norm = normalize_text(alias)
            if alias_norm and (tail == alias_norm or tail.startswith(alias_norm + " ")):
                matched_alias = alias_norm
                break
        if not matched_alias:
            return {"group_by": [], "explicit_filters": []}

        remainder = tail[len(matched_alias):].strip()
        remainder = re.sub(r"^(?:de|del|en|igual a|=)\s+", "", remainder).strip()
        if not remainder:
            return {"group_by": [best], "explicit_filters": []}
        return {"group_by": [], "explicit_filters": [{"field": best, "value_hint": remainder}]}

    def _remove_metric_and_report_phrases(self, question, metric, source_context):
        """Descarta los nombres de métrica/informe ANTES de buscar filtros.

        Antes, un campo llamado EGRESOS se interpretaba como dimensión
        dentro de la expresión EGRESOS PROBABLES y exigía un valor «probables hay».
        """
        cleaned = normalize_text(question)
        phrases = [
            metric.get("label"),
            source_context.get("report"), source_context.get("semantic_model"),
            metric.get("semantic_model"),
            *self._metric_reports(metric),
        ]
        # Quitar matched_name si es alias coincidente con la pregunta se
        # gestiona adicionalmente en _implicit_value_text.
        for phrase in sorted(_unique_strings(phrases), key=len, reverse=True):
            norm = normalize_text(phrase)
            if norm:
                cleaned = re.sub(r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", " ", cleaned)
        cleaned = re.sub(r"\b(?:tablero|informe)\b", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _detect_explicit_dimension_filters(
        self, question, candidates, already_fields=None,
        metric=None, source_context=None,
    ):
        normalized = (
            self._remove_metric_and_report_phrases(question, metric, source_context or {})
            if metric else normalize_text(question)
        )
        already_fields = already_fields or set()
        filters = []
        for field in candidates:
            if self._is_temporal_field(field):
                continue
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in already_fields:
                continue
            aliases = sorted(field.get("aliases", []), key=lambda v: len(normalize_text(v)), reverse=True)
            for alias in aliases:
                alias_norm = normalize_text(alias)
                if not alias_norm or len(alias_norm) < 3:
                    continue
                pattern = (
                    r"\b" + re.escape(alias_norm) + r"\b"
                    + r"(?:\s+(?:de|del|igual a|=|:))?"
                    + r"\s+([a-z0-9][a-z0-9\s\.\-]{1,80})"
                )
                match = re.search(pattern, normalized)
                if not match:
                    continue
                hint = re.split(
                    r"\b(?:en|durante|para el|para la|del tablero|del informe)\b",
                    match.group(1), maxsplit=1,
                )[0].strip()
                # «servicio de urgencias» es filtro; «servicio por...»,
                # «servicio hay...» o «servicio en ...» no lo son.
                invalid_start = {"hay", "hubo", "tiene", "tienen", "es", "son", "por", "para", "con"}
                if not hint or canonical_tokens(hint)[0] in invalid_start:
                    continue
                if len(hint.split()) == 1 and hint in GENERIC_QUERY_WORDS:
                    continue
                filters.append({"field": field, "value_hint": hint})
                already_fields.add(key)
                break
        return filters

    def _metric_removal_tokens(self, metric, matched_name, source_context):
        values = [matched_name, metric.get("label"), metric.get("semantic_model"), source_context.get("report")]
        values.extend(self._metric_reports(metric))
        tokens = set()
        for value in values:
            for token in canonical_tokens(value):
                tokens.add(token)
                without_numeric_suffix = re.sub(r"\d+$", "", token)
                if len(without_numeric_suffix) >= 3:
                    tokens.add(without_numeric_suffix)
        return tokens

    def _implicit_value_text(self, question, metric, matched_name, source_context, group_by):
        removals = self._metric_removal_tokens(metric, matched_name, source_context)
        for group in group_by:
            for alias in group.get("aliases", []):
                removals.update(canonical_tokens(alias))
        removals.update(canonical_token(word) for word in GENERIC_QUERY_WORDS)
        removals.update({"a", "al", "del", "de", "en", "hay", "hubo", "dentro", "segun"})
        removals.update(canonical_token(word) for word in MONTHS)

        result = []
        for token in canonical_tokens(question):
            if token in removals or re.fullmatch(r"20\d{2}", token) or token.isdigit():
                continue
            result.append(token)
        return " ".join(result).strip()

    def _resolve_implicit_filter(
        self, question, metric, matched_name, source_context,
        candidates, group_by, used_fields,
    ):
        leftover = self._implicit_value_text(question, metric, matched_name, source_context, group_by)
        if not leftover:
            return None

        best = None
        checked = 0
        for field in candidates:
            if checked >= self.max_implicit_dimensions:
                break
            if self._is_temporal_field(field):
                continue
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in used_fields:
                continue

            visual_type = normalize_text(field.get("visual_type"))
            role = normalize_text(field.get("role"))
            if visual_type not in {
                "slicer", "piechart", "donutchart", "treemap", "table", "pivottable",
                "clusteredbarchart", "clusteredcolumnchart", "stackedbarchart", "stackedcolumnchart",
            } and role not in {"category", "group", "rows", "legend"}:
                continue

            checked += 1
            resolved = self._resolve_value(
                question=question, field=field,
                semantic_model=metric.get("semantic_model"),
                value_hint=leftover,
            )
            if not resolved:
                continue
            candidate = {"field": field, **resolved}
            if best is None or candidate["score"] > best["score"]:
                best = candidate
            if best and best["score"] >= 1.0:
                break
        return best

    # ---------------- time ----------------
    def _is_temporal_field(self, field):
        aliases = " ".join(normalize_text(value) for value in field.get("aliases", []))
        table = normalize_text(field.get("table"))
        column = normalize_text(field.get("column"))
        level = normalize_text(field.get("level"))
        return (
            table in {"calendario", "calendar", "fecha", "dates"}
            or level in {"ano", "mes", "dia", "year", "month", "day"}
            or any(token in aliases for token in ("date", "fecha", " ano", " mes"))
            or column in {"date", "fecha", "fecha servicio", "fecha atencion"}
        )

    def _detect_year_month(self, question):
        normalized = normalize_text(question)
        year_match = re.search(r"\b(20\d{2})\b", normalized)
        year = int(year_match.group(1)) if year_match else None
        month = None
        month_name = None
        for name, number in MONTHS.items():
            if re.search(r"\b" + re.escape(name) + r"\b", normalized):
                month = number
                month_name = name
                break
        return year, month, month_name

    def _best_date_field(self, candidates):
        temporal = [field for field in candidates if self._is_temporal_field(field)]
        if not temporal:
            return None

        def score(field):
            value = field.get("relevance_score", 0)
            column = normalize_text(field.get("column"))
            table = normalize_text(field.get("table"))
            if column in {"date", "fecha"}:
                value += 80
            if table in {"calendario", "calendar"}:
                value += 60
            if field.get("kind") == "hierarchy_level":
                value += 30
            return value

        temporal.sort(key=score, reverse=True)
        return temporal[0]

    def _temporal_filters(self, question, candidates):
        year, month, month_name = self._detect_year_month(question)
        if year is None and month is None:
            return []
        date_field = self._best_date_field(candidates)
        if not date_field:
            return []
        return [{
            "type": "date_range",
            "table": date_field["table"],
            "column": date_field["column"],
            "year": year,
            "month": month,
            "month_name": month_name,
            "source": "query_plan_temporal",
        }]

    # ---------------- public API ----------------
    def looks_numeric(self, question, dashboard=None):
        normalized = normalize_text(question)
        if any(pattern in normalized for pattern in DESCRIPTIVE_PATTERNS):
            return False

        numeric_terms = (
            "cuanto", "cuantos", "cuantas", "cantidad", "numero", "total",
            "promedio", "porcentaje", "valor", "capacidad", "giro", "ocupacion",
            "ocupacional", "ingresos", "egresos",
        )
        if any(re.search(r"\b" + re.escape(term) + r"\b", normalized) for term in numeric_terms):
            return True

        source_context = self._source_context(question, dashboard=dashboard)
        metric_result = self._resolve_metric(question, source_context)
        if metric_result.get("status") == "resolved" and metric_result.get("score", 0) >= 0.98:
            if normalized.startswith(("cual es", "cuales son", "dame", "muestra")):
                return True
        return False

    def build(self, question, intent_result=None, selected_metric_id=None):
        intent_result = intent_result or {}
        dashboard = intent_result.get("dashboard")
        source_context = self._source_context(question, dashboard=dashboard)
        metric_result = self._resolve_metric(
            question, source_context, selected_metric_id=selected_metric_id
        )

        if metric_result.get("status") != "resolved":
            return {
                "status": metric_result.get("status", "not_found"),
                "stage": "metric",
                "question": question,
                "source_context": source_context,
                "metric_resolution": metric_result,
            }

        metric = metric_result["metric"]
        semantic_model = metric.get("semantic_model")
        reports = metric.get("reports", []) or []
        report = metric.get("report") or (reports[0] if reports else source_context.get("report"))
        candidates = self._relevant_dimensions(metric)

        group_detection = self._detect_group_or_dimension_filter(question, metric, candidates)
        group_by = group_detection["group_by"]

        # Nunca convertir silenciosamente "por servicio" en total escalar
        # si la metadata de ese informe no expone SERVICIO.
        requested_group = re.search(
            r"\b(?:por|segun|agrupad[oa] por|desglosad[oa] por)\s+"
            r"(?:el|la|los|las)?\s*"
            r"(servicio|servicios|especialidad|especialidades|aseguradora|asegurador|sexo|estado|tipo)\b",
            normalize_text(question),
        )
        if requested_group and not group_by and not group_detection["explicit_filters"]:
            return {
                "status": "unsupported_filter", "stage": "dimensions",
                "reason": "requested_dimension_not_found_in_report",
                "requested_dimension": requested_group.group(1),
                "question": question, "semantic_model": semantic_model,
                "source_context": source_context, "metric_resolution": metric_result,
            }

        explicit_specs = list(group_detection["explicit_filters"])
        used_fields = {
            (normalize_text(spec["field"].get("table")), normalize_text(spec["field"].get("column")))
            for spec in explicit_specs
        }
        explicit_specs.extend(
            self._detect_explicit_dimension_filters(
                question, candidates, already_fields=used_fields,
                metric=metric, source_context=source_context,
            )
        )

        filters = []
        for spec in explicit_specs:
            field = spec["field"]
            resolved = self._resolve_value(
                question=question, field=field, semantic_model=semantic_model,
                value_hint=spec.get("value_hint"),
            )
            if not resolved:
                return {
                    "status": "unsupported_filter", "stage": "dimension_value",
                    "reason": "requested_value_not_found",
                    "requested_value": spec.get("value_hint"),
                    "dimension": {"table": field["table"], "column": field["column"]},
                    "question": question, "semantic_model": semantic_model,
                    "source_context": source_context, "metric_resolution": metric_result,
                    "domain_error": self.domain_errors.get((semantic_model, field["table"], field["column"])),
                }
            filters.append({
                "type": "categorical",
                "concept": (field.get("aliases") or [field["column"]])[0],
                "table": field["table"],
                "column": field["column"],
                "operator": "=",
                "value": resolved["value"],
                "match_score": resolved["score"],
                "source": "query_plan_explicit_dimension",
            })
            used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))

        implicit = None
        if not filters and not group_by:
            implicit = self._resolve_implicit_filter(
                question=question, metric=metric,
                matched_name=metric_result.get("matched_name"),
                source_context=source_context, candidates=candidates,
                group_by=group_by, used_fields=used_fields,
            )
        if implicit:
            field = implicit["field"]
            filters.append({
                "type": "categorical",
                "concept": (field.get("aliases") or [field["column"]])[0],
                "table": field["table"],
                "column": field["column"],
                "operator": "=",
                "value": implicit["value"],
                "match_score": implicit["score"],
                "source": "query_plan_implicit_value",
            })

        temporal_filters = self._temporal_filters(question, candidates)
        year, month, _ = self._detect_year_month(question)
        if (year is not None or month is not None) and not temporal_filters:
            return {
                "status": "unsupported_filter", "stage": "temporal_filters",
                "reason": "date_dimension_not_found_in_report",
                "requested_year": year, "requested_month": month,
                "question": question, "semantic_model": semantic_model,
                "source_context": source_context, "metric_resolution": metric_result,
            }
        filters.extend(temporal_filters)

        # Una consulta con un valor categórico implícito (p. ej. Nueva EPS)
        # no debe transformarse silenciosamente en el total sin filtro.
        if not any(item.get("type") == "categorical" for item in filters) and not group_by:
            leftover = self._implicit_value_text(
                question, metric, metric_result.get("matched_name"),
                source_context, group_by,
            )
            significant = [token for token in leftover.split() if len(token) >= 3]
            if significant:
                return {
                    "status": "unsupported_filter", "stage": "implicit_dimension",
                    "reason": "possible_dimension_value_not_resolved",
                    "unresolved_text": leftover,
                    "question": question, "semantic_model": semantic_model,
                    "source_context": source_context, "metric_resolution": metric_result,
                }

        normalized_group_by = [{
            "table": field["table"],
            "column": field["column"],
            "label": (field.get("aliases") or [field["column"]])[0],
            "source": "query_plan_group_by",
        } for field in group_by]

        pages = self._metric_pages(metric)
        return {
            "status": "ready",
            "intent": "numeric_query",
            "mode": "grouped" if normalized_group_by else "scalar",
            "question": question,
            "source_context": source_context,
            "semantic_model": semantic_model,
            "report": report,
            "dashboard": metric.get("dashboard") or (pages[0] if pages else None),
            "metric": metric,
            "metric_match": {
                "matched_name": metric_result.get("matched_name"),
                "score": metric_result.get("score"),
            },
            "filters": filters,
            "group_by": normalized_group_by,
            "dimension_candidates_checked": min(len(candidates), 20),
        }

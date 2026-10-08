import json
import math
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
    "hay", "hubo", "tiene", "tienen", "valor", "cantidad",
    "dame", "muestra", "mostrar", "del", "de", "la", "el",
    "los", "las", "un", "una", "en", "al", "para", "por",
    "corresponden", "correspondiente", "correspondientes", "tablero",
    "informe", "institucionales",
}

# Palabras discriminativas para elegir métrica (p. ej. «Total Cirugías»
# frente a «Cirugías»), pero sin valor como filtro: no deben quedar como
# «término sin aplicar» ni intentar resolverse como valor de dimensión.
FILTER_NEUTRAL_WORDS = {"total", "numero"}

# Relleno conversacional que nunca explica ni agrega significado.
STOPWORDS = {
    "a", "al", "con", "sin", "que", "y", "o", "u", "e", "me", "mi", "se",
    "su", "sus", "lo", "le", "les", "fue", "fueron", "ser", "sido", "esta",
    "este", "estos", "estas", "ese", "esa", "hay", "hubo", "han", "ha",
    "dentro", "segun", "mes", "ano", "anio", "durante", "favor", "por",
    "dime", "dame", "quiero", "saber", "cuanto", "cuantos", "cuanta",
    "cuantas", "cual", "cuales", "como", "donde", "cuando", "tuvo",
    "tuvieron", "tiene", "tienen", "son", "es", "del", "de", "la", "el",
    "los", "las", "un", "una", "unos", "unas", "en", "para", "muestra",
    "mostrar", "valor", "cantidad", "informe", "tablero", "modelo",
    "semantico", "dashboard", "reporte", "pagina", "hacer", "ver",
}

GENERIC_PAGE_WORDS = {"general", "inicio", "resumen", "principal", "home", "detalle", "portada", "indicadores"}

TECHNICAL_SUFFIXES = {"ok", "id", "cod", "key"}

TEMPORAL_WORDS = {"date", "fecha", "ano", "anio", "mes", "year", "month", "dia", "day"}

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
    shortest = min(len(left), len(right))
    # Palabras cortas solo coinciden si son idénticas: «mayo» != «mayor».
    if shortest < 6:
        return 0.0
    # Prefijo solo cuando una palabra es prefijo literal de la otra
    # (ocupacion/ocupacional). programada != programacion,
    # hospitalario != hospitalizacion, consulta != consultorio.
    if abs(len(left) - len(right)) <= 3 and (left.startswith(right) or right.startswith(left)):
        return 0.90
    ratio = SequenceMatcher(None, left, right).ratio()
    return ratio if ratio >= 0.88 else min(ratio, 0.80)


def _exact_phrase(question, candidate):
    return bool(
        question and candidate
        and re.search(r"(?<![a-z0-9])" + re.escape(candidate) + r"(?![a-z0-9])", question)
    )


def _phrase_score(question, candidate, weights=None):
    """Qué tanto cubre la pregunta al candidato.

    `weights` (token -> peso IDF) hace que palabras genéricas del catálogo
    (cirugías, pacientes...) valgan poco frente a las distintivas.
    """
    q = normalize_text(question)
    c = normalize_text(candidate)
    if not q or not c:
        return 0.0
    weights = weights or {}

    if _exact_phrase(q, c):
        specificity = min(len(c.split()), 6)
        base = min(1.20, 1.00 + 0.03 * specificity)
        if weights:
            base += 0.10 * min(3.0, sum(weights.get(t, 1.0) for t in canonical_tokens(c)))
        return base

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

    # Todas las palabras del candidato aparecen tal cual (aunque separadas):
    # «total de cirugías» cubre por completo «Total Cirugías».
    if len(c_tokens) >= 2 and all(value == 1.0 for value in matched):
        base = min(1.20, 1.00 + 0.02 * min(len(c_tokens), 6))
        if weights:
            base += 0.10 * min(3.0, sum(weights.get(t, 1.0) for t in c_tokens))
        return base

    token_weights = [weights.get(token, 1.0) for token in c_tokens]
    coverage = sum(w for w, value in zip(token_weights, matched) if value >= 0.82) / sum(token_weights)
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

    # ---- pesos IDF: palabras repetidas en todo el catálogo valen poco ----
    def _token_weight_index(self):
        if getattr(self, "_token_weights", None) is not None:
            return self._token_weights
        labels = set()
        document_frequency = {}
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            for name in (metric.get("label"), metric.get("measure")):
                key = normalize_text(name)
                if not key or key in labels:
                    continue
                labels.add(key)
                for token in set(canonical_tokens(key)):
                    document_frequency[token] = document_frequency.get(token, 0) + 1
        total = len(labels)
        weights = {}
        if total > 1:
            for token, count in document_frequency.items():
                weights[token] = 0.25 + 0.75 * (1.0 - count / total)
        self._token_weights = weights
        self._known_labels = labels
        return weights

    def _token_weight(self, token):
        return self._token_weight_index().get(token, 1.0)

    def _unexplained_penalty(self, business_question, explained_tokens):
        """Castiga palabras distintivas de la pregunta que el candidato no explica."""
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}
        ignored.update(canonical_token(word) for word in MONTHS)
        penalty = 0.0
        for token in set(canonical_tokens(business_question)):
            if token in ignored or token.isdigit() or len(token) < 3:
                continue
            if any(_token_similarity(token, other) >= 0.82 for other in explained_tokens):
                continue
            penalty += 0.12 * self._token_weight(token)
        return min(0.45, penalty)

    def _page_bonus(self, question_tokens, metric, name_tokens):
        """Mencionar la página/dashboard de la métrica desempata de verdad (+0.20).

        Se ignoran páginas genéricas y las palabras que ya forman parte del
        nombre de la métrica (una página «Cirugías Realizadas» no debe premiar
        a la métrica «Cirugías Realizadas» solo por llamarse igual).
        """
        stop = {canonical_token(word) for word in STOPWORDS}
        for page in self._metric_pages(metric):
            tokens = [
                token for token in canonical_tokens(page)
                if token not in name_tokens and token not in GENERIC_PAGE_WORDS
                and token not in stop
            ]
            if not tokens:
                continue
            if len(tokens) == 1 and self._token_weight(tokens[0]) < 0.5:
                continue
            if all(
                any(_token_similarity(token, other) >= 0.82 for other in question_tokens)
                for token in tokens
            ):
                return 0.20
        return 0.0

    def _logical_key(self, metric):
        return (
            normalize_text(metric.get("semantic_model")),
            normalize_text(metric.get("table")),
            normalize_text(metric.get("dax_expression")),
        )

    def _resolve_metric(self, question, source_context, selected_metric_id=None):
        # Una selección realizada durante una aclaración manda por ID,
        # no por el texto de la respuesta del usuario.
        if selected_metric_id is not None:
            for metric in self._dedupe_metrics(self.metrics):
                if metric.get("validation_status") != "approved":
                    continue
                if str(metric.get("metric_id")) == str(selected_metric_id):
                    return {
                        "status": "resolved", "metric": metric,
                        "matched_name": metric.get("label"), "score": 10.0,
                        "candidates": [{"metric": metric, "score": 10.0,
                                        "business_score": 10.0,
                                        "matched_name": metric.get("label")}],
                    }
            return {"status": "not_found", "candidates": []}

        weights = self._token_weight_index()
        business_question = self._metric_business_question(question, source_context)
        normalized_business = normalize_text(business_question)
        question_tokens = canonical_tokens(business_question)
        resolved_routing = source_context.get("status") == "resolved"
        strong = resolved_routing and source_context.get("routing_strength") == "strong"
        weak = resolved_routing and source_context.get("routing_strength") == "weak"
        model_hint = normalize_text(source_context.get("semantic_model")) if (strong or weak) else ""
        report_hint = normalize_text(source_context.get("report")) if strong else ""
        candidates = []

        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            metric_model = normalize_text(metric.get("semantic_model"))
            metric_reports = [normalize_text(value) for value in self._metric_reports(metric)]

            primary_label = metric.get("label") or ""
            primary_norm = normalize_text(primary_label)
            primary_score = _phrase_score(business_question, primary_label, weights)
            label_is_exact = _exact_phrase(normalized_business, primary_norm)

            titles = _unique_strings(
                appearance.get("visual_title")
                for appearance in metric.get("appearances", []) or []
            )
            exact_title = None
            for title in titles:
                title_norm = normalize_text(title)
                if title_norm == primary_norm or not _exact_phrase(normalized_business, title_norm):
                    continue
                # Un título compartido con la etiqueta de OTRA métrica
                # (EGRESOS de AÑO ACTUAL) solo es alias, no nombre propio.
                if title_norm in self._known_labels:
                    continue
                exact_title = title
                break

            aliases = [
                item for item in self._metric_names(metric)
                if normalize_text(item) != primary_norm
            ]
            best_alias = max(
                ((_phrase_score(business_question, name, weights), name) for name in aliases),
                key=lambda pair: pair[0], default=(0.0, None),
            )
            label_weight = sum(weights.get(t, 1.0) for t in canonical_tokens(primary_label))
            if label_is_exact:
                best_name = primary_label
                best_name_score = primary_score
                # Una etiqueta de una palabra genérica («Cirugías») pesa poco.
                name_priority = 0.32 * min(1.0, label_weight)
            elif exact_title:
                best_name = exact_title
                best_name_score = _phrase_score(business_question, exact_title, weights)
                name_priority = 0.32 * min(1.0, sum(weights.get(t, 1.0) for t in canonical_tokens(exact_title)))
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

            in_hint_model = bool(model_hint) and metric_model == model_hint
            in_hint_report = bool(report_hint) and (
                not metric_reports or report_hint in metric_reports
            )
            # Solo un informe/alias nombrado (routing fuerte) pesa. El routing
            # débil sale del nombre de una página, que puede coincidir con el
            # nombre de la métrica y no debe desempatar por sí solo.
            if in_hint_model and strong:
                score += 0.20
                if report_hint and in_hint_report:
                    score += 0.10
            elif in_hint_model:
                score += 0.01  # solo ordena opciones; no rompe un empate (< margen)

            explained = set()
            for value in [*self._metric_names(metric), *self._metric_reports(metric),
                          *self._metric_pages(metric), metric.get("semantic_model")]:
                explained.update(canonical_tokens(value))
            name_tokens = set(canonical_tokens(best_name)) | set(canonical_tokens(primary_label))
            score -= self._unexplained_penalty(business_question, explained)
            score += self._page_bonus(question_tokens, metric, name_tokens)

            # Medidas auxiliares (sin visual donde aparezcan) pierden frente a
            # las que el usuario ve en un tablero, salvo que las nombre exacto.
            if not (metric.get("appearances") or []):
                score -= 0.08 if (label_is_exact and label_weight >= 1.0) else 0.25

            candidates.append({
                "metric": metric,
                "score": round(score, 4),
                "business_score": round(best_name_score, 4),
                "matched_name": best_name,
                "exact_primary_label": label_is_exact,
                "hinted": bool(in_hint_model and (not report_hint or in_hint_report)),
            })

        if not candidates:
            return {"status": "not_found", "candidates": []}

        # Informe nombrado explícitamente y la métrica existe allí: solo
        # compiten las métricas de ese informe. Si no existe allí, el
        # nombre del tablero solo orienta (boost) y se avisa.
        hint_ignored = False
        if strong:
            hinted = [item for item in candidates if item["hinted"]
                      and item["business_score"] >= self.min_metric_score]
            if hinted:
                candidates = hinted
            else:
                hint_ignored = True

        def order(item):
            metric = item["metric"]
            return (
                -item["score"], normalize_text(metric.get("semantic_model")),
                normalize_text(metric.get("report")), normalize_text(metric.get("label")),
                str(metric.get("metric_id")),
            )

        candidates.sort(key=order)
        groups = []
        seen = set()
        for item in candidates:
            key = self._logical_key(item["metric"])
            if key in seen:
                continue
            seen.add(key)
            groups.append(item)

        best = groups[0]
        if best["business_score"] < self.min_metric_score:
            return {"status": "not_found", "candidates": groups[:8]}
        tied = [
            item for item in groups
            if best["score"] - item["score"] < self.ambiguity_margin
            and item["business_score"] >= self.min_metric_score
        ]
        if len(tied) > 1:
            rest = [item for item in groups if item not in tied]
            return {"status": "ambiguous", "candidates": (tied + rest)[:max(8, len(tied))]}

        return {
            "status": "resolved", "metric": best["metric"],
            "matched_name": best["matched_name"], "score": best["score"],
            "candidates": groups[:8],
            "source_hint_ignored": hint_ignored,
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
        # Sufijos técnicos (TURNO_OK, SERVICIO_ID): «turno» debe encontrar TURNO_OK.
        for alias in list(normalized_aliases):
            parts = alias.split()
            while len(parts) >= 2 and parts[-1] in TECHNICAL_SUFFIXES:
                parts = parts[:-1]
                aliases.append(" ".join(parts))
        normalized_aliases = {normalize_text(alias) for alias in aliases}
        for synonyms in DIMENSION_SYNONYMS.values():
            # Por palabra completa: OPORTUNIDAD no contiene «unidad».
            if any(
                re.search(r"(?<![a-z0-9])" + re.escape(synonym) + r"(?![a-z0-9])", alias)
                for alias in normalized_aliases for synonym in synonyms
            ):
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

    def _value_match_score(self, question, value, value_hint=None, allow_short=False):
        q = normalize_text(value_hint or question)
        v = normalize_text(value)
        if not q or not v:
            return 0.0
        # Códigos cortos («M», «F», «A1»): solo si el texto pedido ES el valor
        # (filtro explícito «sexo M»); jamás como subcadena de otra palabra.
        if len(v) < 3:
            return 1.10 if (allow_short and q == v) else 0.0
        if _exact_phrase(q, v):
            return 1.10

        ignored = {canonical_token(word) for word in GENERIC_QUERY_WORDS | STOPWORDS}
        q_tokens = [
            token for token in canonical_tokens(q)
            if len(token) >= 2 and token not in ignored
        ]
        v_tokens = set(canonical_tokens(v))
        if not q_tokens or not v_tokens:
            return 0.0
        matched = {token for token in q_tokens if token in v_tokens}
        if not any(len(token) >= 3 for token in matched):
            return 0.0
        q_coverage = sum(1 for token in q_tokens if token in v_tokens) / len(q_tokens)
        v_coverage = len(matched) / len(v_tokens)
        if q_coverage == 1.0 or v_coverage == 1.0:
            return min(1.05, 0.94 + min(len(matched), 4) * 0.02)
        if q_coverage >= 0.60:
            return 0.72 + 0.22 * q_coverage
        return 0.0

    def _resolve_value(self, question, field, semantic_model, value_hint=None):
        values = self._get_values(semantic_model, field["table"], field["column"])
        if values is None:
            return None
        scored = []
        for value in values:
            score = self._value_match_score(
                question, value, value_hint=value_hint, allow_short=bool(value_hint)
            )
            if score > 0:
                scored.append((score, value))
        scored.sort(key=lambda item: (item[0], len(normalize_text(item[1]))), reverse=True)
        if not scored or scored[0][0] < 0.84:
            return None
        return {
            "value": scored[0][1], "score": round(scored[0][0], 4),
            "tokens": set(canonical_tokens(scored[0][1])),
        }

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
        """Filtros «<dimensión> <valor>» pedidos de forma explícita.

        Cada mención («sede norte») produce UN filtro: el campo mejor ubicado
        (el de la tabla de la métrica / visuales de la métrica) y, como
        respaldo, los demás campos con el mismo alias en `alternatives`.
        """
        normalized = (
            self._remove_metric_and_report_phrases(question, metric, source_context or {})
            if metric else normalize_text(question)
        )
        already_fields = already_fields if already_fields is not None else set()
        metric_table = normalize_text((metric or {}).get("table"))

        def priority(field):
            bonus = 60 if metric_table and normalize_text(field.get("table")) == metric_table else 0
            return -(field.get("relevance_score", 0) + bonus)

        ordered = sorted(candidates, key=priority)
        mentions = {}
        order = []
        for field in ordered:
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
                    r"(?<![a-z0-9])" + re.escape(alias_norm) + r"(?![a-z0-9])"
                    + r"(?:\s+(?:de|del|igual a|=|:))?"
                    + r"\s+([a-z0-9][a-z0-9\s\.\-]{1,80})"
                )
                match = re.search(pattern, normalized)
                if not match:
                    continue
                hint = re.split(
                    r"\b(?:en|durante|para el|para la|del tablero|del informe|y|con|pero)\b",
                    match.group(1), maxsplit=1,
                )[0].strip()
                # «servicio de urgencias» es filtro; «servicio por...»,
                # «servicio hay...» o «servicio en ...» no lo son.
                invalid_start = {"hay", "hubo", "tiene", "tienen", "es", "son", "por", "para", "con"}
                tokens = canonical_tokens(hint)
                if not hint or not tokens or tokens[0] in invalid_start:
                    continue
                if len(hint.split()) == 1 and hint in GENERIC_QUERY_WORDS:
                    continue
                # Misma mención (mismo texto pedido) = mismo filtro, aunque
                # varias tablas tengan una columna llamada igual (SEDE).
                mention = (alias_norm, hint)
                if mention not in mentions:
                    mentions[mention] = {"field": field, "value_hint": hint, "alternatives": [], "alias": alias_norm}
                    order.append(mention)
                else:
                    mentions[mention]["alternatives"].append(field)
                break
        filters = [mentions[key] for key in order]
        for spec in filters:
            already_fields.add(
                (normalize_text(spec["field"].get("table")), normalize_text(spec["field"].get("column")))
            )
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

    def _implicit_value_text(
        self, question, metric, matched_name, source_context, group_by,
        extra_removals=None,
    ):
        removals = self._metric_removal_tokens(metric, matched_name, source_context)
        for group in group_by:
            for alias in group.get("aliases", []):
                removals.update(canonical_tokens(alias))
        removals.update(canonical_token(word) for word in GENERIC_QUERY_WORDS)
        removals.update(canonical_token(word) for word in STOPWORDS)
        removals.update(canonical_token(word) for word in FILTER_NEUTRAL_WORDS)
        removals.update({"a", "al", "del", "de", "en", "hay", "hubo", "dentro", "segun"})
        removals.update(canonical_token(word) for word in MONTHS)
        removals.update(extra_removals or ())
        # Página/dashboard mencionada completa («programación quirúrgica»).
        question_tokens = set(canonical_tokens(question))
        for page in self._metric_pages(metric):
            page_tokens = canonical_tokens(page)
            if page_tokens and all(token in question_tokens for token in page_tokens):
                removals.update(page_tokens)

        result = []
        for word in normalize_text(question).split():
            token = canonical_token(word)
            if token in removals or re.fullmatch(r"20\d{2}", token) or token.isdigit():
                continue
            result.append(word)
        return " ".join(result).strip()

    def _categorical_filter(self, field, resolved, source, semantic_model):
        data_type = self._column_type(semantic_model, field["table"], field["column"])
        return {
            "type": "categorical",
            "concept": (field.get("aliases") or [field["column"]])[0],
            "table": field["table"],
            "column": field["column"],
            "operator": "=",
            "value": resolved["value"],
            "data_type": data_type,
            "match_score": resolved["score"],
            "source": source,
        }

    def _implicit_eligible(self, field, semantic_model):
        """Columnas categóricas de cualquier visual (slicer, tabla, matriz, gráfico)."""
        if field.get("kind") not in ("column", "hierarchy_level"):
            return False
        if self._is_temporal_field(field):
            return False
        # Un código numérico o una fecha no es un valor que se nombre en texto libre.
        return self._column_type(semantic_model, field.get("table"), field.get("column")) not in ("number", "date")

    def _resolve_implicit_filter(
        self, question, metric, matched_name, source_context,
        candidates, group_by, used_fields, extra_removals=None,
    ):
        leftover = self._implicit_value_text(
            question, metric, matched_name, source_context, group_by,
            extra_removals=extra_removals,
        )
        if not leftover:
            return None

        semantic_model = metric.get("semantic_model")
        best = None
        checked = 0
        for field in candidates:
            if checked >= self.max_implicit_dimensions:
                break
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in used_fields:
                continue
            if not self._implicit_eligible(field, semantic_model):
                continue

            checked += 1
            resolved = self._resolve_value(
                question=question, field=field,
                semantic_model=semantic_model, value_hint=leftover,
            )
            if not resolved:
                continue
            candidate = {"field": field, **resolved}
            if best is None or candidate["score"] > best["score"]:
                best = candidate
            if best and best["score"] >= 1.0:
                break
        return best

    # ---------------- column types ----------------
    def _technical_column_types(self, semantic_model):
        key = normalize_text(semantic_model)
        cache = self.__dict__.setdefault("_column_type_cache", {})
        if key in cache:
            return cache[key]
        types = {}
        try:
            path = self.source_router.catalog_path_for_model(semantic_model, required=False)
            catalog = self._load_json(path, {}) if path else {}
        except Exception:
            catalog = {}
        for table in catalog.get("tables", []) or []:
            for column in table.get("columns", []) or []:
                types[(normalize_text(table.get("name")), normalize_text(column.get("name")))] = (
                    self._classify_data_type(column.get("data_type"))
                )
        cache[key] = types
        return types

    @staticmethod
    def _classify_data_type(data_type):
        text = normalize_text(data_type)
        if not text:
            return None
        if "date" in text or "time" in text:
            return "date"
        if any(item in text for item in ("int", "decimal", "double", "number", "currency", "float", "whole")):
            return "number"
        return "text"

    def _column_type(self, semantic_model, table, column):
        """'date' | 'number' | 'text' | None (desconocido) según el catálogo técnico."""
        types = self._technical_column_types(semantic_model)
        return types.get((normalize_text(table), normalize_text(column)))

    # ---------------- time ----------------
    def _is_temporal_field(self, field):
        words = set()
        for value in [*field.get("aliases", []), field.get("column"), field.get("level")]:
            words.update(normalize_text(value).split())
        table = normalize_text(field.get("table"))
        column = normalize_text(field.get("column"))
        level = normalize_text(field.get("level"))
        return (
            table in {"calendario", "calendar", "fecha", "dates"}
            or level in {"ano", "mes", "dia", "year", "month", "day"}
            or bool(words & TEMPORAL_WORDS)
            or column in {"date", "fecha", "fecha servicio", "fecha atencion"}
        )

    def _detect_year_month(self, question):
        normalized = normalize_text(question)
        year_match = re.search(r"\b(20\d{2})\b", normalized)
        year = int(year_match.group(1)) if year_match else None
        month = None
        month_name = None
        for name, number in MONTHS.items():
            if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", normalized):
                month = number
                month_name = name
                break
        return year, month, month_name

    def _temporal_role(self, field, semantic_model):
        """'date' | 'year' | 'month' | None para un campo temporal."""
        column_type = self._column_type(semantic_model, field.get("table"), field.get("column"))
        words = set(normalize_text(field.get("column")).split())
        if column_type == "date":
            return "date"
        if words & {"ano", "anio", "year"}:
            return "year"
        if words & {"mes", "month"}:
            return "month"
        if column_type is None and (words & {"date", "fecha"} or field.get("kind") == "hierarchy_level"):
            return "date"
        return None

    def _best_date_field(self, candidates, semantic_model=None):
        temporal = [
            field for field in candidates
            if self._is_temporal_field(field)
            and (semantic_model is None or self._temporal_role(field, semantic_model) == "date")
        ]
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

    def _best_temporal_field(self, candidates, semantic_model, role):
        found = [
            field for field in candidates
            if self._is_temporal_field(field) and self._temporal_role(field, semantic_model) == role
        ]
        found.sort(key=lambda field: field.get("relevance_score", 0), reverse=True)
        return found[0] if found else None

    def _temporal_filters(self, question, candidates, semantic_model=None):
        """Filtros de año/mes según el TIPO real de la columna.

        Devuelve (filtros, términos_sin_aplicar, notas). Columna de fecha ->
        date_range; columnas enteras AÑO/MES -> filtro por valor numérico.
        Un mes sin año filtra el mes en todos los años y lo dice en las notas.
        """
        year, month, month_name = self._detect_year_month(question)
        if year is None and month is None:
            return [], [], []

        unapplied = []
        notes = []
        date_field = self._best_date_field(candidates, semantic_model) if semantic_model else self._best_date_field(candidates)
        if date_field:
            if month is not None and year is None:
                notes.append(f"Mes sin año ({month_name}): se consideran todos los años.")
            return [{
                "type": "date_range",
                "table": date_field["table"],
                "column": date_field["column"],
                "year": year,
                "month": month,
                "month_name": month_name,
                "source": "query_plan_temporal",
            }], unapplied, notes

        filters = []
        year_field = self._best_temporal_field(candidates, semantic_model, "year")
        month_field = self._best_temporal_field(candidates, semantic_model, "month")
        if year is not None:
            if year_field:
                filters.append({
                    "type": "categorical", "concept": "año",
                    "table": year_field["table"], "column": year_field["column"],
                    "operator": "=", "value": year, "data_type": "number",
                    "temporal": "year", "source": "query_plan_temporal",
                })
            else:
                unapplied.append(f"año {year}")
        if month is not None:
            month_filter = None
            if month_field:
                month_type = self._column_type(semantic_model, month_field["table"], month_field["column"])
                value = month
                data_type = "number"
                if month_type == "text":
                    data_type = "text"
                    value = None
                    domain = self._get_values(semantic_model, month_field["table"], month_field["column"]) or []
                    for item in domain:
                        if normalize_text(item) == month_name:
                            value = item
                            break
                if value is not None:
                    month_filter = {
                        "type": "categorical", "concept": "mes",
                        "table": month_field["table"], "column": month_field["column"],
                        "operator": "=", "value": value, "data_type": data_type,
                        "temporal": "month", "source": "query_plan_temporal",
                    }
            if month_filter:
                filters.append(month_filter)
                if year is None:
                    notes.append(f"Mes sin año ({month_name}): se consideran todos los años.")
            else:
                unapplied.append(f"mes {month_name}")
        return filters, unapplied, notes

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
        used_fields.update(
            (normalize_text(field.get("table")), normalize_text(field.get("column")))
            for field in group_by
        )
        explicit_specs.extend(
            self._detect_explicit_dimension_filters(
                question, candidates, already_fields=used_fields,
                metric=metric, source_context=source_context,
            )
        )

        filters = []
        unapplied_terms = []
        notes = []
        consumed_tokens = set()
        if metric_result.get("source_hint_ignored"):
            notes.append(
                "La métrica no existe en el informe mencionado; se usó "
                f"{report or semantic_model}."
            )
        for spec in explicit_specs:
            field = spec["field"]
            resolved = None
            for option in [field, *spec.get("alternatives", [])]:
                resolved = self._resolve_value(
                    question=question, field=option, semantic_model=semantic_model,
                    value_hint=spec.get("value_hint"),
                )
                if resolved:
                    field = option
                    break
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
            filters.append(self._categorical_filter(
                field, resolved, "query_plan_explicit_dimension", semantic_model,
            ))
            used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))
            consumed_tokens.update(resolved.get("tokens", ()))
            consumed_tokens.update(canonical_tokens(spec.get("value_hint")))
            for alias in field.get("aliases", []) or []:
                consumed_tokens.update(canonical_tokens(alias))

        # Valores implícitos («cirugía plástica»): se buscan SIEMPRE, también
        # cuando ya hay filtros explícitos o agrupación; así ninguna palabra
        # específica se pierde porque otro filtro coincidió primero.
        for _ in range(3):
            implicit = self._resolve_implicit_filter(
                question=question, metric=metric,
                matched_name=metric_result.get("matched_name"),
                source_context=source_context, candidates=candidates,
                group_by=group_by, used_fields=used_fields,
                extra_removals=consumed_tokens,
            )
            if not implicit:
                break
            field = implicit["field"]
            filters.append(self._categorical_filter(
                field, implicit, "query_plan_implicit_value", semantic_model,
            ))
            used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))
            consumed_tokens.update(implicit.get("tokens", ()))

        temporal_filters, temporal_unapplied, temporal_notes = self._temporal_filters(
            question, candidates, semantic_model,
        )
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
        unapplied_terms.extend(temporal_unapplied)
        notes.extend(temporal_notes)

        # Palabras específicas que ningún filtro explicó. Sin ningún filtro
        # categórico el resultado sería un total engañoso: se detiene. Con
        # otros filtros ya aplicados se continúa, pero se declara lo omitido.
        leftover = self._implicit_value_text(
            question, metric, metric_result.get("matched_name"),
            source_context, group_by, extra_removals=consumed_tokens,
        )
        significant = [token for token in leftover.split() if len(token) >= 3]
        if significant:
            if not any(
                item.get("type") == "categorical" and item.get("source") != "query_plan_temporal"
                for item in filters
            ) and not group_by:
                return {
                    "status": "unsupported_filter", "stage": "implicit_dimension",
                    "reason": "possible_dimension_value_not_resolved",
                    "unresolved_text": leftover,
                    "question": question, "semantic_model": semantic_model,
                    "source_context": source_context, "metric_resolution": metric_result,
                }
            unapplied_terms.append(" ".join(significant))

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
            "unapplied_terms": unapplied_terms,
            "notes": notes,
            "group_by": normalized_group_by,
            "dimension_candidates_checked": min(len(candidates), 20),
        }

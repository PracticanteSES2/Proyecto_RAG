import json
import re
import unicodedata
from pathlib import Path

MONTHS = {
    "enero","febrero","marzo","abril","mayo","junio",
    "julio","agosto","septiembre","setiembre","octubre",
    "noviembre","diciembre",
}

STOPWORDS = {
    "a","al","cual","cuales","cuanto","cuantos","cuanta","cuantas",
    "de","del","el","en","entre","es","fue","hay","hubo","la","las",
    "los","para","por","que","se","un","una","y","total","cantidad",
    "numero","valor","dato","datos","mes","ano","año",
}


def normalize_text(value):
    value = str(value or "").lower().strip()
    value = "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


class MasterMetricResolver:

    def __init__(
        self,
        catalog_path,
        min_score=0.48,
        ambiguity_margin=0.10,
        same_dashboard_ambiguity_margin=0.03,
        dashboard_match_threshold=0.72,
    ):
        self.catalog_path = Path(catalog_path)
        self.min_score = float(min_score)
        self.ambiguity_margin = float(ambiguity_margin)
        self.same_dashboard_ambiguity_margin = float(
            same_dashboard_ambiguity_margin
        )
        self.dashboard_match_threshold = float(dashboard_match_threshold)

        payload = json.loads(
            self.catalog_path.read_text(encoding="utf-8")
        )
        self.metrics = payload.get("metrics", [])
        self.available_dashboards = self._load_dashboards()
        self.available_reports = self._load_reports()
        self.available_semantic_models = sorted({
            metric.get("semantic_model")
            for metric in self.metrics
            if metric.get("semantic_model")
        })

    def _semantic_tokens(self, value):
        tokens = []
        for token in normalize_text(value).split():
            if token.isdigit():
                continue
            if token in MONTHS or token in STOPWORDS:
                continue
            if len(token) < 2:
                continue
            tokens.append(token)
        return tokens

    def _is_technical_alias(self, alias):
        text = str(alias or "")
        if any(x in text for x in ("(", ")", "[", "]")):
            return True
        normalized = normalize_text(text)
        return (
            not normalized
            or normalized in {"true","false","none","null"}
            or normalized.isdigit()
        )

    def _metric_dashboards(self, metric):
        values = []

        if metric.get("dashboard"):
            values.append(str(metric["dashboard"]))

        for appearance in metric.get("appearances", []) or []:
            page = appearance.get("page_display_name")
            if page:
                values.append(str(page))

        unique = []
        seen = set()
        for value in values:
            key = normalize_text(value)
            if key and key not in seen:
                unique.append(value)
                seen.add(key)

        return unique

    def _metric_reports(self, metric):
        values = []

        if metric.get("report"):
            values.append(
                str(
                    metric[
                        "report"
                    ]
                )
            )

        for report in (
            metric.get(
                "reports",
                [],
            )
            or []
        ):
            if report:
                values.append(
                    str(report)
                )

        for appearance in (
            metric.get(
                "appearances",
                [],
            )
            or []
        ):
            report = appearance.get(
                "report"
            )

            if report:
                values.append(
                    str(report)
                )

        unique = []
        seen = set()

        for value in values:
            key = normalize_text(
                value
            )

            if (
                key
                and key not in seen
            ):
                unique.append(
                    value
                )
                seen.add(key)

        return unique

    def _load_reports(self):
        values = []
        seen = set()

        for metric in self.metrics:
            for report in self._metric_reports(
                metric
            ):
                key = normalize_text(
                    report
                )

                if (
                    key
                    and key not in seen
                ):
                    values.append(
                        report
                    )
                    seen.add(key)

        return values

    def _detect_report_from_question(
        self,
        question,
    ):
        scored = []

        for report in self.available_reports:
            score = self._dashboard_match_score(
                question,
                report,
            )

            if score >= 0.72:
                scored.append(
                    (
                        report,
                        score,
                    )
                )

        scored.sort(
            key=lambda item:
                item[1],
            reverse=True,
        )

        if not scored:
            return None

        if (
            len(scored) > 1
            and scored[0][1]
            - scored[1][1]
            < 0.08
        ):
            return None

        return scored[0][0]

    def _semantic_model_score(
        self,
        question,
        metric,
    ):
        model = metric.get(
            "semantic_model"
        )

        if not model:
            return 0.0

        return self._dashboard_match_score(
            question,
            model,
        )

    def _load_dashboards(self):
        values = []
        seen = set()

        for metric in self.metrics:
            for dashboard in self._metric_dashboards(metric):
                key = normalize_text(dashboard)
                if key and key not in seen:
                    values.append(dashboard)
                    seen.add(key)

        return values

    def _token_overlap_score(self, text_a, text_b):
        a = set(self._semantic_tokens(text_a))
        b = set(self._semantic_tokens(text_b))

        if not a or not b:
            return 0.0

        common = a & b
        coverage = len(common) / len(b)
        precision = len(common) / len(a)
        return 0.80 * coverage + 0.20 * precision

    def _dashboard_match_score(self, question, dashboard):
        q = normalize_text(question)
        d = normalize_text(dashboard)

        if not d:
            return 0.0

        if d in q:
            return 1.0

        return self._token_overlap_score(question, dashboard)

    def _detect_dashboard_from_question(self, question):
        scored = []

        for dashboard in self.available_dashboards:
            score = self._dashboard_match_score(question, dashboard)

            if score >= self.dashboard_match_threshold:
                scored.append((dashboard, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        if not scored:
            return None

        if len(scored) > 1 and scored[0][1] - scored[1][1] < 0.08:
            return None

        return scored[0][0]

    def _score_alias(self, question, alias):
        if not alias:
            return 0.0

        q_norm = normalize_text(question)
        a_norm = normalize_text(alias)
        a_tokens = self._semantic_tokens(alias)

        if not a_norm or not a_tokens:
            return 0.0

        if a_norm in q_norm and len(a_tokens) >= 2:
            return min(1.0, 0.90 + 0.02 * len(a_tokens))

        if a_norm in q_norm and len(a_tokens) == 1:
            return 0.78

        q_tokens = set(self._semantic_tokens(question))
        a_tokens = set(a_tokens)

        if not q_tokens or not a_tokens:
            return 0.0

        common = q_tokens & a_tokens
        coverage = len(common) / len(a_tokens)
        precision = len(common) / len(q_tokens)

        if coverage < 0.50:
            return 0.0

        return 0.78 * coverage + 0.22 * precision

    def _business_score(self, question, metric):
        """
        Los aliases de un visual NO se usan para puntuar medidas
        explícitas. Un visual puede contener varias medidas y todas
        heredar el mismo título; eso produciría falsos positivos
        como AÑO_ACTUAL ~= "pacientes observados".
        """
        scores = []

        source_type = metric.get(
            "source_type"
        )

        label = metric.get(
            "label"
        )

        if label:
            scores.append(
                self._score_alias(
                    question,
                    label,
                )
            )

        measure = metric.get(
            "measure"
        )

        # Medidas explícitas:
        # usar solo su propio nombre/label.
        if source_type == "explicit_measure":
            if measure:
                scores.append(
                    self._score_alias(
                        question,
                        measure,
                    )
                )

            return max(
                scores,
                default=0.0,
            )

        # Agregaciones visuales:
        # sí pueden usar aliases de negocio derivados del visual.
        for alias in (
            metric.get(
                "aliases",
                [],
            )
            or []
        ):
            if self._is_technical_alias(
                alias
            ):
                continue

            scores.append(
                0.95
                * self._score_alias(
                    question,
                    alias,
                )
            )

        return max(
            scores,
            default=0.0,
        )

    def _aggregation_intent_bonus(
        self,
        question,
        metric,
    ):
        """
        Bonus pequeño: no decide por sí solo una métrica,
        solo desempata cuando el lenguaje del usuario coincide
        con el tipo de agregación real del visual.
        """
        q = normalize_text(
            question
        )

        aggregation = (
            metric.get(
                "aggregation"
            )
            or ""
        )

        aggregation = normalize_text(
            aggregation
        )

        count_terms = [
            "cuantos",
            "cuantas",
            "cantidad",
            "recuento",
            "numero",
        ]

        average_terms = [
            "promedio",
            "media",
        ]

        if (
            any(
                term in q
                for term in count_terms
            )
            and aggregation in {
                "count",
                "distinctcount",
            }
        ):
            return 0.08

        if (
            any(
                term in q
                for term in average_terms
            )
            and aggregation
            == "average"
        ):
            return 0.08

        return 0.0

    def resolve(
        self,
        question,
        dashboard=None,
        approved_only=True,
        semantic_model=None,
        report=None,
    ):
        explicit_dashboard = (
            dashboard is not None
        )

        explicit_report = (
            report is not None
        )

        requested_dashboard = (
            dashboard
            or self._detect_dashboard_from_question(
                question
            )
        )

        requested_report = (
            report
            or self._detect_report_from_question(
                question
            )
        )

        requested_model_norm = (
            normalize_text(
                semantic_model
            )
            if semantic_model
            else None
        )

        candidates = []

        for metric in self.metrics:
            if (
                approved_only
                and metric.get(
                    "validation_status"
                )
                != "approved"
            ):
                continue

            metric_model = metric.get(
                "semantic_model"
            )

            if (
                requested_model_norm
                and normalize_text(
                    metric_model
                )
                != requested_model_norm
            ):
                continue

            business_score = (
                self._business_score(
                    question,
                    metric,
                )
            )

            if business_score < 0.30:
                continue

            metric_dashboards = (
                self._metric_dashboards(
                    metric
                )
            )

            metric_reports = (
                self._metric_reports(
                    metric
                )
            )

            dashboard_score = 0.0
            report_score = 0.0

            if requested_dashboard:
                requested_norm = (
                    normalize_text(
                        requested_dashboard
                    )
                )

                matching = [
                    value
                    for value
                    in metric_dashboards
                    if normalize_text(
                        value
                    )
                    == requested_norm
                ]

                # Solo un dashboard pasado explícitamente por el flujo
                # puede restringir candidatos. Un nombre de página
                # detectado dentro de la pregunta es CONTEXTO DÉBIL:
                # "urgencias" puede ser un valor de SERVICIO y no la
                # página donde vive la métrica.
                if (
                    explicit_dashboard
                    and metric_dashboards
                    and not matching
                ):
                    continue

                if matching:
                    dashboard_score = 1.0
                else:
                    dashboard_score = max(
                        (
                            self._dashboard_match_score(
                                question,
                                value,
                            )
                            for value
                            in metric_dashboards
                        ),
                        default=0.0,
                    )

            else:
                dashboard_score = max(
                    (
                        self._dashboard_match_score(
                            question,
                            value,
                        )
                        for value
                        in metric_dashboards
                    ),
                    default=0.0,
                )

            if requested_report:
                requested_report_norm = (
                    normalize_text(
                        requested_report
                    )
                )

                report_matching = [
                    value
                    for value
                    in metric_reports
                    if normalize_text(
                        value
                    )
                    == requested_report_norm
                ]

                # Igual que con las páginas: solo un reporte recibido
                # explícitamente puede excluir otros modelos/reportes.
                # Una coincidencia inferida desde texto se usa como bonus.
                if (
                    explicit_report
                    and metric_reports
                    and not report_matching
                ):
                    continue

                if report_matching:
                    report_score = 1.0

            else:
                report_score = max(
                    (
                        self._dashboard_match_score(
                            question,
                            value,
                        )
                        for value
                        in metric_reports
                    ),
                    default=0.0,
                )

            model_score = (
                1.0
                if requested_model_norm
                else self._semantic_model_score(
                    question,
                    metric,
                )
            )

            intent_bonus = (
                self._aggregation_intent_bonus(
                    question,
                    metric,
                )
            )

            final_score = (
                business_score
                + 0.18 * dashboard_score
                + 0.16 * report_score
                + 0.08 * model_score
                + intent_bonus
            )

            candidate = metric.copy()
            candidate[
                "business_score"
            ] = round(
                business_score,
                4,
            )
            candidate[
                "dashboard_score"
            ] = round(
                dashboard_score,
                4,
            )
            candidate[
                "report_score"
            ] = round(
                report_score,
                4,
            )
            candidate[
                "model_score"
            ] = round(
                model_score,
                4,
            )
            candidate[
                "intent_bonus"
            ] = round(
                intent_bonus,
                4,
            )
            candidate[
                "score"
            ] = round(
                final_score,
                4,
            )
            candidate[
                "candidate_dashboards"
            ] = metric_dashboards
            candidate[
                "candidate_reports"
            ] = metric_reports

            candidates.append(
                candidate
            )

        candidates.sort(
            key=lambda item:
                item["score"],
            reverse=True,
        )

        base_result = {
            "resolved_dashboard":
                requested_dashboard,
            "resolved_report":
                requested_report,
            "resolved_semantic_model":
                semantic_model,
        }

        if not candidates:
            return {
                "status":
                    "not_found",
                **base_result,
                "candidates":
                    [],
            }

        best = candidates[0]

        if (
            best[
                "business_score"
            ]
            < self.min_score
        ):
            return {
                "status":
                    "not_found",
                **base_result,
                "best_score":
                    best["score"],
                "candidates":
                    candidates[:5],
            }

        if len(candidates) > 1:
            second = candidates[1]

            gap = (
                best["score"]
                - second["score"]
            )

            best_dashboards = {
                normalize_text(x)
                for x
                in best.get(
                    "candidate_dashboards",
                    [],
                )
                if x
            }

            second_dashboards = {
                normalize_text(x)
                for x
                in second.get(
                    "candidate_dashboards",
                    [],
                )
                if x
            }

            best_reports = {
                normalize_text(x)
                for x
                in best.get(
                    "candidate_reports",
                    [],
                )
                if x
            }

            second_reports = {
                normalize_text(x)
                for x
                in second.get(
                    "candidate_reports",
                    [],
                )
                if x
            }

            best_model = normalize_text(
                best.get(
                    "semantic_model"
                )
            )

            second_model = normalize_text(
                second.get(
                    "semantic_model"
                )
            )

            different_context = (
                (
                    bool(
                        best_dashboards
                        or second_dashboards
                    )
                    and
                    best_dashboards
                    != second_dashboards
                )
                or
                (
                    bool(
                        best_reports
                        or second_reports
                    )
                    and
                    best_reports
                    != second_reports
                )
                or
                (
                    bool(
                        best_model
                        or second_model
                    )
                    and
                    best_model
                    != second_model
                )
            )

            if (
                requested_dashboard is None
                and requested_report is None
                and semantic_model is None
                and different_context
                and gap
                < self.ambiguity_margin
            ):
                options = []

                best_business_score = (
                    best.get(
                        "business_score",
                        0.0,
                    )
                )

                for candidate in candidates:
                    candidate_business_score = (
                        candidate.get(
                            "business_score",
                            0.0,
                        )
                    )

                    if (
                        best_business_score
                        - candidate_business_score
                        > 0.05
                    ):
                        continue

                    candidate_reports = (
                        candidate.get(
                            "candidate_reports",
                            [],
                        )
                        or []
                    )

                    if candidate_reports:
                        for value in candidate_reports:
                            if (
                                value
                                and value
                                not in options
                            ):
                                options.append(
                                    value
                                )

                    else:
                        for value in candidate.get(
                            "candidate_dashboards",
                            [],
                        ):
                            if (
                                value
                                and value
                                not in options
                            ):
                                options.append(
                                    value
                                )

                return {
                    "status":
                        "ambiguous",
                    "reason":
                        "same_business_concept_multiple_sources",
                    **base_result,
                    "clarification_options":
                        options[:6],
                    "candidates":
                        candidates[:5],
                }

            same_context_gap = (
                best.get(
                    "business_score",
                    0.0,
                )
                -
                second.get(
                    "business_score",
                    0.0,
                )
            )

            if (
                gap
                < self.ambiguity_margin
                and
                same_context_gap
                < self.same_dashboard_ambiguity_margin
                and
                best.get(
                    "metric_id"
                )
                != second.get(
                    "metric_id"
                )
            ):
                return {
                    "status":
                        "ambiguous",
                    "reason":
                        "multiple_similar_metrics",
                    **base_result,
                    "clarification_options":
                        [],
                    "candidates":
                        candidates[:5],
                }

        resolved_report = (
            requested_report
            or (
                best.get(
                    "candidate_reports",
                    [],
                )[0]
                if best.get(
                    "candidate_reports",
                    [],
                )
                else None
            )
        )

        resolved_model = (
            semantic_model
            or best.get(
                "semantic_model"
            )
        )

        return {
            "status":
                "resolved",
            "resolved_dashboard":
                requested_dashboard,
            "resolved_report":
                resolved_report,
            "resolved_semantic_model":
                resolved_model,
            "metric":
                best,
            "candidates":
                candidates[:5],
        }

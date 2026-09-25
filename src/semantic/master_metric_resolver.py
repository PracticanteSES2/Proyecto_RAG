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

    def resolve(self, question, dashboard=None, approved_only=True):
        requested_dashboard = (
            dashboard
            or self._detect_dashboard_from_question(question)
        )

        candidates = []

        for metric in self.metrics:
            if (
                approved_only
                and metric.get("validation_status") != "approved"
            ):
                continue

            business_score = self._business_score(question, metric)

            if business_score < 0.30:
                continue

            metric_dashboards = self._metric_dashboards(metric)
            dashboard_score = 0.0

            if requested_dashboard:
                requested_norm = normalize_text(requested_dashboard)

                matching = [
                    value for value in metric_dashboards
                    if normalize_text(value) == requested_norm
                ]

                if metric_dashboards and not matching:
                    continue

                if matching:
                    dashboard_score = 1.0
            else:
                dashboard_score = max(
                    (
                        self._dashboard_match_score(question, value)
                        for value in metric_dashboards
                    ),
                    default=0.0,
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
                + intent_bonus
            )

            candidate = metric.copy()
            candidate["business_score"] = round(business_score, 4)
            candidate["dashboard_score"] = round(dashboard_score, 4)
            candidate["intent_bonus"] = round(intent_bonus, 4)
            candidate["score"] = round(final_score, 4)
            candidate["candidate_dashboards"] = metric_dashboards
            candidates.append(candidate)

        candidates.sort(key=lambda item: item["score"], reverse=True)

        if not candidates:
            return {
                "status": "not_found",
                "resolved_dashboard": requested_dashboard,
                "candidates": [],
            }

        best = candidates[0]

        if best["business_score"] < self.min_score:
            return {
                "status": "not_found",
                "resolved_dashboard": requested_dashboard,
                "best_score": best["score"],
                "candidates": candidates[:5],
            }

        if len(candidates) > 1:
            second = candidates[1]
            gap = best["score"] - second["score"]

            best_dashboards = {
                normalize_text(x)
                for x in best.get("candidate_dashboards", [])
                if x
            }

            second_dashboards = {
                normalize_text(x)
                for x in second.get("candidate_dashboards", [])
                if x
            }

            different_context = (
                bool(best_dashboards or second_dashboards)
                and best_dashboards != second_dashboards
            )

            if (
                requested_dashboard is None
                and different_context
                and gap < self.ambiguity_margin
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

                    # Mostrar únicamente dashboards cuyo concepto
                    # de negocio sea casi tan fuerte como el mejor.
                    if (
                        best_business_score
                        - candidate_business_score
                        > 0.05
                    ):
                        continue

                    for value in candidate.get(
                        "candidate_dashboards",
                        [],
                    ):
                        if (
                            value
                            and value not in options
                        ):
                            options.append(
                                value
                            )

                return {
                    "status": "ambiguous",
                    "reason": "same_business_concept_multiple_dashboards",
                    "clarification_options": options[:6],
                    "candidates": candidates[:5],
                }

            # Una vez que el dashboard está resuelto,
            # exigimos una similitud MUCHO mayor para contrapreguntar.
            # Esto evita que AÑO_ACTUAL o TOTAL_OBS compitan con una
            # métrica visual cuyo nombre coincide explícitamente.
            same_dashboard_gap = (
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
                gap < self.ambiguity_margin
                and
                same_dashboard_gap
                < self.same_dashboard_ambiguity_margin
                and
                best.get("metric_id")
                != second.get("metric_id")
            ):
                return {
                    "status": "ambiguous",
                    "reason": "multiple_similar_metrics",
                    "clarification_options": [],
                    "candidates": candidates[:5],
                }

        return {
            "status": "resolved",
            "resolved_dashboard": requested_dashboard,
            "metric": best,
            "candidates": candidates[:5],
        }

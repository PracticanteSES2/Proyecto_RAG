import json
import re
import unicodedata
from pathlib import Path


MONTHS = {
    "enero", "febrero", "marzo", "abril",
    "mayo", "junio", "julio", "agosto",
    "septiembre", "setiembre", "octubre",
    "noviembre", "diciembre",
}

STOPWORDS = {
    "a", "al", "cual", "cuales", "cuanto", "cuantos",
    "cuanta", "cuantas", "de", "del", "el", "en", "entre",
    "es", "fue", "ha", "han", "hay", "hubo", "la", "las",
    "lo", "los", "para", "por", "que", "se", "un", "una",
    "y", "valor", "dato", "datos", "mes", "ano", "año",
}

CALCULATION_WORDS = {
    "promedio", "prom", "media", "mensual",
    "total", "cantidad", "recuento", "numero",
    "porcentaje", "porcentual", "pct",
    "proyeccion", "proyectado", "estimado",
    "variacion", "crecimiento", "cambio",
}

VERB_FORMS = {
    "realizado": "realiz",
    "realizada": "realiz",
    "realizados": "realiz",
    "realizadas": "realiz",
    "realizar": "realiz",
    "realizaron": "realiz",
    "realiza": "realiz",
    "realizan": "realiz",
    "registrado": "registr",
    "registrada": "registr",
    "registrados": "registr",
    "registradas": "registr",
    "registrar": "registr",
    "registraron": "registr",
    "cancelado": "cancel",
    "cancelada": "cancel",
    "cancelados": "cancel",
    "canceladas": "cancel",
    "cancelar": "cancel",
    "programado": "program",
    "programada": "program",
    "programados": "program",
    "programadas": "program",
    "programar": "program",
    "observado": "observ",
    "observada": "observ",
    "observados": "observ",
    "observadas": "observ",
    "observar": "observ",
}


def normalize_text(value):
    value = str(value or "").lower().strip()

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


class MasterMetricResolver:
    """
    Resuelve una pregunta contra master_metrics.json.

    Separa tres señales:
      - business_score: concepto/indicador
      - metric_score: total, promedio, porcentaje, etc.
      - context_score: tabla/página/servicio

    La normalización morfológica permite hacer coincidir:
      cirugías <-> cirugia
      realizadas <-> realizado
      atenciones <-> atencion
      generales <-> general
    """

    def __init__(
        self,
        catalog_path,
        min_score=0.44,
        ambiguity_margin=0.08,
        same_dashboard_ambiguity_margin=0.035,
        dashboard_match_threshold=0.68,
        context_signal_threshold=0.58,
    ):
        self.catalog_path = Path(
            catalog_path
        )

        self.min_score = float(
            min_score
        )

        self.ambiguity_margin = float(
            ambiguity_margin
        )

        self.same_dashboard_ambiguity_margin = float(
            same_dashboard_ambiguity_margin
        )

        self.dashboard_match_threshold = float(
            dashboard_match_threshold
        )

        self.context_signal_threshold = float(
            context_signal_threshold
        )

        payload = json.loads(
            self.catalog_path.read_text(
                encoding="utf-8"
            )
        )

        self.metrics = payload.get(
            "metrics",
            [],
        )

        self.available_dashboards = (
            self._load_dashboards()
        )

    # ========================================================
    # NORMALIZACIÓN
    # ========================================================

    def _canonical_token(
        self,
        token,
    ):
        token = normalize_text(
            token
        )

        if not token:
            return ""

        if token in VERB_FORMS:
            return VERB_FORMS[
                token
            ]

        # atenciones -> atencion
        if (
            token.endswith("iones")
            and len(token) > 6
        ):
            return (
                token[:-5]
                + "ion"
            )

        # generales -> general
        if (
            token.endswith("ales")
            and len(token) > 5
        ):
            return token[:-2]

        # pacientes -> paciente
        if (
            token.endswith("entes")
            and len(token) > 6
        ):
            return token[:-1]

        # plásticas -> plastica
        # cirugías -> cirugia
        # consultas -> consulta
        if (
            token.endswith("s")
            and len(token) > 4
        ):
            return token[:-1]

        return token

    def _semantic_tokens(
        self,
        value,
        remove_calculation=False,
    ):
        tokens = []

        for raw_token in normalize_text(
            value
        ).split():

            if raw_token.isdigit():
                continue

            canonical = (
                self._canonical_token(
                    raw_token
                )
            )

            if not canonical:
                continue

            if (
                raw_token in MONTHS
                or canonical in MONTHS
            ):
                continue

            if (
                raw_token in STOPWORDS
                or canonical in STOPWORDS
            ):
                continue

            if (
                remove_calculation
                and (
                    raw_token
                    in CALCULATION_WORDS
                    or canonical
                    in CALCULATION_WORDS
                )
            ):
                continue

            if len(canonical) < 2:
                continue

            tokens.append(
                canonical
            )

        return tokens

    # ========================================================
    # DASHBOARDS / CONTEXTO
    # ========================================================

    def _metric_dashboards(
        self,
        metric,
    ):
        values = []

        direct = metric.get(
            "dashboard"
        )

        if direct:
            values.append(
                str(direct)
            )

        for appearance in (
            metric.get(
                "appearances",
                [],
            )
            or []
        ):
            page = appearance.get(
                "page_display_name"
            )

            if page:
                values.append(
                    str(page)
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
                seen.add(
                    key
                )

        return unique

    def _metric_context_values(
        self,
        metric,
    ):
        values = []

        for value in [
            metric.get("table"),
            metric.get("dashboard"),
        ]:
            if value:
                values.append(
                    str(value)
                )

        for appearance in (
            metric.get(
                "appearances",
                [],
            )
            or []
        ):
            page = appearance.get(
                "page_display_name"
            )

            if page:
                values.append(
                    str(page)
                )

            title = appearance.get(
                "visual_title"
            )

            if title:
                values.append(
                    str(title)
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
                seen.add(
                    key
                )

        return unique

    def _load_dashboards(
        self,
    ):
        result = []
        seen = set()

        for metric in self.metrics:

            for dashboard in (
                self._metric_dashboards(
                    metric
                )
            ):
                key = normalize_text(
                    dashboard
                )

                if (
                    key
                    and key not in seen
                ):
                    result.append(
                        dashboard
                    )
                    seen.add(
                        key
                    )

        return result

    # ========================================================
    # SIMILITUD
    # ========================================================

    def _token_overlap_score(
        self,
        text_a,
        text_b,
        remove_calculation=False,
    ):
        a = set(
            self._semantic_tokens(
                text_a,
                remove_calculation=
                    remove_calculation,
            )
        )

        b = set(
            self._semantic_tokens(
                text_b,
                remove_calculation=
                    remove_calculation,
            )
        )

        if not a or not b:
            return 0.0

        common = a & b

        coverage = (
            len(common)
            / len(b)
        )

        precision = (
            len(common)
            / len(a)
        )

        return (
            0.78 * coverage
            + 0.22 * precision
        )

    def _score_alias(
        self,
        question,
        alias,
    ):
        if not alias:
            return 0.0

        q_tokens = set(
            self._semantic_tokens(
                question
            )
        )

        a_tokens = set(
            self._semantic_tokens(
                alias
            )
        )

        if not q_tokens or not a_tokens:
            return 0.0

        if a_tokens <= q_tokens:
            return 1.0

        common = q_tokens & a_tokens

        if not common:
            return 0.0

        coverage = (
            len(common)
            / len(a_tokens)
        )

        precision = (
            len(common)
            / len(q_tokens)
        )

        if coverage < 0.34:
            return 0.0

        return (
            0.78 * coverage
            + 0.22 * precision
        )

    def _dashboard_match_score(
        self,
        question,
        dashboard,
    ):
        q = normalize_text(
            question
        )

        d = normalize_text(
            dashboard
        )

        if not d:
            return 0.0

        if d in q:
            return 1.0

        return self._token_overlap_score(
            question,
            dashboard,
            remove_calculation=True,
        )

    def _detect_dashboard_from_question(
        self,
        question,
    ):
        scored = []

        for dashboard in (
            self.available_dashboards
        ):
            score = (
                self._dashboard_match_score(
                    question,
                    dashboard,
                )
            )

            if (
                score
                >= self.dashboard_match_threshold
            ):
                scored.append(
                    (
                        dashboard,
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
            and (
                scored[0][1]
                - scored[1][1]
            )
            < 0.08
        ):
            return None

        return scored[0][0]

    # ========================================================
    # SCORE DE NEGOCIO
    # ========================================================

    def _is_technical_alias(
        self,
        alias,
    ):
        text = str(
            alias or ""
        )

        if any(
            marker in text
            for marker in (
                "(", ")", "[", "]"
            )
        ):
            return True

        normalized = normalize_text(
            text
        )

        return (
            not normalized
            or normalized
            in {
                "true",
                "false",
                "none",
                "null",
            }
            or normalized.isdigit()
        )

    def _business_score(
        self,
        question,
        metric,
    ):
        source_type = metric.get(
            "source_type"
        )

        direct_scores = []

        for value in [
            metric.get("label"),
            metric.get("measure"),
        ]:
            if value:
                direct_scores.append(
                    self._score_alias(
                        question,
                        value,
                    )
                )

        direct_score = max(
            direct_scores,
            default=0.0,
        )

        alias_scores = []

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

            alias_scores.append(
                self._score_alias(
                    question,
                    alias,
                )
            )

        alias_score = max(
            alias_scores,
            default=0.0,
        )

        if source_type == (
            "explicit_measure"
        ):
            # Los aliases de medidas explícitas pueden heredar
            # el título de un visual. Los usamos, pero con menor peso.
            return max(
                direct_score,
                0.72 * alias_score,
            )

        return max(
            direct_score,
            alias_score,
        )

    # ========================================================
    # TIPO DE CÁLCULO
    # ========================================================

    def _requested_calculation(
        self,
        question,
    ):
        text = normalize_text(
            question
        )

        if any(
            term in text
            for term in [
                "proyeccion",
                "proyectado",
                "estimado",
            ]
        ):
            return "projection"

        if any(
            term in text
            for term in [
                "porcentaje",
                "porcentual",
                "%",
            ]
        ):
            return "percentage"

        if any(
            term in text
            for term in [
                "variacion",
                "crecimiento",
                "cambio",
            ]
        ):
            return "variation"

        if any(
            term in text
            for term in [
                "promedio",
                "media",
            ]
        ):
            return "average"

        if any(
            term in text
            for term in [
                "cuanto",
                "cuanta",
                "cuantos",
                "cuantas",
                "cantidad",
                "recuento",
                "numero",
                "total",
            ]
        ):
            return "count"

        return None

    def _metric_calculation_score(
        self,
        question,
        metric,
    ):
        requested = (
            self._requested_calculation(
                question
            )
        )

        if requested is None:
            return 0.50

        aggregation = normalize_text(
            metric.get(
                "aggregation"
            )
            or ""
        )

        metric_text = " ".join(
            str(value)
            for value in [
                metric.get("label"),
                metric.get("measure"),
                " ".join(
                    metric.get(
                        "aliases",
                        [],
                    )
                    or []
                ),
            ]
            if value
        )

        metric_norm = normalize_text(
            metric_text
        )

        metric_tokens = set(
            self._semantic_tokens(
                metric_text
            )
        )

        if requested == "average":

            if aggregation == "average":
                return 1.0

            if (
                "promedio"
                in metric_tokens
                or "media"
                in metric_tokens
                or any(
                    token.startswith(
                        "prom"
                    )
                    for token
                    in metric_tokens
                )
            ):
                return 1.0

            return 0.0

        if requested == "count":

            if aggregation in {
                "count",
                "distinctcount",
            }:
                return 1.0

            if any(
                term in metric_norm
                for term in [
                    "total",
                    "recuento",
                    "cantidad",
                    "count",
                ]
            ):
                return 0.95

            return 0.20

        if requested == "percentage":

            if any(
                term in metric_norm
                for term in [
                    "porcentaje",
                    "porcentual",
                    "pct",
                    "percent",
                ]
            ):
                return 1.0

            return 0.0

        if requested == "projection":

            if any(
                term in metric_norm
                for term in [
                    "proyeccion",
                    "proyect",
                    "estimad",
                ]
            ):
                return 1.0

            return 0.0

        if requested == "variation":

            if any(
                term in metric_norm
                for term in [
                    "variacion",
                    "crecimiento",
                    "cambio",
                ]
            ):
                return 1.0

            return 0.0

        return 0.50

    def _context_score(
        self,
        question,
        metric,
    ):
        return max(
            (
                self._token_overlap_score(
                    question,
                    value,
                    remove_calculation=True,
                )
                for value
                in self._metric_context_values(
                    metric
                )
            ),
            default=0.0,
        )

    # ========================================================
    # RESOLUCIÓN
    # ========================================================

    def resolve(
        self,
        question,
        dashboard=None,
        approved_only=True,
    ):
        requested_dashboard = (
            dashboard
            or self._detect_dashboard_from_question(
                question
            )
        )

        raw_candidates = []

        for metric in self.metrics:

            if (
                approved_only
                and metric.get(
                    "validation_status"
                )
                != "approved"
            ):
                continue

            metric_dashboards = (
                self._metric_dashboards(
                    metric
                )
            )

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
                    if (
                        normalize_text(
                            value
                        )
                        == requested_norm
                    )
                ]

                if (
                    metric_dashboards
                    and not matching
                ):
                    continue

            business_score = (
                self._business_score(
                    question,
                    metric,
                )
            )

            metric_score = (
                self._metric_calculation_score(
                    question,
                    metric,
                )
            )

            context_score = (
                self._context_score(
                    question,
                    metric,
                )
            )

            # Un tipo de cálculo genérico ("total"/"promedio")
            # nunca es suficiente por sí solo.
            if (
                business_score < 0.18
                and context_score < 0.35
            ):
                continue

            dashboard_score = 0.0

            if requested_dashboard:
                if any(
                    normalize_text(value)
                    == normalize_text(
                        requested_dashboard
                    )
                    for value
                    in metric_dashboards
                ):
                    dashboard_score = 1.0

            raw_candidates.append(
                {
                    "metric":
                        metric,
                    "business_score":
                        business_score,
                    "metric_score":
                        metric_score,
                    "context_score":
                        context_score,
                    "dashboard_score":
                        dashboard_score,
                    "metric_dashboards":
                        metric_dashboards,
                }
            )

        if not raw_candidates:
            return {
                "status":
                    "not_found",
                "resolved_dashboard":
                    requested_dashboard,
                "candidates":
                    [],
            }

        max_context_score = max(
            item["context_score"]
            for item
            in raw_candidates
        )

        has_context_signal = (
            max_context_score
            >= self.context_signal_threshold
        )

        candidates = []

        for item in raw_candidates:

            final_score = (
                0.46
                * item[
                    "business_score"
                ]
                + 0.24
                * item[
                    "metric_score"
                ]
                + 0.30
                * item[
                    "context_score"
                ]
                + 0.08
                * item[
                    "dashboard_score"
                ]
            )

            if (
                has_context_signal
                and item[
                    "context_score"
                ]
                < 0.18
            ):
                final_score -= 0.18

            metric = (
                item["metric"]
                .copy()
            )

            metric[
                "business_score"
            ] = round(
                item[
                    "business_score"
                ],
                4,
            )

            metric[
                "metric_score"
            ] = round(
                item[
                    "metric_score"
                ],
                4,
            )

            metric[
                "context_score"
            ] = round(
                item[
                    "context_score"
                ],
                4,
            )

            metric[
                "dashboard_score"
            ] = round(
                item[
                    "dashboard_score"
                ],
                4,
            )

            metric[
                "score"
            ] = round(
                final_score,
                4,
            )

            metric[
                "candidate_dashboards"
            ] = item[
                "metric_dashboards"
            ]

            candidates.append(
                metric
            )

        candidates.sort(
            key=lambda candidate:
                candidate["score"],
            reverse=True,
        )

        best = candidates[0]

        if (
            best["score"]
            < self.min_score
        ):
            return {
                "status":
                    "not_found",
                "resolved_dashboard":
                    requested_dashboard,
                "best_score":
                    best["score"],
                "candidates":
                    candidates[:5],
            }

        resolved_dashboard = (
            requested_dashboard
        )

        if (
            resolved_dashboard is None
            and len(
                best.get(
                    "candidate_dashboards",
                    [],
                )
            )
            == 1
        ):
            resolved_dashboard = (
                best[
                    "candidate_dashboards"
                ][0]
            )

        if len(candidates) > 1:

            second = candidates[1]

            gap = (
                best["score"]
                - second["score"]
            )

            best_dashboards = {
                normalize_text(
                    value
                )
                for value
                in best.get(
                    "candidate_dashboards",
                    [],
                )
                if value
            }

            second_dashboards = {
                normalize_text(
                    value
                )
                for value
                in second.get(
                    "candidate_dashboards",
                    [],
                )
                if value
            }

            different_context = (
                bool(
                    best_dashboards
                    or second_dashboards
                )
                and
                best_dashboards
                != second_dashboards
            )

            if (
                resolved_dashboard is None
                and different_context
                and gap
                < self.ambiguity_margin
            ):
                options = []

                best_score = best.get(
                    "score",
                    0.0,
                )

                for candidate in candidates:

                    if (
                        best_score
                        - candidate.get(
                            "score",
                            0.0,
                        )
                        > 0.07
                    ):
                        continue

                    for value in (
                        candidate.get(
                            "candidate_dashboards",
                            [],
                        )
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
                        "same_business_concept_multiple_dashboards",
                    "clarification_options":
                        options[:6],
                    "candidates":
                        candidates[:5],
                }

            if (
                gap
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
                    "clarification_options":
                        [],
                    "candidates":
                        candidates[:5],
                }

        return {
            "status":
                "resolved",
            "resolved_dashboard":
                resolved_dashboard,
            "metric":
                best,
            "candidates":
                candidates[:5],
        }

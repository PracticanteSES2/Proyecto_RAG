import re
import unicodedata


GENERIC_ENTITY_TOKENS = {
    "cirugia",
    "consulta",
    "atencion",
    "egreso",
    "procedimiento",
    "paciente",
    "urgencia",
    "hospitalizacion",
    "cita",
    "servicio",
    "parto",
    "observacion",
}

STOPWORDS = {
    "a", "al", "de", "del", "el", "en", "entre",
    "ha", "han", "la", "las", "lo", "los",
    "para", "por", "que", "se", "un", "una", "y",
}

VERB_FORMS = {
    "realizado": "realiz",
    "realizada": "realiz",
    "realizados": "realiz",
    "realizadas": "realiz",
    "realizar": "realiz",
    "realizaron": "realiz",
    "registrado": "registr",
    "registrada": "registr",
    "registrados": "registr",
    "registradas": "registr",
    "cancelado": "cancel",
    "cancelada": "cancel",
    "cancelados": "cancel",
    "canceladas": "cancel",
    "programado": "program",
    "programada": "program",
    "programados": "program",
    "programadas": "program",
    "observado": "observ",
    "observada": "observ",
    "observados": "observ",
    "observadas": "observ",
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


def canonical_token(token):
    token = normalize_text(
        token
    )

    if not token:
        return ""

    if token in VERB_FORMS:
        return VERB_FORMS[
            token
        ]

    if (
        token.endswith("iones")
        and len(token) > 6
    ):
        return (
            token[:-5]
            + "ion"
        )

    if (
        token.endswith("ales")
        and len(token) > 5
    ):
        return token[:-2]

    if (
        token.endswith("entes")
        and len(token) > 6
    ):
        return token[:-1]

    if (
        token.endswith("s")
        and len(token) > 4
    ):
        return token[:-1]

    return token


def canonical_tokens(value):
    result = []

    for raw in normalize_text(
        value
    ).split():

        if raw in STOPWORDS:
            continue

        token = canonical_token(
            raw
        )

        if (
            token
            and token not in STOPWORDS
        ):
            result.append(
                token
            )

    return result


class QuerySemanticPlanner:
    """
    Separa una pregunta numérica en:
      - pregunta para resolver la métrica;
      - valores de dimensiones/filtros;
      - dashboard sugerido por esos valores.
    """

    def __init__(
        self,
        master_metric_resolver,
        business_filter_resolver,
        powerbi_provider,
        max_candidate_dashboards=2,
        min_value_score=0.82,
    ):
        self.master_metric_resolver = (
            master_metric_resolver
        )

        self.business_filter_resolver = (
            business_filter_resolver
        )

        self.powerbi_provider = (
            powerbi_provider
        )

        self.max_candidate_dashboards = int(
            max_candidate_dashboards
        )

        self.min_value_score = float(
            min_value_score
        )

    def _candidate_dashboards(
        self,
        question,
        initial_metric_result,
    ):
        """
        Reduce al mínimo las consultas de dominios a Power BI.

        Antes, incluso cuando el MasterMetricResolver ya había
        resuelto un dashboard, el planner seguía agregando páginas
        hasta completar 6 candidatos. Eso disparaba muchas consultas
        VALUES(...) innecesarias.

        Ahora:
        - resolved -> solo ese dashboard;
        - ambiguous -> solo opciones reales de aclaración;
        - candidatos -> máximo N dashboards de los mejores candidatos;
        - fallback -> máximo N por similitud léxica.
        """

        resolved = (
            initial_metric_result.get(
                "resolved_dashboard"
            )
        )

        if resolved:
            return [
                resolved
            ]

        options = (
            initial_metric_result.get(
                "clarification_options",
                [],
            )
            or []
        )

        if options:
            return list(
                dict.fromkeys(
                    options
                )
            )[
                :self.max_candidate_dashboards
            ]

        result = []

        for candidate in (
            initial_metric_result.get(
                "candidates",
                [],
            )
        ):
            for dashboard in (
                candidate.get(
                    "candidate_dashboards",
                    [],
                )
            ):
                if (
                    dashboard
                    and dashboard not in result
                ):
                    result.append(
                        dashboard
                    )

                if (
                    len(result)
                    >= self.max_candidate_dashboards
                ):
                    return result

        # Solo si el resolver no dio contexto útil,
        # recurrimos a similitud contra páginas conocidas.
        if not result:

            scored = []

            for dashboard in (
                self.business_filter_resolver
                .get_available_dashboards()
            ):

                score = (
                    self.master_metric_resolver
                    ._dashboard_match_score(
                        question,
                        dashboard,
                    )
                )

                if score <= 0:
                    continue

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

            for dashboard, _ in scored[
                :self.max_candidate_dashboards
            ]:

                result.append(
                    dashboard
                )

        return result

    def _dedupe_matches(
        self,
        matches,
    ):
        best_by_key = {}

        for item in matches:

            key = (
                item.get(
                    "concept"
                ),
                normalize_text(
                    item.get(
                        "value"
                    )
                ),
            )

            current = best_by_key.get(
                key
            )

            item_score = item.get(
                "rank_score",
                item.get(
                    "score",
                    0.0,
                ),
            )

            current_score = (
                current.get(
                    "rank_score",
                    current.get(
                        "score",
                        0.0,
                    ),
                )
                if current
                else -1.0
            )

            if (
                current is None
                or item_score
                > current_score
            ):
                best_by_key[
                    key
                ] = item

        result = list(
            best_by_key.values()
        )

        result.sort(
            key=lambda item:
                item.get(
                    "rank_score",
                    item.get(
                        "score",
                        0.0,
                    ),
                ),
            reverse=True,
        )

        return result

    def _build_metric_question(
        self,
        question,
        matches,
    ):
        question_tokens = (
            canonical_tokens(
                question
            )
        )

        removable = set()

        for item in matches:

            for token in canonical_tokens(
                item.get(
                    "value"
                )
            ):
                if (
                    token
                    not in GENERIC_ENTITY_TOKENS
                ):
                    removable.add(
                        token
                    )

        cleaned = [
            token
            for token
            in question_tokens
            if token not in removable
        ]

        if not cleaned:
            return question

        return " ".join(
            cleaned
        )

    def _build_filter_question(
        self,
        question,
        matches,
    ):
        values = []

        for item in matches:

            value = item.get(
                "value"
            )

            if (
                value
                and value not in values
            ):
                values.append(
                    str(value)
                )

        if not values:
            return question

        return (
            question
            + " "
            + " ".join(
                values
            )
        )

    def _dashboard_hint(
        self,
        matches,
    ):
        if not matches:
            return None

        # Agrupar evidencia por dashboard.
        by_dashboard = {}

        for item in matches:

            dashboard = item.get(
                "dashboard"
            )

            if not dashboard:
                continue

            score = item.get(
                "rank_score",
                item.get(
                    "score",
                    0.0,
                ),
            )

            by_dashboard[
                dashboard
            ] = max(
                by_dashboard.get(
                    dashboard,
                    0.0,
                ),
                score,
            )

        if not by_dashboard:
            return None

        scored = sorted(
            by_dashboard.items(),
            key=lambda item:
                item[1],
            reverse=True,
        )

        if len(scored) == 1:
            return scored[0][0]

        if (
            scored[0][1]
            - scored[1][1]
            >= 0.05
        ):
            return scored[0][0]

        # Si el mismo valor aparece en varias páginas
        # con la misma fuerza, no inventamos.
        return None

    def plan(
        self,
        question,
        semantic_model=None,
    ):
        semantic_model = (
            semantic_model
            or self.powerbi_provider
            .default_semantic_model
        )

        initial_metric_result = (
            self.master_metric_resolver
            .resolve(
                question
            )
        )

        dashboards = (
            self._candidate_dashboards(
                question,
                initial_metric_result,
            )
        )

        all_matches = []

        for dashboard in dashboards:

            matches = (
                self.business_filter_resolver
                .find_dimension_matches(
                    question=
                        question,
                    dashboard=
                        dashboard,
                    semantic_model=
                        semantic_model,
                    min_score=
                        self.min_value_score,
                )
            )

            all_matches.extend(
                matches
            )

        matches = (
            self._dedupe_matches(
                all_matches
            )
        )

        dashboard_hint = (
            self._dashboard_hint(
                matches
            )
        )

        return {
            "status":
                "planned",
            "original_question":
                question,
            "metric_question":
                self._build_metric_question(
                    question,
                    matches,
                ),
            "filter_question":
                self._build_filter_question(
                    question,
                    matches,
                ),
            "dimension_matches":
                matches,
            "candidate_dashboards":
                dashboards,
            "dashboard_hint":
                dashboard_hint,
            "initial_metric_result":
                initial_metric_result,
        }

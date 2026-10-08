import re
import unicodedata
from difflib import SequenceMatcher


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


def normalize_text(value):
    value = str(value or "").lower().strip()

    value = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )

    value = re.sub(r"[^a-z0-9]+", " ", value)

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
        canonical = canonical_token(token)

        if canonical:
            result.append(canonical)

    return result


def token_similarity(left, right):
    if left == right:
        return 1.0

    if (
        len(left) >= 5
        and len(right) >= 5
        and (
            left.startswith(right[:5])
            or right.startswith(left[:5])
        )
    ):
        return 0.90

    return SequenceMatcher(
        None,
        left,
        right,
    ).ratio()


def phrase_match_score(question, value):
    question_tokens = canonical_tokens(question)
    value_tokens = canonical_tokens(value)

    if not question_tokens or not value_tokens:
        return 0.0

    matched_scores = []

    for value_token in value_tokens:

        best = max(
            (
                token_similarity(
                    value_token,
                    question_token,
                )
                for question_token in question_tokens
            ),
            default=0.0,
        )

        matched_scores.append(best)

    coverage = (
        sum(
            1
            for score in matched_scores
            if score >= 0.78
        )
        / len(value_tokens)
    )

    if coverage < 0.60:
        return 0.0

    average_similarity = (
        sum(matched_scores)
        / len(matched_scores)
    )

    multiword_bonus = (
        0.06
        if len(value_tokens) >= 2
        and coverage == 1.0
        else 0.0
    )

    return min(
        1.0,
        (
            0.72 * coverage
            + 0.28 * average_similarity
            + multiword_bonus
        ),
    )


class QuerySemanticPlanner:

    def __init__(
        self,
        master_metric_resolver,
        business_filter_resolver,
        powerbi_provider,
        source_router=None,
        max_candidate_dashboards=5,
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

        self.source_router = (
            source_router
        )

        self.max_candidate_dashboards = int(
            max_candidate_dashboards
        )

        self.min_value_score = float(
            min_value_score
        )

    def _master_resolve(
        self,
        question,
        semantic_model=None,
        report=None,
        dashboard=None,
    ):
        return (
            self.master_metric_resolver
            .resolve(
                question=
                    question,
                semantic_model=
                    semantic_model,
                report=
                    report,
                dashboard=
                    dashboard,
            )
        )

    def _candidate_contexts(
        self,
        question,
        initial_metric_result,
        semantic_model=None,
        report=None,
    ):
        contexts = []

        def add(
            dashboard,
            model,
            report_name=None,
            score=1.0,
        ):
            if not dashboard:
                return

            key = (
                normalize_text(
                    model
                ),
                normalize_text(
                    report_name
                ),
                normalize_text(
                    dashboard
                ),
            )

            if any(
                item["_key"] == key
                for item in contexts
            ):
                return

            contexts.append({
                "_key":
                    key,
                "dashboard":
                    dashboard,
                "semantic_model":
                    model,
                "report":
                    report_name,
                "score":
                    score,
            })

        result = (
            initial_metric_result
            or {}
        )

        metric = result.get(
            "metric",
            {},
        )

        resolved_model = (
            semantic_model
            or result.get(
                "resolved_semantic_model"
            )
            or metric.get(
                "semantic_model"
            )
        )

        resolved_report = (
            report
            or result.get(
                "resolved_report"
            )
        )

        resolved_dashboard = result.get(
            "resolved_dashboard"
        )

        if resolved_dashboard:
            add(
                resolved_dashboard,
                resolved_model,
                resolved_report,
                1.0,
            )

        for candidate in result.get(
            "candidates",
            [],
        ):
            candidate_model = (
                semantic_model
                or candidate.get(
                    "semantic_model"
                )
            )

            candidate_reports = (
                candidate.get(
                    "candidate_reports",
                    [],
                )
                or []
            )

            candidate_report = (
                report
                or (
                    candidate_reports[0]
                    if len(
                        candidate_reports
                    ) == 1
                    else None
                )
            )

            for dashboard in candidate.get(
                "candidate_dashboards",
                [],
            ):
                add(
                    dashboard,
                    candidate_model,
                    candidate_report,
                    candidate.get(
                        "score",
                        0.0,
                    ),
                )

        # Si conocemos el modelo por el reporte pero la métrica no
        # aportó páginas, buscamos únicamente páginas de ESE modelo.
        if (
            self.source_router
            and len(contexts)
            < self.max_candidate_dashboards
        ):
            page_candidates = (
                self.source_router
                .candidate_pages(
                    question=
                        question,
                    semantic_model=
                        semantic_model,
                    limit=
                        self.max_candidate_dashboards,
                )
            )

            for item in page_candidates:
                add(
                    item.get(
                        "dashboard"
                    ),
                    (
                        semantic_model
                        or item.get(
                            "semantic_model"
                        )
                    ),
                    (
                        report
                        or item.get(
                            "report"
                        )
                    ),
                    item.get(
                        "score",
                        0.0,
                    ),
                )

                if (
                    len(contexts)
                    >=
                    self.max_candidate_dashboards
                ):
                    break

        # Compatibilidad legacy: solo si no obtuvimos ningún contexto.
        if not contexts:
            fallback_model = (
                semantic_model
                or self.powerbi_provider
                .default_semantic_model
            )

            for dashboard in getattr(
                self.master_metric_resolver,
                "available_dashboards",
                [],
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

                add(
                    dashboard,
                    fallback_model,
                    report,
                    score,
                )

                if (
                    len(contexts)
                    >=
                    self.max_candidate_dashboards
                ):
                    break

        contexts.sort(
            key=lambda item:
                item.get(
                    "score",
                    0.0,
                ),
            reverse=True,
        )

        for item in contexts:
            item.pop(
                "_key",
                None,
            )

        return contexts[
            :self.max_candidate_dashboards
        ]

    def _resolve_values_for_dashboard(
        self,
        question,
        dashboard,
        semantic_model,
    ):
        if not semantic_model:
            return []

        matches = []

        base = (
            self.business_filter_resolver
        )

        concepts = getattr(
            base,
            "CONCEPTS",
            {},
        )

        for concept in concepts:
            column = None

            try:
                column = base._find_column(
                    concept,
                    dashboard,
                    semantic_model=
                        semantic_model,
                )
            except TypeError:
                # Compatibilidad con el resolver legacy.
                try:
                    column = base._find_column(
                        concept,
                        dashboard,
                    )
                except Exception:
                    column = None
            except Exception:
                column = None

            if not column:
                continue

            table = column.get(
                "table"
            )

            column_name = column.get(
                "column"
            )

            if (
                not table
                or not column_name
            ):
                continue

            try:
                values = base._get_values(
                    semantic_model,
                    table,
                    column_name,
                )
            except Exception:
                values = []

            best_value = None
            best_score = 0.0

            for value in values:
                score = phrase_match_score(
                    question,
                    value,
                )

                if score > best_score:
                    best_score = score
                    best_value = value

            if (
                best_value is None
                or best_score
                < self.min_value_score
            ):
                continue

            matches.append({
                "status":
                    "resolved",
                "concept":
                    concept,
                "dashboard":
                    dashboard,
                "semantic_model":
                    semantic_model,
                "table":
                    table,
                "column":
                    column_name,
                "operator":
                    "=",
                "value":
                    best_value,
                "score":
                    round(
                        best_score,
                        4,
                    ),
                "source":
                    "semantic_dimension_value",
            })

        return matches

    def _dedupe_matches(
        self,
        matches,
    ):
        by_key = {}

        for item in matches:
            key = (
                item.get(
                    "semantic_model"
                ),
                item.get(
                    "concept"
                ),
                normalize_text(
                    item.get(
                        "value"
                    )
                ),
            )

            current = by_key.get(
                key
            )

            if (
                current is None
                or item.get(
                    "score",
                    0.0,
                )
                > current.get(
                    "score",
                    0.0,
                )
            ):
                by_key[
                    key
                ] = item

        return list(
            by_key.values()
        )

    def _build_metric_question(
        self,
        question,
        matches,
    ):
        question_tokens = canonical_tokens(
            question
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
        values = [
            str(
                item.get(
                    "value"
                )
            )
            for item in matches
            if item.get(
                "value"
            )
        ]

        if not values:
            return question

        return (
            question
            + " "
            + " ".join(
                values
            )
        )

    def plan(
        self,
        question,
        semantic_model=None,
        report=None,
    ):
        initial_metric_result = (
            self._master_resolve(
                question=
                    question,
                semantic_model=
                    semantic_model,
                report=
                    report,
            )
        )

        contexts = (
            self._candidate_contexts(
                question=
                    question,
                initial_metric_result=
                    initial_metric_result,
                semantic_model=
                    semantic_model,
                report=
                    report,
            )
        )

        all_matches = []

        for context in contexts:
            model = (
                context.get(
                    "semantic_model"
                )
                or semantic_model
            )

            matches = (
                self._resolve_values_for_dashboard(
                    question=
                        question,
                    dashboard=
                        context.get(
                            "dashboard"
                        ),
                    semantic_model=
                        model,
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

        metric_question = (
            self._build_metric_question(
                question,
                matches,
            )
        )

        filter_question = (
            self._build_filter_question(
                question,
                matches,
            )
        )

        resolved_models = []

        for context in contexts:
            model = context.get(
                "semantic_model"
            )

            if (
                model
                and model
                not in resolved_models
            ):
                resolved_models.append(
                    model
                )

        return {
            "status":
                "planned",
            "original_question":
                question,
            "metric_question":
                metric_question,
            "filter_question":
                filter_question,
            "dimension_matches":
                matches,
            "candidate_dashboards":
                [
                    item.get(
                        "dashboard"
                    )
                    for item in contexts
                    if item.get(
                        "dashboard"
                    )
                ],
            "candidate_contexts":
                contexts,
            "semantic_model":
                (
                    semantic_model
                    or (
                        resolved_models[0]
                        if len(
                            resolved_models
                        ) == 1
                        else None
                    )
                ),
            "report":
                report,
            "initial_metric_result":
                initial_metric_result,
        }

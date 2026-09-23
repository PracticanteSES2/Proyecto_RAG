import re
import unicodedata


class QueryEngine:

    def __init__(
        self,
        conversation_manager,
        metric_resolver,
        filter_resolver,
        business_filter_resolver,
        dax_generator,
        dax_validator,
        powerbi_provider,
        rag_answer_engine
    ):

        self.conversation_manager = conversation_manager
        self.metric_resolver = metric_resolver
        self.filter_resolver = filter_resolver
        self.business_filter_resolver = business_filter_resolver
        self.dax_generator = dax_generator
        self.dax_validator = dax_validator
        self.powerbi_provider = powerbi_provider
        self.rag_answer_engine = rag_answer_engine

        # Estado para aclaraciones producidas por MetricResolver.
        self._pending_metric_clarification = None


    # ========================================================
    # UTILIDADES
    # ========================================================

    def _normalize_text(self, value):

        if not value:
            return ""

        value = str(value).lower().strip()

        value = "".join(
            character
            for character in unicodedata.normalize(
                "NFD",
                value
            )
            if unicodedata.category(character) != "Mn"
        )

        value = re.sub(
            r"[^a-z0-9\s]",
            " ",
            value
        )

        value = re.sub(
            r"\s+",
            " ",
            value
        )

        return value.strip()


    def _extract_value(
        self,
        powerbi_result
    ):

        rows = powerbi_result.get(
            "rows",
            []
        )

        if not rows:
            return None

        first_row = rows[0]

        if not first_row:
            return None

        return next(
            iter(
                first_row.values()
            ),
            None
        )


    # ========================================================
    # ACLARACIONES DE MÉTRICA
    # ========================================================

    def _candidate_options(
        self,
        candidates
    ):

        dashboards = []
        measures = []

        for candidate in candidates:

            dashboard = candidate.get(
                "dashboard"
            )

            measure = candidate.get(
                "measure"
            )

            if (
                dashboard
                and dashboard not in dashboards
            ):
                dashboards.append(
                    dashboard
                )

            if (
                measure
                and measure not in measures
            ):
                measures.append(
                    measure
                )

        # Si hay más de un dashboard, primero aclaramos servicio/tablero.
        if len(dashboards) > 1:
            return (
                "dashboard",
                dashboards[:3]
            )

        # Si todos los candidatos pertenecen al mismo dashboard
        # pero hay varias medidas, aclaramos la medida.
        if len(measures) > 1:
            return (
                "measure",
                measures[:3]
            )

        if dashboards:
            return (
                "dashboard",
                dashboards[:1]
            )

        return (
            "measure",
            measures[:3]
        )


    def _build_metric_clarification_question(
        self,
        candidates
    ):

        option_type, options = (
            self._candidate_options(
                candidates
            )
        )

        if not options:

            return (
                "Encontré varias métricas posibles. "
                "¿Podrías precisar un poco más "
                "a cuál te refieres?"
            )

        if option_type == "dashboard":

            return (
                "Encontré varias opciones relacionadas. "
                "¿A qué servicio o tablero te refieres? "
                + ", ".join(options)
                + "."
            )

        return (
            "Encontré varias medidas relacionadas. "
            "¿A cuál te refieres? "
            + ", ".join(options)
            + "."
        )


    def _select_pending_metric_candidate(
        self,
        message
    ):

        pending = (
            self._pending_metric_clarification
        )

        if not pending:
            return None

        answer = self._normalize_text(
            message
        )

        candidates = pending.get(
            "candidates",
            []
        )

        if not answer:
            return None

        # ----------------------------------------------------
        # 1. Intentar seleccionar por medida
        # ----------------------------------------------------

        measure_matches = []

        for candidate in candidates:

            measure = self._normalize_text(
                candidate.get(
                    "measure"
                )
            )

            if (
                measure
                and (
                    answer in measure
                    or measure in answer
                )
            ):

                measure_matches.append(
                    candidate
                )

        if len(measure_matches) == 1:
            selected = measure_matches[0]

        else:

            # ------------------------------------------------
            # 2. Intentar seleccionar por dashboard
            # ------------------------------------------------

            dashboard_matches = []

            for candidate in candidates:

                dashboard = self._normalize_text(
                    candidate.get(
                        "dashboard"
                    )
                )

                if (
                    dashboard
                    and (
                        answer in dashboard
                        or dashboard in answer
                    )
                ):

                    dashboard_matches.append(
                        candidate
                    )

            unique_measures = {
                candidate.get(
                    "measure"
                )
                for candidate in dashboard_matches
                if candidate.get(
                    "measure"
                )
            }

            if (
                dashboard_matches
                and len(unique_measures) == 1
            ):

                selected = (
                    dashboard_matches[0]
                )

            elif dashboard_matches:

                # El usuario aclaró el dashboard,
                # pero todavía hay varias medidas posibles.
                self._pending_metric_clarification[
                    "candidates"
                ] = dashboard_matches

                return (
                    "needs_more_clarification",
                    dashboard_matches
                )

            else:

                return None


        intent_result = pending[
            "intent_result"
        ].copy()

        intent_result[
            "dashboard"
        ] = selected.get(
            "dashboard"
        )

        metric_result = {
            "status":
                "resolved",

            "dashboard":
                selected.get(
                    "dashboard"
                ),

            "metric_type":
                pending.get(
                    "metric_type"
                ),

            "semantic_model":
                selected.get(
                    "semantic_model"
                ),

            "measure":
                selected.get(
                    "measure"
                ),

            "table":
                selected.get(
                    "table"
                ),

            "score":
                selected.get(
                    "final_score",
                    selected.get(
                        "score",
                        0
                    )
                ),

            "vector_score":
                selected.get(
                    "vector_score",
                    selected.get(
                        "score",
                        0
                    )
                ),

            "context":
                selected.get(
                    "text",
                    ""
                ),

            "alternatives":
                []
        }

        self._pending_metric_clarification = (
            None
        )

        return (
            intent_result,
            metric_result
        )


    # ========================================================
    # PROCESAR MENSAJE
    # ========================================================

    def process(
        self,
        message
    ):

        # ----------------------------------------------------
        # 0. ¿Estamos respondiendo una aclaración de métrica?
        # ----------------------------------------------------

        pending_selection = (
            self._select_pending_metric_candidate(
                message
            )
        )

        if (
            pending_selection
            and pending_selection[0]
            == "needs_more_clarification"
        ):

            candidates = pending_selection[1]

            return {
                "status":
                    "needs_clarification",

                "route":
                    "clarification",

                "question":
                    self._build_metric_clarification_question(
                        candidates
                    ),

                "clarification_type":
                    "metric_ambiguity",

                "candidates":
                    candidates
            }

        if pending_selection:

            (
                intent_result,
                metric_result
            ) = pending_selection

        else:

            # Si había una aclaración pendiente pero el mensaje no
            # identifica ninguna opción, volvemos a preguntar.
            if (
                self._pending_metric_clarification
                is not None
            ):

                candidates = (
                    self._pending_metric_clarification
                    .get(
                        "candidates",
                        []
                    )
                )

                return {
                    "status":
                        "needs_clarification",

                    "route":
                        "clarification",

                    "question":
                        self._build_metric_clarification_question(
                            candidates
                        ),

                    "clarification_type":
                        "metric_ambiguity",

                    "candidates":
                        candidates
                }


            # ------------------------------------------------
            # 1. INTENCIÓN + CONVERSACIÓN
            # ------------------------------------------------

            intent_result = (
                self.conversation_manager
                .handle_message(
                    message
                )
            )

            if (
                intent_result.get(
                    "status"
                )
                == "needs_clarification"
            ):

                return {
                    "status":
                        "needs_clarification",

                    "route":
                        "clarification",

                    "question":
                        intent_result.get(
                            "clarification_question"
                        ),

                    "intent":
                        intent_result
                }

            if (
                intent_result.get(
                    "status"
                )
                != "ready"
            ):

                return {
                    "status":
                        "error",

                    "stage":
                        "intent",

                    "details":
                        intent_result
                }


            # ------------------------------------------------
            # 2. ROUTING DOCUMENTAL
            # ------------------------------------------------

            intent = intent_result.get(
                "intent"
            )

            if intent in [
                "describe_dashboard",
                "get_filters",
                "general_question"
            ]:

                rag_result = (
                    self.rag_answer_engine
                    .answer(
                        intent_result
                    )
                )

                return {
                    "status":
                        rag_result.get(
                            "status"
                        ),

                    "route":
                        "rag",

                    "question":
                        intent_result.get(
                            "original_question"
                        ),

                    "dashboard":
                        intent_result.get(
                            "dashboard"
                        ),

                    "answer":
                        rag_result.get(
                            "answer"
                        ),

                    "sources":
                        rag_result.get(
                            "sources",
                            []
                        )
                }


            # ------------------------------------------------
            # 3. RESOLVER MÉTRICA
            # ------------------------------------------------

            metric_result = (
                self.metric_resolver
                .resolve(
                    intent_result
                )
            )

            if (
                metric_result.get(
                    "status"
                )
                == "ambiguous"
            ):

                candidates = (
                    metric_result.get(
                        "candidates",
                        []
                    )
                )

                self._pending_metric_clarification = {
                    "intent_result":
                        intent_result.copy(),

                    "metric_type":
                        intent_result.get(
                            "metric_type"
                        ),

                    "candidates":
                        candidates
                }

                return {
                    "status":
                        "needs_clarification",

                    "route":
                        "clarification",

                    "question":
                        self._build_metric_clarification_question(
                            candidates
                        ),

                    "clarification_type":
                        "metric_ambiguity",

                    "candidates":
                        candidates
                }

            if (
                metric_result.get(
                    "status"
                )
                != "resolved"
            ):

                return {
                    "status":
                        "metric_not_resolved",

                    "stage":
                        "metric",

                    "details":
                        metric_result
                }


        # ====================================================
        # 4. DASHBOARD RESUELTO
        # ====================================================

        resolved_dashboard = (
            intent_result.get(
                "dashboard"
            )
            or metric_result.get(
                "dashboard"
            )
        )

        resolved_intent = (
            intent_result.copy()
        )

        resolved_intent[
            "dashboard"
        ] = resolved_dashboard


        # ====================================================
        # 5. MODELO SEMÁNTICO
        # ====================================================

        semantic_model = (
            metric_result.get(
                "semantic_model"
            )
            or self.powerbi_provider
            .default_semantic_model
        )


        # ====================================================
        # 6. FILTROS TEMPORALES
        # ====================================================

        temporal_filter_result = (
            self.filter_resolver
            .resolve(
                resolved_intent
            )
        )

        if (
            temporal_filter_result.get(
                "status"
            )
            != "resolved"
        ):

            return {
                "status":
                    "filter_not_resolved",

                "stage":
                    "temporal_filters",

                "details":
                    temporal_filter_result
            }


        # ====================================================
        # 7. FILTROS DE NEGOCIO
        # ====================================================

        business_filter_result = (
            self.business_filter_resolver
            .resolve(
                question=(
                    resolved_intent.get(
                        "original_question"
                    )
                    or ""
                ),
                dashboard=
                    resolved_dashboard,
                semantic_model=
                    semantic_model
            )
        )

        if (
            business_filter_result.get(
                "status"
            )
            != "resolved"
        ):

            return {
                "status":
                    "filter_not_resolved",

                "stage":
                    "business_filters",

                "details":
                    business_filter_result
            }


        # ====================================================
        # 8. COMBINAR FILTROS
        # ====================================================

        temporal_filters = (
            temporal_filter_result.get(
                "filters",
                []
            )
        )

        business_filters = (
            business_filter_result.get(
                "filters",
                []
            )
        )

        combined_filters = (
            temporal_filters
            + business_filters
        )

        filter_result = {
            "status":
                "resolved",

            "filters":
                combined_filters,

            "problems":
                []
        }


        # ====================================================
        # 9. GENERAR DAX
        # ====================================================

        dax_result = (
            self.dax_generator
            .generate(
                metric_result,
                filter_result
            )
        )

        if (
            dax_result.get(
                "status"
            )
            != "generated"
        ):

            return {
                "status":
                    "dax_not_generated",

                "stage":
                    "dax_generator",

                "details":
                    dax_result
            }


        # ====================================================
        # 10. VALIDAR DAX
        # ====================================================

        validation_result = (
            self.dax_validator
            .validate(
                dax_result,
                metric_result,
                filter_result
            )
        )

        if not validation_result.get(
            "valid",
            False
        ):

            return {
                "status":
                    "dax_rejected",

                "stage":
                    "dax_validator",

                "details":
                    validation_result
            }


        # ====================================================
        # 11. EJECUTAR POWER BI
        # ====================================================

        powerbi_result = (
            self.powerbi_provider
            .execute_validated(
                validation_result,
                semantic_model=
                    semantic_model
            )
        )

        if (
            powerbi_result.get(
                "status"
            )
            != "success"
        ):

            return {
                "status":
                    "powerbi_error",

                "stage":
                    "powerbi",

                "details":
                    powerbi_result
            }


        # ====================================================
        # 12. EXTRAER VALOR
        # ====================================================

        value = self._extract_value(
            powerbi_result
        )


        # ====================================================
        # 13. RESPUESTA ESTRUCTURADA
        # ====================================================

        return {
            "status":
                "success",

            "route":
                "powerbi",

            "question":
                resolved_intent.get(
                    "original_question"
                ),

            "dashboard":
                resolved_dashboard,

            "semantic_model":
                semantic_model,

            "metric":
                metric_result.get(
                    "measure"
                ),

            "metric_type":
                resolved_intent.get(
                    "metric_type"
                ),

            "year":
                resolved_intent.get(
                    "year"
                ),

            "month":
                resolved_intent.get(
                    "month"
                ),

            "filters":
                combined_filters,

            "business_filters":
                business_filters,

            "value":
                value,

            "dax":
                validation_result.get(
                    "dax"
                ),

            "powerbi":
                powerbi_result
        }


    def close(self):

        if self.powerbi_provider:

            self.powerbi_provider.close()
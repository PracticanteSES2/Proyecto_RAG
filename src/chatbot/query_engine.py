import re
import unicodedata

class QueryEngine:

    def __init__(
        self,
        conversation_manager,
        master_metric_resolver,
        master_metric_dax_generator,
        metric_resolver,
        filter_resolver,
        business_filter_resolver,
        dax_generator,
        dax_validator,
        powerbi_provider,
        rag_answer_engine,
    ):

        self.conversation_manager = (
            conversation_manager
        )

        # Fuente principal de métricas
        self.master_metric_resolver = (
            master_metric_resolver
        )

        self.master_metric_dax_generator = (
            master_metric_dax_generator
        )

        # Fallback para compatibilidad mientras
        # terminamos de migrar todo al catálogo maestro.
        self.metric_resolver = (
            metric_resolver
        )

        self.filter_resolver = (
            filter_resolver
        )

        self.business_filter_resolver = (
            business_filter_resolver
        )

        self.dax_generator = (
            dax_generator
        )

        self.dax_validator = (
            dax_validator
        )

        self.powerbi_provider = (
            powerbi_provider
        )

        self.rag_answer_engine = (
            rag_answer_engine
        )

        # Estado de conversación para una ambigüedad
        # producida por MasterMetricResolver.
        self._pending_master_metric = None

    # ========================================================
    # ESTADO
    # ========================================================

    def reset(self):
        self._pending_master_metric = None

    # ========================================================
    # NORMALIZACIÓN
    # ========================================================

    def _normalize_text(
        self,
        value,
    ):
        if not value:
            return ""

        value = (
            str(value)
            .lower()
            .strip()
        )

        value = "".join(
            character
            for character in unicodedata.normalize(
                "NFD",
                value,
            )
            if unicodedata.category(
                character
            )
            != "Mn"
        )

        value = re.sub(
            r"[^a-z0-9\s]",
            " ",
            value,
        )

        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

    def _looks_like_new_question(
        self,
        message,
    ):
        text = self._normalize_text(
            message
        )

        if not text:
            return False

        question_terms = [
            "que ",
            "cual ",
            "cuales ",
            "cuanto ",
            "cuantos ",
            "cuantas ",
            "como ",
            "donde ",
            "cuando ",
            "por que ",
            "para que ",
        ]

        if any(
            text.startswith(term)
            for term in question_terms
        ):
            return True

        # Una respuesta a una aclaración suele ser corta:
        # "Cirugías", "Consultas prioritarias", etc.
        if len(text.split()) >= 6:
            return True

        return False
    # ========================================================
    # RESULTADO ESCALAR
    # ========================================================

    def _extract_value(
        self,
        powerbi_result,
    ):
        rows = powerbi_result.get(
            "rows",
            [],
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
            None,
        )

    # ========================================================
    # AMBIGÜEDAD MASTER METRIC
    # ========================================================

    def _build_master_clarification_question(
        self,
        options,
    ):
        options = [
            option
            for option in options
            if option
        ]

        if not options:
            return (
                "Encontré más de una métrica posible. "
                "¿Podrías precisar el tablero o servicio "
                "al que te refieres?"
            )

        if len(options) == 1:
            return (
                "Encontré más de una posibilidad. "
                f"¿Te refieres a {options[0]}?"
            )

        if len(options) == 2:
            options_text = (
                f"{options[0]} o "
                f"{options[1]}"
            )
        else:
            options_text = (
                ", ".join(
                    options[:-1]
                )
                + " o "
                + options[-1]
            )

        return (
            "Encontré este indicador en varios "
            "tableros. ¿Te refieres a "
            f"{options_text}?"
        )

    def _match_clarification_option(
        self,
        message,
        options,
    ):
        message_normalized = (
            self._normalize_text(
                message
            )
        )

        matches = []

        for option in options:

            option_normalized = (
                self._normalize_text(
                    option
                )
            )

            if not option_normalized:
                continue

            # Respuesta exacta o nombre del tablero
            # incluido dentro de la respuesta.
            if (
                option_normalized
                == message_normalized
                or option_normalized
                in message_normalized
            ):
                matches.append(
                    option
                )

                continue

            # Respuesta parcial con todas las palabras
            # principales del mensaje presentes
            # en la opción.
            message_tokens = {
                token
                for token
                in message_normalized.split()
                if len(token) >= 3
            }

            option_tokens = set(
                option_normalized.split()
            )

            if (
                message_tokens
                and message_tokens
                <= option_tokens
            ):
                matches.append(
                    option
                )

        # Solo resolvemos automáticamente
        # si hay una única coincidencia.
        if len(matches) == 1:
            return matches[0]

        return None

    def _handle_pending_master_clarification(
        self,
        message,
    ):
        pending = (
            self._pending_master_metric
        )

        if pending is None:
            return None

        options = pending.get(
            "options",
            [],
        )

        selected_dashboard = (
            self._match_clarification_option(
                message,
                options,
            )
        )

        if not selected_dashboard:
            return {
                "status":
                    "needs_clarification",
                "route":
                    "clarification",
                "question":
                    self._build_master_clarification_question(
                        options
                    ),
                "clarification_type":
                    "master_metric_dashboard",
                "clarification_options":
                    options,
            }

        original_intent = (
            pending.get(
                "intent_result",
                {},
            ).copy()
        )

        original_question = (
            original_intent.get(
                "original_question"
            )
            or ""
        )

        metric_result = (
            self.master_metric_resolver
            .resolve(
                question=
                    original_question,
                dashboard=
                    selected_dashboard,
            )
        )

        if (
            metric_result.get(
                "status"
            )
            != "resolved"
        ):
            # Conservamos el estado si aún
            # necesita más precisión.
            return {
                "status":
                    "needs_clarification",
                "route":
                    "clarification",
                "question":
                    (
                        "Aún encontré más de una métrica "
                        "posible dentro de ese tablero. "
                        "¿Podrías precisar el indicador?"
                    ),
                "clarification_type":
                    "master_metric_internal",
                "details":
                    metric_result,
            }

        original_intent[
            "dashboard"
        ] = selected_dashboard

        self._pending_master_metric = None

        return {
            "status":
                "resolved",
            "intent_result":
                original_intent,
            "master_result":
                metric_result,
        }

    # ========================================================
    # FILTROS
    # ========================================================

    def _resolve_filters(
        self,
        intent_result,
        dashboard,
        semantic_model,
    ):
        resolved_intent = (
            intent_result.copy()
        )

        resolved_intent[
            "dashboard"
        ] = dashboard

        temporal_result = (
            self.filter_resolver
            .resolve(
                resolved_intent
            )
        )

        if (
            temporal_result.get(
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
                    temporal_result,
            }

        business_result = (
            self.business_filter_resolver
            .resolve(
                question=(
                    resolved_intent.get(
                        "original_question"
                    )
                    or ""
                ),
                dashboard=
                    dashboard,
                semantic_model=
                    semantic_model,
            )
        )

        if (
            business_result.get(
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
                    business_result,
            }

        temporal_filters = (
            temporal_result.get(
                "filters",
                [],
            )
        )

        business_filters = (
            business_result.get(
                "filters",
                [],
            )
        )

        combined_filters = (
            temporal_filters
            + business_filters
        )

        return {
            "status":
                "resolved",
            "intent":
                resolved_intent,
            "filters":
                combined_filters,
            "business_filters":
                business_filters,
            "filter_result": {
                "status":
                    "resolved",
                "filters":
                    combined_filters,
                "problems":
                    [],
            },
        }

    def _get_master_clarification_options(
        self,
        master_result,
    ):

        options = master_result.get(
            "clarification_options",
            [],
        )

        if options:
            return options

        candidates = master_result.get(
            "candidates",
            [],
        )

        dashboards = []

        for candidate in candidates:

            for dashboard in candidate.get(
                "candidate_dashboards",
                [],
            ):

                if (
                    dashboard
                    and dashboard not in dashboards
                ):
                    dashboards.append(
                        dashboard
                    )

        if len(dashboards) > 1:
            return dashboards[:6]

        metrics = []

        for candidate in candidates:

            label = candidate.get(
                "label"
            )

            if (
                label
                and label not in metrics
            ):
                metrics.append(
                    label
                )

        return metrics[:6]

    # ========================================================
    # EJECUTAR MASTER METRIC
    # ========================================================

    def _execute_master_metric(
        self,
        intent_result,
        master_result,
    ):
        metric = master_result.get(
            "metric",
            {},
        )

        dashboard = (
            master_result.get(
                "resolved_dashboard"
            )
            or metric.get(
                "dashboard"
            )
        )

        # En medidas explícitas el dashboard puede estar
        # solamente dentro de appearances.
        if not dashboard:

            appearances = metric.get(
                "appearances",
                [],
            )

            if appearances:
                dashboard = (
                    appearances[0]
                    .get(
                        "page_display_name"
                    )
                )

        semantic_model = (
            metric.get(
                "semantic_model"
            )
            or
            self.powerbi_provider
            .default_semantic_model
        )

        filters_bundle = (
            self._resolve_filters(
                intent_result=
                    intent_result,
                dashboard=
                    dashboard,
                semantic_model=
                    semantic_model,
            )
        )

        if (
            filters_bundle.get(
                "status"
            )
            != "resolved"
        ):
            return filters_bundle

        dax_result = (
            self.master_metric_dax_generator
            .generate(
                metric=
                    metric,
                filter_result=
                    filters_bundle[
                        "filter_result"
                    ],
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
                    "master_metric_dax",
                "details":
                    dax_result,
            }

        # La expresión fue leída de master_metrics.json
        # y solo se ejecutan métricas approved.
        powerbi_result = (
            self.powerbi_provider
            .execute_dax(
                dax=
                    dax_result.get(
                        "dax"
                    ),
                semantic_model=
                    semantic_model,
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
                    "powerbi_master_metric",
                "details":
                    powerbi_result,
            }

        value = self._extract_value(
            powerbi_result
        )

        resolved_intent = (
            filters_bundle[
                "intent"
            ]
        )

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
                dashboard,
            "semantic_model":
                semantic_model,
            "metric":
                metric.get(
                    "label"
                ),
            "metric_id":
                metric.get(
                    "metric_id"
                ),
            "metric_type":
                resolved_intent.get(
                    "metric_type"
                ),
            "metric_source":
                metric.get(
                    "source_type"
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
                filters_bundle[
                    "filters"
                ],
            "business_filters":
                filters_bundle[
                    "business_filters"
                ],
            "value":
                value,
            "dax":
                dax_result.get(
                    "dax"
                ),
            "powerbi":
                powerbi_result,
        }

    # ========================================================
    # FALLBACK LEGACY
    # ========================================================

    def _execute_legacy_metric(
        self,
        intent_result,
    ):
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
            != "resolved"
        ):
            return {
                "status":
                    "metric_not_resolved",
                "stage":
                    "metric",
                "details":
                    metric_result,
            }

        dashboard = (
            intent_result.get(
                "dashboard"
            )
            or metric_result.get(
                "dashboard"
            )
        )

        semantic_model = (
            metric_result.get(
                "semantic_model"
            )
            or
            self.powerbi_provider
            .default_semantic_model
        )

        filters_bundle = (
            self._resolve_filters(
                intent_result=
                    intent_result,
                dashboard=
                    dashboard,
                semantic_model=
                    semantic_model,
            )
        )

        if (
            filters_bundle.get(
                "status"
            )
            != "resolved"
        ):
            return filters_bundle

        dax_result = (
            self.dax_generator
            .generate(
                metric_result,
                filters_bundle[
                    "filter_result"
                ],
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
                    dax_result,
            }

        validation_result = (
            self.dax_validator
            .validate(
                dax_result,
                metric_result,
                filters_bundle[
                    "filter_result"
                ],
            )
        )

        if not validation_result.get(
            "valid",
            False,
        ):
            return {
                "status":
                    "dax_rejected",
                "stage":
                    "dax_validator",
                "details":
                    validation_result,
            }

        powerbi_result = (
            self.powerbi_provider
            .execute_validated(
                validation_result,
                semantic_model=
                    semantic_model,
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
                    powerbi_result,
            }

        value = self._extract_value(
            powerbi_result
        )

        resolved_intent = (
            filters_bundle[
                "intent"
            ]
        )

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
                dashboard,
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
            "metric_source":
                "legacy_explicit_measure",
            "year":
                resolved_intent.get(
                    "year"
                ),
            "month":
                resolved_intent.get(
                    "month"
                ),
            "filters":
                filters_bundle[
                    "filters"
                ],
            "business_filters":
                filters_bundle[
                    "business_filters"
                ],
            "value":
                value,
            "dax":
                validation_result.get(
                    "dax"
                ),
            "powerbi":
                powerbi_result,
        }

    # ========================================================
    # PROCESS
    # ========================================================

    def process(
        self,
        message,
    ):

# ----------------------------------------------------
# 0. ¿HAY ACLARACIÓN MASTER PENDIENTE?
# ----------------------------------------------------

        if (
            self._pending_master_metric
            is not None
        ):

            # Si el usuario escribió una pregunta nueva,
            # abandonamos la aclaración anterior.
            if self._looks_like_new_question(
                message
            ):
                self._pending_master_metric = None

            else:
                pending_result = (
                    self._handle_pending_master_clarification(
                        message
                    )
                )

                if pending_result:

                    if (
                        pending_result.get(
                            "status"
                        )
                        == "needs_clarification"
                    ):
                        return pending_result

                    intent_result = (
                        pending_result[
                            "intent_result"
                        ]
                    )

                    master_result = (
                        pending_result[
                            "master_result"
                        ]
                    )

                    return (
                        self._execute_master_metric(
                            intent_result,
                            master_result,
                        )
                    )



        # ----------------------------------------------------
        # 1. INTENCIÓN + CONVERSACIÓN NORMAL
        # ----------------------------------------------------

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
                    intent_result,
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
                    intent_result,
            }

        intent = intent_result.get(
            "intent"
        )

        # ----------------------------------------------------
        # 2. RAG
        # ----------------------------------------------------

        if intent in [
            "describe_dashboard",
            "get_filters",
            "general_question",
        ]:

            rag_result = (
                self.rag_answer_engine
                .answer(
                    intent_result
                )
            )

            if (
                rag_result.get(
                    "status"
                )
                == "not_found"
            ):
                return {
                    "status":
                        "not_found",
                    "route":
                        "out_of_scope",
                    "question":
                        intent_result.get(
                            "original_question"
                        ),
                    "dashboard":
                        None,
                    "answer":
                        rag_result.get(
                            "answer"
                        ),
                    "sources":
                        [],
                    "synthesis_mode":
                        "none",
                }

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
                        [],
                    ),
                "synthesis_mode":
                    rag_result.get(
                        "synthesis_mode"
                    ),
            }

        # ----------------------------------------------------
        # 3. MASTER METRICS = FUENTE PRINCIPAL
        # ----------------------------------------------------

        # IMPORTANTE:
        # En la primera resolución NO pasamos el dashboard heredado
        # por ConversationManager/IntentParser. Ese valor puede venir
        # de una consulta anterior y contaminar la selección.
        #
        # MasterMetricResolver debe inferir el dashboard directamente
        # desde la pregunta actual. Solo pasamos dashboard de forma
        # explícita después de que el usuario responda una contrapregunta.
        master_result = (
            self.master_metric_resolver
            .resolve(
                question=(
                    intent_result.get(
                        "original_question"
                    )
                    or message
                )
            )
        )

        master_status = (
            master_result.get(
                "status"
            )
        )

        if (
            master_status
            == "ambiguous"
        ):
            options = (
                self._get_master_clarification_options(
                    master_result
                )
            )

            self._pending_master_metric = {
                "intent_result":
                    intent_result.copy(),
                "options":
                    options,
                "master_result":
                    master_result,
            }

            return {
                "status":
                    "needs_clarification",
                "route":
                    "clarification",
                "question":
                    self._build_master_clarification_question(
                        options
                    ),
                "clarification_type":
                    "master_metric_dashboard",
                "clarification_options":
                    options,
                "details":
                    master_result,
            }

        if (
            master_status
            == "resolved"
        ):
            return (
                self._execute_master_metric(
                    intent_result,
                    master_result,
                )
            )

        # ----------------------------------------------------
        # 4. FALLBACK LEGACY
        # ----------------------------------------------------

        return (
            self._execute_legacy_metric(
                intent_result
            )
        )

    # ========================================================
    # CIERRE
    # ========================================================

    def close(self):
        if self.powerbi_provider:
            self.powerbi_provider.close()

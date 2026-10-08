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
        query_semantic_planner=None,
        source_router=None,
        query_plan_builder=None,
        query_plan_dax_generator=None,
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

        # Capa previa que separa:
        # métrica + dimensión + valor de dimensión.
        self.query_semantic_planner = (
            query_semantic_planner
        )

        # Enrutador Informe/Página -> Modelo semántico.
        self.source_router = (
            source_router
        )

        # Planner determinista de consultas numéricas.
        self.query_plan_builder = (
            query_plan_builder
        )

        self.query_plan_dax_generator = (
            query_plan_dax_generator
        )

        # Estado de conversación para una ambigüedad
        # producida por MasterMetricResolver.
        self._pending_master_metric = None
        self._pending_query_plan = None
        self._pending_dashboard_clarification = None

    # ========================================================
    # ESTADO
    # ========================================================

    def reset(self):
        self._pending_master_metric = None
        self._pending_query_plan = None
        self._pending_dashboard_clarification = None

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

        metric_question = (
            original_intent.get(
                "_metric_question"
            )
            or original_question
        )

        metric_result = (
            self.master_metric_resolver
            .resolve(
                question=
                    metric_question,
                dashboard=
                    selected_dashboard,
                semantic_model=
                    pending.get(
                        "semantic_model_hint"
                    ),
                report=
                    pending.get(
                        "report_hint"
                    ),
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

        try:
            temporal_result = (
                self.filter_resolver
                .resolve(
                    resolved_intent,
                    semantic_model=
                        semantic_model,
                    dashboard=
                        dashboard,
                )
            )
        except TypeError:
            # Compatibilidad con FilterResolver legacy.
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
                        "_filter_question"
                    )
                    or
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

        # Si el planner encontró un valor de dimensión, su dashboard
        # es una señal fuerte de contexto para esta consulta.
        if not dashboard:

            dimension_dashboards = []

            for item in intent_result.get(
                "_dimension_matches",
                [],
            ):
                value = item.get(
                    "dashboard"
                )

                if (
                    value
                    and value not in dimension_dashboards
                ):
                    dimension_dashboards.append(
                        value
                    )

            appearances = (
                metric.get(
                    "appearances",
                    [],
                )
                or []
            )

            appearance_dashboards = []

            for appearance in appearances:

                page = appearance.get(
                    "page_display_name"
                )

                if (
                    page
                    and page not in appearance_dashboards
                ):
                    appearance_dashboards.append(
                        page
                    )

            # Si la dimensión y las apariciones coinciden en una sola página,
            # usamos esa página.
            intersection = [
                value
                for value in dimension_dashboards
                if value in appearance_dashboards
            ]

            if len(intersection) == 1:
                dashboard = intersection[0]

            elif (
                len(dimension_dashboards) == 1
                and not appearance_dashboards
            ):
                dashboard = dimension_dashboards[0]

            elif len(appearance_dashboards) == 1:
                dashboard = appearance_dashboards[0]

            elif len(appearance_dashboards) > 1:

                self._pending_master_metric = {
                    "intent_result":
                        intent_result.copy(),
                    "options":
                        appearance_dashboards,
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
                            appearance_dashboards
                        ),
                    "clarification_type":
                        "master_metric_dashboard",
                    "clarification_options":
                        appearance_dashboards,
                }

        if not dashboard:

            return {
                "status":
                    "needs_clarification",
                "route":
                    "clarification",
                "question":
                    (
                        "Identifiqué el indicador, pero no pude "
                        "determinar con seguridad el tablero o "
                        "servicio donde debe consultarse."
                    ),
                "clarification_type":
                    "metric_context",
                "metric":
                    metric.get(
                        "label"
                    ),
            }

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
            "report":
                (
                    master_result.get(
                        "resolved_report"
                    )
                    or metric.get(
                        "report"
                    )
                    or (
                        metric.get(
                            "reports",
                            [],
                        )[0]
                        if metric.get(
                            "reports",
                            [],
                        )
                        else None
                    )
                ),
            "source_context":
                intent_result.get(
                    "_source_context"
                ),
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
            "dimension_matches":
                resolved_intent.get(
                    "_dimension_matches",
                    [],
                ),
            "metric_question":
                resolved_intent.get(
                    "_metric_question"
                ),
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

        try:
            validation_result = (
                self.dax_validator
                .validate(
                    dax_result,
                    metric_result,
                    filters_bundle[
                        "filter_result"
                    ],
                    semantic_model=
                        semantic_model,
                )
            )
        except TypeError:
            # Compatibilidad con DAXValidator legacy.
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
            "source_context":
                resolved_intent.get(
                    "_source_context"
                ),
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
    # QUERY PLAN DETERMINISTA
    # ========================================================

    def _row_value(self, row):
        if not row:
            return None

        for key, value in row.items():
            if "__value" in str(key).lower():
                return value

        return next(iter(row.values()), None)

    def _format_grouped_answer(self, plan, rows):
        if not rows:
            return (
                "La consulta se ejecutó correctamente, "
                "pero no devolvió filas."
            )

        groups = plan.get("group_by", []) or []
        metric_label = plan.get("metric", {}).get("label") or "Resultado"
        headers = [
            item.get("label") or item.get("column")
            for item in groups
        ] + [metric_label]

        table_rows = []
        for row in rows[:50]:
            values = []
            for group in groups:
                column = str(group.get("column") or "").lower()
                selected = None
                for key, value in row.items():
                    key_norm = str(key).lower()
                    if column and column in key_norm and "__value" not in key_norm:
                        selected = value
                        break
                values.append(selected)
            values.append(self._row_value(row))
            table_rows.append(values)

        def clean(value):
            if value is None:
                return ""
            return str(value).replace("|", "\\|")

        lines = [
            "| " + " | ".join(clean(value) for value in headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        lines.extend(
            "| " + " | ".join(clean(value) for value in row) + " |"
            for row in table_rows
        )
        if len(rows) > len(table_rows):
            lines.append("")
            lines.append(f"Mostrando {len(table_rows)} de {len(rows)} filas.")
        return "\n".join(lines)

    @staticmethod
    def _is_blank_value(value):
        if value is None:
            return True
        if isinstance(value, float) and value != value:
            return True
        return str(value).strip().upper() in ("", "BLANK", "NONE", "NAN", "NULL")

    def _execute_query_plan(self, plan):
        dax_result = self.query_plan_dax_generator.generate(plan)
        if dax_result.get("status") != "generated":
            return {
                "status": "dax_not_generated",
                "route": "powerbi",
                "stage": "query_plan_dax",
                "query_plan": plan,
                "details": dax_result,
            }

        powerbi_result = self.powerbi_provider.execute_dax(
            dax=dax_result.get("dax"),
            semantic_model=plan.get("semantic_model"),
        )
        if powerbi_result.get("status") != "success":
            return {
                "status": "powerbi_error",
                "route": "powerbi",
                "stage": "query_plan_powerbi",
                "query_plan": plan,
                "dax": dax_result.get("dax"),
                "details": powerbi_result,
            }

        rows = powerbi_result.get("rows", []) or []
        mode = plan.get("mode", "scalar")
        # ROW() siempre devuelve una fila: BLANK/None/"" también es vacío.
        if mode == "scalar" and rows and all(
            self._is_blank_value(value) for value in (rows[0] or {}).values()
        ):
            rows = []
        if not rows and mode == "scalar":
            return {
                "status": "empty_result", "route": "powerbi",
                "stage": "query_plan_result", "query_plan": plan,
                "dax": dax_result.get("dax"),
                "details": powerbi_result,
            }
        value = None
        answer = None

        total_rows = len(rows)
        if mode == "grouped":
            answer = self._format_grouped_answer(plan, rows)
        elif rows:
            value = self._row_value(rows[0])

        metric = plan.get("metric", {})
        return {
            "status": "success",
            "route": "powerbi",
            "result_type": "table" if mode == "grouped" else "scalar",
            "question": plan.get("question"),
            "report": plan.get("report"),
            "dashboard": plan.get("dashboard"),
            "semantic_model": plan.get("semantic_model"),
            "metric": metric.get("label"),
            "metric_id": metric.get("metric_id"),
            "metric_source": metric.get("source_type"),
            "value": value,
            "rows": rows,
            "filters": plan.get("filters", []),
            "business_filters": [
                item for item in plan.get("filters", [])
                if item.get("type") == "categorical"
            ],
            "group_by": plan.get("group_by", []),
            "answer": answer,
            "total_rows": total_rows,
            "metric_format": metric.get("format_string") or metric.get("format"),
            "unapplied_terms": plan.get("unapplied_terms") or [],
            "dax": dax_result.get("dax"),
            "powerbi": powerbi_result,
            "query_plan": plan,
            "source_context": plan.get("source_context"),
        }

    # ========================================================
    # ACLARACIONES DE MÉTRICAS EN QUERY PLAN
    # ========================================================

    _CLARIFICATION_MARGIN = 0.35
    _CLARIFICATION_MAX_OPTIONS = 6
    _CLARIFICATION_STOPWORDS = {
        "los", "las", "una", "uno", "del", "que", "con", "por", "para",
        "esa", "ese", "esta", "este", "quiero", "opcion", "numero", "tablero",
        "informe", "modelo", "pagina", "reporte", "dato", "datos",
    }

    def _clarification_context(self, metric):
        """Reporte, página y modelo con los que se distingue una opción."""
        appearances = metric.get("appearances", []) or []
        reports = metric.get("reports", []) or []
        report = (
            metric.get("report")
            or (reports[0] if reports else None)
            or next((a.get("report") for a in appearances if a.get("report")), None)
        )
        page = metric.get("dashboard") or next(
            (a.get("page_display_name") for a in appearances if a.get("page_display_name")),
            None,
        )
        return (
            str(report).strip() if report else "",
            str(page).strip() if page else "",
            str(metric.get("semantic_model") or "").strip(),
        )

    def _build_clarification_choices(self, raw_candidates):
        scored = []
        seen_ids = set()
        for item in raw_candidates:
            metric = item.get("metric", {}) or {}
            metric_id = metric.get("metric_id")
            label = str(metric.get("label") or "").strip()
            if not label or not metric_id or metric_id in seen_ids:
                continue
            seen_ids.add(metric_id)
            scored.append((float(item.get("score") or 0.0), metric))
        if not scored:
            return []
        best = max(score for score, _ in scored)
        scored = [
            pair for pair in scored
            if best - pair[0] <= self._CLARIFICATION_MARGIN
        ][: self._CLARIFICATION_MAX_OPTIONS]

        choices = []
        for _, metric in scored:
            report, page, model = self._clarification_context(metric)
            title = next(
                (
                    str(a.get("visual_title")).strip()
                    for a in metric.get("appearances", []) or []
                    if a.get("visual_title")
                    and self._normalize_text(a.get("visual_title"))
                    == self._normalize_text(metric.get("label"))
                ),
                str(metric.get("label")).strip(),
            )
            where = " › ".join(part for part in (report, page) if part)
            detail = " · ".join(part for part in (where, model) if part)
            choices.append({
                "id": metric.get("metric_id"),
                "label": title,
                "detail": detail,
                "description": str(metric.get("description") or "").strip(),
                "_parts": [report, page, model, str(metric.get("measure") or "").strip()],
            })

        # Etiquetas distinguibles: se agregan reporte/página/modelo
        # progresivamente solo mientras existan duplicados.
        for index in range(4):
            groups = {}
            for choice in choices:
                groups.setdefault(choice["label"].casefold(), []).append(choice)
            duplicated = [group for group in groups.values() if len(group) > 1]
            if not duplicated:
                break
            for group in duplicated:
                for choice in group:
                    part = choice["_parts"][index]
                    if part and part.casefold() not in choice["label"].casefold():
                        choice["label"] = f"{choice['label']} — {part}"
        groups = {}
        for choice in choices:
            groups.setdefault(choice["label"].casefold(), []).append(choice)
        for group in groups.values():
            if len(group) > 1:
                for number, choice in enumerate(group, 1):
                    choice["label"] = f"{choice['label']} ({number})"
        for choice in choices:
            choice.pop("_parts", None)
        return choices

    def _clarification_response(self, choices, question=None):
        lines = []
        for index, choice in enumerate(choices, 1):
            line = f"{index}. {choice['label']}"
            if choice.get("detail") and choice["detail"] not in choice["label"]:
                line += f" ({choice['detail']})"
            lines.append(line)
        return {
            "status": "needs_clarification", "route": "clarification",
            "clarification_type": "query_plan_metric",
            "question": (question or "Encontré varios indicadores. ¿Cuál necesitas?")
            + "\n\n" + "\n".join(lines),
            "clarification_options": [dict(choice) for choice in choices],
        }

    def _query_plan_clarification(self, plan):
        raw_candidates = plan.get("metric_resolution", {}).get("candidates", [])
        choices = self._build_clarification_choices(raw_candidates)
        if not choices:
            return {
                "status": "metric_not_resolved", "route": "powerbi",
                "stage": "query_plan_metric", "query_plan": plan,
            }
        self._pending_query_plan = {
            "type": "query_plan_metric",
            "question": plan.get("question"),
            "intent": plan.get("intent"),
            "choices": choices,
        }
        response = self._clarification_response(choices)
        response["query_plan"] = plan
        return response

    def _run_selected_metric(self, pending, choice):
        self._pending_query_plan = None
        plan = self.query_plan_builder.build(
            pending["question"], selected_metric_id=choice["id"]
        )
        if plan.get("status") == "ready":
            return self._execute_query_plan(plan)
        return self._query_plan_failure(plan)

    def select_clarification_option(self, option_id):
        """Resuelve una contrapregunta pendiente con la opción elegida (botón)."""
        unavailable = {
            "status": "error", "route": "clarification",
            "stage": "select_option",
            "error": "La opción elegida ya no está disponible.",
        }
        pending = self._pending_query_plan
        if pending is not None:
            choice = next(
                (c for c in pending["choices"] if str(c["id"]) == str(option_id)),
                None,
            )
            if choice is None:
                return unavailable
            return self._run_selected_metric(pending, choice)

        dashboard_pending = self._pending_dashboard_clarification
        if dashboard_pending is not None:
            choice = next(
                (c for c in dashboard_pending["choices"] if str(c["id"]) == str(option_id)),
                None,
            )
            if choice is None:
                return unavailable
            self._pending_dashboard_clarification = None
            select = getattr(self.conversation_manager, "select_dashboard", None)
            if callable(select):
                select(choice["id"])
            return self.process(dashboard_pending["question"])

        return {
            "status": "error", "route": "clarification",
            "stage": "select_option",
            "error": "No hay una aclaración pendiente.",
        }

    def _match_query_plan_choice(self, message, choices):
        """Devuelve la opción elegida por un mensaje escrito, o None."""
        norm = self._normalize_text(message)
        if not norm:
            return None

        number = re.fullmatch(
            r"(?:(?:la|el|opcion|numero|num|no|n)\s+)*(\d{1,2})(?:\s+(?:opcion|por favor))?",
            norm,
        )
        if number:
            index = int(number.group(1))
            return choices[index - 1] if 1 <= index <= len(choices) else None

        exact = [c for c in choices if self._normalize_text(c["label"]) == norm]
        if len(exact) == 1:
            return exact[0]

        contained = [
            c for c in choices
            if len(norm) >= 4 and (
                norm in self._normalize_text(c["label"])
                or self._normalize_text(c["label"]) in norm
            )
        ]
        if len(contained) == 1:
            return contained[0]

        # Palabras del reporte / página / modelo que distinguen una opción.
        def tokens(text):
            return {
                token for token in self._normalize_text(text).split()
                if len(token) >= 3 and token not in self._CLARIFICATION_STOPWORDS
            }

        option_tokens = [
            tokens(f"{c['label']} {c.get('detail') or ''}") for c in choices
        ]
        message_tokens = tokens(norm)
        scores = []
        for position, current in enumerate(option_tokens):
            others = [
                t for other, t in enumerate(option_tokens) if other != position
            ]
            informative = {
                t for t in current
                if t in message_tokens and not all(t in other for other in others)
            }
            exclusive = {
                t for t in informative if not any(t in other for other in others)
            }
            scores.append((len(exclusive), len(informative)))
        best = max(scores, default=(0, 0))
        if best[1] > 0 and scores.count(best) == 1:
            return choices[scores.index(best)]
        return None

    def _continue_query_plan(self, message):
        pending = self._pending_query_plan
        if pending is None:
            return None
        choices = pending["choices"]
        # Primero intentar emparejar una opción: una respuesta larga puede
        # ser una opción y no una pregunta nueva.
        selected = self._match_query_plan_choice(message, choices)
        if selected is None:
            if self._looks_like_new_question(message):
                self._pending_query_plan = None
                return None
            return self._clarification_response(
                choices,
                "Indica el número o el nombre de la opción correspondiente.",
            )
        return self._run_selected_metric(pending, selected)

    def _query_plan_failure(self, plan):
        if plan.get("status") == "ambiguous":
            return self._query_plan_clarification(plan)
        if plan.get("status") == "unsupported_filter":
            return {
                "status": "unsupported_filter", "route": "powerbi",
                "stage": plan.get("stage"), "details": plan,
                "query_plan": plan,
                "powerbi_unavailable": bool(plan.get("domain_error")),
            }
        return {
            "status": "metric_not_resolved", "route": "powerbi",
            "stage": "query_plan_metric", "query_plan": plan,
            "details": plan.get("metric_resolution"),
        }

    # ========================================================
    # PROCESS
    # ========================================================

    def process(
        self,
        message,
    ):
        if self._pending_query_plan is not None:
            response = self._continue_query_plan(message)
            if response is not None:
                return response


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
        # 1. QUERY PLAN ANTES DEL PARSER LEGACY
        # ----------------------------------------------------
        #
        # El IntentParser histórico exige dashboard/tipo de métrica en
        # ciertos casos. El Query Plan ya puede resolver eso directamente
        # desde master_metrics + visual catalog, así que una consulta
        # cuantitativa debe pasar primero por esta capa.

        if self.query_plan_builder and self.query_plan_dax_generator:
            try:
                early_numeric = self.query_plan_builder.looks_numeric(
                    message,
                    dashboard=None,
                )
            except Exception:
                early_numeric = False

            if early_numeric:
                early_intent = {
                    "status": "ready",
                    "intent": "query_metric",
                    "dashboard": None,
                    "metric_type": None,
                    "year": None,
                    "month": None,
                    "original_question": message,
                }

                try:
                    early_plan = self.query_plan_builder.build(
                        question=message,
                        intent_result=early_intent,
                    )
                except Exception as error:
                    return {
                        "status": "error",
                        "route": "powerbi",
                        "stage": "query_plan_early",
                        "error": f"{type(error).__name__}: {error}",
                    }

                if early_plan.get("status") == "ready":
                    return self._execute_query_plan(early_plan)

                return self._query_plan_failure(early_plan)

        # ----------------------------------------------------
        # 2. INTENCIÓN + CONVERSACIÓN NORMAL
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
            clarification = {
                "status":
                    "needs_clarification",
                "route":
                    "clarification",
                "question":
                    intent_result.get("question")
                    or intent_result.get("clarification_question"),
                "intent":
                    intent_result,
            }
            dashboards = [
                str(name) for name in intent_result.get("candidates") or []
                if name
            ]
            self._pending_dashboard_clarification = None
            if dashboards and "dashboard" in (
                intent_result.get("missing_fields") or []
            ):
                options = [
                    {"id": name, "label": name, "detail": "", "description": ""}
                    for name in dashboards
                ]
                self._pending_dashboard_clarification = {
                    "question": (
                        (intent_result.get("state") or {}).get("original_question")
                        or message
                    ),
                    "choices": options,
                }
                clarification["clarification_type"] = "dashboard"
                clarification["clarification_options"] = [
                    dict(option) for option in options
                ]
            return clarification

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
        # 2. QUERY PLAN NUMÉRICO DETERMINISTA
        # ----------------------------------------------------

        original_question = (
            intent_result.get("original_question")
            or message
        )

        should_try_query_plan = False

        if self.query_plan_builder and self.query_plan_dax_generator:
            if intent in ("query_metric", "compare_metric"):
                should_try_query_plan = True
            elif intent == "general_question":
                try:
                    should_try_query_plan = self.query_plan_builder.looks_numeric(
                        original_question,
                        dashboard=intent_result.get("dashboard"),
                    )
                except Exception:
                    should_try_query_plan = False

        if should_try_query_plan:
            try:
                query_plan = self.query_plan_builder.build(
                    question=original_question,
                    intent_result=intent_result,
                )
            except Exception as error:
                return {
                    "status": "error",
                    "route": "powerbi",
                    "stage": "query_plan",
                    "error": f"{type(error).__name__}: {error}",
                }

            plan_status = query_plan.get("status")

            if plan_status == "ready":
                return self._execute_query_plan(query_plan)

            return self._query_plan_failure(query_plan)

        # ----------------------------------------------------
        # 3. RAG DOCUMENTAL
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
        # Primero separamos la pregunta en:
        #   - pregunta para resolver la métrica
        #   - valores de dimensiones/filtros de negocio
        #
        # Ejemplo:
        # "¿Cuántas cirugías plásticas se han realizado?"
        #   -> métrica: cirugías realizadas
        #   -> filtro: ESPECIALIDAD = CIRUGIA PLASTICA

        original_question = (
            intent_result.get(
                "original_question"
            )
            or message
        )

        metric_question = (
            original_question
        )

        source_context = {
            "status":
                "unresolved",
        }

        if self.source_router:
            try:
                source_context = (
                    self.source_router
                    .resolve(
                        question=
                            original_question,
                        dashboard=
                            intent_result.get(
                                "dashboard"
                            ),
                    )
                )
            except Exception as error:
                source_context = {
                    "status":
                        "error",
                    "error":
                        (
                            f"{type(error).__name__}: "
                            f"{error}"
                        ),
                }

        intent_result[
            "_source_context"
        ] = source_context

        strong_source_context = (
            source_context.get(
                "status"
            )
            == "resolved"
            and source_context.get(
                "routing_strength"
            )
            == "strong"
        )

        # IMPORTANTE:
        # una página detectada por palabras como "urgencias" NO debe
        # fijar el modelo antes de resolver la métrica. "Urgencias"
        # puede ser SERVICIO = URGENCIAS.
        semantic_model_hint = (
            source_context.get(
                "semantic_model"
            )
            if strong_source_context
            else None
        )

        report_hint = (
            source_context.get(
                "report"
            )
            if strong_source_context
            else None
        )

        if self.query_semantic_planner:

            try:

                semantic_plan = (
                    self.query_semantic_planner
                    .plan(
                        question=
                            original_question,
                        semantic_model=
                            semantic_model_hint,
                        report=
                            report_hint,
                    )
                )

                metric_question = (
                    semantic_plan.get(
                        "metric_question"
                    )
                    or original_question
                )

                intent_result[
                    "_metric_question"
                ] = metric_question

                intent_result[
                    "_filter_question"
                ] = (
                    semantic_plan.get(
                        "filter_question"
                    )
                    or original_question
                )

                intent_result[
                    "_dimension_matches"
                ] = (
                    semantic_plan.get(
                        "dimension_matches",
                        [],
                    )
                )

            except Exception as error:

                # Fallback seguro: una falla del planner no debe tumbar
                # todo el chat. El resolver tradicional sigue disponible.
                intent_result[
                    "_semantic_plan_error"
                ] = (
                    f"{type(error).__name__}: "
                    f"{error}"
                )

                intent_result[
                    "_metric_question"
                ] = original_question

                intent_result[
                    "_filter_question"
                ] = original_question

                intent_result[
                    "_dimension_matches"
                ] = []

        else:

            intent_result[
                "_metric_question"
            ] = original_question

            intent_result[
                "_filter_question"
            ] = original_question

            intent_result[
                "_dimension_matches"
            ] = []

        # En la primera resolución NO pasamos un dashboard heredado
        # del ConversationManager. MasterMetricResolver debe inferirlo
        # desde la pregunta métrica actual.
        master_result = (
            self.master_metric_resolver
            .resolve(
                question=
                    metric_question,
                semantic_model=
                    semantic_model_hint,
                report=
                    report_hint,
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
                "semantic_model_hint":
                    semantic_model_hint,
                "report_hint":
                    report_hint,
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

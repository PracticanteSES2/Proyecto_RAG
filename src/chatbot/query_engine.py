import re
import unicodedata

from src.chatbot.intent_parser import ordinal_choice_index
from src.chatbot.reasoning_trace import ReasoningTrace, format_score, short
from src.chatbot.response_formatter import NONE_OF_THE_ABOVE_ID, format_value_es

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
        option_describer=None,
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

        # LLM que describe en una frase qué consultaría cada opción de una
        # contrapregunta. Sin él se usa la descripción del catálogo.
        self.option_describer = option_describer

        # Razonamiento del turno en curso y del último turno terminado.
        self._trace = None
        self.last_reasoning = None

        # Estado de conversación para una ambigüedad
        # producida por MasterMetricResolver.
        self._pending_master_metric = None
        self._pending_query_plan = None
        self._pending_dashboard_clarification = None

        # Última consulta numérica exitosa (pregunta + indicador + filtros +
        # agrupación). Permite seguimientos como «¿y en 2025?». Sobrevive a
        # reset() (app.py lo llama tras cada respuesta final) y solo se borra
        # con reset(full=True) («Nueva conversación») o tras una respuesta
        # final que no sea un dato de Power BI.
        self._last_success = None

    # ========================================================
    # ESTADO
    # ========================================================

    def reset(self, full=False):
        """Limpia las contrapreguntas pendientes. Con full=True («Nueva
        conversación») también olvida el contexto de seguimiento."""
        self._pending_master_metric = None
        self._pending_query_plan = None
        self._pending_dashboard_clarification = None
        if full:
            self._last_success = None

    # ========================================================
    # RAZONAMIENTO (qué revisó y por qué decidió)
    # ========================================================

    def _think(self, title, *lines):
        if self._trace is not None:
            self._trace.add(title, *lines)

    def _traced(self, kind, text, runner):
        """Ejecuta un turno registrando su razonamiento en result["reasoning"]."""
        if self._trace is not None:
            return runner()  # turno anidado (p. ej. tablero elegido -> process)
        self._trace = ReasoningTrace(kind, text)
        try:
            result = runner()
            if isinstance(result, dict):
                self._think(
                    "Resultado del turno",
                    f"estado={result.get('status')} · ruta={result.get('route')}"
                    + (f" · etapa={result.get('stage')}" if result.get("stage") else ""),
                    f"error: {result.get('error')}" if result.get("error") else None,
                )
                result["reasoning"] = self._trace.to_dict()
            self.last_reasoning = self._trace.to_dict()
            return result
        except Exception as error:
            self._think("Error inesperado", f"{type(error).__name__}: {error}")
            self.last_reasoning = self._trace.to_dict()
            raise
        finally:
            self._trace = None

    @staticmethod
    def _metric_where(metric):
        appearances = metric.get("appearances") or []
        reports = metric.get("reports") or []
        report = metric.get("report") or (reports[0] if reports else None) or next(
            (a.get("report") for a in appearances if a.get("report")), None
        )
        pages = []
        for appearance in appearances:
            page = appearance.get("page_display_name")
            if page and page not in pages:
                pages.append(page)
        where = " › ".join(part for part in (report, ", ".join(pages[:3])) if part)
        return where or "sin informe"

    def _candidate_line(self, item):
        metric = item.get("metric") or {}
        line = (
            f"{metric.get('label')} [{metric.get('metric_id')}] · {self._metric_where(metric)}"
            f" · modelo {metric.get('semantic_model') or '-'}"
            f" · puntaje {format_score(item.get('score'))}"
        )
        if item.get("business_score") is not None:
            line += f" (por nombre {format_score(item.get('business_score'))})"
        if item.get("matched_name"):
            line += f" · coincidió con «{item.get('matched_name')}»"
        return line

    @staticmethod
    def _filter_line(item):
        if item.get("type") == "date_range":
            period = item.get("label") or "-".join(
                str(v) for v in (item.get("year"), item.get("month")) if v
            )
            column = f"{item.get('table')}[{item.get('column')}]" if item.get("column") else ""
            if item.get("start") and item.get("end"):
                column += f" >= {item['start']} y < {item['end']}"
            elif item.get("months"):
                column += f" meses {item['months']} de todos los años"
            return f"periodo {period} · {column}".strip(" ·")
        if item.get("type") == "temporal_set":
            columns = " y ".join(f"{c.get('table')}[{c.get('column')}]" for c in item.get("columns") or [])
            pairs = ", ".join(f"{y}-{m:02d}" for y, m in item.get("values") or [])
            return f"periodo {item.get('label')} · ({columns}) en {pairs}"
        value = item.get("value") if item.get("value") is not None else item.get("values")
        line = f"{item.get('table')}[{item.get('column')}] = {value}"
        if item.get("temporal") and item.get("label"):
            line += f" (periodo {item.get('label')})"
        if item.get("source"):
            line += f" (origen {item.get('source')}"
            if item.get("match_score") is not None:
                line += f", coincidencia {format_score(item.get('match_score'))}"
            line += ")"
        if item.get("reason"):
            line += f" — por qué: {item['reason']}"
        return line

    def _trace_plan(self, plan, title="Query Plan"):
        if self._trace is None or not isinstance(plan, dict):
            return
        context = plan.get("source_context") or {}
        resolution = plan.get("metric_resolution") or {}
        lines = [
            f"estado del plan: {plan.get('status')}"
            + (f" (etapa {plan.get('stage')})" if plan.get("stage") else "")
        ]
        if context:
            lines.append("enrutamiento a tablero/modelo: " + ", ".join(
                f"{key}={context.get(key)}"
                for key in ("status", "routing_strength", "report", "semantic_model",
                            "dashboard", "reason")
                if context.get(key)
            ))
        for mention in context.get("board_mentions") or []:
            known = mention.get("contexts") or []
            lines.append(
                f"tablero nombrado: «{mention.get('phrase')}»"
                + (
                    " → " + "; ".join(sorted({
                        f"{item.get('report') or item.get('semantic_model')}"
                        + (f" › {item.get('dashboard')}" if item.get("dashboard") else "")
                        for item in known
                    }))
                    if known else " (nombre no reconocido)"
                )
                + " · sus palabras no se usan como filtro"
            )
        if context.get("board_mention_models") and context.get("status") != "resolved":
            lines.append(
                "el tablero nombrado existe en varios modelos ("
                + ", ".join(context["board_mention_models"]) + "): no se fija ninguno"
            )
        if context.get("board_note"):
            lines.append(f"tablero nombrado: {context['board_note']}")
        if resolution.get("status"):
            lines.append(f"resolución del indicador: {resolution.get('status')}")
        self._think(title, *lines)
        if plan.get("resolution_notes"):
            self._think("Decisiones al resolver el indicador", *plan["resolution_notes"])

        candidates = resolution.get("candidates") or []
        if candidates:
            self._think(
                "Indicadores evaluados (de mayor a menor puntaje)",
                *[self._candidate_line(item) for item in candidates[:8]],
                f"... y {len(candidates) - 8} más" if len(candidates) > 8 else None,
            )
        suggestions = resolution.get("suggestions") or []
        if suggestions:
            self._think(
                "Ninguno alcanzó el puntaje mínimo; indicadores que comparten palabras con la pregunta",
                *[self._candidate_line(item) for item in suggestions[:8]],
            )

        if plan.get("status") == "ready":
            metric = plan.get("metric") or {}
            match = plan.get("metric_match") or {}
            self._think(
                "Indicador elegido",
                f"{metric.get('label')} [{metric.get('metric_id')}] · {self._metric_where(metric)}",
                f"modelo semántico: {plan.get('semantic_model')}",
                f"medida/expresión: {metric.get('dax_expression') or metric.get('measure')}",
                f"coincidió con «{match.get('matched_name')}» (puntaje {format_score(match.get('score'))})"
                if match.get("matched_name") else None,
                f"interpretación: {match.get('interpretation')}" if match.get("interpretation") else None,
                f"modo: {plan.get('mode')}",
            )
            period = plan.get("period") or {}
            buckets = plan.get("temporal_buckets") or []
            self._think(
                "Filtros y agrupación",
                f"periodo interpretado: «{period.get('phrase')}» → {period.get('label')}"
                f" (referencia: hoy {period.get('today')})"
                if period.get("label") else None,
                *([f"filtro: {self._filter_line(item)}" for item in plan.get("filters") or []]
                  or ["sin filtros"]),
                *[f"agrupar por: {item.get('table')}[{item.get('column')}]"
                  for item in plan.get("group_by") or [] if not item.get("temporal")],
                *[f"agrupar por {str(item.get('label')).lower()}: {len(buckets)} periodos "
                  f"({buckets[0]['label']} … {buckets[-1]['label']})" if buckets else
                  f"agrupar por {str(item.get('label')).lower()}"
                  for item in plan.get("group_by") or [] if item.get("temporal")],
                *[f"no aplicado: {term}" for term in plan.get("unapplied_terms") or []],
                *[f"nota: {note}" for note in plan.get("notes") or []],
                *[f"valor implícito {decision}" for decision in plan.get("implicit_decisions") or []],
                "columnas del catálogo técnico (el indicador no aparece en ningún visual): "
                + ", ".join(plan["technical_columns_used"])
                if plan.get("technical_columns_used") else None,
            )
        elif plan.get("reason") or plan.get("unresolved_text"):
            dimension = plan.get("requested_dimension") or plan.get("dimension")
            self._think(
                "Por qué no se pudo armar la consulta",
                f"motivo: {plan.get('reason')}" if plan.get("reason") else None,
                f"palabras sin interpretar: «{plan.get('unresolved_text')}»"
                if plan.get("unresolved_text") else None,
                (
                    f"indicador descartado: {plan['rejected_metric'].get('label')} (coincidió con "
                    f"«{plan['rejected_metric'].get('matched_name')}», pero "
                    f"{plan['rejected_metric']['why']})"
                    if plan["rejected_metric"].get("why") else
                    f"indicador descartado: {plan['rejected_metric'].get('label')} (coincidió con "
                    f"«{plan['rejected_metric'].get('matched_name')}» solo por las palabras de la "
                    "agrupación o del filtro; ninguna palabra distintiva de la pregunta lo respalda)"
                )
                if plan.get("rejected_metric") else None,
                f"tablero nombrado: {plan.get('named_report')}" if plan.get("named_report") else None,
                f"valor pedido: {plan.get('requested_value')}" if plan.get("requested_value") else None,
                f"dimensión pedida: {dimension}" if dimension else None,
                f"periodo pedido: {plan.get('requested_period')}" if plan.get("requested_period") else None,
                *[f"no aplicado: {term}" for term in plan.get("unapplied_terms") or []],
                *[f"valor implícito {decision}" for decision in plan.get("implicit_decisions") or []],
                f"error de dominio: {plan.get('domain_error')}" if plan.get("domain_error") else None,
            )

    def _trace_dax(self, title, dax_result, powerbi_result=None):
        if self._trace is None:
            return
        lines = [f"generación DAX: {dax_result.get('status')}"]
        if dax_result.get("dax"):
            lines.append("DAX: " + " ".join(str(dax_result.get("dax")).split()))
        if dax_result.get("status") != "generated":
            lines.append(f"detalle: {short(dax_result, 300)}")
        if powerbi_result is not None:
            lines.append(f"Power BI: {powerbi_result.get('status')}")
            if powerbi_result.get("status") == "success":
                rows = powerbi_result.get("rows") or []
                lines.append(f"filas devueltas: {len(rows)}")
                if rows:
                    lines.append(f"primera fila: {short(rows[0], 200)}")
            else:
                lines.append(
                    f"error de Power BI: {short(powerbi_result.get('error') or powerbi_result, 300)}"
                )
        self._think(title, *lines)

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
            metric_value = self._row_value(row)
            formatted = format_value_es(
                metric_value,
                metric_label,
                plan.get("metric", {}).get("format_string"),
            )
            values.append(formatted if formatted is not None else metric_value)
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

    def _apply_ranking(self, plan, rows):
        """Orden y límite pedidos («top 5», «el servicio con más peso»).
        La DAX ya los aplica (TOPN/ORDER BY); aquí se garantiza el mismo
        resultado aunque el generador no soporte ranking."""
        ranking = plan.get("ranking") or {}
        if not ranking or not rows:
            return rows

        def key(row):
            value = self._row_value(row)
            try:
                return float(value)
            except (TypeError, ValueError):
                return float("-inf")

        ordered = sorted(rows, key=key, reverse=ranking.get("direction") != "asc")
        limit = ranking.get("limit")
        return ordered[: int(limit)] if limit else ordered

    def _execute_query_plan(self, plan):
        ranked_generator = (
            getattr(self.query_plan_dax_generator, "generate_ranked", None)
            if plan.get("ranking") else None
        )
        if plan.get("ranking"):
            ranking = plan["ranking"]
            self._think(
                "Ranking pedido en la pregunta",
                f"«{ranking.get('phrase')}»: orden "
                + ("de menor a mayor" if ranking.get("direction") == "asc" else "de mayor a menor")
                + (f", límite {ranking.get('limit')}" if ranking.get("limit") else ", sin límite"),
                "se agrupa por: " + ", ".join(
                    f"{item.get('table')}[{item.get('column')}]" for item in plan.get("group_by") or []
                ),
            )
        dax_result = (
            ranked_generator(plan) if callable(ranked_generator)
            else self.query_plan_dax_generator.generate(plan)
        )
        if dax_result.get("status") != "generated":
            self._trace_dax("Consulta a Power BI", dax_result)
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
        self._trace_dax("Consulta a Power BI", dax_result, powerbi_result)
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

        if mode == "grouped":
            rows = self._apply_ranking(plan, rows)
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

    @staticmethod
    def _short_text(text, limit=110):
        """Primera frase, cortada a `limit` caracteres."""
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if not text:
            return ""
        text = re.split(r"(?<=[.;])\s", text, maxsplit=1)[0].rstrip(".;").strip()
        if len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        return text

    def _choice_summary(self, label, description, report, page, limit=110):
        """Descripción corta de una opción sin repetir lo que ya dice su etiqueta."""
        label_tokens = set(self._normalize_text(label).split())

        def adds(text):
            tokens = set(self._normalize_text(text).split())
            return bool(tokens) and not tokens <= label_tokens

        location = []
        if report and adds(report):
            location.append(report)
            label_tokens |= set(self._normalize_text(report).split())
        if page and adds(page):
            location.append(f"página {page}" if location else f"Página {page}")
        parts = [self._short_text(description, limit), " › ".join(location)]
        return " · ".join(part for part in parts if part)

    def _describe_choices(self, question, choices, metrics):
        """Pide al LLM una frase por opción («qué obtendrías de este
        indicador»). Queda en choice["model_description"]."""
        if self.option_describer is None or not question:
            self._think(
                "Descripción de las opciones",
                "sin LLM disponible: se usa la descripción del catálogo",
            )
            return
        options = []
        for choice in choices:
            metric = metrics.get(choice["id"]) or {}
            report, page = choice["_where"]
            visuals = []
            for appearance in metric.get("appearances") or []:
                title = str(appearance.get("visual_title") or "").strip()
                if title and title not in visuals:
                    visuals.append(title)
            options.append({
                "id": choice["id"],
                "label": metric.get("label") or choice["label"],
                "measure": metric.get("measure"),
                "dax_expression": metric.get("dax_expression"),
                "description": metric.get("description"),
                "report": report, "page": page,
                "visuals": ", ".join(visuals[:4]),
                "semantic_model": metric.get("semantic_model"),
            })
        try:
            outcome = self.option_describer.describe(question, options)
        except Exception as error:
            outcome = {"status": "error", "descriptions": {},
                       "error": f"{type(error).__name__}: {error}"}
        descriptions = outcome.get("descriptions") or {}
        for choice in choices:
            if descriptions.get(choice["id"]):
                choice["model_description"] = descriptions[choice["id"]]
        self._think(
            "Descripción de las opciones con el LLM",
            f"estado: {outcome.get('status')} · {outcome.get('elapsed_s', '-')} s"
            + (f" · modelo {outcome.get('model')}" if outcome.get("model") else ""),
            f"opciones descritas por el modelo: {len(descriptions)} de {len(choices)}"
            + (" (las demás usan la descripción del catálogo)"
               if len(descriptions) < len(choices) else ""),
            f"error: {outcome.get('error')}" if outcome.get("error") else None,
            f"respuesta del modelo: {short(outcome.get('raw'), 900)}" if outcome.get("raw") else None,
        )

    def _finalize_choices(self, question, choices, metrics):
        """Descripción corta visible de cada opción: la del LLM si la dio, si
        no la del catálogo; más informe/página cuando la etiqueta no los dice."""
        self._describe_choices(question, choices, metrics)
        for choice in choices:
            report, page = choice.pop("_where")
            model_text = choice.get("model_description")
            choice["summary"] = self._choice_summary(
                choice.pop("_summary_label", choice["label"]),
                model_text or choice["description"], report, page,
                limit=170 if model_text else 110,
            )
            choice["summary_source"] = "modelo" if model_text else "catálogo"
        return choices

    def _build_clarification_choices(self, raw_candidates, margin=_CLARIFICATION_MARGIN,
                                     question=None):
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
            if margin is None or best - pair[0] <= margin
        ][: self._CLARIFICATION_MAX_OPTIONS]

        choices = []
        metrics = {metric.get("metric_id"): metric for _, metric in scored}
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
                # Sin página, la descripción muestra al menos el tablero o el
                # modelo: así dos opciones parecidas nunca son indistinguibles.
                "_where": (report or model, page),
            })

        # Etiquetas distinguibles: se agregan reporte/página/modelo
        # progresivamente solo mientras existan duplicados. Se comparan sin
        # tildes, mayúsculas ni guiones bajos («Total cirugías» = «TOTAL_CIRUGIAS»).
        def label_key(choice):
            return self._normalize_text(choice["label"]) or choice["label"].casefold()

        for _ in range(4):
            groups = {}
            for choice in choices:
                groups.setdefault(label_key(choice), []).append(choice)
            duplicated = [group for group in groups.values() if len(group) > 1]
            if not duplicated:
                break
            for group in duplicated:
                for choice in group:
                    # Siguiente dato no vacío (informe, página, modelo, medida):
                    # una medida sin informe ni página muestra su modelo.
                    while choice["_parts"]:
                        part = choice["_parts"].pop(0)
                        if part and self._normalize_text(part) not in self._normalize_text(choice["label"]):
                            choice["label"] = f"{choice['label']} — {part}"
                            break
        groups = {}
        for choice in choices:
            groups.setdefault(label_key(choice), []).append(choice)
        for group in groups.values():
            if len(group) > 1:
                for number, choice in enumerate(group, 1):
                    choice["label"] = f"{choice['label']} ({number})"
        for choice in choices:
            choice.pop("_parts", None)
        return self._finalize_choices(question, choices, metrics)

    _NONE_LABEL = "Ninguna de las anteriores"
    _NONE_CAPTION = "Buscar otros indicadores parecidos a la pregunta"

    def _clarification_response(self, choices, question=None, none_label=_NONE_LABEL):
        # `prompt` es solo la pregunta: la interfaz muestra las opciones como
        # botones con su descripción corta. `question` conserva además la
        # lista numerada para quien responde escribiendo. La última opción
        # («Ninguna de las anteriores») busca otros indicadores.
        prompt = question or "Encontré varios indicadores. ¿Cuál necesitas?"
        lines = []
        for index, choice in enumerate(choices, 1):
            line = f"{index}. {choice['label']}"
            if choice.get("summary"):
                line += f" ({choice['summary']})"
            lines.append(line)
        lines.append(f"{len(choices) + 1}. {none_label}")
        self._think(
            "Contrapregunta al usuario",
            prompt,
            *[
                f"opción {line} [descripción: {choice.get('summary_source', 'catálogo')}]"
                for line, choice in zip(lines, choices)
            ],
            f"opción {lines[-1]}",
        )
        return {
            "status": "needs_clarification", "route": "clarification",
            "clarification_type": "query_plan_metric",
            "prompt": prompt,
            "question": prompt + "\n\n" + "\n".join(lines),
            "clarification_options": [dict(choice) for choice in choices],
            "none_option": {
                "id": NONE_OF_THE_ABOVE_ID, "label": none_label,
                "caption": self._NONE_CAPTION,
            },
        }

    def _query_plan_clarification(self, plan, raw_candidates=None, prompt=None, margin=_CLARIFICATION_MARGIN):
        if raw_candidates is None:
            raw_candidates = plan.get("metric_resolution", {}).get("candidates", [])
        choices = self._build_clarification_choices(
            raw_candidates, margin=margin, question=plan.get("question"),
        )
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
            "excluded": [],
        }
        response = self._clarification_response(choices, prompt)
        response["query_plan"] = plan
        return response

    def _search_alternatives(self, pending):
        """«Ninguna de las anteriores»: ofrece los indicadores más cercanos a
        la pregunta que aún no se mostraron; si no quedan, pide reformular."""
        excluded = list(dict.fromkeys(
            [*pending.get("excluded", []), *(c["id"] for c in pending["choices"])]
        ))
        self._think(
            "El usuario descartó las opciones ofrecidas",
            f"pregunta original: {pending['question']}",
            f"indicadores descartados: {', '.join(str(i) for i in excluded)}",
        )
        finder = getattr(self.query_plan_builder, "alternative_metrics", None)
        raw = []
        if callable(finder):
            try:
                raw = finder(pending["question"], exclude_ids=excluded) or []
            except Exception as error:
                self._think("La búsqueda de alternativas falló", f"{type(error).__name__}: {error}")
        self._think(
            "Otros indicadores cercanos a la pregunta",
            *([self._candidate_line(item) for item in raw] or ["no quedan indicadores parecidos"]),
        )
        choices = self._build_clarification_choices(raw, margin=None, question=pending["question"])
        if not choices:
            self._pending_query_plan = None
            return {
                "status": "not_found", "route": "clarification",
                "stage": "none_of_the_above", "question": pending["question"],
                "answer": (
                    f"No encontré otros indicadores parecidos a «{pending['question']}». "
                    "Reformula la pregunta con el nombre del indicador o indica el "
                    "tablero o la página donde lo ves."
                ),
            }
        self._pending_query_plan = {**pending, "choices": choices, "excluded": excluded}
        return self._clarification_response(
            choices, "Busqué otros indicadores parecidos a tu pregunta. ¿Es alguno de estos?",
        )

    def _unresolved_words_clarification(self, plan):
        """Palabras que no se pudieron interpretar como filtro: se pregunta si
        se calcula la métrica sin ellas en lugar de responder que no se pudo."""
        metric = (plan.get("metric_resolution") or {}).get("metric") or {}
        words = str(plan.get("unresolved_text") or "").strip()
        if not metric.get("metric_id") or not words:
            return None
        label = str(metric.get("label") or "").strip()
        report, page, model = self._clarification_context(metric)
        choices = self._finalize_choices(plan.get("question"), [{
            "id": metric.get("metric_id"),
            "label": f"Consultar {label.capitalize()} sin «{words}»",
            "detail": " · ".join(
                part for part in (" › ".join(p for p in (report, page) if p), model) if part
            ),
            "description": str(metric.get("description") or "").strip(),
            "_summary_label": label,
            "_where": (report or model, page),
        }], {metric.get("metric_id"): metric})
        self._pending_query_plan = {
            "type": "query_plan_metric",
            "question": plan.get("question"),
            "intent": plan.get("intent"),
            "choices": choices,
            "excluded": [],
            "none_label": "No, buscar otro indicador",
        }
        response = self._clarification_response(
            choices,
            f"Identifiqué el indicador {label.capitalize()}, pero no entendí «{words}» "
            "como un filtro de ese tablero. ¿Lo consulto sin ese filtro? "
            "También puedes reescribir la pregunta indicando el servicio, la "
            "especialidad u otro filtro.",
            none_label="No, buscar otro indicador",
        )
        response["query_plan"] = plan
        return response

    def _run_selected_metric(self, pending, choice):
        self._pending_query_plan = None
        self._think(
            "El usuario eligió una opción",
            f"{choice['label']} [{choice['id']}]",
            f"pregunta original: {pending['question']}",
        )
        plan = self.query_plan_builder.build(
            pending["question"], selected_metric_id=choice["id"]
        )
        self._trace_plan(plan, "Query Plan con el indicador elegido")
        if plan.get("status") == "ready":
            return self._execute_query_plan(plan)
        return self._query_plan_failure(plan)

    def select_clarification_option(self, option_id, label=None):
        """Resuelve una contrapregunta pendiente con la opción elegida (botón).
        `label` (texto del botón) solo se usa en el razonamiento."""
        def run():
            result = self._select_clarification_option(option_id)
            self._remember_success(result)
            return result

        return self._traced(
            "option", f"{label} [{option_id}]" if label else option_id, run,
        )

    def _select_clarification_option(self, option_id):
        unavailable = {
            "status": "error", "route": "clarification",
            "stage": "select_option",
            "error": "La opción elegida ya no está disponible.",
        }
        pending = self._pending_query_plan
        if pending is not None:
            if str(option_id) == NONE_OF_THE_ABOVE_ID:
                return self._search_alternatives(pending)
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
            self._think(
                "El usuario eligió un tablero",
                f"{choice['id']} · pregunta original: {dashboard_pending['question']}",
            )
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

        # Una sola opción («¿Lo consulto sin ese filtro?»): basta con un «sí».
        if len(choices) == 1 and re.fullmatch(
            r"(?:si|ok|okay|dale|claro|de acuerdo|correcto|hazlo|adelante|consultalo)"
            r"(?:\s+(?:por favor|porfa|gracias))?",
            norm,
        ):
            return choices[0]

        number = re.fullmatch(
            r"(?:(?:la|el|opcion|numero|num|no|n)\s+)*(\d{1,2})(?:\s+(?:opcion|por favor))?",
            norm,
        )
        if number:
            index = int(number.group(1))
            return choices[index - 1] if 1 <= index <= len(choices) else None

        # Ordinales: «la primera», «el segundo», «primera opción», «la última»
        # («la última» es la última opción real, no «Ninguna de las anteriores»).
        position = ordinal_choice_index(norm, len(choices))
        # Una palabra suelta que forma parte de una etiqueta («primera» con
        # la opción «Primera vez») se empareja por nombre, no como ordinal.
        if position is not None and len(norm.split()) == 1 and any(
            norm in self._normalize_text(c["label"]).split() for c in choices
        ):
            position = None
        if position is not None:
            self._think(
                "La respuesta es un ordinal",
                f"«{message}» -> opción {position + 1}: {choices[position]['label']}",
            )
            return choices[position]

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
        return self._choice_by_location(message, choices)

    _LOCATION_REPLY = re.compile(
        r"^(?:(?:es|seria|quiero|prefiero|dame)\s+)?(?:el|la|los|las|lo)?\s*"
        r"(?:(?:de|del|en|en el|en la)\s+)?(?:(?:el|la)\s+)?"
        r"(?:(?:tablero|informe|reporte|pagina|modelo|hoja)\s+(?:de\s+|del\s+)?)?(?P<rest>.+)$"
    )

    def _choice_by_location(self, message, choices):
        """«el de referencia», «la del tablero de camas», «el de urgencias»:
        elige la opción cuyo tablero/página/modelo (o etiqueta) contiene esas
        palabras, tolerando plurales y tildes. Solo si una única opción las tiene."""
        from src.semantic.query_plan_builder import _tokens_match_loosely, canonical_token

        norm = self._normalize_text(message)
        match = self._LOCATION_REPLY.match(norm)
        rest = match.group("rest") if match else norm
        wanted = [
            canonical_token(token) for token in rest.split()
            if len(token) >= 3 and token not in self._CLARIFICATION_STOPWORDS
        ]
        if not wanted:
            return None
        hits = []
        for choice in choices:
            text = f"{choice.get('label') or ''} {choice.get('detail') or ''}"
            tokens = {canonical_token(token) for token in self._normalize_text(text).split() if len(token) >= 3}
            if all(any(_tokens_match_loosely(word, token) for token in tokens) for word in wanted):
                hits.append(choice)
        if len(hits) == 1:
            self._think(
                "La respuesta nombra el tablero o la página de una opción",
                f"«{message}» -> {hits[0]['label']}",
            )
            return hits[0]
        return None

    _NONE_REPLY = re.compile(
        r"(?:no\s+(?:es\s+)?)?(?:ningun|ninguna|ninguno)"
        r"(?:\s+de)?(?:\s+(?:las|los|esas|esos|estas|estos))?"
        r"(?:\s+(?:anteriores|anterior|opciones|indicadores))?"
        r"(?:\s+(?:me\s+)?sirven?)?"
        r"|(?:(?:busca|buscar|busque|quiero|dame)\s+)?(?:otro|otra|otros|otras)"
        r"(?:\s+(?:opcion|opciones|indicador|indicadores))?"
    )

    def _is_none_reply(self, message, count):
        """«Ninguna de las anteriores» escrito (o el número de esa opción)."""
        norm = self._normalize_text(message)
        if not norm:
            return False
        if count == 1 and re.fullmatch(r"no(?:\s+(?:gracias|es ese|ese no|por favor))?", norm):
            return True
        number = re.fullmatch(
            r"(?:(?:la|el|opcion|numero|num|no|n)\s+)*(\d{1,2})(?:\s+(?:opcion|por favor))?",
            norm,
        )
        if number:
            return int(number.group(1)) == count + 1
        return bool(self._NONE_REPLY.fullmatch(norm))

    def _continue_query_plan(self, message):
        pending = self._pending_query_plan
        if pending is None:
            return None
        choices = pending["choices"]
        self._think(
            "Hay una contrapregunta pendiente",
            f"pregunta original: {pending['question']}",
            "opciones: " + " | ".join(str(c["label"]) for c in choices),
        )
        if self._is_none_reply(message, len(choices)):
            return self._search_alternatives(pending)
        # Primero intentar emparejar una opción: una respuesta larga puede
        # ser una opción y no una pregunta nueva.
        selected = self._match_query_plan_choice(message, choices)
        if selected is None:
            if self._looks_like_new_question(message):
                self._think(
                    "La respuesta no coincide con ninguna opción",
                    "parece una pregunta nueva: se descarta la contrapregunta",
                )
                self._pending_query_plan = None
                return None
            self._think(
                "La respuesta no coincide con ninguna opción",
                "se vuelve a preguntar",
            )
            return self._clarification_response(
                choices,
                "Indica el número o el nombre de la opción correspondiente.",
                none_label=pending.get("none_label") or self._NONE_LABEL,
            )
        return self._run_selected_metric(pending, selected)

    def _resolution_prompt(self, plan):
        """Texto de la contrapregunta según por qué no se eligió un indicador."""
        reason = plan.get("reason")
        words = str(plan.get("unresolved_text") or "").strip()
        if reason == "same_name_in_several_boards":
            return "Ese indicador existe en varios tableros. ¿Cuál necesitas?"
        if reason == "qualifier_matches_other_metrics" and words:
            return f"«{words}» aparece en varios indicadores. ¿Cuál necesitas?"
        if reason == "metric_not_in_named_report":
            board = plan.get("named_report") or "ese tablero"
            suggestions = (plan.get("metric_resolution") or {}).get("suggestions") or []
            in_board = any(
                self._normalize_text((item.get("metric") or {}).get("semantic_model"))
                == self._normalize_text((plan.get("source_context") or {}).get("semantic_model"))
                for item in suggestions
            )
            if in_board:
                return (
                    f"En el tablero {board} no encontré ese indicador. Estos son los más "
                    "parecidos de ese tablero. ¿Es alguno de estos?"
                )
            return (
                f"En el tablero {board} no encontré ese indicador. Lo encontré en otro "
                "tablero. ¿Es este?"
            )
        if reason == "unresolved_words_outweigh_metric" and words:
            return (
                f"No encontré un indicador que corresponda a «{words}». "
                "¿Es alguno de estos?"
            )
        return None

    def _query_plan_failure(self, plan):
        if plan.get("status") == "ambiguous":
            return self._query_plan_clarification(plan, prompt=self._resolution_prompt(plan))
        if plan.get("status") == "not_found":
            # Ningún indicador coincide lo suficiente, pero algunos comparten
            # palabras con la pregunta: se ofrecen en lugar de «no encontré».
            suggestions = (plan.get("metric_resolution") or {}).get("suggestions") or []
            if suggestions:
                return self._query_plan_clarification(
                    plan, raw_candidates=suggestions, margin=None,
                    prompt=self._resolution_prompt(plan)
                    or "No identifiqué con certeza el indicador. ¿Es alguno de estos?",
                )
        if (
            plan.get("status") == "unsupported_filter"
            and plan.get("reason") == "possible_dimension_value_not_resolved"
        ):
            clarification = self._unresolved_words_clarification(plan)
            if clarification is not None:
                return clarification
        if plan.get("status") == "unsupported_filter":
            return {
                "status": "unsupported_filter", "route": "powerbi",
                "stage": plan.get("stage"), "details": plan,
                "query_plan": plan,
                "powerbi_unavailable": bool(plan.get("domain_error")),
            }
        return self._metric_not_resolved_response(plan)

    @staticmethod
    def _examples_text(examples):
        parts = [
            f"«{item['label']}»" + (f" ({item['report']})" if item.get("report") else "")
            for item in examples or [] if item.get("label")
        ]
        if not parts:
            return ""
        return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " o " + parts[-1]

    def _metric_not_resolved_response(self, plan):
        """Sin indicador ni sugerencias. Distingue:
        - fuera de alcance (ninguna palabra coincide con el catálogo) -> se dice;
        - pregunta genérica o con palabras conocidas -> se pide el indicador o
          el tablero con un ejemplo real del catálogo."""
        response = {
            "status": "metric_not_resolved", "route": "powerbi",
            "stage": "query_plan_metric", "query_plan": plan,
            "details": plan.get("metric_resolution"),
        }
        describe = getattr(self.query_plan_builder, "describe_unresolved", None)
        if not callable(describe) or not plan.get("question"):
            return response
        try:
            info = describe(plan["question"]) or {}
        except Exception as error:
            self._think("No se pudo clasificar la pregunta", f"{type(error).__name__}: {error}")
            return response
        # El plan puede traer ya la clasificación (p. ej. el indicador se
        # descartó porque nada de lo no interpretado existe en el catálogo).
        kind = plan.get("unresolved_kind") or info.get("kind")
        words = ", ".join(f"«{word}»" for word in info.get("words") or [])
        examples = self._examples_text(info.get("examples"))
        example_text = f" Por ejemplo: {examples}." if examples else ""
        board = plan.get("named_report")
        if board and plan.get("unresolved_kind") != "out_of_scope":
            # La pregunta nombra un tablero que existe: no es «fuera de
            # alcance», sino que ese tablero no tiene el indicador pedido.
            board_words = set(self._normalize_text(board).split())
            words = ", ".join(
                f"«{word}»" for word in info.get("words") or []
                if word not in board_words and word.rstrip("s") not in board_words
            )
            self._think(
                "Indicador no encontrado en el tablero nombrado",
                f"tablero: {board}; ningún indicador de ese tablero coincide con "
                f"{words or 'la pregunta'}",
            )
            answer = (
                f"En el tablero {board} no encontré un indicador para "
                f"{words or 'tu pregunta'}. Escribe el nombre del indicador tal como "
                "aparece en el tablero o pregunta qué muestra ese tablero."
            )
            return {**response, "answer": answer, "unresolved_kind": "not_in_named_board"}
        if kind == "out_of_scope":
            self._think(
                "Pregunta fuera de alcance",
                f"ninguna palabra distintiva ({words}) aparece en los indicadores, "
                "tableros o dimensiones del catálogo",
            )
            return {
                "status": "not_found", "route": "out_of_scope",
                "stage": "query_plan_metric", "query_plan": plan,
                "question": plan.get("question"), "sources": [],
                "answer": (
                    "Esa pregunta está fuera del alcance de los tableros disponibles: no "
                    "corresponde a ninguno de sus indicadores ni a su documentación. "
                    "Puedo ayudarte con indicadores de los tableros institucionales."
                    + example_text
                ),
            }
        if kind == "generic":
            self._think(
                "Pregunta genérica",
                "no nombra un indicador concreto y ningún indicador del catálogo coincide",
            )
            answer = (
                "Tu pregunta no menciona un indicador concreto. ¿Qué indicador o "
                "tablero necesitas? Escribe su nombre." + example_text
            )
        else:
            self._think(
                "Indicador no identificado",
                f"palabras conocidas por el catálogo: "
                f"{', '.join(info.get('known_words') or []) or '-'}; ningún indicador coincide",
            )
            answer = (
                f"No identifiqué un indicador para {words or 'tu pregunta'} en los tableros "
                "disponibles. Escribe el nombre del indicador o del tablero donde lo ves."
                + example_text
            )
        return {**response, "answer": answer, "unresolved_kind": kind}

    # ========================================================
    # PREGUNTAS COMPUESTAS (participación / varias métricas)
    # ========================================================

    @staticmethod
    def _fmt_es(value, max_decimals=2):
        """Número con formato español: 3.906,4 / 488,3."""
        if value is None:
            return "sin dato"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        text = f"{number:,.{max_decimals}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text.replace(",", "§").replace(".", ",").replace("§", ".")

    def _composite_scope_text(self, plan):
        period = None
        scope = "total"
        for item in plan.get("filters", []) or []:
            if item.get("type") != "date_range" and not (item.get("temporal") and item.get("label")):
                continue
            year, month = item.get("year"), item.get("month")
            kind = item.get("period_kind")
            if year and month and kind in (None, "month"):
                name = item.get("month_name") or str(month)
                period, scope = f"{name} de {year}", "total del mes"
            elif year and kind in (None, "year"):
                period, scope = item.get("label") or f"{year}", "total del año"
            elif item.get("label"):
                # Rango, trimestre, «2026 hasta hoy», días...
                period, scope = item["label"], "total del periodo"
        values = [
            str(item.get("value")) for item in plan.get("filters", []) or []
            if item.get("type") == "categorical" and item.get("value") is not None
            and not item.get("temporal")  # AÑO/MES ya van en el periodo
        ]
        return period, values, scope

    def _composite_answer(self, plan, measures, unresolved, failed_labels):
        period, values, scope = self._composite_scope_text(plan)
        parts = []
        for measure in measures:
            if measure["format"] == "percent":
                if measure["value"] is None:
                    parts.append("participación sin dato")
                else:
                    parts.append(
                        f"participación del {self._fmt_es(measure['value'] * 100, 2)} % "
                        f"sobre el {scope}"
                    )
            else:
                parts.append(f"{str(measure['label']).lower()} {self._fmt_es(measure['value'])}")
        subject = ", ".join(values)
        head = f"En {period}, " if period else ""
        if subject:
            head += f"{subject} registró: " if head else f"{subject} registró: "
        else:
            head += "resultado: " if head else "Resultado: "
        answer = head + " y ".join(parts) + "."
        notes = []
        if unresolved:
            notes.append(
                "No pude interpretar " + ", ".join(f"«{w}»" for w in unresolved)
                + "; respondí solo las partes que identifiqué."
            )
        if failed_labels:
            notes.append(
                "No pude resolver: " + ", ".join(failed_labels) + "."
            )
        return " ".join([answer, *notes])

    def _composite_failure(self, stage, plan, dax_result=None, powerbi_result=None):
        if dax_result is not None and dax_result.get("status") != "generated":
            return {
                "status": "dax_not_generated", "route": "powerbi",
                "stage": stage, "query_plan": plan, "details": dax_result,
            }
        return {
            "status": "powerbi_error", "route": "powerbi", "stage": stage,
            "query_plan": plan,
            "dax": (dax_result or {}).get("dax"),
            "details": powerbi_result,
        }

    def _execute_composite(self, composite):
        """Ejecuta cada medida del plan compuesto y arma un único resultado."""
        measures, executed, failed_labels = [], [], []
        last_failure = None
        for item in composite["items"]:
            plan = item["plan"]
            if item["kind"] == "share":
                dax_result = self.query_plan_dax_generator.generate_share(plan)
            else:
                dax_result = self.query_plan_dax_generator.generate(plan)
            if dax_result.get("status") != "generated":
                self._trace_dax(f"Consulta a Power BI: {item['label']}", dax_result)
                last_failure = self._composite_failure("query_plan_dax", plan, dax_result)
                failed_labels.append(item["label"])
                continue
            powerbi_result = self.powerbi_provider.execute_dax(
                dax=dax_result.get("dax"),
                semantic_model=plan.get("semantic_model"),
            )
            self._trace_dax(f"Consulta a Power BI: {item['label']}", dax_result, powerbi_result)
            if powerbi_result.get("status") != "success":
                last_failure = self._composite_failure(
                    "query_plan_powerbi", plan, dax_result, powerbi_result
                )
                failed_labels.append(item["label"])
                continue
            rows = powerbi_result.get("rows", []) or []
            if dax_result.get("mode") == "grouped":
                executed.append((item, plan, dax_result, powerbi_result, rows, None))
                continue
            value = self._row_value(rows[0]) if rows else None
            if item["kind"] == "share":
                if value is not None:
                    value = float(value)  # fracción (0,125 = 12,5 %)
                measure = {
                    "label": item["label"], "value": value,
                    "format": "percent", "unit": "%", "dax": dax_result.get("dax"),
                }
            else:
                measure = {
                    "label": item["label"], "value": value,
                    "format": "number", "unit": None, "dax": dax_result.get("dax"),
                }
            measures.append(measure)
            executed.append((item, plan, dax_result, powerbi_result, rows, measure))

        if not executed:
            return last_failure
        item, plan, dax_result, powerbi_result, rows, _ = executed[0]

        if dax_result.get("mode") == "grouped":
            group = plan["share_dimension"]
            lines = [
                f"| {group.get('label') or group.get('column')} | Participación |",
                "| --- | --- |",
            ]
            for row in rows[:50]:
                label = next(
                    (v for k, v in row.items() if "__value" not in str(k).lower()), ""
                )
                value = self._row_value(row)
                pct = "" if value is None else f"{self._fmt_es(float(value) * 100, 2)} %"
                lines.append(f"| {str(label).replace('|', chr(92) + '|')} | {pct} |")
            answer = "\n".join(lines)
            result_type, value, metric_label = "table", None, plan["metric"].get("label")
            measures_out = None
        else:
            if all(m["value"] is None for m in measures):
                return {
                    "status": "empty_result", "route": "powerbi",
                    "stage": "query_plan_result", "query_plan": plan,
                    "dax": dax_result.get("dax"), "details": powerbi_result,
                }
            answer = self._composite_answer(
                plan, measures, composite.get("unresolved"),
                composite.get("failed_labels", []) + failed_labels,
            )
            result_type = "scalar"
            value, metric_label = measures[0]["value"], measures[0]["label"]
            measures_out = measures

        base_plan = executed[0][1]
        metric = base_plan.get("metric", {})
        result = {
            "status": "success",
            "route": "powerbi",
            "result_type": result_type,
            "question": composite.get("question"),
            "report": base_plan.get("report"),
            "dashboard": base_plan.get("dashboard"),
            "semantic_model": base_plan.get("semantic_model"),
            "metric": metric_label,
            "metric_id": metric.get("metric_id"),
            "metric_source": metric.get("source_type"),
            "value": value,
            "rows": rows,
            "filters": base_plan.get("filters", []),
            "business_filters": [
                f for f in base_plan.get("filters", []) if f.get("type") == "categorical"
            ],
            "group_by": base_plan.get("group_by", []),
            "answer": answer,
            "dax": dax_result.get("dax"),
            "dax_queries": [e[2].get("dax") for e in executed],
            "powerbi": powerbi_result,
            "query_plan": base_plan,
            "query_plans": [e[1] for e in executed],
            "source_context": base_plan.get("source_context"),
        }
        if measures_out is not None:
            result["measures"] = measures_out
        return result

    def _run_query_plan(self, question, intent_result, stage):
        """Query Plan completo (compuesto o simple). Devuelve (respuesta, estado_del_plan)."""
        try:
            composite = self.query_plan_builder.build_composite(
                question, intent_result=intent_result
            )
            if composite is not None:
                if composite.get("status") == "composite":
                    self._think(
                        "Pregunta compuesta (varias medidas o participación)",
                        *[f"{item['kind']}: {item['label']}" for item in composite["items"]],
                        *[f"sin interpretar: «{word}»" for word in composite.get("unresolved") or []],
                        *[f"no resuelta: {label}" for label in composite.get("failed_labels") or []],
                    )
                    for item in composite["items"]:
                        self._trace_plan(item["plan"], f"Plan de «{item['label']}»")
                    return self._execute_composite(composite), "composite"
                self._think("Pregunta compuesta que no se pudo resolver")
                self._trace_plan(composite)
                return self._query_plan_failure(composite), composite.get("status")
            plan = self.query_plan_builder.build(
                question=question, intent_result=intent_result,
            )
            self._trace_plan(plan, f"Query Plan ({stage})")
        except Exception as error:
            self._think("El Query Plan lanzó un error", f"{type(error).__name__}: {error}")
            return {
                "status": "error", "route": "powerbi", "stage": stage,
                "error": f"{type(error).__name__}: {error}",
            }, "error"
        if plan.get("status") == "ready":
            return self._execute_query_plan(plan), "ready"
        return self._query_plan_failure(plan), plan.get("status")

    # ========================================================
    # PROCESS
    # ========================================================

    # ========================================================
    # SEGUIMIENTO («¿y en 2025?», «y por especialidad»)
    # ========================================================

    _FOLLOWUP_MAX_WORDS = 10

    @staticmethod
    def _is_temporal_filter(item):
        return (
            item.get("type") == "date_range"
            or bool(item.get("temporal"))
            or item.get("source") == "query_plan_temporal"
        )

    def _descriptive_reason(self, question):
        """Frase que hace descriptiva la pregunta («como se calcula», «los
        rangos del»...) o None. Sin Query Plan se usa el detector común."""
        detector = getattr(self.query_plan_builder, "descriptive_reason", None)
        try:
            if callable(detector):
                return detector(question)
            from src.semantic.question_kind import descriptive_phrase
            return descriptive_phrase(question)
        except Exception:
            return None

    def _has_pending_clarification(self):
        state = getattr(self.conversation_manager, "state", None)
        return bool(
            self._pending_query_plan is not None
            or self._pending_master_metric is not None
            or self._pending_dashboard_clarification is not None
            or getattr(state, "awaiting_clarification", False)
        )

    def _remember_success(self, result, followup=False):
        """Guarda la última consulta numérica exitosa (indicador + filtros +
        agrupación). Una respuesta final que no es un dato de Power BI (RAG,
        fuera de alcance...) a una pregunta nueva borra el contexto; una
        contrapregunta, un resultado vacío o un seguimiento fallido lo conservan."""
        if not isinstance(result, dict):
            return
        status = result.get("status")
        plan = result.get("query_plan") or {}
        metric = plan.get("metric") or {}
        if (
            status == "success" and result.get("route") == "powerbi"
            and plan.get("status") == "ready" and metric.get("metric_id")
            and not result.get("measures")
        ):
            self._last_success = {
                "question": plan.get("followup_base_question") or plan.get("question"),
                "metric_id": metric.get("metric_id"),
                "metric_label": metric.get("label"),
                "semantic_model": plan.get("semantic_model"),
                "filters": [dict(item) for item in plan.get("filters") or []],
                "group_by": [dict(item) for item in plan.get("group_by") or []],
                "ranking": dict(plan["ranking"]) if plan.get("ranking") else None,
            }
            return
        if status in ("needs_clarification", "empty_result", "error") or followup:
            return
        self._last_success = None

    def _followup_plan(self, message):
        """Plan de seguimiento o None si el mensaje no es claramente un
        complemento de la última respuesta numérica.

        Condiciones: hay una consulta exitosa previa y ninguna contrapregunta
        pendiente; el mensaje empieza con «y», es corto, no nombra otro
        indicador y aporta un período, un filtro o una agrupación.
        """
        last = self._last_success
        builder = self.query_plan_builder
        if last is None or builder is None or self.query_plan_dax_generator is None:
            return None
        if self._has_pending_clarification():
            return None
        words = self._normalize_text(message).split()
        if len(words) < 2 or words[0] != "y" or len(words) > self._FOLLOWUP_MAX_WORDS:
            return None
        complement = " ".join(words[1:])
        metric_words = getattr(builder, "metric_words", None)
        named = metric_words(complement) if callable(metric_words) else []
        if named:
            self._think(
                "¿Es un seguimiento de la consulta anterior?",
                f"no: nombra un indicador ({', '.join(named)}); se trata como pregunta nueva",
            )
            return None

        plan = builder.build(complement, selected_metric_id=last["metric_id"])
        status = plan.get("status")
        if status == "ready":
            new_filters = plan.get("filters") or []
            if not new_filters and not plan.get("group_by"):
                self._think(
                    "¿Es un seguimiento de la consulta anterior?",
                    f"no: «{complement}» no aporta un período, filtro ni agrupación reconocible",
                )
                return None
            def column_key(item):
                return (self._normalize_text(item.get("table")), self._normalize_text(item.get("column")))

            new_temporal = any(self._is_temporal_filter(item) for item in new_filters)
            new_columns = {
                column_key(item) for item in new_filters if not self._is_temporal_filter(item)
            }
            # «y por especialidad» tras «... de urología»: agrupar por la
            # columna reemplaza el filtro sobre ella; «y de ortopedia?» tras
            # una tabla por especialidad reemplaza esa agrupación.
            new_groups = {column_key(item) for item in plan.get("group_by") or []}
            inherited = []
            replaced = []
            for item in last["filters"]:
                temporal = self._is_temporal_filter(item)
                key = column_key(item)
                if (temporal and new_temporal) or (
                    not temporal and (key in new_columns or key in new_groups)
                ):
                    replaced.append(item)
                    continue
                inherited.append(dict(item))
            group_by = plan.get("group_by") or [
                dict(item) for item in last["group_by"] if column_key(item) not in new_columns
            ]
            ranking = plan.get("ranking") or (last.get("ranking") if not plan.get("group_by") else None)
            plan = {
                **plan,
                "filters": inherited + list(new_filters),
                "group_by": group_by,
                "mode": "grouped" if group_by else "scalar",
                "ranking": ranking if group_by else None,
                "question": f"{last['question']} ({message.strip()})",
                "followup_base_question": last["question"],
                "followup_of": {"question": last["question"], "metric": last["metric_label"]},
            }
            self._think(
                "Seguimiento de la consulta anterior",
                f"se interpretó «{message.strip()}» como seguimiento de «{last['question']}» "
                f"(indicador {last['metric_label']})",
                *[f"se conserva: {self._filter_line(item)}" for item in inherited],
                *[f"se reemplaza: {self._filter_line(item)}" for item in replaced],
                *[f"nuevo: {self._filter_line(item)}" for item in new_filters],
                *[f"agrupar por: {item.get('table')}[{item.get('column')}]" for item in group_by],
            )
            return plan
        if status == "unsupported_filter":
            self._think(
                "Seguimiento de la consulta anterior",
                f"se interpretó «{message.strip()}» como seguimiento de «{last['question']}» "
                f"(indicador {last['metric_label']}), pero el complemento no se pudo aplicar",
            )
            return {**plan, "followup_of": {"question": last["question"], "metric": last["metric_label"]}}
        return None

    def _process_turn(self, message):
        followup = self._followup_plan(message)
        if followup is not None:
            self._trace_plan(followup, "Query Plan del seguimiento")
            if followup.get("status") == "ready":
                result = self._execute_query_plan(followup)
            else:
                result = self._query_plan_failure(followup)
            result["followup_of"] = followup.get("followup_of")
            self._remember_success(result, followup=True)
            return result
        result = self._process(message)
        self._remember_success(result)
        return result

    def process(self, message):
        return self._traced("question", message, lambda: self._process_turn(message))

    def _process(
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

        unresolved_plan_response = None
        unresolved_plan_pending = None
        query_plan_attempted = False

        if self.query_plan_builder and self.query_plan_dax_generator:
            try:
                early_numeric =self.query_plan_builder.looks_numeric(
                    message,
                    dashboard=None,
                )
            except Exception:
                early_numeric = False

            descriptive = None if early_numeric else self._descriptive_reason(message)
            self._think(
                "¿La pregunta pide un dato numérico?",
                "sí: se intenta primero el Query Plan (Power BI)" if early_numeric
                else (
                    f"no: es una pregunta descriptiva («{descriptive}»): pide una explicación "
                    "(cálculo, significado, rangos, filtros...), no un valor; se responde con la "
                    "documentación aunque contenga palabras numéricas"
                ) if descriptive
                else "no se detectó: se pasa al analizador de intención",
            )

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

                early_response, early_status = self._run_query_plan(
                    message, early_intent, "query_plan_early"
                )
                if early_status != "not_found":
                    return early_response
                is_ranking = getattr(self.query_plan_builder, "is_ranking", None)
                if (
                    early_response.get("status") == "needs_clarification"
                    and callable(is_ranking) and is_ranking(message)
                ):
                    self._think(
                        "Pregunta de ranking",
                        "pide ordenar o limitar un indicador («top», «con más/menos»): "
                        "se contrapregunta por el indicador sin pasar por la documentación",
                    )
                    return early_response
                # Métrica no resuelta: la pregunta puede ser documental
                # aunque use palabras numéricas. Se intenta el RAG y solo si
                # también falla se devuelve este resultado (que puede ser una
                # contrapregunta con indicadores sugeridos: queda pendiente
                # solo si finalmente se devuelve).
                self._think(
                    "Indicador no identificado con certeza",
                    "se prueba la documentación (RAG); si tampoco responde se "
                    "devuelve el resultado del Query Plan",
                )
                unresolved_plan_response = early_response
                unresolved_plan_pending = self._pending_query_plan
                self._pending_query_plan = None
                query_plan_attempted = True

        # ----------------------------------------------------
        # 2. INTENCIÓN + CONVERSACIÓN NORMAL
        # ----------------------------------------------------

        intent_result = (
            self.conversation_manager
            .handle_message(
                message
            )
        )

        self._think(
            "Analizador de intención",
            f"estado: {intent_result.get('status')} · intención: {intent_result.get('intent')}",
            f"tablero: {intent_result.get('dashboard')}"
            + (f" (identificado por {intent_result.get('dashboard_reason')})"
               if intent_result.get("dashboard_reason") else "")
            if intent_result.get("dashboard") else None,
            f"faltan: {', '.join(intent_result.get('missing_fields') or [])}"
            if intent_result.get("missing_fields") else None,
            f"tableros candidatos: {', '.join(str(c) for c in intent_result.get('candidates') or [])}"
            if intent_result.get("candidates") else None,
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
                # Los tableros ya se muestran como botones: sin «Por ejemplo: ...».
                clarification["prompt"] = (
                    re.split(r"\s*Por ejemplo:", clarification["question"] or "")[0].strip()
                    or "¿A qué tablero te refieres?"
                )
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

        # Una pregunta descriptiva («¿cómo se calcula el porcentaje de
        # ocupación?») nunca va a Power BI, aunque el analizador de intención
        # la haya marcado numérica por la palabra «porcentaje».
        if intent in ("query_metric", "compare_metric"):
            descriptive = self._descriptive_reason(
                intent_result.get("original_question") or message
            )
            if descriptive:
                self._think(
                    "Pregunta descriptiva",
                    f"«{descriptive}» pide una explicación, no un valor: se busca en la "
                    f"documentación en vez de consultar Power BI (intención original: {intent})",
                )
                intent = "general_question"
                intent_result = {**intent_result, "intent": intent}

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
            elif intent == "general_question" and not query_plan_attempted:
                try:
                    should_try_query_plan = self.query_plan_builder.looks_numeric(
                        original_question,
                        dashboard=intent_result.get("dashboard"),
                    )
                except Exception:
                    should_try_query_plan = False

        if should_try_query_plan:
            plan_response, _ = self._run_query_plan(
                original_question, intent_result, "query_plan"
            )
            return plan_response

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

            self._think(
                "Búsqueda en la documentación (RAG)",
                f"estado: {rag_result.get('status')} · síntesis: {rag_result.get('synthesis_mode')}",
                *[
                    f"fuente: {source.get('dashboard') or '-'} · {source.get('chunk_type') or '-'}"
                    f" · puntaje {format_score(source.get('score'))}"
                    f" · {short(source.get('text'), 120)}"
                    for source in rag_result.get("sources") or []
                ],
            )

            if (
                rag_result.get(
                    "status"
                )
                == "not_found"
            ):
                # Fallback: el RAG no tiene evidencia; si el Query Plan sí
                # puede resolver la pregunta (o pedir aclaración), se usa.
                if (
                    self.query_plan_builder
                    and self.query_plan_dax_generator
                    and not query_plan_attempted
                    and intent == "general_question"
                    and not self.query_plan_builder.is_descriptive(original_question)
                ):
                    previous_pending = self._pending_query_plan
                    fallback_response, fallback_status = self._run_query_plan(
                        original_question, intent_result, "query_plan_fallback"
                    )
                    if fallback_status in ("ready", "composite", "ambiguous"):
                        return fallback_response
                    if fallback_response.get("status") == "needs_clarification":
                        # La pregunta no parecía numérica y la documentación
                        # no tiene evidencia («¿qué medicamento le doy a un
                        # paciente con fiebre?»): una contrapregunta con
                        # indicadores que solo comparten alguna palabra
                        # («pacientes») no ayuda. Se responde fuera de alcance.
                        self._pending_query_plan = previous_pending
                        self._think(
                            "Respaldo del Query Plan descartado",
                            "la pregunta no pide un dato y la documentación no tiene evidencia "
                            f"({rag_result.get('not_found_reason') or 'sin evidencia'}); el "
                            f"Query Plan solo ofrecía una contrapregunta (plan {fallback_status}) "
                            "con indicadores que comparten alguna palabra: se responde que está "
                            "fuera de alcance",
                        )
                if unresolved_plan_response is not None:
                    self._pending_query_plan = unresolved_plan_pending
                    return unresolved_plan_response
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

        self._think(
            "Ruta MasterMetric (anterior al Query Plan)",
            f"pregunta para la métrica: {metric_question}",
            f"resolución: {master_status}",
            None if master_status in ("resolved", "ambiguous")
            else "se usa el resolvedor legacy",
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

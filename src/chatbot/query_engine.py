import inspect
import re
import unicodedata

from src.chatbot import contextual_rewriter
from src.chatbot.contextual_rewriter import LLMContextRewriter
from src.chatbot.conversation_memory import ConversationMemory
from src.chatbot.intent_parser import ordinal_choice_index
from src.chatbot.reasoning_trace import ReasoningTrace, format_score, short
from src.chatbot.runtime_stats import STATS, degradation_lines, status_line
from src.chatbot.response_formatter import (
    NONE_OF_THE_ABOVE_ID, format_filters_line, format_value_es, group_header,
)
from src.providers.domain_cache import domain_cache_for
from src.semantic.request_phrases import requester, rewrite_request, without_requester

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
        context_llm=None,
        conversation_memory=None,
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
        self.progress_listener = None
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

        # Memoria de la conversación (últimos turnos: lo que dijo el usuario,
        # lo que respondió el asistente y con qué datos). Sobrevive a reset()
        # y se borra con reset(full=True). La usa la reescritura contextual
        # («y en el mes pasado?») y se pasa a la redacción del RAG.
        self.conversation_memory = conversation_memory or ConversationMemory()
        # LLM para reescribir mensajes que dependen del contexto cuando las
        # reglas no bastan. Sin él se usa el de OptionDescriber (MedGemma,
        # que app.py solo crea si el servidor está disponible).
        self.context_llm = context_llm
        self._turn_interpretation = None
        # Mensaje que depende de una contrapregunta pendiente («y en el mes
        # pasado?» antes de elegir el indicador): se responde tras el botón.
        self._deferred_context_message = None
        self._applying_deferred = None

    # ========================================================
    # ESTADO
    # ========================================================

    def reset(self, full=False):
        """Limpia las contrapreguntas pendientes. Con full=True («Nueva
        conversación») también olvida el contexto de seguimiento y la memoria
        de la conversación."""
        self._pending_master_metric = None
        self._pending_query_plan = None
        self._pending_dashboard_clarification = None
        self._deferred_context_message = None
        if full:
            self._last_success = None
            memory = getattr(self, "conversation_memory", None)
            if memory is not None:
                memory.clear()

    def conversation_history(self, limit=6):
        """Últimos `limit` turnos como mensajes [{"role": "user"|"assistant",
        "text": str, "meta": {...}}] (cada turno aporta dos mensajes). Lo usa
        la redacción de respuestas (RAGAnswerEngine / AnswerSynthesizer)."""
        memory = getattr(self, "conversation_memory", None)
        return memory.history(limit) if memory is not None else []

    # Turnos de historial que se pasan a la redacción del RAG.
    _RAG_HISTORY_TURNS = 3

    def _call_rag(self, intent_result):
        """Llama al RAG con el historial de la conversación si lo acepta
        (interfaz acordada: RAGAnswerEngine.answer(intent_data, history=None))."""
        answer = self.rag_answer_engine.answer
        history = self.conversation_history(self._RAG_HISTORY_TURNS)
        if history and self._accepts_history(answer):
            return answer(intent_result, history=history)
        return answer(intent_result)

    @staticmethod
    def _accepts_history(function):
        try:
            parameters = inspect.signature(function).parameters
        except (TypeError, ValueError):
            return False
        return "history" in parameters or any(
            parameter.kind == parameter.VAR_KEYWORD for parameter in parameters.values()
        )

    def _record_turn(self, user_text, result, via):
        memory = getattr(self, "conversation_memory", None)
        if memory is None or not isinstance(result, dict):
            return
        topic = None
        if (
            result.get("status") == "success" and result.get("route") == "powerbi"
            and self._last_success is not None
        ):
            topic = self._last_success
        try:
            memory.record(
                user_text, result, via=via,
                interpreted=getattr(self, "_turn_interpretation", None), topic=topic,
            )
        except Exception:
            # La memoria nunca debe tumbar la respuesta.
            pass

    # ========================================================
    # RAZONAMIENTO (qué revisó y por qué decidió)
    # ========================================================

    def _think(self, title, *lines):
        if self._trace is not None:
            self._trace.add(title, *lines)

    def _activity(self, title, *lines):
        """Operación que empieza y puede tardar: solo para la vista en vivo."""
        if self._trace is not None:
            self._trace.activity(title, *lines)

    def set_progress_listener(self, listener):
        """Función que recibe en vivo los pasos del turno (o None). También
        engancha las consultas DAX del proveedor de Power BI, incluidas las de
        exploración de valores que hace el Query Plan."""
        self.progress_listener = listener
        provider = self.powerbi_provider
        if provider is not None and hasattr(provider, "query_listener"):
            provider.query_listener = self._on_powerbi_query if listener else None
        if provider is not None and hasattr(provider, "activity_listener"):
            # Aperturas/reconexiones (posible ventana de inicio de sesión).
            provider.activity_listener = self._activity if listener else None

    def _on_powerbi_query(self, semantic_model, dax):
        self._activity(f"Consultando Power BI ({semantic_model or 'modelo por defecto'})",
                       short(" ".join(str(dax or "").split()), 160))

    def _traced(self, kind, text, runner):
        """Ejecuta un turno registrando su razonamiento en result["reasoning"]."""
        if self._trace is not None:
            return runner()  # turno anidado (p. ej. tablero elegido -> process)
        self._trace = ReasoningTrace(kind, text, listener=getattr(self, "progress_listener", None))
        domains = domain_cache_for(getattr(self, "powerbi_provider", None))
        if domains is not None:
            # Con el texto del turno: sin un código en él («403», «UCI-06») las
            # columnas de códigos no se exploran (src/providers/domain_cache.py).
            domains.begin_turn(question=self._exploration_text(kind, text))
        # Estado del servidor al empezar (queda en el razonamiento y en la
        # exportación): llamadas a MedGemma en curso, conexiones, hilos...
        before = self._server_snapshot()
        if before is not None:
            # Cabecera del razonamiento (no es un paso de la decisión).
            self._trace.server_state = status_line(before)
        STATS.turn_started()
        failed = True
        try:
            result = runner()
            failed = False
            if isinstance(result, dict):
                self._think_exploration(domains)
                self._think_degradation(before)
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
            self._think(
                "Error inesperado", f"{type(error).__name__}: {error}",
                f"estaba en: {self._trace.current_activity}" if self._trace.current_activity else None,
            )
            self.last_reasoning = self._trace.to_dict()
            raise
        finally:
            STATS.turn_finished(error=failed)
            self._trace = None
            if domains is not None:
                domains.end_turn()

    def _exploration_text(self, kind, text):
        """Texto en el que puede venir un código que el usuario nombró: el del
        turno y, si es un botón, la pregunta pendiente (sin el id de la opción,
        «%OCUPACIÓN [761d17ce09971f3d]»: ese id no es un código del usuario)."""
        parts = [str(text or "")]
        if kind == "option":
            parts[0] = re.sub(r"\s*\[[^\]]*\]\s*$", "", parts[0])
            for name in ("_pending_query_plan", "_pending_dashboard_clarification", "_pending_master_metric"):
                pending = getattr(self, name, None)
                if isinstance(pending, dict):
                    parts.extend(str(pending[key]) for key in ("question", "original_question")
                                 if pending.get(key))
        return " ".join(part for part in parts if part)

    def _server_snapshot(self):
        try:
            return STATS.snapshot(getattr(self, "powerbi_provider", None))
        except Exception:
            return None  # el diagnóstico nunca tumba el turno

    def _think_degradation(self, before):
        """Paso final si algo se degradó en el turno (MedGemma cortado o
        saturado, reconexión con Power BI...)."""
        if before is None:
            return
        after = self._server_snapshot()
        lines = degradation_lines(before, after) if after is not None else []
        if lines:
            self._think("Estado al terminar (degradado)", *lines, status_line(after))

    def _think_exploration(self, domains):
        """Una línea con las consultas de valores de columnas (exploración) del
        turno y su tiempo: contra Power BI real es donde suele irse el tiempo."""
        if domains is None:
            return
        # Totales y, por cada consulta lenta (> POWERBI_DOMAIN_SLOW_S) o
        # cancelada por tiempo, sus columnas y su tiempo (src/providers/domain_cache.py).
        lines = domains.describe_turn()
        if lines:
            self._think("Consultas de exploración a Power BI", *lines)

    @staticmethod
    def _metric_pages(metric):
        pages = []
        for appearance in metric.get("appearances") or []:
            page = appearance.get("page_display_name") or appearance.get("page")
            if page and page not in pages:
                pages.append(str(page))
        return pages[:3]

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

        # «Total + listado»: solo después de un total correcto y con una sola
        # consulta extra (src/semantic/detail_list.py).
        detail = self._detail_listing(plan, value) if mode == "scalar" and value is not None else None

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
            **({"detail": detail} if detail else {}),
        }

    # ========================================================
    # LISTADO DE DETALLE («TOTAL + LISTADO»)
    # ========================================================

    def _listable_choice(self, question, plan):
        """Pregunta de listado explícita («lista de camas bloqueadas», «qué
        camas están disponibles») con varios indicadores posibles: si exactamente
        uno cuenta registros identificables de la entidad nombrada (CAMAS =
        COUNT(HCACODIGO) frente a HOSPITALIZACIÓN = SUM(DEMANDA_INS) o
        NUMERO_CAMAS, un número fijo por servicio), se usa ese sin
        contrapreguntar. Devuelve ([métricas en orden], verificar): con
        verificar=True (rescate por nombre de tabla) el plan con cada métrica
        debe explicar la pregunta para usarse."""
        from src.semantic.answer_shape import detail_request
        from src.semantic.detail_list import entity_matches_metric, listable_entity

        if not isinstance(plan, dict) or plan.get("status") not in ("ambiguous", "not_found"):
            return [], False
        request = detail_request(question)
        # Solo con una lista pedida de forma explícita («lista de», «qué
        # camas están…»): un indicador que no cuenta registros no puede
        # responderla. «¿Cuántas … hay?» también se responde con un total, así
        # que la contrapregunta entre indicadores se mantiene.
        if not request or request.get("strength") != "explicit":
            return [], False
        if plan.get("status") == "not_found":
            return self._listable_by_table(request), True
        resolution = plan.get("metric_resolution") or {}
        items = [
            item for item in (resolution.get("candidates") or resolution.get("suggestions") or [])
            if (item.get("metric") or {}).get("metric_id")
        ]
        # Solo las opciones que se ofrecerían (dentro del margen de la contrapregunta).
        scores = [item.get("score") for item in items if isinstance(item.get("score"), (int, float))]
        if scores:
            floor = max(scores) - self._CLARIFICATION_MARGIN
            items = [
                item for item in items
                if not isinstance(item.get("score"), (int, float)) or item["score"] >= floor
            ]
        candidates = [item["metric"] for item in items]
        if len(candidates) < 2:
            return [], False
        listable = []
        for metric in candidates:
            try:
                entity = listable_entity(metric, self.query_plan_builder, counting_only=True)
            except Exception:
                entity = None
            if entity and entity_matches_metric(request["entity"], metric):
                listable.append(metric)
        if not listable:
            # Ninguna opción cuenta la entidad: «qué interconsultas están
            # pendientes» ofrecía %PENDIENTE / PENDIENTES1; la tabla
            # INTERCONSULTAS tiene un único conteo.
            return self._listable_by_table(request), True
        if len(listable) != 1:
            return [], False
        chosen = listable[0]
        self._think(
            "Pregunta de listado: indicador que permite listar",
            f"«{request['phrase']}» pide la lista de {request['entity']}; de las opciones "
            f"({', '.join(str(m.get('label')) for m in candidates)}) solo {chosen.get('label')} "
            f"cuenta {request['entity']} identificables ({chosen.get('model_expression') or chosen.get('dax_expression')}): "
            "se usa sin contrapreguntar",
        )
        return [chosen], False

    def _drop_listed_entity(self, question, plan):
        """«lista de PACIENTES en espera…» con EN_ESPERA: «pacientes» es lo que
        se lista (cada fila de la tabla), no un filtro sin aplicar."""
        from src.semantic.answer_shape import detail_request
        from src.semantic.request_phrases import singular

        entity = str((detail_request(question) or {}).get("entity") or "")
        forms = {entity, singular(entity)}
        kept, dropped = [], []
        for term in plan.get("unapplied_terms") or []:
            words = [w for w in str(term).split() if self._normalize_text(w) not in forms]
            (kept.append(" ".join(words)) if words else dropped.append(term))
            if words and len(words) < len(str(term).split()):
                dropped.append(entity)
        if dropped:
            plan["unapplied_terms"] = [term for term in kept if term]
            self._think(
                "Pregunta de listado",
                f"«{entity}» es lo que se lista (cada fila de {(plan.get('metric') or {}).get('table')}): "
                "no es un filtro sin aplicar",
            )

    @staticmethod
    def _plan_explains_question(plan):
        """El plan con el indicador rescatado explica la pregunta: está listo
        y deja a lo sumo una palabra sin aplicar («pendientes» frente a «SIN
        RESPUESTA»). Con más («sanitas hospitalizados camas») era otra tabla."""
        if not isinstance(plan, dict) or plan.get("status") != "ready":
            return False
        words = " ".join(str(term) for term in plan.get("unapplied_terms") or []).split()
        return len(words) <= 1

    def _listable_by_table(self, request):
        """La entidad de la lista nombra una tabla del modelo («interconsultas»
        -> INTERCONSULTAS) que tiene un único conteo de registros (mismo modelo,
        tabla y expresión aunque se publique con varios nombres): ese indicador.
        None si no hay ninguno o hay varios (se mantiene la contrapregunta)."""
        from src.semantic.detail_list import compact, listable_entity, words
        from src.semantic.request_phrases import singular

        builder = self.query_plan_builder
        entity_word = str(request.get("entity") or "")
        forms = {entity_word, singular(entity_word)}
        question_words = set(request.get("question_words") or ())
        question_words |= {singular(word) for word in question_words}
        # La pregunta nombra la tabla con todas sus palabras («interconsultas»
        # -> INTERCONSULTAS; «pacientes en ESPERA» -> EN_ESPERA). Primero las
        # que además son la entidad de la lista; si varias cumplen, ninguna.
        by_entity, by_words = {}, {}
        for metric in getattr(builder, "metrics", None) or []:
            if metric.get("validation_status") not in (None, "approved") or not metric.get("metric_id"):
                continue
            table_words = {singular(word) for word in words(metric.get("table"))} | words(metric.get("table"))
            content = {word for word in words(metric.get("table")) if len(word) >= 4}
            covered = bool(content) and all(
                word in question_words or singular(word) in question_words for word in content
            )
            if not covered:
                continue
            try:
                entity = listable_entity(metric, builder, counting_only=True)
            except Exception:
                entity = None
            if not entity:
                continue
            key = (compact(metric.get("semantic_model")), compact(entity.get("table")),
                   compact(entity.get("function")), compact(entity.get("column")))
            target = by_entity if forms & table_words else by_words
            target.setdefault(key, metric)
        # Candidatos en orden (tabla de la entidad, luego tabla nombrada con
        # sus palabras); cada grupo solo cuenta si tiene un único conteo. Quien
        # llama arma el plan y lo descarta si deja la pregunta sin explicar.
        chosen = [next(iter(group.values())) for group in (by_entity, by_words) if len(group) == 1]
        for metric in chosen:
            self._think(
                "Pregunta de listado: indicador que permite listar",
                f"«{request['phrase']}» pide la lista de {entity_word}; ninguna opción la cuenta, pero la tabla "
                f"{metric.get('table')} ({metric.get('semantic_model')}) tiene un único conteo de registros: "
                f"{metric.get('label')} ({metric.get('model_expression') or metric.get('dax_expression')}); "
                "se usa si el plan con ese indicador explica la pregunta",
            )
        return chosen

    def _detail_listing(self, plan, total):
        """Lista de las entidades que cuenta el indicador («qué camas están
        disponibles», «lista de camas bloqueadas», «cuántas camas hay
        disponibles en ...» con pocas camas). None si la pregunta no la pide;
        si no se puede traer, el total se responde igual y se dice por qué."""
        from src.semantic.detail_list import (
            consistency, detail_max_rows, detail_rows, detail_timeout_s, plan_detail,
        )

        try:
            spec = plan_detail(plan, self.query_plan_builder)
        except Exception as error:
            self._think("Listado de detalle", f"no se pudo planear: {type(error).__name__}: {error}")
            return None
        if spec.get("status") == "not_requested":
            return None
        request = spec.get("request") or {}
        strength = request.get("strength")
        cap = detail_max_rows()
        base = {
            "strength": strength, "entity_word": request.get("entity"), "cue": request.get("phrase"),
            "cap": cap, "total": total,
        }
        if spec.get("status") != "ready":
            self._think(
                "Listado de detalle",
                f"la pregunta pide una lista («{request.get('phrase')}»), pero el indicador "
                f"{(plan.get('metric') or {}).get('label')} no cuenta registros identificables "
                f"({spec.get('reason')}): se responde solo el total",
            )
            # Pedida de forma explícita («lista de…»): se dice por qué no hay lista.
            return {**base, "status": "not_listable", "reason": spec.get("reason")} if strength == "explicit" else None
        columns = spec["columns"]
        detail = {
            **base, "columns": columns, "source": spec.get("source"), "visual": spec.get("visual"),
            "excluded_private": spec.get("excluded_private") or [],
            "entity": spec.get("entity"), "entity_shown": spec.get("entity_shown"),
        }
        header_text = ", ".join(
            c["header"] + (" (oculta: identificador técnico)" if c.get("hidden") else "") for c in columns
        )
        origin = (
            f"tabla de detalle del tablero ({spec.get('visual')})" if spec.get("source") == "catalogo"
            else "reglas (entidad contada, ubicación y filtros)"
        )
        private_line = (
            "columnas con datos de personas excluidas: " + ", ".join(detail["excluded_private"])
            + " (mostrarlas es decisión del propietario: POWERBI_DETAIL_ALLOWED_COLUMNS)"
            if detail["excluded_private"] else None
        )
        from src.chatbot.response_formatter import _to_number

        number = _to_number(total)
        if number is not None and number <= 0:
            self._think("Listado de detalle", "el total es 0: no hay filas que listar")
            return {**detail, "status": "empty", "rows": []}
        if strength == "soft" and number is not None and number > cap:
            self._think(
                "Listado de detalle",
                f"columnas: {header_text} · origen: {origin}",
                f"el total ({number:g}) supera el tope de {cap} filas (POWERBI_DETAIL_MAX_ROWS) y la "
                "pregunta no pide la lista de forma explícita: se da el total y se ofrece filtrar "
                "(sin consulta extra)",
                private_line,
            )
            return {**detail, "status": "too_long", "rows": []}

        generator = getattr(self.query_plan_dax_generator, "generate_detail", None)
        if not callable(generator):
            return None
        limit = cap + 1
        dax_result = generator(plan, columns, limit)
        if dax_result.get("status") != "generated":
            self._think("Listado de detalle", f"no se generó la consulta: {dax_result.get('reason')}")
            return {**detail, "status": "error", "error": dax_result.get("reason"), "rows": []}
        validator = getattr(self.dax_validator, "validate_detail_query", None)
        if callable(validator):
            try:
                validation = validator(
                    dax_result["dax"], columns, limit, semantic_model=plan.get("semantic_model"),
                )
            except Exception as error:
                validation = {"valid": False, "errors": [f"{type(error).__name__}: {error}"]}
            if not validation.get("valid"):
                self._think(
                    "Listado de detalle", "consulta rechazada por el validador DAX",
                    *[str(e) for e in validation.get("errors") or []],
                )
                return {**detail, "status": "error", "error": "dax_rejected", "rows": [],
                        "dax": dax_result["dax"]}
        self._activity("Trayendo la lista de detalle de Power BI")
        try:
            powerbi_result = self.powerbi_provider.execute_dax(
                dax=dax_result["dax"], semantic_model=plan.get("semantic_model"),
                timeout_s=detail_timeout_s(),
            )
        except TypeError:
            powerbi_result = self.powerbi_provider.execute_dax(
                dax=dax_result["dax"], semantic_model=plan.get("semantic_model"),
            )
        except Exception as error:
            powerbi_result = {"status": "error", "error": f"{type(error).__name__}: {error}"}
        detail["dax"] = dax_result["dax"]
        if powerbi_result.get("status") != "success":
            reason = "tiempo agotado" if powerbi_result.get("timed_out") else "error de Power BI"
            self._think(
                "Listado de detalle",
                f"columnas: {header_text} · tope {cap} filas · origen: {origin}",
                f"la consulta del listado falló ({reason}): se responde el total sin la lista",
                "DAX: " + " ".join(str(dax_result["dax"]).split()),
                f"error: {short(powerbi_result.get('error') or powerbi_result.get('message'), 300)}",
            )
            return {**detail, "status": "error", "error": reason, "rows": []}
        cells, counts, truncated, all_counts = detail_rows(powerbi_result.get("rows") or [], columns, cap)
        check = consistency(total, all_counts, truncated, (spec.get("entity") or {}).get("function"))
        detail.update({
            "status": "ok", "rows": cells, "counts": counts, "truncated": truncated,
            "consistency": check,
            # Varias filas iguales (la entidad no se muestra o se repite): se
            # agrega la cantidad de cada fila. Con una suma (PRODUCTOS
            # VENCIDOS = SUM(cantidad)) la cantidad de cada fila es el dato.
            "show_counts": bool((spec.get("entity") or {}).get("aggregate"))
            or any(c is not None and c != 1 for c in counts),
            "value_header": (
                str((plan.get("metric") or {}).get("label") or "CANTIDAD")
                if (spec.get("entity") or {}).get("aggregate") else "CANTIDAD"
            ),
        })
        if check == "constant":
            detail.update({"status": "inconsistent", "rows": [], "counts": []})
        self._think(
            "Listado de detalle",
            f"columnas: {header_text} · origen: {origin}",
            f"filas: {len(cells)}{' (recortada: hay más)' if truncated else ''} · tope {cap} "
            "(POWERBI_DETAIL_MAX_ROWS)",
            {
                "ok": "coincide con el total", "mismatch": "las filas NO suman el total (se avisa)",
                "constant": "la medida da el mismo valor en cada fila (no responde al detalle): no se muestra la lista",
                "unknown": "no se puede comparar con el total (lista recortada o total no numérico)",
            }[check],
            private_line,
            "DAX: " + " ".join(str(dax_result["dax"]).split()),
        )
        return detail

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
                # La tabla y la expresión real de la medida: sin ellas MedGemma
                # adivinaba qué se cuenta («ocupación del personal» para camas).
                "table": metric.get("table"),
                "model_expression": metric.get("model_expression"),
                "description": metric.get("description"),
                "report": report, "page": page,
                "visuals": ", ".join(visuals[:4]),
                "semantic_model": metric.get("semantic_model"),
            })
        self._activity(f"MedGemma está describiendo {len(options)} opciones")
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
            "descripciones descartadas por mencionar algo que el indicador no tiene: " + "; ".join(
                f"{key} ({', '.join(words)})" for key, words in outcome["rejected"].items()
            ) if outcome.get("rejected") else None,
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

    # Nombre técnico: guion bajo (total_triage, Pac_act) o cifra pegada a la
    # palabra (PENDIENTES1).
    _TECHNICAL_LABEL_RE = re.compile(r"_|[^\W\d_]\d{1,2}$")

    def _readable_label(self, metric):
        """Etiqueta visible de una opción. Si la medida tiene un nombre técnico
        («PENDIENTES1», «total_triage», «Pac_act») se muestra el título de su
        visual (si el tablero lo trae) o el nombre sin guiones bajos ni la
        cifra pegada («PENDIENTES», «Total triage»). El id no cambia."""
        label = str(metric.get("label") or "").strip()
        titles = []
        for appearance in metric.get("appearances") or []:
            title = str(appearance.get("visual_title") or "").strip()
            if title and title not in titles:
                titles.append(title)
        same = next(
            (title for title in titles if self._normalize_text(title) == self._normalize_text(label)),
            None,
        )
        if same:
            return same
        if not self._TECHNICAL_LABEL_RE.search(label):
            return label
        if titles:
            return titles[0]
        readable = re.sub(r"([^\W\d_])\d{1,2}$", r"\1", label)
        readable = re.sub(r"\s+", " ", readable.replace("_", " ")).strip()
        if readable and readable == readable.lower():
            readable = readable[0].upper() + readable[1:]
        return readable or label

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
            title = self._readable_label(metric)
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

    def _single_option_prompt(self, prompt, choice):
        """Con una sola opción real no se dice «varios indicadores» ni «¿es
        alguno de estos?»: se pregunta «¿Te refieres a X?»."""
        ask = f"¿Te refieres a {choice['label']}?"
        text = str(prompt or "").strip()
        if not text or text.startswith("Encontré varios indicadores"):
            return ask
        text = text.replace(
            "Estos son los más parecidos de ese tablero. ", "Encontré uno parecido en ese tablero. ",
        ).replace(
            "Estos son los más parecidos de otros tableros. ", "",
        )
        for plural in ("¿Es alguno de estos?", "¿Es alguna de estas?", "¿Cuál necesitas?"):
            if text.endswith(plural):
                return text[: -len(plural)] + ask
        return text

    def _clarification_response(self, choices, question=None, none_label=_NONE_LABEL):
        # `prompt` es solo la pregunta: la interfaz muestra las opciones como
        # botones con su descripción corta. `question` conserva además la
        # lista numerada para quien responde escribiendo. La última opción
        # («Ninguna de las anteriores») busca otros indicadores.
        prompt = question or "Encontré varios indicadores. ¿Cuál necesitas?"
        if len(choices) == 1:
            prompt = self._single_option_prompt(prompt, choices[0])
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
        if pending.get("composite"):
            return self._run_selected_composite(pending, choice)
        self._pending_query_plan = None
        self._think(
            "El usuario eligió una opción",
            f"{choice['label']} [{choice['id']}]",
            f"pregunta original: {pending['question']}",
        )
        self._activity("Armando la consulta con el indicador elegido")
        plan = self.query_plan_builder.build(
            pending["question"], selected_metric_id=choice["id"]
        )
        self._trace_plan(plan, "Query Plan con el indicador elegido")
        if plan.get("status") == "ready":
            self._note_same_measure_pages(plan)
            return self._execute_query_plan(plan)
        return self._query_plan_failure(plan)

    def select_clarification_option(self, option_id, label=None):
        """Resuelve una contrapregunta pendiente con la opción elegida (botón).
        `label` (texto del botón) solo se usa en el razonamiento."""
        def run():
            result = self._select_clarification_option(option_id)
            self._remember_success(result)
            return result

        top_level = self._trace is None
        deferred = None
        if top_level:
            self._turn_interpretation = None
            deferred = getattr(self, "_deferred_context_message", None)
            self._deferred_context_message = None
        result = self._traced(
            "option", f"{label} [{option_id}]" if label else option_id, run,
        )
        if top_level:
            self._record_turn(label or option_id, result, via="botón")
            if (
                deferred and isinstance(result, dict) and result.get("status") == "success"
                and result.get("route") == "powerbi"
            ):
                # «y en el mes pasado?» llegó con la contrapregunta pendiente:
                # con el indicador ya elegido se responde ese mensaje.
                self._applying_deferred = (deferred, label or option_id)
                try:
                    followed = self.process(deferred)
                finally:
                    self._applying_deferred = None
                if isinstance(followed, dict) and followed.get("status") in ("success", "empty_result"):
                    followed["applied_after_choice"] = label or option_id
                    return followed
        return result

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

    def _board_named_in_reply(self, message, choices):
        """«el de referencia» cuando ninguna opción es de Referencia: devuelve
        el tablero/página conocido que nombra la respuesta (entrada del
        enrutador: semantic_model, report, name...) o None si la respuesta no
        nombra un tablero o si alguna opción ya es de ese tablero."""
        router = getattr(self.query_plan_builder, "source_router", None)
        mentions_of = getattr(router, "board_mentions", None)
        norm = self._normalize_text(message)
        match = self._LOCATION_REPLY.match(norm)
        rest = (match.group("rest") if match else norm).strip()
        if not callable(mentions_of) or not rest or len(rest.split()) > 5:
            return None
        try:
            mentions = mentions_of(f"tablero {rest}") or []
        except Exception:
            return None
        contexts = [
            context for mention in mentions
            # El nombre debe cubrir toda la respuesta («el de referencia»), no
            # una palabra suelta de una frase más larga.
            if len(mention.get("tokens") or []) == len(rest.split())
            for context in mention.get("contexts") or []
        ]
        if not contexts:
            return None
        models = {self._normalize_text(context.get("semantic_model")) for context in contexts}
        for choice in choices:
            detail = self._normalize_text(choice.get("detail"))
            if any(model and model in detail for model in models):
                return None
        return contexts[0]

    def _search_in_named_board(self, pending, board):
        """La respuesta a la contrapregunta nombra un tablero que no es de
        ninguna opción: se dice y se busca la pregunta original en ese tablero.
        Si allí tampoco hay un indicador, se vuelven a ofrecer las opciones."""
        name = board.get("report") or board.get("semantic_model") or board.get("name")
        notice = f"Ninguna de las opciones es {self._board_phrase(name, 'del')}."
        model = self._normalize_text(board.get("semantic_model"))
        self._think(
            "La respuesta nombra un tablero que no es de ninguna opción",
            f"tablero: {name}; se busca «{pending['question']}» en ese tablero",
        )
        question = f"{pending['question']} en el tablero {board.get('name') or name}"
        self._pending_query_plan = None
        response, _ = self._run_query_plan(question, pending.get("intent") or {}, "board_from_reply")
        status = response.get("status")
        if status in ("success", "empty_result"):
            plan = response.get("query_plan")
            if isinstance(plan, dict):
                plan["notes"] = [f"{notice} Lo busqué en ese tablero.", *(plan.get("notes") or [])]
            return response
        options = response.get("clarification_options") or []
        if status == "needs_clarification" and any(
            model and model in self._normalize_text(option.get("detail")) for option in options
        ):
            response["prompt"] = f"{notice} {response.get('prompt') or ''}".strip()
            response["question"] = f"{notice} {response.get('question') or ''}".strip()
            return response
        # Tampoco está en ese tablero (o solo se ofrecerían indicadores de
        # otros tableros): se dice y se vuelven a ofrecer las opciones.
        self._think(
            "Tampoco hay un indicador parecido en ese tablero",
            "se vuelven a ofrecer las opciones anteriores",
        )
        self._pending_query_plan = pending
        return self._clarification_response(
            pending["choices"],
            f"{notice} En ese tablero tampoco encontré un indicador para "
            f"«{str(pending['question']).strip(' ¿?')}». ¿Es alguna de estas?",
            none_label=pending.get("none_label") or self._NONE_LABEL,
        )

    @staticmethod
    def _board_phrase(name, article="el"):
        """«el tablero NAOS» / «el TABLERO NAOS» (sin repetir «tablero»)."""
        name = str(name or "").strip()
        if name.lower().startswith("tablero"):
            return f"{article} {name}"
        return f"{article} tablero {name}"

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

    # Pregunta completa: empieza con un interrogativo seguido de al menos dos
    # palabras («cuántas atenciones de urgencias hubo en 2024») o con una
    # petición («me piden...», «se me ha solicitado...», «necesito saber...»).
    # «cuál de las dos», «cuál es la primera»: siguen siendo respuestas.
    _FULL_QUESTION_RE = re.compile(
        r"^(?:y\s+)?(?:"
        r"(?:cuant[oa]s?|que(?!\s+sea\s)|como|donde|cuando|quien(?:es)?|por\s+que|para\s+que)\s+\S+\s+\S+"
        r"|cual(?:es)?\s+(?!de\s|es\s+(?:la|el)\s+(?:primer|segund|tercer|ultim))\S+\s+\S+\s+\S+"
        r"|(?:a\s+mi\s+)?(?:se\s+)?(?:me|nos)\s+(?:ha|han|piden|pidieron|solicitan|solicitaron)\s"
        r"|(?:de\s+\S+\s+)?se\s+(?:me|nos)\s+(?:ha|han)\s"
        r"|(?:necesito|necesitamos|quisiera|quiero|queremos)\s+(?:saber|conocer|reportar|consultar)\s"
        r")"
    )

    def _is_new_full_question(self, message):
        return bool(self._FULL_QUESTION_RE.match(self._normalize_text(message)))

    # Palabras con las que se responde a una contrapregunta («quiero la de...
    # del tablero..., por favor», «la primera»): no son una petición nueva.
    _REPLY_WORDS = {
        "la", "el", "los", "las", "lo", "de", "del", "en", "a", "al", "y", "con", "que", "me",
        "mi", "un", "una", "uno", "es", "esa", "ese", "esta", "este", "eso", "opcion", "numero",
        "num", "quiero", "prefiero", "seria", "sea", "dame", "elijo", "escojo", "tablero",
        "informe", "pagina", "modelo", "reporte", "por", "favor", "porfa", "gracias", "ok", "si",
        "bueno", "pues", "entonces", "mejor", "otra", "otro", "primera", "primero", "segunda",
        "segundo", "tercera", "tercero", "cuarta", "cuarto", "quinta", "quinto", "ultima",
        "ultimo", "da", "indicador", "dato", "valor", "total",
    }

    def _reply_adds_new_request(self, message, choice):
        """¿El mensaje, además de nombrar la opción, pide otra cosa? «cirugías
        programadas de urología en 2024» con la opción «Cirugías programadas»
        es una pregunta nueva (urología, 2024), no la elección de esa opción
        para la pregunta anterior. Devuelve las palabras de más (o [])."""
        from src.semantic.query_plan_builder import _tokens_match_loosely, canonical_token

        option_tokens = {
            canonical_token(token)
            for token in self._normalize_text(f"{choice.get('label') or ''} {choice.get('detail') or ''}").split()
        }
        extra = []
        for word in self._normalize_text(message).split():
            if word in self._REPLY_WORDS or (word.isdigit() and len(word) <= 2):
                continue
            token = canonical_token(word)
            if any(_tokens_match_loosely(token, other) for other in option_tokens):
                continue
            extra.append(word)
        has_period = any(re.fullmatch(r"(?:19|20)\d{2}", word) for word in extra) or any(
            word in self._MONTH_WORDS for word in extra
        )
        if has_period or len([word for word in extra if len(word) >= 3]) >= 2:
            return extra
        return []

    def _defer_context_message(self, message, pending):
        """«y en el mes pasado?», «compáralo con el año anterior», «los de
        hospitalización» mientras la contrapregunta sigue pendiente: el mensaje
        depende de la pregunta pendiente (aún sin indicador), no es una pregunta
        nueva. Se vuelve a preguntar y, al elegir la opción, se responde la
        consulta con ese cambio (antes se descartaba la contrapregunta y el
        mensaje se respondía solo, sin contexto)."""
        try:
            analysis = contextual_rewriter.analyze(message)
        except Exception:
            return None
        cues = analysis.get("cues") or []
        if analysis.get("courtesy") or not cues or analysis.get("correction"):
            return None
        complement = analysis.get("complement") or ""
        if self._named_metric_words(complement):
            return None
        if complement.strip() and self._resolves_to_metric(complement):
            return None
        self._deferred_context_message = str(message).strip()
        self._think(
            "Mensaje que depende de la contrapregunta pendiente",
            f"«{message.strip()}» se refiere a «{pending['question']}» ({', '.join(cues)}), pero aún "
            "falta elegir el indicador",
            "se vuelve a preguntar; al elegir la opción se responde la consulta con ese cambio",
        )
        return self._clarification_response(
            pending["choices"],
            f"Para responder «{message.strip()}» primero necesito saber cuál indicador de "
            f"«{pending['question']}» necesitas:",
            none_label=pending.get("none_label") or self._NONE_LABEL,
        )

    _MONTH_WORDS = {
        "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
        "setiembre", "octubre", "noviembre", "diciembre", "hoy", "ayer", "semana", "mes", "ano",
    }

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
        # Una pregunta completa es una pregunta nueva aunque comparta palabras
        # con alguna opción («cuántas atenciones de urgencias hubo en 2024»
        # frente a la opción PACIENTES INTUBADOS EN URGENCIAS): antes se
        # elegía esa opción y se respondía la pregunta ANTERIOR.
        norm = self._normalize_text(message)
        typed = getattr(self, "_turn_message", None) or message
        if (self._is_new_full_question(message) or self._is_new_full_question(typed)) and not any(
            self._normalize_text(choice["label"]) == norm for choice in choices
        ):
            self._think(
                "Pregunta nueva: se descarta la contrapregunta pendiente",
                f"«{message}» es una pregunta completa, no una respuesta a las opciones; se "
                "resuelve desde cero (sin el indicador, el tablero ni las opciones descartadas "
                f"de «{pending['question']}»)",
            )
            self._pending_query_plan = None
            return None
        # Primero intentar emparejar una opción: una respuesta larga puede
        # ser una opción y no una pregunta nueva.
        selected = self._match_query_plan_choice(message, choices)
        extra = self._reply_adds_new_request(message, selected) if selected is not None else []
        if extra:
            self._think(
                "Pregunta nueva: se descarta la contrapregunta pendiente",
                f"«{message}» nombra la opción {selected['label']}, pero pide además "
                f"{', '.join(f'«{word}»' for word in extra)}: es una pregunta nueva, no la elección "
                f"de esa opción para «{pending['question']}»; se resuelve desde cero",
            )
            self._pending_query_plan = None
            return None
        if selected is None:
            board = self._board_named_in_reply(message, choices)
            if board is not None:
                return self._search_in_named_board(pending, board)
            deferred = self._defer_context_message(message, pending)
            if deferred is not None:
                return deferred
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

    def _qualifier_prompt(self, plan, words):
        """Contrapregunta cuando una palabra de la pregunta forma parte del
        nombre de otros indicadores. Solo se citan las palabras que de verdad
        aparecen en esos nombres («urgencias» en PACIENTES INTUBADOS EN
        URGENCIAS), nunca el resto sin interpretar («solicitado cada»)."""
        from src.semantic.query_plan_builder import _tokens_match_loosely, canonical_token

        candidates = (plan.get("metric_resolution") or {}).get("candidates") or []
        names = []
        for item in candidates:
            metric = item.get("metric") or {}
            names.append(" ".join(str(part or "") for part in (
                metric.get("label"), item.get("matched_name"),
                *[a.get("visual_title") for a in metric.get("appearances") or []],
            )))
        name_tokens = {
            canonical_token(token)
            for name in names for token in self._normalize_text(name).split() if len(token) >= 4
        }
        cited = []
        for word in str(words).split():
            token = canonical_token(self._normalize_text(word))
            if len(token) >= 4 and any(_tokens_match_loosely(token, other) for other in name_tokens):
                if word not in cited:
                    cited.append(word)
        if cited:
            quoted = " y ".join(f"«{word}»" for word in cited)
            verb = "aparecen" if len(cited) > 1 else "aparece"
            return f"{quoted} {verb} en el nombre de varios indicadores. ¿Cuál necesitas?"
        return "Encontré varios indicadores que pueden responder tu pregunta. ¿Cuál necesitas?"

    def _resolution_prompt(self, plan):
        """Texto de la contrapregunta según por qué no se eligió un indicador."""
        reason = plan.get("reason")
        words = str(plan.get("unresolved_text") or "").strip()
        if reason == "same_name_in_several_boards":
            return "Ese indicador existe en varios tableros. ¿Cuál necesitas?"
        if reason == "similar_name_in_several_boards":
            return (
                "Hay varios indicadores con un nombre casi igual y la pregunta no indica "
                "cuál. ¿Cuál necesitas?"
            )
        if reason == "options_from_named_board":
            board = plan.get("named_report") or "ese tablero"
            return f"Estos son los indicadores del tablero {board} más parecidos a tu pregunta. ¿Cuál necesitas?"
        if reason == "options_from_named_page":
            page = plan.get("named_page") or "esa página"
            if (plan.get("named_page_models") or 1) > 1:
                return (
                    f"La página {page} existe en varios tableros. Estos son sus indicadores "
                    "principales. ¿Cuál necesitas?"
                )
            report = plan.get("named_page_report")
            where = f"la página {page}" + (f" del tablero {report}" if report else "")
            return f"Estos son los indicadores de {where}. ¿Cuál necesitas?"
        if reason == "metric_not_in_named_page":
            page = plan.get("named_page") or "esa página"
            report = plan.get("named_page_report")
            where = f"la página {page}" + (f" del tablero {report}" if report else "")
            found = plan.get("found_elsewhere") or {}
            suggestions = (plan.get("metric_resolution") or {}).get("suggestions") or []
            if found and len(suggestions) == 1 and (
                (suggestions[0].get("metric") or {}).get("metric_id") == found.get("metric_id")
            ):
                return (
                    f"En {where} no encontré ese indicador. Lo encontré en otra página. ¿Es este?"
                )
            return (
                f"En {where} no encontré ese indicador. Estos son los más parecidos de esa "
                "página. ¿Es alguno de estos?"
            )
        if reason == "qualifier_matches_other_metrics" and words:
            return self._qualifier_prompt(plan, words)
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
            offered = (plan.get("metric_resolution") or {}).get("candidates") or suggestions
            if len(offered) > 1:
                return (
                    f"En el tablero {board} no encontré ese indicador. Estos son los más "
                    "parecidos de otros tableros. ¿Es alguno de estos?"
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

    # ---------------- compuestas: filtros comunes y notas ----------------
    @staticmethod
    def _filter_identity(item):
        return (
            item.get("type"), str(item.get("table")).casefold(), str(item.get("column")).casefold(),
            str(item.get("value")), str(item.get("values")), str(item.get("start")),
            str(item.get("end")), str(item.get("label")),
        )

    def _composite_filters(self, plans):
        """(filtros comunes a todas las medidas, {índice: filtros propios})."""
        identities = [
            {self._filter_identity(item) for item in plan.get("filters") or []}
            for plan in plans
        ]
        shared = set.intersection(*identities) if identities else set()
        common = [
            item for item in (plans[0].get("filters") or [])
            if self._filter_identity(item) in shared
        ] if plans else []
        own = {
            index: [
                item for item in plan.get("filters") or []
                if self._filter_identity(item) not in shared
            ]
            for index, plan in enumerate(plans)
        }
        return common, own

    @staticmethod
    def _own_filters_text(filters):
        text = format_filters_line(filters)
        return text[len("Filtros: "):] if text.startswith("Filtros: ") else text

    def _composite_notes(self, composite, plans, failed_labels):
        """Notas de la respuesta compuesta: las de cada sub-plan, la división
        y las partes que no se pudieron responder."""
        notes = []
        for plan in plans:
            notes.extend(str(note) for note in plan.get("notes") or [] if note)
        notes.extend(str(note) for note in composite.get("notes") or [] if note)
        unresolved = composite.get("unresolved") or []
        if unresolved:
            notes.append(
                "No pude interpretar " + ", ".join(f"«{w}»" for w in unresolved)
                + "; respondí solo las partes que identifiqué."
            )
        if failed_labels:
            notes.append(
                "No pude resolver: " + ", ".join(f"«{label}»" for label in failed_labels)
                + "; respondí solo las partes que identifiqué."
            )
        return list(dict.fromkeys(notes))

    def _execute_composite(self, composite):
        """Ejecuta cada medida del plan compuesto y arma un único resultado."""
        if composite.get("grouped") or any(
            item["plan"].get("mode") == "grouped" for item in composite["items"]
        ):
            return self._execute_composite_table(composite)
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
            value = self._row_value(rows[0]) if rows else None
            if item["kind"] == "share":
                if value is not None:
                    value = float(value)  # fracción (0,125 = 12,5 %)
                measure = {
                    "label": item["label"], "value": value,
                    "format": "percent", "unit": "%", "dax": dax_result.get("dax"),
                }
            else:
                fmt = (plan.get("metric") or {}).get("format_string")
                measure = {
                    "label": item["label"], "value": value,
                    "format": fmt if fmt and "%" in str(fmt) else "number",
                    "unit": None, "dax": dax_result.get("dax"),
                }
            measures.append(measure)
            executed.append((item, plan, dax_result, powerbi_result, rows, measure))

        if not executed:
            return last_failure
        item, plan, dax_result, powerbi_result, rows, _ = executed[0]
        if all(m["value"] is None for m in measures):
            return {
                "status": "empty_result", "route": "powerbi",
                "stage": "query_plan_result", "query_plan": plan,
                "dax": dax_result.get("dax"), "details": powerbi_result,
            }

        plans = [e[1] for e in executed]
        common, own = self._composite_filters(plans)
        for index, measure in enumerate(measures):
            extra = self._own_filters_text(own.get(index))
            if extra:
                measure["label"] = f"{measure['label']} ({extra})"
        all_failed = list(composite.get("failed_labels", [])) + failed_labels
        answer = self._composite_answer(
            plan, measures, composite.get("unresolved"), all_failed,
        )
        base_plan = dict(executed[0][1])
        base_plan["notes"] = self._composite_notes(composite, plans, all_failed)
        metric = base_plan.get("metric", {})
        return {
            "status": "success",
            "route": "powerbi",
            "result_type": "scalar",
            "question": composite.get("question"),
            "report": base_plan.get("report"),
            "dashboard": base_plan.get("dashboard"),
            "semantic_model": base_plan.get("semantic_model"),
            "metric": measures[0]["label"],
            "metric_id": metric.get("metric_id"),
            "metric_source": metric.get("source_type"),
            "value": measures[0]["value"],
            "measures": measures,
            "rows": rows,
            "filters": common,
            "business_filters": [f for f in common if f.get("type") == "categorical"],
            "unapplied_terms": list(dict.fromkeys(
                term for p in plans for term in p.get("unapplied_terms") or []
            )),
            "group_by": base_plan.get("group_by", []),
            "answer": answer,
            "dax": dax_result.get("dax"),
            "dax_queries": [e[2].get("dax") for e in executed],
            "powerbi": powerbi_result,
            "query_plan": base_plan,
            "query_plans": plans,
            "source_context": base_plan.get("source_context"),
            "composite": True,
        }

    # ---------------- compuestas en tabla (varias columnas) ----------------
    @staticmethod
    def _group_key(row):
        """Valores de agrupación de una fila (sin las columnas de medida)."""
        return tuple(
            value for key, value in row.items()
            if not re.search(r"__(?:value|m\d+|orden)", str(key).lower())
        )

    def _composite_table_rows(self, composite):
        """Ejecuta la tabla compuesta. Devuelve (claves en orden, columnas,
        consultas, fallidas, último fallo). Una sola consulta multi-medida si
        todas son del mismo modelo; si no (o si falla), una por medida y se
        unen por el valor de agrupación."""
        items = composite["items"]
        models = {self._normalize_text(i["plan"].get("semantic_model")) for i in items}
        queries, failed, last_failure = [], [], None
        if len(models) == 1:
            dax_result = self.query_plan_dax_generator.generate_multi(
                [{"kind": i["kind"], "plan": i["plan"]} for i in items]
            )
            powerbi_result = None
            if dax_result.get("status") == "generated":
                powerbi_result = self.powerbi_provider.execute_dax(
                    dax=dax_result.get("dax"),
                    semantic_model=items[0]["plan"].get("semantic_model"),
                )
            self._trace_dax(
                "Consulta a Power BI: " + " + ".join(i["label"] for i in items),
                dax_result, powerbi_result,
            )
            if powerbi_result is not None and powerbi_result.get("status") == "success":
                rows = powerbi_result.get("rows", []) or []
                keys, columns = [], [{} for _ in items]
                for row in rows:
                    key = self._group_key(row)
                    keys.append(key)
                    for index, name in enumerate(dax_result["columns"]):
                        columns[index][key] = next(
                            (v for k, v in row.items() if str(k).lower().endswith(f"[{name}]") or str(k) == name),
                            None,
                        )
                queries.append((dax_result, powerbi_result, rows))
                return keys, columns, queries, failed, None
            self._think(
                "La consulta multi-medida no se pudo usar",
                "se consulta cada medida por separado y se unen por el valor de agrupación",
            )

        keys, columns = [], []
        for item in items:
            plan = item["plan"]
            if item["kind"] == "share":
                dax_result = self.query_plan_dax_generator.generate_share(plan)
            else:
                dax_result = self.query_plan_dax_generator.generate_ranked(plan)
            if dax_result.get("status") != "generated":
                self._trace_dax(f"Consulta a Power BI: {item['label']}", dax_result)
                last_failure = self._composite_failure("query_plan_dax", plan, dax_result)
                failed.append(item["label"])
                columns.append(None)
                continue
            powerbi_result = self.powerbi_provider.execute_dax(
                dax=dax_result.get("dax"), semantic_model=plan.get("semantic_model"),
            )
            self._trace_dax(f"Consulta a Power BI: {item['label']}", dax_result, powerbi_result)
            if powerbi_result.get("status") != "success":
                last_failure = self._composite_failure(
                    "query_plan_powerbi", plan, dax_result, powerbi_result
                )
                failed.append(item["label"])
                columns.append(None)
                continue
            rows = powerbi_result.get("rows", []) or []
            column = {}
            for row in rows:
                key = self._group_key(row)
                if key not in column:
                    column[key] = self._row_value(row)
                if key not in keys:
                    keys.append(key)
            columns.append(column)
            queries.append((dax_result, powerbi_result, rows))
        return keys, columns, queries, failed, last_failure

    def _execute_composite_table(self, composite):
        """Tabla con una columna por medida («programadas y realizadas por
        especialidad», «peso y participación por servicio»)."""
        items = composite["items"]
        keys, columns, queries, failed, last_failure = self._composite_table_rows(composite)
        if not queries:
            return last_failure
        kept = [(item, column) for item, column in zip(items, columns) if column is not None]
        base_plan = dict(kept[0][0]["plan"])
        dax_result, powerbi_result, rows = queries[0]
        if not keys or all(
            self._is_blank_value(column.get(key)) for _, column in kept for key in keys
        ):
            return {
                "status": "empty_result", "route": "powerbi",
                "stage": "query_plan_result", "query_plan": base_plan,
                "dax": dax_result.get("dax"), "details": powerbi_result,
            }

        plans = [item["plan"] for item, _ in kept]
        common, own = self._composite_filters(plans)
        groups = base_plan.get("group_by") or []
        headers = [g.get("label") or g.get("column") for g in groups] or ["Grupo"]
        measures = []
        for index, (item, _) in enumerate(kept):
            label = item["label"]
            extra = self._own_filters_text(own.get(index))
            if extra:
                label = f"{label} ({extra})"
            fmt = "percent" if item["kind"] == "share" else (item["plan"].get("metric") or {}).get("format_string")
            measures.append({"label": label, "format": fmt, "kind": item["kind"]})
            headers.append(label)

        def cell(value, measure):
            if self._is_blank_value(value):
                return ""
            if measure["kind"] == "share":
                return f"{self._fmt_es(float(value) * 100, 2)} %"
            text = format_value_es(value, measure["label"], measure["format"])
            return text if text is not None else str(value)

        def clean(value):
            return "" if value is None else str(value).replace("|", "\\|")

        lines = [
            "| " + " | ".join(clean(h) for h in headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        for key in keys[:50]:
            labels = list(key)[:len(headers) - len(measures)]
            labels += [""] * (len(headers) - len(measures) - len(labels))
            values = [cell(column.get(key), m) for (_, column), m in zip(kept, measures)]
            lines.append("| " + " | ".join(clean(v) for v in [*labels, *values]) + " |")
        if len(keys) > 50:
            lines.append("")
            lines.append(f"Mostrando 50 de {len(keys)} filas.")

        all_failed = list(composite.get("failed_labels", [])) + failed
        base_plan["notes"] = self._composite_notes(composite, plans, all_failed)
        metric = base_plan.get("metric", {})
        return {
            "status": "success",
            "route": "powerbi",
            "result_type": "table",
            "question": composite.get("question"),
            "report": base_plan.get("report"),
            "dashboard": base_plan.get("dashboard"),
            "semantic_model": base_plan.get("semantic_model"),
            "metric": " y ".join(m["label"] for m in measures),
            "metric_id": metric.get("metric_id"),
            "metric_source": metric.get("source_type"),
            "value": None,
            "measures": measures,
            "rows": rows,
            "total_rows": len(keys),
            "filters": common,
            "business_filters": [f for f in common if f.get("type") == "categorical"],
            "unapplied_terms": list(dict.fromkeys(
                term for p in plans for term in p.get("unapplied_terms") or []
            )),
            "group_by": base_plan.get("group_by", []),
            "answer": "\n".join(lines),
            "dax": dax_result.get("dax"),
            "dax_queries": [q[0].get("dax") for q in queries],
            "powerbi": powerbi_result,
            "query_plan": base_plan,
            "query_plans": plans,
            "source_context": base_plan.get("source_context"),
            "composite": True,
        }

    def _handle_composite(self, composite):
        """Ejecuta una compuesta o contrapregunta su parte ambigua.
        Devuelve (respuesta, estado_del_plan)."""
        if composite.get("status") == "composite":
            parts = composite.get("split_parts") or []
            self._think(
                "Pregunta compuesta (varias medidas o participación)",
                {
                    "share": "división: participación sobre el total",
                    "mentions": "división: indicadores nombrados unidos por «y»",
                    "coordination": "división: partes coordinadas ("
                    + " | ".join(f"«{p}»" for p in parts) + ")",
                }.get(composite.get("split")),
                *[f"{item['kind']}: {item['label']}"
                  + (f" ← «{item['part']}»" if item.get("part") else "")
                  for item in composite["items"]],
                "presentación: tabla con una columna por medida"
                if composite.get("grouped") else "presentación: un valor por medida",
                *[f"nota: {note}" for note in composite.get("notes") or []],
                *[f"sin interpretar: «{word}»" for word in composite.get("unresolved") or []],
                *[f"no resuelta: {label}" for label in composite.get("failed_labels") or []],
            )
            for item in composite["items"]:
                if item["plan"].get("composite_sub_question"):
                    self._think(
                        f"Sub-pregunta de «{item['label']}»",
                        f"«{item['plan']['composite_sub_question']}»",
                    )
                self._trace_plan(item["plan"], f"Plan de «{item['label']}»")
            for failure in composite.get("failures") or []:
                self._trace_plan(failure, "Parte no resuelta")
            return self._execute_composite(composite), "composite"

        context = composite.get("composite_context")
        if context:
            self._think(
                "Pregunta compuesta con una parte ambigua",
                f"parte: «{context.get('part_text')}»",
                "ya resueltas: " + ", ".join(context.get("ready_labels") or []) if context.get("ready_labels") else None,
                "se contrapregunta esa parte y luego se responde la pregunta completa",
            )
        else:
            self._think("Pregunta compuesta que no se pudo resolver")
        self._trace_plan(composite)
        response = self._query_plan_failure(composite)
        if (
            context and isinstance(response, dict)
            and response.get("status") == "needs_clarification"
            and self._pending_query_plan is not None
        ):
            self._pending_query_plan["composite"] = context
            old_prompt = response.get("prompt") or ""
            ready = context.get("ready_labels") or []
            prompt = (
                f"Para «{context.get('part_text')}» encontré varios indicadores"
                + (f" (ya identifiqué {', '.join(ready)})" if ready else "")
                + ". ¿Cuál necesitas?"
            )
            question = str(response.get("question") or "")
            response["prompt"] = prompt
            response["question"] = (
                prompt + question[len(old_prompt):] if old_prompt and question.startswith(old_prompt)
                else prompt
            )
        return response, composite.get("status")

    def _run_selected_composite(self, pending, choice):
        """Opción elegida para una parte de una pregunta compuesta: se arma de
        nuevo la compuesta completa con esa elección."""
        self._pending_query_plan = None
        context = pending["composite"]
        selections = {**(context.get("selections") or {}), context["part"]: choice["id"]}
        self._think(
            "El usuario eligió una opción de una pregunta compuesta",
            f"{choice['label']} [{choice['id']}] para «{context.get('part_text')}»",
            f"pregunta completa: {context['question']}",
        )
        composite = self.query_plan_builder.build_composite(
            context["question"], intent_result=pending.get("intent") or {},
            selections=selections,
        )
        if composite is None:
            plan = self.query_plan_builder.build(pending["question"], selected_metric_id=choice["id"])
            self._trace_plan(plan, "Query Plan con el indicador elegido")
            if plan.get("status") == "ready":
                return self._execute_query_plan(plan)
            return self._query_plan_failure(plan)
        return self._handle_composite(composite)[0]

    def _run_query_plan(self, question, intent_result, stage):
        """Query Plan completo (compuesto o simple). Devuelve (respuesta, estado_del_plan)."""
        self._activity("Buscando el indicador, los filtros y el periodo (Query Plan)")
        try:
            composite = self.query_plan_builder.build_composite(
                question, intent_result=intent_result
            )
            if composite is not None:
                return self._handle_composite(composite)
            plan = self.query_plan_builder.build(
                question=question, intent_result=intent_result,
            )
            self._trace_plan(plan, f"Query Plan ({stage})")
            listable, verify = self._listable_choice(question, plan)
            for metric in listable:
                trial = self.query_plan_builder.build(
                    question=question, intent_result=intent_result,
                    selected_metric_id=metric["metric_id"],
                )
                if verify and not self._plan_explains_question(trial):
                    self._think(
                        "Pregunta de listado: indicador descartado",
                        f"con {metric.get('label')} ({metric.get('semantic_model')}) quedan sin aplicar: "
                        + (", ".join(str(t) for t in trial.get("unapplied_terms") or []) or str(trial.get("status")))
                        + "; no es la tabla que pide la pregunta",
                    )
                    continue
                plan = trial
                if verify:
                    self._drop_listed_entity(question, plan)
                self._trace_plan(plan, "Query Plan con el indicador que permite listar")
                break
        except Exception as error:
            self._think("El Query Plan lanzó un error", f"{type(error).__name__}: {error}")
            return {
                "status": "error", "route": "powerbi", "stage": stage,
                "error": f"{type(error).__name__}: {error}",
            }, "error"
        if plan.get("status") == "ready":
            self._note_same_measure_pages(plan)
            return self._execute_query_plan(plan), "ready"
        return self._query_plan_failure(plan), plan.get("status")

    _PAGES_IN_NOTE = 8

    def _note_same_measure_pages(self, plan):
        """La MISMA medida (mismo modelo, tabla y expresión) publicada en varias
        páginas (p. ej. TIEMPO PROMEDIO GESTION FACTURA en cada área de Control
        Facturación): no se contrapregunta entre páginas; se responde una vez
        y la respuesta dice dónde aparece, porque cada página puede aplicar sus
        propios filtros de visual."""
        builder = self.query_plan_builder
        key_of = getattr(builder, "_logical_key", None)
        metric = plan.get("metric") or {}
        if not callable(key_of) or not metric.get("metric_id"):
            return
        key = key_of(metric)
        if not key[-1]:
            return  # sin expresión no se puede saber si es la misma medida
        places = []
        for other in getattr(builder, "metrics", None) or []:
            if other.get("validation_status") not in (None, "approved") or key_of(other) != key:
                continue
            for appearance in other.get("appearances") or []:
                page = str(appearance.get("page_display_name") or "").strip()
                report = str(appearance.get("report") or other.get("report") or "").strip()
                if page and (report, page) not in places:
                    places.append((report, page))
        if len(places) < 2:
            return
        # Con filtros o agrupación la respuesta ya está acotada a lo que se
        # pidió: la nota de páginas no aporta y solo alarga la respuesta.
        if plan.get("filters") or plan.get("group_by"):
            self._think(
                "La misma medida aparece en varias páginas",
                f"{metric.get('label')}: misma medida en {len(places)} páginas; la respuesta ya "
                "está filtrada o agrupada según la pregunta, así que no se agrega la nota de páginas",
            )
            return
        reports = list(dict.fromkeys(report for report, _ in places if report))
        pages = ", ".join(page for _, page in places[: self._PAGES_IN_NOTE])
        if len(places) > self._PAGES_IN_NOTE:
            pages += f" y {len(places) - self._PAGES_IN_NOTE} más"
        where = self._board_phrase(reports[0], "del") if len(reports) == 1 else "de varios tableros"
        note = (
            f"Este indicador aparece en {len(places)} páginas {where} ({pages}); "
            "es el valor general, sin los filtros propios de cada página."
        )
        notes = list(plan.get("notes") or [])
        if note not in notes:
            plan["notes"] = [*notes, note]
        self._think(
            "La misma medida aparece en varias páginas",
            f"{metric.get('label')}: misma medida (modelo, tabla y expresión) en {len(places)} páginas; "
            "se responde una vez con el valor general en lugar de contrapreguntar por página",
        )

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

    def _pages_without_metrics(self, question):
        """Páginas que la pregunta nombra al pedir un dato y que no tienen
        indicadores en los modelos (solo están en la documentación)."""
        finder = getattr(self.query_plan_builder, "named_page_without_metrics", None)
        if not callable(finder):
            return []
        try:
            pages = list(finder(question) or [])
        except Exception:
            return []
        if pages:
            self._think(
                "Página sin indicadores en los modelos",
                f"la pregunta pide un dato de la página {' / '.join(pages)}, que solo está en la "
                "documentación: se responde con ella y se dice que el indicador no está en los modelos",
            )
        return pages

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
                "report": plan.get("report") or plan.get("dashboard"),
                "filters": [dict(item) for item in plan.get("filters") or []],
                "group_by": [dict(item) for item in plan.get("group_by") or []],
                "ranking": dict(plan["ranking"]) if plan.get("ranking") else None,
                # Valor mostrado (para «de esos 33» y el desglose del total).
                "value": result.get("value") if result.get("result_type") == "scalar" else None,
                "metric_format": result.get("metric_format"),
                # Dónde está el indicador («¿y en qué tablero lo veo?»).
                "pages": self._metric_pages(metric),
            }
            return
        if status in ("needs_clarification", "empty_result", "error") or followup:
            return
        self._last_success = None

    # Referencias a la respuesta anterior: «de esos», «de esas 33», «de esta
    # cantidad», «del total anterior», «de los 33», «desglósalo por...»,
    # «ahora por...», «lo mismo en...».
    _ANAPHORA_RE = re.compile(
        r"(?<![a-z0-9])(?:"
        r"(?:de|entre|para|en|sobre)\s+(?:esos|esas|estos|estas|ellos|ellas|aquellos|aquellas)"
        r"(?:\s+\d+(?:\s\d{3})*(?:\s\d+)?(?![a-z0-9]))?"
        r"|(?:de|en|para|sobre)\s+(?:esta|esa|este|ese)\s+(?:cantidad|cifra|total|numero|valor|"
        r"resultado|dato|consulta|respuesta|indicador)"
        r"|(?:de|en|sobre)\s+(?:el|la)\s+(?:total|cifra|cantidad|resultado|valor|consulta|respuesta)\s+anterior"
        r"|del\s+(?:total|resultado|valor|dato)\s+anterior"
        r"|(?:de|entre)\s+(?:los|las)\s+\d+(?:\s\d{3})*(?:\s\d+)?(?![a-z0-9])"
        r"|desglos[a-z]*|discrimin[a-z]*"
        r"|ahora(?=\s+(?:por|en|de|del|para|solo|sin|con|segun)\s)"
        r"|lo\s+mismo|la\s+misma\s+(?:consulta|pregunta|cifra)"
        r")(?![a-z0-9])"
    )
    _CITED_NUMBER_RE = re.compile(
        r"(?<![a-z0-9])(?:de|entre|para|en|sobre)\s+(?:esos|esas|estos|estas|ellos|ellas|los|las)\s+"
        r"(\d[\d.,]*\d|\d)(?![a-z0-9])"
    )
    _ANAPHORA_MAX_WORDS = 18
    _FOLLOWUP_FILLER = {
        "y", "cuantos", "cuantas", "cuanto", "cuanta", "cual", "cuales", "que", "hay",
        "hubo", "tiene", "tienen", "tuvo", "son", "fueron", "es", "corresponden",
        "corresponde", "pertenecen", "me", "lo", "la", "los", "las", "dime", "dame",
        "muestrame", "ahora", "favor", "por favor",
    }

    @staticmethod
    def _parse_number(text):
        """«33», «1.234», «1.234,5» -> float (formato español) o None."""
        text = str(text or "").strip().rstrip(".,")
        if not text:
            return None
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
            text = text.replace(".", "")
        try:
            return float(text)
        except ValueError:
            return None

    def _anaphora(self, message, original=None):
        """(frases, número citado o None) de las referencias a la respuesta
        anterior en el mensaje (o en su forma original, antes de reescribirlo)."""
        phrases = []
        for text in (original, message):
            norm = self._normalize_text(text)
            for match in self._ANAPHORA_RE.finditer(norm):
                if match.group(0) not in phrases:
                    phrases.append(match.group(0))
        number = None
        if phrases:
            # El número citado se lee del texto con su puntuación («3.906,4»).
            raw = "".join(
                char for char in unicodedata.normalize("NFD", str(original or message).lower())
                if unicodedata.category(char) != "Mn"
            )
            cited = self._CITED_NUMBER_RE.search(raw)
            if cited:
                number = self._parse_number(cited.group(1))
        return phrases, number

    def _same_number(self, cited, value):
        try:
            return cited is not None and value is not None and abs(float(value) - cited) < 0.5
        except (TypeError, ValueError):
            return False

    # Palabras de un seguimiento que aparecen en nombres de indicadores pero no
    # nombran uno: periodos («mes pasado», «año anterior», «actual»), la
    # respuesta anterior («ese indicador», «el total») o el propósito.
    _CONTEXT_WORDS = {
        "pasado", "pasada", "pasados", "pasadas", "anterior", "anteriores", "actual", "actuales",
        "presente", "corriente", "curso", "ultimo", "ultima", "ultimos", "ultimas", "proximo",
        "indicador", "indicadores", "dato", "datos", "cifra", "cifras", "valor", "valores",
        "tabla", "tablas", "resultado", "resultados", "consulta", "mismo", "misma", "total",
        "totales", "general", "mes", "meses", "ano", "anos", "dia", "dias", "semana", "semanas",
        "trimestre", "semestre", "periodo", "comite", "informe", "reporte", "solo", "solamente",
    }

    def _without_period_phrases(self, text):
        """Texto normalizado sin sus frases de periodo («en el mes pasado», «de
        septiembre de 2026», «por mes», «hasta hoy»): al decidir si un mensaje
        nombra un indicador, el periodo se reconoce primero («pasado» también
        aparece en nombres de indicadores)."""
        from src.semantic.period_parser import PeriodParser, neutral_phrases

        text = self._normalize_text(text)
        parser = PeriodParser()

        def drop(phrase, tokens=None):
            nonlocal text
            phrase = " ".join(str(phrase or "").split())
            if phrase and re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text):
                text = re.sub(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", " ", text)
                return True
            removed = False
            for token in tokens or []:
                if re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])", text):
                    text = re.sub(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])", " ", text)
                    removed = True
            return removed

        for _ in range(4):
            changed = False
            try:
                period = parser.parse(text)
                granularity = parser.granularity(text)
                neutral = neutral_phrases(text)
            except Exception:
                break
            if period and drop(period.get("phrase"), period.get("tokens")):
                changed = True
            if granularity and drop(granularity.get("phrase")):
                changed = True
            for phrase in neutral:
                changed = drop(phrase) or changed
            text = " ".join(text.split())
            if not changed:
                break
        return text

    def _named_metric_words(self, text, own_label=None):
        """Palabras del texto que nombran un indicador del catálogo, sin contar
        el periodo, las palabras de contexto ni (si se da) las del indicador
        anterior."""
        metric_words = getattr(self.query_plan_builder, "metric_words", None)
        if not callable(metric_words):
            return []
        try:
            words = metric_words(self._without_period_phrases(text)) or []
        except Exception:
            return []
        own = set(self._normalize_text(own_label).split()) if own_label else set()
        return [
            word for word in words
            if word not in self._CONTEXT_WORDS
            and not (own and (word in own or word.rstrip("s") in own or f"{word}s" in own))
        ]

    def _explained_by_plan(self, words, plan):
        """Palabras que el plan del seguimiento ya explica como valor de filtro
        o agrupación («hospitalización» -> SERVICIO = HOSPITALIZACION)."""
        texts = []
        for item in (plan or {}).get("filters") or []:
            values = item.get("values") if item.get("values") is not None else [item.get("value")]
            for value in values if isinstance(values, (list, tuple)) else [values]:
                texts.append(self._normalize_text(value))
            texts.append(self._normalize_text(item.get("label")))
        for item in (plan or {}).get("group_by") or []:
            texts.append(self._normalize_text(item.get("label") or item.get("column")))
        tokens = {token for text in texts for token in text.split()}
        explained = []
        for word in words:
            stem = word.rstrip("s")
            if any(token == word or token.rstrip("s") == stem or (len(stem) >= 5 and token.startswith(stem[:5]))
                   for token in tokens):
                explained.append(word)
        return explained

    _YEAR_IN_TEXT = re.compile(r"(?<![0-9])(?:19|20)\d{2}(?![0-9])")
    _RELATIVE_YEAR = re.compile(
        r"(?<![a-z0-9])(?:an(?:i)?o\s+(?:pasado|anterior|actual|antepasado|en\s+curso)|este\s+an(?:i)?o|"
        r"ultimo\s+an(?:i)?o|lo\s+que\s+va|lo\s+corrido|mes\s+(?:pasado|anterior|actual)|este\s+mes|"
        r"ultimos?\s+\d+|hoy|ayer|semana)(?![a-z0-9])"
    )

    def _previous_year(self, last):
        """Año del periodo de la consulta anterior (si es uno solo)."""
        for item in last.get("filters") or []:
            if not self._is_temporal_filter(item):
                continue
            if item.get("year"):
                return int(item["year"])
            start, end = str(item.get("start") or ""), str(item.get("end") or "")
            if start[:4].isdigit() and end[:4].isdigit():
                end_year = int(end[:4]) - (1 if end[4:] in ("-01-01",) else 0)
                if int(start[:4]) == end_year:
                    return int(start[:4])
            if item.get("column") and self._normalize_text(item.get("column")) in ("ano", "anio", "year"):
                try:
                    return int(item.get("value"))
                except (TypeError, ValueError):
                    pass
        return None

    def _with_previous_year(self, complement, last):
        """«de septiembre» tras una consulta de octubre de 2026 -> «de septiembre
        de 2026»: un mes sin año toma el año del periodo anterior."""
        from src.semantic.period_parser import MONTHS

        norm = self._normalize_text(complement)
        if not norm or self._YEAR_IN_TEXT.search(norm) or self._RELATIVE_YEAR.search(norm):
            return complement, None
        months = [word for word in norm.split() if word in MONTHS]
        if not months:
            return complement, None
        year = self._previous_year(last)
        if not year:
            return complement, None
        return f"{str(complement).rstrip(' ?¿!.')} de {year}", year

    def _followup_plan(self, message, original=None, complement=None, why=None, base=None, lenient=False):
        """Plan de seguimiento o None si el mensaje no es claramente un
        complemento de la última respuesta numérica.

        Condiciones: hay una consulta exitosa previa y ninguna contrapregunta
        pendiente, y además:
        - el mensaje empieza con «y», es corto, no nombra ningún indicador y
          aporta un período, un filtro o una agrupación («y en 2025?»); o
        - se refiere a la respuesta anterior («de esos 33», «de esta
          cantidad de pacientes», «desglósalo por...», «ahora por...») y no
          nombra OTRO indicador (puede repetir el nombre del mismo); o
        - la reescritura contextual ya decidió que depende de la consulta
          anterior y pasa su `complement` («eso mismo pero de septiembre» ->
          «de septiembre»), con `why` y, para volver a un tema anterior, `base`.
        Una pregunta nueva completa que nombra otro indicador nunca es seguimiento.
        Las frases de periodo («el mes pasado») se reconocen ANTES de buscar
        nombres de indicador.
        Con `lenient` (referencia explícita a la respuesta anterior, «los de
        urgencias», cuando ni las reglas estrictas ni el LLM bastaron) se
        responde la consulta anterior declarando lo que no se pudo aplicar.
        """
        last = base or self._last_success
        builder = self.query_plan_builder
        if last is None or builder is None or self.query_plan_dax_generator is None:
            return None
        if self._has_pending_clarification():
            return None
        phrases, cited = [], None
        pending_named = []
        from_context = complement is not None
        if complement is not None:
            # La reescritura contextual ya decidió que el mensaje depende del
            # contexto: solo se descarta si nombra OTRO indicador que el plan
            # no explique como filtro.
            pending_named = self._named_metric_words(complement, own_label=last.get("metric_label"))
            own = set(self._normalize_text(last.get("metric_label")).split())
            complement_text = self._normalize_text(complement)
            for word in sorted(own, key=len, reverse=True):
                if len(word) >= 4:
                    complement_text = re.sub(
                        r"(?<![a-z0-9])" + re.escape(word) + r"s?(?![a-z0-9])", " ", complement_text,
                    )
            complement = re.sub(r"\s+", " ", complement_text).strip()
            if not complement:
                return None
            why = why or "el mensaje depende de la consulta anterior"
        else:
            words = self._normalize_text(message).split()
            phrases, cited = self._anaphora(message, original)
            # «de los 33» sin demostrativo solo es referencia si 33 es el valor anterior.
            plain_number = [p for p in phrases if re.fullmatch(r"(?:de|entre) (?:los|las) [\d ]+", p)]
            if plain_number and len(plain_number) == len(phrases) and not self._same_number(cited, last.get("value")):
                phrases = []
            if phrases and len(words) <= self._ANAPHORA_MAX_WORDS:
                complement_text = self._normalize_text(message)
                for phrase in sorted(phrases, key=len, reverse=True):
                    complement_text = re.sub(
                        r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", " ", complement_text,
                    )
                # Las palabras del propio indicador («de esta cantidad de
                # pacientes») no son un indicador nuevo.
                own = set(self._normalize_text(last.get("metric_label")).split())
                named = self._named_metric_words(complement_text, own_label=last.get("metric_label"))
                if named:
                    self._think(
                        "¿Es un seguimiento de la consulta anterior?",
                        f"no: aunque se refiere a la respuesta anterior ({', '.join(phrases)}), nombra "
                        f"otro indicador ({', '.join(named)}); se trata como pregunta nueva",
                    )
                    return None
                kept = [
                    word for word in complement_text.split()
                    if word not in self._FOLLOWUP_FILLER and word not in own
                    and word.rstrip("s") not in own and word not in ("de", "del", "el")
                ]
                if not kept:
                    return None
                complement = complement_text
                for word in sorted(own, key=len, reverse=True):
                    if len(word) >= 4:
                        complement = re.sub(r"(?<![a-z0-9])" + re.escape(word) + r"s?(?![a-z0-9])", " ", complement)
                complement = re.sub(r"\s+", " ", complement).strip()
                reference = ", ".join(f"«{phrase}»" for phrase in phrases)
                if cited is not None and last.get("value") is not None and not self._same_number(cited, last["value"]):
                    reference += (
                        f" (el número citado, {format_value_es(cited) or cited}, no coincide con el valor "
                        f"anterior {format_value_es(last['value']) or last['value']}; se usa la consulta anterior)"
                    )
                why = f"se refiere a la respuesta anterior: {reference}"
            else:
                phrases = []
                if len(words) < 2 or words[0] != "y" or len(words) > self._FOLLOWUP_MAX_WORDS:
                    return None
                complement = " ".join(words[1:])
                named = self._named_metric_words(complement)
                own = set(self._normalize_text(last.get("metric_label")).split())
                if any(word in own or word.rstrip("s") in own or f"{word}s" in own for word in named):
                    # Repite el nombre del indicador: es una pregunta completa.
                    self._think(
                        "¿Es un seguimiento de la consulta anterior?",
                        f"no: nombra un indicador ({', '.join(named)}); se trata como pregunta nueva",
                    )
                    return None
                if named:
                    # Un complemento corto («y de hospitalización») puede ser un
                    # valor de filtro con el mismo nombre que un indicador: se
                    # decide con el plan (si no lo explica, es pregunta nueva).
                    content = [w for w in self._without_period_phrases(complement).split()
                               if w not in self._FOLLOWUP_FILLER and w not in ("de", "del", "en", "el", "la")]
                    if len(content) > 3:
                        self._think(
                            "¿Es un seguimiento de la consulta anterior?",
                            f"no: nombra un indicador ({', '.join(named)}); se trata como pregunta nueva",
                        )
                        return None
                    pending_named = named
                why = "empieza con «y» y solo agrega un complemento"

        complement, inherited_year = self._with_previous_year(complement, last)
        plan = builder.build(complement, selected_metric_id=last["metric_id"])
        if pending_named:
            unexplained = [w for w in pending_named if w not in self._explained_by_plan(pending_named, plan)]
            if unexplained and lenient:
                # Se declara lo que no se pudo aplicar («No pude aplicar: urgencias»).
                known = {self._normalize_text(term) for term in plan.get("unapplied_terms") or []}
                plan = {**plan, "unapplied_terms": [
                    *(plan.get("unapplied_terms") or []),
                    *[word for word in unexplained if word not in known],
                ]}
            if unexplained and not lenient:
                self._think(
                    "¿Es un seguimiento de la consulta anterior?",
                    f"no: nombra un indicador ({', '.join(unexplained)}) que no es un filtro de "
                    f"{last['metric_label']}; se trata como pregunta nueva",
                )
                return None
        status = plan.get("status")
        if from_context and status == "ready" and not lenient:
            # Sin «y» ni anáfora, todo el complemento debe entenderse como
            # periodo, filtro o agrupación del indicador anterior; si sobra
            # algo («total atenciones por servicio»: «atenciones») es otra pregunta.
            unapplied = [
                term for term in plan.get("unapplied_terms") or []
                if self._normalize_text(term) not in ("cuantos", "cuantas", "cuanto", "cuanta")
            ]
            if unapplied:
                self._think(
                    "¿Es un seguimiento de la consulta anterior?",
                    f"no: «{', '.join(unapplied)}» no es un periodo, filtro ni agrupación de "
                    f"{last['metric_label']}",
                )
                return None
        if status == "ready":
            new_filters = plan.get("filters") or []
            if not new_filters and not plan.get("group_by") and not (lenient and plan.get("unapplied_terms")):
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
                "question": f"{last['question']} ({(original or message).strip()})",
                "followup_base_question": last["question"],
                "followup_of": {
                    "question": last["question"], "metric": last["metric_label"],
                    "value": last.get("value"), "metric_format": last.get("metric_format"),
                    "anaphora": bool(phrases),
                },
                "unapplied_terms": [
                    term for term in plan.get("unapplied_terms") or []
                    if self._normalize_text(term) not in ("cuantos", "cuantas", "cuanto", "cuanta")
                ],
            }
            self._think(
                "Seguimiento de la consulta anterior",
                f"se interpretó «{(original or message).strip()}» como seguimiento de «{last['question']}» "
                f"(indicador {last['metric_label']}): {why}",
                "se hereda el indicador y sus filtros; solo cambia lo que agrega el mensaje",
                f"el mes sin año toma el año de la consulta anterior ({inherited_year})" if inherited_year else None,
                *[f"se conserva: {self._filter_line(item)}" for item in inherited],
                *[f"se reemplaza: {self._filter_line(item)}" for item in replaced],
                *[f"nuevo: {self._filter_line(item)}" for item in new_filters],
                *[f"agrupar por: {item.get('table')}[{item.get('column')}]" for item in group_by],
            )
            return plan
        if status == "unsupported_filter":
            self._think(
                "Seguimiento de la consulta anterior",
                f"se interpretó «{(original or message).strip()}» como seguimiento de «{last['question']}» "
                f"(indicador {last['metric_label']}), pero el complemento no se pudo aplicar",
            )
            return {**plan, "followup_of": {"question": last["question"], "metric": last["metric_label"]}}
        return None

    _NON_ADDITIVE_RE = re.compile(r"promedio|porcentaje|%|tasa|indice|razon|proporcion|media|giro|estancia")

    def _note_breakdown_of_previous(self, plan, result):
        """«¿Cuántos de esos 33 tiene cada especialidad?»: la tabla desglosa el
        valor anterior; se dice cuánto suman sus filas frente a ese total."""
        followup = plan.get("followup_of") or {}
        previous = followup.get("value")
        if (
            not isinstance(result, dict) or result.get("status") != "success"
            or result.get("result_type") != "table" or previous is None
        ):
            return
        label = str(followup.get("metric") or "")
        if self._NON_ADDITIVE_RE.search(self._normalize_text(label)) or "%" in str(followup.get("metric_format") or ""):
            return
        total = 0.0
        for row in result.get("rows") or []:
            try:
                total += float(self._row_value(row))
            except (TypeError, ValueError):
                return
        try:
            previous = float(previous)
        except (TypeError, ValueError):
            return
        groups = ", ".join(
            str(item.get("label") or item.get("column")) for item in plan.get("group_by") or []
        )
        previous_text = format_value_es(previous) or previous
        total_text = format_value_es(total) or total
        if abs(total - previous) < 0.5:
            note = f"Desglose por {groups} de los {previous_text} de la consulta anterior (las filas suman {total_text})."
        else:
            note = (
                f"Desglose por {groups} de la consulta anterior ({previous_text}): las filas suman "
                f"{total_text}; puede diferir si un mismo registro aparece en más de un grupo o sin {groups}."
            )
        query_plan = result.get("query_plan")
        if isinstance(query_plan, dict):
            query_plan["notes"] = [*(query_plan.get("notes") or []), note]
        self._think("Desglose del valor anterior", note)

    def _rewrite_request(self, message):
        """Quita el relleno de petición («se me ha solicitado saber») y convierte
        «cada una de las especialidades», «desglose por sede»... en «por
        <dimensión>». Una respuesta corta a una contrapregunta no se toca."""
        if self._pending_query_plan is not None and not self._is_new_full_question(message):
            return message
        recognizer = getattr(self.query_plan_builder, "grouping_dimension_name", None)
        try:
            rewritten, notes = rewrite_request(
                message, dimension=recognizer if callable(recognizer) else None,
            )
        except Exception as error:
            self._think("No se pudo reinterpretar la forma de la pregunta", f"{type(error).__name__}: {error}")
            return message
        if notes and rewritten.strip():
            self._think(
                "Frases de la pedida reinterpretadas",
                *notes,
                f"pregunta que se resuelve: «{rewritten}»",
            )
            return rewritten
        return message

    # ========================================================
    # CONVERSACIÓN: mensajes que dependen del contexto
    # ========================================================
    #
    # «Y en el mes pasado?», «necesito eso mismo pero de septiembre», «para el
    # comité, los de urgencias», «¿cómo se calcula ese indicador?», «compáralo
    # con el año pasado», «no, me refería a hospitalización»... se entienden con
    # la memoria de la conversación. Primero reglas deterministas sobre la
    # consulta anterior (indicador, filtros, periodo, agrupación, tablero) y, si
    # no bastan, MedGemma reescribe el mensaje (validado). Una pregunta nueva
    # completa (nombra su propio indicador) no se reescribe.

    # Mensajes sin señal explícita que se prueban como complemento de la
    # consulta anterior («en septiembre», «por servicio»): hasta estas palabras.
    _CONTEXT_SHORT_WORDS = 6
    # Señales fuertes: se refieren a la respuesta anterior aunque el mensaje
    # nombre una palabra que también está en nombres de indicadores.
    _STRONG_CUES = {"lo mismo", "referencia", "elipsis", "corrección", "volver a un tema"}

    _DESCRIPTIVE_HEADS = {
        "como se calcula": "¿Cómo se calcula", "como se calculan": "¿Cómo se calcula",
        "que significa": "¿Qué significa", "que significan": "¿Qué significa",
        "que quiere decir": "¿Qué quiere decir", "que es": "¿Qué es", "que mide": "¿Qué mide",
        "como se mide": "¿Cómo se mide", "como se interpreta": "¿Cómo se interpreta",
        "como se define": "¿Cómo se define", "para que sirve": "¿Para qué sirve",
        "que muestra": "¿Qué muestra", "que filtros": "¿Qué filtros tiene", "que filtro": "¿Qué filtros tiene",
        "de donde sale": "¿De dónde sale", "como funciona": "¿Cómo funciona",
        "que contiene": "¿Qué contiene", "explica": "Explica",
    }
    _NUMERIC_CUE_RE = re.compile(
        r"(?<![a-z0-9])(?:cuant[oa]s?|total|cantidad|numero|valor|cifra|que\s+tanto|cual\s+(?:fue|es)|"
        r"cuales\s+(?:fueron|son)|por\s+[a-z]{3,})(?![a-z0-9])"
    )
    _SAME_PERIOD_LAST_YEAR = re.compile(
        r"(?<![a-z0-9])(?:(?:el|al|del)\s+)?(?:mismo\s+(?:periodo|mes|trimestre)\s+del?\s+)?"
        r"an(?:i)?o\s+(?:pasado|anterior)(?![a-z0-9])"
    )

    def _context_llm_provider(self):
        llm = getattr(self, "context_llm", None)
        if llm is not None:
            return llm
        return getattr(getattr(self, "option_describer", None), "llm_provider", None)

    def _note_interpretation(self, text, why, source="reglas"):
        self._turn_interpretation = text
        self._think(
            "Interpretación con el contexto de la conversación",
            f"Interpreté tu mensaje como: «{text}»",
            f"por qué: {why}",
            "cómo: reglas sobre la consulta anterior (indicador, filtros, periodo, agrupación o tablero)"
            if source == "reglas" else
            "cómo: MedGemma reescribió el mensaje con los últimos turnos; se validó que no "
            "agregue indicadores, cifras ni datos que no estaban en la conversación",
        )

    def _plan_interpretation(self, plan):
        """«CANTIDAD DE PACIENTES por ESPECIALIDAD (SERVICIO = URGENCIAS · septiembre 2026)»."""
        text = str((plan.get("metric") or {}).get("label") or "el indicador anterior")
        groups = ", ".join(str(group_header(g)) for g in plan.get("group_by") or [])
        if groups:
            text += f" por {groups}"
        filters = self._own_filters_text(plan.get("filters"))
        if filters:
            text += f", {filters}"
        return text

    def _context_analysis(self, message):
        """Señales de contexto del mensaje, o None si no hay conversación previa
        o hay una contrapregunta pendiente (la contrapregunta manda)."""
        memory = getattr(self, "conversation_memory", None)
        if memory is None or not len(memory) or self._has_pending_clarification():
            return None
        try:
            analysis = contextual_rewriter.analyze(message)
        except Exception as error:
            self._think("No se pudo analizar el contexto del mensaje", f"{type(error).__name__}: {error}")
            return None
        if analysis.get("courtesy"):
            return None
        return analysis

    def _previous_turn(self):
        memory = getattr(self, "conversation_memory", None)
        return memory.last() if memory is not None else None

    def _run_followup(self, followup, message, why=None):
        """Ejecuta un plan de seguimiento (o su falla) y conserva el tema."""
        self._trace_plan(followup, "Query Plan del seguimiento")
        if followup.get("status") == "ready":
            self._note_interpretation(
                self._plan_interpretation(followup),
                why or "el mensaje completa la consulta anterior (mismo indicador; cambia lo que agrega)",
            )
            result = self._execute_query_plan(followup)
            self._note_breakdown_of_previous(followup, result)
        else:
            result = self._query_plan_failure(followup)
        result["followup_of"] = followup.get("followup_of")
        self._remember_success(result, followup=True)
        return result

    # ---------------- temas de la conversación ----------------

    def _topic_subject(self, topic):
        """«el indicador cantidad de pacientes del tablero briefing hospitalario».

        En minúsculas: la pregunta reescrita va a la búsqueda documental y los
        nombres en mayúsculas («PESO», «TABLERO LAVANDERIA») recuperan peor
        (con MedGemma real, «¿cómo se calcula ese indicador?» tras el peso de
        lavandería respondía con la medida TURNO_OK)."""
        text = f"el indicador {str(topic.get('metric_label') or '').lower()}"
        report = topic.get("report")
        if report:
            text += " " + self._board_phrase(str(report).lower(), "del")
        return text

    _LEAD_QUESTION_RE = re.compile(
        r"^\s*(?:cuant[oa]s?|cual(?:es)?|que\s+tanto|que)(?:\s+(?:fue|fueron|es|son|hubo|hay|habia|tuvo|"
        r"tiene|tienen|registro|registraron|se\s+registraron?|da|dio))?(?![a-z0-9])"
    )

    def _insert_subject(self, complement, subject):
        """«cuál fue en septiembre» + «nedocs» -> «cuál fue nedocs en septiembre»."""
        complement = str(complement or "").strip()
        match = self._LEAD_QUESTION_RE.match(contextual_rewriter.fold(complement))
        if not match:
            return f"{subject} {complement}".strip()
        lead, rest = complement[: match.end()].strip(), complement[match.end():].strip()
        return " ".join(part for part in (lead, subject, rest) if part)

    def _documentation_subject(self, turn):
        """De qué trató una respuesta documental: el indicador o tema de la
        pregunta (sin «cómo se calcula», interrogativos...) y su tablero."""
        question = (turn or {}).get("interpreted") or (turn or {}).get("user") or ""
        norm = self._normalize_text(question)
        reason = self._descriptive_reason(question)
        if reason:
            norm = norm.replace(self._normalize_text(reason), " ")
        norm = re.sub(
            r"(?<![a-z0-9])(?:y|que|cual|cuales|como|cuanto|cuantos|cuantas|me|puedes|podrias|decir|dime|"
            r"explica|explicame|sabes|tiene|tienen|muestra|muestran|hay|es|son|se|el|la|los|las|un|una)(?![a-z0-9])",
            " ", norm,
        )
        subject = " ".join(norm.split())
        board = ((turn or {}).get("meta") or {}).get("dashboard")
        return subject, board

    _BOARD_STOPWORDS = {"tablero", "de", "del", "la", "el", "los", "las", "y"}

    def _board_tokens(self, text):
        return set(self._normalize_text(text).split()) - self._BOARD_STOPWORDS

    @staticmethod
    def _same_tokens(left, right):
        """Conjuntos de palabras equivalentes (uno contiene al otro), tolerando
        erratas de la documentación («LAVADERIA» / «LAVANDERIA»)."""
        from difflib import SequenceMatcher

        if not left or not right:
            return False
        small, big = (left, right) if len(left) <= len(right) else (right, left)
        return all(
            any(word == other or SequenceMatcher(None, word, other).ratio() >= 0.85 for other in big)
            for word in small
        )

    def _board_main_metric(self, board):
        """Indicador principal de un tablero (por informe o página): el que más
        aparece en sus visuales (las tarjetas cuentan doble). None si no hay
        uno claro."""
        builder = self.query_plan_builder
        target = self._board_tokens(board)
        if not target or builder is None:
            return None
        scores = {}
        for metric in getattr(builder, "metrics", None) or []:
            if metric.get("validation_status") not in (None, "approved") or not metric.get("metric_id"):
                continue
            score = 0
            for appearance in metric.get("appearances") or []:
                names = (appearance.get("report"), appearance.get("page_display_name"))
                if any(self._same_tokens(target, self._board_tokens(name)) for name in names):
                    score += 2 if "card" in str(appearance.get("visual_type") or "").lower() else 1
            if score:
                key = (self._normalize_text(metric.get("label")), self._normalize_text(metric.get("semantic_model")))
                if key not in scores or scores[key][0] < score:
                    scores[key] = (score, metric)
        if not scores:
            return None
        ranked = sorted(scores.values(), key=lambda item: -item[0])
        if len(ranked) > 1 and ranked[1][0] == ranked[0][0]:
            return None
        return ranked[0][1]

    def _topic_plan(self, topic, complement="", drop_groups=False, why=None, message=None):
        """Plan de la consulta del tema (indicador, filtros y agrupación del
        turno guardado), con el complemento del mensaje si aporta algo."""
        plan = None
        content = [
            word for word in self._normalize_text(complement).split()
            if len(word) >= 3 and word not in self._FOLLOWUP_FILLER
            and word not in ("del", "las", "los", "por", "para", "con", "que", "una", "uno")
        ]
        if content:
            plan = self._followup_plan(
                message or complement, original=message, complement=complement, why=why, base=topic,
            )
            if plan is None or plan.get("status") != "ready":
                return plan
        if plan is None:
            try:
                built = self.query_plan_builder.build("total", selected_metric_id=topic["metric_id"])
            except Exception as error:
                self._think("No se pudo rearmar la consulta anterior", f"{type(error).__name__}: {error}")
                return None
            if built.get("status") != "ready":
                return None
            plan = {
                **built,
                "filters": [dict(item) for item in topic.get("filters") or []],
                "group_by": [dict(item) for item in topic.get("group_by") or []],
                "ranking": dict(topic["ranking"]) if topic.get("ranking") else None,
                "question": f"{topic['question']} ({(message or '').strip()})" if message else topic["question"],
                "followup_base_question": topic["question"],
                "followup_of": {
                    "question": topic["question"], "metric": topic.get("metric_label"),
                    "value": topic.get("value"), "metric_format": topic.get("metric_format"),
                    "anaphora": False,
                },
                "unapplied_terms": [],
            }
        if drop_groups:
            plan = {**plan, "group_by": [], "ranking": None}
        plan["mode"] = "grouped" if plan.get("group_by") else "scalar"
        return plan

    # ---------------- reglas que van antes del seguimiento clásico ----------------

    def _contextual_special(self, message, rewritten, analysis):
        last = self._last_success
        previous = self._previous_turn() or {}
        previous_route = (previous.get("meta") or {}).get("route")
        complement = analysis.get("complement") or ""
        own_label = last.get("metric_label") if last else None
        named = self._named_metric_words(complement, own_label=own_label)
        cues = analysis.get("cues") or []

        # 0. Dónde se ve: «¿y eso en qué tablero lo veo?», «¿dónde está?».
        if last is not None and not named and self._WHERE_RE.search(self._normalize_text(message)) and (
            cues or len(self._normalize_text(message).split()) <= self._CONTEXT_SHORT_WORDS
        ) and not self._mentions_board(complement):
            return self._where_is_topic(message, last)

        # 1. Documentación del tema anterior: «¿cómo se calcula ese indicador?»,
        #    «¿y eso qué significa?», «¿por qué tan alto?», «¿y qué filtros tiene?».
        descriptive = self._descriptive_reason(message)
        if (
            (descriptive or analysis.get("why")) and not named
            and not self._has_own_subject(analysis, descriptive) and not self._mentions_board(complement)
        ):
            response = self._documentation_about_topic(message, analysis, descriptive, last, previous)
            if response is not None:
                return response

        # 2. Comparación con otro periodo: «compáralo con el año pasado».
        if analysis.get("compare") and last is not None and not named:
            response = self._comparison_turn(message, analysis, last)
            if response is not None:
                return response

        # 3. Total sin desglose: «ok, y el total?».
        if analysis.get("total") and last is not None and last.get("group_by") and not named:
            plan = self._topic_plan(
                last, complement, drop_groups=True, message=message,
                why="pide el total de la consulta anterior (sin el desglose)",
            )
            if plan is not None and plan.get("status") == "ready":
                self._think(
                    "Total de la consulta anterior",
                    f"«{message.strip()}» pide el total de {last['metric_label']}: se quita la agrupación "
                    "y se conservan los filtros",
                )
                return self._run_followup(plan, message, "pide el total de la consulta anterior (sin el desglose)")

        # 4. Corrección: «no, me refería a hospitalización» (otro valor del
        #    filtro: se reemplaza) o «no, me refería a las cirugías realizadas»
        #    (otro indicador: misma consulta con ese indicador).
        correction = analysis.get("correction")
        if correction and last is not None and previous_route == "powerbi":
            why = "corrige la consulta anterior: se reemplaza lo que nombra y se conserva el resto"
            plan = self._followup_plan(message, original=message, complement=correction, why=why)
            if plan is not None:
                return self._run_followup(plan, message, why)
        metric_text = (
            self._corrected_metric_text(correction, last)
            if correction and last is not None and previous_route == "powerbi" else None
        )
        if metric_text:
            question = f"{metric_text} {self._topic_scope_text(last)}".strip()
            self._note_interpretation(
                question,
                f"corrige el indicador de la consulta anterior ({last['metric_label']}): se repite "
                "la consulta con el indicador que nombra, el mismo periodo, filtros y agrupación",
            )
            result = self._process(question)
            self._remember_success(result)
            return result

        # 5. Volver a un tema anterior: «volviendo a las cirugías programadas, ¿y en 2025?».
        if analysis.get("regreso") and named:
            response = self._return_to_topic(message, analysis, named)
            if response is not None:
                return response

        # 6. Dato numérico después de una respuesta documental: «¿y cuántos
        #    hubo en 2025?» tras «¿qué muestra el tablero de cancelaciones?».
        if previous_route == "rag" and last is None and not named and not self._resolves_to_metric(complement) and (
            "conector" in cues or "referencia" in cues or "lo mismo" in cues
            or len(self._normalize_text(message).split()) <= self._CONTEXT_SHORT_WORDS
        ):
            response = self._numeric_after_documentation(message, analysis, previous)
            if response is not None:
                return response
        return None

    # Palabras que no son un sujeto propio en «¿por qué tan alto?», «¿y qué
    # filtros tiene?», «¿cómo se calcula?»: la pregunta es sobre el tema anterior.
    _SUBJECTLESS_WORDS = {
        "tan", "alto", "alta", "altos", "altas", "bajo", "baja", "bajos", "bajas", "poco", "pocos",
        "poca", "pocas", "mucho", "muchos", "mucha", "muchas", "tanto", "tantos", "tanta", "tantas",
        "elevado", "elevada", "subio", "bajo", "aumento", "disminuyo", "cambio", "diferente",
        "significa", "significan", "calcula", "calculan", "tiene", "tienen", "muestra", "muestran",
        "sale", "salen", "mide", "miden", "define", "funciona", "contiene", "quiere", "decir",
        "sirve", "indicador", "dato", "cifra", "valor", "numero", "resultado", "tabla", "esta",
        "este", "estos", "estas", "ahora", "entonces", "bueno", "pero", "porque", "explica",
        "explicame", "interpreta", "obtiene", "calculo", "formula", "bien", "normal", "raro",
    }

    def _has_own_subject(self, analysis, descriptive):
        """¿La pregunta descriptiva nombra su propio tema («¿qué es el NEDOCS?»)?"""
        norm = self._normalize_text(analysis.get("complement"))
        if descriptive:
            norm = re.sub(
                r"(?<![a-z0-9])" + re.escape(self._normalize_text(descriptive)) + r"(?![a-z0-9])", " ", norm,
            )
        norm = re.sub(r"(?<![a-z0-9])por que(?![a-z0-9])", " ", norm)
        return any(
            len(word) >= 4 and word not in self._SUBJECTLESS_WORDS and word not in self._FOLLOWUP_FILLER
            for word in norm.split()
        )

    def _metric_ids(self, text):
        """Indicadores (ids) a los que resuelve el texto solo, o None si no
        resuelve a ninguno."""
        builder = self.query_plan_builder
        try:
            result = builder._resolve_metric_flexible(text, builder._source_context(text))
        except Exception:
            return None
        if result.get("status") == "resolved":
            metric = result.get("metric") or {}
            return {metric.get("metric_id")} if metric.get("metric_id") else None
        if result.get("status") == "ambiguous":
            ids = set()
            for item in result.get("candidates") or []:
                metric = item.get("metric") if isinstance(item, dict) and "metric" in item else item
                if isinstance(metric, dict) and metric.get("metric_id"):
                    ids.add(metric["metric_id"])
            return ids or None
        return None

    def _corrected_metric_text(self, correction, last):
        """«no, me refería a las realizadas» tras CIRUGÍAS PROGRAMADAS: si lo
        corregido (solo o junto al nombre del indicador anterior, «cirugías
        realizadas») es OTRO indicador, devuelve ese texto; si es el mismo
        indicador o ninguno, None (la corrección es de filtro)."""
        said = self._normalize_text(correction).split()
        own = [w for w in self._normalize_text(last.get("metric_label")).split() if len(w) >= 4 and w not in said]
        # Lo corregido solo y con cada palabra del indicador anterior
        # («realizadas» -> «cirugias realizadas»).
        texts = [correction, *[f"{word} {correction}" for word in own]]
        same = False
        for text in texts:
            ids = self._metric_ids(text)
            if ids and last.get("metric_id") not in ids:
                return text
            same = same or bool(ids)
        return None

    def _resolves_to_metric(self, text):
        """¿El texto, solo, nombra un indicador del catálogo? (metric_words no
        basta: «cirugías» también es alias de una dimensión)."""
        builder = self.query_plan_builder
        if self._named_metric_words(text):
            return True
        text = self._without_period_phrases(text)
        if not text:
            return False
        try:
            context = builder._source_context(text)
            result = builder._resolve_metric_flexible(text, context)
        except Exception:
            return False
        return result.get("status") in ("resolved", "ambiguous")

    def _mentions_board(self, text):
        detect = getattr(getattr(self.conversation_manager, "intent_parser", None), "detect_dashboard", None)
        if not callable(detect) or not self._normalize_text(text):
            return False
        try:
            return bool(detect(text))
        except Exception:
            return False

    def _topic_scope_text(self, topic):
        """Periodo, valores de filtro y agrupación de una consulta, en texto
        («urgencias octubre 2026 por especialidad»)."""
        parts = []
        for item in topic.get("filters") or []:
            if self._is_temporal_filter(item):
                label = re.sub(r"\s*\([^)]*\)", "", str(item.get("label") or ""))
                if label:
                    parts.append(label)
            elif item.get("value") not in (None, ""):
                parts.append(f"de {item.get('value')}")
            elif item.get("values"):
                parts.append("de " + " y ".join(str(v) for v in item["values"]))
        for item in topic.get("group_by") or []:
            parts.append(f"por {str(item.get('label') or item.get('column')).lower()}")
        return " ".join(parts)

    _WHERE_RE = re.compile(
        r"(?<![a-z0-9])(?:en\s+(?:que|cual|cuales)\s+(?:tableros?|informes?|reportes?|paginas?|hojas?)"
        r"|donde\s+(?:(?:lo|la|los|las|se|puedo|podria|lo\s+puedo)\s+)*(?:veo|ver|ve|encuentro|encontrar|"
        r"encuentra|consulto|consultar|esta|estan|aparece|aparecen|miro|mirar|busco|buscar|sale|salen|"
        r"reviso|revisar))(?![a-z0-9])"
    )

    def _where_is_topic(self, message, last):
        """Respuesta directa con el informe y las páginas del indicador anterior
        (se conocen del catálogo: no hace falta buscar en la documentación)."""
        label = last.get("metric_label") or "el indicador"
        report = last.get("report")
        pages = last.get("pages") or []
        if not report and not pages:
            return None
        text = f"**{label}** (la consulta anterior) está en " + (
            self._board_phrase(report) if report else "el informe de Power BI"
        )
        if pages:
            text += (", página " if len(pages) == 1 else ", páginas ") + ", ".join(f"«{p}»" for p in pages)
        text += "."
        if last.get("semantic_model") and last.get("semantic_model") != report:
            text += f" Modelo semántico: {last['semantic_model']}."
        self._note_interpretation(
            f"¿En qué tablero está {self._topic_subject(last)}?",
            f"pregunta dónde se ve el indicador de la respuesta anterior ({label})",
        )
        self._think(
            "Ubicación del indicador",
            "se responde con el informe y las páginas del catálogo de Power BI",
        )
        result = {
            "status": "success", "route": "rag", "question": message, "answer": text,
            "sources": [], "synthesis_mode": "catalogo",
        }
        # El tema sigue siendo el mismo indicador.
        self._remember_success(result, followup=True)
        return result

    def _documentation_about_topic(self, message, analysis, descriptive, last, previous):
        """Pregunta documental sin sujeto propio: se completa con el tema
        anterior (el indicador de la última respuesta numérica o el tablero /
        tema de la última respuesta documental)."""
        previous_route = (previous.get("meta") or {}).get("route")
        if last is not None and previous_route in ("powerbi", "rag"):
            subject = self._topic_subject(last)
            why = f"pregunta por el indicador de la respuesta anterior ({last['metric_label']})"
        elif previous_route == "rag":
            phrase, board = self._documentation_subject(previous)
            if phrase and len(phrase.split()) <= 8:
                subject = phrase
            elif board:
                subject = self._board_phrase(board)
            else:
                return None
            why = "pregunta por el tema de la respuesta documental anterior"
        else:
            return None
        if analysis.get("why"):
            question = f"¿Qué mide y cómo se calcula {subject}?"
            why += "; «¿por qué?» se responde con lo que mide y cómo se calcula (la documentación no trae causas)"
        else:
            head = self._DESCRIPTIVE_HEADS.get(self._normalize_text(descriptive))
            if head:
                question = f"{head} {subject}?"
            else:
                question = self._replace_reference(message, analysis, subject)
        self._note_interpretation(question, why)
        result = self._process(question)
        # El tema sigue siendo el mismo indicador: «¿y en 2025?» después
        # vuelve a la consulta numérica.
        self._remember_success(result, followup=True)
        return result

    def _replace_reference(self, message, analysis, subject):
        """Cambia el demostrativo («ese indicador», «eso») por el tema; si no
        hay, agrega el tema al final."""
        text = str(message or "").strip()
        folded = contextual_rewriter.fold(text)
        for reference in analysis.get("references") or []:
            match = re.search(
                r"(?<![a-z0-9])" + r"\s+".join(map(re.escape, reference.split())) + r"(?![a-z0-9])", folded,
            )
            if match:
                return text[: match.start()] + subject + text[match.end():]
        body = re.sub(r"[\s?¿.!]+$", "", text)
        body = re.sub(r"^[¿\s]*(?:y|e)\s+", "", body, flags=re.IGNORECASE)
        return f"¿{body.lstrip('¿')} {subject}?"

    def _comparison_turn(self, message, analysis, last):
        """«compáralo con el año pasado»: la consulta anterior y la misma con el
        otro periodo, lado a lado (un valor por periodo o una columna por periodo)."""
        target = analysis.get("compare") or ""
        base_plan = self._topic_plan(last, "", message=message)
        if base_plan is None or base_plan.get("status") != "ready":
            return None
        target_norm = self._normalize_text(target)
        has_period = any(self._is_temporal_filter(item) for item in last.get("filters") or [])
        other = None
        if has_period and self._SAME_PERIOD_LAST_YEAR.search(target_norm):
            shifted = self._shift_filters_one_year(base_plan.get("filters"))
            if shifted is not None:
                other = {**base_plan, "filters": shifted}
                how = "el mismo periodo un año antes"
        if other is None:
            other = self._followup_plan(
                message, original=message, complement=target, base=last,
                why=f"compara la consulta anterior con «{target}»",
            )
            how = f"el periodo «{target}»"
            if other is None or other.get("status") != "ready":
                return None
        label = str((base_plan.get("metric") or {}).get("label") or last.get("metric_label"))
        composite = {
            "status": "composite",
            "question": f"{last['question']} ({message.strip()})",
            "items": [
                {"kind": "metric", "label": label, "plan": base_plan},
                {"kind": "metric", "label": label, "plan": other},
            ],
            "grouped": bool(base_plan.get("group_by")),
            "notes": [],
        }
        self._think(
            "Comparación con otro periodo",
            f"«{message.strip()}» compara la consulta anterior ({last['metric_label']}) con {how}",
            *[f"periodo comparado: {self._filter_line(item)}" for item in other.get("filters") or []
              if self._is_temporal_filter(item)],
        )
        self._note_interpretation(
            f"{self._plan_interpretation(base_plan)}, frente a "
            f"{self._own_filters_text([i for i in other.get('filters') or [] if self._is_temporal_filter(i)]) or target}",
            f"compara la consulta anterior con {how}",
        )
        result = self._execute_composite(composite)
        if isinstance(result, dict):
            result["followup_of"] = base_plan.get("followup_of")
            if result.get("status") == "success" and not composite["grouped"]:
                self._note_variation(result)
            # Los periodos van en cada medida; la línea «Filtros:» solo lleva
            # los filtros comunes (sin el periodo de la primera consulta).
            if isinstance(result.get("query_plan"), dict):
                result["query_plan"] = {**result["query_plan"], "filters": list(result.get("filters") or [])}
        self._remember_success(result, followup=True)
        return result

    def _note_variation(self, result):
        """Nota con la diferencia entre los dos periodos de una comparación."""
        measures = [m for m in result.get("measures") or [] if isinstance(m, dict)]
        if len(measures) != 2:
            return
        try:
            current, other = float(measures[0]["value"]), float(measures[1]["value"])
        except (TypeError, ValueError, KeyError):
            return
        percent = "%" in str(measures[0].get("format") or "")
        diff = current - other
        sign = "+" if diff > 0 else ("−" if diff < 0 else "")
        if percent:
            note = f"Diferencia: {sign}{self._fmt_es(abs(diff) * 100, 2)} puntos porcentuales."
        else:
            note = f"Diferencia: {sign}{self._fmt_es(abs(diff))}"
            if other:
                note += f" ({sign}{self._fmt_es(abs(diff) / abs(other) * 100, 1)} %)"
            note += "."
        plan = result.get("query_plan")
        if isinstance(plan, dict):
            plan["notes"] = [*(plan.get("notes") or []), note]
        self._think("Diferencia entre los periodos", note)

    def _shift_filters_one_year(self, filters):
        """Los filtros con el periodo un año antes, o None si ningún filtro de
        periodo tiene año («agosto 2026» -> «agosto 2025»; con AÑO y MES por
        separado solo cambia AÑO y las etiquetas)."""
        from datetime import date
        from src.semantic.period_parser import period_label

        def back(value):
            try:
                day = date.fromisoformat(str(value)[:10])
            except ValueError:
                return None
            try:
                return day.replace(year=day.year - 1)
            except ValueError:  # 29 de febrero
                return day.replace(year=day.year - 1, day=28)

        years = {}
        shifted = []
        for item in filters or []:
            new = dict(item)
            if not self._is_temporal_filter(item):
                shifted.append(new)
                continue
            if item.get("start") and item.get("end"):
                start, end = back(item["start"]), back(item["end"])
                if start is None or end is None:
                    return None
                new["start"], new["end"] = start.isoformat(), end.isoformat()
                if item.get("year"):
                    years[int(item["year"])] = int(item["year"]) - 1
                    new["year"] = int(item["year"]) - 1
                new["label"] = period_label(start, end)
                new.pop("to_date", None)
            elif item.get("year"):
                years[int(item["year"])] = int(item["year"]) - 1
                new["year"] = int(item["year"]) - 1
            elif self._normalize_text(item.get("column")) in ("ano", "anio", "year"):
                try:
                    years[int(item.get("value"))] = int(item.get("value")) - 1
                    new["value"] = int(item.get("value")) - 1
                except (TypeError, ValueError):
                    return None
            shifted.append(new)
        if not years:
            return None
        for new in shifted:
            if self._is_temporal_filter(new) and new.get("label") and not (new.get("start") and new.get("end")):
                label = str(new["label"])
                for old, year in years.items():
                    label = re.sub(r"(?<![0-9])" + str(old) + r"(?![0-9])", str(year), label)
                new["label"] = label
        return shifted

    def _return_to_topic(self, message, analysis, named):
        """«volviendo a las cirugías programadas, ¿y en 2025?»: el tema anterior
        cuyo indicador coincide con lo que nombra el mensaje."""
        memory = getattr(self, "conversation_memory", None)
        topics = memory.numeric_topics() if memory is not None else []
        for topic in topics:
            label = set(self._normalize_text(topic.get("metric_label")).split())
            if all(word in label or word.rstrip("s") in label or f"{word}s" in label for word in named):
                complement = self._normalize_text(analysis.get("complement"))
                for word in named:
                    complement = re.sub(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", " ", complement)
                complement = " ".join(complement.split())
                why = f"vuelve a un tema anterior de la conversación ({topic.get('metric_label')})"
                plan = self._topic_plan(topic, complement, message=message, why=why)
                if plan is None:
                    return None
                return self._run_followup(plan, message, why)
        return None

    def _numeric_after_documentation(self, message, analysis, previous):
        """Pide un dato tras una respuesta documental: se consulta el indicador
        del que se habló (o el principal del tablero)."""
        complement = analysis.get("complement") or ""
        norm = self._normalize_text(complement)
        builder = self.query_plan_builder
        has_period = False
        try:
            has_period = bool(builder is not None and builder._has_period(norm))
        except Exception:
            has_period = False
        if not (self._NUMERIC_CUE_RE.search(norm) or has_period):
            return None
        phrase, board = self._documentation_subject(previous)
        about_board = bool(board) and (not phrase or "tablero" in phrase.split())
        if phrase and not about_board and self._named_metric_words(phrase):
            question = self._insert_subject(complement, phrase)
            self._note_interpretation(
                question, "pide un dato del indicador del que trató la respuesta documental anterior",
            )
            result = self._process(question)
            self._remember_success(result)
            return result
        if not board:
            return None
        metric = self._board_main_metric(board)
        if metric is not None and builder is not None and self.query_plan_dax_generator is not None:
            topic = {
                "question": f"{metric.get('label')} ({self._board_phrase(board, 'del')})",
                "metric_id": metric["metric_id"], "metric_label": metric.get("label"),
                "semantic_model": metric.get("semantic_model"), "report": board,
                "filters": [], "group_by": [], "ranking": None, "value": None, "metric_format": None,
            }
            why = (
                f"pide un dato después de la respuesta documental sobre {self._board_phrase(board)}: "
                f"se usa su indicador principal ({metric.get('label')})"
            )
            plan = self._topic_plan(topic, complement, message=message, why=why)
            if plan is not None:
                return self._run_followup(plan, message, why)
        question = f"{complement} en {self._board_phrase(board)}".strip()
        self._note_interpretation(question, "pide un dato del tablero de la respuesta documental anterior")
        result = self._process(question)
        self._remember_success(result)
        return result

    # ---------------- reglas que van después del seguimiento clásico ----------------

    def _contextual_generic(self, message, rewritten, analysis):
        """Mensajes que dependen de la consulta anterior sin «y» ni anáfora
        («necesito eso mismo pero de septiembre», «para el comité, los de
        urgencias», «no, me refería a hospitalización», «en septiembre») y, si
        las reglas no bastan, la reescritura con MedGemma."""
        last = self._last_success
        cues = set(analysis.get("cues") or [])
        complement = analysis.get("complement") or ""
        words = self._normalize_text(message).split()
        own_label = last.get("metric_label") if last else None
        strong = bool(cues & self._STRONG_CUES)
        # Con una referencia explícita («eso mismo», «los de...») se perdonan
        # las palabras del indicador anterior; sin ella, nombrar cualquier
        # indicador (también el mismo) hace del mensaje una pregunta completa.
        named = self._named_metric_words(complement, own_label=own_label if strong else None)
        short = len(words) <= self._CONTEXT_SHORT_WORDS and not self._is_new_full_question(message)
        if named and not strong:
            return None  # nombra su propio indicador: pregunta nueva
        if not cues and not short:
            return None
        # metric_words no ve todos los nombres («cantidad de pacientes»: ambas
        # palabras son genéricas o de dimensión); sin referencia explícita, si el
        # texto solo ya resuelve a un indicador es una pregunta completa.
        if not strong and self._resolves_to_metric(complement):
            return None
        if last is not None and complement.strip() and not analysis.get("correction"):
            target = complement
            reason = (
                "corrige la consulta anterior" if analysis.get("correction")
                else "depende de la consulta anterior (" + ", ".join(sorted(cues)) + ")" if cues
                else "es un complemento corto sin indicador propio"
            )
            plan = self._followup_plan(
                message, original=message, complement=target, why=reason,
            )
            if plan is not None:
                return self._run_followup(plan, message, reason)
        if not cues:
            return None  # sin señal explícita no se gasta una llamada al LLM
        response = self._llm_rewrite_turn(message, analysis)
        if response is not None:
            return response
        # Referencia explícita a la respuesta anterior («los de urgencias»,
        # «no, me refería a hospitalización») que no se pudo aplicar: se
        # responde la consulta anterior diciendo qué no se pudo aplicar, en
        # lugar de tratar el mensaje como una pregunta nueva sin sentido.
        target = analysis.get("correction") or complement
        if strong and last is not None and target.strip():
            reason = (
                "se refiere a la consulta anterior (" + ", ".join(sorted(cues)) + "), pero lo que "
                "agrega no es un filtro de ese indicador: se responde la consulta anterior y se dice qué no se aplicó"
            )
            plan = self._followup_plan(
                message, original=message, complement=target, why=reason, lenient=True,
            )
            if plan is not None:
                return self._run_followup(plan, message, reason)
        return None

    def _llm_rewrite_turn(self, message, analysis):
        llm = self._context_llm_provider()
        memory = getattr(self, "conversation_memory", None)
        if llm is None or memory is None or not len(memory):
            return None
        if not (analysis.get("cues") or analysis.get("complement")):
            return None
        transcript = memory.transcript(limit=3)
        history = memory.history(3)
        allowed = " ".join(
            f"{m['text']} {(m.get('meta') or {}).get('interpreted') or ''} "
            f"{(m.get('meta') or {}).get('metric') or ''} {(m.get('meta') or {}).get('dashboard') or ''}"
            for m in history
        )
        # Indicadores: solo los que nombró el usuario o se consultaron (la
        # prosa de una respuesta documental puede nombrar otros: «egresos» no
        # puede volverse «ingresos»).
        metric_text = " ".join(
            f"{m['text'] if m['role'] == 'user' else ''} {(m.get('meta') or {}).get('interpreted') or ''} "
            f"{(m.get('meta') or {}).get('metric') or ''} {(m.get('meta') or {}).get('dashboard') or ''}"
            for m in history
        )
        self._activity("Interpretando el mensaje con el contexto de la conversación (MedGemma)")
        metric_words = getattr(self.query_plan_builder, "metric_words", None)
        try:
            outcome = LLMContextRewriter(llm).rewrite(
                message, transcript, allowed, metric_words=metric_words if callable(metric_words) else None,
                metric_text=metric_text,
                required_text=self._without_period_phrases(analysis.get("complement") or ""),
            )
        except Exception as error:
            outcome = {"status": "error", "reason": f"{type(error).__name__}: {error}", "elapsed": None}
        if outcome.get("status") != "success":
            self._think(
                "Reescritura con MedGemma descartada",
                f"estado: {outcome.get('status')}"
                + (f" · {outcome.get('elapsed')} s" if outcome.get("elapsed") is not None else ""),
                f"propuesta: «{outcome.get('question')}»" if outcome.get("question") else None,
                f"motivo: {outcome.get('reason')}" if outcome.get("reason") else None,
                "se responde el mensaje tal como llegó",
            )
            return None
        question = outcome["question"]
        if self._normalize_text(question) == self._normalize_text(message):
            return None
        self._note_interpretation(
            question,
            f"el mensaje depende de la conversación ({', '.join(analysis.get('cues') or []) or 'mensaje corto sin indicador'}) "
            f"y las reglas no bastaron (MedGemma, {outcome.get('elapsed')} s)",
            source="llm",
        )
        result = self._process(question)
        self._remember_success(result)
        return result

    def _process_turn(self, message):
        self._activity("Interpretando la pregunta")
        applying = getattr(self, "_applying_deferred", None)
        if applying:
            self._think(
                "Mensaje pendiente aplicado a la opción elegida",
                f"«{applying[0]}» llegó mientras esperaba la elección del indicador; con "
                f"«{applying[1]}» elegido se responde ese mensaje sobre la consulta",
            )
        # Mensaje tal como lo escribió el usuario (la contrapregunta pendiente
        # decide con él si es una pregunta nueva aunque se haya reescrito).
        previous = getattr(self, "_turn_message", None)
        self._turn_message = message
        try:
            return self._process_typed_turn(message)
        finally:
            self._turn_message = previous

    def _process_typed_turn(self, message):
        rewritten = self._rewrite_request(message)
        analysis = self._context_analysis(message)
        if analysis is not None:
            contextual = self._contextual_special(message, rewritten, analysis)
            if contextual is not None:
                return self._with_interpretation(contextual)
        followup = self._followup_plan(rewritten, original=message)
        if followup is not None:
            return self._with_interpretation(self._run_followup(followup, message))
        if analysis is not None:
            contextual = self._contextual_generic(message, rewritten, analysis)
            if contextual is not None:
                return self._with_interpretation(contextual)
        result = self._process(rewritten)
        result = self._check_requester_filter(message, rewritten, result)
        self._remember_success(result)
        return result

    def _with_interpretation(self, result):
        if isinstance(result, dict) and self._turn_interpretation:
            result.setdefault("interpreted_as", self._turn_interpretation)
        return result

    def _check_requester_filter(self, message, rewritten, result):
        """«De urgencias se me ha solicitado...»: «de urgencias» puede ser quien
        pide el dato o un filtro. Se conserva como filtro solo si coincide
        exactamente con un valor (SERVICIO = URGENCIAS); si solo se parece a un
        valor de otra columna («Del quirófano» -> ESTADO = Paciente en Quirófano)
        se vuelve a consultar sin esa frase y se dice en el razonamiento."""
        who = requester(message)
        if not who or not isinstance(result, dict) or result.get("status") != "success":
            return result
        plan = result.get("query_plan") or {}
        who_words = [
            word for word in self._normalize_text(who["who"]).split()
            if word not in ("el", "la", "los", "las", "de", "del")
        ]
        if not who_words:
            return result

        def words_of(value):
            return set(self._normalize_text(value).split())

        loose = []
        for item in plan.get("filters") or []:
            if item.get("type") != "categorical":
                continue
            values = item.get("values") if item.get("values") is not None else [item.get("value")]
            for value in values if isinstance(values, (list, tuple)) else [values]:
                value_words = words_of(value)
                hit = all(
                    any(word == other or word.rstrip("s") == other.rstrip("s") or
                        (len(word) >= 5 and other.startswith(word[:5])) for other in value_words)
                    for word in who_words
                )
                exact = self._normalize_text(value).rstrip("s") == " ".join(who_words).rstrip("s")
                if hit and not exact:
                    loose.append((item, value))
        if not loose:
            if any(self._normalize_text(item.get("value")).rstrip("s") == " ".join(who_words).rstrip("s")
                   for item in plan.get("filters") or [] if item.get("type") == "categorical"):
                self._think(
                    "Quién pide el dato o filtro",
                    f"«{who['phrase']}» coincide exactamente con un valor de filtro: se aplica como filtro "
                    "(si era solo quien pide el dato, la respuesta muestra el filtro aplicado)",
                )
            return result
        item, value = loose[0]
        retry = without_requester(rewritten, who["phrase"])
        if not retry or retry == rewritten:
            return result
        self._think(
            "Quién pide el dato o filtro",
            f"«{who['phrase']}» va antes de la petición y solo se parece al valor "
            f"{item.get('column')} = {value} (no coincide exactamente): se toma como quien pide "
            f"el dato y se consulta de nuevo sin esa frase («{retry}»)",
        )
        pending_before = self._pending_query_plan
        second = self._process(retry)
        if isinstance(second, dict) and second.get("status") == "success":
            second_plan = second.get("query_plan")
            if isinstance(second_plan, dict):
                second_plan["notes"] = [
                    f"«{who['phrase']}» se tomó como quien solicita el dato, no como filtro.",
                    *(second_plan.get("notes") or []),
                ]
            return second
        self._think(
            "Quién pide el dato o filtro",
            "sin esa frase no se obtuvo una respuesta directa: se conserva la primera respuesta",
        )
        self._pending_query_plan = pending_before
        self._pending_dashboard_clarification = None
        return result

    def process(self, message):
        top_level = getattr(self, "_trace", None) is None
        if top_level:
            self._turn_interpretation = None
            # Un mensaje aplazado vale solo hasta el botón siguiente.
            self._deferred_context_message = None
        result = self._traced("question", message, lambda: self._process_turn(message))
        if top_level:
            self._record_turn(message, result, via="texto")
        return result

    def _discard_stale_dashboard_clarification(self, message):
        """«¿A qué tablero te refieres?» pendiente y llega una pregunta nueva
        completa: se olvidan la contrapregunta y lo deducido de la pregunta
        anterior (tablero, intención) para resolver la nueva desde cero."""
        state = getattr(self.conversation_manager, "state", None)
        waiting = self._pending_dashboard_clarification is not None or bool(
            getattr(state, "awaiting_clarification", False)
        )
        is_reply = getattr(self.conversation_manager, "is_reply_to_clarification", None)
        if not waiting or not callable(is_reply) or is_reply(message):
            return
        previous = (self._pending_dashboard_clarification or {}).get("question") or getattr(
            state, "original_question", None
        )
        self._think(
            "Contrapregunta de tablero descartada",
            f"«{message}» es una pregunta nueva, no la respuesta a «¿A qué tablero te refieres?» "
            f"de «{previous}»: se resuelve desde cero, sin el tablero ni la intención anteriores",
        )
        self._pending_dashboard_clarification = None
        discard = getattr(self.conversation_manager, "discard_clarification", None)
        if callable(discard):
            discard()

    def _process(
        self,
        message,
    ):
        if self._pending_query_plan is not None:
            response = self._continue_query_plan(message)
            if response is not None:
                return response

        self._discard_stale_dashboard_clarification(message)


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

            self._activity("Buscando en la documentación y redactando la respuesta con MedGemma")
            rag_result = self._call_rag(intent_result)

            self._think(
                "Búsqueda en la documentación (RAG)",
                f"estado: {rag_result.get('status')} · síntesis: {rag_result.get('synthesis_mode')}",
                rag_result.get("synthesis_issue"),
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

            answer = rag_result.get("answer")
            missing_pages = self._pages_without_metrics(original_question)
            if missing_pages and answer:
                # La pregunta pide un dato de una página que solo existe en la
                # documentación: se responde con ella, pero se dice que el
                # indicador no está en los modelos disponibles.
                answer = (
                    f"No encontré el indicador de la página {' / '.join(missing_pages)} en los "
                    "modelos de Power BI disponibles; esto es lo que dice su documentación:\n\n"
                    + str(answer)
                )
            return {
                "status":
                    rag_result.get(
                        "status"
                    ),
                "pages_without_metrics": missing_pages or [],
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
                    answer,
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

from src.chatbot.conversation_state import ConversationState

class ConversationManager:

    def __init__(self, intent_parser):
        self.intent_parser = intent_parser
        self.state = ConversationState()

    # ========================================================
    # CAMPOS QUE TODAVÍA HACEN FALTA
    # ========================================================

    def _get_missing_fields(self):

        return self.intent_parser.determine_missing_fields(
            intent=self.state.intent,
            dashboard=self.state.dashboard,
            metric_type=self.state.metric_type
        )

    # ========================================================
    # INTENTAR COMPLETAR UNA ACLARACIÓN
    # ========================================================

    def _apply_clarification(self, message):

        missing = self.state.missing_fields.copy()

        # --------------------------------------------
        # Dashboard
        # --------------------------------------------

        if "dashboard" in missing:

            dashboard = (
                self.intent_parser.detect_dashboard(
                    message
                )
            )

            if dashboard:
                self.state.dashboard = dashboard

        # --------------------------------------------
        # Métrica
        # --------------------------------------------

        if "metric" in missing:

            metric_type = (
                self.intent_parser.detect_metric_type(
                    message
                )
            )

            if metric_type:
                self.state.metric_type = metric_type

        # También podemos aprovechar para detectar
        # año o mes si el usuario los agrega.

        year = self.intent_parser.detect_year(
            message
        )

        month = self.intent_parser.detect_month(
            message
        )

        if year:
            self.state.year = year

        if month:
            self.state.month = month

    # ========================================================
    # CREAR RESULTADO FINAL DEL ESTADO
    # ========================================================

    def _build_ready_result(self):

        return {
            "status": "ready",

            "intent":
                self.state.intent,

            "dashboard":
                self.state.dashboard,

            "metric_type":
                self.state.metric_type,

            "year":
                self.state.year,

            "month":
                self.state.month,

            "original_question":
                self.state.original_question,
        }

    # ========================================================
    # MENSAJE PRINCIPAL
    # ========================================================

    def handle_message(self, message):

        # ----------------------------------------------------
        # CASO 1:
        # estamos esperando que el usuario aclare algo
        # ----------------------------------------------------

        if self.state.awaiting_clarification:

            self._apply_clarification(
                message
            )

            missing = (
                self._get_missing_fields()
            )

            self.state.missing_fields = missing

            # Todavía falta información
            if missing:

                candidates = []

                if "dashboard" in missing:

                    candidates = (
                        self.intent_parser
                        .get_candidate_dashboards(
                            self.state.original_question
                            or message
                        )
                    )

                clarification = (
                    self.intent_parser
                    .build_clarification_question(
                        missing,
                        candidates
                    )
                )

                return {
                    "status":
                        "needs_clarification",

                    "missing_fields":
                        missing,

                    "question":
                        clarification,

                    "state":
                        self.state.to_dict()
                }

            # Ya quedó completa
            self.state.awaiting_clarification = False

            return self._build_ready_result()

        # ----------------------------------------------------
        # CASO 2:
        # pregunta nueva
        # ----------------------------------------------------

        parsed = (
            self.intent_parser.parse(
                message
            )
        )

        self.state.update_from_intent(
            parsed
        )

        if (
            parsed.status
            == "needs_clarification"
        ):

            return {
                "status":
                    "needs_clarification",

                "missing_fields":
                    parsed.missing_fields,

                "question":
                    parsed.clarification_question,

                "candidates":
                    parsed.candidate_dashboards,

                "state":
                    self.state.to_dict()
            }

        return self._build_ready_result()

    # ========================================================
    # LIMPIAR CONVERSACIÓN
    # ========================================================

    def reset(self):
        self.state.clear()
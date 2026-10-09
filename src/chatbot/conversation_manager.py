import re
import unicodedata

from src.chatbot.conversation_state import ConversationState
from src.chatbot.intent_parser import ordinal_choice_index

_DASHBOARD_STOPWORDS = {
    "tablero", "tableros", "informe", "reporte", "servicio", "area",
    "del", "los", "las", "una", "uno", "por", "con", "para", "quiero",
    "ver", "sobre", "pagina",
}


def _normalize(value):
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text)).strip()

class ConversationManager:

    def __init__(self, intent_parser):
        self.intent_parser = intent_parser
        self.state = ConversationState()
        # Tableros ofrecidos en la última contrapregunta.
        self.candidate_dashboards = []

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
    # TABLERO ELEGIDO ENTRE LOS CANDIDATOS
    # ========================================================

    def _match_candidate_dashboard(self, message):
        """Empareja texto libre (nombre parcial, alias, número) con un candidato."""
        candidates = [c for c in self.candidate_dashboards if c]
        text = _normalize(message)
        if not candidates or not text:
            return None

        if text.isdigit():
            index = int(text)
            return candidates[index - 1] if 1 <= index <= len(candidates) else None

        # «la primera», «el segundo», «la última».
        position = ordinal_choice_index(text, len(candidates))
        if position is not None:
            return candidates[position]

        exact = [c for c in candidates if _normalize(c) == text]
        if len(exact) == 1:
            return exact[0]

        tokens = [
            t for t in text.split()
            if len(t) >= 3 and t not in _DASHBOARD_STOPWORDS
        ]
        if not tokens:
            return None
        matches = [
            c for c in candidates
            if all(
                any(word.startswith(t) or t.startswith(word) and len(word) >= 4
                    for word in _normalize(c).split())
                for t in tokens
            )
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def select_dashboard(self, dashboard):
        """Fija el tablero elegido (botón); la pregunta original se reejecuta."""
        self.state.dashboard = dashboard
        self.state.dashboard_reason = "botón elegido por el usuario"
        self.state.missing_fields = [
            f for f in self.state.missing_fields if f != "dashboard"
        ]

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

            if not dashboard:
                dashboard = self._match_candidate_dashboard(message)

            if dashboard:
                self.state.dashboard = dashboard
                self.state.dashboard_reason = "respuesta del usuario a la contrapregunta"

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

            "dashboard_reason":
                self.state.dashboard_reason,
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

                if candidates:
                    self.candidate_dashboards = list(candidates)

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

                    "candidates":
                        candidates,

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

            self.candidate_dashboards = list(
                parsed.candidate_dashboards or []
            )

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
        self.candidate_dashboards = []
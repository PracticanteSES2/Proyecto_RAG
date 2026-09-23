from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConversationState:

    intent: Optional[str] = None
    dashboard: Optional[str] = None
    metric_type: Optional[str] = None

    year: Optional[int] = None
    month: Optional[int] = None

    missing_fields: list = field(
        default_factory=list
    )

    awaiting_clarification: bool = False

    original_question: Optional[str] = None


    def update_from_intent(
        self,
        parsed_intent
    ):

        data = parsed_intent.to_dict()

        if data.get("intent"):
            self.intent = data["intent"]

        if data.get("dashboard"):
            self.dashboard = data["dashboard"]

        if data.get("metric_type"):
            self.metric_type = data["metric_type"]

        if data.get("year"):
            self.year = data["year"]

        if data.get("month"):
            self.month = data["month"]

        self.missing_fields = (
            data.get("missing_fields")
            or []
        )

        self.awaiting_clarification = (
            data.get("status")
            == "needs_clarification"
        )

        if data.get("original_question"):
            self.original_question = (
                data["original_question"]
            )


    def is_ready(self):

        return (
            not self.awaiting_clarification
            and not self.missing_fields
        )


    def to_dict(self):

        return {
            "intent": self.intent,
            "dashboard": self.dashboard,
            "metric_type": self.metric_type,
            "year": self.year,
            "month": self.month,
            "missing_fields":
                self.missing_fields,
            "awaiting_clarification":
                self.awaiting_clarification,
            "original_question":
                self.original_question,
        }


    def clear(self):

        self.intent = None
        self.dashboard = None
        self.metric_type = None

        self.year = None
        self.month = None

        self.missing_fields = []

        self.awaiting_clarification = False
        self.original_question = None
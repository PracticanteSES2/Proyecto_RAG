import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import Optional


# ============================================================
# CONSTANTES
# ============================================================

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


METRIC_KEYWORDS = {
    "promedio": [
        "promedio",
        "media",
    ],

    "total": [
        "total",
        "cantidad",
        "cuantas",
        "cuantos",
        "numero",
    ],

    "proyeccion": [
        "proyeccion",
        "proyectado",
        "estimacion",
        "estimado",
    ],

    "porcentaje": [
        "porcentaje",
        "porcentual",
        "%",
    ],

    "variacion": [
        "variacion",
        "crecimiento",
        "disminucion",
        "aumento",
        "comparacion",
    ],
}


# ============================================================
# MODELO DE RESULTADO
# ============================================================

@dataclass
class ParsedIntent:

    status: str

    intent: Optional[str] = None

    dashboard: Optional[str] = None

    metric_type: Optional[str] = None

    year: Optional[int] = None

    month: Optional[int] = None

    missing_fields: Optional[list] = None

    clarification_question: Optional[str] = None

    candidate_dashboards: Optional[list] = None

    original_question: Optional[str] = None

    def to_dict(self):
        return asdict(self)


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalize_text(text: str) -> str:

    if not text:
        return ""

    text = text.lower().strip()

    text = "".join(
        character
        for character in unicodedata.normalize(
            "NFD",
            text
        )
        if unicodedata.category(character) != "Mn"
    )

    text = re.sub(
        r"[^a-z0-9%\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# PARSER
# ============================================================

class IntentParser:

    def __init__(
        self,
        retriever
    ):

        self.retriever = retriever

        # Los tableros ya los conoce nuestro HybridRetriever
        self.dashboards = retriever.dashboards


    # --------------------------------------------------------
    # INTENCIÓN GENERAL
    # --------------------------------------------------------

    def detect_intent(
        self,
        question
    ):

        normalized = normalize_text(
            question
        )

        # ====================================================
        # 1. PREGUNTAS SOBRE FILTROS
        # ====================================================

        filter_terms = [
            "filtro",
            "filtros",
            "filtrar",
            "segmentar",
            "segmentador",
            "segmentadores",
        ]

        if any(
            term in normalized
            for term in filter_terms
        ):
            return "get_filters"


        # ====================================================
        # 2. COMPARACIONES NUMÉRICAS
        # ====================================================

        comparison_terms = [
            "comparar",
            "comparacion",
            "versus",
            "vs",
            "frente a",
            "diferencia entre",
        ]

        numeric_terms = [
            "cuanto",
            "cuantos",
            "cuantas",
            "cantidad",
            "numero",
            "total",
            "promedio",
            "porcentaje",
            "valor",
            "variacion",
        ]

        has_comparison = any(
            term in normalized
            for term in comparison_terms
        )

        has_numeric_context = any(
            term in normalized
            for term in numeric_terms
        )

        if (
            has_comparison
            and has_numeric_context
        ):
            return "compare_metric"


        # ====================================================
        # 3. CONSULTAS NUMÉRICAS / ANALÍTICAS
        # ====================================================

        if any(
            term in normalized
            for term in numeric_terms
        ):
            return "query_metric"


        # ====================================================
        # 4. DESCRIPCIÓN GENERAL DEL TABLERO
        # ====================================================

        description_patterns = [
            "que informacion muestra",
            "que muestra el tablero",
            "que contiene el tablero",
            "de que trata el tablero",
            "descripcion del tablero",
        ]

        if any(
            pattern in normalized
            for pattern in description_patterns
        ):
            return "describe_dashboard"


        # ====================================================
        # 5. FALLBACK DOCUMENTAL
        # ====================================================

        # Toda pregunta que no sea claramente numérica
        # se envía al RAG abierto.
        return "general_question"

    # --------------------------------------------------------
    # TABLERO
    # --------------------------------------------------------

    def detect_dashboard(
        self,
        question: str
    ):

        text = normalize_text(question)

        exact_matches = []

        for dashboard in self.dashboards:

            normalized_dashboard = (
                normalize_text(
                    dashboard
                )
            )

            if (
                normalized_dashboard
                in text
            ):

                exact_matches.append(
                    dashboard
                )

        if exact_matches:

            # Preferimos coincidencia exacta más larga
            exact_matches.sort(
                key=len,
                reverse=True
            )

            return exact_matches[0]

        return None


    # --------------------------------------------------------
    # TIPO DE MÉTRICA
    # --------------------------------------------------------

    def detect_metric_type(
        self,
        question: str
    ):

        text = normalize_text(question)

        for metric_type, keywords in (
            METRIC_KEYWORDS.items()
        ):

            if any(
                keyword in text
                for keyword in keywords
            ):

                return metric_type

        return None


    # --------------------------------------------------------
    # AÑO
    # --------------------------------------------------------

    def detect_year(
        self,
        question: str
    ):

        match = re.search(
            r"\b(20\d{2})\b",
            question
        )

        if match:
            return int(
                match.group(1)
            )

        return None


    # --------------------------------------------------------
    # MES
    # --------------------------------------------------------

    def detect_month(
        self,
        question: str
    ):

        text = normalize_text(question)

        for month_name, number in (
            MONTHS.items()
        ):

            if month_name in text:
                return number

        return None


    # --------------------------------------------------------
    # CANDIDATOS CUANDO NO SABEMOS EL TABLERO
    # --------------------------------------------------------

    def get_candidate_dashboards(
        self,
        question: str,
        limit: int = 3
    ):

        results = self.retriever.search(
            question,
            limit=10
        )

        dashboards = []

        for result in results:

            dashboard = result.get(
                "dashboard"
            )

            if (
                dashboard
                and dashboard not in dashboards
            ):
                dashboards.append(
                    dashboard
                )

            if len(dashboards) >= limit:
                break

        return dashboards


    # --------------------------------------------------------
    # DETECCIÓN DE AMBIGÜEDAD
    # --------------------------------------------------------

    def determine_missing_fields(
        self,
        intent,
        dashboard,
        metric_type
    ):
        missing = []

        intents_requiring_dashboard = [
            "describe_dashboard",
            "get_filters",
        ]

        if (
            intent
            in intents_requiring_dashboard
            and not dashboard
        ):
            missing.append(
                "dashboard"
            )

        return missing


    # --------------------------------------------------------
    # CONTRAPREGUNTA
    # --------------------------------------------------------

    def build_clarification_question(
        self,
        missing_fields,
        candidates
    ):

        if "dashboard" in missing_fields:

            if candidates:

                options = ", ".join(
                    candidates
                )

                return (
                    "¿A qué tablero o servicio te refieres? "
                    f"Por ejemplo: {options}."
                )

            return (
                "¿A qué tablero o servicio "
                "te refieres?"
            )


        if "metric" in missing_fields:

            return (
                "¿Qué dato deseas consultar: "
                "total, promedio, porcentaje, "
                "proyección u otro indicador?"
            )

        return (
            "¿Podrías precisar un poco más "
            "la información que deseas consultar?"
        )


    # --------------------------------------------------------
    # PARSE PRINCIPAL
    # --------------------------------------------------------

    def parse(
        self,
        question: str
    ):

        intent = self.detect_intent(
            question
        )

        dashboard = self.detect_dashboard(
            question
        )

        metric_type = self.detect_metric_type(
            question
        )

        year = self.detect_year(
            question
        )

        month = self.detect_month(
            question
        )

        missing_fields = (
            self.determine_missing_fields(
                intent,
                dashboard,
                metric_type
            )
        )

        candidates = []

        if (
            "dashboard"
            in missing_fields
        ):

            candidates = (
                self.get_candidate_dashboards(
                    question
                )
            )

        if missing_fields:

            clarification = (
                self.build_clarification_question(
                    missing_fields,
                    candidates
                )
            )

            return ParsedIntent(

                status=
                    "needs_clarification",

                intent=intent,

                dashboard=dashboard,

                metric_type=metric_type,

                year=year,

                month=month,

                missing_fields=
                    missing_fields,

                clarification_question=
                    clarification,

                candidate_dashboards=
                    candidates,

                original_question=
                    question,
            )

        return ParsedIntent(

            status="ready",

            intent=intent,

            dashboard=dashboard,

            metric_type=metric_type,

            year=year,

            month=month,

            missing_fields=[],

            clarification_question=None,

            candidate_dashboards=[],

            original_question=question,
        )

if __name__ == "__main__":

    from pathlib import Path

    from src.rag.retriever import (
        HybridRetriever
    )

    PROJECT_ROOT = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    QDRANT_PATH = (
        PROJECT_ROOT
        / "data"
        / "vector_db"
        / "qdrant"
    )

    retriever = HybridRetriever(
        QDRANT_PATH
    )

    parser = IntentParser(
        retriever
    )

    questions = [

        "¿Cuál es el promedio mensual de cirugías?",

        "¿Qué información muestra el tablero "
        "de consultas ambulatorias?",

        "¿Qué filtros puedo utilizar "
        "para analizar las cirugías?",

        "¿Cuántas atenciones hubo?",

        "¿Cuál fue el promedio en agosto de 2026?",
    ]

    for question in questions:

        print(
            "\n======================================"
        )

        print(
            "PREGUNTA:",
            question
        )

        result = parser.parse(
            question
        )

        print(
            result.to_dict()
        )
    retriever.close()
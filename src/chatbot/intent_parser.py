import re
import unicodedata
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from typing import Optional

from src.semantic.question_kind import descriptive_phrase


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


# Palabras de un alias de tablero que no lo distinguen de los demás:
# «tablero de lavandería» se reconoce por «lavandería».
DASHBOARD_GENERIC_WORDS = {
    "tablero", "tableros", "informe", "informes", "reporte", "reportes",
    "dashboard", "de", "del", "la", "el", "los", "las", "y", "en", "pagina",
}

# Ordinales con los que se elige una opción de una lista («la primera»).
ORDINALS = {
    "primer": 1, "primera": 1, "primero": 1, "1a": 1, "1ra": 1, "1ro": 1, "1era": 1, "1er": 1,
    "segunda": 2, "segundo": 2, "2a": 2, "2da": 2, "2do": 2,
    "tercera": 3, "tercero": 3, "tercer": 3, "3a": 3, "3ra": 3, "3ro": 3, "3er": 3,
    "cuarta": 4, "cuarto": 4, "4a": 4, "4ta": 4, "4to": 4,
    "quinta": 5, "quinto": 5, "5a": 5, "5ta": 5, "5to": 5,
    "sexta": 6, "sexto": 6, "6a": 6, "6ta": 6, "6to": 6,
    "septima": 7, "septimo": 7, "7a": 7, "7ma": 7, "7mo": 7,
}
_LAST_WORDS = {"ultima", "ultimo"}
_ORDINAL_RE = re.compile(
    r"(?:(?:quiero|dame|elijo|escojo|prefiero|seria|es|me\s+quedo\s+con|con)\s+)?"
    r"(?:(?:la|el|lo)\s+)?"
    r"(?P<ord>[a-z0-9]+)"
    r"(?:\s+(?:opcion|alternativa|indicador|tablero|de\s+(?:la\s+lista|ellas|ellos|arriba)|"
    r"que\s+(?:aparece|sale)|por\s+favor|porfa|gracias))*"
)


def ordinal_choice_index(text, count):
    """Índice (base 0) elegido con un ordinal («la primera», «el segundo»,
    «la última», «primera opción»), o None si el texto no es un ordinal o se
    sale de la lista. `text` debe venir normalizado (minúsculas, sin tildes)."""
    match = _ORDINAL_RE.fullmatch(str(text or "").strip())
    if not match or not count:
        return None
    word = match.group("ord")
    if word in _LAST_WORDS:
        return count - 1
    position = ORDINALS.get(word)
    if position is None or position > count:
        return None
    return position - 1


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

    # Cómo se identificó el tablero (nombre, alias, alias con error de
    # tipeo o único candidato de la búsqueda): se muestra en el razonamiento.
    dashboard_reason: Optional[str] = None

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
        retriever,
        source_router=None,
    ):

        self.retriever = retriever

        # Los tableros ya los conoce nuestro HybridRetriever
        self.dashboards = retriever.dashboards

        # Registro de fuentes (informe + alias): «tablero de lavandería»
        # identifica «Tablero Lavanderia» aunque no se escriba su nombre exacto.
        self.source_router = source_router

        # Motivo con el que detect_dashboard identificó el último tablero.
        self.last_dashboard_reason = None


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

        # «¿Cómo se calcula el porcentaje de ocupación?», «¿cuáles son los
        # rangos del NEDOCS?»: piden una explicación, no un valor, aunque
        # contengan palabras numéricas. Van al RAG documental.
        if descriptive_phrase(question):
            description_patterns = [
                "que informacion muestra",
                "que muestra el tablero",
                "que contiene el tablero",
                "de que trata el tablero",
                "descripcion del tablero",
            ]
            if any(pattern in normalized for pattern in description_patterns):
                return "describe_dashboard"
            return "general_question"

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

            # «botón azul en tiempos de urgencias»: «URGENCIAS» (nombre de
            # una página/tablero documentado y también de un servicio) está
            # dentro de un nombre más largo de OTRO tablero («tiempos de
            # urgencias»): no se fija ese tablero corto.
            shadow = self._shadowing_alias(text, exact_matches[0])
            if shadow is not None:
                alias, dashboard = shadow
                if dashboard:
                    self.last_dashboard_reason = f"alias más específico «{alias}»"
                    return dashboard
                self.last_dashboard_reason = None
                return None

            self.last_dashboard_reason = "nombre del tablero"
            return exact_matches[0]

        alias_match = self._detect_dashboard_by_alias(text)
        if alias_match:
            dashboard, reason = alias_match
            self.last_dashboard_reason = reason
            return dashboard

        self.last_dashboard_reason = None
        return None

    # --------------------------------------------------------
    # TABLERO POR ALIAS (índice RAG + registro de fuentes)
    # --------------------------------------------------------

    def _dashboard_aliases(self):
        """{alias normalizado: tablero}: alias del índice RAG y del registro
        de fuentes (informe y alias) de los tableros conocidos."""
        dashboards = list(self.dashboards or [])
        known = {normalize_text(name): name for name in dashboards if name}
        aliases = {}
        retriever_aliases = getattr(self.retriever, "dashboard_aliases", None) or {}
        for alias, dashboard in retriever_aliases.items():
            if dashboard in dashboards and normalize_text(alias):
                aliases[normalize_text(alias)] = dashboard
        for source in getattr(self.source_router, "sources", None) or []:
            dashboard = known.get(normalize_text(source.get("report")))
            if not dashboard:
                continue
            for alias in [source.get("report"), *(source.get("aliases") or [])]:
                normalized = normalize_text(alias)
                if normalized and normalized not in aliases:
                    aliases[normalized] = dashboard
        return aliases

    def _shadowing_alias(self, text, dashboard):
        """(alias, tablero o None) si el nombre `dashboard` aparece en la
        pregunta solo como parte de un alias más largo de otro tablero/informe
        del registro de fuentes («urgencias» dentro de «tiempos de urgencias»).
        El tablero devuelto es el del alias si es un tablero conocido."""
        name = normalize_text(dashboard)
        if not name:
            return None
        known = {normalize_text(item): item for item in self.dashboards or [] if item}
        aliases = self._dashboard_aliases()
        candidates = []
        for source in getattr(self.source_router, "sources", None) or []:
            for value in [source.get("report"), *(source.get("aliases") or [])]:
                alias = normalize_text(value)
                if (
                    alias and len(alias) > len(name) and alias != name
                    and re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", alias)
                    and re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text)
                ):
                    candidates.append(alias)
        if not candidates:
            return None
        alias = max(candidates, key=len)
        target = aliases.get(alias) or known.get(alias)
        if target and normalize_text(target) == name:
            return None
        return alias, target

    @staticmethod
    def _distinctive_words(text):
        return [
            word for word in text.split()
            if word not in DASHBOARD_GENERIC_WORDS and len(word) >= 3
        ]

    def _detect_dashboard_by_alias(self, text):
        """(tablero, motivo) por alias normalizado; tolera un error de tipeo
        en palabras largas («lavandria»). Solo responde si las coincidencias
        señalan un único tablero (o una es claramente más específica)."""
        aliases = self._dashboard_aliases()
        if not text or not aliases:
            return None

        exact = {}
        for alias, dashboard in aliases.items():
            if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text):
                exact[dashboard] = max(exact.get(dashboard, 0), len(alias))
        if exact:
            ranked = sorted(exact.items(), key=lambda item: item[1], reverse=True)
            if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
                return ranked[0][0], "alias del tablero"
            return None

        # Mismas palabras distintivas que un alias, con a lo sumo un error
        # de tipeo por palabra (solo palabras de 6 letras o más). Solo cuando
        # la pregunta nombra un tablero («tablero de lavandria»): «cirugías»
        # suelto no debe fijar el Tablero Quirúrgico.
        if not re.search(r"(?<![a-z0-9])(?:tablero|tableros|informe|reporte|dashboard)(?![a-z0-9])", text):
            return None
        words = self._distinctive_words(text)
        fuzzy = set()
        for alias, dashboard in aliases.items():
            alias_words = self._distinctive_words(alias)
            if alias_words and all(
                any(
                    word == other or (
                        len(word) >= 6 and len(other) >= 6
                        and SequenceMatcher(None, word, other).ratio() >= 0.88
                    )
                    for other in words
                )
                for word in alias_words
            ):
                fuzzy.add(dashboard)
        if len(fuzzy) == 1:
            return fuzzy.pop(), "alias del tablero (con error de tipeo)"
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

        # Palabra completa: «mayores de edad» no es mayo.
        for month_name, number in (
            MONTHS.items()
        ):

            if re.search(
                r"(?<![a-z0-9])" + month_name + r"(?![a-z0-9])",
                text
            ):
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

        dashboard_reason = (
            self.last_dashboard_reason if dashboard else None
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

            # Un único tablero candidato: no se pregunta «¿A qué tablero?»
            # con un solo botón.
            if len(candidates) == 1:
                dashboard = candidates[0]
                dashboard_reason = "único tablero candidato en la documentación"
                candidates = []
                missing_fields = self.determine_missing_fields(
                    intent,
                    dashboard,
                    metric_type
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

            dashboard_reason=dashboard_reason,
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
"""
Lógica pura de ranking para el RAG documental (sin modelos ni Qdrant).

Contiene:
- tokenización normalizada (sin tildes, sin palabras vacías, plural simple);
- índice léxico tipo BM25 normalizado a [0, 1] con bonificación por frases
  («turno ok», «botón azul»);
- detección de la intención documental de la pregunta (qué muestra, filtros,
  cómo se calcula, qué significa, técnica);
- pesos por tipo de chunk según la intención;
- detección de alcance (informe / página) por coincidencia de tokens;
- selección final con diversidad de fuentes.

Se mantiene separada del retriever para poder probarla sin modelo real.
"""
import math
import re
import unicodedata
from collections import Counter, defaultdict


# ============================================================
# NORMALIZACIÓN Y TOKENS
# ============================================================

def normalize_text(text):
    text = str(text or "").lower().strip()
    text = "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if unicodedata.category(character) != "Mn"
    )
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Palabras vacías del español + términos de formulación de la pregunta que
# no aportan contenido para buscar ("qué muestra", "cómo se calcula", ...).
STOPWORDS = {
    "a", "al", "algo", "algun", "alguna", "ante", "aqui", "asi", "cada",
    "como", "con", "cual", "cuales", "cuando", "de", "del", "desde",
    "donde", "dos", "e", "el", "ella", "ellos", "en", "entre", "era",
    "es", "esa", "ese", "eso", "esta", "este", "esto", "estos", "estas",
    "fue", "ha", "hay", "la", "las", "le", "les", "lo", "los", "mas",
    "me", "mi", "mis", "muy", "no", "nos", "o", "para", "pero", "por",
    "porque", "q", "que", "quien", "se", "sea", "ser", "si", "sin",
    "sobre", "son", "su", "sus", "te", "tu", "u", "un", "una", "unas",
    "uno", "unos", "y", "ya", "yo", "puedo", "puede", "hace", "hacer",
    # Formulación de la pregunta
    "calcula", "calculan", "calcular", "calculado", "calculada",
    "contiene", "contienen", "dime", "explica", "explicame", "indica",
    "indican", "informacion", "muestra", "muestran", "mostrar", "obtiene",
    "obtienen", "quiero", "saber", "significa", "significan", "sirve",
    "sirven", "tiene", "tienen", "trata", "ver", "favor",
}

# Términos genéricos de navegación: no identifican un tablero concreto.
GENERIC_TERMS = {
    "tablero", "tableros", "dashboard", "dashboards", "informe", "informes",
    "reporte", "reportes", "pagina", "paginas", "hoja", "hojas", "inicio",
}

_PLURAL_ES_CONSONANTS = set("rlndzj")


def stem(word):
    """Singular muy simple y simétrico (se aplica igual a pregunta y chunk)."""
    if len(word) > 5 and word.endswith("es") and word[-3] in _PLURAL_ES_CONSONANTS:
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def tokenize(text, drop_stopwords=True):
    tokens = []
    for word in normalize_text(text).split():
        if drop_stopwords and word in STOPWORDS:
            continue
        tokens.append(stem(word))
    return tokens


GENERIC_STEMS = {stem(term) for term in GENERIC_TERMS}


def name_tokens(name):
    """Tokens distintivos de un nombre de informe/página."""
    return tuple(
        token
        for token in tokenize(name)
        if token not in GENERIC_STEMS
    )


# ============================================================
# INTENCIÓN DOCUMENTAL
# ============================================================

INTENT_PATTERNS = {
    "technical": [
        r"\bsql\b", r"\bquery\b", r"\bqueries\b", r"\bconsultas? (?:sql|tecnicas?)\b",
        r"\borigen de (?:los )?datos\b", r"\bfuente de (?:los )?datos\b",
        r"\bbase de datos\b", r"\bque tablas?\b", r"\btablas? (?:de origen|origen|fuente)\b",
        r"\bcolumnas?\b", r"\bde donde (?:salen|se obtienen|vienen)\b",
    ],
    "filters": [
        r"\bfiltr", r"\bsegment",
    ],
    "calculation": [
        r"\bcomo se calcula", r"\bcomo calcula", r"\bcomo se obtiene",
        r"\bcomo se mide", r"\bformula", r"\bcalculo\b", r"\bcalcul",
        r"\bexpresion\b", r"\bdax\b",
    ],
    "overview": [
        r"\bque muestra", r"\bque informacion", r"\bpara que sirve",
        r"\bque contiene", r"\bde que trata", r"\bque tiene el tablero",
        r"\b(?:que|q) es el tablero",r"\bdescrib", r"\bdescripcion",
        r"\bque indicadores", r"\bque puedo ver", r"\bque hay en",
        r"\bque se ve\b",
    ],
    "definition": [
        r"\bque significa", r"\bsignificado", r"\bque es\b", r"\bq es\b",
        r"\bque son\b", r"\bque indica", r"\brangos?\b", r"\bcolor",
        r"\bsemaforo", r"\bcategorias?\b", r"\bniveles?\b",
    ],
}

INTENT_ORDER = ["technical", "filters", "calculation", "overview", "definition"]


def detect_question_intent(question):
    normalized = normalize_text(question)
    for intent in INTENT_ORDER:
        if any(re.search(pattern, normalized) for pattern in INTENT_PATTERNS[intent]):
            return intent
    return "general"


# Pesos aditivos por tipo de chunk. Los volcados SQL y el contexto de tablas
# compiten con las descripciones en lenguaje natural; se penalizan salvo que
# la pregunta sea técnica.
BASE_TYPE_PRIOR = {
    "dashboard_overview": 0.04,
    "document_section": 0.05,
    "documented_measure": 0.05,
    "indicator": 0.04,
    "filter": 0.03,
    "visual": 0.02,
    "measure": 0.0,
    "calculated_column": -0.03,
    "table_context": -0.12,
    "sql_query": -0.20,
}

INTENT_TYPE_BONUS = {
    "overview": {"dashboard_overview": 0.14, "visual": 0.03, "document_section": 0.03},
    "filters": {"filter": 0.12, "dashboard_overview": 0.06, "visual": 0.03},
    "calculation": {
        "documented_measure": 0.14, "measure": 0.10, "calculated_column": 0.06,
        "indicator": 0.06, "document_section": 0.03,
    },
    "definition": {
        "document_section": 0.05, "documented_measure": 0.05, "visual": 0.03,
        "dashboard_overview": 0.03, "indicator": 0.04,
    },
    "technical": {"sql_query": 0.24, "table_context": 0.16, "calculated_column": 0.05},
    "general": {},
}


def type_prior(chunk_type, intent):
    prior = BASE_TYPE_PRIOR.get(chunk_type or "", 0.0)
    prior += INTENT_TYPE_BONUS.get(intent, {}).get(chunk_type or "", 0.0)
    return prior


# ============================================================
# ÍNDICE LÉXICO
# ============================================================

class LexicalIndex:
    """BM25 normalizado: cobertura ponderada por rareza de los términos.

    score = Σ idf(t)·tf_sat(t) / Σ idf(t)   (en [0, 1])
    más una bonificación cuando dos términos consecutivos de la pregunta
    aparecen juntos en el chunk («turno ok», «boton azul»).

    Cada término de la consulta puede ser un token o una tupla de variantes
    equivalentes (p. ej. filtro/segmentador); cuenta como un solo término.
    """

    K1 = 1.2
    B = 0.5
    PHRASE_BONUS = 0.15
    MAX_PHRASE_BONUS = 0.30

    def __init__(self, documents):
        # documents: lista de listas de tokens (en orden).
        self.documents = [list(doc) for doc in documents]
        self.counters = [Counter(doc) for doc in self.documents]
        self.bigrams = [
            set(zip(doc, doc[1:]))
            for doc in self.documents
        ]
        self.size = len(self.documents)
        self.avg_length = (
            sum(len(doc) for doc in self.documents) / self.size
            if self.size else 1.0
        ) or 1.0
        self.document_frequency = Counter()
        for counter in self.counters:
            self.document_frequency.update(counter.keys())

    @staticmethod
    def _variants(term):
        return term if isinstance(term, tuple) else (term,)

    def idf(self, term):
        # Con variantes se usa la más frecuente (idf más conservador).
        df = max(
            self.document_frequency.get(token, 0)
            for token in self._variants(term)
        )
        return math.log(1.0 + (self.size - df + 0.5) / (df + 0.5))

    def matched_terms(self, index, query_terms):
        """Términos de la consulta presentes en el chunk."""
        counter = self.counters[index]
        return {
            term
            for term in query_terms
            if any(counter.get(token, 0) for token in self._variants(term))
        }

    def score(self, index, query_terms):
        unique = list(dict.fromkeys(query_terms))
        if not unique:
            return 0.0

        counter = self.counters[index]
        length = len(self.documents[index]) or 1
        norm = self.K1 * (1 - self.B + self.B * length / self.avg_length)

        weighted = 0.0
        total = 0.0
        for term in unique:
            idf = self.idf(term)
            total += idf
            tf = sum(counter.get(token, 0) for token in self._variants(term))
            if tf:
                # Saturación BM25 escalada para que una aparición en un chunk
                # de longitud media valga 1 (cobertura); los chunks largos
                # (volcados SQL) valen algo menos.
                weighted += idf * min(1.0, tf * (1 + self.K1) / (tf + norm))

        score = weighted / total if total else 0.0

        bonus = 0.0
        for first, second in zip(query_terms, query_terms[1:]):
            pair = (self._variants(first)[0], self._variants(second)[0])
            if pair[0] != pair[1] and pair in self.bigrams[index]:
                bonus += self.PHRASE_BONUS
        score += min(bonus, self.MAX_PHRASE_BONUS)

        return min(score, 1.0)


# Variantes léxicas: la pregunta dice «filtros» y la documentación
# «segmentador» o «permiten filtrar».
TERM_VARIANTS = {
    "filtro": ("filtro", "filtrar", "filtran", "filtrado", "segmentador",
               "segmentar", "segmentan", "segmentacion"),
    "segmentador": ("segmentador", "segmentar", "segmentan", "filtro", "filtrar"),
    "color": ("color", "semaforo", "semaforizacion"),
    "formula": ("formula", "calculo", "expresion"),
}

# Término implícito según la intención (se añade a la consulta léxica).
INTENT_TERMS = {
    # Formas ya normalizadas por stem(): «variables» -> «variabl».
    "calculation": ("calculo", "formula", "variable", "variabl", "expresion"),
}


def query_terms(question, exclude=(), intent=None):
    """Términos léxicos de la pregunta: sin palabras vacías, sin términos
    genéricos («tablero») ni los que solo nombran el alcance detectado."""
    exclude = set(exclude or ())
    terms = []
    for token in tokenize(question):
        if token in GENERIC_STEMS or token in exclude:
            continue
        terms.append(TERM_VARIANTS.get(token, token))
    extra = INTENT_TERMS.get(intent)
    if extra and extra not in terms:
        terms.append(extra)
    return terms


# ============================================================
# ALCANCE (INFORME / PÁGINA)
# ============================================================

class ScopeIndex:
    """Detecta qué informe o página nombra la pregunta.

    - Informe: nombre del modelo semántico, alias del tablero y source_group.
    - Página: el campo `dashboard` del chunk.
    Coincide si TODOS los tokens distintivos del nombre están en la pregunta
    (se ignoran «de», «del», «tablero», tildes y plurales). Gana el nombre con
    más tokens; ante empate se prefiere el informe.
    """

    def __init__(self):
        self.report_names = defaultdict(set)   # tokens -> {source_group}
        self.page_names = defaultdict(set)     # tokens -> {(source_group, page)}
        self.report_labels = {}                # source_group -> nombre legible

    def add_report_name(self, source_group, name):
        tokens = name_tokens(name)
        if tokens and source_group:
            self.report_names[tokens].add(source_group)

    def add_page(self, source_group, page):
        tokens = name_tokens(page)
        if tokens and page:
            self.page_names[tokens].add((source_group, page))

    def detect(self, question):
        question_tokens = set(tokenize(question))
        if not question_tokens:
            return None

        best_weight = 0
        reports = set()
        pages = set()
        matched = set()

        def consider(tokens):
            return len(tokens) if set(tokens) <= question_tokens else 0

        for tokens, groups in self.report_names.items():
            weight = consider(tokens)
            if not weight:
                continue
            if weight > best_weight:
                best_weight, reports, pages, matched = weight, set(groups), set(), set(tokens)
            elif weight == best_weight:
                reports |= groups
                matched |= set(tokens)

        for tokens, entries in self.page_names.items():
            weight = consider(tokens)
            if not weight:
                continue
            if weight > best_weight:
                best_weight, reports, pages, matched = weight, set(), set(entries), set(tokens)
            elif weight == best_weight:
                pages |= entries
                matched |= set(tokens)

        if not best_weight:
            return None

        if reports:
            # Se nombró el informe: alcance = todo el informe. Las páginas
            # empatadas del mismo informe se conservan como foco.
            focus = {page for group, page in pages if group in reports}
            return {
                "kind": "report",
                "source_groups": sorted(reports),
                "pages": sorted(focus),
                "matched_tokens": sorted(matched),
                "weight": best_weight,
            }

        return {
            "kind": "page",
            "source_groups": sorted({group for group, _ in pages}),
            "pages": sorted({page for _, page in pages}),
            "matched_tokens": sorted(matched),
            "weight": best_weight,
        }


# ============================================================
# SELECCIÓN CON DIVERSIDAD
# ============================================================

def select_diverse(candidates, limit, same_key_penalty=0.03, same_page_penalty=0.01,
                   max_per_key=4, max_sql=1, technical=False):
    """Selección voraz tipo MMR sobre candidatos ya puntuados.

    candidates: dicts con "final_score", "text", "dashboard", "chunk_type",
    "section". Penaliza repetir el mismo subapartado (página + tipo + sección)
    y descarta textos duplicados.
    """
    remaining = sorted(candidates, key=lambda item: item["final_score"], reverse=True)
    selected = []
    seen_texts = set()
    key_count = Counter()
    page_count = Counter()
    sql_count = 0

    while remaining and len(selected) < limit:
        best_index = None
        best_value = None
        for index, item in enumerate(remaining):
            key = (item.get("dashboard"), item.get("chunk_type"), item.get("section"))
            value = (
                item["final_score"]
                - same_key_penalty * key_count[key]
                - same_page_penalty * page_count[item.get("dashboard")]
            )
            if best_value is None or value > best_value:
                best_index, best_value = index, value
            # Los candidatos están ordenados: si ya no pueden superar al mejor
            # aun sin penalización, se corta la búsqueda.
            if best_value is not None and item["final_score"] < best_value:
                break

        item = remaining.pop(best_index)
        text = (item.get("text") or "").strip()
        key = (item.get("dashboard"), item.get("chunk_type"), item.get("section"))

        if not text or text in seen_texts:
            continue
        if key_count[key] >= max_per_key:
            continue
        if item.get("chunk_type") == "sql_query" and not technical:
            if sql_count >= max_sql:
                continue
            sql_count += 1

        seen_texts.add(text)
        key_count[key] += 1
        page_count[item.get("dashboard")] += 1
        selected.append(item)

    return selected

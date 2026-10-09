"""
Métricas de calidad de una respuesta del chatbot (sobre todo RAG/LLM).

Todas son heurísticas deterministas y baratas; no llaman a ningún servicio:

- cobertura de palabras clave (tomadas del docx fuente del caso),
- cifras de la respuesta que no aparecen en las fuentes recuperadas ni en la
  pregunta (posible alucinación),
- idioma (español frente a inglés, por palabras vacías),
- longitud (caracteres y palabras),
- menciones a procesos internos que nunca deben verse ("chunk", "embedding",
  "Qdrant", "prompt", ...).

Además deja un gancho opcional para un juez LLM (desactivado por defecto):
`load_judge("paquete.modulo:funcion")` devuelve una función
`juez(caso, turno, result, ui) -> {"score": 0..1, "comment": str}`.
"""
import importlib
import re
import unicodedata

# ----------------------------------------------------------------------------
# Normalización
# ----------------------------------------------------------------------------


def strip_accents(text):
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", str(text or ""))
        if not unicodedata.combining(ch)
    )


def norm(text):
    """minúsculas, sin tildes, solo letras/dígitos y espacios simples."""
    text = strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9ñ%]+", " ", text)
    return " ".join(text.split())


def contains(haystack, needle):
    """`needle` está en `haystack` ignorando mayúsculas, tildes y puntuación."""
    needle = norm(needle)
    return bool(needle) and needle in norm(haystack)


# ----------------------------------------------------------------------------
# Palabras clave
# ----------------------------------------------------------------------------


def keyword_coverage(text, keywords):
    """(fracción cubierta, encontradas, faltantes). Sin palabras clave -> (None, [], [])."""
    keywords = [k for k in (keywords or []) if str(k).strip()]
    if not keywords:
        return None, [], []
    found = [k for k in keywords if contains(text, k)]
    missing = [k for k in keywords if k not in found]
    return len(found) / len(keywords), found, missing


# ----------------------------------------------------------------------------
# Cifras (posible alucinación)
# ----------------------------------------------------------------------------

_NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?![\w])")
_LIST_MARKER = re.compile(r"^\s*\d{1,2}[.)]\s", re.MULTILINE)


def _number_values(token):
    """Valores posibles de un número escrito en formato español o inglés."""
    token = token.strip(".,")
    values = set()
    if not token:
        return values
    # Español: 3.906,4 / 488,3 / 12.500
    es = token.replace(".", "").replace(",", ".")
    # Inglés: 3,906.4 / 488.3
    en = token.replace(",", "")
    for candidate in (es, en, token.replace(",", ".")):
        try:
            values.add(round(float(candidate), 4))
        except ValueError:
            continue
    return values


def extract_numbers(text):
    """Números de un texto (como cadenas), sin los marcadores de lista "1." ni dígitos sueltos."""
    text = _LIST_MARKER.sub(" ", str(text or ""))
    numbers = []
    for match in _NUMBER.finditer(text):
        token = match.group(0).strip(".,")
        digits = re.sub(r"\D", "", token)
        if len(digits) <= 1:
            continue  # "1", "3": enumeraciones, "1 a 3 párrafos"...
        numbers.append(token)
    return numbers


def unsupported_numbers(answer, evidence_texts):
    """Cifras de `answer` que no aparecen en ninguna evidencia (fuentes, pregunta)."""
    supported = set()
    for text in evidence_texts or []:
        for token in _NUMBER.findall(str(text or "")):
            supported |= _number_values(token)
    out = []
    for token in extract_numbers(answer):
        if not (_number_values(token) & supported) and token not in out:
            out.append(token)
    return out


# ----------------------------------------------------------------------------
# Idioma
# ----------------------------------------------------------------------------

_ES = {
    "el", "la", "los", "las", "de", "del", "que", "en", "y", "por", "para", "con",
    "una", "un", "es", "se", "su", "sus", "al", "como", "permite", "muestra",
    "tablero", "indicador", "segun", "total", "promedio", "mes", "ano", "no", "este",
    "esta", "lo", "le", "mas", "sobre", "entre", "cada",
}
_EN = {
    "the", "of", "and", "to", "in", "is", "for", "with", "this", "that", "shows",
    "dashboard", "by", "are", "it", "on", "from", "as", "be", "which", "average",
    "per", "month", "year", "not", "there", "these", "has", "have",
}


def spanish_ratio(text):
    """Fracción de palabras vacías españolas frente a inglesas (None si no hay señal)."""
    words = norm(text).split()
    es = sum(1 for w in words if w in _ES)
    en = sum(1 for w in words if w in _EN)
    if es + en < 3:
        return None
    return es / (es + en)


# ----------------------------------------------------------------------------
# Términos internos prohibidos
# ----------------------------------------------------------------------------

INTERNAL_TERMS = (
    r"\bchunks?\b", r"\bembeddings?\b", r"\bqdrant\b", r"\bprompts?\b",
    r"\bollama\b", r"contexto recuperado", r"\[fuente\s*\d", r"\bsystem prompt\b",
    r"\bvector(?:ial|es)?\s+(?:store|db|database)\b", r"\bsentence[- ]transformers?\b",
)


def internal_terms(text):
    low = strip_accents(str(text or "")).lower()
    found = []
    for pattern in INTERNAL_TERMS:
        match = re.search(pattern, low)
        if match and match.group(0) not in found:
            found.append(match.group(0))
    return found


# ----------------------------------------------------------------------------
# Resumen de calidad de un turno
# ----------------------------------------------------------------------------


def source_texts(result):
    """Textos de las fuentes que el RAG usó para responder."""
    texts = []
    for source in (result or {}).get("sources") or []:
        if isinstance(source, dict):
            texts.append(source.get("text") or "")
            for key in ("dashboard", "page", "section", "title"):
                if source.get(key):
                    texts.append(str(source.get(key)))
    return texts


def quality_metrics(ui, result, question="", keywords=None):
    """Métricas de calidad del texto mostrado (`ui`) para un turno."""
    text = str(ui or "")
    coverage, found, missing = keyword_coverage(text, keywords)
    evidence = source_texts(result) + [question or ""]
    route = (result or {}).get("route")
    return {
        "chars": len(text),
        "words": len(text.split()),
        "keyword_coverage": None if coverage is None else round(coverage, 3),
        "keywords_found": found,
        "keywords_missing": missing,
        # Solo se evalúan cifras "inventadas" en respuestas documentales.
        "unsupported_numbers": unsupported_numbers(text, evidence) if route == "rag" else [],
        "spanish_ratio": None if spanish_ratio(text) is None else round(spanish_ratio(text), 3),
        "internal_terms": internal_terms(text),
        "n_sources": len((result or {}).get("sources") or []),
        "synthesis_mode": (result or {}).get("synthesis_mode"),
    }


# ----------------------------------------------------------------------------
# Juez LLM opcional (desactivado por defecto)
# ----------------------------------------------------------------------------


def load_judge(spec):
    """'paquete.modulo:funcion' -> función juez, o None si spec está vacío.

    La función recibe (caso, turno, result, ui) y devuelve un dict con al menos
    "score" (0..1) y opcionalmente "comment". El evaluador NO la usa salvo que
    se pase --judge; así nunca se envían datos a un servicio sin pedirlo.
    """
    if not spec:
        return None
    module_name, _, func_name = str(spec).partition(":")
    module = importlib.import_module(module_name)
    judge = getattr(module, func_name or "judge")
    if not callable(judge):
        raise TypeError(f"{spec} no es invocable")
    return judge

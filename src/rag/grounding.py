"""Salvaguarda de respaldo de la respuesta documental (RAG).

Una respuesta del RAG NUNCA puede afirmar cifras, tendencias ni listas de valores que no estén en
la documentación recuperada (auditoría holdout 2: G16 inventó una lista de especialidades, G29
afirmó «subió» sin cifras, MT19.3 dio números). Se aplica a la síntesis con el LLM y al respaldo
extractivo (RAGAnswerEngine):

- cada número de la respuesta debe aparecer en las fuentes o en la pregunta (se comparan todas las
  lecturas de «1.234,5» / «1,234.5»); la frase o viñeta con un número sin respaldo se quita;
- una frase que afirma una tendencia («subió», «bajó», «aumentó», «disminuyó»...) cuyo verbo no está
  en las fuentes se quita (la dirección de un dato no sale de la documentación);
- una viñeta corta sin ninguna palabra de contenido de las fuentes se quita (lista inventada).

Si después de quitar no queda una respuesta con contenido, quien llama la trata como «sin evidencia».
"""
import re
import unicodedata

_NUMBER_RE = re.compile(r"(?<![\w])\d+(?:[.,]\d+)*(?![\w])")
# Marcadores de lista («1.», «2)») y de paso al comienzo de la línea: no son cifras afirmadas.
_LIST_MARKER_RE = re.compile(r"^(\s*)(?:\d{1,2}[.)]|[*\-•])\s+", re.MULTILINE)
_TREND_RE = re.compile(
    r"(?<![a-z])(?:sub(?:io|ieron|e|en)|baj(?:o|aron|a|an)|aument(?:o|aron|a|an)|disminu(?:yo|yeron|ye|yen)"
    r"|crec(?:io|ieron|e|en)|cay(?:o|eron)|descend(?:io|ieron)|empeor(?:o|aron)|mejor(?:o|aron))(?![a-z])"
)
_CONTENT_STOP = {
    "para", "como", "esta", "este", "estos", "estas", "entre", "sobre", "segun", "tiene", "tienen",
    "donde", "cuando", "tambien", "solo", "cada", "otro", "otra", "otros", "otras", "desde", "hasta",
    "datos", "dato", "total", "valor", "valores", "tablero", "tableros", "indicador", "indicadores",
}


def _fold(text):
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def number_readings(token):
    """Valores posibles de un número escrito con «.» o «,» (miles o decimales)."""
    token = token.strip()
    readings = {token}
    digits = re.sub(r"[.,]", "", token)
    readings.add(digits.lstrip("0") or "0")
    for decimal in (".", ","):
        if decimal in token:
            head, _, tail = token.rpartition(decimal)
            head = re.sub(r"[.,]", "", head).lstrip("0") or "0"
            tail = tail.rstrip("0")
            readings.add(head + ("." + tail if tail else ""))
    return readings


def _supported_numbers(texts):
    supported = set()
    for text in texts:
        for match in _NUMBER_RE.finditer(str(text or "")):
            supported |= number_readings(match.group(0))
    return supported


def _content_words(text):
    return {word for word in re.findall(r"[a-z0-9ñ]{4,}", _fold(text)) if word not in _CONTENT_STOP}


def _stem(word):
    return word[:5]


def _pieces(answer):
    """Divide la respuesta en piezas (líneas; las líneas largas, en frases) conservando el orden."""
    pieces = []
    for line in str(answer).split("\n"):
        if not line.strip() or _LIST_MARKER_RE.match(line):
            pieces.append((line, True))
            continue
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])", line)
        for index, sentence in enumerate(sentences):
            pieces.append((sentence, index == len(sentences) - 1))
    return pieces


def unsupported_pieces(answer, sources_text, question=""):
    """Frases/viñetas de `answer` sin respaldo en `sources_text` (lista de str)."""
    if not answer:
        return []
    context = "\n".join(str(text or "") for text in sources_text)
    numbers = _supported_numbers([context, question])
    folded_context = _fold(context)
    context_words = _content_words(context)
    context_stems = {_stem(word) for word in context_words}
    found = []
    for piece, _ in _pieces(answer):
        text = _LIST_MARKER_RE.sub(r"\1", piece)
        if not text.strip():
            continue
        claimed = [match.group(0) for match in _NUMBER_RE.finditer(text)]
        if any(not (number_readings(token) & numbers) for token in claimed):
            found.append((piece, "cifra"))
            continue
        folded = _fold(text)
        trend = _TREND_RE.search(folded)
        if trend and _stem(trend.group(0)) not in folded_context:
            found.append((piece, "tendencia"))
            continue
        if _LIST_MARKER_RE.match(piece):
            words = _content_words(re.sub(r"\*\*|__", "", text))
            if words and len(words) <= 6 and not any(_stem(word) in context_stems for word in words):
                found.append((piece, "lista"))
    return found


def ground_answer(answer, sources_text, question=""):
    """(respuesta respaldada, quitados). Quita frases y viñetas con cifras, tendencias o elementos de
    lista que no están en las fuentes. Si no se quitó nada, la respuesta vuelve igual."""
    removed = unsupported_pieces(answer, sources_text, question)
    if not removed:
        return answer, []
    drop = {piece for piece, _ in removed}
    lines, current = [], []
    for piece, ends_line in _pieces(answer):
        if piece not in drop:
            current.append(piece)
        if ends_line:
            lines.append(" ".join(part for part in current if part.strip()) if current else None)
            current = []
    kept = [line for line in lines if line is not None]
    text = "\n".join(kept)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # Un encabezado que quedó sin viñetas («Las especialidades son:») no es respuesta.
    text = re.sub(r"(?m)^[^\n]*:\s*$\n?(?=\s*$|\Z)", "", text).strip()
    return text, removed


def has_content(text, min_words=6):
    return len(re.findall(r"\w{3,}", re.sub(r"[*_#`•\-]+", " ", str(text or "")))) >= min_words

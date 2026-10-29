"""
Resumen extractivo legible para cuando el LLM no está disponible o no
responde a tiempo.

Los chunks llevan prefijos técnicos («Tablero: NEDOCS Columna calculada:
total Tabla: Descripción: … Expresión DAX: …»). Aquí se quitan esos rótulos,
se conservan las frases descriptivas y se arma una lista breve por fuente.
"""
import re
import unicodedata

from src.rag.source_labels import dictionary_board, dictionary_page_label


# Rótulos que abren el nombre del elemento documentado.
_ITEM_LABELS = (
    "Visualización documentada",
    "Medida Power BI",
    "Medida documentada",
    "Columna calculada",
    "Sección",
    "Filtro documentado",
    "Indicador documentado",
    "Indicador",
    "Filtro",
)

# Rótulos técnicos cuyo valor se descarta (hasta el siguiente rótulo).
_DROP_LABELS = (
    "Alias",
    "Tabla documentada",
    "Tabla",
    "Tipo de dato",
    "Formato",
    "Estado",
)

# A partir de aquí empieza código (DAX/SQL): se corta.
_CODE_MARKERS = (
    "Expresión DAX oficial del modelo:",
    "Expresión documentada:",
    "Expresión DAX:",
    "Consulta técnica documentada",
)

_TECHNICAL_TYPES = {"sql_query", "table_context"}

_LABEL_RE = re.compile(
    r"\b("
    + "|".join(re.escape(label) for label in _ITEM_LABELS + _DROP_LABELS + (
        "Tablero", "Descripción", "Contenido",
    ))
    + r"):"
)

MAX_ITEM_CHARS = 350


def _fields(text):
    """[(rótulo, valor)] en orden de aparición."""
    matches = list(_LABEL_RE.finditer(text))
    fields = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        fields.append((match.group(1), text[match.end():end].strip(" .;:-–")))
    return fields


# Fin de frase: punto/cierre seguido de espacio y comienzo de otra frase.
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[\"«(¿¡A-ZÁÉÍÓÚÑ0-9])")
HARD_ITEM_CHARS = 700
# Expresión DAX (empieza por una función o referencia: «DIVIDE(», «SUM(», «[M]», «'T'[C]»).
_DAX_LIKE_RE = re.compile(r"^(?:[A-Z][A-Z0-9.]*\s*\(|\[|'[^']+'\[|[A-Za-z_]\w*\[)")


def _drop_truncated_tail(text):
    """El texto del chunk puede venir cortado («…, el último…»): se quita la
    frase incompleta final si queda al menos una frase completa."""
    stripped = text.rstrip()
    if not stripped.endswith(("…", "...")):
        return stripped
    ends = [match.start() for match in _SENTENCE_END_RE.finditer(stripped)]
    return stripped[:ends[-1]].rstrip() if ends else stripped


def _shorten(text, limit=MAX_ITEM_CHARS):
    """Frases completas hasta `limit` caracteres (nunca corta a mitad de
    frase; la primera frase entra entera salvo que pase de HARD_ITEM_CHARS)."""
    text = _drop_truncated_tail(re.sub(r"\s+", " ", text or "").strip())
    if len(text) <= limit:
        return text
    sentences = _SENTENCE_END_RE.split(text)
    kept = []
    for sentence in sentences:
        if kept and len(" ".join([*kept, sentence])) > limit:
            break
        kept.append(sentence)
    result = " ".join(kept)
    if len(result) > HARD_ITEM_CHARS:
        cut = result[:HARD_ITEM_CHARS]
        cut = cut[:cut.rfind(" ")] if " " in cut else cut
        return cut.rstrip(" ,;:") + "…"
    return result


def readable_source(source):
    """(título, descripción) legibles de un chunk, o None si no aporta."""
    text = str(source.get("text") or "").strip()
    if not text:
        return None

    chunk_type = source.get("chunk_type") or ""
    if chunk_type in _TECHNICAL_TYPES:
        return None

    # Separar la parte descriptiva del código.
    description_code = ""
    for marker in _CODE_MARKERS:
        position = text.find(marker)
        if position >= 0:
            # La medida Power BI pone su descripción DESPUÉS de «Expresión
            # DAX oficial del modelo:» y antes de «Expresión documentada:».
            if marker == "Expresión DAX oficial del modelo:":
                rest = text[position + len(marker):]
                documented = rest.find("Expresión documentada:")
                description_code = rest[:documented] if documented >= 0 else rest
                text = text[:position]
                break
            if marker == "Expresión documentada:" and chunk_type == "documented_measure":
                # Medida documentada sin descripción: la expresión es lo único.
                expression = text[position + len(marker):]
                expression = expression.split("Estado:", 1)[0]
                description_code = "Expresión documentada: " + _shorten(expression, 200)
            text = text[:position]
            break

    page = None
    title = None
    descriptions = []

    for label, value in _fields(text):
        if not value:
            continue
        if label == "Tablero":
            page = dictionary_page_label(value)
        elif label in _ITEM_LABELS:
            title = title or value
        elif label in ("Descripción", "Contenido"):
            descriptions.append(value)

    code = description_code.strip(" .;:")
    if code:
        # Junto a una descripción, la expresión DAX va rotulada como fórmula.
        if descriptions and _DAX_LIKE_RE.match(code):
            code = "Fórmula: " + code
        descriptions.append(code)

    parts = [part for part in descriptions if part]
    description = " ".join(
        part if index == len(parts) - 1 or part.endswith((".", "…", "?", "!")) else part + "."
        for index, part in enumerate(parts)
    )

    # Visualización «Nombre: descripción» viene en el mismo campo.
    if title and not description and ": " in title:
        title, description = title.split(": ", 1)

    if not description:
        if chunk_type == "dashboard_overview" or not title:
            return None
        description = ""

    return (
        (title or page or "").strip(),
        _shorten(description),
    )


# Palabras sin contenido para medir la pertinencia de una entrada.
_STOPWORDS = {
    "que", "cual", "cuales", "como", "donde", "cuando", "quien", "para", "por", "con", "sin", "del",
    "las", "los", "una", "uno", "unos", "unas", "el", "la", "de", "en", "es", "son", "se", "su", "sus",
    "al", "lo", "le", "les", "me", "mi", "y", "o", "a", "hay", "tiene", "tienen", "dame", "dime",
    "lista", "listado", "muestra", "mostrar", "quiero", "saber", "significa", "calcula", "calculan",
    "hospital", "tablero", "tableros", "esta", "este", "estos", "estas", "ese", "esa", "sobre", "segun",
    "todos", "todas", "cada", "mas", "menos", "muy",
}
# Secciones que no explican nada al usuario.
_NOISE_TITLES = {"historial de cambios", "control de cambios", "versiones", "changelog"}
# «… Se usa en: PÁGINA › Visual; …»: lista de visuales, ruido en la respuesta.
_USAGE_RE = re.compile(r"\s*Se usa en:.*$", re.DOTALL)
# Descripción de diccionario que empieza por la entrada: «TABLA[COLUMNA]: …».
_ENTRY_PREFIX_RE = re.compile(r"^(?P<entry>[^:\n]{1,80}\[[^\]\n]{1,60}\]):\s*(?P<rest>.+)$", re.DOTALL)


def _plain(text):
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def _tokens(text):
    """Palabras con contenido (sin tildes, plurales simples reducidos)."""
    found = set()
    for word in re.findall(r"[a-z0-9]+", _plain(text)):
        if len(word) < 2 or word in _STOPWORDS:
            continue
        if len(word) > 4 and word.endswith("es"):
            word = word[:-2]
        elif len(word) > 3 and word.endswith("s"):
            word = word[:-1]
        found.add(word)
    return found


def _board_key(source):
    """Tablero (grupo/modelo) de la fuente: no se mezclan entradas de tableros distintos."""
    for key in ("source_group", "semantic_model"):
        if source.get(key):
            return _plain(source[key]).strip()
    return _plain(dictionary_board(source.get("dashboard"))).strip()


def _board_name(source):
    return str(source.get("semantic_model") or "").strip()


def _entry(source):
    """(título, descripción) de la fuente con la entrada del diccionario como
    título («MEDICAMENTOS DESABASTECIDOS[SERVICIO]» en vez de «Columnas clave»)."""
    item = readable_source(source)
    if item is None:
        return None
    title, description = item
    match = _ENTRY_PREFIX_RE.match(description or "")
    if match:
        title, description = match.group("entry").strip(), match.group("rest").strip()
    description = _USAGE_RE.sub("", description or "").strip(" .;")
    description = _shorten(description) if description else ""
    return title, description


def readable_fallback(sources, max_items=3, question=None):
    """Texto breve y legible con lo esencial de las fuentes, sin LLM.

    - Primero la entrada más pertinente (palabras de la pregunta en su título
      y descripción, luego el puntaje de recuperación).
    - Solo entradas del MISMO tablero que esa entrada (no se mezclan tableros
      sin relación).
    - Frases completas (nunca se corta a mitad de frase) y sin la lista
      «Se usa en: …» de visuales.
    - La fuente legible: diccionario o página entre paréntesis y el tablero al final.
    """
    question_tokens = _tokens(question)
    question_compact = re.sub(r"[^a-z0-9]+", "", _plain(question))
    items = []
    seen = set()
    for index, source in enumerate(sources or []):
        entry = _entry(source)
        if entry is None:
            continue
        title, description = entry
        if _plain(title).strip() in _NOISE_TITLES:
            continue
        key = (_plain(title).strip(), _plain(description).strip()[:120])
        if key in seen:
            continue
        seen.add(key)
        relevance = 0.0
        if question_tokens:
            title_hits = len(question_tokens & _tokens(title))
            text_hits = len(question_tokens & _tokens(description))
            relevance = 0.12 * title_hits + 0.04 * text_hits + float(source.get("score") or 0)
            # La entrada nombrada tal cual en la pregunta («turno ok» -> TURNO_OK).
            named = re.sub(r"[^a-z0-9]+", "", _plain(re.sub(r"^.*\[|\]$", "", title or "")))
            if len(named) >= 4 and named in question_compact:
                relevance += min(0.05 * len(named), 0.4)
        items.append({
            "index": index, "source": source, "title": title, "description": description,
            "relevance": relevance,
        })
    if not items:
        return None
    items.sort(key=lambda item: (-item["relevance"], item["index"]))
    primary = items[0]
    board = _board_key(primary["source"])
    chosen, titles = [], set()
    for item in items:
        if _board_key(item["source"]) != board:
            continue
        title_key = _plain(item["title"]).strip()
        if title_key and title_key in titles:
            continue  # la misma entrada dos veces (medida e indicador «Giro Cama»)
        titles.add(title_key)
        chosen.append(item)
        if len(chosen) >= max_items:
            break

    lines = []
    for item in chosen:
        source, title, description = item["source"], item["title"], item["description"]
        # «DICCIONARIO TABLERO X» -> «Diccionario de variables · TABLERO X».
        page = dictionary_page_label(source.get("dashboard")) or None
        prefix = title or page or "Documentación"
        if page and title and page.lower() not in title.lower() and page != _board_name(source):
            prefix = f"{title} ({page})"
        lines.append(f"{prefix}: {description}" if description else prefix)

    model = _board_name(primary["source"])
    footer = f"\n\nFuente: tablero {model}." if model and model.lower() not in lines[0].lower() else ""
    if len(lines) == 1:
        line = lines[0]
        return line + ("" if line.endswith((".", "…", "?", "!")) else ".") + footer
    return "Según la documentación de los tableros:\n" + "\n".join(f"- {line}" for line in lines) + footer

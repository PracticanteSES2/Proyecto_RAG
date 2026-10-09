"""
Resumen extractivo legible para cuando el LLM no está disponible o no
responde a tiempo.

Los chunks llevan prefijos técnicos («Tablero: NEDOCS Columna calculada:
total Tabla: Descripción: … Expresión DAX: …»). Aquí se quitan esos rótulos,
se conservan las frases descriptivas y se arma una lista breve por fuente.
"""
import re


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


def _shorten(text, limit=MAX_ITEM_CHARS):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Cortar en el último fin de frase si lo hay.
    period = cut.rfind(". ")
    if period > limit * 0.5:
        return cut[:period + 1]
    return cut.rstrip() + "…"


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
            page = value
        elif label in _ITEM_LABELS:
            title = title or value
        elif label in ("Descripción", "Contenido"):
            descriptions.append(value)

    if description_code.strip():
        descriptions.append(description_code.strip(" .;:"))

    description = " ".join(part for part in descriptions if part)

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


def readable_fallback(sources, max_items=5):
    """Texto breve y legible con lo esencial de cada fuente."""
    lines = []
    seen = set()

    for source in sources or []:
        item = readable_source(source)
        if item is None:
            continue
        title, description = item
        key = (title.lower(), description.lower())
        if key in seen:
            continue
        seen.add(key)

        page = source.get("dashboard")
        prefix = title or page or "Documentación"
        if page and title and page.lower() not in title.lower():
            prefix = f"{title} ({page})"

        lines.append(
            f"- {prefix}: {description}" if description else f"- {prefix}"
        )
        if len(lines) >= max_items:
            break

    if not lines:
        return None

    return (
        "Esto es lo que indica la documentación de los tableros:\n"
        + "\n".join(lines)
    )

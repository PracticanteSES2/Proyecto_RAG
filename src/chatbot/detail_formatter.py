"""
Redacción del «total + listado» (determinista, sin LLM).

«**6 camas disponibles** en HOSPITALIZACIÓN GENERAL (indicador CAMAS):» y una
tabla markdown con los nombres de negocio de las columnas (SERVICIO, CAMA),
ordenada como la devuelve la consulta, más las notas del listado (recortado,
demasiado largo, no se pudo traer, no coincide con el total, privacidad).
Lo usa ``format_query_plan_answer`` cuando el resultado trae ``detail``
(``QueryEngine._detail_listing``).
"""
import re
import unicodedata

from src.semantic.request_phrases import singular

# Palabras entre la entidad y su calificativo («camas QUE ESTÁN disponibles»).
_SKIP = {
    "hay", "estan", "esta", "quedan", "queda", "se", "encuentran", "encuentra", "siguen", "sigue",
    "permanecen", "tenemos", "tiene", "tienen", "que", "actualmente", "ahora", "hoy", "todavia",
    "aun", "son",
}
_STOP = {"en", "de", "del", "con", "por", "para", "segun", "a", "al", "y", "o"}
_LOCATION_WORDS = ("servicio", "servicios", "hsunombre", "unidad", "piso", "sede", "area", "ubicacion")


def _fold(text):
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _tokens(text):
    """[(original, normalizado)] de las palabras de un texto."""
    return [(word, re.sub(r"[^a-z0-9]", "", _fold(word))) for word in re.findall(r"[\wÁÉÍÓÚÑÜáéíóúñü-]+", str(text or ""))]


def _matches_value(token, value):
    forms = {token, singular(token)}
    for word in re.findall(r"[a-z0-9]+", _fold(value)):
        if forms & {word, singular(word)}:
            return True
        if len(token) >= 6 and len(word) >= 6 and token[:6] == word[:6]:
            return True
    return False


def _filter_values(item):
    values = item.get("values") if item.get("value") in (None, "") else [item.get("value")]
    return [str(v) for v in values or [] if v not in (None, "")]


def _is_location(item):
    text = _fold(" ".join(str(item.get(k) or "") for k in ("concept", "column")))
    return any(word in text for word in _LOCATION_WORDS)


def _number_value(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _agree(word, one):
    """«camas» -> «cama» y «disponibles» -> «disponible» cuando el total es 1."""
    if not one:
        return word
    folded = _fold(word)
    single = singular(folded)
    if single == folded:
        return word
    return word[: len(word) - (len(folded) - len(single))]


def detail_lead(result, value_text, scope_period=""):
    """Frase inicial «**6 camas disponibles** en HOSPITALIZACIÓN GENERAL
    (indicador CAMAS)» o None si no hay listado que encabezar."""
    detail = result.get("detail") or {}
    entity = detail.get("entity_word")
    question = (result.get("query_plan") or {}).get("question") or result.get("question") or ""
    if not entity or detail.get("status") not in ("ok", "too_long", "empty"):
        return None
    tokens = _tokens(question)
    position = next((i for i, (_, norm) in enumerate(tokens) if norm == entity), None)
    if position is None:
        return None
    one = _number_value(result.get("value")) == 1
    noun = _agree(tokens[position][0].lower(), one)
    filters = [
        item for item in result.get("filters") or (result.get("query_plan") or {}).get("filters") or []
        if item.get("type") == "categorical" and not item.get("temporal")
        and str(item.get("source") or "") != "query_plan_temporal"
    ]
    used, qualifiers = set(), []
    for original, norm in tokens[position + 1: position + 6]:
        if norm in _SKIP:
            continue
        if norm in _STOP or not norm:
            break
        match = next((i for i, item in enumerate(filters) if i not in used and any(
            _matches_value(norm, value) for value in _filter_values(item))), None)
        if match is None:
            break
        used.add(match)
        qualifiers.append(_agree(original.lower(), one))
    phrase = " ".join([value_text, noun, *qualifiers])
    rest = []
    for index, item in enumerate(filters):
        if index in used:
            continue
        values = _filter_values(item)
        if not values:
            continue
        joined = values[0] if len(values) == 1 else ", ".join(values[:-1]) + " o " + values[-1]
        if _is_location(item):
            rest.append(f"en {joined}")
        else:
            concept = str(item.get("concept") or item.get("column") or "").lower()
            rest.append(f"con {concept} {joined}".replace("  ", " "))
    if scope_period:
        rest.append(scope_period)
    label = result.get("metric") or ((result.get("query_plan") or {}).get("metric") or {}).get("label")
    lead = f"**{phrase}**" + (" " + ", ".join(rest) if rest else "")
    if label:
        lead += f" (indicador {label})"
    return lead + (":" if detail.get("status") == "ok" and detail.get("rows") else ".")


def _cell(value):
    if value is None or str(value).strip() == "":
        return "(sin dato)"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).replace("|", "\\|").replace("\n", " ")


def detail_table(detail):
    """Tabla markdown del listado (cabeceras de negocio) o ""."""
    rows = detail.get("rows") or []
    columns = detail.get("columns") or []
    if detail.get("status") != "ok" or not rows or not columns:
        return ""
    headers = [str(c.get("header") or c.get("column")) for c in columns]
    counts = detail.get("counts") or []
    if detail.get("show_counts"):
        headers.append("CANTIDAD")
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for index, row in enumerate(rows):
        cells = [_cell(value) for value in row]
        if detail.get("show_counts"):
            cells.append(_cell(counts[index] if index < len(counts) else None))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _count_text(value):
    number = _number_value(value)
    if number is None:
        return str(value)
    from src.chatbot.response_formatter import format_number_es

    return format_number_es(number)


def detail_notes(result):
    """Notas del listado (en español, sin términos internos)."""
    detail = result.get("detail") or {}
    status = detail.get("status")
    noun = detail.get("entity_word") or "registros"
    total = _count_text(result.get("value"))
    location = next((c.get("header") for c in detail.get("columns") or [] if c.get("role") == "location"), None)
    narrow = f"un {str(location).lower()}" if location else "un filtro (servicio, estado...)"
    label = result.get("metric") or "este indicador"
    notes = []
    if status == "ok" and detail.get("truncated"):
        notes.append(
            f"Muestro las primeras {len(detail.get('rows') or [])} filas de {total} {noun}: la lista es "
            f"más larga. Indica {narrow} para acotarla."
        )
    elif status == "too_long":
        notes.append(
            f"La lista de {total} {noun} es demasiado larga para mostrarla aquí (más de "
            f"{detail.get('cap')}). Indica {narrow} y te muestro el detalle."
        )
    elif status == "error":
        notes.append(f"No pude traer la lista de detalle ({detail.get('error')}); el total sí es el de Power BI.")
    elif status == "inconsistent":
        notes.append(
            f"No muestro la lista: {label} da el mismo valor en cada fila, así que la lista no "
            "coincidiría con el total."
        )
    elif status == "not_listable":
        notes.append(f"{label} no cuenta registros identificables, así que no puedo listar el detalle; "
                     "te doy el total.")
    if status == "ok" and detail.get("consistency") == "mismatch":
        listed = sum(c for c in detail.get("counts") or [] if c is not None)
        notes.append(
            f"Ojo: las filas de la lista suman {_count_text(listed)} y {label} da {total}; el indicador "
            "aplica reglas propias de conteo."
        )
    if status == "ok" and detail.get("excluded_private"):
        notes.append(
            "Por privacidad, la lista no incluye datos que identifican a personas ("
            + ", ".join(detail["excluded_private"]) + ")."
        )
    return notes

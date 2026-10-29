"""
Diccionario de variables en el RAG: cómo reconocer sus chunks y cómo nombrar
una fuente para el usuario.

El diccionario (`docs_tableros/<grupo>/md/_diccionario*.md`) entra al índice
como un «tablero» llamado «DICCIONARIO <TABLERO>» (o «DICCIONARIO <TEMA>
<TABLERO>»). Los índices nuevos llevan además `is_dictionary: True` en el
payload; los anteriores solo se reconocen por el nombre.

Lógica pura (sin Qdrant ni modelos): la usan el retriever, el resolvedor de
métricas y la capa de presentación del chatbot.
"""
import re
import unicodedata

DICTIONARY_PREFIX = "DICCIONARIO"
DICTIONARY_LABEL = "Diccionario de variables"

# Sección del chunk (metadato `section` de chunk_builder) -> sección del .md.
DICTIONARY_SECTION_LABELS = {
    "measures": "Medidas",
    "calculated_columns": "Columnas calculadas",
    "data_sources": "Tablas",
    "tables": "Tablas",
    "notes": "Observaciones",
    "overview": "Resumen",
}

# Rótulo del chunk que antecede al nombre de la entrada (ver chunk_builder).
_ENTRY_RE = re.compile(
    r"(?:Fuente de datos|Nota u observación|Contenido|Definición|Regla de negocio)"
    r":\s*(?P<nombre>[^:\n]{1,120}?):\s"
)
MAX_ENTRY_CHARS = 80


def _plain(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().upper()


def is_dictionary_name(name):
    """«DICCIONARIO …» (sin distinguir tildes ni mayúsculas)."""
    plain = _plain(name)
    return plain == DICTIONARY_PREFIX or plain.startswith(DICTIONARY_PREFIX + " ")


def is_dictionary_source(source):
    """El resultado/payload es un chunk del diccionario de variables."""
    if not isinstance(source, dict):
        return False
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    flag = source.get("is_dictionary")
    if flag is None:
        flag = metadata.get("is_dictionary")
    if flag:
        return True
    return is_dictionary_name(source.get("dashboard") or metadata.get("dashboard"))


def dictionary_board(name):
    """«DICCIONARIO TABLERO CVC» -> «TABLERO CVC» (el resto del nombre)."""
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    if not is_dictionary_name(text):
        return text
    return text[len(DICTIONARY_PREFIX):].strip()


def entry_name(source):
    """Nombre de la entrada del diccionario: [Medida], TABLA[COLUMNA] o el
    nombre que encabeza el texto («EN_ESPERA[TramoHorario]: …»)."""
    measure = str(source.get("measure") or "").strip()
    chunk_type = source.get("chunk_type") or ""
    if measure and chunk_type in ("measure", "documented_measure"):
        return f"[{measure}]"
    column = str(source.get("column") or "").strip()
    table = str(source.get("table") or "").strip()
    if column and chunk_type == "calculated_column":
        return f"{table}[{column}]" if table else column
    text = str(source.get("text") or "")
    if chunk_type == "calculated_column":
        match = re.search(r"Columna calculada:\s*(?P<c>.+?)\s+Tabla:\s*(?P<t>.*?)\s+Descripción:", text)
        if match:
            column, table = match.group("c").strip(), match.group("t").strip()
            return f"{table}[{column}]" if table else column
    match = _ENTRY_RE.search(text)
    if match:
        name = match.group("nombre").strip()
        if name and len(name) <= MAX_ENTRY_CHARS:
            return name
    return ""


def entry_identifier(source):
    """Identificador que define el chunk, sin tabla: «TURNO_OK» para
    [TURNO_OK] o LAVANDERIA[TURNO_OK]; «» para relaciones o sin nombre."""
    name = entry_name(source)
    if not name or "→" in name:
        return ""
    match = re.fullmatch(r"(?:[^\[\]]*)\[(?P<id>[^\[\]]+)\]", name)
    return (match.group("id") if match else name).strip()


def dictionary_section(source):
    section = str(source.get("section") or "").strip()
    return DICTIONARY_SECTION_LABELS.get(section, section)


def source_label(source):
    """Nombre legible de una fuente para el usuario.

    Diccionario: «Diccionario de variables · TABLERO X › Medidas › [M]».
    Resto: el nombre de la página tal cual (formato de siempre).
    """
    if not isinstance(source, dict):
        return ""
    dashboard = str(source.get("dashboard") or "").strip()
    if not is_dictionary_source(source):
        return dashboard
    board = dictionary_board(dashboard)
    head = f"{DICTIONARY_LABEL} · {board}" if board else DICTIONARY_LABEL
    parts = [head]
    section = dictionary_section(source)
    if section and section != "Resumen":
        parts.append(section)
    entry = entry_name(source)
    if entry:
        parts.append(entry)
    return " › ".join(parts)


def dictionary_page_label(dashboard):
    """«DICCIONARIO TABLERO X» -> «Diccionario de variables · TABLERO X»;
    otros nombres, sin cambios."""
    if not is_dictionary_name(dashboard):
        return str(dashboard or "")
    board = dictionary_board(dashboard)
    return f"{DICTIONARY_LABEL} · {board}" if board else DICTIONARY_LABEL

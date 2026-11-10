"""
Términos de negocio para redactar respuestas (sin LLM).

Lee el diccionario de cada tablero (`docs_tableros/<grupo>/md/_diccionario*.md`,
entradas «- **CLAVE**: descripción») para:

- `metric_unit(metric)`: la unidad de un indicador («minutos», «días»,
  «camas»...). Sale del «Unidad: ...» de la medida o de la columna que el
  visual promedia/suma, o de una descripción de columna que empieza por
  «Minutos/Horas/Días entre...». Sin evidencia devuelve None: nunca se inventa.
- `column_business_name(...)`: el nombre de negocio de una columna
  («servicio» para HSUNOMBRE) a partir de las descripciones cortas.
- `board_filters_sentence(metric)`: la frase corta que reemplaza la nota
  técnica «Filtros del tablero aplicados (...): HSUNOMBRE no es ...».
"""
import re
from functools import lru_cache
from pathlib import Path

from src.comun.rutas import RAIZ_PROYECTO
from src.comun.texto import normalizar

_ENTRY_RE = re.compile(r"^- \*\*(?P<key>[^*]+)\*\*:\s*(?P<desc>.*)$")
_FRONT_RE = re.compile(r"^tablero:\s*(?P<name>.+?)\s*$", re.MULTILINE)
_UNIT_RE = re.compile(r"Unidad:\s*(?P<unit>[^.;(]+)")
_LEADING_TIME_RE = re.compile(r"^(?P<unit>minutos|horas|d[ií]as)\s+(?:entre|desde|de|que|transcurrid)", re.IGNORECASE)
_AGGREGATIONS_WITH_UNIT = {"average", "avg", "sum", "min", "max", "median"}
# Unidades que no se añaden a la cifra: el % ya lo pone el formato y las
# demás no son cantidades.
_NOT_APPENDED = ("porcentaje", "proporcion", "%", "fecha", "texto", "1 o 0", "puntos", "codigo", "html")
TIME_UNITS = {"minutos", "horas", "dias"}
_NAME_PREFIX_RE = re.compile(
    r"^(?:nombre|descripci[oó]n|c[oó]digo|identificador|marca|indicador)\s+(?:de la|de los|de las|del|de)\s+",
    re.IGNORECASE,
)


def fold(text):
    return normalizar(text, "%")


def _docs_root():
    try:
        from src.docs_md.repositorio import raiz_documentos

        return Path(raiz_documentos())
    except Exception:
        return RAIZ_PROYECTO / "docs_tableros"


@lru_cache(maxsize=4)
def _load(root):
    """{nombre plegado del tablero o carpeta: {CLAVE: descripción}}."""
    index = {}
    root = Path(root)
    if not root.is_dir():
        return index
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        md = folder / "md"
        files = sorted(md.glob("_diccionario*.md")) if md.is_dir() else []
        if not files:
            continue
        entries, names = {}, {fold(folder.name), fold(folder.name.replace("tablero_", "", 1))}
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            match = _FRONT_RE.search(text[:2000])
            if match:
                names.add(fold(match.group("name")))
                names.add(fold(re.sub(r"(?i)^tablero\s+", "", match.group("name"))))
            for line in text.splitlines():
                entry = _ENTRY_RE.match(line.strip())
                if entry:
                    entries.setdefault(entry.group("key").strip(), entry.group("desc").strip())
        for name in names:
            if name:
                index.setdefault(name, entries)
    return index


def dictionary_for(metric, root=None):
    """Entradas del diccionario del tablero del indicador ({} si no hay)."""
    index = _load(str(root or _docs_root()))
    metric = metric or {}
    source = metric.get("board_filters_source") or {}
    candidates = [metric.get("source_group"), *(metric.get("source_groups") or []), metric.get("report"),
                  source.get("report"), *(metric.get("reports") or []), metric.get("semantic_model")]
    for candidate in candidates:
        for key in (fold(candidate), fold(re.sub(r"(?i)^tablero[\s_]+", "", str(candidate or "")))):
            if key and key in index:
                return index[key]
    return {}


def _lookup(entries, key):
    if key in entries:
        return entries[key]
    folded = fold(key)
    for name, desc in entries.items():
        if fold(name) == folded:
            return desc
    return None


def _clean_unit(raw):
    unit = re.split(r"[(;,]|\s+Tabla:", str(raw or ""))[0].strip().rstrip(".").strip()
    words = unit.split()
    if not words or len(words) > 3 or re.search(r"\d", unit):
        return None
    if any(bad in fold(unit) for bad in _NOT_APPENDED):
        return None
    return unit.lower()


def metric_unit(metric, root=None):
    """Unidad del indicador según el diccionario, o None si no hay evidencia."""
    metric = metric or {}
    entries = dictionary_for(metric, root)
    if not entries:
        return None
    measure = metric.get("measure")
    if measure and str(measure) != "None":
        desc = _lookup(entries, f"[{measure}]")
        found = _UNIT_RE.search(desc or "")
        return _clean_unit(found.group("unit")) if found else None
    aggregation = fold(metric.get("aggregation"))
    table, column = metric.get("table"), metric.get("column")
    if aggregation not in _AGGREGATIONS_WITH_UNIT or not table or not column:
        return None
    desc = _lookup(entries, f"{table}[{column}]")
    if not desc:
        return None
    found = _UNIT_RE.search(desc)
    if found:
        return _clean_unit(found.group("unit"))
    leading = _LEADING_TIME_RE.match(desc)
    return leading.group("unit").lower() if leading else None


def unit_word(unit, value):
    """«días» -> «día» cuando la cifra es 1."""
    if not unit:
        return unit
    try:
        one = abs(float(value)) == 1
    except (TypeError, ValueError):
        one = False
    if not one or " " in unit:
        return unit
    from src.semantic.request_phrases import singular

    return singular(unit) or unit


def column_business_name(entries, table, column):
    """Nombre de negocio corto de una columna («servicio» para HSUNOMBRE) o
    None. Prefiere la entrada de la misma tabla; si su descripción no da un
    nombre corto, usa la más corta de la misma columna en otras tablas."""
    if not entries or not column:
        return None
    own = _lookup(entries, f"{table}[{column}]") if table else None
    own_name = _short_name(own)
    if own_name:
        return own_name
    names = [
        name for key, desc in entries.items()
        if key.endswith(f"[{column}]") and "→" not in key
        for name in [_short_name(desc)] if name
    ]
    return min(names, key=len) if names else None


def _short_name(desc):
    first = re.split(r"[.;:,(]", str(desc or ""), maxsplit=1)[0].strip()
    first = _NAME_PREFIX_RE.sub("", first).strip()
    if not first or "[" in first or re.search(r"\d", first) or len(first.split()) > 4:
        return None
    if first.isupper():
        return None  # otro nombre técnico, no una descripción
    return first[0].lower() + first[1:]


# ---------------- nota de filtros del tablero ----------------
_CARD_TYPES = {"card", "cardvisual", "multirowcard", "kpi", "gauge"}
_TABLE_TYPES = {"tableex", "table", "pivottable", "matrix"}


def visual_kind(visual_type):
    kind = fold(visual_type).replace(" ", "")
    if kind in _CARD_TYPES:
        return "tarjeta"
    if kind in _TABLE_TYPES:
        return "tabla"
    if "chart" in kind or "map" in kind or kind in ("donut", "pie", "funnel", "treemap", "waterfall", "scatter"):
        return "gráfico"
    return "visual"


def board_phrase(report):
    """«del tablero BRIEFING HOSPITALARIO» / «del TABLERO EPS»."""
    report = str(report or "").strip()
    if not report:
        return ""
    return f"del {report}" if fold(report).startswith("tablero") else f"del tablero {report}"


def _blank(value):
    return value is None or str(value).strip() == ""


def _values(values, limit=2):
    shown = [str(v).strip() for v in values if not _blank(v)]
    text = ", ".join(shown[:limit])
    if len(shown) > limit:
        text += f" y {len(shown) - limit} más"
    return text


def _is_code(value):
    return bool(re.fullmatch(r"-?\d+(?:[.,]\d+)?", str(value).strip()))


def _filter_phrase(condition, name):
    """Frase de negocio de un filtro, o None si es demasiado técnico (códigos
    numéricos, «contiene», comparaciones): ese detalle queda en el razonamiento."""
    if not name or not isinstance(condition, dict):
        return None
    negated = condition.get("op") == "not" and isinstance(condition.get("arg"), dict)
    inner = condition["arg"] if negated else condition
    if inner.get("op") == "in":
        values = [v for v in inner.get("values") or [] if not _blank(v)]
        if not values:
            return f"con {name}" if negated else f"sin {name}"
        if all(_is_code(v) for v in values):
            return None
        return f"{'excluye' if negated else 'solo'} {name} {_values(values)}"
    if inner.get("op") == "cmp" and inner.get("value") is None and inner.get("cmp") in ("=", "<>"):
        blank = (inner.get("cmp") == "=") != negated
        return f"sin {name}" if blank else f"con {name}"
    return None


def board_filters_sentence(metric, root=None, max_shown=1):
    """«Cifra tal como la muestra la tarjeta de la página GESTIÓN CAMAS del
    tablero BRIEFING HOSPITALARIO (con 5 filtros de esa página; p. ej.,
    excluye servicio ATENCION DOMICILIARIA, BLOQUEAR y 19 más).» o None."""
    metric = metric or {}
    filters = metric.get("visual_filters") or []
    if not filters:
        return None
    source = metric.get("board_filters_source") or {}
    entries = dictionary_for(metric, root)
    where = "Cifra tal como la muestra el tablero"
    if source.get("page"):
        kind = visual_kind(source.get("visual_type"))
        article = "la" if kind in ("tarjeta", "tabla") else "el"
        where = f"Cifra tal como la muestra {article} {kind} de la página {source['page']}"
        report = source.get("report") or metric.get("report")
        if report:
            where += " " + board_phrase(report)
    phrases = []
    for item in filters:
        name = column_business_name(entries, item.get("table"), item.get("column"))
        phrase = _filter_phrase(item.get("condition"), name)
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    count = len(filters)
    noun = "filtro" if count == 1 else f"{count} filtros"
    if count == 1:
        detail = f"con su filtro: {phrases[0]}" if phrases else "con su filtro"
    elif phrases:
        detail = f"con sus {noun}; p. ej., " + "; ".join(phrases[:max_shown])
    else:
        detail = f"con sus {noun}"
    return f"{where} ({detail})."


def replaced_filter_sentence(metric, dropped_columns, root=None):
    """«Para el servicio se usa lo que pediste en lugar del filtro de la página.»"""
    entries = dictionary_for(metric, root)
    names = []
    for column in dropped_columns:
        name = column_business_name(entries, None, column) or str(column).strip().lower()
        if name and name not in names:
            names.append(name)
    if not names:
        return None
    joined = " y ".join(names)
    return f"Para {joined} se usa lo que pediste en lugar del filtro que trae la página."

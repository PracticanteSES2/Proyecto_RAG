"""
Forma de la respuesta que pide una pregunta numérica (reglas, sin LLM).

Los usuarios del hospital (2026-10-14): «El RAG debería saber cuándo es una
lista y cuándo no… al decir que filtre por algo, que traiga la filtración y la
lista con detalles de ese filtro». Tres formas:

- ``scalar`` (por defecto): un valor («¿cuántos egresos hubo en 2025?»).
- ``grouped``: «por X», «por cada X», «distribución», «desglose»... (lo
  resuelve el Query Plan con su agrupación; «detalle de M por X» también es una
  agrupación, no un listado).
- ``detail`` («total + listado»): el total y la lista de las entidades que
  cuenta el indicador, con columnas de detalle (cama, servicio...):

  - fuerza ``explicit`` (la lista se muestra siempre, cortada al tope):
    «cuáles», «cuáles son las <entidad>», «qué <entidad> (hay|están|quedan)…»,
    «lista/listado de <entidad>», «lístame…», «detalle de las <entidad>» y el
    total con la lista al final («cuántas <entidad> … y cuáles son», «… y en
    qué camas»);
  - fuerza ``soft`` (la lista solo si el total filtrado es corto):
    «muéstrame las <entidad>», «cuántas/cuántos <entidad> hay|están|quedan…»
    (estado actual, sin periodo). Con un total mayor que el tope se da el total
    y se ofrece filtrar.

  Que el indicador cuente entidades identificables (COUNT/DISTINCTCOUNT de una
  columna tipo código: 'CAMAS DISPONIBLES'[HCACODIGO]) lo decide
  ``src/semantic/detail_list.py`` con el plan ya armado; aquí solo se lee la
  pregunta.
"""
import re

from src.semantic.question_kind import descriptive_phrase, normalize_question

# Palabras de la petición de lista: no son filtros ni el indicador (el Query
# Plan las agrega a sus palabras vacías para no declararlas «No pude aplicar»).
DETAIL_REQUEST_WORDS = {
    "lista", "listado", "listar", "listame", "listarme", "listalas", "listalos",
    "enumera", "enumerame", "enumerar", "detallame", "detalla", "detallar",
    "estan", "quedan", "encuentran", "siguen", "permanecen", "cuales", "todas", "todos",
    "muestrame", "mostrarme", "ensename", "ver",
}

_FILLER = (
    r"(?:(?:y|oye|hola|bueno|entonces|disculpa|perdon|por\s+favor|porfa|dime|me\s+puedes\s+decir"
    r"|me\s+podrias\s+decir|me\s+dices|quisiera\s+saber|quiero\s+saber|necesito\s+saber"
    r"|necesito|quiero|quisiera|podrias\s+decirme|puedes\s+decirme|me\s+das|dame)\s+)*"
)
# Verbos de estado actual: «qué camas HAY/ESTÁN/QUEDAN disponibles».
_STATE_VERBS = (
    r"(?:hay|estan|esta|quedan|queda|se\s+encuentran|se\s+encuentra|siguen|sigue|permanecen"
    r"|tenemos|tiene|tienen)"
)
# Palabras que nunca son la entidad de una lista («cuáles son los…» la toma
# después del artículo; «qué es…» es descriptiva).
_NOT_ENTITY = {
    "es", "son", "fue", "fueron", "era", "eran", "sera", "seran", "seria", "serian", "hay",
    "ha", "han", "de", "del", "el", "la", "los", "las", "un", "una", "tal", "tan", "tanto",
    "tanta", "tantos", "tantas", "porcentaje", "promedio", "valor", "total", "cantidad",
    "numero", "tasa", "indice", "proporcion", "media", "dia", "mes", "ano", "fecha", "hora",
    "significa", "significan", "mide", "miden", "indica", "indican", "filtros", "filtro",
    "informacion", "indicadores", "indicador", "graficos", "visuales", "paginas", "pagina",
    "tablero", "tableros", "informe", "reporte", "tiempo", "tipo",
}
_ARTICLE = r"(?:(?:todas\s+|todos\s+)?(?:las|los|sus)\s+)?"
_ENTITY = r"(?P<entity>[a-z][a-z0-9]{2,})"
# «qué camas…», «cuáles camas…»: la entidad en plural («qué servicio tiene
# más egresos» es un ranking, no una lista).
_ENTITY_PLURAL = r"(?P<entity>[a-z][a-z0-9]{2,}s)"

_EXPLICIT_PATTERNS = (
    # «lista de camas bloqueadas», «listado de las camas», «lístame las camas»
    ("lista", re.compile(
        r"(?<![a-z0-9])(?:una\s+|la\s+|el\s+)?(?:lista|listado|relacion\s+detallada)\s+(?:de|con)\s+"
        + _ARTICLE + _ENTITY)),
    ("listar", re.compile(
        r"(?<![a-z0-9])(?:listar|listame|listarme|enumera|enumerame|enumerar|detallame)\s+"
        + _ARTICLE + _ENTITY)),
    # «detalle de las camas bloqueadas» (sin «por X»: eso es una agrupación)
    ("detalle", re.compile(
        r"(?<![a-z0-9])(?:el\s+)?detalle\s+de\s+(?:(?:las|los)\s+" + _ENTITY
        + r"|(?P<plural>[a-z][a-z0-9]{2,}s)(?![a-z0-9]))")),
    # «cuáles son las camas disponibles», «cuáles camas están bloqueadas»
    ("cuales", re.compile(
        r"(?<![a-z0-9])cuales\s+(?:son|eran|serian|estan|quedan|hay\s+de)\s+(?:las|los)\s+" + _ENTITY)),
    ("cuales", re.compile(
        r"(?<![a-z0-9])cuales\s+" + _ENTITY_PLURAL + r"\s+" + _STATE_VERBS + r"(?![a-z0-9])")),
    # «qué camas están disponibles en UCI», «qué pacientes hay en UCI»
    ("que", re.compile(
        r"^" + _FILLER + r"(?:en\s+\w+\s+)?que\s+" + _ENTITY_PLURAL + r"\s+" + _STATE_VERBS
        + r"(?![a-z0-9])")),
)
_SOFT_PATTERNS = (
    # «muéstrame las camas disponibles», «enséñame los pacientes de UCI»
    ("muestrame", re.compile(
        r"(?<![a-z0-9])(?:muestrame|mostrarme|ensename|quiero\s+ver|ver)\s+(?:todas\s+|todos\s+)?"
        r"(?:las|los)\s+" + _ENTITY)),
    # «cuántas camas hay disponibles», «cuántas camas bloqueadas hay»: el
    # verbo puede ir antes o después del calificativo (máximo 3 palabras).
    ("cuantas", re.compile(
        r"(?<![a-z0-9])cuant[oa]s\s+" + _ENTITY + r"(?:\s+[a-z0-9]+){0,3}?\s+" + _STATE_VERBS
        + r"(?![a-z0-9])")),
)
_TRAILING_RE = re.compile(
    r"(?<![a-z0-9])y\s+(?:en\s+|de\s+|a\s+)?(?:cuales|que|donde)(?:\s+[a-z0-9]+){0,2}\s*$"
)
_COUNTED_RE = re.compile(r"(?<![a-z0-9])cuant[oa]s\s+" + _ENTITY)
# Agrupaciones: «por X», «por cada X», «de cada X», «distribución», «desglose»,
# «según X». Con ellas la forma es grouped (la decide el Query Plan).
_GROUPING_RE = re.compile(
    r"(?<![a-z0-9])(?:por\s+(?:cada\s+)?(?!favor\b|ciento\b|que\b|ejemplo\b)[a-z]{3,}|de\s+cada"
    r"|cada\s+un[oa]"
    r"|distribucion|distribuid[oa]s?|desglose|desglosad[oa]s?|desglosa\w*|segun\s+[a-z]{3,}"
    r"|discriminad[oa]s?|agrupad[oa]s?)(?![a-z0-9])"
)
# Periodo pasado: «cuántas cirugías hubo en 2024» es un total del periodo, no
# un estado actual con lista.
_PAST_RE = re.compile(
    r"(?<![a-z0-9])(?:hubo|fueron|tuvo|tuvieron|habia|habian|20\d\d|enero|febrero|marzo|abril|mayo"
    r"|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|ayer|pasad[oa]|anterior"
    r"|ultim[oa]s?|semana|mes|ano|trimestre|semestre)(?![a-z0-9])"
)


# Ranking («qué servicios tienen más egresos», «top 5»): orden y límite, no lista.
_RANKING_RE = re.compile(
    r"(?<![a-z0-9])(?:mas|menos|mayor|mayores|menor|menores|top|primer[oa]s?|maximo|minimo)(?![a-z0-9])"
)


def _entity(match):
    entity = match.groupdict().get("entity") or match.groupdict().get("plural")
    return entity if entity and entity not in _NOT_ENTITY else None


def grouping_requested(question):
    """¿La pregunta pide una agrupación («por X», «desglose», «distribución»)?"""
    return bool(_GROUPING_RE.search(normalize_question(question)))


def detail_request(question):
    """Petición de lista de detalle en la pregunta, o None.

    {"strength": "explicit"|"soft", "cue": «lista»/«que»/«cuantas»...,
     "phrase": texto normalizado que coincidió, "entity": «camas»}.
    Una agrupación («por servicio», «detalle de M por X») no es un listado.
    """
    text = normalize_question(question)
    if not text or grouping_requested(text) or _RANKING_RE.search(text) or descriptive_phrase(text):
        return None
    words = text.split()
    # Total y lista en la misma pregunta: «cuántas camas ocupadas hay en uci y
    # cuáles son», «cuántos pacientes de sanitas están hospitalizados y en qué
    # camas»: la entidad es la contada («camas», «pacientes»).
    trailing = _TRAILING_RE.search(text)
    counted = _COUNTED_RE.search(text)
    if trailing and counted and _entity(counted):
        return {"strength": "explicit", "cue": "y cuales", "phrase": trailing.group(0).strip(),
                "entity": _entity(counted), "question_words": words}
    for strength, patterns in (("explicit", _EXPLICIT_PATTERNS), ("soft", _SOFT_PATTERNS)):
        for cue, pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            entity = _entity(match)
            if not entity:
                continue
            if cue == "cuantas" and _PAST_RE.search(text):
                return None
            return {"strength": strength, "cue": cue, "phrase": match.group(0).strip(), "entity": entity,
                    "question_words": words}
    return None


def answer_shape(question):
    """«grouped» | «detail» | «scalar» según la pregunta (sin mirar el catálogo)."""
    if grouping_requested(question):
        return "grouped"
    return "detail" if detail_request(question) else "scalar"

"""Texto y tokens del motor de resolución (etapa 1: normalizar la pregunta).

Funciones de módulo que antes vivían al principio de query_plan_builder.py: normalización
(normalize_text, canonical_token/s, canonical_phrases), similitud de palabras (_token_similarity,
_tokens_match_loosely, _alias_prefix), palabras de petición y de forma de pregunta, análisis de
dominios de valores (value_contradiction) y puntaje de frases (_phrase_score). query_plan_builder
las reexporta con los mismos nombres.
"""
import re
import threading
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from src.semantic import plan_budget
from src.semantic.answer_shape import DETAIL_REQUEST_WORDS

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

GENERIC_QUERY_WORDS = {
    "cuanto", "cuantos", "cuantas", "cual", "cuales", "es", "son",
    "hay", "hubo", "tiene", "tienen", "valor", "cantidad",
    "dame", "muestra", "mostrar", "del", "de", "la", "el",
    "los", "las", "un", "una", "en", "al", "para", "por",
    "corresponden", "correspondiente", "correspondientes", "tablero",
    "informe", "institucionales",
}

# Palabras discriminativas para elegir métrica (p. ej. «Total Cirugías»
# frente a «Cirugías»), pero sin valor como filtro: no deben quedar como
# «término sin aplicar» ni intentar resolverse como valor de dimensión.
FILTER_NEUTRAL_WORDS = {"total", "numero"}

# Relleno conversacional que nunca explica ni agrega significado.
STOPWORDS = {
    "a", "al", "con", "sin", "que", "y", "o", "u", "e", "me", "mi", "se",
    "su", "sus", "lo", "le", "les", "fue", "fueron", "ser", "sido", "esta",
    "este", "estos", "estas", "ese", "esa", "hay", "hubo", "han", "ha",
    "dentro", "segun", "mes", "ano", "anio", "durante", "favor", "por",
    "dime", "dame", "quiero", "saber", "cuanto", "cuantos", "cuanta",
    "cuantas", "cual", "cuales", "como", "donde", "cuando", "tuvo",
    "tuvieron", "tiene", "tienen", "son", "es", "del", "de", "la", "el",
    "los", "las", "un", "una", "unos", "unas", "en", "para", "muestra",
    "mostrar", "valor", "cantidad", "informe", "tablero", "modelo",
    "semantico", "dashboard", "reporte", "pagina", "hacer", "ver",
}
# Forma de pedir el dato («necesito saber», «me podrías indicar»): no es
# filtro ni métrica. _is_request_word tolera además un error de tipeo.
REQUEST_WORDS = {
    "necesito", "necesitamos", "necesitaria", "necesitaba", "requiero",
    "quisiera", "queria", "quisieramos", "gustaria", "conocer", "consultar",
    "obtener", "informacion", "info", "porfa", "porfavor", "puedes", "puede",
    "podrias", "podria", "pueden", "ayudame", "indicame",
    "indiqueme", "dimelo", "muestrame", "mostrarme", "regalame", "dar",
    "darme", "decir", "decirme", "hola", "gracias", "nos", "dato", "datos",
    "cifra", "cifras",
    # Imperativos de petición («identifica la cantidad de...», «calcula...»).
    "identifica", "identificame", "identificar", "indica", "indicar", "calcula", "calculame",
    "calcular", "revisa", "revisame", "busca", "buscame", "trae", "traeme", "averigua",
    "averiguame", "determina", "determinar", "senala", "senalame", "reporta", "reportame",
    "informame", "entregame", "genera", "generame",
    # «compara X de agosto contra el mes pasado»: el periodo ya dice qué se compara.
    "compara", "comparame", "comparar", "comparemos", "contrasta",
}
STOPWORDS |= REQUEST_WORDS

# Verbos, auxiliares y adverbios corrientes de la pregunta («hay registrado»,
# «lleva», «tuvimos», «se hicieron», «más»): nunca son un filtro ni un valor
# de dimensión, así que no deben quedar como «palabras sin interpretar».
COMMON_VERB_WORDS = {
    "registrado", "registrados", "registrada", "registradas", "registraron",
    "registramos", "lleva", "llevan", "llevamos", "llevaba", "llevaban",
    "llevado", "tuvimos", "tenemos", "tenia", "tenian", "habia", "habian",
    "habido", "hicieron", "hizo", "hecho", "hechos", "hecha", "hechas",
    "hacen", "hace", "va", "van", "vamos", "iba", "iban", "mas", "menos",
    "aproximadamente", "exactamente", "alrededor", "solo", "solamente",
    "top", "ranking", "estan", "estaba", "estaban", "estuvo", "estuvieron", "existen",
}
STOPWORDS |= COMMON_VERB_WORDS

# Forma de la pregunta que NUNCA es un valor de filtro: adverbios de «ahora»
# («en este momento», «ahorita») y verbos de duración («cuánto duran / se
# demoran / tardan»). No se suman a STOPWORDS (no cambian la elección del
# indicador): solo se ignoran al buscar valores y palabras sin interpretar.
QUESTION_FORM_WORDS = {
    "momento", "ahora", "ahorita", "actualmente", "instante",
    "dura", "duran", "duro", "duraron", "durado", "durando",
    "demora", "demoran", "demoro", "demoraron", "demorado", "demorando", "demoras",
    "tarda", "tardan", "tardo", "tardaron", "tardado", "tardando",
    # Verbos de movimiento o estado de uso común en preguntas («cuánto tiempo
    # PASA un paciente», «hasta que lo SUBEN», «cuántas LLEGAN»).
    # Sin homónimos que puedan ser valores («baja complejidad», «toma de
    # muestras», «uso»).
    "pasa", "pasan", "pasaron", "queda", "quedan", "quedo", "lleva", "llevan",
    "llega", "llegan", "llego", "sube", "suben", "subio", "bajan",
    "sale", "salen", "salio", "entran", "toman", "tomo",
    "usan", "usando", "pudimos", "pudieron", "pudo", "tenemos", "tienen",
    "reportado", "reportados", "reportada", "reportadas", "registrado", "registrados",
    "registrada", "registradas", "muestran",
    # Marcadores de exclusión («sin contar X», «excepto X»): el valor se excluye (r9).
    "contar", "incluir", "excepto", "exceptuando", "salvo", "excluyendo", "descontando", "excepcion",
}
_QUESTION_FORM_TOKENS = set(QUESTION_FORM_WORDS)   # ya sin tildes ni mayúsculas
# Cola de «por <dimensión> ...» que no nombra un valor («en total», «en general»).
_GROUP_NEUTRAL_TAIL_WORDS = {
    "total", "totales", "general", "global", "todo", "todos", "toda", "todas",
    "en", "de", "el", "la", "los", "las", "y", "por", "favor",
}


def _is_question_form_word(word):
    """Adverbio de tiempo presente, verbo de duración o pretérito plural
    («tomaron», «lavaron», «atendieron»): forma de la pregunta, nunca un
    valor de dimensión."""
    word = normalize_text(word)
    if word in _QUESTION_FORM_TOKENS:
        return True
    return len(word) >= 7 and word.endswith(("aron", "ieron"))


# Forma de pedir una lista («lista de», «qué camas están…»): no es filtro.
STOPWORDS |= DETAIL_REQUEST_WORDS

# Demostrativos y pronombres que remiten a la respuesta anterior («de esos»,
# «de ellas»): nunca son el indicador, un filtro ni el sustantivo principal.
STOPWORDS |= {
    "esos", "esas", "eso", "esto", "ellos", "ellas", "aquel", "aquella",
    "aquellos", "aquellas",
}
# «qué tanto/tantas» = «cuánto/cuántas»: interrogativo, no sustantivo.
STOPWORDS |= {"tanto", "tanta", "tantos", "tantas"}

# Sinónimos de negocio por palabra (genéricos, no de un tablero concreto):
# «kilos de ropa» o «cuánto pesaron» preguntan por el PESO.
BUSINESS_TOKEN_SYNONYMS = {
    "kilo": "peso", "kilos": "peso", "kg": "peso", "kgs": "peso",
    "kilogramo": "peso", "kilogramos": "peso", "pesaron": "peso",
    "pesamos": "peso", "pesaba": "peso", "pesaban": "peso",
    # «cuánto se demoran / tardan / duran» pregunta por un TIEMPO.
    "demora": "tiempo", "demoras": "tiempo", "demoran": "tiempo", "demoro": "tiempo",
    "demoraron": "tiempo", "demoraba": "tiempo", "demoraban": "tiempo",
    "tarda": "tiempo", "tardan": "tiempo", "tardo": "tiempo", "tardaron": "tiempo",
    "duran": "tiempo", "duraron": "tiempo", "duracion": "tiempo",
}

# Cualquier forma de «tardar», «demorar» o «durar» (con o sin «se») pregunta por un TIEMPO:
# «se tardaban», «demorarse», «nos demoramos» (r9, causa 2).
_TIME_VERB_RE = re.compile(
    r"^(?:tard|demor|dur)(?:a|an|o|ar|aron|aba|aban|amos|ando|aria|arian|ara|aran)(?:se|nos|le|les)?$"
)

GENERIC_PAGE_WORDS = {"general", "inicio", "resumen", "principal", "home", "detalle", "portada", "indicadores"}

TECHNICAL_SUFFIXES = {"ok", "id", "cod", "key"}

TEMPORAL_WORDS = {"date", "fecha", "ano", "anio", "mes", "year", "month", "dia", "day"}

DESCRIPTIVE_PATTERNS = (
    "que significa", "que es", "que quiere decir", "como se calcula",
    "como se define", "definicion de", "explica",
    "que muestra", "que muestran", "que contiene", "que informacion",
    "que filtros", "que filtro", "para que sirve", "para que se usa",
    "como se mide", "como se interpreta", "como funciona", "que mide",
    "de que trata", "que visuales", "que paginas", "objetivo del",
    "descripcion del", "describe",
)

# Términos que, por sí solos, indican una consulta cuantitativa.
NUMERIC_TERM_PATTERNS = (
    r"cuant[oa]s?", r"cantidad", r"numero", r"total", r"promedio", r"media",
    r"porcentaje", r"valor", r"capacidad", r"giro", r"ocupacion",
    r"ocupacional", r"ingresos", r"egresos", r"participacion", r"proporcion",
    r"tasa", r"variacion", r"representa", r"representan", r"suma",
    r"sumatoria", r"%",
)

# Verbos/interrogativos que piden un dato ("dime el peso...", "cuál fue el ...").
QUERY_VERB_PATTERNS = (
    r"(?:y\s+)?(?:que|cual(?:es)?)\s+(?:fue|fueron|es|son|ha\s+sido|han\s+sido|seria|serian|era|eran)",
    r"(?:y\s+)?(?:dime|dame|dinos|muestrame|muestra|mostrar|muestre|indica|indicame|"
    r"consulta|calcula|obten|entregame|reporta|reportame|informame|necesito|"
    r"quiero|quisiera|me\s+(?:puedes|podrias|das|dices|indicas|muestras)|"
    r"puedes|podrias)",
)

# Participación / proporción sobre el total de una dimensión.
SHARE_PHRASES = (
    r"(?:el\s+|la\s+)?(?:porcentaje|%)\s+de\s+participacion(?:\s+porcentual)?",
    r"(?:el\s+|la\s+)?participacion(?:\s+porcentual)?(?:\s+relativa)?",
    r"(?:el\s+|la\s+)?(?:porcentaje|%)\s+(?:del|sobre\s+el)\s+total",
    r"(?:la\s+|una\s+)?proporcion(?:\s+(?:del|sobre\s+el)\s+total)?",
    r"(?:el\s+)?peso\s+relativo",
    r"(?:que\s+)?(?:porcentaje|parte|fraccion)\s+(?:del\s+total\s+)?(?:representa|representan|supone|aporta)",
    r"cuanto\s+(?:representa|representan|aporta|aportan)",
    r"que\s+tanto\s+(?:representa|representan|aporta|aportan)",
)
SHARE_RE = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(SHARE_PHRASES) + r")(?![a-z0-9])"
)
FILLER_WORDS = {
    "y", "e", "el", "la", "los", "las", "un", "una", "de", "del", "en", "al",
    "que", "cual", "cuales", "como", "fue", "fueron", "es", "son", "tuvo",
    "tuvieron", "tiene", "tienen", "hubo", "hay", "se", "su", "sus", "mes",
    "ano", "servicio", "tablero", "informe", "total", "con", "por", "para",
    "cuanto", "cuanta", "cuantos", "cuantas", "dime", "dame", "muestra",
    "numero", "valor", "porcentaje", "sobre", "durante", "entre",
}

DIMENSION_SYNONYMS = {
    "servicio": {"servicio", "servicios", "unidad", "unidades", "area", "areas"},
    "aseguradora": {"asegurador", "aseguradora", "aseguradoras", "aseguradores", "eps", "pagador", "pagadores"},
    "especialidad": {"especialidad", "especialidades"},
    "cirujano": {"cirujano", "cirujanos", "medico", "medicos"},
    "estado": {"estado", "estados", "situacion"},
    "causa": {"causa", "causas", "motivo", "motivos"},
    "modalidad": {"modalidad", "modalidades", "tipo atencion", "tipo de atencion"},
    "sexo": {"sexo", "genero"},
    "clasificacion": {"clasificacion", "triage"},
    "tipo": {"tipo", "tipos"},
    # Persona que registra/atiende («NOMBRE_COMPLETO», «USUARIO»).
    "colaborador": {
        "nombre completo", "usuario", "usuarios", "colaborador", "colaboradores",
        "empleado", "empleados", "funcionario", "funcionarios", "trabajador",
        "trabajadores", "operario", "operarios",
    },
}


def normalize_text(value):
    # Se llama cientos de miles de veces por turno con los mismos textos
    # (nombres de indicadores, columnas, valores de dominio): con caché.
    return _normalize_str(str(value or ""))


@lru_cache(maxsize=262144)
def _normalize_str(value):
    value = value.lower().strip()
    value = "".join(
        char for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    value = _NON_ALNUM_RE.sub(" ", value)
    return _SPACES_RE.sub(" ", value).strip()


_NON_ALNUM_RE = re.compile(r"[^a-z0-9%]+")
_SPACES_RE = re.compile(r"\s+")


def canonical_token(token):
    return _canonical_str(str(token or ""))


@lru_cache(maxsize=65536)
def _canonical_str(token):
    token = normalize_text(token)
    if not token:
        return ""
    token = BUSINESS_TOKEN_SYNONYMS.get(token, token)
    if _TIME_VERB_RE.match(token):
        return "tiempo"
    if token.endswith("iones") and len(token) > 6:
        return token[:-5] + "ion"
    if token.endswith("ales") and len(token) > 5:
        return token[:-2]
    if token.endswith("ares") and len(token) > 5:
        return token[:-2]
    if token.endswith("ores") and len(token) > 5:
        return token[:-2]
    if token.endswith("s") and len(token) > 4:
        return token[:-1]
    return token


def canonical_tokens(value):
    result = []
    for token in normalize_text(value).split():
        item = canonical_token(token)
        if item:
            result.append(item)
    return result


# Sin participios: «vencidos» (ya vencieron) no es «en vencimiento» (por vencer).
_VERB_ENDINGS = {
    "ar", "er", "ir", "a", "e", "an", "en", "o", "io", "ia", "ian", "ieron", "aron",
    "iendo", "ando", "era", "eran", "ara", "aran", "iera", "ieran", "ira", "iran", "ce", "cen",
}


# Final «y cuáles son» / «y en qué camas»: petición de lista (answer_shape).
_TRAILING_DETAIL_RE = re.compile(
    r"(?<![a-z0-9])y\s+(?:en\s+|de\s+|a\s+)?(?:cuales|que|donde)(?:\s+[a-z0-9]+){0,2}\s*$"
)


def _derived_noun_match(left, right):
    """Sustantivo en -miento y una forma conjugada de su verbo: «vencen» ->
    VENCIMIENTO, «crecen» -> CRECIMIENTO, «seguir» -> SEGUIMIENTO."""
    for noun, verb in ((left, right), (right, left)):
        for suffix in ("imiento", "amiento"):
            if noun.endswith(suffix):
                stem = noun[: -len(suffix)]
                if len(stem) >= 4 and verb.startswith(stem) and verb[len(stem):] in _VERB_ENDINGS:
                    return True
    return False


_NEGATING_PREFIXES = ("in", "im", "des", "dis")


def _negated_form(left, right):
    """«inasistencia» / «asistencia», «insatisfecha» / «satisfecha»,
    «desocupada» / «ocupada»: el prefijo niega la palabra; no son la misma."""
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) < 5:
        return False
    return any(longer == prefix + shorter for prefix in _NEGATING_PREFIXES)


# Conjugación frente a participio del mismo verbo: «facturó» / FACTURADO,
# «lavaron» / LAVADO, «atendieron» / ATENDIDOS.
_FINITE_VERB_ENDINGS = ("aron", "ieron", "amos", "emos", "imos", "o", "io", "an", "en", "a", "e")
_PARTICIPLE_ENDINGS = ("ados", "adas", "idos", "idas", "ado", "ada", "ido", "ida")


def _verb_participle_match(left, right):
    for verb, participle in ((left, right), (right, left)):
        for ending in _PARTICIPLE_ENDINGS:
            if not participle.endswith(ending):
                continue
            stem = participle[: -len(ending)]
            if len(stem) < 5 or not verb.startswith(stem):
                continue
            if verb[len(stem):] in _FINITE_VERB_ENDINGS:
                return True
    return False


# Verbo (con o sin pronombre enclítico) frente al sustantivo de acción en -ción/-sión del
# catálogo: «asignarle» / ASIGNACIÓN, «dispensarse» / DISPENSACIÓN, «admitieron» / ADMISIÓN,
# «facturaron» / FACTURACIÓN (r9, causa 2: verbos sin lematizar).
_CLITIC_RE = re.compile(r"(?<=[aei]r)(?:se|le|les|lo|la|los|las|me|nos|te)$|(?<=ndo)(?:se|le|les|lo|la|los|las)$")
_AR_ENDINGS = {
    "a", "an", "ar", "o", "e", "en", "aron", "aba", "aban", "ado", "ada", "ados", "adas", "ando",
    "amos", "aria", "arian", "ara", "aran", "ase", "asen", "emos",
}
_ER_IR_ENDINGS = {
    "e", "en", "er", "ir", "io", "ieron", "ia", "ian", "ido", "ida", "idos", "idas", "iendo", "imos",
    "a", "an", "iera", "ieran", "iria", "irian",
}


def _strip_clitic(word):
    stripped = _CLITIC_RE.sub("", word)
    return stripped if len(stripped) >= 5 else word


def _action_noun_match(left, right):
    for noun, verb in ((left, right), (right, left)):
        if not noun.endswith(("cion", "sion")) or len(noun) < 8:
            continue
        verb = _strip_clitic(verb)
        if verb.endswith(("cion", "sion")):
            continue
        if noun.endswith("acion"):
            stem, endings = noun[:-5], _AR_ENDINGS
        elif noun.endswith(("icion", "ision")):
            stem, endings = noun[:-5], _ER_IR_ENDINGS
            # admitir -> admisión, remitir -> remisión: la «t» del verbo se vuelve «s».
            if noun.endswith("ision") and verb.startswith(stem + "it") and verb[len(stem) + 2:] in endings:
                return len(stem) >= 3
        else:
            continue
        if len(stem) >= 4 and verb.startswith(stem) and verb[len(stem):] in endings:
            return True
    return False


def _token_similarity(left, right):
    if left == right:
        return 1.0
    # Mismos pares de palabras una y otra vez (pregunta × catálogo): con caché.
    if isinstance(left, str) and isinstance(right, str):
        return _token_similarity_cached(left, right)
    return _token_similarity_raw(left, right)


@lru_cache(maxsize=262144)
def _token_similarity_cached(left, right):
    return _token_similarity_raw(left, right)


def _token_similarity_raw(left, right):
    if left == right:
        return 1.0
    if _negated_form(left, right):
        return 0.0
    if _derived_noun_match(left, right):
        return 0.90
    if _verb_participle_match(left, right):
        return 0.88
    if _action_noun_match(left, right):
        return 0.88
    shortest = min(len(left), len(right))
    # Palabras cortas solo coinciden si son idénticas: «mayo» != «mayor».
    if shortest < 6:
        return 0.0
    # Prefijo solo cuando una palabra es prefijo literal de la otra
    # (ocupacion/ocupacional). programada != programacion,
    # hospitalario != hospitalizacion, consulta != consultorio.
    if abs(len(left) - len(right)) <= 3 and (left.startswith(right) or right.startswith(left)):
        return 0.90
    ratio = SequenceMatcher(None, left, right).ratio()
    return ratio if ratio >= 0.88 else min(ratio, 0.80)


# Solo verbos de petición que nunca nombran un valor: «consulta» o «ayudas»
# sí pueden ser valores reales (consulta externa, ayudas diagnósticas).
_TYPO_REQUEST_TOKENS = {
    canonical_token(word) for word in (
        "necesito", "necesitamos", "necesitaria", "quisiera", "gustaria",
        "informacion", "podrias", "indicame", "muestrame",
        "necesitaba", "necesitariamos", "requiero", "quisieramos",
    )
}
_REQUEST_TOKENS = {canonical_token(word) for word in REQUEST_WORDS}


def _phonetic_token(token):
    """Forma «fonética» aproximada del español escrito, para tolerar errores
    de ortografía que no cambian cómo suena la palabra: c/s/z («nesesito»,
    «nesecito», «nezesito»), b/v, h muda, ll/y y qu/k."""
    text = str(token or "").replace("ch", "#")
    text = re.sub(r"c(?=[ei])", "s", text)
    text = text.replace("z", "s").replace("v", "b").replace("ll", "y").replace("qu", "k")
    text = text.replace("c", "k").replace("h", "").replace("#", "ch")
    return text


_PHONETIC_REQUEST_TOKENS = {_phonetic_token(word) for word in _TYPO_REQUEST_TOKENS}


def _is_request_word(token):
    """Palabra de petición (token canónico), también con un error de tipeo («necsito»)."""
    if token in _REQUEST_TOKENS:
        return True
    if len(token) < 6:
        return False
    # Ortografía distinta con el mismo sonido («nesesito», «nesecito»).
    phonetic = _phonetic_token(token)
    if phonetic in _PHONETIC_REQUEST_TOKENS:
        return True
    return any(
        SequenceMatcher(None, token, word).ratio() >= 0.88
        # Letras intercambiadas («nesecito»): mismas letras y mismo inicio.
        or (token[:2] == word[:2] and sorted(token) == sorted(word))
        or (token[:2] == word[:2] and SequenceMatcher(None, phonetic, _phonetic_token(word)).ratio() >= 0.88)
        for word in _TYPO_REQUEST_TOKENS
    )


def _stem_token(token):
    """Raíz aproximada de una palabra en español para comparar plurales,
    géneros y derivados: pediátricos/pediatría -> «pediatr», ambulatorias/
    ambulatorio -> «ambulator», menores -> «menor». Nunca deja menos de 4
    letras (sura no se vuelve «sur»)."""
    token = normalize_text(token)
    # Participios y pretéritos («tomaron»/«tomadas», «realizaron»/«realizadas»).
    for suffix in ("aron", "ieron", "adas", "ados", "idas", "idos", "ada", "ado", "ida", "ido"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    for suffix in ("icos", "icas", "ico", "ica", "ios", "ias", "io", "ia", "os", "as", "es", "o", "a", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _tokens_match_loosely(left, right):
    """Misma palabra salvo plural/género/derivación (raíz) o error de tipeo leve."""
    if not left or not right:
        return False
    if left == right or _token_similarity(left, right) >= 0.88:
        return True
    return min(len(left), len(right)) >= 5 and _stem_token(left) == _stem_token(right)


def _alias_prefix(text, alias):
    """Parte inicial de `text` que nombra `alias` palabra por palabra, admitiendo
    plural/género/derivación («aseguradores» = ASEGURADORA, «servicios» =
    SERVICIO); None si no empieza por él. Las palabras cortas (≤ 4 letras)
    deben ser iguales o tener la misma forma canónica."""
    text_words = normalize_text(text).split()
    alias_words = normalize_text(alias).split()
    if not alias_words or len(text_words) < len(alias_words):
        return None

    def same(word, other):
        if word == other or canonical_token(word) == canonical_token(other):
            return True
        return min(len(word), len(other)) >= 5 and _stem_token(word) == _stem_token(other)

    # Un conector entre dos palabras del nombre técnico («areas DE servicio»
    # = AREA_SERVICIO) no rompe la coincidencia; antes de la primera, sí.
    position = 0
    for index, other in enumerate(alias_words):
        while (
            index and position < len(text_words) and text_words[position] in _ALIAS_CONNECTORS
            and not same(text_words[position], other)
        ):
            position += 1
        if position >= len(text_words) or not same(text_words[position], other):
            return None
        position += 1
    return " ".join(text_words[:position])


_ALIAS_CONNECTORS = {"de", "del", "la", "el", "los", "las"}


# Frases equivalentes con la MISMA polaridad («sin responder» = «sin
# respuesta»): se reescriben antes de resolver el indicador. Una palabra
# suelta no se reescribe: «respondidas» no es «sin respuesta».
PHRASE_SYNONYMS = (
    (re.compile(r"(?<![a-z0-9])(?:sin responder|no respondidas?|no respondidos?|"
                r"pendientes? (?:de|por) (?:respuesta|responder))(?![a-z0-9])"), "sin respuesta"),
)


# Perífrasis verbal con gerundio («se están manejando», «están atendiendo»,
# «van llegando»): es el verbo de la pregunta, nunca un indicador ni un valor
# de filtro. Se quita (solo con el auxiliar delante: un gerundio suelto podría
# ser parte de un nombre).
PROGRESSIVE_VERB_RE = re.compile(
    r"(?<![a-z0-9])(?:se\s+|nos\s+|les?\s+)?(?:esta|estan|estaba|estaban|estamos|estuvo|estuvieron|"
    r"sigue|siguen|seguimos|va|van|vamos|viene|vienen|venimos|anda|andan)\s+"
    r"[a-z]{3,}(?:ando|iendo|yendo)(?![a-z0-9])"
)


# «cómo están REPARTIDAS las camas por estado», «cómo se distribuyen los
# pacientes por servicio»: el verbo de reparto pide la agrupación que sigue
# («por <X>»); no es el sustantivo del indicador ni un filtro (holdout H02).
DISTRIBUTION_VERB_RE = re.compile(
    r"(?<![a-z0-9])(?:(?:se\s+)?(?:esta|estan|estaba|estaban|quedan|queda|quedaron|quedo|van|fueron|son)\s+)?"
    r"(?:repartid|distribuid|dividid)[oa]s?(?![a-z0-9])"
    r"|(?<![a-z0-9])se\s+(?:reparten|distribuyen|dividen|reparte|distribuye|divide)(?![a-z0-9])"
)


# Complemento agente de una pasiva: «confirmadas POR EL PACIENTE», «facturados POR LOS
# FACTURADORES», «canceladas por la institución». Nombra quién hizo la acción (a lo sumo un valor
# de filtro), nunca un desglose: se quita «por» y queda el sustantivo (r9, causa 4).
AGENT_COMPLEMENT_RE = re.compile(
    r"(?<![a-z0-9])((?:(?!(?:agrup|separ|desglos|discrimin|distribu|repart|divid|clasific|orden|filtr|organiz|segment)[a-z]*(?:ad|id)[oa]s?(?![a-z]))[a-z]{3,}(?:ad|id)[oa]s?|hech[oa]s?|puest[oa]s?|vist[oa]s?|abiert[oa]s?|escrit[oa]s?)"
    r"(?:\s+(?:ya|solo|directamente|personalmente))?)\s+por\s+(?=(?:el|la|los|las|un|una|nuestr[oa]s?|su|sus)\s+[a-z])"
)


def canonical_phrases(text):
    """(texto, [(frase original, reemplazo)]) con las frases equivalentes unificadas."""
    original = str(text or "")
    normalized = normalize_text(original)
    changes = []
    for match in PROGRESSIVE_VERB_RE.finditer(normalized):
        changes.append((match.group(0), ""))
    normalized = re.sub(r"\s{2,}", " ", PROGRESSIVE_VERB_RE.sub(" ", normalized)).strip()
    for match in AGENT_COMPLEMENT_RE.finditer(normalized):
        changes.append((match.group(0).strip(), match.group(1)))
    normalized = AGENT_COMPLEMENT_RE.sub(lambda match: match.group(1) + " ", normalized)
    distribution = DISTRIBUTION_VERB_RE.search(normalized)
    if distribution and re.search(r"(?<![a-z0-9])(?:por|segun|x)(?![a-z0-9])", normalized[distribution.end():]):
        changes.append((distribution.group(0), ""))
        normalized = re.sub(r"\s{2,}", " ", DISTRIBUTION_VERB_RE.sub(" ", normalized, count=1)).strip()
    for pattern, replacement in PHRASE_SYNONYMS:
        for match in pattern.finditer(normalized):
            if match.group(0) != replacement:
                changes.append((match.group(0), replacement))
        normalized = pattern.sub(replacement, normalized)
    if not changes:
        return original, []
    return normalized, changes


# ---------------- valores opuestos dentro de un dominio ----------------
# Conectores que nunca distinguen un valor de otro («MENORES DE EDAD»).
_VALUE_CONNECTORS = {"de", "del", "la", "el", "los", "las", "y", "e", "en", "a", "al", "por", "para", "o", "u"}
# Palabras de polaridad: distinguen ACEPTADO de NO ACEPTADO o CON/SIN
# ANTIBIÓTICO aunque sean palabras vacías en el resto del planificador.
_POLARITY_WORDS = {"no", "sin", "con"}
_ROMAN_DIGITS = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}


def _value_word_forms(word):
    """Formas comparables de una palabra de un valor: normalizada, canónica
    (sinónimos de negocio, plural) y raíz («menores» -> menor)."""
    word = normalize_text(word)
    forms = {word, canonical_token(word)}
    if len(word) >= 5:
        forms.add(_stem_token(word))
    if word in _ROMAN_DIGITS:
        forms.add(_ROMAN_DIGITS[word])
    return {form for form in forms if form}


def _value_words(value):
    """Palabras de un valor de dimensión que pueden distinguirlo de otro."""
    return [
        word for word in normalize_text(value).split()
        if word not in _VALUE_CONNECTORS
    ]


def _word_in_text(word, value_words, text_words):
    """¿La palabra `word` del valor aparece en el texto pedido?

    - Palabras cortas (≤ 3 letras, números romanos): idénticas.
    - Polaridad (no/sin/con): solo si precede (a ≤ 2 palabras) a otra
      palabra del mismo valor: «no aceptadas» sí niega; «¿no hay aceptadas?» no.
    - Resto: misma forma canónica, misma raíz o error de tipeo leve.
    """
    word = normalize_text(word)
    if word in _POLARITY_WORDS:
        others = [other for other in value_words if normalize_text(other) != word]
        for index, text_word in enumerate(text_words):
            if text_word != word:
                continue
            window = text_words[index + 1:index + 3]
            if not others or any(_word_in_text(other, others, window) for other in others):
                return True
        return False
    forms = _value_word_forms(word)
    for text_word in text_words:
        text_forms = _value_word_forms(text_word)
        if forms & text_forms:
            if len(word) <= 3 or len(text_word) <= 3:
                if word == text_word or _ROMAN_DIGITS.get(word) == text_word or _ROMAN_DIGITS.get(text_word) == word:
                    return True
                continue
            return True
        if min(len(word), len(text_word)) >= 6 and _token_similarity(word, text_word) >= 0.88:
            return True
    return False


def _value_word_key(word):
    """Forma con la que se cuenta la frecuencia de una palabra en un dominio."""
    return _stem_token_cached(word) if len(word) >= 5 else normalize_text(word)


@lru_cache(maxsize=65536)
def _stem_token_cached(word):
    return _stem_token(word)


_DOMAIN_ANALYSIS_LOCK = threading.Lock()
_DOMAIN_WORDS_CACHE = {}       # dominio -> (palabras, claves, frecuencias)
_DOMAIN_TEXT_CACHE = {}        # (dominio, texto) -> análisis con presencia en el texto
_DOMAIN_CACHE_LIMIT = 64


def _bounded_put(cache, key, value):
    with _DOMAIN_ANALYSIS_LOCK:
        if len(cache) >= _DOMAIN_CACHE_LIMIT:
            cache.pop(next(iter(cache)), None)
        cache[key] = value


def _domain_word_analysis(domain):
    cached = _DOMAIN_WORDS_CACHE.get(domain)
    if cached is not None:
        return cached
    words_by_value = {item: _value_words(item) for item in domain}
    keys_by_value = {
        item: {_value_word_key(word) for word in words} for item, words in words_by_value.items()
    }
    frequency = {}
    for keys in keys_by_value.values():
        for item in keys:
            frequency[item] = frequency.get(item, 0) + 1
    cached = (words_by_value, keys_by_value, frequency)
    _bounded_put(_DOMAIN_WORDS_CACHE, domain, cached)
    return cached


def _domain_text_analysis(domain, text_words):
    """Análisis de `value_contradiction` común a todos los valores del dominio
    para un mismo texto: palabras y raíces de cada valor, frecuencias, qué
    palabras distintivas de cada valor aparecen en el texto (base_hits) y la
    lista ordenada de valores que tienen alguna (rivales posibles)."""
    memo_key = (domain, text_words)
    cached = _DOMAIN_TEXT_CACHE.get(memo_key)
    if cached is not None:
        return cached
    plan_budget.check("análisis de valores opuestos")
    words_by_value, keys_by_value, frequency = _domain_word_analysis(domain)
    total = len(domain)
    text_list = list(text_words)
    cache = {}

    def present(word, words):
        # La polaridad depende de las demás palabras del valor; el resto no.
        memo = (word, tuple(words)) if normalize_text(word) in _POLARITY_WORDS else word
        if memo not in cache:
            cache[memo] = _word_in_text(word, words, text_list)
        return cache[memo]

    base_hits = {}
    for item, words in words_by_value.items():
        found = [
            word for word in words
            if frequency.get(_value_word_key(word), 0) < total and present(word, words)
        ]
        if found:
            base_hits[item] = found
    analysis = {
        "words_by_value": words_by_value, "keys_by_value": keys_by_value,
        "frequency": frequency, "present": present, "base_hits": base_hits,
        "rivals": [item for item in domain if item in base_hits],
    }
    _bounded_put(_DOMAIN_TEXT_CACHE, memo_key, analysis)
    return analysis


def value_contradiction(text, value, domain):
    """Motivo (texto) por el que `value` contradice lo pedido en `text`, o None.

    Un filtro nunca elige un valor opuesto a la palabra distintiva de la
    pregunta: «menores de edad» no es MAYORES DE EDAD, «no aceptadas» no es
    ACEPTADO, «triage» no es TRIAGE III. La distintividad se mide DENTRO del
    dominio de la columna (frecuencia de la palabra entre sus valores): las
    palabras que comparten todos los valores («de edad», «triage») no
    cuentan como coincidencia.
    - Regla A: si el valor tiene palabras distintivas, al menos una debe
      aparecer en el texto.
    - Regla B: si el texto nombra una palabra que distingue a OTRO valor
      del elegido (y ninguna que distinga al elegido de ese otro), el
      elegido contradice la pregunta (o el otro es más preciso).
    """
    domain = [item for item in dict.fromkeys(str(v) for v in (domain or []) if v is not None)]
    if str(value) not in domain:
        domain.append(str(value))
    if len(domain) < 2:
        return None
    text_words = normalize_text(text).split()
    if not text_words:
        return None
    # El análisis del dominio (palabras, raíces, frecuencias) y qué palabras
    # de cada valor aparecen en el texto no dependen del valor elegido: se
    # calculan una vez por (dominio, texto). Sin esto, una columna de ~1000
    # valores que coinciden todos por una palabra («pacientes» con
    # TIPO_PACIENTE) costaba O(n²) raíces por turno y colgaba el motor.
    analysis = _domain_text_analysis(tuple(domain), tuple(text_words))
    key = _value_word_key
    frequency = analysis["frequency"]
    keys_by_value = analysis["keys_by_value"]
    words_by_value = analysis["words_by_value"]
    present = analysis["present"]
    total = len(domain)
    own_words = words_by_value[str(value)]
    own_keys = keys_by_value[str(value)]

    distinctive = [word for word in own_words if frequency.get(key(word), 0) < total]
    shared = [word for word in own_words if frequency.get(key(word), 0) >= total]
    hits = [word for word in distinctive if present(word, own_words)]

    def rival_hits(other):
        # Solo los valores con alguna palabra distintiva presente en el texto
        # pueden ser rivales (precalculado): el resto devuelve [] sin recorrerlo.
        return [word for word in analysis["base_hits"].get(other, ()) if key(word) not in own_keys]

    candidates = analysis["rivals"]
    if distinctive and not hits:
        rivals = [(other, rival_hits(other)) for other in candidates if other != str(value)]
        rivals = [(other, found) for other, found in rivals if found]
        if rivals:
            other, found = rivals[0]
            return (
                f"la pregunta dice «{' '.join(found)}» (valor {other}), no "
                f"«{' '.join(distinctive)}»"
            )
        return (
            f"ninguna palabra distintiva de {value} («{' '.join(distinctive)}») aparece en la pregunta"
            + (f"; «{' '.join(shared)}» la comparten todos los valores de la columna" if shared else "")
        )
    for other in candidates:
        if other == str(value):
            continue
        found = rival_hits(other)
        if not found:
            continue
        other_keys = keys_by_value[other]
        own_only = [word for word in own_words if key(word) not in other_keys]
        if not any(present(word, own_words) for word in own_only):
            return (
                f"la pregunta dice «{' '.join(found)}», que distingue a {other} de {value}"
            )
    return None


_WORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")


def _exact_phrase(question, candidate):
    """¿`candidate` aparece en `question` como palabras completas? (Sin
    compilar un regex por candidato: se llama miles de veces por turno.)"""
    if not question or not candidate:
        return False
    start = question.find(candidate)
    while start != -1:
        end = start + len(candidate)
        if (start == 0 or question[start - 1] not in _WORD_CHARS) and (
            end >= len(question) or question[end] not in _WORD_CHARS
        ):
            return True
        start = question.find(candidate, start + 1)
    return False


def _phrase_score(question, candidate, weights=None):
    """Qué tanto cubre la pregunta al candidato.

    `weights` (token -> peso IDF) hace que palabras genéricas del catálogo
    (cirugías, pacientes...) valgan poco frente a las distintivas.
    """
    q = normalize_text(question)
    c = normalize_text(candidate)
    if not q or not c:
        return 0.0
    weights = weights or {}
    # Un rango que empieza en 0 («0-30 DÍAS») se nombra por su tope:
    # «los próximos 30 días» cubre «0-30 días»; «30-120» sigue exigiendo el 120.
    if not _exact_phrase(q, c):
        c = re.sub(r"(?<![0-9])0 (?=[0-9])", "", c).strip() or c

    if _exact_phrase(q, c):
        specificity = min(len(c.split()), 6)
        base = min(1.20, 1.00 + 0.03 * specificity)
        if weights:
            base += 0.10 * min(3.0, sum(weights.get(t, 1.0) for t in canonical_tokens(c)))
        return base

    q_tokens = canonical_tokens(q)
    c_tokens = canonical_tokens(c)
    if not q_tokens or not c_tokens:
        return 0.0

    matched = []
    for candidate_token in c_tokens:
        best = max(
            (_token_similarity(candidate_token, question_token) for question_token in q_tokens),
            default=0.0,
        )
        matched.append(best)

    # Todas las palabras del candidato aparecen tal cual (aunque separadas):
    # «total de cirugías» cubre por completo «Total Cirugías».
    if len(c_tokens) >= 2 and all(value == 1.0 for value in matched):
        base = min(1.20, 1.00 + 0.02 * min(len(c_tokens), 6))
        if weights:
            base += 0.10 * min(3.0, sum(weights.get(t, 1.0) for t in c_tokens))
        return base

    token_weights = [weights.get(token, 1.0) for token in c_tokens]
    coverage = sum(w for w, value in zip(token_weights, matched) if value >= 0.82) / sum(token_weights)
    if coverage < 0.60:
        return 0.0

    average = sum(matched) / len(matched)
    precision = min(len(c_tokens), len(q_tokens)) / max(len(c_tokens), len(q_tokens))
    return min(0.99, 0.68 * coverage + 0.24 * average + 0.08 * precision)


def _original_phrase(question, phrase):
    """Fragmento de la pregunta original (con tildes) que corresponde a una
    frase normalizada: «este ano» -> «este año». Si no se ubica, la frase."""
    target = normalize_text(phrase)
    if not target:
        return phrase
    words = list(re.finditer(r"[^\W_]+|%", str(question or "")))
    for i in range(len(words)):
        joined = ""
        for j in range(i, len(words)):
            joined = (joined + " " + normalize_text(words[j].group(0))).strip()
            if joined == target or re.sub(r"(\d) (er|ero|ro|do|to|o|a)\b", r"\1\2", joined) == target:
                return question[words[i].start():words[j].end()]
            if len(joined) > len(target) + 4:
                break
    return phrase


def _unique_strings(values):
    result = []
    seen = set()
    for value in values:
        if not value:
            continue
        key = normalize_text(value)
        if key and key not in seen:
            result.append(str(value))
            seen.add(key)
    return result

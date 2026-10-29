import json
import math
import os
import re
import threading
import unicodedata
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from src.providers.domain_cache import connection_open, domain_cache_for, identifier_column
from src.semantic.question_kind import descriptive_phrase
from src.semantic.answer_shape import DETAIL_REQUEST_WORDS, detail_request
from src.semantic.period_parser import (
    GRANULARITY_LABELS,
    MONTH_NAMES as PERIOD_MONTH_NAMES,
    MONTHS as PERIOD_MONTHS,
    TO_DATE_WORDS,
    PeriodParser,
    as_date,
    neutral_phrases,
    split_period,
    year_months,
)

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
# Forma de pedir una lista («lista de», «qué camas están…»): no es filtro.
STOPWORDS |= DETAIL_REQUEST_WORDS

# Demostrativos y pronombres que remiten a la respuesta anterior («de esos»,
# «de ellas»): nunca son el indicador, un filtro ni el sustantivo principal.
STOPWORDS |= {
    "esos", "esas", "eso", "esto", "ellos", "ellas", "aquel", "aquella",
    "aquellos", "aquellas",
}

# Sinónimos de negocio por palabra (genéricos, no de un tablero concreto):
# «kilos de ropa» o «cuánto pesaron» preguntan por el PESO.
BUSINESS_TOKEN_SYNONYMS = {
    "kilo": "peso", "kilos": "peso", "kg": "peso", "kgs": "peso",
    "kilogramo": "peso", "kilogramos": "peso", "pesaron": "peso",
    "pesamos": "peso", "pesaba": "peso", "pesaban": "peso",
}

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
    value = str(value or "").lower().strip()
    value = "".join(
        char for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    value = re.sub(r"[^a-z0-9%]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_token(token):
    token = normalize_text(token)
    if not token:
        return ""
    token = BUSINESS_TOKEN_SYNONYMS.get(token, token)
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


def _token_similarity(left, right):
    if left == right:
        return 1.0
    if _derived_noun_match(left, right):
        return 0.90
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


def canonical_phrases(text):
    """(texto, [(frase original, reemplazo)]) con las frases equivalentes unificadas."""
    original = str(text or "")
    normalized = normalize_text(original)
    changes = []
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
    words_by_value = {item: _value_words(item) for item in domain}
    cache = {}
    # Frecuencia de cada palabra (por su forma canónica) en el dominio.
    def key(word):
        return _stem_token(word) if len(word) >= 5 else normalize_text(word)

    keys_by_value = {item: {key(word) for word in words} for item, words in words_by_value.items()}
    frequency = {}
    for keys in keys_by_value.values():
        for item in keys:
            frequency[item] = frequency.get(item, 0) + 1
    total = len(domain)
    own_words = words_by_value[str(value)]
    own_keys = keys_by_value[str(value)]

    def present(word, words):
        # La polaridad depende de las demás palabras del valor; el resto no.
        memo = (word, tuple(words)) if normalize_text(word) in _POLARITY_WORDS else word
        if memo not in cache:
            cache[memo] = _word_in_text(word, words, text_words)
        return cache[memo]

    distinctive = [word for word in own_words if frequency.get(key(word), 0) < total]
    shared = [word for word in own_words if frequency.get(key(word), 0) >= total]
    hits = [word for word in distinctive if present(word, own_words)]

    def rival_hits(other):
        words = words_by_value[other]
        return [
            word for word in words
            if key(word) not in own_keys and frequency.get(key(word), 0) < total and present(word, words)
        ]

    if distinctive and not hits:
        rivals = [(other, rival_hits(other)) for other in domain if other != str(value)]
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
    for other in domain:
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


def _exact_phrase(question, candidate):
    return bool(
        question and candidate
        and re.search(r"(?<![a-z0-9])" + re.escape(candidate) + r"(?![a-z0-9])", question)
    )


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


class QueryPlanBuilder:
    """Planificador determinista: métrica -> modelo -> dimensiones -> DAX."""

    def __init__(
        self,
        master_metrics_path,
        visual_catalog_path,
        source_router,
        powerbi_provider,
        project_root=None,
        min_metric_score=0.74,
        ambiguity_margin=0.055,
        max_implicit_dimensions=6,
        today=None,
    ):
        # Fecha de referencia de los periodos relativos («este año», «mes
        # pasado»): date, callable o None (= hoy). Las pruebas la fijan.
        self.today = today
        self.master_metrics_path = Path(master_metrics_path)
        self.visual_catalog_path = Path(visual_catalog_path)
        self.source_router = source_router
        self.powerbi_provider = powerbi_provider
        self.project_root = Path(
            project_root or self.master_metrics_path.resolve().parents[2]
        ).resolve()
        self.min_metric_score = float(min_metric_score)
        self.ambiguity_margin = float(ambiguity_margin)
        self.max_implicit_dimensions = int(max_implicit_dimensions)
        self.master = self._load_json(self.master_metrics_path, {})
        self.visual_catalog = self._load_json(self.visual_catalog_path, {})
        self.metrics = list(self.master.get("metrics", []) or [])
        self.value_cache = {}
        self.domain_errors = {}  # Fallos temporales XMLA: nunca cachear como dominio vacío.
        self.reports = self._normalize_reports(self.visual_catalog)
        self.dimension_fields = self._build_dimension_index()
        self.static_values = self._build_static_value_index()
        # Tarjetas cuyo visual filtra el dato («0-30 DÍAS» = mes <= 1): la
        # expresión del indicador lleva ese filtro.
        self.metrics = self._with_visual_filters(self.metrics)
        # Sumas de dinero (SUM de MONTO/VALOR/COSTO...): se muestran como pesos.
        self.metrics = self._with_value_formats(self.metrics)
        # Opcional (POWERBI_DOMAIN_PREWARM=1): precalienta en segundo plano los
        # dominios de las columnas más usadas para nombrar valores.
        self.prewarm_thread = self._maybe_prewarm_domains()

    # ---------------- filtros de nivel de visual ----------------
    _CALENDAR_TABLE_RE = re.compile(r"^(?:calendario|calendar|fecha|dates?|localdatetable.*|datetabletemplate.*)$")

    def _visual_index(self):
        """{(modelo normalizado, visual_id): visual} del catálogo de visuales."""
        cached = self.__dict__.get("_visual_index_cache")
        if cached is None:
            cached = {}
            for report in self.reports:
                model = normalize_text(report.get("semantic_model"))
                for page in report.get("pages", []) or []:
                    for visual in page.get("visuals", []) or []:
                        if visual.get("visual_id"):
                            cached.setdefault((model, str(visual["visual_id"])), visual)
            self._visual_index_cache = cached
        return cached

    def _visual_filter_clauses(self, semantic_model, visual):
        """[(tabla, columna, condición)] de los filtros de nivel de visual que
        cambian el dato, o None si alguno no se entiende (no se aplica nada).
        Se ignoran los filtros sin condición y los de fecha/calendario (el
        periodo lo decide la pregunta)."""
        from src.semantic.visual_filters import UnsupportedCondition, condition_from_visual_file

        clauses = []
        for item in ((visual.get("filters") or {}).get("visual") or []):
            field = item.get("field") or {}
            table, column = field.get("table"), field.get("column")
            if field.get("kind") != "column" or not table or not column:
                if item.get("values") or item.get("condition"):
                    return None
                continue
            if self._CALENDAR_TABLE_RE.match(normalize_text(table).replace(" ", "")):
                continue
            if self._column_type(semantic_model, table, column) == "date":
                continue
            if "condition" in item or item.get("condition_error"):
                if item.get("condition_error"):
                    return None
                condition = item.get("condition")
            else:
                # Catálogo anterior a guardar la condición: se lee del visual.json.
                try:
                    condition = condition_from_visual_file(visual.get("source_file"), item.get("name"), column)
                except UnsupportedCondition:
                    return None
                if condition is None and item.get("values"):
                    return None  # tenía valores pero no se pudo leer el operador
            if condition is None:
                continue
            clauses.append((table, column, condition))
        return clauses

    def _with_visual_filters(self, metrics):
        """Indicadores definidos por un visual (tarjeta, gráfico) cuyo visual
        tiene filtros propios: la expresión pasa a CALCULATE(expr, filtros).
        «MEDICAMENTOS EN VENCIMIENTO 0-30 DÍAS» = DISTINCTCOUNT(IPRCODIGO) con
        mes <= 1; «INTERCONSULTAS SIN RESPUESTA» = ... con OID_RESPUESTA en
        blanco. Solo si TODAS sus apariciones llevan los mismos filtros (si no,
        el valor general es el de la medida sin filtro)."""
        try:
            from src.semantic.visual_filters import condition_signature, describe_condition, filter_dax
        except Exception:
            return metrics
        index = self._visual_index()
        if not index:
            return metrics
        result = []
        for metric in metrics:
            appearances = metric.get("appearances") or []
            expression = metric.get("dax_expression")
            if (
                metric.get("source_type") != "visual_aggregation" or not appearances or not expression
                or metric.get("visual_filters")
            ):
                result.append(metric)
                continue
            model = normalize_text(metric.get("semantic_model"))
            signatures, chosen = set(), None
            try:
                for appearance in appearances:
                    visual = index.get((model, str(appearance.get("visual_id"))))
                    clauses = None if visual is None else self._visual_filter_clauses(
                        metric.get("semantic_model"), visual,
                    )
                    if clauses is None:
                        signatures = None
                        break
                    signatures.add(tuple(sorted(condition_signature(*clause) for clause in clauses)))
                    chosen = clauses
            except Exception:
                signatures = None
            if not signatures or len(signatures) != 1 or not chosen:
                result.append(metric)
                continue
            try:
                arguments = [filter_dax(table, column, condition) for table, column, condition in chosen]
            except Exception:
                result.append(metric)
                continue
            enriched = dict(metric)
            enriched["base_dax_expression"] = expression
            enriched["dax_expression"] = "CALCULATE(" + expression + ", " + ", ".join(arguments) + ")"
            enriched["visual_filters"] = [
                {"table": table, "column": column, "condition": condition,
                 "text": describe_condition(condition, column)}
                for table, column, condition in chosen
            ]
            result.append(enriched)
        return result

    # ---------------- formato del valor (dinero) ----------------
    _MONEY_NAME_RE = re.compile(
        r"(?<![a-z])(?:monto|montos|valor|valores|costo|costos|precio|precios|pago|pagos|tarifa|tarifas|"
        r"facturado|facturada|facturados|recaudo|recaudado|cartera|glosa|glosado|presupuesto|"
        r"pesos|dinero|subtotal|iva|copago|cuota)(?![a-z])"
    )
    _NOT_MONEY_LABEL_RE = re.compile(
        r"(?<![a-z])(?:dia|dias|tiempo|tiempos|hora|horas|minuto|minutos|cantidad|cantidades|numero|"
        r"unidades|unidad|porcentaje|promedio|conteo|recuento|pacientes|registros|casos)(?![a-z])|%"
    )
    _SUM_EXPRESSION_RE = re.compile(r"^\s*(?:CALCULATE\s*\(\s*)?SUMX?\s*\(", re.IGNORECASE)

    def _is_money_metric(self, metric):
        """¿El indicador es una suma de dinero? Por su formato de Power BI
        («$#,0») o por ser SUM/SUMX de una columna de dinero (MONTO_FACTURADO,
        VALOR, COSTO...) sin palabras de otra unidad en su nombre."""
        fmt = str(metric.get("format_string") or "")
        if "$" in fmt or "€" in fmt or "currency" in fmt.lower():
            return True
        if fmt:
            return False
        label = normalize_text(f"{metric.get('label') or ''} {metric.get('measure') or ''}")
        if self._NOT_MONEY_LABEL_RE.search(label):
            return False
        expression = str(
            metric.get("model_expression") or metric.get("base_dax_expression") or metric.get("dax_expression") or ""
        )
        if not self._SUM_EXPRESSION_RE.search(expression):
            return False
        columns = " ".join(re.findall(r"\[([^\]]+)\]", expression))
        names = normalize_text(columns.replace("_", " "))
        return bool(self._MONEY_NAME_RE.search(names))

    def _with_value_formats(self, metrics):
        result = []
        for metric in metrics:
            if not metric.get("format") and self._is_money_metric(metric):
                metric = {**metric, "format": "currency"}
            result.append(metric)
        return result

    def _load_json(self, path, default):
        if not Path(path).exists():
            return default
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def _normalize_reports(self, catalog):
        reports = list(catalog.get("reports", []) or [])
        if reports:
            return reports
        if catalog.get("semantic_model"):
            return [{
                "report": catalog.get("report") or catalog.get("semantic_model"),
                "semantic_model": catalog.get("semantic_model"),
                "source_group": catalog.get("source_group"),
                "pages": catalog.get("pages", []),
                "metrics": catalog.get("metrics", []),
            }]
        return []

    # ---------------- metrics ----------------
    def _metric_names(self, metric):
        values = [metric.get("label"), metric.get("measure")]
        values.extend(metric.get("aliases", []) or [])
        for appearance in metric.get("appearances", []) or []:
            values.extend([
                appearance.get("visual_title"),
                appearance.get("native_query_ref"),
            ])
        return _unique_strings(values)

    def _metric_reports(self, metric):
        values = [metric.get("report")]
        values.extend(metric.get("reports", []) or [])
        for appearance in metric.get("appearances", []) or []:
            values.append(appearance.get("report"))
        return _unique_strings(values)

    def _metric_pages(self, metric):
        values = [metric.get("dashboard")]
        for appearance in metric.get("appearances", []) or []:
            values.append(appearance.get("page_display_name"))
        return _unique_strings(values)

    def _metric_visual_ids(self, metric):
        return {
            str(appearance.get("visual_id"))
            for appearance in metric.get("appearances", []) or []
            if appearance.get("visual_id")
        }

    def _source_context(self, question, dashboard=None):
        try:
            return self._refine_board_context(
                self.source_router.resolve(question=question, dashboard=dashboard)
            )
        except Exception as error:
            return {
                "status": "error",
                "routing_strength": "none",
                "error": f"{type(error).__name__}: {error}",
            }

    def _dedupe_metrics(self, metrics):
        result = []
        seen = set()
        for metric in metrics:
            reports = metric.get("reports", []) or []
            key = (
                normalize_text(metric.get("semantic_model")),
                normalize_text(metric.get("report") or (reports[0] if reports else None)),
                normalize_text(metric.get("label")),
                normalize_text(metric.get("dax_expression")),
            )
            if key in seen:
                continue
            result.append(metric)
            seen.add(key)
        return result

    def _metric_business_question(self, question, source_context):
        text = normalize_text(question)
        # «… y en qué camas» / «… y cuáles son» pide el listado de lo contado
        # («cuántos pacientes de sanitas…»): no nombra el indicador.
        trailing = _TRAILING_DETAIL_RE.search(text)
        if trailing and re.search(r"(?<![a-z0-9])cuant[oa]s\s", text[:trailing.start()]):
            text = text[:trailing.start()].strip()

        removals = [
            source_context.get("report"),
            source_context.get("semantic_model"),
            source_context.get("source_group"),
        ]

        for value in removals:
            normalized = normalize_text(value)
            if normalized:
                text = re.sub(
                    r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])",
                    " ",
                    text,
                )

        text = re.sub(r"\b(?:tablero|informe|modelo semantico)\b", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    # ---- pesos IDF: palabras repetidas en todo el catálogo valen poco ----
    def _token_weight_index(self):
        if getattr(self, "_token_weights", None) is not None:
            return self._token_weights
        labels = set()
        document_frequency = {}
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            for name in (metric.get("label"), metric.get("measure")):
                key = normalize_text(name)
                if not key or key in labels:
                    continue
                labels.add(key)
                for token in set(canonical_tokens(key)):
                    document_frequency[token] = document_frequency.get(token, 0) + 1
        total = len(labels)
        weights = {}
        if total > 1:
            for token, count in document_frequency.items():
                weights[token] = 0.25 + 0.75 * (1.0 - count / total)
        self._token_weights = weights
        self._known_labels = labels
        return weights

    def _token_weight(self, token):
        return self._token_weight_index().get(token, 1.0)

    def _unexplained_penalty(self, business_question, explained_tokens):
        """Castiga palabras distintivas de la pregunta que el candidato no explica."""
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}
        ignored.update(canonical_token(word) for word in MONTHS)
        ignored.update(self._period_words(business_question))  # «este año», «últimos 3 meses»
        penalty = 0.0
        for token in set(canonical_tokens(business_question)):
            if token in ignored or token.isdigit() or len(token) < 3 or _is_request_word(token):
                continue
            if any(_token_similarity(token, other) >= 0.82 for other in explained_tokens):
                continue
            penalty += 0.12 * self._token_weight(token)
        return min(0.45, penalty)

    def _page_bonus(self, question_tokens, metric, name_tokens):
        """Mencionar la página/dashboard de la métrica desempata de verdad (+0.20).

        Se ignoran páginas genéricas y las palabras que ya forman parte del
        nombre de la métrica (una página «Cirugías Realizadas» no debe premiar
        a la métrica «Cirugías Realizadas» solo por llamarse igual).
        """
        stop = {canonical_token(word) for word in STOPWORDS}
        for page in self._metric_pages(metric):
            tokens = [
                token for token in canonical_tokens(page)
                if token not in name_tokens and token not in GENERIC_PAGE_WORDS
                and token not in stop
            ]
            if not tokens:
                continue
            if len(tokens) == 1 and self._token_weight(tokens[0]) < 0.5:
                continue
            if all(
                any(_token_similarity(token, other) >= 0.82 for other in question_tokens)
                for token in tokens
            ):
                return 0.20
        return 0.0

    def _logical_key(self, metric):
        return (
            normalize_text(metric.get("semantic_model")),
            normalize_text(metric.get("table")),
            normalize_text(metric.get("dax_expression")),
        )

    _SUGGESTION_LIMIT = 6

    def _metric_suggestions(self, business_question, model_hint="", strong=False,
                            ratio=0.6, limit=_SUGGESTION_LIMIT):
        """Métricas que comparten alguna palabra distintiva con la pregunta.

        No alcanzan para responder, pero sí para contrapreguntar: «¿cuántas
        cirugías hay?» -> Total cirugías / Cirugías realizadas / ...
        """
        weights = self._token_weight_index()
        ignored = {
            canonical_token(word)
            for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
        }
        question_tokens = {
            token for token in canonical_tokens(business_question)
            if len(token) >= 4 and not token.isdigit()
            and token not in ignored and not _is_request_word(token)
        }
        if not question_tokens:
            return []

        suggestions = []
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            best_score, best_name, best_extra = 0.0, None, 0
            for name in self._metric_names(metric):
                name_tokens = canonical_tokens(name)
                score = sum(
                    weights.get(token, 1.0) for token in question_tokens
                    if any(_token_similarity(token, other) >= 0.88 for other in name_tokens)
                )
                # Palabras del nombre que la pregunta no menciona: a igual
                # puntaje va primero el nombre más cercano («Total cirugías»
                # antes que «Cirugías programadas» para «¿cuántas cirugías?»).
                extra = sum(
                    1 for other in set(name_tokens)
                    if other not in ignored and not any(
                        _token_similarity(other, token) >= 0.88 for token in question_tokens
                    )
                )
                if score > best_score or (score == best_score and score > 0 and extra < best_extra):
                    best_score, best_name, best_extra = score, name, extra
            if best_score <= 0:
                continue
            if model_hint and normalize_text(metric.get("semantic_model")) == model_hint:
                best_score += 0.20 if strong else 0.01
            # Las que el usuario ve en un tablero van primero.
            if not (metric.get("appearances") or []):
                best_score -= 0.25
            suggestions.append({
                "metric": metric, "score": round(best_score, 4),
                "business_score": round(best_score, 4), "matched_name": best_name,
                "_extra": best_extra,
            })

        suggestions.sort(key=lambda item: (
            -item["score"], item["_extra"], normalize_text(item["metric"].get("label")),
            str(item["metric"].get("metric_id")),
        ))
        result, seen = [], set()
        for item in suggestions:
            key = self._logical_key(item["metric"])
            if key in seen:
                continue
            seen.add(key)
            if item["score"] > 0:
                result.append(item)
        if not result:
            return []
        # Solo las cercanas a la mejor: una palabra suelta compartida con una
        # métrica lejana no debe llenar la lista.
        best = result[0]["score"]
        return [item for item in result if item["score"] >= best * ratio][:limit]

    # Palabras de conteo al inicio de un nombre que la pregunta no repite:
    # «cuántos suministros pendientes» = NÚMERO DE SUMINISTROS PENDIENTES.
    _COUNT_NAME_PREFIX_RE = re.compile(
        r"^(?:numero|nro|total|cantidad|conteo|recuento)\s+(?:(?:de|del)\s+(?:(?:la|las|los|el)\s+)?)?"
    )

    def _core_name_score(self, business_question, label, weights):
        """Puntaje del nombre sin «número de / total de / cantidad de» al
        inicio, solo si lo que queda tiene al menos dos palabras con contenido
        («suministros pendientes»; «Total cirugías» no se recorta)."""
        norm = normalize_text(label)
        core = self._COUNT_NAME_PREFIX_RE.sub("", norm).strip()
        if not core or core == norm:
            return 0.0
        content = [
            token for token in canonical_tokens(core)
            if token not in {canonical_token(word) for word in STOPWORDS} and not token.isdigit()
        ]
        if len(content) < 2 or self._weak_name_kind(core):
            return 0.0
        return _phrase_score(business_question, core, weights)

    def _focus_suggestions(self, business_question, source_context, suggestions):
        """Opciones de una contrapregunta sin indicadores irrelevantes.

        - Las palabras del tablero al que se enrutó («farmacia» en «... en
          farmacia») no hacen pariente a un indicador: NÚMERO DE SUMINISTROS
          PENDIENTES no se ofrece para «medicamentos vencidos en farmacia».
        - Si alguna opción comparte la palabra MÁS distintiva de la pregunta
          (peso IDF; «vencidos» frente a «medicamentos») o está en la página
          nombrada (MEDICAMENTOS VENCIDOS), se descartan las que no, y esas van
          primero."""
        if not suggestions:
            return suggestions
        ignored = {
            canonical_token(word)
            for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
        }
        question_tokens = [
            token for token in dict.fromkeys(canonical_tokens(business_question))
            if len(token) >= 4 and not token.isdigit() and token not in ignored and not _is_request_word(token)
        ]
        strong = (
            (source_context or {}).get("status") == "resolved"
            and (source_context or {}).get("routing_strength") == "strong"
        )
        board_tokens = set()
        if strong:
            for phrase in self._board_name_phrases(source_context):
                board_tokens.update(canonical_tokens(phrase))
        content = [token for token in question_tokens if token not in board_tokens] or question_tokens
        if not content:
            return suggestions
        named_page = normalize_text((source_context or {}).get("dashboard"))

        def name_hits(metric):
            # Nombres visibles, no referencias técnicas («Sum(PENDIENTES_FARMACIA.HCNFOLIO)»).
            names = [
                token for name in [*self._metric_names(metric), metric.get("table")]
                if name and not re.search(r"[().]", str(name))
                for token in canonical_tokens(name)
            ]
            return {token for token in content if any(_token_similarity(token, other) >= 0.88 for other in names)}

        def page_hit(metric):
            for page in self._metric_pages(metric):
                page_norm = normalize_text(page)
                if named_page and page_norm == named_page:
                    return True
                tokens = [t for t in canonical_tokens(page) if t not in ignored and len(t) >= 3]
                if tokens and all(self._explains(t, content) for t in tokens):
                    return True
            return False

        scored = [(item, name_hits(item["metric"]), page_hit(item["metric"])) for item in suggestions]
        related = [entry for entry in scored if entry[1] or entry[2]]
        if not related:
            return suggestions
        matched_tokens = {token for _, hits, _ in related for token in hits}
        # Más distintiva: mayor peso IDF; a igual peso, la que comparten menos opciones.
        top = max(
            sorted(matched_tokens),
            key=lambda token: (
                round(self._token_weight(token), 6),
                -sum(1 for _, hits, _ in related if token in hits),
            ),
        ) if matched_tokens else None
        focused = [
            entry for entry in related
            if (top is not None and top in entry[1]) or entry[2]
        ] or related
        # Orden estable: primero las que comparten la palabra distintiva; dentro
        # de cada grupo se respeta el orden del resolutor.
        focused.sort(key=lambda entry: 0 if top is not None and top in entry[1] else 1)
        dropped = [entry[0]["metric"].get("label") for entry in scored if entry not in focused]
        if dropped:
            self._note(
                "opciones descartadas por no compartir la palabra distintiva "
                + (f"«{top}» " if top else "")
                + "ni estar en la página nombrada: " + ", ".join(str(label) for label in dropped[:6])
            )
        return [entry[0] for entry in focused]

    def _resolve_metric(self, question, source_context, selected_metric_id=None,
                        with_suggestions=False, candidate_limit=8):
        # Una selección realizada durante una aclaración manda por ID,
        # no por el texto de la respuesta del usuario.
        if selected_metric_id is not None:
            for metric in self._dedupe_metrics(self.metrics):
                if metric.get("validation_status") != "approved":
                    continue
                if str(metric.get("metric_id")) == str(selected_metric_id):
                    return {
                        "status": "resolved", "metric": metric,
                        "matched_name": metric.get("label"), "score": 10.0,
                        "candidates": [{"metric": metric, "score": 10.0,
                                        "business_score": 10.0,
                                        "matched_name": metric.get("label")}],
                    }
            return {"status": "not_found", "candidates": []}

        weights = self._token_weight_index()
        business_question = self._metric_business_question(question, source_context)
        normalized_business = normalize_text(business_question)
        question_tokens = canonical_tokens(business_question)
        resolved_routing = source_context.get("status") == "resolved"
        strong = resolved_routing and source_context.get("routing_strength") == "strong"
        weak = resolved_routing and source_context.get("routing_strength") == "weak"
        model_hint = normalize_text(source_context.get("semantic_model")) if (strong or weak) else ""
        report_hint = normalize_text(source_context.get("report")) if strong else ""
        candidates = []

        def not_found(weak_candidates):
            result = {"status": "not_found", "candidates": weak_candidates}
            if with_suggestions:
                result["suggestions"] = self._focus_suggestions(
                    business_question, source_context,
                    self._metric_suggestions(business_question, model_hint=model_hint, strong=strong),
                )
            return result

        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            metric_model = normalize_text(metric.get("semantic_model"))
            metric_reports = [normalize_text(value) for value in self._metric_reports(metric)]

            primary_label = metric.get("label") or ""
            primary_norm = normalize_text(primary_label)
            primary_score = _phrase_score(business_question, primary_label, weights)
            label_is_exact = _exact_phrase(normalized_business, primary_norm)
            if primary_score < self.min_metric_score:
                # «cuántos suministros pendientes» nombra NÚMERO DE SUMINISTROS
                # PENDIENTES: «número de» / «total de» no se exige.
                primary_score = max(primary_score, self._core_name_score(business_question, primary_label, weights))

            titles = _unique_strings(
                appearance.get("visual_title")
                for appearance in metric.get("appearances", []) or []
            )
            exact_title = None
            for title in titles:
                title_norm = normalize_text(title)
                if title_norm == primary_norm or not _exact_phrase(normalized_business, title_norm):
                    continue
                # Un título compartido con la etiqueta de OTRA métrica
                # (EGRESOS de AÑO ACTUAL) solo es alias, no nombre propio.
                if title_norm in self._known_labels:
                    continue
                exact_title = title
                break

            aliases = [
                item for item in self._metric_names(metric)
                if normalize_text(item) != primary_norm
            ]
            best_alias = max(
                ((_phrase_score(business_question, name, weights), name) for name in aliases),
                key=lambda pair: pair[0], default=(0.0, None),
            )
            label_weight = sum(weights.get(t, 1.0) for t in canonical_tokens(primary_label))
            if label_is_exact:
                best_name = primary_label
                best_name_score = primary_score
                # Una etiqueta de una palabra genérica («Cirugías») pesa poco.
                name_priority = 0.32 * min(1.0, label_weight)
            elif exact_title:
                best_name = exact_title
                best_name_score = _phrase_score(business_question, exact_title, weights)
                name_priority = 0.32 * min(1.0, sum(weights.get(t, 1.0) for t in canonical_tokens(exact_title)))
            elif best_alias[0] > primary_score:
                best_name = best_alias[1]
                best_name_score = best_alias[0]
                name_priority = 0.0
            else:
                best_name = primary_label
                best_name_score = primary_score
                name_priority = 0.0

            # Un nombre sin contenido propio («2024», «Registrado») o solo
            # genérico («Promedio mensual») no elige el indicador por sí solo.
            best_name, best_name_score, name_priority = self._discard_weak_name(
                metric, business_question, best_name, best_name_score, name_priority,
                in_named_model=bool(model_hint) and strong and metric_model == model_hint,
            )
            if best_name_score <= 0:
                continue
            score = best_name_score + name_priority

            in_hint_model = bool(model_hint) and metric_model == model_hint
            in_hint_report = bool(report_hint) and (
                not metric_reports or report_hint in metric_reports
            )
            # Solo un informe/alias nombrado (routing fuerte) pesa. El routing
            # débil sale del nombre de una página, que puede coincidir con el
            # nombre de la métrica y no debe desempatar por sí solo.
            if in_hint_model and strong:
                score += 0.20
                if report_hint and in_hint_report:
                    score += 0.10
            elif in_hint_model:
                score += 0.01  # solo ordena opciones; no rompe un empate (< margen)

            explained = set()
            for value in [*self._metric_names(metric), *self._metric_reports(metric),
                          *self._metric_pages(metric), metric.get("semantic_model")]:
                explained.update(canonical_tokens(value))
            name_tokens = set(canonical_tokens(best_name)) | set(canonical_tokens(primary_label))
            score -= self._unexplained_penalty(business_question, explained)
            score += self._page_bonus(question_tokens, metric, name_tokens)

            # Medidas auxiliares (sin visual donde aparezcan) pierden frente a
            # las que el usuario ve en un tablero, salvo que las nombre exacto.
            if not (metric.get("appearances") or []):
                score -= 0.08 if (label_is_exact and label_weight >= 1.0) else 0.25

            candidates.append({
                "metric": metric,
                "score": round(score, 4),
                "business_score": round(best_name_score, 4),
                "matched_name": best_name,
                "exact_primary_label": label_is_exact,
                "hinted": bool(in_hint_model and (not report_hint or in_hint_report)),
                # Para el desempate: ¿coincidió por su propio nombre o por un
                # alias (título de visual) que comparte con otras medidas?
                "_own_name": self._is_own_name(metric, best_name),
                "_shared_alias": (
                    not self._is_own_name(metric, best_name) and self._is_shared_alias(metric, best_name)
                ),
            })

        if not candidates:
            return not_found([])

        # Informe nombrado explícitamente y la métrica existe allí: solo
        # compiten las métricas de ese informe. Si no existe allí, el
        # nombre del tablero solo orienta (boost) y se avisa.
        hint_ignored = False
        if strong:
            hinted = [item for item in candidates if item["hinted"]
                      and item["business_score"] >= self.min_metric_score]
            if hinted:
                candidates = hinted
            else:
                hint_ignored = True

        # Página nombrada («tablero de triage» -> TRIAGE): un indicador que no
        # aparece en ella pierde frente a los que sí; si ninguno de la página
        # coincide, se marca para decirlo en vez de usar el de otra página.
        page_missing = None
        routed_page = self._routed_page(source_context) if strong and not hint_ignored else None
        if routed_page is not None:
            member_keys = {self._logical_key(member["metric"]) for member in self._page_members(routed_page)}
            valid = [item for item in candidates if item["business_score"] >= self.min_metric_score]
            if member_keys and valid:
                on_page = [item for item in valid if self._logical_key(item["metric"]) in member_keys]
                if on_page:
                    if len(on_page) < len(valid):
                        dropped = [
                            str(item["metric"].get("label")) for item in valid if item not in on_page
                        ]
                        self._note(
                            f"la pregunta nombra la página {routed_page['page']}: se descartan indicadores "
                            f"que no aparecen en ella ({', '.join(dict.fromkeys(dropped[:6]))})"
                        )
                    candidates = on_page
                else:
                    page_missing = routed_page

        def order(item):
            metric = item["metric"]
            return (
                -item["score"], normalize_text(metric.get("semantic_model")),
                normalize_text(metric.get("report")), normalize_text(metric.get("label")),
                str(metric.get("metric_id")),
            )

        candidates.sort(key=order)
        groups = []
        seen = set()
        for item in candidates:
            key = self._logical_key(item["metric"])
            if key in seen:
                continue
            seen.add(key)
            groups.append(item)

        best = groups[0]
        if best["business_score"] < self.min_metric_score:
            return not_found(groups[:candidate_limit])
        tied = [
            item for item in groups
            if best["score"] - item["score"] < self.ambiguity_margin
            and item["business_score"] >= self.min_metric_score
        ]
        visible = self._visible_over_auxiliary(business_question, best, groups)
        if visible:
            best = visible[0]
            groups = [*visible, *[item for item in groups if item not in visible]]
            tied = visible
        if len(tied) > 1:
            # Nombre propio frente a alias compartido, palabra que es parte de
            # un valor de filtro y sustantivo contado («cuántas camas»).
            kept = self._break_metric_tie(business_question, tied)
            if len(kept) == 1:
                best = kept[0]
                groups = [best, *[item for item in groups if item is not best]]
                tied = kept
            else:
                tied = kept + [item for item in tied if item not in kept]
        if len(tied) > 1:
            rest = [item for item in groups if item not in tied]
            limit = None if candidate_limit is None else max(candidate_limit, len(tied))
            result = {"status": "ambiguous", "candidates": (tied + rest)[:limit]}
            if page_missing is not None:
                result["page_hint_ignored"] = page_missing
            return result

        return {
            "status": "resolved", "metric": best["metric"],
            "matched_name": best["matched_name"], "score": best["score"],
            "candidates": groups[:candidate_limit],
            "source_hint_ignored": hint_ignored,
            **({"page_hint_ignored": page_missing} if page_missing is not None else {}),
        }

    def alternative_metrics(self, question, intent_result=None, exclude_ids=(),
                            limit=_SUGGESTION_LIMIT):
        """Indicadores más cercanos a la pregunta que aún no se ofrecieron.

        Se usa con «Ninguna de las anteriores»: primero los candidatos del
        resolutor (en su orden) y luego los que solo comparten alguna palabra
        distintiva con la pregunta. Excluye las métricas ya ofrecidas y sus
        duplicados (misma medida publicada en otro informe).
        """
        intent_result = intent_result or {}
        source_context = self._source_context(question, dashboard=intent_result.get("dashboard"))
        excluded_ids = {str(value) for value in exclude_ids or ()}
        excluded_keys = {
            self._logical_key(metric) for metric in self.metrics
            if str(metric.get("metric_id")) in excluded_ids
        }
        resolution = self._resolve_metric(question, source_context, candidate_limit=None)
        resolved_routing = source_context.get("status") == "resolved"
        strength = source_context.get("routing_strength")
        strong = resolved_routing and strength == "strong"
        model_hint = (
            normalize_text(source_context.get("semantic_model"))
            if resolved_routing and strength in ("strong", "weak") else ""
        )
        suggestions = self._metric_suggestions(
            self._metric_business_question(question, source_context),
            model_hint=model_hint, strong=strong, ratio=0.0, limit=None,
        )
        result, seen = [], set(excluded_keys)
        for item in [*(resolution.get("candidates") or []), *suggestions]:
            metric = item.get("metric") or {}
            key = self._logical_key(metric)
            if str(metric.get("metric_id")) in excluded_ids or key in seen:
                continue
            seen.add(key)
            result.append({key_: value for key_, value in item.items() if not key_.startswith("_")})
        # Variantes por año (CIRUGIAS_2023/2024, Cirugias_Año_Actual) = una opción.
        result = self._collapse_year_variants(result, question)
        return result if limit is None else result[:limit]

    # ---------------- medida auxiliar frente a indicador visible ----------------
    def _visible_over_auxiliary(self, business_question, best, groups):
        """El mejor candidato es una medida auxiliar (no aparece en ningún
        visual: CAMAS_DISPONIBLES de Atenciones, capacidad × días) y otro que sí
        se ve en un tablero, a poca distancia, explica con su nombre y su tabla
        las mismas palabras de la pregunta (CAMAS de la tabla CAMAS
        DISPONIBLES): se prefiere el visible. Devuelve los visibles que
        compiten (uno = se elige; varios = se contrapregunta entre ellos)."""
        if best["metric"].get("appearances"):
            return []
        content = [canonical_token(word) for word in self._question_content_words(business_question)]
        best_vocabulary = self._metric_vocabulary_tokens(best["metric"], with_pages=False)
        needed = [token for token in content if self._explains(token, best_vocabulary)]
        if not needed:
            return []
        rivals = []
        for item in groups:
            if item is best or not item["metric"].get("appearances"):
                continue
            if best["score"] - item["score"] >= 3 * self.ambiguity_margin:
                continue
            if item["business_score"] < self.min_metric_score:
                continue
            vocabulary = self._metric_vocabulary_tokens(item["metric"], with_pages=False)
            if all(self._explains(token, vocabulary) for token in needed):
                rivals.append(item)
        if rivals:
            self._note(
                f"{best['metric'].get('label')} ({best['metric'].get('semantic_model')}) no aparece en ningún "
                "tablero; " + ", ".join(
                    f"{item['metric'].get('label')} ({item['metric'].get('semantic_model')})" for item in rivals
                ) + " sí y su nombre y su tabla explican lo mismo de la pregunta: se prefiere"
                + ("" if len(rivals) == 1 else "n")
            )
        return rivals

    # ---------------- desempate entre indicadores empatados ----------------
    def _is_own_name(self, metric, name):
        """¿`name` es el nombre propio de la medida (etiqueta, medida o la
        referencia «TABLA.medida») y no un título de visual u otro alias?"""
        own = {normalize_text(metric.get("label")), normalize_text(metric.get("measure"))}
        own.discard("")
        if normalize_text(name) in own:
            return True
        text = str(name or "")
        return "." in text and normalize_text(text.rsplit(".", 1)[1]) in own

    def _visual_title_owners(self):
        """{título de visual normalizado: claves lógicas de las medidas que lo muestran}."""
        cached = self.__dict__.get("_visual_title_owners_cache")
        if cached is None:
            cached = {}
            for metric in self._dedupe_metrics(self.metrics):
                if metric.get("validation_status") != "approved":
                    continue
                for appearance in metric.get("appearances") or []:
                    title = normalize_text(appearance.get("visual_title"))
                    if title:
                        cached.setdefault(title, set()).add(self._logical_key(metric))
            self._visual_title_owners_cache = cached
        return cached

    def _is_shared_alias(self, metric, name):
        """Alias que no es exclusivo de la medida: es el nombre de otra medida
        («%OCUPACIÓN» de CamasFiltradas = %OCUPACION) o el título de un visual
        que muestra varias medidas."""
        norm = normalize_text(name)
        if not norm:
            return False
        self._token_weight_index()  # arma self._known_labels
        own = {normalize_text(metric.get("label")), normalize_text(metric.get("measure"))}
        if norm in (self.__dict__.get("_known_labels") or set()) - own:
            return True
        owners = self._visual_title_owners().get(norm) or set()
        return bool(owners - {self._logical_key(metric)})

    def _break_metric_tie(self, business_question, tied):
        """Candidatos empatados que siguen compitiendo tras tres reglas
        genéricas (cada una solo descarta si queda al menos uno):
        1. Nombre propio frente a alias compartido: si uno coincide por el
           nombre de su medida y otro solo por un título de visual/alias que
           comparten varias medidas, se prefiere el nombre propio
           (%OCUPACION frente a CamasFiltradas por el visual «%OCUPACIÓN»).
        2. Palabra que es parte de un valor de filtro: si el nombre de un
           candidato solo coincide con palabras que forman un valor categórico
           documentado de su tabla («hospitalización general» =
           SERVICIO_SOLICITADO), eso es un filtro, no el indicador
           (HOSPITALIZACIÓN de Demanda Insatisfecha).
        3. Sustantivo contado: en «cuántas/cuántos X ...» se prefieren los
           indicadores que cuentan X (nombre, o COUNT/DISTINCTCOUNT sobre una
           tabla o columna que lo nombra)."""
        kept = list(tied)

        own = [item for item in kept if item.get("_own_name")]
        shared = [item for item in kept if not item.get("_own_name") and item.get("_shared_alias")]
        if own and shared:
            top_own = max(float(item.get("business_score") or 0.0) for item in own)
            # Solo si el alias no explica nada más de la pregunta (su tabla o
            # página no nombra otra palabra: «consultas PRIORITARIAS» sigue
            # ofreciendo la medida de la tabla CONSULTAS_PRIORITARIAS).
            content = [canonical_token(word) for word in self._question_content_words(business_question)]

            def explained(item):
                vocabulary = self._metric_vocabulary_tokens(item["metric"])
                return {token for token in content if self._explains(token, vocabulary)}

            own_explained = set().union(*(explained(item) for item in own))
            dropped = [
                item for item in shared
                if float(item.get("business_score") or 0.0) <= top_own + 1e-9
                and explained(item) <= own_explained
            ]
            if dropped:
                kept = [item for item in kept if item not in dropped]
                self._note(
                    ", ".join(
                        f"{item['metric'].get('label')} coincidió solo por «{item.get('matched_name')}»"
                        for item in dropped
                    )
                    + ", un alias que comparte con otras medidas; "
                    + ", ".join(str(item["metric"].get("label")) for item in own)
                    + " coincide por su propio nombre: se prefiere"
                    + (" sin contrapreguntar" if len(kept) == 1 else "")
                )

        if len(kept) > 1:
            in_value = []
            for item in kept:
                value = self._name_inside_value_phrase(business_question, item)
                if value:
                    in_value.append((item, value))
            if in_value and len(in_value) < len(kept):
                dropped = [item for item, _ in in_value]
                kept = [item for item in kept if item not in dropped]
                self._note(
                    "; ".join(
                        f"«{item.get('matched_name')}» de {item['metric'].get('label')} "
                        f"({item['metric'].get('semantic_model')}) es parte del valor «{value}» de su tabla "
                        f"{item['metric'].get('table')}: es un filtro, no el indicador"
                        for item, value in in_value
                    )
                )

        if len(kept) > 1:
            head = self._counted_noun(business_question)
            if head:
                counting = [item for item in kept if self._metric_counts(item["metric"], head)]
                if counting and len(counting) < len(kept):
                    dropped = [item for item in kept if item not in counting]
                    kept = counting
                    self._note(
                        f"la pregunta cuenta «{head}»: "
                        + ", ".join(str(item["metric"].get("label")) for item in counting)
                        + " lo cuenta; "
                        + ", ".join(str(item["metric"].get("label")) for item in dropped)
                        + " no"
                    )
        return kept

    # «cuántas camas», «cuántos de los pacientes»: el sustantivo que se cuenta.
    _COUNTED_NOUN_RE = re.compile(
        r"(?<![a-z0-9])cuant[oa]s\s+(?:(?:de|del)\s+)?(?:(?:los|las|el|la)\s+)?([a-z0-9]+)"
    )
    _COUNT_FUNCTION_RE = re.compile(
        r"\b(?:COUNT|COUNTA|COUNTX|COUNTAX|COUNTROWS|COUNTBLANK|DISTINCTCOUNT|DISTINCTCOUNTNOBLANK)\s*\(",
        re.IGNORECASE,
    )

    def _counted_noun(self, business_question):
        """Sustantivo contado en «cuántos/cuántas X» (canónico) o None. Las
        unidades genéricas («pacientes», «casos», «registros») no distinguen
        indicadores y se ignoran."""
        match = self._COUNTED_NOUN_RE.search(normalize_text(business_question))
        if not match:
            return None
        token = canonical_token(match.group(1))
        content_free, _ = self._weak_token_sets()
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        if len(token) < 4 or token.isdigit() or token in content_free or token in units:
            return None
        return token

    def _metric_counts(self, metric, head):
        """¿El indicador cuenta `head`? Su etiqueta/medida lo nombra o su
        expresión es un conteo (COUNT, DISTINCTCOUNT, COUNTROWS...) sobre una
        tabla o columna que lo nombra (COUNT('CAMAS DISPONIBLES'[HCACODIGO]))."""
        names = set(canonical_tokens(metric.get("label"))) | set(canonical_tokens(metric.get("measure")))
        if self._explains(head, names):
            return True
        expression = " ".join(
            str(value) for value in (
                self._measure_expression(metric.get("semantic_model"), metric), metric.get("model_expression"),
            ) if value
        )
        if not self._COUNT_FUNCTION_RE.search(expression):
            return False
        referenced = set()
        for table, column in re.findall(r"'([^']+)'\s*\[([^\]]+)\]", expression):
            referenced.update(canonical_tokens(table))
            referenced.update(canonical_tokens(column))
        for table, column in re.findall(r"(?<![\w'\]])([A-Za-z_][\w]*)\s*\[([^\]]+)\]", expression):
            referenced.update(canonical_tokens(table))
            referenced.update(canonical_tokens(column))
        for table in re.findall(r"COUNTROWS\s*\(\s*'?([^'(),\[\]]+?)'?\s*\)", expression, re.IGNORECASE):
            referenced.update(canonical_tokens(table))
        return self._explains(head, {token for token in referenced if len(token) >= 3})

    # ---------------- valores categóricos documentados ----------------
    def _documented_values_index(self):
        """{modelo normalizado: [(tabla normalizada o None, columna, [valores])]}
        de data/model_metadata/*/_documented_values.json (valores CASE/IN del
        SQL documentado y literales DAX; tools/local_data). table=None: aplica
        a las columnas con ese nombre en cualquier tabla."""
        cached = self.__dict__.get("_documented_values_cache")
        if cached is not None:
            return cached
        index = {}
        root = self.project_root / "data" / "model_metadata"
        try:
            paths = sorted(root.glob("*/_documented_values.json")) if root.exists() else []
        except OSError:
            paths = []
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            model = normalize_text(payload.get("semantic_model"))
            for item in payload.get("columns") or []:
                if not isinstance(item, dict) or not item.get("column"):
                    continue
                values = [str(value) for value in item.get("values") or [] if value not in (None, "")]
                if values:
                    table = normalize_text(item.get("table")) or None
                    index.setdefault(model, []).append((table, str(item["column"]), values))
        self._documented_values_cache = index
        return index

    def _table_documented_values(self, semantic_model, table):
        """[(columna, [valores])] documentados (o filtros estáticos del PBIR)
        de las columnas de `table` en el modelo."""
        table_norm = normalize_text(table)
        if not table_norm:
            return []
        columns = {}
        for item in self._technical_catalog(semantic_model).get("tables", []) or []:
            if normalize_text(item.get("name")) == table_norm:
                for column in item.get("columns", []) or []:
                    if column.get("name"):
                        columns[normalize_text(column.get("name"))] = column.get("name")
        result = {}
        for doc_table, column, values in self._documented_values_index().get(normalize_text(semantic_model), []):
            column_norm = normalize_text(column)
            if doc_table == table_norm or (doc_table is None and column_norm in columns):
                name = columns.get(column_norm, column)
                result.setdefault(name, [])
                result[name].extend(value for value in values if value not in result[name])
        model_norm = normalize_text(semantic_model)
        for (model, static_table, column), values in self.static_values.items():
            if model == model_norm and static_table == table_norm:
                name = columns.get(column, column)
                result.setdefault(name, [])
                result[name].extend(value for value in values if value not in result[name])
        return list(result.items())

    def _name_inside_value_phrase(self, business_question, item):
        """Valor documentado (de varias palabras, todas en la pregunta) de la
        tabla del candidato que contiene todas las palabras con que coincidió
        su nombre, o None: «hospitalización general» contiene HOSPITALIZACIÓN."""
        metric = item.get("metric") or {}
        name_tokens = [token for token in self._name_key(item.get("matched_name")) if len(token) >= 3]
        if not name_tokens:
            return None
        question_words = normalize_text(business_question).split()
        table = self._metric_fact_table(metric)
        for _, values in self._table_documented_values(metric.get("semantic_model"), table):
            for value in values:
                words = [word for word in _value_words(value) if len(word) >= 3]
                if len(words) < 2 or len(words) <= len(name_tokens):
                    continue
                if not all(_word_in_text(word, words, question_words) for word in words):
                    continue
                if all(any(_tokens_match_loosely(token, canonical_token(word)) for word in words)
                       for token in name_tokens):
                    return value
        return None

    # ---------------- alcance «todo el hospital» ----------------
    # «en el hospital», «de la clínica», «en la institución»: el lugar donde se
    # mide todo; «ocupación general», «el total», «global», «institucional»:
    # sin filtro. Nunca son un filtro, un término «no aplicado» ni motivo para
    # explorar valores de columnas.
    _SCOPE_PLACE_WORDS = {"hospital", "institucion", "clinica"}
    _SCOPE_ADJECTIVE_WORDS = {"general", "global", "total", "institucional", "institucionales"}
    _SCOPE_CONNECTORS = {
        "en", "de", "del", "la", "el", "los", "las", "a", "al", "para", "todo", "toda",
        "nivel", "este", "esta", "nuestro", "nuestra", "y",
    }
    _SCOPE_FOLLOWERS = {"hoy", "ayer", "actualmente", "ahora", "actual", "manana"}
    # Palabras sueltas demasiado genéricas para elegir por sí solas un valor de
    # varias palabras («general» no es HOSPITALIZACIÓN GENERAL).
    _GENERIC_VALUE_WORDS = _SCOPE_ADJECTIVE_WORDS | {
        "otro", "otra", "otros", "otras", "todo", "toda", "todos", "todas", "varios",
        "varias", "normal", "comun", "nuevo", "nueva", "principal",
    }

    def _scope_words(self, question, metric):
        """Palabras de la pregunta que solo dicen «todo el hospital»:
        - lugar («hospital», «institución», «clínica») precedido de en/de/del
          (+ artículo) y no seguido de otra palabra con contenido («hospital
          día» sí puede ser un valor);
        - «general», «global», «total», «institucional» al inicio, tras un
          conector («en general») o tras una palabra que explica el indicador
          («ocupación general»). Tras otra palabra («hospitalización general»)
          son parte de un valor y no se tocan."""
        words = normalize_text(question).split()
        if not words:
            return []
        vocabulary = self._metric_vocabulary_tokens(metric or {}, with_pages=False)
        period_words = set(self._period_words(question))
        stop = {canonical_token(word) for word in STOPWORDS}
        found = []
        for index, word in enumerate(words):
            if word in self._SCOPE_PLACE_WORDS:
                previous = words[index - 1] if index else ""
                following = words[index + 1] if index + 1 < len(words) else ""
                if previous not in self._SCOPE_CONNECTORS:
                    continue
                if following and not (
                    following in self._SCOPE_CONNECTORS or following in self._SCOPE_FOLLOWERS
                    or canonical_token(following) in stop or canonical_token(following) in period_words
                    or following.isdigit() or following in MONTHS
                ):
                    continue
                found.append(word)
            elif word in self._SCOPE_ADJECTIVE_WORDS:
                position = index - 1
                while position >= 0 and words[position] in self._SCOPE_CONNECTORS:
                    position -= 1
                if position < 0 or position < index - 1:
                    found.append(word)
                    continue
                previous = canonical_token(words[position])
                if (
                    previous in stop or _is_request_word(previous)
                    or self._explains(previous, vocabulary)
                ):
                    found.append(word)
        return found

    # ---------------- palabras del tipo de medida ----------------
    # «porcentaje de inasistencia», «tasa de...», «promedio de...», «total
    # de...», «cantidad de...», «número de...»: dicen QUÉ TIPO de dato se pide,
    # no un filtro. Las explica un indicador de ese tipo (%, promedio, conteo
    # o suma) aunque su nombre no las contenga (%INASISTENCIA).
    _MEASURE_TYPE_WORDS = {
        "porcentaje": "percent", "porcentual": "percent", "%": "percent", "tasa": "percent",
        "proporcion": "percent", "promedio": "average", "total": "amount",
        "cantidad": "amount", "numero": "amount", "conteo": "amount", "suma": "amount",
        "sumatoria": "amount", "recuento": "amount",
    }
    _AVERAGE_FUNCTION_RE = re.compile(r"\b(?:AVERAGE|AVERAGEX|AVERAGEA|MEDIAN|MEDIANX)\s*\(", re.IGNORECASE)
    _AMOUNT_FUNCTION_RE = re.compile(
        r"\b(?:SUM|SUMX|COUNT|COUNTA|COUNTX|COUNTAX|COUNTROWS|DISTINCTCOUNT|DISTINCTCOUNTNOBLANK)\s*\(",
        re.IGNORECASE,
    )

    # Nombres de indicadores de cosas aún pendientes: «sin respuesta», «en espera»...
    _PENDING_LABEL_RE = re.compile(
        r"(?<![a-z0-9])(?:sin\s+(?:respuesta|responder|atender|atencion|cerrar|cierre|resolver|asignar|gestion"
        r"|entregar|entrega)|en\s+espera|por\s+(?:responder|atender|entregar|asignar))(?![a-z0-9])"
    )

    def _metric_measure_kinds(self, metric):
        """Tipos de dato que da el indicador: {'percent', 'average', 'amount'}."""
        label = normalize_text(f"{metric.get('label') or ''} {metric.get('measure') or ''}")
        expression = " ".join(
            str(value) for value in (
                metric.get("base_dax_expression") or metric.get("dax_expression"), metric.get("model_expression"),
                self._measure_expression(metric.get("semantic_model"), metric),
            ) if value
        )
        fmt = str(metric.get("format_string") or metric.get("format") or "")
        kinds = set()
        if (
            "%" in label or "%" in fmt or fmt.lower() == "percent"
            or re.search(r"(?<![a-z])(?:porcentaje|tasa|proporcion|indice)(?![a-z])", label)
        ):
            kinds.add("percent")
        elif re.search(r"\bDIVIDE\s*\(", expression, re.IGNORECASE) and not self._AVERAGE_FUNCTION_RE.search(expression):
            kinds.add("percent")
        if "promedio" in label.split() or self._AVERAGE_FUNCTION_RE.search(expression):
            kinds.add("average")
        if not kinds and (
            self._AMOUNT_FUNCTION_RE.search(expression)
            or re.search(r"(?<![a-z])(?:total|cantidad|numero|conteo)(?![a-z])", label)
        ):
            kinds.add("amount")
        return kinds

    def _measure_type_words(self, question, metric):
        """Palabras de la pregunta que solo dicen el tipo de dato y que el
        indicador elegido da («porcentaje» con %INASISTENCIA): no son filtros."""
        kinds = self._metric_measure_kinds(metric or {})
        if not kinds:
            return []
        found = []
        for word in normalize_text(question).split():
            kind = self._MEASURE_TYPE_WORDS.get(word) or self._MEASURE_TYPE_WORDS.get(canonical_token(word))
            if kind and kind in kinds:
                found.append(word)
        return found

    # ---------------- palabra de la tabla que además es un valor ----------------
    def _table_word_filters(self, metric, words, candidates, used_fields, semantic_model):
        """Palabras que solo explica el NOMBRE DE LA TABLA del indicador (no su
        etiqueta, medida ni títulos) y que además son un valor categórico
        documentado de una columna de esa tabla: se filtran en lugar de darlas
        por explicadas. «camas disponibles» con CAMAS (tabla CAMAS
        DISPONIBLES) -> ESTADOS_CAM = DISPONIBLE. Devuelve [(palabra, campo, resuelto)]."""
        table = self._metric_fact_table(metric)
        table_tokens = [token for token in canonical_tokens(table) if len(token) >= 3]
        if not table_tokens or not words:
            return []
        names = [metric.get("label"), metric.get("measure")]
        names.extend(appearance.get("visual_title") for appearance in metric.get("appearances") or [])
        name_tokens = {
            token for name in names if name and "." not in str(name)
            for token in canonical_tokens(name) if len(token) >= 3
        }
        documented = self._table_documented_values(semantic_model, table)
        if not documented:
            return []
        used = set(used_fields)
        found = []
        for word in words:
            token = canonical_token(word)
            if not self._explains(token, table_tokens) or self._explains(token, name_tokens):
                continue
            for column, values in documented:
                key = (normalize_text(table), normalize_text(column))
                if key in used:
                    continue
                # Valor de una sola palabra (sin conectores) que es esta palabra.
                matches = [
                    value for value in values
                    if len(_value_words(value)) == 1 and _tokens_match_loosely(token, canonical_token(_value_words(value)[0]))
                ]
                if len(matches) != 1:
                    continue
                value = matches[0]
                field = next(
                    (item for item in candidates
                     if (normalize_text(item.get("table")), normalize_text(item.get("column"))) == key),
                    None,
                ) or {"table": table, "column": column, "aliases": [column], "kind": "column"}
                # Se confirma con el dominio real si se puede (con su forma escrita).
                domain = self._get_values(semantic_model, field["table"], field["column"])
                if domain:
                    actual = next((item for item in domain if normalize_text(item) == normalize_text(value)), None)
                    if actual is None:
                        continue
                    value = actual
                used.add(key)
                found.append((word, field, {
                    "value": value, "score": 1.0, "phrase": word,
                    "tokens": {token, *canonical_tokens(value)},
                }))
                break
        return found

    def _generic_partial_value(self, span_tokens, value_tokens, question):
        """¿El calificativo es solo una palabra genérica («general») que cubre
        parte de un valor de varias palabras cuyo resto no está en la pregunta?"""
        generic = {canonical_token(word) for word in self._GENERIC_VALUE_WORDS}
        if not span_tokens or not all(token in generic for token in span_tokens):
            return False
        rest = [
            token for token in value_tokens
            if not any(_tokens_match_loosely(token, other) for other in span_tokens)
        ]
        if not rest:
            return False
        question_tokens = canonical_tokens(question)
        return not all(
            any(_tokens_match_loosely(token, other) for other in question_tokens) for token in rest
        )

    # ---------------- dimension index ----------------
    def _physical_column(self, field):
        if field.get("column"):
            return field.get("column")
        if field.get("kind") == "hierarchy_level":
            parts = [part for part in str(field.get("query_ref") or "").split(".") if part]
            if len(parts) >= 2:
                return parts[1]
        return None

    def _field_aliases(self, field):
        values = [
            field.get("display_name"), field.get("native_query_ref"),
            field.get("column"), field.get("level"), field.get("query_ref"),
        ]
        aliases = _unique_strings(values)
        normalized_aliases = {normalize_text(alias) for alias in aliases}
        # Sufijos técnicos (TURNO_OK, SERVICIO_ID): «turno» debe encontrar TURNO_OK.
        for alias in list(normalized_aliases):
            parts = alias.split()
            while len(parts) >= 2 and parts[-1] in TECHNICAL_SUFFIXES:
                parts = parts[:-1]
                aliases.append(" ".join(parts))
        normalized_aliases = {normalize_text(alias) for alias in aliases}
        for synonyms in DIMENSION_SYNONYMS.values():
            # Por palabra completa: OPORTUNIDAD no contiene «unidad».
            if any(
                re.search(r"(?<![a-z0-9])" + re.escape(synonym) + r"(?![a-z0-9])", alias)
                for alias in normalized_aliases for synonym in synonyms
            ):
                aliases.extend(sorted(synonyms))
        return _unique_strings(aliases)

    def _build_dimension_index(self):
        fields = []
        for report in self.reports:
            report_name = report.get("report") or report.get("semantic_model")
            semantic_model = report.get("semantic_model")
            source_group = report.get("source_group")
            for page in report.get("pages", []) or []:
                page_name = page.get("page_display_name") or page.get("page_name")
                for visual in page.get("visuals", []) or []:
                    for field in visual.get("fields", []) or []:
                        if field.get("kind") not in ("column", "hierarchy_level"):
                            continue
                        table = field.get("table")
                        column = self._physical_column(field)
                        if not table or not column:
                            continue
                        fields.append({
                            "semantic_model": semantic_model,
                            "report": report_name,
                            "source_group": source_group,
                            "page": page_name,
                            "visual_id": visual.get("visual_id"),
                            "visual_type": visual.get("visual_type"),
                            "role": field.get("role"),
                            "kind": field.get("kind"),
                            "table": table,
                            "column": column,
                            "level": field.get("level"),
                            "query_ref": field.get("query_ref"),
                            "display_name": field.get("display_name"),
                            "native_query_ref": field.get("native_query_ref"),
                            "aliases": self._field_aliases(field),
                        })
        # Campo sin nombre de negocio (la dona «HSUNOMBRE» de DETALLE OCUPACIÓN):
        # hereda los nombres con que otros visuales del modelo muestran esa
        # columna (HSUNOMBRE -> «SERVICIO»). Funciona con catálogos ya construidos.
        self._business_names_index = self._build_business_names_index(fields)
        for field in fields:
            names = [field.get("display_name"), field.get("native_query_ref")]
            if any(self._business_column_name(name, field.get("column")) for name in names):
                continue
            for name in self._column_business_names(
                field.get("semantic_model"), field.get("column"), field.get("table"),
            ):
                field["aliases"] = _unique_strings([*field["aliases"], *self._field_aliases({"display_name": name})])
        return fields

    @staticmethod
    def _business_column_name(name, column):
        """Nombre de negocio de una columna en un visual («ASEGURADORA» para
        TERNOMCOM), normalizado y sin dígitos finales («SERVICIO1»); None si es
        el nombre técnico, una agregación («Recuento de X», «Sum(T.C)») o vacío."""
        text = re.sub(r"\s*\d+$", "", str(name or "")).strip()
        norm = normalize_text(text)
        if (
            not norm or len(norm) < 3 or len(norm.split()) > 3 or "(" in text or "." in text
            or norm == normalize_text(column)
            or re.match(r"^(?:recuento|conteo|count|suma|sum|promedio|average|total)\b", norm)
        ):
            return None
        return text

    def _build_business_names_index(self, fields):
        index = {}
        for field in fields:
            key = (normalize_text(field.get("semantic_model")), normalize_text(field.get("column")))
            for name in (field.get("display_name"), field.get("native_query_ref")):
                business = self._business_column_name(name, field.get("column"))
                item = (normalize_text(field.get("table")), business)
                if business and item not in index.setdefault(key, []):
                    index[key].append(item)
                # Por nombre técnico en cualquier modelo (misma base de datos).
                if business and business not in index.setdefault(("*", key[1]), []):
                    index[("*", key[1])].append(business)
        return index

    @staticmethod
    def _technical_code_column(column):
        """Nombre técnico de una sola palabra que no es una palabra de negocio
        ni de tiempo (TERNOMCOM, HSUNOMBRE, HCACODIGO, GEEDESCRI): significa lo
        mismo en todas las tablas del modelo. FECHA o ESTADO no (cada tabla le
        da su propio sentido: «FECHA INGRESO», «ESTADO TRÁMITE»)."""
        norm = normalize_text(column)
        if not norm or " " in norm or len(norm) < 6 or norm in TEMPORAL_WORDS:
            return False
        return not any(norm in synonyms for synonyms in DIMENSION_SYNONYMS.values())

    def _column_business_names(self, semantic_model, column, table=None):
        """Nombres de negocio con que los visuales del modelo muestran una
        columna: los de la misma tabla y, si es un código técnico, los de
        cualquier tabla (TERNOMCOM -> «ASEGURADOR», «ASEGURADORA»; HSUNOMBRE
        -> «SERVICIO»). Sirve de alias en tiempo de ejecución sin reconstruir
        los catálogos (el catálogo visual ya guarda displayName/nativeQueryRef
        de cada columna)."""
        index = self.__dict__.get("_business_names_index")
        if index is None:
            index = self._business_names_index = self._build_business_names_index(self.dimension_fields or [])
        anywhere = self._technical_code_column(column)
        table = normalize_text(table)
        names = _unique_strings(
            name for owner, name in index.get((normalize_text(semantic_model), normalize_text(column)), [])
            if anywhere or not table or owner == table
        )
        if not names and anywhere:
            # Código técnico que este modelo nunca renombra (GEEDESCRI de
            # REFERENCIA): los nombres que le dan los visuales de otros modelos
            # («ESPECIALIDAD» en BRIEFING), si son pocos y coinciden.
            others = index.get(("*", normalize_text(column)), [])
            if 0 < len({normalize_text(name) for name in others}) <= 2:
                names = _unique_strings(others)
        return names

    def _iter_filters(self, value):
        if isinstance(value, list):
            for item in value:
                yield from self._iter_filters(item)
        elif isinstance(value, dict):
            if "field" in value and isinstance(value.get("field"), dict):
                yield value
            for item in value.values():
                yield from self._iter_filters(item)

    def _build_static_value_index(self):
        result = {}
        for report in self.reports:
            semantic_model = report.get("semantic_model")
            for page in report.get("pages", []) or []:
                for filter_item in self._iter_filters(page.get("filters", {})):
                    field = filter_item.get("field", {})
                    table = field.get("table")
                    column = field.get("column")
                    if not table or not column:
                        continue
                    key = (normalize_text(semantic_model), normalize_text(table), normalize_text(column))
                    result.setdefault(key, [])
                    for value in filter_item.get("values", []) or []:
                        if value is not None and str(value) not in result[key]:
                            result[key].append(str(value))
        return result

    def _relevant_dimensions(self, metric):
        semantic_model = metric.get("semantic_model")
        reports = {normalize_text(value) for value in self._metric_reports(metric)}
        pages = {normalize_text(value) for value in self._metric_pages(metric)}
        visual_ids = self._metric_visual_ids(metric)
        candidates = {}

        for field in self.dimension_fields:
            if normalize_text(field.get("semantic_model")) != normalize_text(semantic_model):
                continue
            if reports and normalize_text(field.get("report")) not in reports:
                continue

            score = 10
            if str(field.get("visual_id")) in visual_ids:
                score += 110
            if normalize_text(field.get("page")) in pages:
                score += 65
            if normalize_text(field.get("visual_type")) == "slicer":
                score += 35
            if normalize_text(field.get("role")) in {
                "category", "group", "rows", "legend", "series", "values"
            }:
                score += 15

            key = (
                normalize_text(field.get("table")),
                normalize_text(field.get("column")),
                normalize_text(field.get("level")),
            )
            item = {**field, "relevance_score": score}
            if key not in candidates or score > candidates[key]["relevance_score"]:
                candidates[key] = item

        values = list(candidates.values())
        values.sort(key=lambda item: item["relevance_score"], reverse=True)
        return values

    # ---------------- dimensiones del catálogo técnico ----------------
    _CALENDAR_TABLE_RE = re.compile(
        r"^(?:calendario|calendar|fecha|fechas|dates?|dim fecha|medidas|measures|"
        r"localdatetable.*|datetabletemplate.*)$"
    )
    # Columnas de personas/identificadores: nunca se ofrecen como dimensión
    # técnica (privacidad y ruido).
    _PRIVATE_COLUMN_PARTS = (
        "nombre", "apell", "docume", "cedula", "identif", "pacien", "telefon",
        "direcc", "correo", "email", "rownumber", "ternom", "ternum", "numdoc",
    )

    def _technical_catalog(self, semantic_model):
        """Catálogo técnico (tablas, columnas, relaciones) del modelo, con caché."""
        key = normalize_text(semantic_model)
        cache = self.__dict__.setdefault("_technical_catalog_cache", {})
        if key in cache:
            return cache[key]
        try:
            path = self.source_router.catalog_path_for_model(semantic_model, required=False)
            catalog = self._load_json(path, {}) if path else {}
        except Exception:
            catalog = {}
        cache[key] = catalog if isinstance(catalog, dict) else {}
        return cache[key]

    def _related_tables(self, semantic_model, table):
        """La tabla y las que la filtran (lado «uno» de sus relaciones activas)."""
        related = {normalize_text(table)}
        relations = [
            (normalize_text(relation.get("FromTable")), normalize_text(relation.get("ToTable")))
            for relation in self._technical_catalog(semantic_model).get("relationships", []) or []
            if relation.get("IsActive") is not False
        ]
        for _ in range(2):  # dimensión y dimensión de la dimensión (copo de nieve)
            related |= {target for source, target in relations if source in related and target}
        return related

    def _technical_field_aliases(self, column):
        """Alias de una columna técnica: su nombre y, solo si la PRIMERA palabra
        es un concepto de dimensión («CLASIFICACION_TRIAGE»), sus sinónimos
        («OID_TRIAGE» no hereda «clasificación» por contener «triage»)."""
        name = normalize_text(column)
        aliases = [column, name]
        parts = name.split()
        while len(parts) >= 2 and parts[-1] in TECHNICAL_SUFFIXES:
            parts = parts[:-1]
            aliases.append(" ".join(parts))
        head = parts[0] if parts else ""
        for synonyms in DIMENSION_SYNONYMS.values():
            if head in synonyms or name in synonyms:
                aliases.extend(sorted(synonyms))
        return _unique_strings(aliases)

    def _measure_expression(self, semantic_model, metric):
        """Expresión DAX de la métrica (la del catálogo técnico si es una medida)."""
        names = {normalize_text(metric.get("measure")), normalize_text(metric.get("label"))}
        for table in self._technical_catalog(semantic_model).get("tables", []) or []:
            for measure in table.get("measures", []) or []:
                if normalize_text(measure.get("name")) in names and measure.get("expression"):
                    return str(measure.get("expression"))
        return str(metric.get("dax_expression") or "")

    @staticmethod
    def _expression_uses_table(expression, table):
        return bool(re.search(
            r"(?<![\w'])'?" + re.escape(str(table)) + r"'?\s*[\[\)]", str(expression or ""),
        ))

    def _metric_fact_table(self, metric):
        """Tabla sobre la que se calcula el indicador: la suya o, si está
        guardado en el calendario/tabla de medidas, la que nombra su expresión."""
        table = metric.get("table")
        if table and self._CALENDAR_TABLE_RE.match(normalize_text(table)):
            cache = self.__dict__.setdefault("_fact_table_cache", {})
            key = (self._logical_key(metric), normalize_text(metric.get("label")))
            if key not in cache:
                cache[key] = self._expression_fact_table(metric.get("semantic_model"), metric) or table
            return cache[key]
        return table

    def _expression_fact_table(self, semantic_model, metric):
        """Única tabla (que no sea calendario/medidas) que la expresión de la
        medida referencia como 'TABLA'[columna] o TABLA[columna], o None."""
        used = self._expression_tables(semantic_model, metric)
        return next(iter(used)) if len(used) == 1 else None

    def _expression_tables(self, semantic_model, metric):
        """Tablas (que no sean calendario/medidas) que nombra la expresión de la medida."""
        expression = str(self._measure_expression(semantic_model, metric) or "")
        if not expression:
            return set()
        tables = {
            table.get("name") for table in self._technical_catalog(semantic_model).get("tables", []) or []
            if table.get("name") and not self._CALENDAR_TABLE_RE.match(normalize_text(table.get("name")))
        }
        used = {
            name for name in tables
            if re.search(r"(?:'" + re.escape(name) + r"'|(?<![\w'])" + re.escape(name) + r")\s*\[", expression,
                         re.IGNORECASE)
            or re.search(r"(?:COUNTROWS|RELATEDTABLE|VALUES|ALL|FILTER)\s*\(\s*'?" + re.escape(name) + r"'?\s*[),]",
                         expression, re.IGNORECASE)
        }
        return used

    def _with_technical_dimensions(self, metric, candidates):
        """Dimensiones del catálogo técnico para métricas SIN visual.

        Una medida que no aparece en ningún visual (TOTAL_TRIAGES) no tiene
        campos visuales propios. Se agregan las columnas de su tabla
        (CLASIFICACION_TRIAGE, MENORES, FECHA...). Si la medida se calcula
        sobre esa tabla, sus columnas van primero y los campos visuales de
        tablas que no la filtran pasan al final (un filtro allí no la
        afectaría); si no, solo se agregan al final como respaldo. Las
        métricas con visual no cambian.
        """
        if metric.get("appearances"):
            return candidates
        semantic_model = metric.get("semantic_model")
        table_name = metric.get("table")
        if table_name and self._CALENDAR_TABLE_RE.match(normalize_text(table_name)):
            # Medida guardada en el calendario o en una tabla de medidas
            # (TOTAL_CIRUGIAS = COUNT(CIRUGIAS[CEDULA])): su tabla real es la
            # única tabla de hechos que nombra su expresión.
            table_name = self._expression_fact_table(semantic_model, metric)
        if not table_name or self._CALENDAR_TABLE_RE.match(normalize_text(table_name)):
            return candidates
        catalog = self._technical_catalog(semantic_model)
        table = next(
            (item for item in catalog.get("tables", []) or []
             if normalize_text(item.get("name")) == normalize_text(table_name)),
            None,
        )
        if not table or not table.get("columns"):
            return candidates
        own_table = self._expression_uses_table(
            self._measure_expression(semantic_model, metric), table.get("name"),
        )
        related = self._related_tables(semantic_model, table.get("name"))
        adjusted = []
        for field in candidates:
            if own_table and normalize_text(field.get("table")) not in related:
                field = {**field, "relevance_score": field.get("relevance_score", 0) - 100,
                         "unrelated_table": True}
            adjusted.append(field)
        seen = {(normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in adjusted}
        technical = []
        for column in table.get("columns", []) or []:
            name = column.get("name")
            lowered = str(name or "").lower()
            if not name or any(part in lowered for part in self._PRIVATE_COLUMN_PARTS):
                continue
            column_type = self._classify_data_type(column.get("data_type"))
            words = set(normalize_text(name).split())
            if column_type == "number" and not words & TEMPORAL_WORDS:
                continue
            key = (normalize_text(table.get("name")), normalize_text(name))
            if key in seen:
                continue
            seen.add(key)
            aliases = self._technical_column_aliases(semantic_model, table.get("name"), name)
            if column_type == "date" and not words & TEMPORAL_WORDS:
                aliases.append("fecha")  # «FechaParto»: es la fecha de la tabla
            technical.append({
                "semantic_model": semantic_model, "report": None, "source_group": None,
                "page": None, "visual_id": None, "visual_type": "technical_catalog",
                "role": None, "kind": "column", "table": table.get("name"), "column": name,
                "level": None, "query_ref": f"{table.get('name')}.{name}",
                "aliases": aliases,
                "relevance_score": 120 if own_table else 5, "technical": True,
            })
        result = adjusted + technical
        result.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
        return result

    def _group_label(self, field):
        """Encabezado de la agrupación: su primer alias o, si es el nombre
        técnico (GEEDESCRI, TERNOMCOM), el nombre de negocio de los visuales."""
        label = (field.get("aliases") or [field.get("column")])[0]
        if normalize_text(label) == normalize_text(field.get("column")):
            names = self._column_business_names(field.get("semantic_model"), field.get("column"), field.get("table"))
            if names:
                return names[0]
        return label

    def _technical_column_aliases(self, semantic_model, table, column):
        """Alias de una columna del catálogo técnico: su nombre, sus sinónimos
        y los nombres de negocio con que la muestran los visuales del modelo."""
        aliases = self._technical_field_aliases(column)
        for name in self._column_business_names(semantic_model, column, table):
            aliases.extend(self._field_aliases({"display_name": name}))
        return _unique_strings(aliases)

    # ---------------- relación de una columna con el indicador ----------------
    # Una columna solo sirve para agrupar, ordenar o filtrar un indicador si su
    # tabla lo filtra. Regla (`_dimension_relation`):
    # - «own»: la tabla del campo es la tabla de hechos del indicador. Siempre vale.
    # - «related»: la expresión del indicador nombra esa tabla, o las relaciones
    #   activas del modelo la conectan con la tabla de hechos (dimensión y
    #   dimensión de la dimensión, como `_related_tables`).
    # - «unrelated»: (a) el modelo declara sus relaciones (catálogo técnico con
    #   tablas y la clave «relationships», aunque la lista esté vacía:
    #   INFO.VIEW.RELATIONSHIPS las devuelve todas; BRIEFING no tiene ninguna y
    #   sus tablas son independientes) y ninguna conecta esa tabla; o (b) sin
    #   relaciones declaradas, la tabla de hechos tiene su PROPIA columna con el
    #   mismo significado (mismo alias de negocio, p. ej. ASEGURADOR frente al
    #   TERNOMCOM «ASEGURADOR» de otra tabla, o una fecha propia frente a la
    #   fecha de otra tabla): se prefiere la propia. Un calendario/tabla de
    #   fechas nunca se descarta en este caso (se supone conectado).
    # - «unknown»: falta información (tabla de hechos desconocida o de medidas,
    #   expresión que no la nombra, sin relaciones ni columna equivalente): el
    #   campo se conserva como antes, para no dejar sin dimensiones a los
    #   modelos sin metadata de relaciones.
    def _has_relationship_metadata(self, semantic_model):
        catalog = self._technical_catalog(semantic_model)
        return bool(catalog.get("tables")) and "relationships" in catalog

    def _fact_table_entry(self, metric):
        """Tabla de hechos del indicador en el catálogo técnico (o None)."""
        table_name = self._metric_fact_table(metric)
        if not table_name or self._CALENDAR_TABLE_RE.match(normalize_text(table_name)):
            return None
        return next(
            (item for item in self._technical_catalog(metric.get("semantic_model")).get("tables", []) or []
             if normalize_text(item.get("name")) == normalize_text(table_name)),
            None,
        )

    def _own_column_profiles(self, metric):
        """[(alias normalizados, es_temporal)] de las columnas de la tabla de
        hechos del indicador: las del catálogo técnico y las de los visuales."""
        model = metric.get("semantic_model")
        table_name = normalize_text(self._metric_fact_table(metric))
        profiles = []
        entry = self._fact_table_entry(metric)
        for column in (entry or {}).get("columns", []) or []:
            name = column.get("name")
            if not name:
                continue
            aliases = {normalize_text(a) for a in self._technical_column_aliases(model, entry.get("name"), name)}
            temporal = (
                self._classify_data_type(column.get("data_type")) == "date"
                or bool(set(normalize_text(name).split()) & TEMPORAL_WORDS)
            )
            profiles.append((aliases - {""}, temporal))
        for field in self.dimension_fields or []:
            if (
                normalize_text(field.get("semantic_model")) == normalize_text(model)
                and normalize_text(field.get("table")) == table_name
            ):
                aliases = {normalize_text(a) for a in field.get("aliases") or []}
                profiles.append((aliases - {""}, self._is_temporal_field(field)))
        return profiles

    def _own_equivalent_column(self, metric, field):
        """¿La tabla del indicador tiene su propia columna con el significado
        de `field` (otra tabla)? Fechas con fechas; el resto por alias común."""
        temporal = self._is_temporal_field(field)
        aliases = {normalize_text(alias) for alias in field.get("aliases") or []} - {""}
        aliases.discard(normalize_text(field.get("table")))
        for own_aliases, own_temporal in self._own_column_profiles(metric):
            if temporal or own_temporal:
                if temporal and own_temporal:
                    return True
                continue
            if aliases & own_aliases:
                return True
        return False

    def _dimension_relation(self, metric, field):
        """«own» | «related» | «unrelated» | «unknown» (ver la regla arriba)."""
        model = metric.get("semantic_model")
        table = self._metric_fact_table(metric)
        field_table = normalize_text(field.get("table"))
        if not table or not field_table or self._CALENDAR_TABLE_RE.match(normalize_text(table)):
            return "unknown"
        if field_table == normalize_text(table):
            return "own"
        cache = self.__dict__.setdefault("_dimension_relation_cache", {})
        metric_key = (self._logical_key(metric), normalize_text(metric.get("label")))
        if metric_key not in cache:
            # Por indicador: tablas de su expresión y, si el modelo declara sus
            # relaciones, las que filtran su tabla (None = sin esa metadata o
            # expresión que no nombra la tabla: se decide por columna).
            if len(cache) > 5000:
                cache.clear()
            used = {normalize_text(name) for name in self._expression_tables(model, metric)}
            related = None
            if self._has_relationship_metadata(model):
                if self._expression_uses_table(self._measure_expression(model, metric), table):
                    related = set()
                    for name in {normalize_text(table)} | used:
                        related |= self._related_tables(model, name)
                else:
                    related = "unknown"
            cache[metric_key] = {"used": used, "related": related, "columns": {}}
        info = cache[metric_key]
        if field_table in info["used"]:
            return "related"
        if info["related"] == "unknown":
            return "unknown"
        if info["related"] is not None:
            return "related" if field_table in info["related"] else "unrelated"
        # Sin relaciones declaradas, un calendario (Calendario[AÑO]) se supone
        # conectado: es la forma habitual de filtrar por periodo.
        if self._CALENDAR_TABLE_RE.match(field_table):
            return "unknown"
        column_key = (field_table, normalize_text(field.get("column")))
        if column_key not in info["columns"]:
            info["columns"][column_key] = (
                "unrelated" if self._own_equivalent_column(metric, field) else "unknown"
            )
        return info["columns"][column_key]

    def _own_table_fallback_fields(self, metric, existing):
        """Columnas de la tabla de hechos de un indicador CON visuales que no
        están entre sus campos visuales (ASEGURADOR de CONSULTAS PRIORITARIAS
        solo aparece agregado): respaldo para «por X», rankings, filtros
        explícitos. Van al final (relevancia baja), marcadas `own_fallback`;
        los valores implícitos no las recorren. Las fechas no se agregan: si
        los visuales del indicador no usan ninguna, la tabla es de estado
        actual para el tablero (FechaSalida de PACIENTES X ASEGURADORA no es
        la fecha de un periodo; ver `_snapshot_table`)."""
        entry = self._fact_table_entry(metric)
        if not entry:
            return []
        model = metric.get("semantic_model")
        seen = {(normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in existing}
        # Después de las propias, las de las tablas que la filtran por una
        # relación activa declarada (REFERENCIA[GEEDESCRI] filtra
        # DETALLE_RECEPCIONES): «solicitudes por especialidad» se puede
        # desglosar aunque ningún visual muestre esa columna. Sin metadata de
        # relaciones no se supone ninguna.
        tables = [(entry, 8)]
        if self._has_relationship_metadata(model):
            own = normalize_text(entry.get("name"))
            related = self._related_tables(model, entry.get("name")) - {own}
            for item in self._technical_catalog(model).get("tables", []) or []:
                name = normalize_text(item.get("name"))
                if name in related and not self._CALENDAR_TABLE_RE.match(name.replace(" ", "")):
                    tables.append((item, 6))
        result = []
        for table, relevance in tables:
            for column in table.get("columns", []) or []:
                name = column.get("name")
                lowered = str(name or "").lower()
                if not name or any(part in lowered for part in self._PRIVATE_COLUMN_PARTS):
                    continue
                column_type = self._classify_data_type(column.get("data_type"))
                words = set(normalize_text(name).split())
                if column_type in ("number", "date") or words & TEMPORAL_WORDS:
                    continue
                key = (normalize_text(table.get("name")), normalize_text(name))
                if key in seen:
                    continue
                seen.add(key)
                aliases = self._technical_column_aliases(model, table.get("name"), name)
                result.append({
                    "semantic_model": model, "report": None, "source_group": None,
                    "page": None, "visual_id": None, "visual_type": "technical_catalog",
                    "role": None, "kind": "column", "table": table.get("name"), "column": name,
                    "level": None, "query_ref": f"{table.get('name')}.{name}",
                    "aliases": aliases, "relevance_score": relevance, "own_fallback": True,
                })
        return result

    def _metric_dimensions(self, metric, dropped=None):
        """Dimensiones candidatas del indicador para agrupar, ordenar, filtrar
        y elegir la fecha del periodo: las de sus visuales o del catálogo
        técnico (`_with_technical_dimensions`) SIN las de tablas que no lo
        filtran («unrelated»: un SUMMARIZECOLUMNS por EGRESOS_POR_SERVICIO
        [TERNOMCOM] repite el total de CONSULTAS PRIORITARIAS en cada fila) y,
        si tiene visuales, con las columnas de su propia tabla como respaldo.
        `dropped` (lista) recibe los campos descartados. Con caché por
        indicador (los catálogos no cambian durante la vida del planificador)."""
        cache = self.__dict__.setdefault("_metric_dimensions_cache", {})
        key = (self._logical_key(metric), normalize_text(metric.get("label")),
               tuple(sorted(self._metric_visual_ids(metric))), tuple(self._metric_pages(metric)),
               tuple(self._metric_reports(metric)))
        if key not in cache:
            if len(cache) > 2000:
                cache.clear()
            candidates = self._with_technical_dimensions(metric, self._relevant_dimensions(metric))
            kept, unrelated = [], []
            for field in candidates:
                (unrelated if self._dimension_relation(metric, field) == "unrelated" else kept).append(field)
            if metric.get("appearances"):
                kept.extend(self._own_table_fallback_fields(metric, kept))
            cache[key] = (kept, unrelated)
        kept, unrelated = cache[key]
        if dropped is not None:
            dropped.extend(unrelated)
        return list(kept)

    def _period_in_metric_note(self, question, temporal, metric, metric_result):
        """Nota visible cuando el periodo pedido forma parte del nombre del
        indicador («triages en 2025» -> TRIAGES_2025): no se agrega otro
        filtro de fecha, pero la respuesta lo dice en vez de callarlo."""
        if temporal.get("period"):
            return None
        period = self._period_parser().parse(normalize_text(question))
        if not period:
            return None
        phrase = normalize_text(period.get("phrase"))
        names = [metric_result.get("matched_name"), metric.get("label"), metric.get("measure")]
        name = next((n for n in names if n and _exact_phrase(normalize_text(n), phrase)), None)
        if not name:
            return None
        return (
            f"El periodo «{_original_phrase(question, period.get('phrase'))}» ya está incluido en "
            f"el indicador {name}; no se aplicó otro filtro de fecha."
        )

    @staticmethod
    def _technical_columns_used(candidates, filters, group_by):
        """«TABLA[COLUMNA]» del catálogo técnico usadas en filtros o agrupación
        (para el razonamiento: la métrica no tenía visual propio)."""
        technical = {
            (normalize_text(field.get("table")), normalize_text(field.get("column"))): field
            for field in candidates if field.get("technical")
        }
        used = []
        for item in [*(filters or []), *(group_by or [])]:
            key = (normalize_text(item.get("table")), normalize_text(item.get("column")))
            field = technical.get(key)
            label = f"{field['table']}[{field['column']}]" if field else None
            if label and label not in used:
                used.append(label)
        return used

    # ---------------- tablero / página nombrado ----------------
    def _models_with_metrics(self):
        if getattr(self, "_metric_models", None) is None:
            self._metric_models = {
                normalize_text(metric.get("semantic_model")) for metric in self.metrics
                if metric.get("validation_status") == "approved" and metric.get("semantic_model")
            }
        return self._metric_models

    def _refine_board_context(self, context):
        """Nombre de tablero presente en varios modelos («tablero de
        cirugías»): si solo uno tiene indicadores, se fija ese (routing fuerte)."""
        if not isinstance(context, dict):
            return context
        models = context.get("board_mention_models") or []
        if len(models) < 2:
            return context
        if context.get("status") == "resolved" and context.get("routing_strength") == "strong":
            return context
        mentions = context.get("board_mentions") or []
        with_metrics = [m for m in models if normalize_text(m) in self._models_with_metrics()]
        why = "el único con indicadores"
        if len(with_metrics) > 1:
            # Desempate por la forma escrita: «tablero de triage» es TRIAGE
            # antes que TRIAGES (solo coincide en singular/plural).
            exact_models = {
                normalize_text(item.get("semantic_model"))
                for mention in mentions for item in mention.get("contexts") or []
                if item.get("exact")
            }
            exact = [m for m in with_metrics if normalize_text(m) in exact_models]
            if len(exact) == 1:
                with_metrics = exact
                why = "el único con indicadores cuyo nombre coincide tal como se escribió"
        board_context = getattr(self.source_router, "board_context", None)
        if len(with_metrics) != 1 or not callable(board_context):
            return context
        target = normalize_text(with_metrics[0])
        entry = next(
            (item for mention in mentions for item in mention.get("contexts") or []
             if normalize_text(item.get("semantic_model")) == target),
            None,
        )
        if entry is None:
            return context
        refined = board_context(entry, mentions=mentions, candidates=context.get("candidates"))
        refined["board_note"] = (
            f"«{entry.get('name')}» existe en {len(models)} modelos; se usa "
            f"{with_metrics[0]}: {why}"
        )
        return refined

    def _strip_board_mentions(self, text, source_context):
        """Quita «tablero/página de X» del texto donde se buscan agrupaciones y
        filtros; devuelve (texto, palabras canónicas del nombre). Esas
        palabras nombran el tablero: no son valores de filtro («tablero de
        triage» no es CLASIFICACIÓN = TRIAGE III)."""
        mentions = (source_context or {}).get("board_mentions") or []
        text = normalize_text(text)
        tokens = set()
        explicit = re.search(r"(?<![a-z0-9])(?:tablero|informe|reporte|dashboard|pagina)(?![a-z0-9])", text)
        dimension_words = {
            canonical_token(word) for synonyms in DIMENSION_SYNONYMS.values() for word in synonyms
        }
        for mention in mentions:
            phrase = normalize_text(mention.get("phrase"))
            # «por eps» agrupa por aseguradora: no nombra el TABLERO EPS. Una
            # mención que solo es una palabra de dimensión cuenta como tablero
            # solo si la pregunta dice «tablero/informe».
            if phrase and not explicit and (
                re.search(r"(?<![a-z0-9])(?:por|segun)\s+(?:(?:el|la|los|las)\s+)?" + re.escape(phrase)
                          + r"(?![a-z0-9])", text)
                or all(token in dimension_words for token in canonical_tokens(phrase))
            ):
                continue
            if phrase:
                pattern = r"(?<![a-z0-9])(?:(?:en|de|del|desde|para)\s+(?:(?:el|la|los|las)\s+)?)?" \
                          + re.escape(phrase) + r"(?![a-z0-9])"
                text = re.sub(pattern, " ", text)
            tokens.update(canonical_tokens(mention.get("name")))
        return re.sub(r"\s+", " ", text).strip(), tokens

    def _dimension_match_score(self, text, field):
        return max((_phrase_score(text, alias) for alias in field.get("aliases", [])), default=0.0)

    def _best_dimension(self, text, candidates, exclude_temporal=False):
        scored = []
        for field in candidates:
            if exclude_temporal and self._is_temporal_field(field):
                continue
            score = self._dimension_match_score(text, field)
            if score <= 0:
                continue
            score += min(0.12, field.get("relevance_score", 0) / 1000.0)
            scored.append((score, field))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1] if scored else None

    # ---------------- actual dimension values ----------------
    def _table_ref(self, table):
        return "'" + str(table).replace("'", "''") + "'"

    def _column_ref(self, column):
        return "[" + str(column).replace("]", "]]" ) + "]"

    def _domain_cache(self):
        """Caché de dominios compartida del proveedor (TTL, lote y presupuesto
        por turno; ver src/providers/domain_cache.py)."""
        return domain_cache_for(self.powerbi_provider)

    def _get_values(self, semantic_model, table, column, essential=False, limit=None):
        """Valores de la columna: los estáticos del PBIR y luego los de Power BI
        (VALUES, desde la caché de dominios). None si Power BI no respondió.
        `essential`: filtro pedido con su columna o periodo (sin límite de
        consultas de exploración del turno ni de tiempo). `limit`: tope TOPN
        (por defecto el histórico, 2500); uno menor basta cuando solo importa
        si el dominio pasa de cierto tamaño (calificativos aproximados)."""
        key = (semantic_model, table, column)
        cache = self._domain_cache()
        domain = cache.get(semantic_model, table, column, essential=essential, limit=limit)
        if domain is None:
            error = cache.errors.get(cache.key(semantic_model, table, column))
            self.domain_errors[key] = error or {
                "status": "skipped", "error_type": None,
                "message": "consulta de valores omitida (límite de consultas de exploración del turno)",
            }
            # No afirmar que un filtro fue verificado si XMLA falló,
            # aunque el PBIR tenga valores estáticos potencialmente antiguos.
            # El siguiente intento consultará de nuevo el dominio.
            return None

        self.domain_errors.pop(key, None)
        memo = self.value_cache.get(key)
        if memo is not None and memo[0] is domain:
            return memo[1]
        static_key = (normalize_text(semantic_model), normalize_text(table), normalize_text(column))
        values = list(self.static_values.get(static_key, []) or [])
        seen = set(values)
        for value in domain:
            if value not in seen:
                values.append(value)
                seen.add(value)
        # Se guarda junto al dominio del que salió: si la caché lo renueva
        # (TTL), se recompone.
        self.value_cache[key] = (domain, values)
        return values

    _PREWARM_COLUMNS_PER_MODEL = 12

    def prewarm_domains(self, max_columns_per_model=None, only_open_connections=False):
        """Trae (en lotes pequeños de columnas de baja cardinalidad) los dominios
        de las columnas de los visuales donde suele nombrarse un valor suelto
        (servicio, especialidad, aseguradora, sede...). Nunca columnas de
        personas o identificadores. `only_open_connections`: solo modelos cuya
        conexión ya abrió el hilo principal (el hilo de precalentamiento no abre
        conexiones: con Interactive Login el inicio de sesión no debe salir de un
        hilo secundario). Devuelve {modelo: columnas}."""
        limit = int(max_columns_per_model or self._PREWARM_COLUMNS_PER_MODEL)
        by_model = {}
        for field in self.dimension_fields:
            model = field.get("semantic_model")
            if not model or not self._plausible_value_column(field) or not self._implicit_eligible(field, model):
                continue
            column = normalize_text(field.get("column")).replace(" ", "")
            if any(part in column for part in self._PRIVATE_COLUMN_PARTS) or identifier_column(field.get("column")):
                continue
            bucket = by_model.setdefault(model, [])
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if len(bucket) < limit and all(
                key != (normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in bucket
            ):
                bucket.append(field)
        if only_open_connections:
            by_model = {
                model: fields for model, fields in by_model.items()
                if connection_open(self.powerbi_provider, model)
            }
        for model, fields in by_model.items():
            self._prefetch_values(model, fields)
        return {model: len(fields) for model, fields in by_model.items()}

    def _maybe_prewarm_domains(self):
        """POWERBI_DOMAIN_PREWARM=1: precalienta en un hilo aparte (no bloquea el
        arranque). Usa el MISMO proveedor (su _connection_lock serializa las
        consultas con las del usuario), solo modelos con la conexión ya abierta,
        lotes pequeños con tiempo límite, y sus consultas no cuentan en el turno
        del usuario (DomainCache.background). Desactivado por defecto."""
        flag = str(os.getenv("POWERBI_DOMAIN_PREWARM") or "").strip().lower()
        if flag not in ("1", "true", "si", "sí", "yes") or self.powerbi_provider is None:
            return None

        def run():
            try:
                with self._domain_cache().background():
                    self.prewarm_domains(only_open_connections=True)
            except Exception:
                pass  # solo optimización: los dominios se consultan al necesitarlos

        thread = threading.Thread(target=run, name="precalentar-dominios", daemon=True)
        thread.start()
        return thread

    def _prefetch_values(self, semantic_model, fields, limit=None, max_batches=None, lead=False):
        """Trae en lotes pequeños los dominios de texto de baja cardinalidad de
        `fields` que aún no están en caché, en el orden dado (prioridad). Solo
        adelanta consultas que se harían igual: los valores no cambian.
        `max_batches=1` + `lead=True`: búsqueda incremental (solo el siguiente
        lote, y solo si la primera columna entra a un lote)."""
        if not semantic_model or not fields:
            return
        columns = [
            (field.get("table"), field.get("column"),
             self._raw_column_type(semantic_model, field.get("table"), field.get("column")))
            for field in fields if field.get("table") and field.get("column")
        ]
        try:
            self._domain_cache().prefetch(semantic_model, columns, limit=limit, max_batches=max_batches,
                                          lead=lead)
        except Exception:
            pass  # el lote es solo una optimización: get() consulta columna por columna

    def _prefetch_next(self, semantic_model, fields, position, limit=None, skip=()):
        """Búsqueda incremental: antes de leer fields[position], trae en un lote
        (si hace falta) esa columna y las siguientes de baja cardinalidad. Así se
        consulta solo lo que se llega a revisar: el llamador se detiene en la
        primera coincidencia fuerte."""
        field = fields[position]
        cache = self._domain_cache()
        if cache is None or cache.cached(semantic_model, field.get("table"), field.get("column"),
                                         limit=limit or 2500) is not None:
            return
        rest = [
            item for item in fields[position:]
            if (normalize_text(item.get("table")), normalize_text(item.get("column"))) not in skip
        ]
        self._prefetch_values(semantic_model, rest, limit=limit, max_batches=1, lead=True)

    def _value_match_score(self, question, value, value_hint=None, allow_short=False):
        q = normalize_text(value_hint or question)
        v = normalize_text(value)
        if not q or not v:
            return 0.0
        # Códigos cortos («M», «F», «A1»): solo si el texto pedido ES el valor
        # (filtro explícito «sexo M»); jamás como subcadena de otra palabra.
        if len(v) < 3:
            return 1.10 if (allow_short and q == v) else 0.0
        if _exact_phrase(q, v):
            return 1.10

        ignored = {canonical_token(word) for word in GENERIC_QUERY_WORDS | STOPWORDS}
        q_tokens = [
            token for token in canonical_tokens(q)
            if len(token) >= 2 and token not in ignored
        ]
        v_tokens = set(canonical_tokens(v))
        if not q_tokens or not v_tokens:
            return 0.0
        matched = {token for token in q_tokens if token in v_tokens}
        if not any(len(token) >= 3 for token in matched):
            return 0.0
        q_coverage = sum(1 for token in q_tokens if token in v_tokens) / len(q_tokens)
        v_coverage = len(matched) / len(v_tokens)
        if q_coverage == 1.0 or v_coverage == 1.0:
            return min(1.05, 0.94 + min(len(matched), 4) * 0.02)
        if q_coverage >= 0.60:
            return 0.72 + 0.22 * q_coverage
        return 0.0

    def _value_contradiction(self, text, value, values, field, origin):
        """Motivo por el que `value` contradice el texto pedido (ver
        `value_contradiction`), anotado en el razonamiento; None si no."""
        reason = value_contradiction(text, value, values)
        if reason:
            self._note(
                f"{origin}: no se eligió {field.get('table')}[{field.get('column')}] = {value}: {reason}"
            )
        return reason

    def _resolve_value(self, question, field, semantic_model, value_hint=None, context=None):
        """Valor explícito pedido. `context` es la mención completa
        («menores de edad» cuando la columna se llama MENORES y la pista es
        «edad»): con ella se descartan los valores que contradicen la palabra
        distintiva de la pregunta (MAYORES DE EDAD) aunque puntúen igual."""
        values = self._get_values(semantic_model, field["table"], field["column"], essential=True)
        if values is None:
            return None
        scored = []
        for value in values:
            score = self._value_match_score(
                question, value, value_hint=value_hint, allow_short=bool(value_hint)
            )
            if score > 0:
                scored.append((score, value))
        scored.sort(key=lambda item: (item[0], len(normalize_text(item[1]))), reverse=True)
        text = " ".join(part for part in (context, value_hint) if part) or question
        for score, value in scored:
            if score < 0.84:
                break
            if self._value_contradiction(text, value, values, field, "filtro explícito"):
                continue
            return {
                "value": value, "score": round(score, 4),
                "tokens": set(canonical_tokens(value)),
            }
        return None

    # ---------------- group / filter parsing ----------------
    def _clean_tail(self, value, metric):
        text = normalize_text(value)
        removals = self._metric_reports(metric) + [metric.get("semantic_model")]
        # «por servicio en lavanderia»: el informe «TABLERO LAVANDERIA» también
        # se nombra sin la palabra «tablero».
        short_names = [
            re.sub(r"^(?:tablero|informe|dashboard)\s+(?:de\s+(?:la\s+|las\s+|los\s+)?)?", "", normalize_text(r))
            for r in removals if r
        ]
        removals += [name for name in short_names if len(name) >= 4]
        for removal in removals:
            normalized = normalize_text(removal)
            if normalized:
                text = re.sub(r"\ben\s+(?:el|la)?\s*" + re.escape(normalized) + r"\b.*$", "", text)
        text = re.sub(r"\ben\s+20\d{2}\b", "", text)
        for month in MONTHS:
            text = re.sub(r"\ben\s+" + re.escape(month) + r"(?:\s+de\s+20\d{2})?\b", "", text)
        return re.sub(r"\s+", " ", text).strip()

    def _board_name_phrases(self, source_context, metric=None):
        """Nombres normalizados con los que la pregunta puede nombrar el
        tablero/informe del contexto (o del indicador): informe, modelo,
        grupo, alias del registro y tableros nombrados, también sin la
        palabra «tablero/informe» delante («TABLERO LAVANDERIA» -> «lavanderia»).
        No incluye páginas: «servicio de urgencias» sigue siendo un valor
        aunque exista una página URGENCIAS."""
        context = source_context or {}
        names = [
            context.get("report"), context.get("semantic_model"),
            str(context.get("source_group") or "").replace("_", " ").replace("-", " "),
        ]
        for mention in context.get("board_mentions") or []:
            names.extend([mention.get("phrase"), mention.get("name")])
        models = {normalize_text(context.get("semantic_model"))}
        if metric:
            names.extend(self._metric_reports(metric))
            names.append(metric.get("semantic_model"))
            models.add(normalize_text(metric.get("semantic_model")))
        sources_for_model = getattr(self.source_router, "sources_for_model", None)
        if callable(sources_for_model):
            for model in models:
                if not model:
                    continue
                try:
                    sources = sources_for_model(model) or []
                except Exception:
                    sources = []
                for source in sources:
                    names.extend([source.get("report"), *(source.get("aliases") or [])])
                    names.append(str(source.get("source_group") or "").replace("_", " ").replace("-", " "))
        phrases = set()
        for name in names:
            norm = normalize_text(name)
            if not norm:
                continue
            phrases.add(norm)
            short = re.sub(r"^(?:tablero|informe|reporte)\s+(?:(?:de|del|de la|de los)\s+)?", "", norm).strip()
            if short and short not in GENERIC_QUERY_WORDS and len(short) >= 3:
                phrases.add(short)
        return phrases

    def _names_board(self, text, source_context, metric=None):
        """¿`text` («lavanderia», «el tablero de lavanderia») es solo el
        nombre del tablero/informe del contexto?"""
        norm = normalize_text(text)
        norm = re.sub(r"^(?:(?:en|de|del)\s+)?(?:(?:el|la|los|las)\s+)?", "", norm)
        norm = re.sub(r"^(?:tablero|informe|reporte)\s+(?:(?:de|del)\s+)?", "", norm).strip()
        if not norm:
            return False
        return norm in self._board_name_phrases(source_context, metric)

    def _detect_group_or_dimension_filter(self, question, metric, candidates, source_context=None):
        normalized = normalize_text(question)
        match = re.search(
            r"\b(?:por|segun|agrupado por|agrupada por|desglosado por|desglosada por)\s+(?:el|la|los|las)?\s*(.+)$",
            normalized,
        )
        if not match:
            return {"group_by": [], "explicit_filters": []}

        tail = self._clean_tail(match.group(1), metric)
        if not tail:
            return {"group_by": [], "explicit_filters": []}

        best = self._best_dimension(tail, candidates, exclude_temporal=True)
        if not best:
            return {"group_by": [], "explicit_filters": []}

        matched_alias = None
        aliases = sorted(best.get("aliases", []), key=lambda value: len(normalize_text(value)), reverse=True)
        for alias in aliases:
            alias_norm = normalize_text(alias)
            if alias_norm and (tail == alias_norm or tail.startswith(alias_norm + " ")):
                matched_alias = alias_norm
                break
        # Plural/género del nombre («por aseguradores» = ASEGURADORA/ASEGURADOR;
        # «por areas de servicio» = AREA DE SERVICIO entero, no «areas» + valor
        # «de servicio»): gana la coincidencia que cubre más palabras.
        loose = max(
            (prefix for prefix in (_alias_prefix(tail, alias) for alias in aliases) if prefix),
            key=lambda prefix: len(prefix.split()), default=None,
        )
        if loose and (not matched_alias or len(loose.split()) > len(matched_alias.split())):
            matched_alias = loose
        if not matched_alias:
            return {"group_by": [], "explicit_filters": []}

        remainder = tail[len(matched_alias):].strip()
        # «peso por servicio en lavanderia»: lo que sigue a la dimensión con
        # «en» es el tablero/informe nombrado, no un valor de SERVICIO.
        if re.match(r"^en\s+", remainder) and self._names_board(remainder, source_context, metric):
            self._note(
                f"«{matched_alias} {remainder}»: «{remainder}» nombra el tablero; "
                f"se agrupa por {best.get('table')}[{best.get('column')}] (no es un valor del filtro)"
            )
            return {"group_by": [best], "explicit_filters": [], "phrase": matched_alias}
        remainder = re.sub(r"^(?:de|del|en|igual a|=)\s+", "", remainder).strip()
        if not remainder:
            return {"group_by": [best], "explicit_filters": [], "phrase": matched_alias}
        return {"group_by": [], "explicit_filters": [{"field": best, "value_hint": remainder, "from_group": True}]}

    def _remove_metric_and_report_phrases(self, question, metric, source_context):
        """Descarta los nombres de métrica/informe ANTES de buscar filtros.

        Antes, un campo llamado EGRESOS se interpretaba como dimensión
        dentro de la expresión EGRESOS PROBABLES y exigía un valor «probables hay».
        """
        cleaned = normalize_text(question)
        phrases = [
            metric.get("label"),
            source_context.get("report"), source_context.get("semantic_model"),
            metric.get("semantic_model"),
            *self._metric_reports(metric),
        ]
        # Quitar matched_name si es alias coincidente con la pregunta se
        # gestiona adicionalmente en _implicit_value_text.
        for phrase in sorted(_unique_strings(phrases), key=len, reverse=True):
            norm = normalize_text(phrase)
            if norm:
                cleaned = re.sub(r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", " ", cleaned)
        cleaned = re.sub(r"\b(?:tablero|informe)\b", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _detect_explicit_dimension_filters(
        self, question, candidates, already_fields=None,
        metric=None, source_context=None,
    ):
        """Filtros «<dimensión> <valor>» pedidos de forma explícita.

        Cada mención («sede norte») produce UN filtro: el campo mejor ubicado
        (el de la tabla de la métrica / visuales de la métrica) y, como
        respaldo, los demás campos con el mismo alias en `alternatives`.
        """
        normalized = (
            self._remove_metric_and_report_phrases(question, metric, source_context or {})
            if metric else normalize_text(question)
        )
        already_fields = already_fields if already_fields is not None else set()
        metric_table = normalize_text((metric or {}).get("table"))

        def priority(field):
            bonus = 60 if metric_table and normalize_text(field.get("table")) == metric_table else 0
            return -(field.get("relevance_score", 0) + bonus)

        ordered = sorted(candidates, key=priority)
        mentions = {}
        order = []
        for field in ordered:
            if self._is_temporal_field(field):
                continue
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in already_fields:
                continue
            aliases = sorted(field.get("aliases", []), key=lambda v: len(normalize_text(v)), reverse=True)
            for alias in aliases:
                alias_norm = normalize_text(alias)
                if not alias_norm or len(alias_norm) < 3:
                    continue
                pattern = (
                    r"(?<![a-z0-9])" + re.escape(alias_norm) + r"(?![a-z0-9])"
                    + r"(?:\s+(?:de|del|igual a|=|:))?"
                    # {0,80}: un código de una letra al final («sexo M»)
                    # también vale cuando se quitó «en el tablero ...».
                    + r"\s+([a-z0-9][a-z0-9\s\.\-]{0,80})"
                )
                match = re.search(pattern, normalized)
                if not match:
                    continue
                hint = re.split(
                    r"\b(?:en|durante|para el|para la|del tablero|del informe|y|con|pero)\b",
                    match.group(1), maxsplit=1,
                )[0].strip()
                # «servicio de urgencias» es filtro; «servicio por...»,
                # «servicio hay...» o «servicio en ...» no lo son.
                invalid_start = {"hay", "hubo", "tiene", "tienen", "es", "son", "por", "para", "con"}
                tokens = canonical_tokens(hint)
                if not hint or not tokens or tokens[0] in invalid_start:
                    continue
                if len(hint.split()) == 1 and hint in GENERIC_QUERY_WORDS:
                    continue
                # Misma mención (mismo texto pedido) = mismo filtro, aunque
                # varias tablas tengan una columna llamada igual (SEDE).
                mention = (alias_norm, hint)
                if mention not in mentions:
                    mentions[mention] = {"field": field, "value_hint": hint, "alternatives": [], "alias": alias_norm}
                    order.append(mention)
                else:
                    mentions[mention]["alternatives"].append(field)
                break
        filters = [mentions[key] for key in order]
        for spec in filters:
            already_fields.add(
                (normalize_text(spec["field"].get("table")), normalize_text(spec["field"].get("column")))
            )
        return filters

    def _metric_removal_tokens(self, metric, matched_name, source_context):
        values = [matched_name, metric.get("label"), metric.get("semantic_model")]
        # El tablero enrutado solo explica palabras si es el del indicador: con
        # «tiempo de triage por eps» (enrutado a TABLERO EPS) y un indicador de
        # TIEMPOS URGENCIAS, «eps» sigue pendiente (es una agrupación).
        routed_model = normalize_text(source_context.get("semantic_model"))
        if not routed_model or routed_model == normalize_text(metric.get("semantic_model")):
            values.append(source_context.get("report"))
        values.extend(self._metric_reports(metric))
        tokens = set()
        for value in values:
            for token in canonical_tokens(value):
                tokens.add(token)
                without_numeric_suffix = re.sub(r"\d+$", "", token)
                if len(without_numeric_suffix) >= 3:
                    tokens.add(without_numeric_suffix)
                # «%OCUPACION» explica «ocupación»: sin esto la palabra quedaba
                # como posible valor y se exploraban los dominios de la tabla.
                if token.startswith("%") and len(token) > 3:
                    tokens.add(canonical_token(token.lstrip("%")))
        return tokens

    def _implicit_value_text(
        self, question, metric, matched_name, source_context, group_by,
        extra_removals=None,
    ):
        removals = self._metric_removal_tokens(metric, matched_name, source_context)
        for group in group_by:
            for alias in group.get("aliases", []):
                removals.update(canonical_tokens(alias))
        removals.update(canonical_token(word) for word in GENERIC_QUERY_WORDS)
        removals.update(canonical_token(word) for word in STOPWORDS)
        removals.update(canonical_token(word) for word in FILTER_NEUTRAL_WORDS)
        removals.update({"a", "al", "del", "de", "en", "hay", "hubo", "dentro", "segun"})
        removals.update(canonical_token(word) for word in MONTHS)
        removals.update(extra_removals or ())
        # Página/dashboard mencionada completa («programación quirúrgica»).
        question_tokens = set(canonical_tokens(question))
        for page in self._metric_pages(metric):
            page_tokens = canonical_tokens(page)
            if page_tokens and all(token in question_tokens for token in page_tokens):
                removals.update(page_tokens)

        result = []
        text = normalize_text(question)
        # «… y en qué camas»: la entidad del listado pedido no es un filtro.
        trailing = _TRAILING_DETAIL_RE.search(text)
        if trailing and re.search(r"(?<![a-z0-9])cuant[oa]s\s", text[:trailing.start()]):
            text = text[:trailing.start()]
        for word in text.split():
            token = canonical_token(word)
            if (
                token in removals or re.fullmatch(r"20\d{2}", token)
                or token.isdigit() or _is_request_word(token)
            ):
                continue
            result.append(word)
        return " ".join(result).strip()

    _FAMILY_MAX_VALUES = 6

    def _value_family(self, leftover, tied, values):
        """Valores que comparten la palabra pedida como cabeza («uci» ->
        UCI ADULTOS, UCI NEONATAL): {"values", "words", "tokens"} o None.

        Solo si la palabra pedida es el INICIO de todos los valores
        empatados, la familia está completa (todos los valores del dominio
        que empiezan así), tiene entre 2 y _FAMILY_MAX_VALUES miembros y no
        es todo el dominio (filtrar por todo no filtra nada)."""
        leftover_tokens = set(canonical_tokens(leftover))
        heads = set()
        for value in tied:
            tokens = canonical_tokens(value)
            prefix = []
            for token in tokens:
                if token in leftover_tokens:
                    prefix.append(token)
                else:
                    break
            if not prefix:
                return None
            heads.add(tuple(prefix))
        if len(heads) != 1:
            return None
        head = next(iter(heads))
        if not any(len(token) >= 3 for token in head):
            return None
        family = [
            value for value in values
            if tuple(canonical_tokens(value)[:len(head)]) == head and len(canonical_tokens(value)) > len(head)
        ]
        if not (2 <= len(family) <= self._FAMILY_MAX_VALUES) or len(family) >= len(values):
            return None
        if set(family) != set(tied) and not set(tied) <= set(family):
            return None
        return {
            "values": sorted(family, key=normalize_text),
            "words": [word for word in normalize_text(leftover).split() if canonical_token(word) in head],
            "tokens": head,
        }

    def _categorical_filter(self, field, resolved, source, semantic_model):
        data_type = self._column_type(semantic_model, field["table"], field["column"])
        if resolved.get("values") and resolved.get("value") is None:
            # Familia de valores («uci» -> UCI ADULTOS, UCI NEONATAL): IN {...}.
            return {
                "type": "categorical",
                "concept": (field.get("aliases") or [field["column"]])[0],
                "table": field["table"],
                "column": field["column"],
                "operator": "in",
                "value": None,
                "values": list(resolved["values"]),
                "data_type": data_type,
                "match_score": resolved["score"],
                "source": source,
            }
        return {
            "type": "categorical",
            "concept": (field.get("aliases") or [field["column"]])[0],
            "table": field["table"],
            "column": field["column"],
            "operator": "=",
            "value": resolved["value"],
            "data_type": data_type,
            "match_score": resolved["score"],
            "source": source,
        }

    def _implicit_eligible(self, field, semantic_model):
        """Columnas categóricas de cualquier visual (slicer, tabla, matriz, gráfico)."""
        if field.get("kind") not in ("column", "hierarchy_level"):
            return False
        if self._is_temporal_field(field):
            return False
        # Un código numérico o una fecha no es un valor que se nombre en texto libre.
        return self._column_type(semantic_model, field.get("table"), field.get("column")) not in ("number", "date")

    def _resolve_implicit_filter(
        self, question, metric, matched_name, source_context,
        candidates, group_by, used_fields, extra_removals=None, decisions=None,
    ):
        """Valor de dimensión nombrado sin su columna («cirugías de ortopedia»).

        Más estricto que un filtro explícito («especialidad ortopedia»):
        - la palabra no puede ser una que ya explica la métrica o el tablero
          nombrado (se quitan antes, ver `_metric_explaining_tokens`);
        - se revisan primero las columnas plausibles para un valor nombrado
          suelto (servicio, especialidad, aseguradora, sede...);
        - la coincidencia debe ser fuerte y única en la columna («triage» no
          elige TRIAGE III entre TRIAGE I..V);
        - en columnas de entidades (aseguradora, sede, persona...) una palabra
          que es un concepto del catálogo («cirugía») no es un valor.
        Cada decisión se anota en `decisions` para el razonamiento.
        """
        removals = set(extra_removals or ())
        removals.update(self._metric_explaining_tokens(metric))
        leftover = self._implicit_value_text(
            question, metric, matched_name, source_context, group_by,
            extra_removals=removals,
        )
        if not leftover:
            return None

        semantic_model = metric.get("semantic_model")
        eligible = []
        unrelated = []
        for field in candidates:
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in used_fields or field.get("own_fallback") or not self._implicit_eligible(field, semantic_model):
                continue
            if not self._field_filters_metric(metric, field):
                if field.get("table") not in unrelated:
                    unrelated.append(field.get("table"))
                continue
            eligible.append(field)
        if unrelated and decisions is not None:
            decisions.append(
                "no revisadas (sus tablas no filtran " + str(metric.get("table")) + "): "
                + ", ".join(str(table) for table in unrelated[:5]) + ("…" if len(unrelated) > 5 else "")
            )
        # Primero las columnas del propio indicador (su tabla o los visuales
        # de su página): «interconsultas de pediatría» filtra la especialidad
        # de INTERCONSULTAS antes que el SERVICIO de otra página del informe.
        own = self._own_dimension_fields(metric, eligible)
        own_keys = {(normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in own}
        rest = [
            field for field in eligible
            if (normalize_text(field.get("table")), normalize_text(field.get("column"))) not in own_keys
        ]
        plausible = [field for field in rest if self._plausible_value_column(field)]
        others = [field for field in rest if not self._plausible_value_column(field)]
        # Todas las plausibles (hasta un tope) y luego las demás dentro del
        # presupuesto original de columnas revisadas.
        ordered = plausible[:max(self.max_implicit_dimensions, 10)]
        ordered += others[:max(0, self.max_implicit_dimensions - len(ordered))]
        ordered = own + ordered
        # Identificadores y datos de personas (documento, ingreso, OID...) nunca
        # son un valor nombrado suelto (como ya no lo son en las columnas propias):
        # se quitan después de armar la lista, sin que otra columna ocupe su lugar.
        # En Power BI real su dominio tiene miles de valores (TOPN 2500 solo trae
        # los primeros en orden alfabético) y consultarlo cuesta segundos.
        ordered = [field for field in ordered if not identifier_column(field.get("column"))]

        # Búsqueda incremental: los dominios se traen en lotes pequeños (solo
        # columnas de baja cardinalidad) a medida que el bucle los revisa, en su
        # orden de prioridad; al encontrar una coincidencia fuerte (≥ 1.0) no se
        # consulta el resto. Mismo orden y mismos valores que antes.
        best = None
        for position, field in enumerate(ordered):
            self._prefetch_next(semantic_model, ordered, position)
            resolved = self._resolve_implicit_value(
                leftover, field, semantic_model, decisions, question=question,
            )
            if not resolved:
                continue
            candidate = {"field": field, **resolved}
            if best is None or candidate["score"] > best["score"]:
                best = candidate
            if best["score"] >= 1.0:
                break
        if best is not None and decisions is not None:
            decisions.append(f"aplicado: {best['reason']}")
        return best

    def _field_filters_metric(self, metric, field):
        """¿Un filtro sobre la tabla de `field` puede cambiar el indicador?

        No, si el indicador se calcula sobre su tabla, el catálogo técnico
        trae las relaciones del modelo y la tabla del campo no es esa tabla ni
        una de las que la filtran (p. ej. BRIEFING: tablas independientes, un
        SERVICIO de la página SEGUIMIENTO RECEPCIÓN no filtra INTERCONSULTAS).
        Con información incompleta se asume que sí (no se descarta). Misma
        regla que la agrupación y el periodo (`_dimension_relation`)."""
        return self._dimension_relation(metric, field) != "unrelated"

    _OWN_FIELD_LIMIT = 8

    def _own_dimension_fields(self, metric, fields):
        """Campos de la tabla del indicador o de los visuales de sus páginas
        (sin columnas de personas/identificadores), en su orden, hasta un tope."""
        table = normalize_text(self._metric_fact_table(metric))
        pages = {normalize_text(page) for page in self._metric_pages(metric)}
        own, seen = [], set()
        for field in fields:
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in seen:
                continue
            column = normalize_text(field.get("column")).replace(" ", "")
            if any(part in column for part in self._PRIVATE_COLUMN_PARTS):
                continue
            if (table and key[0] == table) or (pages and normalize_text(field.get("page")) in pages):
                own.append(field)
                seen.add(key)
            if len(own) >= self._OWN_FIELD_LIMIT:
                break
        return own

    # ---------------- valores implícitos: reglas estrictas ----------------
    # Palabras de columna en las que un valor suele nombrarse suelto en la
    # pregunta («cirugías de ortopedia», «egresos de urgencias», «de sura»).
    PLAUSIBLE_VALUE_COLUMN_WORDS = {
        "servicio", "servicios", "especialidad", "especialidades", "asegurador",
        "aseguradora", "aseguradoras", "eps", "entidad", "pagador", "sede", "sedes",
        "unidad", "area", "ubicacion", "almacen", "bodega", "tipo", "clasificacion",
        "estado", "sexo", "genero", "modalidad", "menores", "mayores", "edad",
        "etario", "turno", "causa", "motivo", "programa", "convenio", "regimen",
        "categoria", "procedimiento", "piso", "grupo",
    }
    # Columnas de entidades (no de conceptos clínicos): un concepto del
    # catálogo («cirugía», «triage») nunca es una aseguradora o una sede.
    ENTITY_COLUMN_WORDS = {
        "asegurador", "aseguradora", "aseguradoras", "eps", "entidad", "pagador",
        "sede", "sedes", "municipio", "departamento", "cirujano", "medico",
        "profesional", "usuario", "colaborador", "nombre", "convenio", "regimen",
    }

    def _column_words(self, field):
        words = set()
        for value in (field.get("column"), field.get("display_name"), field.get("level")):
            words.update(normalize_text(value).split())
        return words

    def _plausible_value_column(self, field):
        return bool(self._column_words(field) & self.PLAUSIBLE_VALUE_COLUMN_WORDS)

    def _metric_explaining_tokens(self, metric):
        """Palabras que explican la métrica (etiqueta, medida, alias propios):
        no pueden ser además un valor implícito («cirugías realizadas de
        ortopedia» -> «cirugías» no es ASEGURADOR = CIRUGIA)."""
        values = [metric.get("label"), metric.get("measure"), *(metric.get("aliases") or [])]
        tokens = set()
        for value in values:
            for token in canonical_tokens(value):
                if len(token) >= 3 and not token.isdigit():
                    tokens.add(token)
                    stripped = re.sub(r"\d+$", "", token)
                    if len(stripped) >= 3:
                        tokens.add(stripped)
        return tokens

    def _metric_concept_tokens(self):
        """Palabras (canónicas) de los nombres de indicadores aprobados."""
        if getattr(self, "_concept_tokens", None) is not None:
            return self._concept_tokens
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS}
        tokens = set()
        for metric in self.metrics:
            if metric.get("validation_status") != "approved":
                continue
            for value in (metric.get("label"), metric.get("measure")):
                for token in canonical_tokens(value):
                    if len(token) >= 4 and token not in ignored and not token.isdigit():
                        tokens.add(token)
        self._concept_tokens = tokens
        return tokens

    def _resolve_implicit_value(self, leftover, field, semantic_model, decisions=None, question=None):
        """Valor de `field` nombrado en `leftover` con las reglas estrictas, o None."""
        values = self._get_values(semantic_model, field["table"], field["column"])
        if not values:
            return None
        scored = []
        for value in values:
            score = self._value_match_score(leftover, value, value_hint=leftover, allow_short=True)
            if score > 0:
                scored.append((score, value))
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], len(normalize_text(item[1]))), reverse=True)
        column = f"{field['table']}[{field['column']}]"
        # Nunca un valor opuesto a la palabra distintiva («menores» no es
        # MAYORES DE EDAD; «aceptadas» no es NO ACEPTADO).
        consistent, contradicted = [], []
        for score, value in scored:
            # La pregunta completa conserva la polaridad («no aceptadas»),
            # que el texto sobrante pierde al quitar palabras vacías.
            reason = (
                value_contradiction(f"{leftover} {question or ''}", value, values)
                if score >= 0.84 else None
            )
            if reason:
                contradicted.append((value, reason))
                continue
            consistent.append((score, value))
        if decisions is not None and contradicted:
            if not consistent and len(contradicted) > 1:
                names = [value for value, _ in contradicted]
                decisions.append(
                    f"descartado: {column} = {names[0]} (la palabra coincide con varios valores de la columna: "
                    + ", ".join(names[:4]) + ("…" if len(names) > 4 else "")
                    + " y la pregunta no nombra lo que los distingue)"
                )
            else:
                decisions.extend(f"descartado: {column} = {value} ({reason})" for value, reason in contradicted)
        scored = consistent
        if not scored:
            return None
        top_score, top_value = scored[0]
        plausible = self._plausible_value_column(field)

        def reject(reason):
            if decisions is not None:
                decisions.append(f"descartado: {column} = {top_value} ({reason})")
            return None

        # Columna plausible: el valor completo o todas las palabras pedidas
        # deben coincidir (≥ 0.94). Otra columna: solo el valor exacto.
        if top_score < (0.94 if plausible else 1.10):
            if top_score >= 0.84:
                return reject(
                    f"coincidencia parcial {top_score:.2f}"
                    + ("" if plausible else " en una columna poco habitual para un valor suelto")
                )
            return None
        ties = [value for score, value in scored[1:] if score >= top_score - 1e-9]
        if ties and top_score < 1.10 and plausible:
            family = self._value_family(leftover, [top_value, *ties], values)
            if family:
                words = " ".join(family["words"])
                return {
                    "value": None, "values": family["values"], "score": round(top_score, 4),
                    "tokens": set(family["tokens"]),
                    "reason": (
                        f"«{words}» nombra a varios valores de {column} que empiezan igual "
                        f"({', '.join(family['values'])}) y la pregunta no dice cuál: se suman todos "
                        "(pregunta por uno si lo quieres por separado)"
                    ),
                }
        if ties and top_score < 1.10:
            return reject(
                "la palabra coincide con varios valores de la columna: "
                + ", ".join([top_value, *ties][:4]) + ("…" if len(ties) > 3 else "")
            )
        value_tokens = {token for token in canonical_tokens(top_value) if len(token) >= 3}
        leftover_tokens = set(canonical_tokens(leftover))
        matched = value_tokens & leftover_tokens
        if (
            self._column_words(field) & self.ENTITY_COLUMN_WORDS
            and matched and matched <= self._metric_concept_tokens()
        ):
            return reject(
                f"«{' '.join(sorted(matched))}» es un concepto de los indicadores, "
                "no una entidad de esa columna"
            )
        words = " ".join(sorted(matched)) or normalize_text(top_value)
        kind = "columna plausible para un valor nombrado" if plausible else "valor exacto"
        return {
            "value": top_value, "score": round(top_score, 4),
            "tokens": set(canonical_tokens(top_value)),
            "reason": (
                f"«{words}» coincide con {column} = {top_value} "
                f"({kind}, coincidencia {top_score:.2f}, único valor de la columna que coincide)"
            ),
        }

    # ---------------- column types ----------------
    def _technical_column_types(self, semantic_model):
        key = normalize_text(semantic_model)
        cache = self.__dict__.setdefault("_column_type_cache", {})
        if key in cache:
            return cache[key]
        types = {}
        try:
            path = self.source_router.catalog_path_for_model(semantic_model, required=False)
            catalog = self._load_json(path, {}) if path else {}
        except Exception:
            catalog = {}
        for table in catalog.get("tables", []) or []:
            for column in table.get("columns", []) or []:
                types[(normalize_text(table.get("name")), normalize_text(column.get("name")))] = (
                    self._classify_data_type(column.get("data_type"))
                )
        cache[key] = types
        return types

    @staticmethod
    def _classify_data_type(data_type):
        text = normalize_text(data_type)
        if not text:
            return None
        if "date" in text or "time" in text:
            return "date"
        if any(item in text for item in ("int", "decimal", "double", "number", "currency", "float", "whole")):
            return "number"
        return "text"

    def _column_type(self, semantic_model, table, column):
        """'date' | 'number' | 'text' | None (desconocido) según el catálogo técnico."""
        types = self._technical_column_types(semantic_model)
        return types.get((normalize_text(table), normalize_text(column)))

    def _raw_column_type(self, semantic_model, table, column):
        """Tipo de dato tal cual lo trae el catálogo técnico («String», «Int64»...)
        o None. Solo columnas del mismo tipo exacto se consultan en lote."""
        key = normalize_text(semantic_model)
        cache = self.__dict__.setdefault("_raw_column_type_cache", {})
        if key not in cache:
            types = {}
            try:
                path = self.source_router.catalog_path_for_model(semantic_model, required=False)
                catalog = self._load_json(path, {}) if path else {}
            except Exception:
                catalog = {}
            for table_item in catalog.get("tables", []) or []:
                for column_item in table_item.get("columns", []) or []:
                    types[(normalize_text(table_item.get("name")), normalize_text(column_item.get("name")))] = (
                        column_item.get("data_type")
                    )
            cache[key] = types
        return cache[key].get((normalize_text(table), normalize_text(column)))

    # ---------------- time ----------------
    def _is_temporal_field(self, field):
        words = set()
        for value in [*field.get("aliases", []), field.get("column"), field.get("level")]:
            words.update(normalize_text(value).split())
        table = normalize_text(field.get("table"))
        column = normalize_text(field.get("column"))
        level = normalize_text(field.get("level"))
        return (
            table in {"calendario", "calendar", "fecha", "dates"}
            or level in {"ano", "mes", "dia", "year", "month", "day"}
            or bool(words & TEMPORAL_WORDS)
            or column in {"date", "fecha", "fecha servicio", "fecha atencion"}
        )

    def _detect_year_month(self, question):
        normalized = normalize_text(question)
        year_match = re.search(r"\b(20\d{2})\b", normalized)
        year = int(year_match.group(1)) if year_match else None
        month = None
        month_name = None
        for name, number in MONTHS.items():
            if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", normalized):
                month = number
                month_name = name
                break
        return year, month, month_name

    def _temporal_role(self, field, semantic_model):
        """'date' | 'year' | 'month' | None para un campo temporal."""
        column_type = self._column_type(semantic_model, field.get("table"), field.get("column"))
        words = set(normalize_text(field.get("column")).split())
        if column_type == "date":
            return "date"
        if words & {"ano", "anio", "year"}:
            return "year"
        if words & {"mes", "month"}:
            return "month"
        if column_type is None and (words & {"date", "fecha"} or field.get("kind") == "hierarchy_level"):
            return "date"
        return None

    def _best_date_field(self, candidates, semantic_model=None):
        temporal = [
            field for field in candidates
            if self._is_temporal_field(field)
            and (semantic_model is None or self._temporal_role(field, semantic_model) == "date")
        ]
        if not temporal:
            return None

        def score(field):
            value = field.get("relevance_score", 0)
            column = normalize_text(field.get("column"))
            table = normalize_text(field.get("table"))
            if column in {"date", "fecha"}:
                value += 80
            if table in {"calendario", "calendar"}:
                value += 60
            if field.get("kind") == "hierarchy_level":
                value += 30
            return value

        temporal.sort(key=score, reverse=True)
        return temporal[0]

    def _best_temporal_field(self, candidates, semantic_model, role):
        found = [
            field for field in candidates
            if self._is_temporal_field(field) and self._temporal_role(field, semantic_model) == role
        ]
        found.sort(key=lambda field: field.get("relevance_score", 0), reverse=True)
        return found[0] if found else None

    # ---------------- periodos (src/semantic/period_parser.py) ----------------
    def _today(self):
        """Fecha de referencia de los periodos relativos (inyectable en pruebas)."""
        value = self.__dict__.get("today")
        if callable(value):
            value = value()
        return as_date(value) or date.today()

    def _period_parser(self):
        return PeriodParser(self._today())

    @staticmethod
    def _strip_phrase(text, phrase):
        """Quita una frase temporal del texto normalizado (o sus meses/años sueltos)."""
        phrase = normalize_text(phrase)
        if not phrase:
            return text
        # Con la preposición que lo introduce: «servicio en 2024» -> «servicio».
        lead = r"(?:(?:en|de|del|durante|para|desde|hasta)\s+(?:(?:el|la|los|las)\s+)?)?"
        pattern = r"(?<![a-z0-9])" + lead + re.escape(phrase) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            text = re.sub(pattern, " ", text)
        else:
            for word in phrase.split():
                if word in PERIOD_MONTHS or re.fullmatch(r"(?:19|20)\d{2}", word):
                    text = re.sub(
                        r"(?<![a-z0-9])" + lead + re.escape(word) + r"(?![a-z0-9])", " ", text,
                    )
        return re.sub(r"\s+", " ", text).strip()

    def _analyze_periods(self, question, metric=None, matched_name=None):
        """Periodo y agrupación temporal de la pregunta.

        Devuelve {"period", "granularity", "tokens", "clean_question"}:
        `tokens` son las palabras que expresaron el periodo (no son filtros
        de dimensión) y `clean_question` la pregunta sin esas frases, para
        buscar agrupaciones y filtros explícitos sin confundirlas con valores.
        Una frase que forma parte del nombre de la métrica («Egresos año
        anterior», «Promedio mensual») no se toma como periodo.
        """
        normalized = normalize_text(question)
        parser = self._period_parser()
        period = parser.parse(normalized)
        granularity = parser.granularity(normalized)
        names = [
            normalize_text(name)
            for name in ((metric or {}).get("label"), (metric or {}).get("measure"), matched_name)
            if name
        ]

        def in_metric_name(phrase):
            phrase = normalize_text(phrase)
            return bool(phrase) and any(_exact_phrase(name, phrase) for name in names)

        if period and in_metric_name(period["phrase"]):
            period = None
        if granularity and in_metric_name(granularity["phrase"]):
            granularity = None

        clean = normalized
        tokens = set()
        phrases = [*(neutral_phrases(normalized))]
        if period:
            phrases.append(period["phrase"])
            tokens.update(canonical_token(word) for word in TO_DATE_WORDS)
        if granularity:
            phrases.append(granularity["phrase"])
        for phrase in phrases:
            tokens.update(canonical_tokens(phrase))
            clean = self._strip_phrase(clean, phrase)
        return {
            "period": period, "granularity": granularity,
            "tokens": tokens, "clean_question": clean, "question": question,
        }

    def _period_words(self, text):
        """Palabras canónicas de las expresiones de periodo del texto (con caché).

        Solo las que de verdad forman un periodo («este año», «últimos 3
        meses»): «días de estancia» no es un periodo y sigue contando.
        """
        cache = self.__dict__.setdefault("_period_words_cache", {})
        key = normalize_text(text)
        if key not in cache:
            if len(cache) > 512:
                cache.clear()
            cache[key] = frozenset(self._analyze_periods(key)["tokens"])
        return cache[key]

    def _month_values(self, field, semantic_model, months):
        """Valores de la columna MES para esos meses (número o nombre según su tipo)."""
        month_type = self._column_type(semantic_model, field["table"], field["column"])
        if month_type != "text":
            return list(months), "number"
        domain = self._get_values(semantic_model, field["table"], field["column"], essential=True) or []
        names = {normalize_text(item): item for item in domain}
        values = [names.get(PERIOD_MONTH_NAMES[month]) for month in months]
        if any(value is None for value in values):
            return None, "text"
        return values, "text"

    def _period_filters(self, period, candidates, semantic_model=None):
        """Filtros de un periodo según el TIPO real de las columnas temporales.

        Devuelve (filtros, términos_sin_aplicar, notas):
        - columna de fecha -> date_range [start, end) (o MONTH() IN {...} para
          meses sin año);
        - columnas AÑO/MES enteras (o MES de texto) -> filtros categóricos por
          valor: AÑO = 2025 + MES IN {1, 2, 3}; varios años completos -> AÑO IN
          {...}; meses de años distintos -> pares (AÑO, MES).
        Sin fecha diaria, un periodo por días no se aplica (se devuelve vacío).
        Cada filtro lleva `label` con el periodo legible («enero–marzo 2025»).
        """
        label = period.get("label")
        unapplied, notes = [], []
        kind = period.get("kind")
        months_any_year = kind == "months_any_year"
        if months_any_year:
            names = label if len(period["months"]) > 1 else period.get("month_name")
            notes.append(f"Mes sin año ({names}): se consideran todos los años.")

        date_field = (
            self._best_date_field(candidates, semantic_model) if semantic_model
            else self._best_date_field(candidates)
        )
        if date_field:
            item = {
                "type": "date_range",
                "table": date_field["table"],
                "column": date_field["column"],
                "year": period.get("year"),
                "month": period.get("month"),
                "month_name": period.get("month_name"),
                "label": label,
                "period_kind": kind,
                "source": "query_plan_temporal",
            }
            if months_any_year:
                item["months"] = list(period["months"])
            else:
                item["start"] = as_date(period["start"]).isoformat()
                item["end"] = as_date(period["end"]).isoformat()
            return [item], unapplied, notes

        if period.get("daily"):
            # AÑO/MES no bastan para «hoy», «ayer» o «últimos 7 días».
            return [], [f"periodo {label} (el tablero no tiene fecha diaria)"], notes

        year_field = self._best_temporal_field(candidates, semantic_model, "year")
        month_field = self._best_temporal_field(candidates, semantic_model, "month")

        def year_filter(values):
            single = len(values) == 1
            return {
                "type": "categorical", "concept": "año",
                "table": year_field["table"], "column": year_field["column"],
                "operator": "=" if single else "IN",
                "value": values[0] if single else None,
                **({} if single else {"values": list(values)}),
                "data_type": "number", "temporal": "year", "label": label,
                "source": "query_plan_temporal",
            }

        def month_filter(months):
            values, data_type = self._month_values(month_field, semantic_model, months)
            if values is None:
                return None
            single = len(values) == 1
            return {
                "type": "categorical", "concept": "mes",
                "table": month_field["table"], "column": month_field["column"],
                "operator": "=" if single else "IN",
                "value": values[0] if single else None,
                **({} if single else {"values": values}),
                "data_type": data_type, "temporal": "month", "label": label,
                "source": "query_plan_temporal",
            }

        filters = []
        if months_any_year:
            item = month_filter(period["months"]) if month_field else None
            if item:
                filters.append(item)
            else:
                unapplied.append(f"mes {label}")
            return filters, unapplied, notes

        pairs = year_months(as_date(period["start"]), as_date(period["end"]))
        years = sorted({year for year, _ in pairs})
        by_year = {year: [m for y, m in pairs if y == year] for year in years}
        whole_years = all(len(by_year[year]) == 12 for year in years)
        if len(years) == 1 or whole_years:
            if year_field:
                filters.append(year_filter(years))
            else:
                unapplied.append(f"año {', '.join(str(year) for year in years)}")
            if not whole_years:
                item = month_filter(by_year[years[0]]) if month_field else None
                if item:
                    filters.append(item)
                else:
                    unapplied.append(f"meses de {label}")
            return filters, unapplied, notes

        # Meses de años distintos (noviembre 2024–febrero 2025): pares (AÑO, MES).
        if year_field and month_field and self._column_type(
            semantic_model, month_field["table"], month_field["column"]
        ) != "text":
            filters.append({
                "type": "temporal_set", "concept": "año y mes",
                "columns": [
                    {"table": year_field["table"], "column": year_field["column"]},
                    {"table": month_field["table"], "column": month_field["column"]},
                ],
                "values": [[year, month] for year, month in pairs],
                "label": label, "temporal": "year_month",
                "source": "query_plan_temporal",
            })
        else:
            unapplied.append(f"periodo {label}")
        return filters, unapplied, notes

    def _temporal_filters(self, question, candidates, semantic_model=None):
        """Filtros del periodo de la pregunta según el TIPO real de la columna.

        Devuelve (filtros, términos_sin_aplicar, notas). Columna de fecha ->
        date_range; columnas enteras AÑO/MES -> filtro por valor numérico.
        Un mes sin año filtra el mes en todos los años y lo dice en las notas.
        """
        period = self._period_parser().parse(normalize_text(question))
        if not period:
            return [], [], []
        return self._period_filters(period, candidates, semantic_model)

    def _bucket_period(self, bucket):
        """Subperiodo de split_period con la forma de un periodo."""
        today = self._today()
        if bucket.get("start") is None:
            month = bucket["months"][0]
            return {
                "kind": "months_any_year", "months": [month], "year": None, "month": month,
                "month_name": PERIOD_MONTH_NAMES[month], "label": bucket["label"],
                "daily": False, "start": None, "end": None,
            }
        start, end = as_date(bucket["start"]), as_date(bucket["end"])
        last = end - timedelta(days=1)
        same_month = (start.year, start.month) == (last.year, last.month)
        return {
            "kind": "range", "start": start, "end": end,
            "year": start.year if start.year == last.year else None,
            "month": start.month if same_month else None,
            "month_name": None, "label": bucket["label"],
            "daily": bucket.get("daily", False), "to_date": end > today,
        }

    def _year_domain_period(self, candidates, semantic_model):
        """Años con datos (columna AÑO entera) como periodo para «por año» sin periodo."""
        year_field = self._best_temporal_field(candidates, semantic_model, "year")
        if not year_field or self._best_date_field(candidates, semantic_model):
            return None
        values = self._get_values(semantic_model, year_field["table"], year_field["column"], essential=True) or []
        years = sorted({int(v) for v in values if str(v).isdigit()})[-10:]
        if not years:
            return None
        parser = self._period_parser()
        period = parser._range(date(years[0], 1, 1), date(years[-1] + 1, 1, 1), "")
        period["label"] = f"{period['label']} (años con datos)"
        return period

    def _current_state_period(self, period):
        """¿El periodo incluye el día de hoy («hoy», «este mes», «este año»)?"""
        start, end = as_date(period.get("start")), as_date(period.get("end"))
        today = self._today()
        return bool(start and end and start <= today < end)

    def _snapshot_table(self, metric, candidates):
        """(tabla, tiene_fechas) de un indicador sin ninguna columna temporal
        válida (propia o relacionada) entre las candidatas: su tabla refleja el
        estado actual (CAMAS DISPONIBLES no tiene fechas; PACIENTES X
        ASEGURADORA tiene FechaSalida, que no es la fecha de un periodo). None
        si queda alguna fecha válida o no se conoce la tabla del indicador."""
        if metric is None or any(self._is_temporal_field(field) for field in candidates):
            return None
        entry = self._fact_table_entry(metric)
        if not entry or not entry.get("columns"):
            return None
        dated = any(
            self._classify_data_type(column.get("data_type")) == "date"
            or set(normalize_text(column.get("name")).split()) & TEMPORAL_WORDS
            for column in entry.get("columns") or []
        )
        return entry.get("name"), dated

    def _apply_temporal(self, analysis, candidates, semantic_model, group_by, metric=None):
        """Filtros del periodo + agrupación temporal («por mes») del plan.

        Devuelve {"filters", "unapplied", "notes", "unsupported_period",
        "group", "buckets"}. La agrupación usa subperiodos explícitos
        (`buckets`, uno por mes/trimestre/año...) que el generador DAX evalúa
        con los mismos filtros de periodo: funciona igual con columna de fecha
        o con columnas AÑO/MES enteras. Si no se puede agrupar, se declara.
        Las fechas de tablas que no filtran el indicador ya no están en
        `candidates` (`_metric_dimensions`): «hoy» sobre una tabla sin fecha
        (estado actual, p. ej. CAMAS DISPONIBLES) responde el valor actual.
        """
        result = {
            "filters": [], "unapplied": [], "notes": [], "unsupported_period": None,
            "group": None, "buckets": [],
        }
        period = analysis.get("period")
        granularity = analysis.get("granularity")
        if period:
            filters, unapplied, notes = self._period_filters(period, candidates, semantic_model)
            snapshot = None if filters else self._snapshot_table(metric, candidates)
            phrase = _original_phrase(analysis.get("question") or "", period.get("phrase")) or period.get("label")
            if not filters and snapshot and self._current_state_period(period):
                table, dated = snapshot
                why = (
                    "el tablero no usa ninguna de sus fechas como periodo" if dated
                    else "la tabla refleja el momento presente, sin histórico por fechas"
                )
                result["notes"].append(f"«{phrase}»: se muestra el estado actual de {table} ({why}).")
                result["current_state"] = True
                period = None
            elif not filters:
                result["unsupported_period"] = period
                result["unapplied"] = unapplied
                if snapshot:
                    # Un periodo pasado en una tabla de estado actual: se dice por qué.
                    result["explanation"] = (
                        f"{metric.get('label')} muestra el estado actual de {snapshot[0]}: no tiene "
                        f"una fecha con la que filtrar «{phrase}»."
                    )
                return result
        if period:
            result["filters"].extend(filters)
            result["unapplied"].extend(unapplied)
            result["notes"].extend(notes)
            for word in period.get("ignored") or []:
                what = "mes" if word in PERIOD_MONTHS else "año"
                result["unapplied"].append(f"{what} {word} (solo se aplicó {period['label']})")

        if not granularity:
            return result
        unit = granularity["unit"]
        name = GRANULARITY_LABELS[unit]
        if group_by:
            result["unapplied"].append(
                f"agrupar por {name.lower()} (ya se agrupa por {group_by[0].get('column')})"
            )
            return result

        base = period
        if base is None:
            base = (self._year_domain_period(candidates, semantic_model) if unit == "year" else None) \
                or self._period_parser().default_window(unit)
            filters, unapplied, _ = self._period_filters(base, candidates, semantic_model)
            if filters and not unapplied:
                result["filters"].extend(filters)
                result["notes"].append(f"Sin periodo en la pregunta: se muestra {base['label']}.")
        buckets = split_period(base, unit, self._today())
        if not buckets:
            result["unapplied"].append(
                f"agrupar por {name.lower()} (más de 62 periodos o periodo sin año: acota el periodo)"
            )
            return result
        planned = []
        table = None
        for bucket in buckets:
            filters, unapplied, _ = self._period_filters(
                self._bucket_period(bucket), candidates, semantic_model,
            )
            if not filters or unapplied:
                result["unapplied"].append(
                    f"agrupar por {name.lower()} (el tablero no tiene la columna de fecha necesaria)"
                )
                # Sin agrupación, el filtro por defecto ya no tiene sentido.
                if period is None:
                    result["filters"] = []
                    result["notes"] = [n for n in result["notes"] if not n.startswith("Sin periodo")]
                return result
            table = table or filters[0].get("table") or (filters[0].get("columns") or [{}])[0].get("table")
            planned.append({"order": bucket["order"], "label": bucket["label"], "filters": filters})
        result["buckets"] = planned
        result["group"] = {
            "table": table, "column": name, "label": name,
            "source": "query_plan_temporal_group", "temporal": unit,
        }
        return result

    # ---------------- public API ----------------
    def is_descriptive(self, question):
        return self._is_descriptive(normalize_text(question))

    def _is_descriptive(self, normalized):
        return self.descriptive_reason(normalized) is not None

    def descriptive_reason(self, question):
        """Frase que vuelve descriptiva la pregunta («como se calcula», «los
        rangos del», «para que sirve»...) o None. Una pregunta descriptiva va
        al RAG aunque contenga palabras numéricas («porcentaje», «total»)."""
        normalized = normalize_text(question)
        for pattern in DESCRIPTIVE_PATTERNS:
            if re.search(r"(?<![a-z0-9])" + re.escape(pattern) + r"(?![a-z0-9])", normalized):
                return pattern
        return descriptive_phrase(normalized)

    @staticmethod
    def _has_period(normalized):
        months = "|".join(MONTHS)
        return bool(
            re.search(r"(?<![a-z0-9])(?:" + months + r")(?![a-z0-9])", normalized)
            or re.search(r"(?<![0-9])20\d{2}(?![0-9])", normalized)
            # Periodos relativos («este año», «mes pasado», «últimos 3 meses»)
            # y agrupaciones temporales («por mes», «mensual»).
            or PeriodParser().parse(normalized)
            or PeriodParser().granularity(normalized)
        )

    def looks_numeric(self, question, dashboard=None):
        """Detecta intención cuantitativa sin depender del orden ni del género.

        Orden de decisión: 1) definicional -> RAG; 2) término numérico
        (cuánto/cuánta/participación/promedio...); 3) la pregunta resuelve a
        una métrica conocida y pide un dato con verbo ("dime", "cuál fue"),
        menciona un período o «por <dimensión>» (incluye estilo telegráfico).
        """
        normalized = normalize_text(question)
        if not normalized or self._is_descriptive(normalized):
            return False
        question = canonical_phrases(question)[0]
        normalized = normalize_text(question)

        if any(
            re.search(r"(?<![a-z0-9])" + term + r"(?![a-z0-9])", normalized)
            for term in NUMERIC_TERM_PATTERNS
        ):
            return True
        # «qué camas están disponibles en UCI», «lista de camas bloqueadas»:
        # piden el listado de un indicador (src/semantic/answer_shape.py).
        if self._detail_list_question(question, dashboard):
            return True

        has_verb = any(
            re.search(r"(?<![a-z0-9])(?:" + verb + r")(?![a-z0-9])", normalized)
            for verb in QUERY_VERB_PATTERNS
        )
        has_period = self._has_period(normalized)
        has_group = bool(re.search(r"(?<![a-z0-9])(?:por|segun)\s+[a-z]", normalized))
        # «top 5 ...», «el servicio con más ...»: un ranking siempre es numérico.
        if self._mentions_ranking(normalized):
            return True
        if not (has_verb or has_period or has_group):
            return self._nominal_metric_with_filter(question, dashboard)

        source_context = self._source_context(question, dashboard=dashboard)
        metric_result = self._resolve_metric_flexible(question, source_context)
        if metric_result.get("status") in ("resolved", "ambiguous"):
            return True
        if (has_group or has_period) and self._names_metric_of_named_board(question, source_context):
            return True
        # Ningún indicador coincide, pero la pregunta nombra una página que sí
        # tiene indicadores («hospitalizaciones parciales de marzo»).
        pages = self._named_pages(source_context) or (
            [] if source_context.get("board_mentions") else self._topic_pages(question)
        )
        return any(self._page_members(page) for page in pages)

    def _names_metric_of_named_board(self, question, source_context):
        """«peso por servicio en lavandería»: la pregunta nombra un tablero
        (routing fuerte) y su sustantivo principal es una palabra del nombre o
        la tabla de un indicador visible de ese tablero (PESO TOTAL por Mes):
        con «por <dimensión>» o un periodo pide datos, no documentación, aunque
        el nombre completo del indicador no coincida."""
        if not (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
            and self._board_named_explicitly(question, source_context)
        ):
            return False
        head = self._head_token(question, source_context)
        if not head:
            return False
        model = normalize_text(source_context.get("semantic_model"))
        return any(
            metric.get("validation_status") == "approved" and metric.get("appearances")
            and normalize_text(metric.get("semantic_model")) == model
            and self._explains(head, self._metric_vocabulary_tokens(metric, with_pages=False))
            for metric in self._dedupe_metrics(self.metrics)
        )

    def _detail_list_question(self, question, dashboard=None):
        """Pregunta de listado («qué <entidad> hay/están», «lista de …») cuya
        entidad resuelve a un indicador: es una pregunta de datos, no de
        documentación."""
        if detail_request(question) is None:
            return False
        source_context = self._source_context(question, dashboard=dashboard)
        metric_result = self._resolve_metric_flexible(question, source_context)
        return metric_result.get("status") in ("resolved", "ambiguous")

    _NOMINAL_MAX_WORDS = 8

    _NOMINAL_NAME_MAX_WORDS = 4
    _LEADING_ARTICLE_RE = re.compile(r"^(?:el|la|los|las|un|una|unos|unas)\s+")

    def _names_indicator_exactly(self, text, source_context):
        """¿La frase completa (sin artículo inicial, 2 a 4 palabras) es el nombre
        de un indicador visible (etiqueta o título de su visual) o de una página
        de un informe que tiene indicadores?"""
        phrase = self._LEADING_ARTICLE_RE.sub("", normalize_text(text).replace("_", " ")).strip()
        words = phrase.split()
        if len(words) < 2 or len(words) > self._NOMINAL_NAME_MAX_WORDS:
            return False
        if self._weak_name_kind(phrase):
            return False

        def same(name):
            return normalize_text(str(name or "").replace("_", " ")) == phrase

        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved" or not metric.get("appearances"):
                continue
            titles = [item.get("visual_title") for item in metric.get("appearances") or []]
            if any(same(name) for name in [metric.get("label"), *titles]):
                return True
        for key, item in self._page_index().items():
            if same(item.get("page")) and self._page_members({
                "semantic_model": item.get("semantic_model"), "page": item.get("page"),
            }):
                return True
        return False

    def _nominal_metric_with_filter(self, question, dashboard=None):
        """Frase nominal sin verbo, periodo ni «por ...» que nombra TAL CUAL un
        indicador más un valor de filtro («interconsultas sin responder de
        pediatría»): pide el dato filtrado -> Power BI. El nombre del indicador
        solo («interconsultas sin respuesta») o un tablero («tablero de
        interconsultas») siguen siendo preguntas para la documentación."""
        text, _ = canonical_phrases(question)
        normalized = normalize_text(text)
        words = normalized.split()
        if not words or len(words) > self._NOMINAL_MAX_WORDS:
            return False
        if re.match(r"^(?:el |la |los |las )?(?:tablero|informe|reporte|pagina|dashboard)\b", normalized):
            return False
        source_context = self._source_context(text, dashboard=dashboard)
        # Frase corta que es TAL CUAL el nombre de un indicador o de una página
        # con indicadores («medicamentos vencidos», «interconsultas sin
        # respuesta»): se pide el dato (si es una página, se ofrecen sus
        # indicadores), no la documentación.
        if self._names_indicator_exactly(text, source_context):
            return True
        metric_result = self._resolve_metric_flexible(text, source_context)
        if metric_result.get("status") != "resolved":
            return False
        matched = normalize_text(metric_result.get("matched_name"))
        label = normalize_text((metric_result.get("metric") or {}).get("label"))
        business = normalize_text(self._metric_business_question(text, source_context))
        if not any(name and _exact_phrase(business, name) for name in (matched, label)):
            return False
        notes = self.__dict__.get("_resolution_notes")
        try:
            self._resolution_notes = []
            plan = self._build_plan(text, {"dashboard": dashboard} if dashboard else None)
        except Exception:
            return False
        finally:
            self._resolution_notes = notes
        if not isinstance(plan, dict) or plan.get("status") != "ready" or plan.get("unapplied_terms"):
            return False
        return any(
            item.get("type") == "categorical" and not item.get("temporal")
            and item.get("source") != "query_plan_temporal"
            for item in plan.get("filters") or []
        )

    # ---------------- participación / multi-métrica ----------------
    def _share_match(self, normalized):
        """Frase de participación en el texto, salvo que sea parte del nombre de una métrica."""
        match = SHARE_RE.search(normalized)
        if not match:
            return None
        phrase = match.group(0).strip()
        for metric in self._dedupe_metrics(self.metrics):
            for name in self._metric_names(metric):
                norm = normalize_text(name)
                if norm and phrase in norm and re.search(
                    r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", normalized
                ):
                    return None
        return match

    def _mentioned_metrics(self, normalized, source_context):
        """Métricas nombradas literalmente (frases completas, sin solaparse)."""
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        model_hint = normalize_text(source_context.get("semantic_model")) if strong else None
        found = []
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            if model_hint and normalize_text(metric.get("semantic_model")) != model_hint:
                continue
            for name in self._metric_names(metric):
                norm = normalize_text(name)
                if len(norm) < 3 or norm in GENERIC_QUERY_WORDS or norm.isdigit():
                    continue
                for m in re.finditer(
                    r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", normalized
                ):
                    found.append({
                        "metric": metric, "name": norm,
                        "start": m.start(), "end": m.end(),
                    })
        found.sort(key=lambda item: (-(item["end"] - item["start"]), item["start"]))
        accepted = []
        for item in found:
            if any(item["start"] < o["end"] and o["start"] < item["end"] for o in accepted):
                continue
            accepted.append(item)
        accepted.sort(key=lambda item: item["start"])
        return accepted

    @staticmethod
    def _metric_key(metric):
        return (
            normalize_text(metric.get("semantic_model")),
            normalize_text(metric.get("label")),
            normalize_text(metric.get("dax_expression")),
        )

    def _distinct_mentions(self, mentions):
        """Una mención por métrica distinta y del mismo modelo semántico."""
        if not mentions:
            return []
        models = {}
        for item in mentions:
            models.setdefault(normalize_text(item["metric"].get("semantic_model")), []).append(item)
        group = max(models.values(), key=len)
        result, seen = [], set()
        for item in group:
            key = self._metric_key(item["metric"])
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    @staticmethod
    def _cut_spans(text, spans):
        """Quita tramos [(ini, fin)] y la conjunción pegada a ellos."""
        for start, end in sorted(spans, reverse=True):
            left, right = text[:start], text[end:]
            if re.search(r"(?<![a-z0-9])(?:y|e)\s+$", left):
                left = re.sub(r"(?:y|e)\s+$", "", left)
            else:
                right = re.sub(r"^\s*(?:y|e)(?![a-z0-9])", "", right)
            text = left + " " + right
        return re.sub(r"\s+", " ", text).strip()

    def _default_share_metric(self, source_context):
        """Métrica base cuando solo se pide la participación ("participación de X")."""
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        if not strong:
            return {"status": "not_found", "candidates": []}
        model_hint = normalize_text(source_context.get("semantic_model"))
        report_hint = normalize_text(source_context.get("report"))
        pool = []
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            if normalize_text(metric.get("semantic_model")) != model_hint:
                continue
            reports = self._metric_reports(metric)
            if report_hint and reports and not any(normalize_text(r) == report_hint for r in reports):
                continue
            if not metric.get("dax_expression"):
                continue
            if self._is_ratio_metric(metric):
                continue  # un porcentaje/promedio no es la base de una participación
            pool.append(metric)
        if not pool:
            return {"status": "not_found", "candidates": []}

        def rank(metric):
            visuals = sum(
                1 for ap in metric.get("appearances", []) or []
                if "participacion" in normalize_text(ap.get("visual_title"))
            )
            return (visuals, len(metric.get("appearances", []) or []))

        ranked = sorted(pool, key=rank, reverse=True)
        if len(ranked) == 1 or rank(ranked[0]) > rank(ranked[1]):
            return {"status": "resolved", "metric": ranked[0]}
        return {
            "status": "ambiguous",
            "candidates": [
                {"metric": m, "score": 1.0, "business_score": 1.0, "matched_name": m.get("label")}
                for m in ranked[:8]
            ],
        }

    def _unresolved_neighbor(self, normalized, share_span, mentions):
        """Palabra suelta unida con «y» a la participación que no se pudo interpretar."""
        before = normalized[:share_span[0]]
        after = normalized[share_span[1]:]
        word = None
        m = re.search(r"([a-z0-9]+)\s+y\s*$", before)
        if m:
            word = m.group(1)
        else:
            m = re.match(r"\s*y\s+([a-z0-9]+)", after)
            if m:
                word = m.group(1)
        if not word or word in FILLER_WORDS or word in MONTHS or word.isdigit():
            return None
        if any(word in item["name"].split() for item in mentions):
            return None
        dimension_words = {
            canonical_token(alias)
            for field in self.dimension_fields
            for entry in field.get("aliases", [])
            for alias in normalize_text(entry).split()
        }
        if canonical_token(word) in dimension_words:
            return None
        return word

    def build_composite(self, question, intent_result=None, selections=None):
        """Preguntas con participación y/o varias métricas ("peso y participación",
        "cirugías programadas y realizadas", "total de X y promedio de X").

        Devuelve None cuando la pregunta es de una sola métrica (flujo normal).
        Si no: {"status": "composite", "items": [...], "unresolved": [...],
        "grouped": bool} con items {"kind": "metric"|"share", "plan": plan,
        "label": str}, o el plan fallido (ambiguous / unsupported_filter /
        not_found, con "composite": True). Un plan ambiguo de UNA parte trae
        "composite_context" para retomar la compuesta tras la contrapregunta.

        `selections` = {parte: metric_id} elegidos en contrapreguntas previas
        de esta misma compuesta (parte "share" o el índice de la parte).
        """
        intent_result = intent_result or {}
        selections = {str(k): v for k, v in (selections or {}).items()}
        normalized = normalize_text(question)
        if not normalized or self._is_descriptive(normalized):
            return None
        source_context = self._source_context(question, dashboard=intent_result.get("dashboard"))
        share = self._share_match(normalized)
        share_question = None if share else self._share_question_match(normalized)
        share = share or share_question
        mentions = self._distinct_mentions(self._mentioned_metrics(normalized, source_context))

        if not share and not self._mentions_are_coordinated(normalized, mentions):
            # Sin nombres literales coordinados: coordinación por partes
            # («programadas y realizadas», «total de X y promedio de X»).
            return self._coordinated_composite(
                question, intent_result, source_context, selections,
            )

        unresolved = []
        rest_text = normalized
        coordinated_with_share = False
        if share:
            all_mentions = self._mentioned_metrics(normalized, source_context)
            neighbor = self._unresolved_neighbor(normalized, share.span(), all_mentions)
            coordinated_with_share = any(
                self._joined_by_conjunction(normalized, share.span(), (m["start"], m["end"]))
                for m in all_mentions
            )
            rest_text = self._cut_spans(normalized, [share.span()])
            # Muletillas interrogativas que quedan al quitar la participación.
            rest_text = re.sub(
                r"(?<![a-z0-9])(?:que|cual|cuales|fue|fueron|tuvo|tuvieron|tiene|tienen"
                r"|es|son|corresponde|corresponden|correspondio|correspondieron)(?![a-z0-9])",
                " ", rest_text,
            )
            rest_text = re.sub(r"\s+", " ", rest_text).strip()
            if neighbor:
                unresolved.append(neighbor)
                rest_text = re.sub(
                    r"(?<![a-z0-9])y\s+" + re.escape(neighbor) + r"(?![a-z0-9])", " ", rest_text
                )
                rest_text = re.sub(
                    r"(?<![a-z0-9])" + re.escape(neighbor) + r"\s+y(?![a-z0-9])", " ", rest_text
                )
            # La frase de participación puede solaparse con una métrica
            # ("peso relativo"): las menciones se recalculan sobre el resto.
            mentions = self._distinct_mentions(
                self._mentioned_metrics(rest_text, source_context)
            )
            # «qué porcentaje de las atenciones...»: «atenciones» nombra tal
            # cual %ATENCIONES, pero la participación divide un total entre
            # otro; un porcentaje o promedio no es su base.
            ratios = [m for m in mentions if self._is_ratio_metric(m["metric"])]
            if ratios:
                self._note(
                    "en la participación no se usa como base "
                    + ", ".join(str(m["metric"].get("label")) for m in ratios)
                    + " (porcentaje o promedio)"
                )
                mentions = [m for m in mentions if m not in ratios]

        share_note = None
        if share and selections.get("share"):
            chosen = self._approved_metric(selections["share"])
            if chosen is None:
                return None
            targets = [(chosen, rest_text)]
            mentions = []
        elif share and not mentions:
            base = self._share_base_metric(question, rest_text, intent_result, source_context)
            if base.get("status") != "resolved":
                return base
            targets = [(base["metric"], rest_text)]
            share_note = base.get("note")
        else:
            targets = []
            for item in mentions:
                others = [(o["start"], o["end"]) for o in mentions if o is not item]
                targets.append((item["metric"], self._cut_spans(rest_text, others)))

        items, failures, failed_labels = [], [], []
        for metric, sub_question in targets:
            plan = self.build(
                sub_question, intent_result=intent_result,
                selected_metric_id=metric.get("metric_id"),
            )
            if plan.get("status") != "ready":
                plan["composite"] = True
                failures.append(plan)
                failed_labels.append(metric.get("label"))
                continue
            plan["question"] = question
            plan["composite_sub_question"] = sub_question
            items.append({"kind": "metric", "plan": plan, "label": metric.get("label")})

        if not items:
            return failures[0]
        grouped = any(i["plan"].get("mode") == "grouped" for i in items)
        if grouped and (
            not self._same_grouping([i["plan"] for i in items])
            or (not share and len(items) < 2)
        ):
            return None  # Agrupaciones distintas: se mantiene el flujo de una sola.

        if share:
            base = items[0]["plan"]
            if base.get("mode") == "grouped":
                dimension = dict(base["group_by"][0])
                dimension["scope"] = "group"
            else:
                categorical = [
                    f for f in base.get("filters", [])
                    if f.get("type") == "categorical" and not f.get("temporal")
                ]
                if not categorical:
                    return {
                        "status": "unsupported_filter", "stage": "share",
                        "reason": "share_requires_dimension_value",
                        "question": question,
                        "semantic_model": base.get("semantic_model"),
                        "source_context": source_context,
                        "query_plan": base, "composite": True,
                    }
                dimension = {
                    "table": categorical[0]["table"], "column": categorical[0]["column"],
                    "label": categorical[0].get("concept"),
                    "value": categorical[0].get("value"), "scope": "filter",
                }
            share_plan = dict(base)
            share_plan["share_dimension"] = dimension
            items.append({"kind": "share", "plan": share_plan, "label": "Participación"})
            if (
                not mentions or share_question
                or (base.get("mode") == "grouped" and not coordinated_with_share)
            ):
                # Solo participación cuando la pregunta no pidió la métrica
                # base («¿qué participación tuvo X?», «qué porcentaje del peso
                # fue de X», «participación del peso por servicio»). «peso y
                # participación por servicio» pide las dos columnas.
                items = [items[-1]]
            grouped = base.get("mode") == "grouped"

        composite = {
            "status": "composite", "question": question, "items": items,
            "unresolved": unresolved, "failures": failures,
            "failed_labels": failed_labels,
            "source_context": source_context,
            "grouped": grouped,
            "split": "share" if share else "mentions",
        }
        if share_note:
            composite["notes"] = [share_note]
        return composite

    # ---------------- compuestas: utilidades ----------------
    # «qué porcentaje de las atenciones de 2025 fueron de nueva eps»: el
    # verbo final («fueron de», «corresponden a») distingue la participación
    # de un indicador que ya es un porcentaje («qué porcentaje de ocupación»).
    _SHARE_QUESTION_RE = re.compile(
        r"(?<![a-z0-9])(?:que|cual\s+(?:es|fue)\s+el|el)\s+(?:porcentaje|%)\s+(?:de|del)"
        r"(?=\s+(?:(?:el|la|los|las)\s+)?[a-z0-9].*?\s"
        r"(?:fueron|fue|son|es|corresponde|corresponden|correspondio|correspondieron"
        r"|pertenece|pertenecen|pertenecio|pertenecieron)\s+(?:de|a|al|del|para)\s)"
    )

    def _share_question_match(self, normalized):
        match = self._SHARE_QUESTION_RE.search(normalized)
        if not match:
            return None
        core = re.search(r"(?:porcentaje|%)\s+de", match.group(0)).group(0)
        for metric in self._dedupe_metrics(self.metrics):
            for name in self._metric_names(metric):
                norm = normalize_text(name)
                if norm and norm.startswith(core) and re.search(
                    r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", normalized
                ):
                    return None
        return match

    def _approved_metric(self, metric_id):
        for metric in self._dedupe_metrics(self.metrics):
            if (
                metric.get("validation_status") == "approved"
                and str(metric.get("metric_id")) == str(metric_id)
            ):
                return metric
        return None

    @staticmethod
    def _joined_by_conjunction(normalized, left_span, right_span):
        """True si entre los dos tramos solo hay «y»/«e» y muletillas."""
        (a_start, a_end), (b_start, b_end) = sorted([left_span, right_span])
        if a_end > b_start:
            return False
        words = normalized[a_end:b_start].split()
        return (
            bool({"y", "e"} & set(words)) and len(words) <= 4
            and all(w in FILLER_WORDS for w in words)
        )

    def _mentions_are_coordinated(self, normalized, mentions):
        """Varias métricas nombradas literalmente y unidas por «y», «e» o coma."""
        if len(mentions) < 2:
            return False
        for left, right in zip(mentions, mentions[1:]):
            words = normalized[left["end"]:right["start"]].split()
            if (
                not ({"y", "e", "con", "ademas"} & set(words))
                or len(words) > 4
                or any(w not in FILLER_WORDS and w not in {"ademas"} for w in words)
            ):
                return False
        return True

    @staticmethod
    def _grouping_signature(plan):
        if plan.get("mode") != "grouped":
            return None
        if plan.get("temporal_buckets"):
            return ("temporal", tuple(b.get("label") for b in plan["temporal_buckets"]))
        return tuple(
            (normalize_text(g.get("table")), normalize_text(g.get("column")))
            for g in plan.get("group_by") or []
        )

    def _same_grouping(self, plans):
        signatures = {self._grouping_signature(plan) for plan in plans}
        return len(signatures) == 1 and None not in signatures

    def _is_ratio_metric(self, metric):
        """¿El indicador es un porcentaje o un promedio (no se puede sumar)?
        Además de `_metric_measure_kinds`: «%» en el nombre sin normalizar o
        en el formato, o una división entre dos agregaciones
        («DISTINCTCOUNT(...)/DISTINCTCOUNT(...)», sin DIVIDE)."""
        metric = metric or {}
        if self._metric_measure_kinds(metric) & {"percent", "average"}:
            return True
        names = f"{metric.get('label') or ''} {metric.get('measure') or ''}"
        fmt = str(metric.get("format_string") or metric.get("format") or "")
        if "%" in names or "%" in fmt:
            return True
        expression = " ".join(
            str(value) for value in (
                metric.get("base_dax_expression") or metric.get("dax_expression"), metric.get("model_expression"),
                self._measure_expression(metric.get("semantic_model"), metric),
            ) if value
        )
        return bool(re.search(r"\)\s*/\s*\(?\s*[A-Z]+\s*\(", expression, re.IGNORECASE))

    def _share_base_metric(self, question, rest_text, intent_result, source_context):
        """Métrica base de una participación sin indicador nombrado literalmente.

        El resto de la pregunta («las atenciones de 2025 de nueva eps») se
        resuelve como cualquier pregunta. Si el indicador existe en varios
        tableros, se queda el único en el que el valor pedido es un filtro
        válido (la participación lo necesita) o, entre los válidos, el de
        participación del tablero enrutado; si quedan varios, se contrapregunta
        esa parte. Sin indicador reconocible: el de participación del tablero
        enrutado (_default_share_metric).
        """
        default = self._default_share_metric(source_context)
        plan = self.build(rest_text, intent_result=intent_result)
        status = plan.get("status")
        if status == "ready" and self._is_ratio_metric(plan["metric"]):
            # Una participación divide el total con el filtro entre el total
            # sin él: con un porcentaje o un promedio («%ATENCIONES» para «qué
            # porcentaje de las atenciones fueron de nueva eps») esa división
            # no tiene sentido. Se buscan los conteos/sumas que también
            # nombran la pregunta.
            additive = [
                candidate for candidate in self.alternative_metrics(
                    rest_text, intent_result, exclude_ids=[plan["metric"].get("metric_id")], limit=8,
                )
                if not self._is_ratio_metric(candidate.get("metric") or {})
                and float(candidate.get("business_score") or 0.0) >= self.min_metric_score
            ]
            if additive:
                self._note(
                    f"{plan['metric'].get('label')} es un porcentaje/promedio: no sirve de base para una "
                    "participación; se prueban los indicadores que cuentan o suman: "
                    + ", ".join(str(c["metric"].get("label")) for c in additive[:5])
                )
                plan = {**plan, "status": "ambiguous",
                        "metric_resolution": {**(plan.get("metric_resolution") or {}), "candidates": additive}}
                status = "ambiguous"
        if status == "ready":
            return {"status": "resolved", "metric": plan["metric"]}
        if status == "ambiguous":
            viable, seen = [], set()
            for candidate in (plan.get("metric_resolution") or {}).get("candidates") or []:
                metric = candidate.get("metric") or {}
                if self._is_ratio_metric(metric):
                    continue
                key = metric.get("metric_id")
                if not key or key in seen:
                    continue
                seen.add(key)
                trial = self.build(rest_text, intent_result=intent_result, selected_metric_id=key)
                if trial.get("status") == "ready" and (
                    trial.get("mode") == "grouped" or any(
                        f.get("type") == "categorical" and not f.get("temporal")
                        for f in trial.get("filters") or []
                    )
                ):
                    viable.append({**candidate, "_trial": trial})
            if default.get("status") == "resolved" and any(
                self._metric_key(c["metric"]) == self._metric_key(default["metric"]) for c in viable
            ):
                return default
            # Entre los válidos, los que filtran por una columna que el
            # tablero muestra con ese indicador (no una columna técnica sin
            # visual) tienen evidencia de que esa participación tiene sentido.
            shown = [c for c in viable if not c["_trial"].get("technical_columns_used")]
            for group, why in (
                (viable, "el único donde el valor pedido es un filtro válido"),
                (shown, "el único donde el valor pedido se filtra por una columna que el tablero muestra"),
            ):
                if len(group) == 1:
                    metric = group[0]["metric"]
                    where = metric.get("report") or metric.get("semantic_model")
                    return {
                        "status": "resolved", "metric": metric,
                        "note": (
                            f"«{metric.get('label')}» existe en varios tableros; usé el de {where}, "
                            f"{why} para calcular la participación."
                        ),
                    }
            viable = [{k: v for k, v in c.items() if k != "_trial"} for c in viable]
            ambiguous = dict(plan)
            if viable:
                ambiguous["metric_resolution"] = {
                    **(plan.get("metric_resolution") or {}), "candidates": viable,
                }
            ambiguous["question"] = rest_text
            ambiguous["composite"] = True
            ambiguous["composite_context"] = {
                "question": question, "part": "share", "part_text": rest_text,
                "selections": {}, "ready_labels": [],
            }
            return ambiguous
        if default.get("status") == "resolved":
            return default
        return {
            "status": default.get("status", "not_found"),
            "stage": "metric", "question": question,
            "source_context": source_context,
            "metric_resolution": default, "composite": True,
        }

    # ---------------- compuestas por coordinación de partes ----------------
    # «cirugías programadas y realizadas», «interconsultas solicitadas y
    # respondidas», «pacientes atendidos y no atendidos» (coordinación
    # elíptica: la segunda parte comparte el sustantivo de la primera) y
    # «total de triages y promedio mensual de triages» (partes completas).
    # Inicio del resto común (periodo, filtros, tablero) tras la última parte.
    _COORD_HARD_STOPS = {
        "en", "durante", "para", "por", "segun", "desde", "hasta", "entre",
        "este", "esta", "ultimo", "ultimos", "ultima", "ultimas", "hoy", "ayer",
        "agrupado", "agrupada", "desglosado", "desglosada",
    }
    _COORD_VERBS = {
        "hubo", "hay", "fue", "fueron", "tuvo", "tuvieron", "tiene", "tienen",
        "se", "registro", "registraron", "llevamos", "lleva", "van", "va",
    }
    # Palabras de petición/interrogativas antes de cada parte.
    _COORD_LEAD = {
        "cuanto", "cuanta", "cuantos", "cuantas", "cual", "cuales", "que", "dime",
        "dame", "muestrame", "muestra", "indica", "indicame", "necesito", "saber",
        "quiero", "quisiera", "conocer", "consultar", "me", "puedes", "podrias",
        "decir", "dar", "el", "la", "los", "las", "y", "e", "tambien", "ademas",
    }
    _COORD_ARTICLES = {"el", "la", "los", "las"}
    # Terminaciones de participios/adjetivos («programadas», «atendidos»,
    # «ambulatorias»): solo entre ellas se completa la parte elíptica.
    _COORD_ADJ_RE = re.compile(
        r"(?:ad[oa]s?|id[oa]s?|ert[oa]s?|uest[oa]s?|ales?|ic[oa]s?|iv[oa]s?|ari[oa]s?|ori[oa]s?)$"
    )

    @staticmethod
    def _coord_tokens(question):
        """Tokens normalizados conservando las comas (separan partes)."""
        tokens = []
        for index, chunk in enumerate(str(question or "").split(",")):
            if index:
                tokens.append(",")
            tokens.extend(normalize_text(chunk).split())
        return tokens

    def _is_coord_stop(self, token):
        return (
            token in self._COORD_HARD_STOPS or token in self._COORD_VERBS
            or token in MONTHS or bool(re.fullmatch(r"(?:19|20)\d{2}", token))
        )

    def _coordination_splits(self, question, protected_spans=()):
        """Posibles divisiones de la pregunta en partes coordinadas.

        Cada división: {"parts": [{"text", "sub_question", "elliptical",
        "fallback"}], "conjunction": índice}. La primera parte va desde el
        inicio de la frase nominal (tras «cuántas», «el»...) hasta la
        conjunción; las siguientes, hasta el resto común (periodo, «en ...»,
        «de ...», verbo). El resto común se agrega a cada sub-pregunta.
        """
        tokens = self._coord_tokens(question)
        splits = []
        normalized = " ".join(t for t in tokens if t != ",")
        # Posición en el texto normalizado de cada token (para no partir el
        # nombre literal de un indicador como «INGRESOS Y EGRESOS»).
        offsets, cursor = [], 0
        for token in tokens:
            if token == ",":
                offsets.append(cursor)
                continue
            offsets.append(cursor)
            cursor += len(token) + 1

        for k, token in enumerate(tokens):
            if token not in ("y", "e") or k == 0:
                continue
            if any(start <= offsets[k] < end for start, end in protected_spans):
                continue
            # ---- partes antes de la conjunción (la primera y las separadas
            # por comas: «programadas, realizadas y canceladas»), hacia atrás
            # hasta una parada (periodo, «en», verbo) o una palabra de petición.
            segments = []
            end = k
            while True:
                start = end - 1
                while start >= 0:
                    word = tokens[start]
                    if word == "," or self._is_coord_stop(word):
                        break
                    if word in self._COORD_LEAD:
                        previous = tokens[start - 1] if start > 0 else ""
                        if not (word in self._COORD_ARTICLES and previous in ("de", "del", "a", "al")):
                            break
                    start -= 1
                if start + 1 >= end:
                    break
                segments.insert(0, (start + 1, end))
                if start >= 0 and tokens[start] == "," and end - start - 1 <= 3 and len(segments) < 6:
                    end = start
                    continue
                break
            if not segments:
                continue
            first = tokens[segments[0][0]:segments[0][1]]
            middles = [tokens[a:b] for a, b in segments[1:]]
            if not any(w not in self._COORD_LEAD for w in first):
                continue
            prefix = [t for t in tokens[:segments[0][0]] if t != ","]
            # ---- última parte: tras la conjunción hasta el resto común
            pos = k + 1
            own_lead = []
            while pos < len(tokens) and tokens[pos] in self._COORD_LEAD:
                own_lead.append(tokens[pos])
                pos += 1
            last_start = pos
            if pos < len(tokens) and tokens[pos] in ("no", "sin"):
                pos += 1
            while pos < len(tokens):
                word = tokens[pos]
                if word in (",", "y", "e", "de", "del") or self._is_coord_stop(word):
                    break
                pos += 1
            last = tokens[last_start:pos]
            if not last or all(w in ("no", "sin") for w in last):
                continue
            rest = [t for t in tokens[pos:] if t != ","]
            others = [*middles, last]
            parts = [{"text": " ".join(first), "words": first, "own_lead": False}]
            for words in others:
                parts.append({
                    "text": " ".join(words), "words": words,
                    "own_lead": bool(own_lead) and words is last,
                })
            splits.append({
                "conjunction": k, "prefix": prefix, "first": first,
                "parts": parts, "rest": rest, "normalized": normalized,
            })
        return splits

    def _coordination_variants(self, split):
        """Sub-preguntas de cada parte: elíptica («cirugías» + «realizadas»)
        y, como respaldo, la parte tal cual."""
        first = split["first"]
        prefix, rest = split["prefix"], split["rest"]
        # «total de triages y promedio mensual de triages»: el «de triages»
        # del resto ya está en la primera parte (no se repite).
        rest_first = rest
        if rest and rest[0] in ("de", "del"):
            end = 1
            while end < len(rest) and rest[end] not in ("de", "del") and not self._is_coord_stop(rest[end]):
                end += 1
            segment = [w for w in rest[1:end] if w not in self._COORD_ARTICLES]
            if segment and all(w in first for w in segment):
                rest_first = rest[end:]
        variants = [[{
            "text": " ".join(first), "elliptical": False,
            "sub_question": " ".join([*prefix, *first, *rest_first]),
        }]]
        head = first[:-1]
        last_first = first[-1]
        for part in split["parts"][1:]:
            words = part["words"]
            content = [w for w in words if w not in ("no", "sin")]
            options = []
            if (
                head and len(content) == 1
                and self._COORD_ADJ_RE.search(last_first) and self._COORD_ADJ_RE.search(content[0])
            ):
                expanded = [*head, *words]
                options.append({
                    "text": " ".join(expanded), "elliptical": True,
                    "shared": " ".join(head), "original": " ".join(words),
                    "sub_question": " ".join([*prefix, *expanded, *rest]),
                })
            options.append({
                "text": " ".join(words), "elliptical": False,
                "sub_question": " ".join([*prefix, *words, *rest]),
            })
            variants.append(options)
        return variants

    def _coordinated_composite(self, question, intent_result, source_context, selections):
        """Compuesta por partes coordinadas o None si la pregunta no lo es.

        Exige al menos dos partes resueltas con indicadores DISTINTOS (si
        coinciden, la «y» une valores de filtro o dimensiones: flujo normal).
        Una parte ambigua se contrapregunta (con el contexto para retomar la
        compuesta); una parte que no se resuelve se declara.
        """
        normalized = normalize_text(question)
        # «cuántas camas ocupadas hay en uci y cuáles son»: la «y» pide el
        # listado del mismo indicador (answer_shape), no otra medida.
        request = detail_request(question)
        if request is not None and request.get("cue") == "y cuales":
            return None
        protected = [
            (m["start"], m["end"])
            for m in self._mentioned_metrics(normalized, source_context)
            if re.search(r"(?<![a-z0-9])(?:y|e)(?![a-z0-9])", m["name"])
        ]
        for split in self._coordination_splits(question, protected):
            result = self._evaluate_coordination(
                question, split, intent_result, source_context, selections,
            )
            if result is not None:
                return result
        return None

    def _evaluate_coordination(self, question, split, intent_result, source_context, selections):
        built = []
        for index, options in enumerate(self._coordination_variants(split)):
            chosen_id = selections.get(str(index))
            outcome = None
            for option in options:
                plan = self.build(
                    option["sub_question"], intent_result=intent_result,
                    selected_metric_id=chosen_id,
                )
                outcome = {**option, "index": index, "plan": plan}
                if plan.get("status") in ("ready", "ambiguous"):
                    break
            built.append(outcome)

        ready = [b for b in built if b["plan"].get("status") == "ready"]
        keys = {self._metric_key(b["plan"]["metric"]) for b in ready}
        # Una parte ambigua solo cuenta si ofrece indicadores distintos de los
        # ya resueltos; si no, se declara como no resuelta.
        ambiguous = []
        for b in built:
            if b["plan"].get("status") != "ambiguous":
                continue
            resolution = b["plan"].get("metric_resolution") or {}
            options = [
                c for c in resolution.get("candidates") or []
                if self._metric_key(c.get("metric") or {}) not in keys
            ]
            if options:
                b["plan"] = {**b["plan"], "metric_resolution": {**resolution, "candidates": options}}
                ambiguous.append(b)
            else:
                b["plan"] = {**b["plan"], "status": "not_found"}
        if not ready or len(keys) + len(ambiguous) < 2 or (len(keys) < 2 and not ambiguous):
            return None
        if len(keys) < len(ready):
            return None  # Dos partes con el mismo indicador: la «y» une filtros.

        # «peso de antifluidos y urgencias»: «urgencias» es un valor de filtro
        # del primer indicador, no otro indicador.
        first = built[0]
        if first["plan"].get("status") == "ready":
            first_metric = first["plan"]["metric"]
            first_filters = {
                (normalize_text(f.get("table")), normalize_text(f.get("column")), str(f.get("value")))
                for f in first["plan"].get("filters") or []
            }
            for item in built[1:]:
                if item["elliptical"] or len(item["text"].split()) > 2:
                    continue
                trial = self.build(
                    " ".join([*split["prefix"], *split["first"], "de", item["text"], *split["rest"]]),
                    intent_result=intent_result,
                    selected_metric_id=first_metric.get("metric_id"),
                )
                extra = [
                    f for f in trial.get("filters") or []
                    if f.get("type") == "categorical" and not f.get("temporal")
                    and (normalize_text(f.get("table")), normalize_text(f.get("column")), str(f.get("value")))
                    not in first_filters
                ]
                if trial.get("status") == "ready" and extra:
                    return None

        split_note = None
        elliptical = [b for b in built if b.get("elliptical")]
        if elliptical:
            # La segunda parte comparte el sustantivo de la primera.
            split_note = "Interpreté " + ", ".join(
                f"«{b['original']}» como «{b['text']}»" for b in elliptical
            ) + "."

        if ambiguous:
            target = ambiguous[0]
            plan = dict(target["plan"])
            plan["composite"] = True
            plan["composite_context"] = {
                "question": question, "part": str(target["index"]),
                "part_text": target["text"], "selections": dict(selections),
                "ready_labels": [b["plan"]["metric"].get("label") for b in ready],
                "parts": [b["text"] for b in built],
            }
            return plan

        # Todas las partes se presentan con la agrupación de la primera.
        signature = self._grouping_signature(ready[0]["plan"])
        items, failed_labels, failures = [], [], []
        for b in built:
            plan = b["plan"]
            if plan.get("status") != "ready":
                plan["composite"] = True
                failures.append(plan)
                failed_labels.append(b["text"])
                continue
            if self._grouping_signature(plan) != signature:
                failed_labels.append(f"{b['text']} (con otra agrupación)")
                continue
            plan["question"] = question
            plan["composite_sub_question"] = b["sub_question"]
            items.append({
                "kind": "metric", "plan": plan, "label": plan["metric"].get("label"),
                "part": b["text"],
            })
        if len(items) < 2:
            return None
        return {
            "status": "composite", "question": question, "items": items,
            "unresolved": [], "failures": failures, "failed_labels": failed_labels,
            "source_context": source_context,
            "grouped": items[0]["plan"].get("mode") == "grouped",
            "split": "coordination",
            "split_parts": [b["text"] for b in built],
            "notes": [split_note] if split_note else [],
        }

    # ---------------- «cuántas X» ≈ «total de X» ----------------
    _COUNT_WORDS_RE = re.compile(
        r"(?<![a-z0-9])(?:cuant[oa]s?|numero\s+(?:de|del)|cantidad\s+(?:de|del))(?![a-z0-9])"
    )

    def _total_variant(self, question):
        """Variante «total de ...» de una pregunta de conteo: «cuántas
        atenciones hubo» o «atenciones de urgencias» -> «total de atenciones...»."""
        text = normalize_text(question)
        if not text or re.search(r"(?<![a-z0-9])totale?s?(?![a-z0-9])", text):
            return None
        variant, replaced = self._COUNT_WORDS_RE.subn("total de", text, count=1)
        return variant if replaced else f"total de {text}"

    def _resolve_metric_flexible(self, question, source_context, selected_metric_id=None, **kwargs):
        """_resolve_metric que, si no encuentra indicador, prueba la variante
        «total de ...» SOLO cuando las palabras de la pregunta señalan un único
        indicador del catálogo (p. ej. TOTAL ATENCIONES). Con varios candidatos
        («cuántas cirugías»: total / realizadas / programadas) se mantiene el
        resultado original para que se contrapregunte."""
        result = self._resolve_metric(
            question, source_context, selected_metric_id=selected_metric_id, **kwargs
        )
        if selected_metric_id is not None or result.get("status") != "not_found":
            return result
        variant = self._total_variant(question)
        if not variant:
            return result
        related = self._metric_suggestions(self._metric_business_question(question, source_context))
        related_keys = {self._logical_key(item["metric"]) for item in related}
        if len(related_keys) != 1:
            return result
        alternative = self._resolve_metric(variant, source_context, **kwargs)
        if (
            alternative.get("status") != "resolved"
            or self._logical_key(alternative["metric"]) not in related_keys
        ):
            return result
        alternative["interpretation"] = (
            f"«{normalize_text(question)}» se interpretó como «{variant}» "
            "(único indicador del catálogo con esas palabras)"
        )
        return alternative

    # ---------------- respaldo del indicador elegido ----------------
    def _metric_evidence_rejection(self, question, metric, metric_result, group_by,
                                   explicit_specs, source_context):
        """Plan not_found si el indicador se eligió solo por las palabras de la
        agrupación o de un filtro («citas asignadas por especialidad» no es
        CIRUGÍAS REALIZADAS aunque una de sus visuales se llame «Cirugías por
        especialidad»). Con ello se contrapregunta en lugar de responder."""
        ignored = {
            canonical_token(word)
            for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
        } | {"por", "segun", "total"}
        dimension_tokens = set()
        for field in [*group_by, *(spec["field"] for spec in explicit_specs)]:
            # El nombre de la tabla («ATENCIONES.SEDE») no nombra la dimensión.
            table_tokens = set(canonical_tokens(field.get("table")))
            for alias in field.get("aliases", []) or []:
                dimension_tokens.update(set(canonical_tokens(alias)) - table_tokens)
        if not dimension_tokens:
            return None

        words = [
            word for word in normalize_text(question).split()
            if canonical_token(word) not in ignored and not word.isdigit()
            and len(word) >= 3 and not _is_request_word(canonical_token(word))
        ]
        distinctive = [word for word in words if canonical_token(word) not in dimension_tokens]
        name_tokens = set()
        for name in self._metric_names(metric):
            name_tokens.update(canonical_tokens(name))
        evidence = [
            word for word in distinctive
            if any(_token_similarity(canonical_token(word), other) >= 0.82 for other in name_tokens)
        ]
        if evidence:
            return None

        # Palabras de la pregunta, sin las de la agrupación/filtro, para buscar
        # indicadores parecidos que ofrecer como opciones.
        remaining = " ".join(
            word for word in normalize_text(question).split()
            if canonical_token(word) not in dimension_tokens
        )
        resolved_routing = source_context.get("status") == "resolved"
        strong = resolved_routing and source_context.get("routing_strength") == "strong"
        model_hint = (
            normalize_text(source_context.get("semantic_model"))
            if resolved_routing and source_context.get("routing_strength") in ("strong", "weak") else ""
        )
        suggestions = [
            item for item in self._metric_suggestions(
                self._metric_business_question(remaining, source_context),
                model_hint=model_hint, strong=strong,
            )
            if self._logical_key(item["metric"]) != self._logical_key(metric)
        ]
        return {
            "status": "not_found",
            "stage": "metric",
            "reason": "metric_matched_only_dimension_words",
            "question": question,
            "source_context": source_context,
            "unresolved_text": " ".join(distinctive),
            "rejected_metric": {
                "metric_id": metric.get("metric_id"), "label": metric.get("label"),
                "matched_name": metric_result.get("matched_name"),
            },
            "metric_resolution": {
                "status": "not_found", "candidates": [],
                "suggestions": [
                    {key: value for key, value in item.items() if not key.startswith("_")}
                    for item in suggestions
                ],
            },
        }

    def _metric_without_group_phrase(self, question, metric_result, group_by, source_context):
        """La agrupación («por especialidad») no debe elegir el indicador.

        Se vuelve a resolver la pregunta sin esa frase; si así se identifica
        con certeza OTRO indicador («total de cirugías por especialidad» ->
        TOTAL CIRUGÍAS y no la visual «Cirugías por especialidad»), se usa ese.
        Si sin la frase queda ambiguo o sin indicador, se conserva el original.
        """
        if not group_by:
            return None
        text = normalize_text(question)
        stripped = text
        for field in group_by:
            aliases = sorted(
                {normalize_text(alias) for alias in field.get("aliases", []) or [] if normalize_text(alias)},
                key=len, reverse=True,
            )
            for alias in aliases:
                stripped = re.sub(
                    r"(?<![a-z0-9])(?:por|segun|agrupad[oa]\s+por|desglosad[oa]\s+por)\s+"
                    r"(?:el\s+|la\s+|los\s+|las\s+)?" + re.escape(alias) + r"(?![a-z0-9])",
                    " ", stripped,
                )
        stripped = re.sub(r"\s+", " ", stripped).strip()
        if not stripped or stripped == text:
            return None
        alternative = self._resolve_metric_flexible(stripped, source_context)
        if (
            alternative.get("status") != "resolved"
            or self._logical_key(alternative["metric"]) == self._logical_key(metric_result["metric"])
        ):
            return None
        alternative["interpretation"] = (
            f"el indicador se eligió sin la agrupación («{stripped}»): "
            f"{alternative['metric'].get('label')} en lugar de "
            f"{metric_result['metric'].get('label')} (que coincidía por «{metric_result.get('matched_name')}»)"
        )
        return alternative

    # ---------------- «M por X» con un indicador que no se desglosa por X ----------------
    _GROUP_TAIL_RE = re.compile(
        r"(?<![a-z0-9])(?:por|segun|agrupad[oa]s?\s+por|desglosad[oa]s?\s+por)\s+"
        r"(?:(?:el|la|los|las|cada)\s+)?(.+)$"
    )

    def _requested_group_tail(self, question):
        """Lo que sigue a «por/según» en la pregunta, sin el periodo («ocupación
        por servicio hoy» -> «servicio»), o None."""
        text = self._analyze_periods(question)["clean_question"]
        match = self._GROUP_TAIL_RE.search(text)
        tail = match.group(1).strip() if match else ""
        return tail or None

    def _group_field_in(self, tail, fields):
        """Campo de `fields` que nombra el comienzo de `tail` («aseguradores» ->
        TERNOMCOM «ASEGURADORA»), sin columnas temporales; o None."""
        if not tail:
            return None
        # Primero el filtro barato (algún alias abre `tail`); luego el mejor
        # de esos por coincidencia y relevancia, como `_best_dimension`.
        named = [
            field for field in fields
            if any(_alias_prefix(tail, alias) for alias in field.get("aliases") or [])
        ]
        return self._best_dimension(tail, named, exclude_temporal=True) if named else None

    def _group_topic_words(self, question, source_context, tail):
        """Palabras del tema de «detalle de ocupación por aseguradores»
        («ocupacion»): sin la agrupación, unidades ni palabras de página genéricas."""
        ignored = {canonical_token(word) for word in self._OPTION_UNIT_WORDS
                   | self._PAGE_IGNORED_NAME_WORDS | GENERIC_PAGE_WORDS}
        ignored |= set(canonical_tokens(tail))
        return [word for word in self._option_words(question, source_context) if word not in ignored]

    def _table_pages(self, semantic_model, table):
        """Páginas del informe que usan la tabla (columnas en visuales o
        indicadores de esa tabla): PACIENTES X ASEGURADORA -> DETALLE OCUPACIÓN."""
        index = self.__dict__.get("_table_pages_index")
        if index is None:
            index = {}
            for field in self.dimension_fields or []:
                key = (normalize_text(field.get("semantic_model")), normalize_text(field.get("table")))
                if field.get("page") and field["page"] not in index.setdefault(key, []):
                    index[key].append(field["page"])
            for metric in self.metrics:
                key = (normalize_text(metric.get("semantic_model")), normalize_text(metric.get("table")))
                for page in self._metric_pages(metric):
                    if page not in index.setdefault(key, []):
                        index[key].append(page)
            self._table_pages_index = index
        return list(index.get((normalize_text(semantic_model), normalize_text(table)), []))

    def _metric_topic_page(self, metric, words):
        """Página (de sus visuales o de su tabla) cuyo nombre explica TODAS las
        palabras del tema («ocupacion» -> DETALLE OCUPACIÓN); "" si las explica
        el nombre/tabla del indicador; None si nada las explica."""
        if not words:
            return None
        pages = _unique_strings([
            *self._metric_pages(metric),
            *self._table_pages(metric.get("semantic_model"), self._metric_fact_table(metric)),
        ])
        for page in pages:
            tokens = self._page_name_tokens(page)
            if tokens and all(self._explains(word, tokens) for word in words):
                return page
        vocabulary = self._metric_vocabulary_tokens(metric, with_pages=False)
        if all(self._explains(word, vocabulary) for word in words):
            return ""
        return None

    def _groupable_on_topic(self, metric, tail, words):
        """¿El indicador se desglosa por `tail` y su página/nombre trata el tema?"""
        return (
            self._metric_topic_page(metric, words) is not None
            and self._group_field_in(tail, self._metric_dimensions(metric)) is not None
        )

    def _group_siblings(self, question, source_context, tail, models, exclude=()):
        """Indicadores de esos modelos que SÍ se desglosan por `tail` y cuya
        página o nombre trata el tema de la pregunta («detalle de ocupación por
        aseguradores»: %OCUPACION no tiene aseguradora, pero la página DETALLE
        OCUPACIÓN cuenta los pacientes de PACIENTES X ASEGURADORA por
        TERNOMCOM). Uno por expresión (TOTAL PACIENTES = PACIENTES por
        ASEGURADORA): el de la página del tema, tarjeta, nombre más corto."""
        words = self._group_topic_words(question, source_context, tail)
        if not words or not tail:
            return []
        models = {normalize_text(model) for model in models if model}
        excluded = {self._logical_key(metric) for metric in exclude}
        groups = {}
        for metric in self.metrics:
            model = metric.get("semantic_model")
            if (
                metric.get("validation_status") != "approved" or normalize_text(model) not in models
                or self._logical_key(metric) in excluded
            ):
                continue
            page = self._metric_topic_page(metric, words)
            if page is None:
                continue
            field = self._group_field_in(tail, self._metric_dimensions(metric))
            if field is None:
                continue
            key = (normalize_text(model), normalize_text(self._measure_expression(model, metric)))
            groups.setdefault(key, []).append({"metric": metric, "page": page, "field": field, "words": words})

        def rank(item):
            metric = item["metric"]
            on_page = [a for a in metric.get("appearances") or []
                       if normalize_text(a.get("page_display_name")) == normalize_text(item["page"])]
            generic = bool(re.match(r"^(?:recuento|conteo|count|suma|sum)\b", normalize_text(metric.get("label"))))
            return (
                0 if on_page else 1,
                0 if any(normalize_text(a.get("visual_type")) == "card" for a in on_page) else 1,
                1 if generic else 0,
                len(str(metric.get("label") or "")),
            )

        return [sorted(members, key=rank)[0] for members in groups.values()]

    def _ungroupable_text(self, metrics, tail, question):
        """«%OCUPACION no se puede desglosar por aseguradores: su tabla CAMAS
        DISPONIBLES no tiene esa columna ni se relaciona con una que la tenga.»"""
        labels = _unique_strings(metric.get("label") for metric in metrics)
        tables = _unique_strings(self._metric_fact_table(metric) for metric in metrics)
        dimension = _original_phrase(question, tail.split()[0]) if tail else "esa dimensión"
        if len(labels) == 1:
            where = f"su tabla {tables[0]}" if tables else "su tabla"
            return (
                f"{labels[0]} no se puede desglosar por {dimension}: {where} no tiene esa columna "
                "ni se relaciona con una que la tenga."
            )
        listed = ", ".join(labels[:-1]) + " y " + labels[-1]
        return f"{listed} no se pueden desglosar por {dimension}: sus tablas no tienen esa columna."

    def _group_sibling_note(self, originals, sibling, tail, question):
        """Nota visible: qué no se pudo desglosar y qué se muestra en su lugar."""
        metric = sibling["metric"]
        field = sibling["field"]
        topic = " ".join(_original_phrase(question, word) for word in sibling.get("words") or [])
        where = metric.get("report") or metric.get("semantic_model")
        if sibling.get("page"):
            where = f"{where} › página {sibling['page']}"
        name = (field.get("aliases") or [field.get("column")])[0]
        lead = f"Para ver «{topic}» por {name.lower()}" if topic else "En su lugar"
        return (
            f"{self._ungroupable_text(originals, tail, question)} {lead} se muestra "
            f"{metric.get('label')} ({where}), que sí se desglosa por {name}."
        )

    def _group_sibling_plan(self, question, intent_result, originals, tail, source_context, why_prefix=""):
        """Plan con el único indicador hermano que se desglosa por `tail`, o None."""
        models = _unique_strings(metric.get("semantic_model") for metric in originals)
        siblings = self._group_siblings(question, source_context, tail, models, exclude=originals)
        if len(siblings) != 1:
            if siblings:
                self._note(
                    f"varios indicadores se desglosan por «{tail}» y tratan el tema: "
                    + ", ".join(str(item["metric"].get("label")) for item in siblings[:5])
                )
            return None
        sibling = siblings[0]
        note = self._group_sibling_note(originals, sibling, tail, question)
        item = {"metric": sibling["metric"], "matched_name": sibling["metric"].get("label"), "score": None}
        return self._forced_plan(
            question, intent_result, item,
            f"{why_prefix}{self._ungroupable_text(originals, tail, question)} Se usa el indicador del "
            f"mismo tablero que sí se desglosa por «{tail}» y trata el tema de la pregunta",
            consumed_tokens=self._option_words(question, source_context),
            visible_note=note, group_sibling=True,
        )

    _VALUE_ROLES = {"values", "y", "y2", "size", "tooltips", "tooltip"}

    def _shown_by_field(self, metric, field):
        """¿Algún visual del tablero muestra este indicador desglosado por esa
        columna (eje, categoría, filas o leyenda del MISMO visual)?"""
        visual_ids = {str(value) for value in self._metric_visual_ids(metric)}
        if not visual_ids or not field:
            return False
        model = normalize_text(metric.get("semantic_model"))
        table, column = normalize_text(field.get("table")), normalize_text(field.get("column"))
        return any(
            str(item.get("visual_id")) in visual_ids
            and normalize_text(item.get("semantic_model")) == model
            and normalize_text(item.get("table")) == table
            and normalize_text(item.get("column")) == column
            and normalize_text(item.get("role")) not in self._VALUE_ROLES
            for item in self.dimension_fields or []
        )

    def _group_shown_option(self, question, intent_result, plan, groupable, tail):
        """«M por X» y todas las opciones se desglosan por X: si todas miden la
        misma tabla del mismo modelo (variantes del mismo conteo: PACIENTES
        de NAOS como DISTINCTCOUNT de AINCONSEC en la tarjeta y de ADNINGRESO en
        la dona por servicio) y un solo indicador aparece en un visual
        desglosado por X, ese es el que el tablero usa para responder: se
        responde con él. Opciones de tablas o modelos distintos siguen siendo
        una ambigüedad real (None: se contrapregunta)."""
        owners = {
            (normalize_text(item["metric"].get("semantic_model")), normalize_text(self._metric_fact_table(item["metric"])))
            for item in groupable
        }
        if len(owners) != 1:
            return None
        shown = []
        for item in groupable:
            field = self._group_field_in(tail, self._metric_dimensions(item["metric"]))
            if self._shown_by_field(item["metric"], field):
                shown.append(item)
        if len({self._logical_key(item["metric"]) for item in shown}) != 1 or len(shown) == len(groupable):
            return None
        chosen = shown[0]
        source_context = plan.get("source_context") or {}
        return self._forced_plan(
            question, intent_result, chosen,
            f"todas las opciones miden la tabla {self._metric_fact_table(chosen['metric'])}; solo esta aparece "
            f"en un visual del tablero desglosada por «{tail}»: se responde con ella",
            consumed_tokens=self._option_words(question, source_context),
        )

    def _group_feasible_options(self, question, intent_result, plan):
        """Contrapregunta de «M por X» (sin opción elegida): las opciones que no
        se pueden desglosar por X no responden la pregunta.
        - Algunas sí y otras no: quedan solo las que sí (una -> se responde).
        - Ninguna: el indicador hermano del mismo tablero que sí se desglosa
          por X y trata el tema (página DETALLE OCUPACIÓN), si es uno solo.
        Devuelve un plan o None (sin cambios)."""
        if plan.get("status") != "ambiguous" or plan.get("reason") is not None:
            return None
        tail = self._requested_group_tail(question)
        resolution = plan.get("metric_resolution") or {}
        items = list(resolution.get("candidates") or [])
        if not tail or len(items) < 2:
            return None
        groupable = [
            item for item in items
            if self._group_field_in(tail, self._metric_dimensions(item.get("metric") or {})) is not None
        ]
        source_context = plan.get("source_context") or {}
        if not groupable:
            return self._group_sibling_plan(
                question, intent_result, [item["metric"] for item in items], tail, source_context,
            )
        if len(groupable) == len(items):
            return self._group_shown_option(question, intent_result, plan, groupable, tail)
        others = [item["metric"] for item in items if item not in groupable]
        text = self._ungroupable_text(others, tail, question)
        self._note(f"opciones depuradas: {text}")
        if len({self._logical_key(item["metric"]) for item in groupable}) == 1:
            chosen = groupable[0]
            words = self._group_topic_words(question, source_context, tail)
            page = self._metric_topic_page(chosen["metric"], words)
            note = self._group_sibling_note(
                others, {"metric": chosen["metric"], "page": page,
                         "field": self._group_field_in(tail, self._metric_dimensions(chosen["metric"])),
                         "words": words},
                tail, question,
            )
            return self._forced_plan(
                question, intent_result, chosen,
                f"única opción que se desglosa por «{tail}»; {text}",
                consumed_tokens=self._option_words(question, source_context),
                visible_note=note, group_sibling=True,
            )
        return {**plan, "metric_resolution": {**resolution, "candidates": groupable}}

    # ---------------- ranking («top 5», «el servicio con más peso») ----------------
    _RANKING_WORDS = {"top", "mas", "mayor", "mayores", "menos", "menor", "menores", "ranking"}
    # «con más de 3 días» / «más que» comparan con una cifra: no son ranking.
    _RANKING_HINT_RE = re.compile(
        r"(?<![a-z0-9])(?:top\s+\d{1,2}|ranking|"
        r"(?:con|tuvo|tiene|tuvieron|tienen|registro|registraron|hizo|hicieron)\s+"
        r"(?:el\s+|la\s+|los\s+|las\s+)?(?:mas|mayor|menos|menor)(?:es)?)(?![a-z0-9])"
        r"(?!\s+(?:de|que)(?![a-z0-9]))"
    )
    _NUMBER_WORDS = {
        "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
        "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    }

    def _mentions_ranking(self, normalized):
        return bool(self._RANKING_HINT_RE.search(normalized))

    def is_ranking(self, question):
        """«top 5 ...», «el servicio con más ...»: pide orden/límite sobre un indicador."""
        return self._mentions_ranking(normalize_text(question))

    def _detect_ranking(self, question, candidates, group_by=None):
        """Orden y límite sobre una agrupación.

        «cuál fue el servicio con más peso» -> SERVICIO, desc, 1;
        «top 5 especialidades con más cirugías» -> ESPECIALIDAD, desc, 5;
        «las sedes con menos atenciones» -> SEDE, asc, sin límite.
        Devuelve None si la pregunta no pide un ranking.
        """
        text = normalize_text(question)
        if not self._mentions_ranking(text):
            return None
        verb = (
            r"(?:con|que\s+(?:tuvo|tiene|tuvieron|tienen|registro|registraron|hizo|hicieron)|"
            r"tuvo|tiene|tuvieron|tienen)\s+(?:el\s+|la\s+|los\s+|las\s+)?"
            r"(?P<dir>mas|mayor(?:es)?|menos|menor(?:es)?)(?![a-z0-9])"
            r"(?!\s+(?:de|que)(?![a-z0-9]))"
        )
        number = r"(?P<n>\d{1,2}|" + "|".join(self._NUMBER_WORDS) + r")"
        fields = [field for field in (group_by or [])] or [
            field for field in candidates if not self._is_temporal_field(field)
        ]
        best = None
        for field in fields:
            aliases = sorted(
                {normalize_text(alias) for alias in field.get("aliases", []) or [] if normalize_text(alias)},
                key=len, reverse=True,
            )
            for alias in aliases:
                if len(alias) < 3:
                    continue
                escaped = re.escape(alias)
                match = re.search(
                    r"(?:(?:top|los|las|primeros|primeras)\s+" + number + r"\s+)?"
                    r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])\s+" + verb,
                    text,
                )
                top = None
                if not match:
                    top = re.search(
                        r"(?<![a-z0-9])top\s+" + number + r"\s+" + escaped + r"(?![a-z0-9])", text,
                    )
                    if not top:
                        continue
                found = match or top
                raw_n = found.groupdict().get("n")
                limit = None
                if raw_n:
                    limit = int(raw_n) if raw_n.isdigit() else self._NUMBER_WORDS.get(raw_n)
                direction_word = (match.group("dir") if match else "mas")
                direction = "asc" if direction_word.startswith(("menos", "menor")) else "desc"
                plural = alias.endswith("s") and canonical_token(alias) != alias
                if limit is None and match and not plural:
                    limit = 1  # «el servicio con más peso»: solo el primero
                candidate = {
                    "field": field, "direction": direction, "limit": limit,
                    "phrase": found.group(0).strip(),
                    "tokens": {canonical_token(word) for word in self._RANKING_WORDS},
                }
                if best is None or len(candidate["phrase"]) > len(best["phrase"]):
                    best = candidate
                break
        return best

    @staticmethod
    def _ranking_note(ranking, label):
        order = "de menor a mayor" if ranking.get("direction") == "asc" else "de mayor a menor"
        limit = ranking.get("limit")
        if limit == 1:
            which = "menor" if ranking.get("direction") == "asc" else "mayor"
            return f"Se muestra solo el {label} con {which} valor."
        if limit:
            return f"Ordenado {order}; se muestran los {limit} primeros ({label})."
        return f"Ordenado {order} ({label})."

    # ---------------- preguntas sin indicador ----------------
    _GENERIC_MEASURE_WORDS = {
        "promedio", "media", "mensual", "mensuales", "anual", "anuales", "diario",
        "diaria", "semanal", "porcentaje", "porcentual", "suma", "sumatoria", "tasa",
        "variacion", "proporcion", "participacion", "indicador", "indicadores",
        "metrica", "metricas", "resultado", "resultados", "pendiente", "pendientes",
    }

    def _catalog_vocabulary(self):
        """Palabras (canónicas) que el catálogo conoce: nombres de indicadores,
        informes, páginas, modelos y alias de dimensiones."""
        if getattr(self, "_vocabulary", None) is not None:
            return self._vocabulary
        values = []
        for metric in self.metrics:
            if metric.get("validation_status") != "approved":
                continue
            values.extend(self._metric_names(metric))
            values.extend(self._metric_reports(metric))
            values.extend(self._metric_pages(metric))
            values.append(metric.get("semantic_model"))
        for field in self.dimension_fields:
            values.extend(field.get("aliases", []) or [])
            values.extend([field.get("report"), field.get("page"), field.get("semantic_model")])
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_PAGE_WORDS}
        vocabulary = set()
        for value in values:
            for token in canonical_tokens(value):
                if len(token) >= 3 and token not in ignored and not token.isdigit():
                    vocabulary.add(token)
        self._vocabulary = vocabulary
        return vocabulary

    def catalog_examples(self, limit=2):
        """Indicadores reales para dar ejemplos: uno por modelo, visibles en un
        tablero y sin cifras en el nombre. -> [{"label", "report"}]."""
        by_model = {}
        for metric in self._dedupe_metrics(self.metrics):
            label = str(metric.get("label") or "").strip()
            if (
                metric.get("validation_status") != "approved" or not label
                or not (metric.get("appearances") or []) or re.search(r"\d", label)
            ):
                continue
            model = normalize_text(metric.get("semantic_model"))
            reports = self._metric_reports(metric)
            current = by_model.get(model)
            if current is None or len(label) < len(current["label"]):
                by_model[model] = {"label": label, "report": reports[0] if reports else None}
        return [by_model[key] for key in sorted(by_model)][:limit]

    _GROUPING_TIME_WORDS = {"mes", "ano", "anio", "trimestre", "semestre", "semana", "dia"}

    def grouping_dimension_name(self, text):
        """Nombre (singular) de la dimensión que nombra `text` («especialidades»
        -> «especialidad», «grupo etario») si es un alias de alguna dimensión del
        catálogo, un sinónimo conocido o una granularidad de tiempo; si no, None.
        Lo usa la reescritura de «cada una de las X» / «desglose por X»."""
        from src.semantic.request_phrases import singular

        aliases = self.__dict__.get("_grouping_aliases")
        if aliases is None:
            aliases = set(self._GROUPING_TIME_WORDS)
            for field in self.dimension_fields or []:
                if self._is_temporal_field(field):
                    continue
                for alias in field.get("aliases", []) or []:
                    norm = normalize_text(alias)
                    if norm and len(norm) >= 3 and len(norm.split()) <= 3:
                        aliases.add(norm)
            for canonical, synonyms in DIMENSION_SYNONYMS.items():
                aliases.add(canonical)
                aliases.update(normalize_text(item) for item in synonyms)
            self._grouping_aliases = aliases
        norm = normalize_text(text)
        if not norm:
            return None
        words = norm.split()
        # Primero el singular («especialidades» -> «especialidad»): es la forma
        # con la que se nombra la agrupación («por especialidad»).
        candidates = [" ".join(singular(word) for word in words), norm]
        for candidate in candidates:
            if candidate in self._GROUPING_TIME_WORDS:
                return candidate
            if candidate in aliases and candidate not in GENERIC_QUERY_WORDS and candidate not in STOPWORDS:
                return candidate
        return None

    def metric_words(self, question):
        """Palabras de la pregunta que nombran un indicador del catálogo (sin
        contar alias de dimensiones como «especialidad» o «servicio»). Sirve
        para distinguir un seguimiento («y por especialidad») de una pregunta
        nueva completa («y cuántas cirugías programadas»)."""
        if getattr(self, "_metric_vocabulary", None) is None:
            dimension_tokens = set()
            for field in self.dimension_fields:
                table_tokens = set(canonical_tokens(field.get("table")))
                for alias in field.get("aliases", []) or []:
                    dimension_tokens.update(set(canonical_tokens(alias)) - table_tokens)
            for synonyms in DIMENSION_SYNONYMS.values():
                for synonym in synonyms:
                    dimension_tokens.update(canonical_tokens(synonym))
            ignored = {
                canonical_token(word)
                for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
            }
            vocabulary = set()
            for metric in self.metrics:
                if metric.get("validation_status") != "approved":
                    continue
                for name in self._metric_names(metric):
                    for token in canonical_tokens(name):
                        if (
                            len(token) >= 3 and not token.isdigit()
                            and token not in ignored and token not in dimension_tokens
                        ):
                            vocabulary.add(token)
            self._metric_vocabulary = vocabulary
        return [
            word for word in normalize_text(question).split()
            if len(word) >= 3 and any(
                _token_similarity(canonical_token(word), token) >= 0.88
                for token in self._metric_vocabulary
            )
        ]

    def describe_unresolved(self, question):
        """Clasifica una pregunta para la que no se encontró indicador:

        - "generic": solo palabras genéricas («promedio mensual», «cuántos hay»);
        - "unknown": tiene palabras que el catálogo conoce, pero ningún indicador;
        - "out_of_scope": ninguna palabra distintiva aparece en el catálogo
          («cuánto gana un médico en Colombia»).
        """
        ignored = {
            canonical_token(word)
            for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS
            | set(MONTHS) | self._GENERIC_MEASURE_WORDS | self._RANKING_WORDS
        }
        words = [
            word for word in normalize_text(question).split()
            if canonical_token(word) not in ignored and not word.isdigit()
            and len(word) >= 3 and not _is_request_word(canonical_token(word))
        ]
        vocabulary = self._catalog_vocabulary()
        known = [
            word for word in words
            if any(_token_similarity(canonical_token(word), token) >= 0.88 for token in vocabulary)
        ]
        if not words:
            kind = "generic"
        elif known:
            kind = "unknown"
        else:
            kind = "out_of_scope"
        return {
            "kind": kind, "words": words, "known_words": known,
            "examples": self.catalog_examples(),
        }

    # =====================================================================
    # RESOLUCIÓN DEL INDICADOR: nombres débiles, mismo nombre en varios
    # tableros, variantes por año, tablero nombrado y calificativos.
    # =====================================================================
    # Palabras que marcan una variante «por año» de una medida
    # (TRIAGES_2025, Cirugias_Año_Actual, CIRUGIAS_AÑO_ANTERIOR).
    _YEAR_MARKER_WORDS = {"ano", "anio", "actual", "anterior", "pasado"}
    # Palabras técnicas o de agregación que no dan contenido a un nombre.
    _TECHNICAL_NAME_WORDS = {
        "conteo", "recuento", "suma", "sum", "min", "max", "avg", "count",
        "promedio", "prom", "media", "dinamico", "visible", "medida", "kpi",
    }
    # Campos con más valores distintos que esto son identificadores o
    # personas: no se usan para emparejar calificativos aproximados.
    _QUALIFIER_MAX_DOMAIN = 500
    _QUALIFIER_FIELD_LIMIT = 20

    def _note(self, text):
        """Decisión de resolución que se mostrará en el razonamiento del turno."""
        notes = self.__dict__.get("_resolution_notes")
        if notes is not None and text and text not in notes:
            notes.append(text)

    def _weak_token_sets(self):
        cached = self.__dict__.get("_weak_tokens_cache")
        if cached is None:
            content_free = {
                canonical_token(word)
                for word in (
                    STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | COMMON_VERB_WORDS
                    | set(MONTHS) | self._YEAR_MARKER_WORDS
                    | {"trimestre", "semestre", "semana", "dia", "periodo", "corte", "fecha"}
                )
            }
            generic = content_free | {
                canonical_token(word)
                for word in self._GENERIC_MEASURE_WORDS | self._TECHNICAL_NAME_WORDS
            }
            cached = (content_free, generic)
            self._weak_tokens_cache = cached
        return cached

    def _weak_name_kind(self, name):
        """«content_free» si el nombre es solo un año/periodo, un verbo o
        relleno («2024», «Registrado»); «generic» si además solo tiene palabras
        de agregación («Promedio mensual», «Total»); None si nombra algo."""
        content_free, generic = self._weak_token_sets()
        tokens = [token for token in canonical_tokens(name) if token != "%"]
        if all(token.isdigit() or token in content_free for token in tokens):
            return "content_free"
        if all(token.isdigit() or token in generic for token in tokens):
            return "generic"
        return None

    def _discard_weak_name(self, metric, business_question, best_name, best_name_score,
                           name_priority, in_named_model=False):
        """Regla: una medida cuyo nombre coincidente es solo un número/año o
        palabras genéricas no se elige por coincidir con el periodo o con
        relleno de la pregunta. Si su etiqueta sí nombra algo, se usa la
        etiqueta; si no, el indicador no compite (puntaje 0). Un nombre solo
        genérico se admite dentro del tablero nombrado en la pregunta."""
        if best_name_score <= 0:
            return best_name, best_name_score, name_priority
        kind = self._weak_name_kind(best_name)
        if kind is None or (kind == "generic" and in_named_model):
            return best_name, best_name_score, name_priority
        label = str(metric.get("label") or "")
        if label and normalize_text(label) != normalize_text(best_name):
            label_kind = self._weak_name_kind(label)
            if label_kind is None or (label_kind == "generic" and in_named_model):
                score = _phrase_score(business_question, label, self._token_weight_index())
                if score > 0:
                    return label, score, 0.0
        self._note(
            f"se descartó {label or best_name} ({metric.get('semantic_model')}): coincidió solo con "
            f"«{best_name}», un nombre sin contenido propio "
            + ("(año/periodo o relleno)" if kind == "content_free" else "(solo palabras genéricas)")
        )
        return best_name, 0.0, 0.0

    def _name_key(self, name):
        """Clave para «el mismo indicador con otro nombre técnico»: palabras
        canónicas sin conectores, «total», años ni marcas de año
        (TRIAGES_2025, TOTAL_TRIAGES y Triages -> ("triage",))."""
        ignored = self.__dict__.get("_name_key_ignored")
        if ignored is None:
            ignored = {
                canonical_token(word)
                for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | self._YEAR_MARKER_WORDS
            }
            self._name_key_ignored = ignored
        return tuple(sorted({
            token for token in canonical_tokens(name)
            if token not in ignored and not token.isdigit() and token != "%"
        }))

    def _has_year_marker(self, name):
        return any(
            re.fullmatch(r"(?:19|20)\d{2}", token) or token in self._YEAR_MARKER_WORDS
            for token in canonical_tokens(name)
        )

    def _collapse_year_variants(self, items, question):
        """Medidas atadas a un año (TRIAGES_2024/2025/2026, IMG_20xx,
        Cirugias_Año_Actual) del mismo modelo cuentan como UNA opción: se
        conservan las que el usuario ve en un tablero; de las demás (sin
        visual), una sola: la medida base (sin año, el año se filtra aparte) o,
        si no hay base, la del año pedido / el año actual / el más reciente."""
        if not items:
            return []
        year = self._detect_year_month(question)[0]
        groups = {}
        for index, item in enumerate(items):
            metric = item.get("metric") or {}
            key = (normalize_text(metric.get("semantic_model")), self._name_key(metric.get("label")))
            groups.setdefault(key, []).append(index)

        keep = set()
        for key, indexes in groups.items():
            visible = [i for i in indexes if (items[i].get("metric") or {}).get("appearances")]
            hidden = [i for i in indexes if i not in visible]
            keep.update(visible)
            if visible or not hidden or not key[1]:
                if not key[1]:
                    keep.update(hidden)
                continue
            if len(hidden) == 1:
                keep.update(hidden)
                continue

            def label(i):
                return str((items[i].get("metric") or {}).get("label") or "")

            bases = [i for i in hidden if not self._has_year_marker(label(i))]
            chosen = None
            if bases:
                chosen = bases[0]
            elif year is not None:
                chosen = next((i for i in hidden if str(year) in normalize_text(label(i)).split()), None)
            if chosen is None:
                chosen = next((i for i in hidden if "actual" in canonical_tokens(label(i))), None)
            if chosen is None:
                years = [
                    (max((int(t) for t in canonical_tokens(label(i)) if re.fullmatch(r"20\d{2}", t)), default=0), -i)
                    for i in hidden
                ]
                chosen = -max(years)[1]
            keep.add(chosen)
            dropped = [label(i) for i in hidden if i != chosen]
            if dropped:
                self._note(
                    f"variantes por año agrupadas en {label(chosen)} ({key[0]}): "
                    + ", ".join(dropped[:6]) + (" ..." if len(dropped) > 6 else "")
                )
        return [item for index, item in enumerate(items) if index in keep]

    def _tidy_unresolved_resolution(self, question, metric_result):
        """Opciones de una resolución ambigua / sugerencias sin variantes por año repetidas."""
        result = dict(metric_result)
        for key in ("candidates", "suggestions"):
            if result.get(key):
                result[key] = self._collapse_year_variants(list(result[key]), question)
        return result

    def _metric_vocabulary_tokens(self, metric, with_pages=True):
        """Palabras con que se puede nombrar un indicador: sus nombres, su tabla y sus páginas."""
        values = [*self._metric_names(metric), metric.get("table")]
        if with_pages:
            values.extend(self._metric_pages(metric))
        tokens = set()
        for value in values:
            tokens.update(token for token in canonical_tokens(value) if len(token) >= 3)
        return tokens

    @staticmethod
    def _explains(token, vocabulary):
        return any(_tokens_match_loosely(token, other) for other in vocabulary)

    def _content_ignored_tokens(self):
        cached = self.__dict__.get("_content_ignored_cache")
        if cached is None:
            cached = {
                canonical_token(word)
                for word in (
                    STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
                    | self._GENERIC_MEASURE_WORDS | self._RANKING_WORDS
                )
            }
            self._content_ignored_cache = cached
        return cached

    def _question_content_words(self, text):
        """Palabras con contenido de la pregunta, en orden (sin relleno,
        petición, periodo, cifras ni palabras genéricas de medida)."""
        ignored = self._content_ignored_tokens() | set(self._period_words(text))
        words = []
        for word in normalize_text(text).split():
            token = canonical_token(word)
            if (
                len(token) < 3 or token.isdigit() or token in ignored
                or _is_request_word(token)
            ):
                continue
            words.append(word)
        return words

    def _head_token(self, question, source_context):
        """Sustantivo principal: primera palabra con contenido de la pregunta
        sin el nombre del tablero («cuánto PESO hay en lavandería»)."""
        words = self._question_content_words(self._metric_business_question(question, source_context))
        # «detalle de pacientes ...»: «detalle» pide la forma de la respuesta,
        # no es el sustantivo del indicador.
        words = [word for word in words if canonical_token(word) not in self._SHAPE_WORDS]
        return canonical_token(words[0]) if words else None

    _SHAPE_WORDS = {"detalle", "desglose"}

    def _board_named_explicitly(self, question, source_context):
        """¿La pregunta nombra de verdad el tablero al que se enrutó? Sí si dice
        «tablero/informe/reporte» o una palabra distintiva de su nombre (≥ 4
        letras y que no sea a la vez un nombre de dimensión: «eps» en «nueva
        eps» es una aseguradora, no el TABLERO EPS)."""
        normalized = normalize_text(question)
        if re.search(r"(?<![a-z0-9])(?:tablero|informe|reporte|dashboard)(?![a-z0-9])", normalized):
            return True
        dimension_words = {
            canonical_token(word) for synonyms in DIMENSION_SYNONYMS.values() for word in synonyms
        }
        generic = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS | {"tablero", "informe"}}
        question_tokens = set(canonical_tokens(normalized))
        for name in (source_context.get("report"), source_context.get("semantic_model"),
                     source_context.get("source_group")):
            for token in canonical_tokens(name):
                if (
                    len(token) >= 4 and token not in generic and token not in dimension_words
                    and token in question_tokens
                ):
                    return True
        return False

    def _named_board_rejection(self, question, source_context, metric_result):
        """Regla: la pregunta nombra un tablero (routing fuerte) y el mejor
        indicador es de otro modelo. No se responde con él: se dice que en ese
        tablero no se encontró y se ofrecen indicadores de ese tablero; si no
        hay, se ofrece el encontrado en el otro tablero como opción."""
        metric = metric_result.get("metric") or {}
        board = source_context.get("report") or source_context.get("semantic_model")
        board_model = normalize_text(source_context.get("semantic_model"))
        business_question = self._metric_business_question(question, source_context)
        options = [
            item for item in self._metric_suggestions(
                business_question, model_hint=board_model, strong=True, ratio=0.0, limit=None,
            )
            if normalize_text(item["metric"].get("semantic_model")) == board_model
        ]
        options = self._collapse_year_variants(options, question)[: self._SUGGESTION_LIMIT]
        elsewhere = None
        if not options and metric.get("metric_id"):
            elsewhere = {
                "metric": metric, "score": metric_result.get("score"),
                "business_score": metric_result.get("score"),
                "matched_name": metric_result.get("matched_name"),
            }
        self._note(
            f"la pregunta nombra el tablero {board}, pero el indicador elegido "
            f"({metric.get('label')}) es de {metric.get('semantic_model')}: no se responde con él; "
            + (f"se ofrecen {len(options)} indicadores de {board}" if options
               else "ese tablero no tiene indicadores parecidos")
        )
        reports = metric.get("reports") or []
        return {
            "status": "not_found", "stage": "metric",
            "reason": "metric_not_in_named_report",
            "named_report": board,
            "found_elsewhere": {
                "metric_id": metric.get("metric_id"), "label": metric.get("label"),
                "report": metric.get("report") or (reports[0] if reports else None),
                "semantic_model": metric.get("semantic_model"),
            } if metric.get("metric_id") else None,
            "question": question, "source_context": source_context,
            "metric_resolution": {
                "status": "not_found", "candidates": [],
                "suggestions": [
                    {k: v for k, v in item.items() if not k.startswith("_")}
                    for item in (options or ([elsewhere] if elsewhere else []))
                ],
            },
        }

    def _rival_group_check(self, question, best):
        """Filtro para los rivales de nombre igual o parecido en «M por X»: si
        el indicador elegido se desglosa por X, un rival que no se puede
        desglosar por X no responde la pregunta y no se ofrece (PACIENTES
        OBSERVADOS de BRIEFING, tabla sin aseguradora, frente a PACIENTES
        OBSERVADOS POR MES de CONSULTAS PRIORITARIAS para «... por aseguradora»)."""
        tail = self._requested_group_tail(question)
        if not tail or self._group_field_in(tail, self._metric_dimensions(best)) is None:
            return lambda metric: True
        return lambda metric: self._group_field_in(tail, self._metric_dimensions(metric)) is not None

    def _same_name_ambiguity(self, question, source_context, metric_result):
        """Regla: si el indicador elegido tiene el mismo nombre (o casi:
        sin «total», años ni mayúsculas/guiones) que otros de OTRO modelo o
        informe, y nada en la pregunta los distingue (tablero nombrado,
        página, tabla o palabra que solo uno explica), se contrapregunta.
        Las variantes por año de un mismo modelo cuentan como una opción.

        La penalización de -0.25 a medidas sin visual sigue ordenando las
        opciones, pero ya no basta para responder sin preguntar."""
        best = metric_result.get("metric") or {}
        if not best.get("metric_id"):
            return None
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        if strong and normalize_text(source_context.get("semantic_model")) == normalize_text(best.get("semantic_model")):
            return None
        keys = {self._name_key(metric_result.get("matched_name")), self._name_key(best.get("label"))}
        keys.discard(())
        if not keys:
            return None

        business_question = self._metric_business_question(question, source_context)
        question_tokens = canonical_tokens(business_question)
        content = {canonical_token(word) for word in self._question_content_words(business_question)}
        best_explained = {t for t in content if self._explains(t, self._metric_vocabulary_tokens(best))}
        best_page = self._page_bonus(question_tokens, best, set(canonical_tokens(best.get("label"))))

        def where(metric):
            reports = metric.get("reports") or []
            report = metric.get("report") or (reports[0] if reports else "")
            return normalize_text(metric.get("semantic_model")), normalize_text(report)

        rivals, seen = [], {self._logical_key(best)}
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            logical = self._logical_key(metric)
            if logical in seen:
                continue
            names =[metric.get("label"), metric.get("measure")] + [
                appearance.get("visual_title") for appearance in metric.get("appearances") or []
            ]
            if not any(name and self._name_key(name) in keys for name in names):
                continue
            explained = {t for t in content if self._explains(t, self._metric_vocabulary_tokens(metric))}
            if best_explained - explained:
                continue  # la pregunta nombra algo que solo explica el elegido
            if best_page and not self._page_bonus(question_tokens, metric, set(canonical_tokens(metric.get("label")))):
                continue
            seen.add(logical)
            rivals.append(metric)

        elsewhere = [metric for metric in rivals if where(metric) != where(best)]
        if not elsewhere:
            return None
        rivals.sort(key=lambda metric: 0 if metric.get("appearances") else 1)
        score = metric_result.get("score")
        items = [
            {"metric": metric, "score": score, "business_score": score,
             "matched_name": metric_result.get("matched_name") if metric is best else metric.get("label")}
            for metric in [best, *rivals]
        ]
        items = self._collapse_year_variants(items, question)[: self._SUGGESTION_LIMIT]
        if len(items) < 2:
            return None
        # «M por X»: entre los del mismo nombre solo responden los que se
        # desglosan por X. Si queda uno, es la respuesta (aunque no sea el
        # que puntuó más); si es el elegido, no hay nada que preguntar.
        tail = self._requested_group_tail(question)
        if tail:
            groupable = [
                item for item in items
                if self._group_field_in(tail, self._metric_dimensions(item["metric"])) is not None
            ]
            if groupable and len(groupable) < len(items):
                self._note(
                    f"«{metric_result.get('matched_name')}» existe en varios tableros; solo "
                    + ", ".join(f"{i['metric'].get('label')} ({i['metric'].get('semantic_model')})" for i in groupable)
                    + f" se desglosa(n) por «{tail}»"
                )
                items = groupable
                if len(items) == 1:
                    if items[0]["metric"] is best:
                        return None
                    return {
                        "status": "ambiguous", "stage": "metric", "reason": None,
                        "question": question, "source_context": source_context,
                        "metric_resolution": {"status": "ambiguous", "candidates": items},
                    }
        self._note(
            f"«{metric_result.get('matched_name')}» existe con el mismo nombre en varios tableros/modelos "
            f"({', '.join(sorted({str(i['metric'].get('semantic_model')) for i in items}))}) y la "
            "pregunta no indica cuál: se contrapregunta"
        )
        return {
            "status": "ambiguous", "stage": "metric",
            "reason": "same_name_in_several_boards",
            "question": question, "source_context": source_context,
            "metric_resolution": {"status": "ambiguous", "candidates": items},
        }

    def _unresolved_outweighs_metric(self, question, metric, metric_result, significant, source_context):
        """Regla: no se ofrece «consultar X sin <palabras>» cuando las palabras
        sin interpretar son el núcleo de la pregunta: incluyen el sustantivo
        principal («cuánto PESO hay...» con el indicador Asignadas) o pesan
        claramente más (≥ 2,5 veces, por peso IDF) que lo que coincidió con el
        indicador. Se devuelve not_found con sugerencias o, si nada de lo no
        interpretado existe en el catálogo, fuera de alcance."""
        leftover = [canonical_token(word) for word in significant]
        head = self._head_token(question, source_context)
        vocabulary = self._metric_vocabulary_tokens(metric)
        business_question = self._metric_business_question(question, source_context)
        evidence = [
            canonical_token(word) for word in self._question_content_words(business_question)
            if canonical_token(word) not in leftover and self._explains(canonical_token(word), vocabulary)
        ]
        left_weight = sum(self._token_weight(token) for token in leftover)
        evidence_weight = sum(self._token_weight(token) for token in evidence)
        head_missing = bool(head) and head in leftover and not self._explains(head, vocabulary)
        heavier = len(leftover) >= 2 and left_weight >= 2.5 * max(evidence_weight, 0.01)
        if not (head_missing or heavier):
            return None

        reason_text = (
            f"el sustantivo principal «{head}» no corresponde al indicador"
            if head_missing else
            f"las palabras sin interpretar pesan {left_weight:.2f} frente a {evidence_weight:.2f} de la coincidencia"
        )
        unresolved_text = " ".join(significant)
        kind = self.describe_unresolved(unresolved_text).get("kind")
        out_of_scope = head_missing and kind == "out_of_scope"
        resolved_routing = source_context.get("status") == "resolved"
        strength = source_context.get("routing_strength")
        model_hint = (
            normalize_text(source_context.get("semantic_model"))
            if resolved_routing and strength in ("strong", "weak") else ""
        )
        suggestions = [] if out_of_scope else [
            item for item in self._metric_suggestions(
                business_question, model_hint=model_hint, strong=strength == "strong",
            )
            if self._logical_key(item["metric"]) != self._logical_key(metric)
        ]
        suggestions = self._collapse_year_variants(suggestions, question)
        self._note(
            f"se descartó {metric.get('label')} ({metric.get('semantic_model')}): {reason_text}; "
            + ("ninguna de esas palabras existe en el catálogo: fuera de alcance" if out_of_scope
               else f"no se ofrece consultarlo sin «{unresolved_text}»")
        )
        plan = {
            "status": "not_found", "stage": "metric",
            "reason": "unresolved_words_outweigh_metric",
            "question": question, "source_context": source_context,
            "unresolved_text": unresolved_text,
            "rejected_metric": {
                "metric_id": metric.get("metric_id"), "label": metric.get("label"),
                "matched_name": metric_result.get("matched_name"),
                "why": reason_text,
            },
            "metric_resolution": {
                "status": "not_found", "candidates": [],
                "suggestions": [
                    {key: value for key, value in item.items() if not key.startswith("_")}
                    for item in suggestions
                ],
            },
        }
        if out_of_scope:
            plan["unresolved_kind"] = "out_of_scope"
        return plan

    # ---------------- opciones de una contrapregunta ----------------
    # Palabras que nombran la unidad contada («pacientes», «casos»): «cuántos
    # pacientes observados» y OBSERVADOS cuentan lo mismo aunque el nombre no
    # diga «pacientes». No distinguen un indicador de otro.
    _OPTION_UNIT_WORDS = {
        "paciente", "pacientes", "persona", "personas", "usuario", "usuarios",
        "registro", "registros", "caso", "casos",
    }
    # Palabras genéricas en un NOMBRE de medida, pero que en la pregunta son el
    # tema («pacientes con PENDIENTES»): cuentan para decidir si una opción
    # tiene que ver con la pregunta.
    _OPTION_TOPIC_WORDS = {"pendiente", "pendientes"}
    # «por servicio», «según la EPS»: la agrupación no dice de qué indicador se trata.
    _OPTION_GROUP_RE = re.compile(
        r"(?<![a-z0-9])(?:por|segun|agrupad[oa]s?\s+por|desglosad[oa]s?\s+por)\s+"
        r"(?:(?:el|la|los|las|cada)\s+)?[a-z0-9%]+"
    )

    def _option_words(self, question, source_context):
        """Palabras distintivas de la pregunta con las que se juzga si una
        opción tiene que ver con ella: sin relleno, petición, periodo, palabras
        de agregación («total», «promedio»), la agrupación («por servicio») ni
        el nombre del tablero nombrado («en naos», «tablero de triage»)."""
        text = self._metric_business_question(question, source_context)
        text, board_tokens = self._strip_board_mentions(text, source_context)
        text = self._OPTION_GROUP_RE.sub(" ", text)
        content_free, _ = self._weak_token_sets()
        aggregation = {
            canonical_token(word)
            for word in (self._GENERIC_MEASURE_WORDS | self._TECHNICAL_NAME_WORDS) - self._OPTION_TOPIC_WORDS
        }
        ignored = set(content_free) | aggregation | set(self._period_words(text)) | set(board_tokens)
        if (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        ):
            for name in (source_context.get("report"), source_context.get("semantic_model"),
                         source_context.get("source_group")):
                ignored.update(token for token in canonical_tokens(name) if len(token) >= 4)
        words = []
        for token in canonical_tokens(text):
            if (
                len(token) < 3 or token.isdigit() or token in ignored
                or _is_request_word(token) or token in words
            ):
                continue
            words.append(token)
        return words

    def _reflexive_verbs(self, question):
        """Verbos en pasiva refleja («se tomaron», «se realizaron»): describen
        la acción contada, no un calificativo que distinga un indicador."""
        return {
            canonical_token(match.group(1))
            for match in re.finditer(r"(?<![a-z0-9])se\s+([a-z]{4,})", normalize_text(question))
        }

    def _option_coverage(self, metric, words):
        """Palabras de `words` que explica el indicador (nombres, tabla o página)."""
        vocabulary = self._metric_vocabulary_tokens(metric or {})
        return {word for word in words if self._explains(word, vocabulary)}

    def _options_named_by_question(self, question, source_context, candidates):
        """Desempate por la frase que nombra la pregunta. Entre opciones que
        explican todas sus palabras distintivas, se quedan las que la pregunta
        nombra enteras: cada palabra de su nombre (sin conectores, «total» ni
        años) está en la pregunta. «cuántos triages pediátricos hubo en 2025»
        nombra TRIAGES_PEDIATRICOS_2025, no PROMEDIO_TRIAGES_PEDIATRICOS_2025
        ni PROM_TRIAGE_PEDIATRICOS (añaden «promedio», que no se dijo). Si varias
        quedan, solo las de nombre más largo (más específico); si ninguna o
        todas, devuelve [] (lo deciden otras reglas). Dos indicadores del mismo
        nombre en tableros distintos siguen siendo ambiguos."""
        words = self._option_words(question, source_context)
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        core = [word for word in words if word not in units] or words
        if not core:
            return []
        question_tokens = set(canonical_tokens(self._metric_business_question(question, source_context)))

        def said(token):
            return any(_tokens_match_loosely(token, other) for other in question_tokens)

        considered, named = [], []
        for item in candidates:
            metric = item.get("metric") or {}
            if float(item.get("business_score") or 0.0) < self.min_metric_score:
                continue
            considered.append(item)
            if len(self._option_coverage(metric, core)) < len(core):
                continue
            keys = [self._name_key(metric.get("label")), self._name_key(item.get("matched_name"))]
            sizes = [len(key) for key in keys if key and all(said(token) for token in key)]
            if sizes:
                named.append((item, max(sizes)))
        if len(considered) < 2 or not named:
            return []
        top = max(size for _, size in named)
        kept = [item for item, size in named if size == top]
        if len(kept) == len(considered):
            return []
        return kept

    def options_explain_question(self, question, candidates, source_context=None):
        """¿Las opciones de una contrapregunta explican la pregunta lo bastante
        como para que tenga intención analítica? Al menos una opción debe
        explicar (nombre, tabla o página) la mitad de sus palabras distintivas
        sin contar las de unidad («pacientes»). «¿Qué medicamento le doy a un
        paciente con fiebre?» solo comparte «paciente» y «escríbeme un código
        en Python» solo «código» (una columna): no se contrapregunta por
        indicadores, se responde fuera de alcance. Sin palabras distintivas
        no se juzga (True)."""
        if source_context is None:
            source_context = self._source_context(question)
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        core = [word for word in self._option_words(question, source_context) if word not in units]
        if not core:
            return True
        best = max(
            (len(self._option_coverage(item.get("metric") or {}, core)) for item in candidates or []),
            default=0,
        )
        return 2 * best >= len(core)

    def _prune_unrelated_options(self, question, source_context, metric_result):
        """Depura las opciones de una contrapregunta:
        - fuera las que no comparten ninguna palabra distintiva de la pregunta
          («% Ocupación» para «pacientes con pendientes por servicio»);
        - si algunas explican TODAS las palabras distintivas, solo esas
          («consultas prioritarias»: las de consultas prioritarias, no
          cualquier «Consultas»). Las palabras de unidad («pacientes») no
          obligan. Esas opciones quedan con el mismo puntaje: la pregunta no
          decide entre ellas y la contrapregunta las muestra todas."""
        words = self._option_words(question, source_context)
        if not words:
            return metric_result
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        core = [word for word in words if word not in units] or words
        # «detalle de ocupación por aseguradores»: una opción que se desglosa
        # por la dimensión pedida y cuya página/nombre trata el tema (PACIENTES
        # por ASEGURADORA, tabla de la página DETALLE OCUPACIÓN) no se descarta
        # por no compartir una palabra con «detalle ocupacion».
        tail = self._requested_group_tail(question)
        topic = self._group_topic_words(question, source_context, tail) if tail else []
        result = dict(metric_result)
        for key in ("candidates", "suggestions"):
            items = list(result.get(key) or [])
            if len(items) < 2:
                continue
            covered = [self._option_coverage(item.get("metric"), core) for item in items]
            related = [index for index, words_covered in enumerate(covered) if words_covered]
            if not related:
                continue  # nada comparte palabras: lo decide otra regla
            full = [index for index in related if len(covered[index]) == len(core)]
            keep = full or related
            if topic and len(keep) < len(items):
                protected = [
                    index for index in range(len(items))
                    if index not in keep and self._groupable_on_topic(items[index].get("metric") or {}, tail, topic)
                ]
                if protected:
                    self._note(
                        "se conservan (se desglosan por «" + tail + "» y su página trata «"
                        + " ".join(topic) + "»): "
                        + ", ".join(str((items[i].get("metric") or {}).get("label")) for i in protected)
                    )
                    keep = sorted(set(keep) | set(protected))
            if len(keep) == len(items):
                continue
            dropped = [
                str((items[index].get("metric") or {}).get("label"))
                for index in range(len(items)) if index not in keep
            ]
            kept = [dict(items[index]) for index in keep]
            if full and len(kept) > 1:
                best = max(float(item.get("score") or 0.0) for item in kept)
                for item in kept:
                    item["score"] = best
            result[key] = kept
            self._note(
                "opciones depuradas: "
                + (f"solo las que explican «{' '.join(core)}»" if full
                   else f"solo las que comparten alguna palabra de «{' '.join(core)}»")
                + f"; fuera: {', '.join(dropped[:6])}" + (" ..." if len(dropped) > 6 else "")
            )
        return result

    def _named_board_options(self, question, source_context, metric_result):
        """Tablero nombrado (routing fuerte) y ninguna opción es de él
        («pacientes con pendientes EN NAOS por servicio» ofrecía %PENDIENTE de
        ASIGNACION DE CITAS): se buscan opciones en ese tablero. Devuelve
        ("resolved", item) si una sola explica todas las palabras de la
        pregunta, ("options", items) si hay varias, o (None, []) si el
        tablero no tiene ninguna parecida (se mantienen las de otros tableros)."""
        board_model = normalize_text(source_context.get("semantic_model"))
        business_question = self._metric_business_question(question, source_context)
        found = [
            item for item in self._metric_suggestions(
                business_question, model_hint=board_model, strong=True, ratio=0.0, limit=None,
            )
            if normalize_text(item["metric"].get("semantic_model")) == board_model
        ]
        found = self._collapse_year_variants(found, question)
        words = self._option_words(question, source_context)
        if not found or not words:
            return None, []
        coverage = [len(self._option_coverage(item["metric"], words)) for item in found]
        best = max(coverage)
        if best == 0:
            return None, []
        top = [item for item, count in zip(found, coverage) if count == best]
        clean = [{key: value for key, value in item.items() if not key.startswith("_")} for item in top]
        if len(top) == 1 and best == len(words):
            return "resolved", clean[0]
        return "options", clean[: self._SUGGESTION_LIMIT]

    # ---------------- páginas nombradas ----------------
    # Una página se nombra por su tema («hospitalizaciones parciales de marzo»,
    # «partos de 2025») o con «tablero/página de X». Sus indicadores salen de
    # las visualizaciones del catálogo (tarjetas primero), de las medidas
    # documentadas de esa página en el RAG y, si el catálogo no tiene sus
    # visualizaciones, de los indicadores del modelo cuyo nombre o tabla
    # explica el nombre de la página (tema).
    _PAGE_IGNORED_NAME_WORDS = {
        "cantidades", "cantidad", "tiempos", "tiempo", "cuentas", "detalle", "resumen", "inicio",
        "general", "listado", "consolidado", "seguimiento", "total", "totales", "indicadores",
        "principal", "portada", "home", "menu", "tablero", "informe", "reporte", "pagina",
    }
    _PAGE_PRINCIPAL_RE = re.compile(r"^(?:total|totales|numero|nro|cantidad|conteo|recuento)(?:\s|$)")
    _PAGE_RANKS = {"card": 0, "visual": 1, "documentation": 2, "topic": 3}

    def _page_index(self):
        """{(modelo, página) normalizados: {"page", "semantic_model", "report",
        "visual", "members": {clave lógica: miembro}}}. Un miembro es
        {"metric", "visual_type", "source", "title", "rank"}."""
        cached = self.__dict__.get("_page_index_cache")
        if cached is not None:
            return cached
        index = {}
        metrics = [m for m in self._dedupe_metrics(self.metrics) if m.get("validation_status") == "approved"]
        model_names = {normalize_text(m.get("semantic_model")): m.get("semantic_model") for m in metrics}

        def entry(model, page, report=None):
            key = (normalize_text(model), normalize_text(page))
            if not key[0] or not key[1]:
                return None
            item = index.setdefault(key, {
                "page": str(page).strip(), "semantic_model": model_names.get(key[0], model),
                "report": report, "visual": False, "members": {},
            })
            if report and not item.get("report"):
                item["report"] = report
            return item

        def add(item, metric, source, visual_type=None, title=None):
            if item is None:
                return
            rank = self._PAGE_RANKS["card"] if visual_type == "card" else self._PAGE_RANKS[
                "visual" if source == "visual" else source
            ]
            key = self._logical_key(metric)
            current = item["members"].get(key)
            if current is None or rank < current["rank"]:
                item["members"][key] = {
                    "metric": metric, "visual_type": visual_type, "source": source,
                    "title": title, "rank": rank, "order": len(item["members"]) if current is None else current["order"],
                }

        for metric in metrics:
            for appearance in metric.get("appearances") or []:
                page = appearance.get("page_display_name")
                item = entry(metric.get("semantic_model"), page, appearance.get("report"))
                if item is None:
                    continue
                item["visual"] = True
                add(item, metric, "visual", appearance.get("visual_type"), appearance.get("visual_title"))

        # Medidas documentadas en la página («TRIAGE»: TOTAL_TRIAGES, PROMEDIO_TRIAGE_2025...).
        by_name = {}
        for metric in metrics:
            for name in (metric.get("measure"), metric.get("label")):
                key = (normalize_text(metric.get("semantic_model")), normalize_text(name))
                if key[1] and metric not in by_name.setdefault(key, []):
                    by_name[key].append(metric)
        for model_key, dashboards in self._semantic_documents_index().items():
            for dashboard in dashboards:
                item = entry(model_names.get(model_key, model_key), dashboard.get("name"))
                if item is None:
                    continue
                for measure in dashboard.get("documented_measures") or []:
                    raw = measure.get("name") if isinstance(measure, dict) else measure
                    name = normalize_text(str(raw or "").split("=")[0])
                    for metric in by_name.get((model_key, name), []):
                        add(item, metric, "documentation")

        # Páginas que el enrutador conoce aunque no tengan indicadores.
        known = getattr(self.source_router, "known_pages", None)
        try:
            pages = known() if callable(known) else []
        except Exception:
            pages = []
        for page in pages or []:
            entry(page.get("semantic_model"), page.get("name"), page.get("report"))
        self._page_index_cache = index
        return index

    def _page_name_tokens(self, page):
        """Palabras con contenido del nombre de una página (sin genéricas)."""
        ignored = self._content_ignored_tokens() | {
            canonical_token(word) for word in self._PAGE_IGNORED_NAME_WORDS | GENERIC_PAGE_WORDS
        }
        return [
            token for token in dict.fromkeys(canonical_tokens(page))
            if len(token) >= 3 and not token.isdigit() and token not in ignored
        ]

    def _page_members(self, page):
        """Indicadores de una página {"semantic_model", "page"} en orden:
        tarjetas, otras visualizaciones, medidas documentadas y, si el catálogo
        no tiene sus visualizaciones, los del modelo cuyo nombre o tabla
        explica el nombre de la página."""
        key = (normalize_text(page.get("semantic_model")), normalize_text(page.get("page")))
        cache = self.__dict__.setdefault("_page_members_cache", {})
        if key in cache:
            return cache[key]
        item = self._page_index().get(key)
        members = list((item or {}).get("members", {}).values())
        if item is not None and not item.get("visual"):
            tokens = self._page_name_tokens(item["page"])
            present = {self._logical_key(member["metric"]) for member in members}
            if tokens:
                for metric in self._dedupe_metrics(self.metrics):
                    if (
                        metric.get("validation_status") != "approved"
                        or normalize_text(metric.get("semantic_model")) != key[0]
                        or self._logical_key(metric) in present
                    ):
                        continue
                    vocabulary = self._metric_vocabulary_tokens(metric, with_pages=False)
                    if all(self._explains(token, vocabulary) for token in tokens):
                        present.add(self._logical_key(metric))
                        members.append({
                            "metric": metric, "visual_type": None, "source": "topic", "title": None,
                            "rank": self._PAGE_RANKS["topic"], "order": len(members),
                        })
        members.sort(key=lambda member: (member["rank"], member["order"]))
        cache[key] = members
        return members

    def _page_report(self, page):
        item = self._page_index().get((normalize_text(page.get("semantic_model")), normalize_text(page.get("page"))))
        report = page.get("report") or (item or {}).get("report")
        if report:
            return report
        sources_for_model = getattr(self.source_router, "sources_for_model", None)
        try:
            sources = sources_for_model(page.get("semantic_model")) if callable(sources_for_model) else []
        except Exception:
            sources = []
        return next((source.get("report") for source in sources or [] if source.get("report")),
                    page.get("semantic_model"))

    def _is_report_page(self, page):
        """Página documentada que en realidad es el informe completo
        («TABLERO DE ATENCIONES INSTITUCIONALES» como nombre de página)."""
        name = normalize_text(page.get("page"))
        names = {normalize_text(page.get("semantic_model")), normalize_text(page.get("report"))}
        sources_for_model = getattr(self.source_router, "sources_for_model", None)
        try:
            sources = sources_for_model(page.get("semantic_model")) if callable(sources_for_model) else []
        except Exception:
            sources = []
        for source in sources or []:
            names.update(normalize_text(value) for value in [source.get("report"), *(source.get("aliases") or [])])
        stripped = {re.sub(r"^(?:tablero|informe|reporte)\s+(?:(?:de|del)\s+)?", "", value) for value in names if value}
        return name in names or name in stripped

    def _named_pages(self, source_context):
        """Páginas nombradas con «tablero/página de X» (no un informe):
        la del enrutamiento fuerte o, si el nombre existe en varios modelos,
        todas las páginas con ese nombre."""
        context = source_context or {}
        pages = []
        if context.get("status") == "resolved" and context.get("routing_strength") == "strong":
            if context.get("board_kind") in ("page", "documentation") and context.get("dashboard"):
                pages.append({"semantic_model": context.get("semantic_model"), "page": context.get("dashboard"),
                              "report": context.get("report")})
        elif context.get("board_mentions"):
            for mention in context.get("board_mentions") or []:
                for item in mention.get("contexts") or []:
                    if item.get("kind") in ("page", "documentation") and item.get("dashboard"):
                        pages.append({"semantic_model": item.get("semantic_model"), "page": item.get("dashboard"),
                                      "report": item.get("report")})
        return self._dedupe_pages(pages)

    def _dedupe_pages(self, pages):
        result, seen = [], set()
        for page in pages:
            key = (normalize_text(page.get("semantic_model")), normalize_text(page.get("page")))
            if key in seen or self._is_report_page(page):
                continue
            seen.add(key)
            result.append(page)
        return result

    def _topic_pages(self, question):
        """Páginas nombradas por su tema, sin «tablero de» («partos de 2025»)."""
        mentions_for = getattr(self.source_router, "page_topic_mentions", None)
        if not callable(mentions_for):
            return []
        ignored = (
            STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS) | GENERIC_PAGE_WORDS
            | self._GENERIC_MEASURE_WORDS | self._TECHNICAL_NAME_WORDS | self._PAGE_IGNORED_NAME_WORDS
        )
        try:
            mentions = mentions_for(question, ignored_words=ignored) or []
        except Exception:
            return []
        # «pacientes por especialidad»: la agrupación no nombra la página
        # DETALLE ESPECIALIDADES (sí «atenciones por asegurador» entera).
        tail = self._requested_group_tail(question)
        if tail:
            tail_tokens = set(canonical_tokens(tail))
            mentions = [
                mention for mention in mentions
                if not set(canonical_tokens(mention.get("phrase"))) <= tail_tokens
            ]
        pages = [
            {"semantic_model": item.get("semantic_model"), "page": item.get("dashboard"),
             "report": item.get("report"), "phrase": mention.get("phrase")}
            for mention in mentions for item in mention.get("contexts") or []
            if item.get("dashboard")
        ]
        return self._dedupe_pages(pages)

    def _page_extra_words(self, metric, question):
        """Palabras con contenido del nombre del indicador que la pregunta no
        dice («pediátricos» en PROMEDIO_TRIAGES_PEDIATRICOS_2025)."""
        content_free, generic = self._weak_token_sets()
        said = set(canonical_tokens(question))
        extra = set()
        for token in canonical_tokens(metric.get("label")):
            if len(token) < 4 or token.isdigit() or token in generic or token in content_free:
                continue
            if not self._explains(token, said):
                extra.add(token)
        return len(extra)

    def _page_principal(self, pool):
        """Indicador principal de una página entre las opciones: el único,
        la única tarjeta o la única «Total …/Número de …»."""
        if len(pool) == 1:
            return pool[0]
        cards = [member for member in pool if member.get("visual_type") == "card"]
        if len(cards) == 1:
            return cards[0]
        candidates = cards or pool
        totals = [
            member for member in candidates
            if self._PAGE_PRINCIPAL_RE.match(normalize_text(member.get("title") or member["metric"].get("label")))
        ]
        return totals[0] if len(totals) == 1 else None

    def _page_choices(self, question, source_context, page, offered, topic=False):
        """Opciones de una página para la pregunta: primero los indicadores ya
        ofrecidos que están en la página; si no hay, los de la página que
        comparten palabras con la pregunta (o todos).

        Devuelve {"items", "principal", "direct"}: `principal` es el indicador
        principal elegido entre varios (tarjeta única o única «Total …», sin
        palabras que la pregunta no dice) y `direct` dice si se puede responder
        sin contrapreguntar."""
        members = self._page_members(page)
        if not members:
            return {"items": [], "principal": None, "direct": False}
        by_key = {self._logical_key(member["metric"]): member for member in members}
        pool, seen = [], set()
        for item in offered:
            key = self._logical_key(item.get("metric") or {})
            if key in by_key and key not in seen:
                seen.add(key)
                pool.append(by_key[key])
        pool.sort(key=lambda member: (member["rank"], member["order"]))
        words = self._option_words(question, source_context)
        candidates = pool or members
        if words:
            coverage = [len(self._option_coverage(member["metric"], words)) for member in candidates]
            best = max(coverage)
            if best > 0:
                candidates = [member for member, count in zip(candidates, coverage) if count == best]
            elif not pool:
                # La pregunta solo nombra la página: se ofrecen sus indicadores.
                candidates = members
        # «promedio mensual de partos»: la agregación pedida elige entre los
        # indicadores de la página (PROM_PD y no la tarjeta «Total»).
        before = len(candidates)
        candidates = self._page_aggregation_match(question, candidates)
        by_aggregation = len(candidates) < before
        if not topic:
            # Página nombrada: sin palabras que la pregunta no dice
            # («pediátricos» en PROMEDIO_TRIAGES_PEDIATRICOS_2025).
            extras = [self._page_extra_words(member["metric"], question) for member in candidates]
            fewest = min(extras)
            candidates = [member for member, count in zip(candidates, extras) if count == fewest]
        # Variantes por año (PROMEDIO_TRIAGE_20xx, ATEHP2024/2025) = una opción.
        collapsed = self._collapse_year_variants(
            [{"metric": member["metric"], "_member": member} for member in candidates], question,
        )
        candidates = self._collapse_glued_year_members([item["_member"] for item in collapsed], question)
        if len(candidates) == 1:
            # Una sola opción: se responde si no añade palabras que la pregunta
            # no dice; es «la principal» solo si la pregunta solo nombró la página.
            direct = not self._page_extra_words(candidates[0]["metric"], question)
            principal = candidates[0] if (direct and not pool and not by_aggregation) else None
            return {"items": candidates, "principal": principal, "direct": direct}
        principal = self._page_principal(candidates)
        if principal is not None and not self._page_extra_words(principal["metric"], question):
            return {"items": [principal], "principal": principal, "direct": True}
        # «INTERCONSULTAS SIN RESPUESTA» no es la principal de «cuántas
        # interconsultas» aunque sea la única tarjeta: se contrapregunta.
        return {"items": candidates, "principal": None, "direct": False}

    _PAGE_AGGREGATIONS = {
        "promedio": {"promedio", "prom", "media", "avg"},
        "total": {"total", "totales", "conteo", "recuento", "count"},
        "porcentaje": {"porcentaje", "porcentual", "pct", "proporcion", "tasa"},
    }

    def _page_aggregation_match(self, question, members):
        """Miembros cuyo nombre lleva la agregación que pide la pregunta
        («promedio», «total», «porcentaje»); todos si ninguno o no se pide."""
        said = set(normalize_text(question).split())
        asked = [words for words in self._PAGE_AGGREGATIONS.values() if said & words]
        if len(asked) != 1:
            return members
        matching = [
            member for member in members
            if set(normalize_text(f"{member['metric'].get('label')} {member.get('title') or ''}").split()) & asked[0]
        ]
        return matching or members

    def _collapse_glued_year_members(self, members, question):
        """ATEHP2024 / ATEHP2025 / ATEHP2026 (año pegado al nombre) cuentan
        como una opción: la del año pedido o, si no hay, la más reciente."""
        year = self._detect_year_month(question)[0]
        groups, order = {}, []
        for member in members:
            label = normalize_text(member["metric"].get("label")).replace(" ", "")
            match = re.fullmatch(r"(.*?[a-z])((?:19|20)\d{2})", label)
            key = (normalize_text(member["metric"].get("semantic_model")), match.group(1) if match else label)
            if key not in groups:
                order.append(key)
            groups.setdefault(key, []).append((int(match.group(2)) if match else None, member))
        result = []
        for key in order:
            items = groups[key]
            dated = [(value, member) for value, member in items if value is not None]
            if len(dated) < 2:
                result.extend(member for _, member in items)
                continue
            chosen = next((member for value, member in dated if value == year), None)
            if chosen is None:
                chosen = max(dated, key=lambda pair: pair[0])[1]
            result.extend(member for value, member in items if value is None or member is chosen)
            self._note(
                f"variantes por año agrupadas en {chosen['metric'].get('label')}: "
                + ", ".join(str(member["metric"].get("label")) for _, member in dated if member is not chosen)
            )
        return result

    def _page_label(self, page):
        return f"{page.get('page')} ({self._page_report(page)})"

    def _named_page_refinement(self, question, intent_result, plan):
        """Regla de páginas nombradas sobre un plan explorado:
        - «tablero/página de X» nombra una página (o varias homónimas en otros
          modelos): solo se ofrecen indicadores de esas páginas; si queda uno
          (o uno claramente principal por página y una sola página), se
          responde con él.
        - Ninguna métrica coincide pero la pregunta nombra una página por su
          tema («partos de 2025»): se ofrecen sus indicadores (tarjetas
          primero) o se responde con el principal («tomé el indicador
          principal de la página X»).
        - La página no tiene indicadores en los modelos: el plan lo indica
          (`pages_without_metrics`) para decirlo junto a la respuesta documental.
        Devuelve el plan nuevo o None."""
        status = plan.get("status")
        source_context = plan.get("source_context") or {}
        pages = self._named_pages(source_context)
        topic = False
        if not pages:
            if status != "not_found" or source_context.get("board_mentions"):
                return None
            if plan.get("reason") in ("metric_not_in_named_report", "metric_not_in_named_page"):
                return None
            pages = self._topic_pages(question)
            topic = True
        if not pages:
            return None
        if status == "ready":
            metric_key = self._logical_key(plan.get("metric") or {})
            if topic or any(
                metric_key in {self._logical_key(member["metric"]) for member in self._page_members(page)}
                for page in pages
            ):
                return None
        elif status not in ("ambiguous", "not_found"):
            return None
        if status == "not_found" and plan.get("reason") in ("metric_not_in_named_report", "metric_not_in_named_page"):
            return None

        resolution = plan.get("metric_resolution") or {}
        offered = [*(resolution.get("candidates") or []), *(resolution.get("suggestions") or [])]
        if status == "ready":
            offered = [{"metric": plan.get("metric")}, *offered]
        if topic and self._topic_offered_elsewhere(pages, offered):
            return None
        groups = []
        for page in pages:
            choice = self._page_choices(question, source_context, page, offered, topic=topic)
            if choice["items"]:
                groups.append((page, choice["items"], choice["principal"], choice["direct"]))
        names = ", ".join(self._page_label(page) for page in pages)
        if not groups:
            if all(not self._page_members(page) for page in pages):
                self._note(
                    f"la pregunta nombra la página {names}, pero esa página no tiene indicadores "
                    "en los modelos disponibles"
                )
                return {**plan, "pages_without_metrics": [self._page_label(page) for page in pages]}
            return None
        scores = [float(item.get("score") or 0.0) for item in offered if item.get("score") is not None]
        best = max(scores) if scores else 1.0
        items, seen = [], set()
        for page, members, _, _ in groups:
            for member in members:
                key = self._logical_key(member["metric"])
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "metric": member["metric"], "score": best, "business_score": best,
                    "matched_name": member.get("title") or member["metric"].get("label"),
                    "page": page.get("page"),
                })
        items = items[: self._SUGGESTION_LIMIT]
        how = "por su tema" if topic else "con «tablero/página de»"
        if len(items) == 1 and len(groups) == 1 and groups[0][3]:
            page, _, principal, _ = groups[0]
            label = items[0]["metric"].get("label")
            visible = (
                f"Tomé el indicador principal de la página {page.get('page')} ({self._page_report(page)}): {label}."
                if principal is not None
                else f"Usé el indicador de la página {page.get('page')} ({self._page_report(page)}): {label}."
            )
            # El nombre de la página y las palabras de agregación («promedio
            # mensual») ya explicaron la elección: no son filtros pendientes.
            generic = {
                canonical_token(word) for word in self._GENERIC_MEASURE_WORDS | self._TECHNICAL_NAME_WORDS
                | FILTER_NEUTRAL_WORDS
            }
            consumed = set(canonical_tokens(page.get("page"))) | {
                token for token in canonical_tokens(question) if token in generic
            }
            forced = self._forced_plan(
                question, intent_result, {key: value for key, value in items[0].items() if key != "page"},
                f"la pregunta nombra la página {self._page_label(page)} {how}; "
                + ("es su indicador principal" if principal is not None else "es su único indicador que coincide"),
                consumed_tokens=consumed,
            )
            if isinstance(forced, dict) and forced.get("status") == "ready":
                forced["notes"] = [visible, *(forced.get("notes") or [])]
                forced["named_page"] = page.get("page")
            return forced
        models = {normalize_text(page.get("semantic_model")) for page, *_ in groups}
        self._note(
            f"la pregunta nombra la página {names} {how}: se ofrecen solo sus indicadores ("
            + ", ".join(str(item["metric"].get("label")) for item in items) + ")"
        )
        # «CIRUGIAS», «Cirugías» y «CIRUGÍAS» son el mismo nombre.
        names_by_key = {}
        for page, *_ in groups:
            names_by_key.setdefault(normalize_text(page.get("page")), str(page.get("page")).strip())
        page_names = list(names_by_key.values())
        return {
            **plan, "status": "ambiguous", "stage": "metric", "reason": "options_from_named_page",
            "named_page": page_names[0] if len(page_names) == 1 else ", ".join(page_names),
            "named_page_report": self._page_report(groups[0][0]) if len(models) == 1 else None,
            "named_page_models": len(models),
            "metric_resolution": {
                "status": "ambiguous",
                "candidates": [{key: value for key, value in item.items() if key != "page"} for item in items],
            },
        }

    def _topic_offered_elsewhere(self, pages, offered):
        """¿Alguna opción ya ofrecida nombra el tema de la página pero está
        fuera de ella? («cirugías»: TOTAL CIRUGÍAS de otro informe) Entonces
        el tema no identifica la página y se mantiene la contrapregunta."""
        member_keys = {
            self._logical_key(member["metric"]) for page in pages for member in self._page_members(page)
        }
        topics = [tokens for tokens in (self._page_name_tokens(page.get("page")) for page in pages) if tokens]
        for item in offered:
            metric = item.get("metric") or {}
            if not metric or self._logical_key(metric) in member_keys:
                continue
            vocabulary = self._metric_vocabulary_tokens(metric)
            if any(all(self._explains(token, vocabulary) for token in tokens) for tokens in topics):
                return True
        return False

    def _routed_page(self, source_context):
        """Página fijada por el enrutamiento fuerte («tablero de triage» ->
        TRIAGE de TABLERO DE ATENCIONES), o None."""
        context = source_context or {}
        if not (
            context.get("status") == "resolved" and context.get("routing_strength") == "strong"
            and context.get("board_kind") in ("page", "documentation") and context.get("dashboard")
        ):
            return None
        page = {"semantic_model": context.get("semantic_model"), "page": context.get("dashboard"),
                "report": context.get("report")}
        return None if self._is_report_page(page) else page

    def _named_page_rejection(self, question, source_context, metric_result, page):
        """Página nombrada y el indicador elegido no está en ella: no se
        responde con el de otra página. Se ofrecen los de la página que
        comparten palabras con la pregunta; si no hay, el encontrado fuera."""
        metric = metric_result.get("metric") or (
            (metric_result.get("candidates") or [{}])[0].get("metric") or {}
        )
        words = self._option_words(question, source_context)
        members = self._page_members(page)
        related = [
            member for member in members
            if words and self._option_coverage(member["metric"], words)
        ]
        collapsed = self._collapse_year_variants(
            [{"metric": member["metric"], "score": metric_result.get("score"),
              "business_score": metric_result.get("score"),
              "matched_name": member.get("title") or member["metric"].get("label")} for member in related],
            question,
        )[: self._SUGGESTION_LIMIT]
        elsewhere = None
        if not collapsed and metric.get("metric_id"):
            elsewhere = {"metric": metric, "score": metric_result.get("score"),
                         "business_score": metric_result.get("score"),
                         "matched_name": metric_result.get("matched_name") or metric.get("label")}
        label = self._page_label(page)
        self._note(
            f"la pregunta nombra la página {label}, pero el indicador elegido ({metric.get('label')}) "
            "no aparece en ella: no se responde con el de otra página; "
            + (f"se ofrecen {len(collapsed)} indicadores de esa página" if collapsed
               else "esa página no tiene indicadores parecidos")
        )
        return {
            "status": "not_found", "stage": "metric",
            "reason": "metric_not_in_named_page",
            "named_page": page.get("page"), "named_page_report": self._page_report(page),
            "named_report": f"{self._page_report(page)} (página {page.get('page')})",
            "found_elsewhere": {
                "metric_id": metric.get("metric_id"), "label": metric.get("label"),
                "semantic_model": metric.get("semantic_model"),
                "pages": self._metric_pages(metric),
            } if metric.get("metric_id") else None,
            "question": question, "source_context": source_context,
            "metric_resolution": {
                "status": "not_found", "candidates": [],
                "suggestions": collapsed or ([elsewhere] if elsewhere else []),
            },
        }

    def named_page_without_metrics(self, question):
        """Páginas («ABORTOS (TABLERO DE ATENCIONES INSTITUCIONALES)») que la
        pregunta nombra al pedir un dato y que no tienen indicadores en los
        modelos disponibles; [] si no aplica. Sirve para decirlo junto a la
        respuesta documental."""
        try:
            normalized = normalize_text(canonical_phrases(question)[0])
            if not normalized or self._is_descriptive(normalized):
                return []
            asks_value = (
                any(re.search(r"(?<![a-z0-9])" + term + r"(?![a-z0-9])", normalized) for term in NUMERIC_TERM_PATTERNS)
                or any(re.search(r"(?<![a-z0-9])(?:" + verb + r")(?![a-z0-9])", normalized)
                       for verb in QUERY_VERB_PATTERNS)
                or self._has_period(normalized)
                or bool(re.search(r"(?<![a-z0-9])(?:por|segun)\s+[a-z]", normalized))
            )
            if not asks_value:
                return []
            source_context = self._source_context(question)
            pages = self._named_pages(source_context) or (
                [] if source_context.get("board_mentions") else self._topic_pages(question)
            )
            if not pages or any(self._page_members(page) for page in pages):
                return []
            return [self._page_label(page) for page in pages]
        except Exception:
            return []

    def _similar_name_ambiguity(self, question, source_context, plan):
        """Regla: el indicador elegido tiene un nombre CASI igual a otro
        indicador distinto (otra tabla o expresión, a menudo de otro tablero)
        y la pregunta no los distingue: IMAGENES TOMADAS (BRIEFING) e
        IMAGENES (ATENCIONES) para «cuántas imágenes se tomaron»; PACIENTES
        OBSERVADOS POR MES y OBSERVADOS_2025 para «cuántos pacientes
        observados hay». Ni la unidad («pacientes») ni el verbo en pasiva
        refleja («se tomaron») distinguen; el rival no puede añadir palabras
        que la pregunta no dice (PROM_IMAGENES, «Total de triages no
        atendidos» no compiten). Dentro del mismo modelo solo compite una
        medida auxiliar sobre la tabla del tema (ver abajo). La MISMA medida
        (mismo modelo, tabla y expresión) en varias páginas no es ambigua: se
        responde una vez."""
        best = plan.get("metric") or {}
        if not best.get("metric_id"):
            return None
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        if strong and normalize_text(source_context.get("semantic_model")) == normalize_text(best.get("semantic_model")):
            return None
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        neutral = units | self._reflexive_verbs(question)
        words = self._option_words(question, source_context)
        core = [word for word in words if word not in neutral]
        if not core or len(self._option_coverage(best, core)) < len(core):
            return None
        matched_name = (plan.get("metric_match") or {}).get("matched_name")
        best_keys = {self._name_key(best.get("label")), self._name_key(matched_name)}
        best_keys.discard(())
        best_tokens = {token for key in best_keys for token in key}
        if not best_tokens:
            return None
        question_tokens = set(canonical_tokens(self._metric_business_question(question, source_context)))

        def said(token):
            return any(_tokens_match_loosely(token, other) for other in question_tokens)

        def table_explains(metric, word):
            return self._explains(word, set(canonical_tokens(metric.get("table"))))

        best_model = normalize_text(best.get("semantic_model"))
        best_table_explains = any(table_explains(best, word) for word in core)
        groups_by = self._rival_group_check(question, best)
        rivals, seen = [], {self._logical_key(best)}
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            logical = self._logical_key(metric)
            if logical in seen:
                continue
            key = self._name_key(metric.get("label"))
            if not key or key in best_keys or not set(key) & best_tokens:
                continue
            if not all(said(token) for token in key):
                continue  # el rival nombra algo que la pregunta no dice
            # Polaridad opuesta: «triages no atendidos» no es «Total de triages
            # atendidos» (solo cuenta la negación: «se tomaron» no distingue).
            polar = (
                set(normalize_text(best.get("label")).split()) ^ set(normalize_text(metric.get("label")).split())
            ) & _POLARITY_WORDS
            if polar and value_contradiction(
                self._metric_business_question(question, source_context),
                metric.get("label"), [best.get("label"), metric.get("label")],
            ):
                continue
            if len(self._option_coverage(metric, core)) < len(core):
                continue
            if not groups_by(metric):
                continue
            # En el MISMO modelo, las tarjetas de nombre parecido suelen ser
            # variantes del propio tablero (CITAS ASIGNADAS / ASIGNADAS): no se
            # pregunta. Solo compite una medida auxiliar (sin visual) sobre la
            # tabla del tema (OBSERVADOS_2025 sobre OBSERVADOS) cuando la
            # elegida se calcula sobre otra tabla que no lo nombra.
            if normalize_text(metric.get("semantic_model")) == best_model and (
                metric.get("appearances") or best_table_explains
                or not all(table_explains(metric, word) for word in core)
            ):
                continue
            seen.add(logical)
            rivals.append(metric)
        if not rivals:
            return None
        rivals.sort(key=lambda metric: 0 if metric.get("appearances") else 1)
        score = (plan.get("metric_match") or {}).get("score")
        items = [
            {"metric": metric, "score": score, "business_score": score,
             "matched_name": matched_name if metric is best else metric.get("label")}
            for metric in [best, *rivals]
        ]
        items = self._collapse_year_variants(items, question)[: self._SUGGESTION_LIMIT]
        if len(items) < 2:
            return None
        self._note(
            f"«{best.get('label')}» tiene un nombre casi igual a otros indicadores distintos ("
            + ", ".join(f"{i['metric'].get('label')} de {i['metric'].get('semantic_model')}" for i in items[1:])
            + ") y la pregunta no indica cuál: se contrapregunta"
        )
        return {
            "status": "ambiguous", "stage": "metric",
            "reason": "similar_name_in_several_boards",
            "question": question, "source_context": source_context,
            "metric_resolution": {"status": "ambiguous", "candidates": items},
        }

    def _forced_plan(self, question, intent_result, item, why, consumed_tokens=(),
                     visible_note=None, group_sibling=False):
        """Plan con un indicador ya decidido (única opción razonable).
        `consumed_tokens`: palabras de la pregunta que ya explicó la elección.
        `visible_note`: nota que se muestra con la respuesta. `group_sibling`:
        indicador elegido porque el pedido no se podía desglosar (no se repite)."""
        metric = item["metric"]
        interpretation = f"{metric.get('label')}: {why}"
        self._note(interpretation)
        forced = {
            "status": "resolved", "metric": metric,
            "matched_name": item.get("matched_name") or metric.get("label"),
            "score": item.get("score"),
            "candidates": [{key: value for key, value in item.items() if not key.startswith("_")}],
            "interpretation": interpretation,
            "final": True,
            "consumed_tokens": set(consumed_tokens or ()),
            "visible_note": visible_note,
            "group_sibling": bool(group_sibling),
        }
        return self._build_plan(question, intent_result, forced_resolution=forced)

    def _refine_options(self, question, intent_result, plan):
        """Revisión final de un plan explorado (sin opción elegida):
        1. tablero nombrado sin opciones de él -> opciones de ese tablero (o
           respuesta directa si una sola explica la pregunta);
        2. opciones sin relación con la pregunta -> fuera;
        3. una sola opción tras agrupar/depurar -> se responde con ella;
        4. respuesta lista pero con un indicador de nombre casi igual en otra
           tabla/tablero -> se contrapregunta."""
        if not isinstance(plan, dict):
            return plan
        # 0. Página nombrada (con «tablero/página de X» o por su tema).
        refined = self._named_page_refinement(question, intent_result, plan)
        if refined is not None:
            if refined.get("status") == "ready" or refined.get("reason") == "options_from_named_page":
                return refined
            if refined.get("status") != plan.get("status"):
                return refined
            plan = refined
        source_context = plan.get("source_context") or {}
        status = plan.get("status")
        if status == "ready":
            similar = self._similar_name_ambiguity(question, source_context, plan)
            return similar if similar is not None else plan
        if status not in ("ambiguous", "not_found") or plan.get("reason") not in (None, "metric_not_in_named_report"):
            if status == "not_found" and (plan.get("metric_resolution") or {}).get("suggestions"):
                plan["metric_resolution"] = self._prune_unrelated_options(
                    question, source_context, plan["metric_resolution"],
                )
            return plan

        resolution = plan.get("metric_resolution") or {}
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        board_model = normalize_text(source_context.get("semantic_model"))
        if strong and plan.get("reason") == "metric_not_in_named_report":
            # El indicador elegido era de otro tablero y se ofrecen los del
            # tablero nombrado: si uno solo explica la pregunta, se responde.
            board_items = [
                item for item in resolution.get("suggestions") or []
                if normalize_text((item.get("metric") or {}).get("semantic_model")) == board_model
            ]
            words = self._option_words(question, source_context)
            full = [
                item for item in board_items
                if words and len(self._option_coverage(item.get("metric"), words)) == len(words)
            ]
            if len(full) == 1:
                board = source_context.get("report") or source_context.get("semantic_model")
                return self._forced_plan(
                    question, intent_result, full[0],
                    f"único indicador del tablero nombrado ({board}) que explica la pregunta",
                )
        if (
            strong and status == "not_found" and plan.get("reason") is None
            and self._board_named_explicitly(question, source_context)
        ):
            # «peso por servicio en lavandería»: ningún nombre alcanzó el
            # puntaje, pero el tablero nombrado tiene UN indicador visible que
            # explica todas las palabras distintivas (PESO TOTAL por Mes): es
            # ese, no una contrapregunta de una sola opción ni la documentación.
            words = self._option_words(question, source_context)
            seen, full = set(), []
            for item in [*(resolution.get("candidates") or []), *(resolution.get("suggestions") or [])]:
                metric = item.get("metric") or {}
                key = self._logical_key(metric)
                if (
                    key in seen or not metric.get("appearances")
                    or normalize_text(metric.get("semantic_model")) != board_model
                ):
                    continue
                seen.add(key)
                if words and len(self._option_coverage(metric, words)) == len(words):
                    full.append(item)
            if len(full) == 1:
                board = source_context.get("report") or source_context.get("semantic_model")
                return self._forced_plan(
                    question, intent_result, full[0],
                    f"único indicador visible del tablero nombrado ({board}) que explica la pregunta",
                )
        if strong and plan.get("reason") is None and self._board_named_explicitly(question, source_context):
            offered =[*(resolution.get("candidates") or []), *(resolution.get("suggestions") or [])]
            if offered and not any(
                normalize_text((item.get("metric") or {}).get("semantic_model")) == board_model
                for item in offered
            ):
                kind, found = self._named_board_options(question, source_context, resolution)
                board = source_context.get("report") or source_context.get("semantic_model")
                if kind == "resolved":
                    return self._forced_plan(
                        question, intent_result, found,
                        f"único indicador del tablero nombrado ({board}) que explica la pregunta; "
                        "las opciones de otros tableros se descartaron",
                    )
                if kind == "options":
                    self._note(
                        f"la pregunta nombra el tablero {board}: se ofrecen sus indicadores "
                        f"({', '.join(str(i['metric'].get('label')) for i in found)}) y no los de otros tableros"
                    )
                    best = max(float(item.get("score") or 0.0) for item in found)
                    plan = {**plan, "status": "ambiguous", "reason": "options_from_named_board",
                            "named_report": board,
                            "metric_resolution": {"status": "ambiguous",
                                                  "candidates": [{**i, "score": best} for i in found]}}
                    return plan
                plan = {**plan, "reason": "metric_not_in_named_report", "named_report": board}
                self._note(
                    f"la pregunta nombra el tablero {board}, pero no tiene indicadores parecidos: "
                    "se ofrecen los de otros tableros"
                )

        resolution = self._prune_unrelated_options(question, source_context, resolution)
        plan = {**plan, "metric_resolution": resolution}
        # «M por X»: fuera las opciones que no se desglosan por X.
        grouped = self._group_feasible_options(question, intent_result, plan)
        if grouped is not None:
            if grouped.get("status") != "ambiguous":
                return grouped
            plan = grouped
            resolution = plan["metric_resolution"]
        candidates = resolution.get("candidates") or []
        if status == "ambiguous" and plan.get("reason") is None and len(candidates) > 1:
            named = self._options_named_by_question(question, source_context, candidates)
            if len({self._logical_key(item["metric"]) for item in named}) == 1:
                return self._forced_plan(
                    question, intent_result, named[0],
                    "la pregunta dice su nombre completo; las demás opciones añaden palabras que "
                    "la pregunta no dice: se responde sin contrapreguntar",
                )
        if (
            status == "ambiguous" and plan.get("reason") is None and len(candidates) == 1
            and float(candidates[0].get("business_score") or 0.0) >= self.min_metric_score
        ):
            return self._forced_plan(
                question, intent_result, candidates[0],
                "única opción tras agrupar variantes y depurar las que no tienen que ver "
                "con la pregunta: se responde sin contrapreguntar",
            )
        return plan

    # ---------------- calificativos sin interpretar ----------------
    def _resolve_qualifiers(self, question, intent_result, metric, metric_result, source_context,
                            candidates, group_by, used_fields, consumed_tokens, allow_switch=True):
        """Palabras que quedan sin interpretar tras métrica, periodo y filtros:
        0) si nombran la tabla o la página del propio indicador, ya están
           explicadas («consultas ambulatorias» -> tabla CONSULTAS_AMBULATORIAS);
        a) si otro indicador las contiene en su nombre (TRIAGES_PEDIATRICOS_2025),
           se cambia a ese indicador o se contrapregunta entre los que las tienen;
        b) si coinciden de forma aproximada con un valor de dimensión del modelo
           (pediátricos -> PEDIATRIA, menores de edad -> MENORES DE EDAD), se filtra.
        Devuelve {"plan": plan|None, "filters": [(campo, valor)], "consumed": tokens}."""
        result = {"plan": None, "filters": [], "consumed": set()}
        leftover = self._implicit_value_text(
            question, metric, metric_result.get("matched_name"), source_context, group_by,
            extra_removals=consumed_tokens,
        )
        words = [word for word in leftover.split() if len(word) >= 3]
        vocabulary = self._metric_vocabulary_tokens(metric)
        # La agrupación «por servicio» (SERVICIOS de la tabla CAMAS DISPONIBLES)
        # no explica «disponibles»: se buscan las palabras de la tabla también
        # entre las que quitó el nombre de la columna agrupada.
        table_words = list(words)
        if group_by:
            ungrouped = self._implicit_value_text(
                question, metric, metric_result.get("matched_name"), source_context, [],
                extra_removals=consumed_tokens,
            )
            table_words.extend(word for word in ungrouped.split() if len(word) >= 3 and word not in table_words)
        if not words and not table_words:
            return result

        own = [word for word in words if self._explains(canonical_token(word), vocabulary)]
        own_table = [word for word in table_words if self._explains(canonical_token(word), vocabulary)]
        # Una palabra que solo nombra la tabla del indicador pero también es un
        # valor documentado de una de sus columnas se filtra («camas
        # disponibles» en la tabla CAMAS DISPONIBLES -> ESTADOS_CAM = DISPONIBLE).
        for word, field, resolved in self._table_word_filters(
            metric, own_table, candidates, used_fields, metric.get("semantic_model"),
        ):
            result["filters"].append((field, resolved))
            result["consumed"].add(canonical_token(word))
            own = [item for item in own if item != word]
            words = [item for item in words if item != word]
            self._note(
                f"«{word}» nombra la tabla {metric.get('table')} del indicador y además es el valor "
                f"{resolved['value']} de {field['table']}[{field['column']}]: se aplica como filtro"
            )
        if own:
            result["consumed"].update(canonical_token(word) for word in own)
            self._note(
                f"«{' '.join(own)}» ya lo explica el indicador {metric.get('label')} "
                f"(su tabla {metric.get('table')} o su página)"
            )
            words = [word for word in words if word not in own]
        if not words:
            return result

        if allow_switch:
            plan = self._qualifier_metric_switch(
                question, intent_result, metric, metric_result, source_context, words,
            )
            if plan is not None:
                result["plan"] = plan
                return result

        # Una palabra que nombra OTRO indicador del mismo modelo («realizadas»
        # junto a CIRUGÍAS PROGRAMADAS) es probablemente otra medida, no un
        # valor: no se aproxima a un valor de dimensión.
        core = [
            canonical_token(word)
            for word in self._question_content_words(self._metric_business_question(question, source_context))
            if word not in words and self._explains(canonical_token(word), vocabulary)
        ]
        siblings = self._sibling_metric_tokens(metric, core)
        candidates_words = [
            word for word in words
            if not self._explains(canonical_token(word), siblings)
        ]
        for field, resolved in self._fuzzy_qualifier_filters(
            metric, candidates, used_fields, candidates_words, question=question,
        ):
            result["filters"].append((field, resolved))
            self._note(
                f"«{resolved['phrase']}» se interpretó como {field['table']}[{field['column']}] = "
                f"{resolved['value']} (coincidencia aproximada por raíz/plural)"
            )
        # c) Lo que sigue sin interpretar y la documentación del propio
        # indicador usa para describirlo («aumento de PRECIO», «imágenes
        # DIAGNÓSTICAS»): es parte del indicador, no un filtro.
        filtered = {
            canonical_token(word)
            for _, resolved in result["filters"] for word in str(resolved.get("phrase") or "").split()
        }
        # Sin las palabras de indicadores hermanos («realizadas» junto a
        # CIRUGÍAS PROGRAMADAS es otra medida aunque la documentación la nombre).
        remaining = [word for word in candidates_words if canonical_token(word) not in filtered]
        # El sustantivo principal («LISTA DE PACIENTES en espera») no lo explica
        # la documentación: si el indicador no lo nombra, cuenta otra cosa.
        head = self._head_token(question, source_context)
        remaining = [word for word in remaining if canonical_token(word) != head]
        skip = set(consumed_tokens) | filtered
        for word, evidence in self._documented_qualifiers(question, metric, remaining, skip_tokens=skip):
            result["consumed"].add(canonical_token(word))
            self._note(
                f"«{word}» describe al propio indicador {metric.get('label')} según su documentación "
                f"(«{evidence}»): no es un filtro"
            )
        return result

    # ---------------- documentación del indicador ----------------
    _DOC_TEXT_FIELDS = (
        "description", "visuals", "indicators", "documented_measures", "definitions",
        "business_rules", "notes",
    )

    def _semantic_documents_index(self):
        """{modelo normalizado: [tableros documentados]} de data/semantic_documents."""
        cached = self.__dict__.get("_semantic_documents_cache")
        if cached is not None:
            return cached
        index = {}
        root = self.project_root / "data" / "semantic_documents"
        try:
            paths = sorted(root.rglob("*.json")) if root.exists() else []
        except OSError:
            paths = []
        for path in paths:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(document, dict):
                continue
            model = normalize_text(document.get("semantic_model"))
            for dashboard in document.get("dashboards") or []:
                # El diccionario de variables no es una página: sus medidas y
                # textos no deben contar como documentación de una página.
                if isinstance(dashboard, dict) and not dashboard.get("is_dictionary"):
                    index.setdefault(model, []).append(dashboard)
        self._semantic_documents_cache = index
        return index

    @staticmethod
    def _flatten_texts(value):
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [text for item in value.values() for text in QueryPlanBuilder._flatten_texts(item)]
        if isinstance(value, (list, tuple)):
            return [text for item in value for text in QueryPlanBuilder._flatten_texts(item)]
        return []

    def _metric_documentation(self, metric):
        """Textos que describen el indicador: su descripción, su DAX y la
        documentación del tablero donde está (tablero con el nombre de su
        página o de su nombre/tabla, o cuyas visualizaciones lo nombran)."""
        cache = self.__dict__.setdefault("_metric_documentation_cache", {})
        key = (self._logical_key(metric), normalize_text(metric.get("label")))
        if key in cache:
            return cache[key]
        texts = [str(metric.get(field)) for field in ("description", "model_expression") if metric.get(field)]
        vocabulary = self._metric_vocabulary_tokens(metric, with_pages=False)
        pages = {normalize_text(page) for page in self._metric_pages(metric)}
        stop = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS}
        label = normalize_text(metric.get("label"))
        label_specific = len([t for t in canonical_tokens(label) if t not in stop and not t.isdigit()]) >= 2
        for dashboard in self._semantic_documents_index().get(normalize_text(metric.get("semantic_model")), []):
            name = normalize_text(dashboard.get("name"))
            name_tokens = [t for t in canonical_tokens(name) if t not in stop and len(t) >= 3]
            dashboard_texts = [
                text for field in self._DOC_TEXT_FIELDS for text in self._flatten_texts(dashboard.get(field))
            ]
            linked = name in pages or (name_tokens and all(self._explains(t, vocabulary) for t in name_tokens))
            if linked:
                texts.extend(dashboard_texts)
                continue
            mentions = [text for text in dashboard_texts if label_specific and _exact_phrase(normalize_text(text), label)]
            if mentions:
                texts.extend(mentions)
                texts.extend(self._flatten_texts(dashboard.get("description")))
        cache[key] = texts
        return texts

    def _same_measure_metrics(self, metric):
        """El indicador y los demás aprobados con su misma medida (modelo,
        tabla y expresión), el propio primero."""
        key = self._logical_key(metric)
        result = [metric]
        if not key[-1]:
            return result
        for other in self._dedupe_metrics(self.metrics):
            if other is metric or other.get("validation_status") != "approved":
                continue
            if self._logical_key(other) == key and other.get("metric_id") != metric.get("metric_id"):
                result.append(other)
        return result

    _BREAKDOWN_LABEL_RE = re.compile(r"(?<![a-z0-9])(?:por|x|segun)\s+[a-z]")

    def _scalar_representative(self, metric):
        """Para un valor único, el nombre de un gráfico «PACIENTES por
        ASEGURADORA» describe un desglose que no se muestra: si la misma
        medida está en una tarjeta («TOTAL PACIENTES»), se responde con ella."""
        if not self._BREAKDOWN_LABEL_RE.search(normalize_text(metric.get("label"))):
            return metric
        for other in self._same_measure_metrics(metric)[1:]:
            if self._BREAKDOWN_LABEL_RE.search(normalize_text(other.get("label"))):
                continue
            if any(item.get("visual_type") == "card" for item in other.get("appearances") or []):
                self._note(
                    f"{metric.get('label')} es la misma medida que la tarjeta {other.get('label')}: "
                    "para un valor único se responde con la tarjeta"
                )
                return other
        return metric

    def _documented_qualifiers(self, question, metric, words, skip_tokens=()):
        """[(palabra, evidencia)] de las palabras que la documentación del
        indicador usa y que en la pregunta califican a una palabra del propio
        indicador (vecina inmediata, saltando conectores): «compras con
        aumento de PRECIO» (aumento ∈ nombre; «precios» en la documentación).
        Nunca palabras de dimensión (servicio, especialidad...)."""
        if not words:
            return []
        # La misma medida publicada en otra página (TOTAL PACIENTES de DETALLE
        # OCUPACIÓN = PACIENTES por ASEGURADORA de INICIO) trae también la
        # documentación de esa página.
        texts = []
        for same in self._same_measure_metrics(metric):
            texts.extend(text for text in self._metric_documentation(same) if text not in texts)
        if not texts:
            return []
        forms = {}
        for text in texts:
            normalized = normalize_text(text)
            for doc_word in normalized.split():
                if len(doc_word) < 4:
                    continue
                for form in (canonical_token(doc_word), _stem_token(doc_word)):
                    forms.setdefault(form, normalized)
        dimension_words = {
            canonical_token(word) for synonyms in DIMENSION_SYNONYMS.values() for word in synonyms
        } | {canonical_token(word) for word in self.PLAUSIBLE_VALUE_COLUMN_WORDS}
        vocabulary = self._metric_vocabulary_tokens(metric)
        connectors = {
            "de", "del", "la", "el", "los", "las", "con", "en", "y", "a", "al", "por",
            "estan", "esta", "estaban", "estuvieron", "hay", "son", "es", "fueron",
        }
        question_words = normalize_text(question).split()
        found = []
        for word in words:
            token = canonical_token(word)
            if len(token) < 4 or token in dimension_words:
                continue
            evidence = forms.get(token) or forms.get(_stem_token(word))
            if not evidence:
                continue
            adjacent = False
            for index, other in enumerate(question_words):
                if other != word:
                    continue
                for step in (-1, 1):
                    position = index + step
                    while 0 <= position < len(question_words) and (
                        question_words[position] in connectors
                        or (
                            canonical_token(question_words[position]) in skip_tokens
                            and not self._explains(canonical_token(question_words[position]), vocabulary)
                        )
                    ):
                        position += step
                    if 0 <= position < len(question_words) and self._explains(
                        canonical_token(question_words[position]), vocabulary,
                    ):
                        adjacent = True
            if not adjacent:
                continue
            # Fragmento de la documentación alrededor de la palabra (para el razonamiento).
            doc_words = evidence.split()
            spot = next(
                (i for i, doc_word in enumerate(doc_words)
                 if canonical_token(doc_word) == token or _stem_token(doc_word) == _stem_token(word)),
                0,
            )
            snippet = " ".join(doc_words[max(0, spot - 4):spot + 4])
            found.append((word, snippet))
        return found

    def _periods_for_metric(self, question, metric, matched_name):
        """_analyze_periods, salvo una medida atada al MISMO año que pide la
        pregunta (TRIAGES_PEDIATRICOS_2025 «en 2025»): ahí el año sí se aplica
        como filtro (no cambia el valor y deja el periodo explícito en la
        respuesta). Con otro año, o sin año en la medida, nada cambia."""
        temporal = self._analyze_periods(question, metric, matched_name)
        if temporal.get("period") is not None:
            return temporal
        names = [metric.get("label"), metric.get("measure"), matched_name]
        name_years = {
            int(token) for name in names if name
            for token in canonical_tokens(name) if re.fullmatch(r"(?:19|20)\d{2}", token)
        }
        if not name_years:
            return temporal
        plain = self._analyze_periods(question)
        period = plain.get("period")
        if plain.get("granularity") and not temporal.get("granularity"):
            return temporal  # «mensual» era parte del nombre: no se agrupa
        if period and period.get("kind") == "year" and period.get("year") in name_years:
            self._note(
                f"la medida {metric.get('label')} ya es del año {period.get('year')}; "
                "el año pedido se aplica igual como filtro"
            )
            return plain
        return temporal

    def _sibling_metric_tokens(self, metric, core):
        """Palabras de los nombres de los indicadores «hermanos»: del mismo
        modelo y que también nombran el sustantivo de la pregunta (`core`):
        CIRUGÍAS REALIZADAS es hermano de CIRUGÍAS PROGRAMADAS."""
        model = normalize_text(metric.get("semantic_model"))
        own = self._logical_key(metric)
        # Al probar otro candidato porque el elegido no entendía un filtro
        # (_candidate_that_filters), el elegido no cuenta como «hermano»: sus
        # palabras («ocupadas» de CAMAS OCUPADAS) pueden ser valores del otro.
        exempt = frozenset(self.__dict__.get("_sibling_exempt") or ())
        cache = self.__dict__.setdefault("_sibling_tokens_cache", {})
        key = (model, own, tuple(sorted(core)), exempt)
        if key in cache:
            return cache[key]
        _, generic = self._weak_token_sets()
        own_tokens = self._metric_vocabulary_tokens(metric, with_pages=False)
        tokens = set()
        if core:
            for other in self._dedupe_metrics(self.metrics):
                if (
                    other.get("validation_status") != "approved"
                    or normalize_text(other.get("semantic_model")) != model
                    or self._logical_key(other) == own
                    or self._logical_key(other) in exempt
                ):
                    continue
                names = [other.get("label"), other.get("measure")] + [
                    appearance.get("visual_title") for appearance in other.get("appearances") or []
                ]
                for name in names:
                    name_tokens = [t for t in canonical_tokens(name) if not t.isdigit()]
                    if not all(self._explains(token, name_tokens) for token in core):
                        continue
                    tokens.update(
                        token for token in name_tokens
                        if len(token) >= 4 and token not in generic and token not in own_tokens
                    )
        cache[key] = tokens
        return tokens

    def _qualifier_metric_switch(self, question, intent_result, metric, metric_result,
                                 source_context, words):
        """Regla 3a: ¿con el calificativo cambia la mejor métrica? Busca
        indicadores cuyo nombre (o tabla/página) contiene el calificativo y el
        sustantivo principal. Uno claramente mejor -> se usa; varios -> se
        contrapregunta entre ellos (y el elegido originalmente)."""
        qualifiers = [canonical_token(word) for word in words]
        current_vocabulary = self._metric_vocabulary_tokens(metric)
        # Lo que ya explicaba el indicador elegido (sin palabras genéricas de
        # medida) debe seguir explicado: «cirugías programadas y realizadas»
        # no cambia CIRUGÍAS PROGRAMADAS por CIRUGÍAS REALIZADAS (son dos medidas).
        core = [
            canonical_token(word)
            for word in self._question_content_words(self._metric_business_question(question, source_context))
            if canonical_token(word) not in qualifiers
            and self._explains(canonical_token(word), current_vocabulary)
        ]
        found = self._qualifier_candidates(
            question, source_context, qualifiers, core, exclude={self._logical_key(metric)},
        )
        if not found:
            return None
        top = found[0]
        second = found[1] if len(found) > 1 else None
        words_text = " ".join(words)
        clear = (
            top["business_score"] >= self.min_metric_score
            and (second is None or second["_covered"] < top["_covered"]
                 or second.get("_explained", 0) < top.get("_explained", 0)
                 or top["score"] - second["score"] >= self.ambiguity_margin)
        )
        if clear:
            chosen = {key: value for key, value in top.items() if not key.startswith("_")}
            interpretation = (
                f"«{words_text}» forma parte del indicador {top['metric'].get('label')} "
                f"(en lugar de {metric.get('label')}, que no lo explicaba)"
            )
            self._note(interpretation)
            forced = {
                "status": "resolved", "metric": top["metric"],
                "matched_name": top["matched_name"], "score": top["score"],
                "candidates": [chosen], "interpretation": interpretation,
            }
            return self._build_plan(question, intent_result, forced_resolution=forced)

        options = [
            {key: value for key, value in item.items() if not key.startswith("_")}
            for item in found[: self._SUGGESTION_LIMIT - 1]
        ]
        options.append({
            "metric": metric, "score": metric_result.get("score"),
            "business_score": metric_result.get("score"),
            "matched_name": metric_result.get("matched_name"),
        })
        best_score = max(float(item.get("score") or 0.0) for item in options)
        for item in options:
            item["score"] = best_score  # todas se muestran: la pregunta no decide
        self._note(
            f"«{words_text}» aparece en el nombre de otros indicadores "
            f"({', '.join(str(i['metric'].get('label')) for i in options[:-1])}); "
            f"no se ofrece {metric.get('label')} sin ese calificativo: se contrapregunta"
        )
        return {
            "status": "ambiguous", "stage": "metric",
            "reason": "qualifier_matches_other_metrics",
            "question": question, "source_context": source_context,
            "unresolved_text": words_text,
            "metric_resolution": {"status": "ambiguous", "candidates": options},
        }

    def _qualifier_candidates(self, question, source_context, qualifiers, core, exclude=()):
        """Indicadores cuyo nombre, tabla o página explican al menos un
        calificativo y todas las palabras `core`, ordenados (más calificativos
        cubiertos, mejor coincidencia por nombre) y sin variantes por año repetidas.
        Con un tablero nombrado (routing fuerte) solo los de ese modelo; una
        palabra que solo coincide con su nombre pero es una dimensión («por
        eps» no es el TABLERO EPS) no restringe."""
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
            and self._board_named_explicitly(question, source_context)
        )
        named_model = normalize_text(source_context.get("semantic_model")) if strong else ""
        business_question = self._metric_business_question(question, source_context)
        weights = self._token_weight_index()
        stop = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}
        question_words = [
            token for token in canonical_tokens(business_question)
            if token not in stop and len(token) >= 3 and not _is_request_word(token)
        ]

        found, seen = [], set(exclude)
        for other in self._dedupe_metrics(self.metrics):
            if other.get("validation_status") != "approved":
                continue
            if named_model and normalize_text(other.get("semantic_model")) != named_model:
                continue
            logical = self._logical_key(other)
            if logical in seen:
                continue
            vocabulary = self._metric_vocabulary_tokens(other)
            covered = [token for token in qualifiers if self._explains(token, vocabulary)]
            if not covered or not all(self._explains(token, vocabulary) for token in core):
                continue
            # Nombres sin contenido propio («Promedio de MIN») no cuentan, pero
            # tampoco descartan el indicador si su etiqueta sí nombra algo; los
            # conectores del nombre («TIEMPO PROMEDIO PARA ATENCIÓN EN TRIAGE»)
            # no se exigen en la pregunta.
            names = [name for name in self._metric_names(other) if not self._weak_name_kind(name)]
            scored = []
            for name in names:
                scored.append((self._loose_phrase_score(business_question, name, weights), name))
                content_name = " ".join(
                    word for word in normalize_text(name).split() if canonical_token(word) not in stop
                )
                if content_name and content_name != normalize_text(name) and len(content_name.split()) >= 2:
                    scored.append((self._loose_phrase_score(business_question, content_name, weights), name))
            if other.get("table") and other.get("label") and not self._weak_name_kind(other.get("label")):
                scored.append((
                    self._loose_phrase_score(
                        business_question, f"{other.get('label')} {other.get('table')}", weights,
                    ),
                    other.get("label"),
                ))
            score, name = max(scored, key=lambda pair: pair[0], default=(0.0, None))
            if score <= 0 or not name:
                continue
            seen.add(logical)
            business = score
            if not other.get("appearances"):
                score -= 0.10
            # Palabras de la pregunta que su propio nombre explica («tiempo
            # PROMEDIO ... triage»): desempata entre los que cubren el calificativo.
            name_tokens = {token for value in names for token in canonical_tokens(value) if len(token) >= 3}
            explained = sum(1 for token in question_words if self._explains(token, name_tokens))
            found.append({
                "metric": other, "score": round(score, 4), "business_score": round(business, 4),
                "matched_name": name, "_covered": len(covered), "_explained": explained,
            })
        found.sort(key=lambda item: (
            -item["_covered"], -item["_explained"], -item["score"], normalize_text(item["metric"].get("label")),
        ))
        return self._collapse_year_variants(found, question)

    def _promote_qualifier_metrics(self, question, source_context, metric_result):
        """Empate entre indicadores que NO explican una palabra de la pregunta
        («consultas PRIORITARIAS»: Consultas de dos tableros): los indicadores
        que sí la nombran (PRIORITARIAS_2025, tabla CONSULTAS PRIORITARIAS) se
        ofrecen primero. Se sigue contrapreguntando: no se elige por el usuario."""
        candidates = list(metric_result.get("candidates") or [])
        if not candidates:
            return metric_result
        best = max(float(item.get("score") or 0.0) for item in candidates)
        tied = [item for item in candidates if best - float(item.get("score") or 0.0) < self.ambiguity_margin]
        vocabularies = [self._metric_vocabulary_tokens(item["metric"]) for item in tied]
        business_question = self._metric_business_question(question, source_context)
        content = [canonical_token(word) for word in self._question_content_words(business_question)]
        qualifiers = [t for t in content if not any(self._explains(t, v) for v in vocabularies)]
        if not qualifiers:
            return metric_result
        core = [t for t in content if t not in qualifiers]
        found = self._qualifier_candidates(
            question, source_context, qualifiers, core,
            exclude={self._logical_key(item["metric"]) for item in tied},
        )[:3]
        if not found:
            return metric_result
        promoted = [
            {**{k: v for k, v in item.items() if not k.startswith("_")}, "score": best}
            for item in found
        ]
        promoted_keys = {self._logical_key(item["metric"]) for item in promoted}
        rest = [item for item in candidates if self._logical_key(item["metric"]) not in promoted_keys]
        self._note(
            f"ningún indicador empatado explica «{' '.join(qualifiers)}»; se ofrecen primero los que sí: "
            + ", ".join(str(item["metric"].get("label")) for item in promoted)
        )
        return {**metric_result, "candidates": promoted + rest}

    @staticmethod
    def _loose_phrase_score(question, name, weights=None):
        """_phrase_score tolerando plural/género/conjugación: las palabras de la
        pregunta que coinciden por raíz con una del nombre se reemplazan por
        ella («imágenes se tomaron» cubre «IMAGENES TOMADAS»)."""
        name_tokens = canonical_tokens(name)
        rewritten = []
        for word in normalize_text(question).split():
            token = canonical_token(word)
            match = next((other for other in name_tokens if _tokens_match_loosely(token, other)), None)
            rewritten.append(match or word)
        return _phrase_score(" ".join(rewritten), name, weights)

    def _value_token_index(self, semantic_model, field):
        """Valores del campo con sus palabras canónicas (caché por campo)."""
        cache = self.__dict__.setdefault("_value_token_cache", {})
        key = (normalize_text(semantic_model), normalize_text(field.get("table")), normalize_text(field.get("column")))
        # Un dominio de más de _QUALIFIER_MAX_DOMAIN valores no se indexa (abajo):
        # si ya se sabe que los pasa (consulta de cardinalidad o dominio ya
        # traído) o es un identificador/dato de persona (documento, ingreso,
        # OID...: siempre miles de valores), no se consulta. Para el resto basta
        # pedir _QUALIFIER_MAX_DOMAIN + 1 valores: con eso se sabe si los pasa.
        domains = self._domain_cache()
        if domains is not None and (
            identifier_column(field.get("column"))
            or domains.exceeds(semantic_model, field["table"], field["column"], self._QUALIFIER_MAX_DOMAIN)
        ):
            domains.note_avoided(semantic_model, field["table"], field["column"])
            return []
        values = self._get_values(semantic_model, field["table"], field["column"],
                                  limit=self._QUALIFIER_MAX_DOMAIN + 1)
        if values is None:
            return None  # fallo temporal: no se cachea
        cached = cache.get(key)
        if cached is not None and cached[0] is values:
            return cached[1]  # mismo dominio (la caché lo renueva al vencer)
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}
        index = []
        if len(values) <= self._QUALIFIER_MAX_DOMAIN:
            for value in values:
                tokens = [t for t in canonical_tokens(value) if t not in ignored and t != "%"]
                if tokens and not all(t.isdigit() for t in tokens):
                    index.append((value, tokens))
        cache[key] = (values, index)
        return index

    @staticmethod
    def _fuzzy_value_score(span_tokens, value_tokens):
        """Todas las palabras del calificativo están en el valor (por raíz o
        tipeo leve) y cubren al menos la mitad del valor. 0.90-1.00."""
        if not span_tokens or not any(len(token) >= 4 for token in span_tokens):
            return 0.0
        matched = set()
        for token in span_tokens:
            hit = next(
                (i for i, other in enumerate(value_tokens) if _tokens_match_loosely(token, other)),
                None,
            )
            if hit is None:
                return 0.0
            matched.add(hit)
        coverage = len(matched) / len(value_tokens)
        if coverage < 0.5:
            return 0.0
        return round(0.90 + 0.10 * coverage, 4)

    def _fuzzy_qualifier_filters(self, metric, candidates, used_fields, words, question=None):
        """Regla 3b: valores de dimensión aproximados del modelo del indicador.
        Prueba primero la frase completa y luego frases más cortas (cada una
        puede ser un filtro distinto: «ortopedia» -> ESPECIALIDAD, «sura» ->
        ASEGURADORA). Revisa hasta _QUALIFIER_FIELD_LIMIT campos."""
        semantic_model = metric.get("semantic_model")
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS}
        used = set(used_fields)
        fields = []
        for field in candidates:
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in used or field.get("own_fallback") or not self._implicit_eligible(field, semantic_model):
                continue
            if any(key == (normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in fields):
                continue
            if not self._field_filters_metric(metric, field):
                continue  # un filtro en una tabla que no filtra al indicador no cambia nada
            fields.append(field)
            if len(fields) >= self._QUALIFIER_FIELD_LIMIT:
                break

        # Búsqueda incremental: los dominios se traen en lotes pequeños (solo
        # columnas de baja cardinalidad; basta el tope _QUALIFIER_MAX_DOMAIN + 1)
        # cuando el bucle llega a cada campo, y una frase deja de revisar campos
        # al encontrar una coincidencia de 1.0 (el máximo: ningún campo
        # posterior la reemplaza). Mismo orden y mismos valores que antes.
        qualifier_limit = self._QUALIFIER_MAX_DOMAIN + 1
        remaining = list(words)
        found = []
        progress = True
        while remaining and progress:
            progress = False
            for size in range(len(remaining), 0, -1):
                for start in range(0, len(remaining) - size + 1):
                    span = remaining[start:start + size]
                    tokens = [canonical_token(word) for word in span if canonical_token(word) not in ignored]
                    if not tokens:
                        continue
                    best = None
                    for position, field in enumerate(fields):
                        if best is not None and best[0] >= 1.0:
                            break
                        key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
                        if key in used:
                            continue
                        self._prefetch_next(semantic_model, fields, position, limit=qualifier_limit, skip=used)
                        index = self._value_token_index(semantic_model, field) or []
                        domain = (
                            self._get_values(semantic_model, field["table"], field["column"])
                            if index else []
                        ) or [value for value, _ in index]
                        for value, value_tokens in index:
                            score = self._fuzzy_value_score(tokens, value_tokens)
                            if not score or (best is not None and score <= best[0]):
                                continue
                            # Una palabra genérica sola («general») no elige un
                            # valor de varias palabras (HOSPITALIZACIÓN GENERAL)
                            # salvo que el resto del valor esté en la pregunta.
                            if self._generic_partial_value(tokens, value_tokens, question):
                                continue
                            # La coincidencia por raíz no puede elegir el
                            # valor opuesto («de edad» de MAYORES DE EDAD
                            # cuando se pidió «menores de edad»).
                            if self._value_contradiction(
                                f"{' '.join(span)} {question or ''}", value, domain, field,
                                "calificativo aproximado",
                            ):
                                continue
                            best = (score, field, value, value_tokens)
                    if best is None:
                        continue
                    score, field, value, value_tokens = best
                    used.add((normalize_text(field.get("table")), normalize_text(field.get("column"))))
                    found.append((field, {
                        "value": value, "score": score, "phrase": " ".join(span),
                        "tokens": set(value_tokens) | {canonical_token(word) for word in span},
                    }))
                    remaining = remaining[:start] + remaining[start + size:]
                    progress = True
                    break
                if progress:
                    break
        return found

    def build(self, question, intent_result=None, selected_metric_id=None):
        """Plan de la consulta. Las decisiones de resolución del indicador
        (nombres descartados, ambigüedades, calificativos) quedan en
        plan["resolution_notes"] para el razonamiento del turno."""
        notes = []
        previous = self.__dict__.get("_resolution_notes")
        self._resolution_notes = notes
        original_question = question
        question, rewrites = canonical_phrases(question)
        for phrase, replacement in rewrites:
            notes.append(f"«{phrase}» se interpretó como «{replacement}»")
        try:
            plan = self._build_plan(question, intent_result, selected_metric_id)
            if rewrites and isinstance(plan, dict) and plan.get("question") == question:
                plan["question"] = original_question
            # Si el indicador elegido no admite el filtro/periodo/agrupación
            # pedido pero existe con el mismo nombre en otro tablero, se
            # pregunta cuál antes de decir que no se pudo.
            if (
                selected_metric_id is None and isinstance(plan, dict)
                and plan.get("status") == "unsupported_filter"
                and plan.get("reason") != "possible_dimension_value_not_resolved"
                and (plan.get("metric_resolution") or {}).get("metric")
            ):
                same_name = self._same_name_ambiguity(
                    question, plan.get("source_context") or {}, plan["metric_resolution"],
                )
                if same_name is not None:
                    plan = same_name
            if selected_metric_id is None:
                plan = self._refine_options(question, intent_result, plan)
        finally:
            self._resolution_notes = previous
        if notes and isinstance(plan, dict):
            plan["resolution_notes"] = list(dict.fromkeys([*(plan.get("resolution_notes") or []), *notes]))
        return plan

    def _build_plan(self, question, intent_result=None, selected_metric_id=None,
                    forced_resolution=None):
        intent_result = intent_result or {}
        dashboard = intent_result.get("dashboard")
        source_context = self._source_context(question, dashboard=dashboard)
        metric_result = forced_resolution or self._resolve_metric_flexible(
            question, source_context, selected_metric_id=selected_metric_id,
            with_suggestions=True,
        )
        exploring = selected_metric_id is None and forced_resolution is None

        # Página nombrada sin ese indicador: no se usa el de otra página.
        if exploring and metric_result.get("page_hint_ignored"):
            return self._named_page_rejection(
                question, source_context, metric_result, metric_result["page_hint_ignored"],
            )

        if metric_result.get("status") != "resolved":
            if exploring and metric_result.get("status") == "ambiguous":
                metric_result = self._promote_qualifier_metrics(question, source_context, metric_result)
            metric_result = self._tidy_unresolved_resolution(question, metric_result)
            plan = {
                "status": metric_result.get("status", "not_found"),
                "stage": "metric",
                "question": question,
                "source_context": source_context,
                "metric_resolution": metric_result,
            }
            if (
                source_context.get("status") == "resolved"
                and source_context.get("routing_strength") == "strong"
                and self._board_named_explicitly(question, source_context)
            ):
                # Para decir «en el tablero X no encontré...» y no «fuera de alcance».
                plan["named_report"] = source_context.get("report") or source_context.get("semantic_model")
            return plan

        # Tablero nombrado en la pregunta sin ese indicador: no se responde con
        # el de otro tablero (ni se ofrece «consultar sin ...» con él).
        if (
            exploring and metric_result.get("source_hint_ignored")
            and self._board_named_explicitly(question, source_context)
        ):
            return self._named_board_rejection(question, source_context, metric_result)

        metric = metric_result["metric"]
        semantic_model = metric.get("semantic_model")
        reports = metric.get("reports", []) or []
        report = metric.get("report") or (reports[0] if reports else source_context.get("report"))
        dropped_dimensions = []
        candidates = self._metric_dimensions(metric, dropped_dimensions)
        # Periodo («entre enero y marzo», «este año») y agrupación temporal
        # («por mes»): sus palabras no son valores ni dimensiones.
        temporal = self._periods_for_metric(question, metric, metric_result.get("matched_name"))
        dimension_question = temporal["clean_question"]
        # «tablero de triage»: las palabras del tablero nombrado no son
        # agrupaciones ni valores de filtro.
        dimension_question, board_tokens = self._strip_board_mentions(
            dimension_question, source_context,
        )

        group_detection = self._detect_group_or_dimension_filter(
            dimension_question, metric, candidates, source_context=source_context,
        )
        group_by = group_detection["group_by"]
        # Un indicador ya decidido al depurar las opciones (`final`) no se
        # vuelve a cambiar por resolver la pregunta sin la agrupación.
        final = selected_metric_id is not None or bool((forced_resolution or {}).get("final"))
        switched = None if final else self._metric_without_group_phrase(
            question, metric_result, group_by, source_context,
        )
        if switched is not None:
            metric_result = switched
            metric = metric_result["metric"]
            semantic_model = metric.get("semantic_model")
            reports = metric.get("reports", []) or []
            report = metric.get("report") or (reports[0] if reports else source_context.get("report"))
            dropped_dimensions = []
            candidates = self._metric_dimensions(metric, dropped_dimensions)
            temporal = self._periods_for_metric(question, metric, metric_result.get("matched_name"))
            dimension_question, board_tokens = self._strip_board_mentions(
                temporal["clean_question"], source_context,
            )
            group_detection = self._detect_group_or_dimension_filter(
                dimension_question, metric, candidates, source_context=source_context,
            )
            group_by = group_detection["group_by"]
        # Ranking («el servicio con más peso», «top 5 especialidades»): la
        # dimensión nombrada se agrupa y el resultado se ordena/limita.
        ranking = self._detect_ranking(question, candidates, group_by)
        if ranking and not group_by:
            group_by = [ranking["field"]]

        # Nunca convertir silenciosamente "por servicio" en total escalar
        # si la metadata de ese informe no expone SERVICIO.
        requested_group = re.search(
            r"\b(?:por|segun|agrupad[oa] por|desglosad[oa] por)\s+"
            r"(?:el|la|los|las)?\s*"
            r"(servicio|servicios|especialidad|especialidades|asegurador(?:a|as|es)?|eps|sexo|estados?|tipos?)\b",
            normalize_text(question),
        )
        # «por X» que solo nombra columnas de tablas que no filtran el
        # indicador: tampoco se agrupa en silencio por ellas.
        group_tail = self._requested_group_tail(question)
        unrelated_group = self._group_field_in(group_tail, dropped_dimensions) if group_tail else None
        if (requested_group or unrelated_group) and not group_by and not group_detection["explicit_filters"]:
            # Otro indicador del mismo tablero que sí se desglosa por X y trata
            # el tema («detalle de ocupación por aseguradores»).
            if not (forced_resolution or {}).get("group_sibling"):
                sibling = self._group_sibling_plan(question, intent_result, [metric], group_tail, source_context)
                if sibling is not None:
                    return sibling
            # Antes de decir que ESTE indicador no se desglosa, ¿la pregunta
            # nombra otro? («tiempo promedio de TRIAGE por eps» eligió TIEMPO
            # GESTION FACTURACION por «promedio de tiempo»).
            if exploring:
                vocabulary = self._metric_vocabulary_tokens(metric)
                tail_tokens = set(canonical_tokens(group_tail))
                pending = [
                    word for word in self._question_content_words(
                        self._metric_business_question(question, source_context)
                    )
                    if canonical_token(word) not in tail_tokens
                    and not self._explains(canonical_token(word), vocabulary)
                ]
                if pending:
                    switched_plan = self._qualifier_metric_switch(
                        question, intent_result, metric, metric_result, source_context, pending,
                    )
                    if switched_plan is not None:
                        return switched_plan
            if unrelated_group is not None:
                self._note(
                    f"«{group_tail}» solo está en {unrelated_group.get('table')}[{unrelated_group.get('column')}], "
                    f"tabla que no filtra {self._metric_fact_table(metric)}: no se agrupa por ella"
                )
            return {
                "status": "unsupported_filter", "stage": "dimensions",
                "reason": "requested_dimension_not_found_in_report",
                "requested_dimension": requested_group.group(1) if requested_group else group_tail,
                "explanation": self._ungroupable_text([metric], group_tail, question) if group_tail else None,
                "question": question, "semantic_model": semantic_model,
                "source_context": source_context, "metric_resolution": metric_result,
            }

        explicit_specs = list(group_detection["explicit_filters"])
        used_fields = {
            (normalize_text(spec["field"].get("table")), normalize_text(spec["field"].get("column")))
            for spec in explicit_specs
        }
        used_fields.update(
            (normalize_text(field.get("table")), normalize_text(field.get("column")))
            for field in group_by
        )
        explicit_specs.extend(
            self._detect_explicit_dimension_filters(
                # La frase de la agrupación ya está explicada: «por areas de
                # servicio» no es además el filtro SERVICIO = «servicio».
                re.sub(
                    r"(?<![a-z0-9])(?:por|segun|agrupad[oa]s?\s+por|desglosad[oa]s?\s+por)\s+"
                    r"(?:(?:el|la|los|las|cada)\s+)?" + re.escape(group_detection["phrase"]) + r"(?![a-z0-9])",
                    " ", dimension_question,
                ) if group_by and group_detection.get("phrase") else dimension_question,
                candidates, already_fields=used_fields,
                metric=metric, source_context=source_context,
            )
        )

        # Un indicador hermano elegido porque el pedido no se desglosaba por X
        # ya se justificó por el tema de la pregunta (su página).
        if selected_metric_id is None and not (forced_resolution or {}).get("group_sibling"):
            rejection = self._metric_evidence_rejection(
                question, metric, metric_result, group_by, explicit_specs, source_context,
            )
            if rejection is not None:
                return rejection

        filters = []
        unapplied_terms = []
        notes = []
        if (forced_resolution or {}).get("visible_note"):
            notes.append(forced_resolution["visible_note"])
        consumed_tokens = set(temporal["tokens"])
        consumed_tokens.update(board_tokens)
        if group_by:
            # «detalle de X por Y»: «detalle» pide la tabla que ya se arma.
            consumed_tokens.update(self._SHAPE_WORDS)
        # Palabras con que se eligió un indicador ya decidido (página nombrada:
        # «promedio» eligió PROM_PD): no son filtros pendientes.
        consumed_tokens.update((forced_resolution or {}).get("consumed_tokens") or ())
        # «en el hospital», «ocupación general»: todo el hospital, sin filtro
        # (ni exploración de valores ni «No pude aplicar»).
        scope = self._scope_words(dimension_question, metric)
        if scope:
            consumed_tokens.update(canonical_token(word) for word in scope)
            self._note(
                f"«{' '.join(dict.fromkeys(scope))}» se refiere a todo el hospital (sin filtro)"
            )
        # «porcentaje de inasistencia» con %INASISTENCIA: tipo de dato, no filtro.
        measure_words = [
            word for word in self._measure_type_words(dimension_question, metric)
            if canonical_token(word) not in consumed_tokens
        ]
        # «interconsultas pendientes» con INTERCONSULTAS SIN RESPUESTA: el
        # estado pendiente ya es el del indicador.
        if re.search(r"(?<![a-z0-9])pendientes?(?![a-z0-9])", normalize_text(dimension_question)) and (
            self._PENDING_LABEL_RE.search(normalize_text(f"{metric.get('label')} {metric.get('measure') or ''}"))
        ):
            measure_words.append("pendientes")
            consumed_tokens.update({"pendiente", "pendientes"})
        if measure_words:
            consumed_tokens.update(canonical_token(word) for word in measure_words)
            self._note(
                f"«{' '.join(dict.fromkeys(measure_words))}» ya lo dice el indicador "
                f"{metric.get('label')} (tipo de dato o estado): no es un filtro"
            )
        implicit_decisions = []
        if ranking:
            consumed_tokens.update(ranking["tokens"])
            notes.append(self._ranking_note(
                ranking, (ranking["field"].get("aliases") or [ranking["field"]["column"]])[0],
            ))
        if metric_result.get("source_hint_ignored"):
            notes.append(
                "La métrica no existe en el informe mencionado; se usó "
                f"{report or semantic_model}."
            )
        absorbed = self._period_in_metric_note(question, temporal, metric, metric_result)
        if absorbed:
            notes.append(absorbed)
        for spec in explicit_specs:
            field = spec["field"]
            resolved = None
            for option in [field, *spec.get("alternatives", [])]:
                resolved = self._resolve_value(
                    question=question, field=option, semantic_model=semantic_model,
                    value_hint=spec.get("value_hint"), context=spec.get("alias"),
                )
                if resolved:
                    field = option
                    break
            if not resolved and self._names_board(spec.get("value_hint"), source_context, metric):
                # El «valor» no existe en la columna pero es el nombre del
                # tablero/informe («... por servicio del tablero lavanderia»):
                # se consume como tablero; con «por <dimensión>» se agrupa.
                key = (normalize_text(field["table"]), normalize_text(field["column"]))
                if spec.get("from_group") and key not in {
                    (normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in group_by
                }:
                    group_by = [*group_by, field]
                self._note(
                    f"«{spec.get('value_hint')}» no es un valor de {field['table']}[{field['column']}] "
                    "sino el nombre del tablero: se toma como tablero"
                    + (f" y se agrupa por {field['column']}" if spec.get("from_group") else "")
                )
                consumed_tokens.update(canonical_tokens(spec.get("value_hint")))
                if not spec.get("from_group"):
                    used_fields.discard(key)
                continue
            if not resolved:
                return {
                    "status": "unsupported_filter", "stage": "dimension_value",
                    "reason": "requested_value_not_found",
                    "requested_value": spec.get("value_hint"),
                    "dimension": {"table": field["table"], "column": field["column"]},
                    "question": question, "semantic_model": semantic_model,
                    "source_context": source_context, "metric_resolution": metric_result,
                    "domain_error": self.domain_errors.get((semantic_model, field["table"], field["column"])),
                }
            filters.append(self._categorical_filter(
                field, resolved, "query_plan_explicit_dimension", semantic_model,
            ))
            used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))
            consumed_tokens.update(resolved.get("tokens", ()))
            consumed_tokens.update(canonical_tokens(spec.get("value_hint")))
            for alias in field.get("aliases", []) or []:
                consumed_tokens.update(canonical_tokens(alias))

        # Valores implícitos («cirugía plástica»): se buscan SIEMPRE, también
        # cuando ya hay filtros explícitos o agrupación; así ninguna palabra
        # específica se pierde porque otro filtro coincidió primero.
        for _ in range(3):
            implicit = self._resolve_implicit_filter(
                question=question, metric=metric,
                matched_name=metric_result.get("matched_name"),
                source_context=source_context, candidates=candidates,
                group_by=group_by, used_fields=used_fields,
                extra_removals=consumed_tokens, decisions=implicit_decisions,
            )
            if not implicit:
                break
            field = implicit["field"]
            implicit_filter = self._categorical_filter(
                field, implicit, "query_plan_implicit_value", semantic_model,
            )
            if implicit.get("reason"):
                implicit_filter["reason"] = implicit["reason"]
            filters.append(implicit_filter)
            used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))
            consumed_tokens.update(implicit.get("tokens", ()))

        temporal_result = self._apply_temporal(temporal, candidates, semantic_model, group_by, metric=metric)
        requested_period = temporal_result["unsupported_period"]
        if requested_period:
            rejection = {
                "status": "unsupported_filter", "stage": "temporal_filters",
                "reason": "date_dimension_not_found_in_report",
                "requested_year": requested_period.get("year"),
                "requested_month": requested_period.get("month"),
                "requested_period": requested_period.get("label"),
                "unapplied_terms": temporal_result["unapplied"],
                "explanation": temporal_result.get("explanation"),
                "question": question, "semantic_model": semantic_model,
                "source_context": source_context, "metric_resolution": metric_result,
            }
            # Antes de rendirse por el periodo, un calificativo puede nombrar
            # otro indicador que sí tiene fecha («triages pediátricos en 2025»:
            # TRIAGES de BRIEFING no tiene fecha, TRIAGES_PEDIATRICOS_2025 sí).
            if exploring:
                qualifier = self._resolve_qualifiers(
                    question, intent_result, metric, metric_result, source_context, candidates,
                    group_by, used_fields, consumed_tokens, allow_switch=True,
                )
                if qualifier.get("plan") is not None and qualifier["plan"].get("status") == "ready":
                    return qualifier["plan"]
            return rejection
        filters.extend(temporal_result["filters"])
        unapplied_terms.extend(temporal_result["unapplied"])
        notes.extend(temporal_result["notes"])

        # Calificativos que quedaron sin interpretar («triages pediátricos»,
        # «consultas ambulatorias», «de ortopedia de sura»): antes de darlos por
        # no entendidos se prueba (a) otro indicador que los nombre y (b) un
        # valor de dimensión aproximado (plural/género/raíz) del modelo.
        qualifier = self._resolve_qualifiers(
            question, intent_result, metric, metric_result, source_context, candidates,
            group_by, used_fields, consumed_tokens, allow_switch=exploring,
        )
        if qualifier.get("plan") is not None:
            return qualifier["plan"]
        for field, resolved in qualifier.get("filters", []):
            filters.append(self._categorical_filter(
                field, resolved, "query_plan_approximate_value", semantic_model,
            ))
            used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))
            consumed_tokens.update(resolved.get("tokens", ()))
            consumed_tokens.update(canonical_tokens(resolved.get("phrase")))
        consumed_tokens.update(qualifier.get("consumed", ()))
        # Con esas palabras ya explicadas, lo que queda puede ser por sí solo un
        # valor («camas ocupadas en uci»: tras ESTADOS_CAM = OCUPADA, «uci» es
        # SERVICIOS = UCI ADULTOS; antes «ocupadas uci» no coincidía con nada).
        if qualifier.get("filters"):
            for _ in range(2):
                implicit = self._resolve_implicit_filter(
                    question=question, metric=metric,
                    matched_name=metric_result.get("matched_name"),
                    source_context=source_context, candidates=candidates,
                    group_by=group_by, used_fields=used_fields,
                    extra_removals=consumed_tokens, decisions=implicit_decisions,
                )
                if not implicit:
                    break
                field = implicit["field"]
                implicit_filter = self._categorical_filter(
                    field, implicit, "query_plan_implicit_value", semantic_model,
                )
                if implicit.get("reason"):
                    implicit_filter["reason"] = implicit["reason"]
                filters.append(implicit_filter)
                used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))
                consumed_tokens.update(implicit.get("tokens", ()))

        # El mismo indicador (mismo nombre) en otro tablero/modelo y nada en la
        # pregunta que los distinga: se contrapregunta en lugar de elegir uno.
        # Va después de los calificativos: «triages pediátricos» ya eligió
        # TRIAGES_PEDIATRICOS_2025 y no debe preguntar entre los TRIAGES.
        if exploring:
            same_name = self._same_name_ambiguity(question, source_context, metric_result)
            if same_name is not None:
                return same_name

        # Palabras específicas que ningún filtro explicó. Sin ningún filtro
        # categórico el resultado sería un total engañoso: se detiene. Con
        # otros filtros ya aplicados se continúa, pero se declara lo omitido.
        # Con un indicador elegido por el usuario (botón) no se vuelve a
        # preguntar, pero lo que no se pudo aplicar se declara: «ortopedia» no
        # desaparece en silencio si el indicador elegido no tiene especialidad.
        leftover = self._implicit_value_text(
            question, metric, metric_result.get("matched_name"),
            source_context, group_by, extra_removals=consumed_tokens,
        )
        significant = [token for token in leftover.split() if len(token) >= 3]
        if significant and exploring:
            # Si lo no interpretado es el núcleo de la pregunta (el sustantivo
            # principal) o pesa más que lo que coincidió con el indicador, no
            # se ofrece «consultarlo sin ...»: se sugieren otros indicadores.
            outweighed = self._unresolved_outweighs_metric(
                question, metric, metric_result, significant, source_context,
            )
            if outweighed is not None:
                return outweighed
        if significant:
            if selected_metric_id is None and not any(
                item.get("type") == "categorical" and item.get("source") != "query_plan_temporal"
                for item in filters
            ) and not group_by:
                # Otro candidato cercano sí entiende esas palabras como filtros
                # («camas ocupadas en uci»: CAMAS de la tabla CAMAS DISPONIBLES
                # tiene ESTADOS_CAM = OCUPADA y SERVICIOS = UCI ADULTOS).
                if exploring:
                    alternative = self._candidate_that_filters(
                        question, intent_result, metric, metric_result, significant,
                    )
                    if alternative is not None:
                        return alternative
                return {
                    "status": "unsupported_filter", "stage": "implicit_dimension",
                    "reason": "possible_dimension_value_not_resolved",
                    "unresolved_text": leftover,
                    "implicit_decisions": implicit_decisions,
                    "question": question, "semantic_model": semantic_model,
                    "source_context": source_context, "metric_resolution": metric_result,
                }
            unapplied_terms.append(" ".join(significant))

        # Nunca se agrupa por una columna de una tabla que no filtra el
        # indicador (repetiría el total en cada fila).
        normalized_group_by = [{
            "table": field["table"],
            "column": field["column"],
            "label": self._group_label(field),
            "source": "query_plan_group_by",
        } for field in group_by if self._dimension_relation(metric, field) != "unrelated"]
        if temporal_result["group"]:
            normalized_group_by = [temporal_result["group"]]

        if not normalized_group_by:
            metric = self._scalar_representative(metric)
        pages = self._metric_pages(metric)
        return {
            "status": "ready",
            "intent": "numeric_query",
            "mode": "grouped" if normalized_group_by else "scalar",
            "question": question,
            "source_context": source_context,
            "semantic_model": semantic_model,
            "report": report,
            "dashboard": metric.get("dashboard") or (pages[0] if pages else None),
            "metric": metric,
            "metric_match": {
                "matched_name": metric_result.get("matched_name"),
                "score": metric_result.get("score"),
                "interpretation": metric_result.get("interpretation"),
            },
            "filters": filters,
            "unapplied_terms": unapplied_terms,
            "notes": notes,
            "implicit_decisions": implicit_decisions,
            "technical_columns_used": self._technical_columns_used(candidates, filters, group_by),
            "board_mentions": [
                mention.get("phrase") for mention in source_context.get("board_mentions") or []
            ],
            "group_by": normalized_group_by,
            "ranking": (
                {key: ranking[key] for key in ("direction", "limit", "phrase")}
                if ranking and normalized_group_by else None
            ),
            "temporal_buckets": temporal_result["buckets"],
            # Estado actual: la respuesta no se presenta como «en lo que va de ...».
            "period": None if temporal_result.get("current_state") else self._period_summary(temporal),
            "dimension_candidates_checked": min(len(candidates), 20),
        }

    _FILTER_SWITCH_CANDIDATES = 3
    _FILTER_SWITCH_SCORE_GAP = 0.35

    def _candidate_that_filters(self, question, intent_result, metric, metric_result, unresolved):
        """El indicador elegido no entiende palabras de la pregunta como filtro
        («uci» con CAMAS OCUPADAS de GESTIÓN CAMAS). Si exactamente uno de los
        siguientes candidatos (por puntaje, a poca distancia) arma la consulta
        con filtros y sin palabras pendientes, se usa ese. None si no."""
        best_score = float(metric_result.get("score") or 0.0)
        current = self._logical_key(metric)
        tried, ready = 0, []
        for item in metric_result.get("candidates") or []:
            other = item.get("metric") or {}
            if self._logical_key(other) == current or not other.get("metric_id"):
                continue
            if float(item.get("business_score") or 0.0) < self.min_metric_score:
                continue
            if best_score - float(item.get("score") or 0.0) > self._FILTER_SWITCH_SCORE_GAP:
                continue
            tried += 1
            if tried > self._FILTER_SWITCH_CANDIDATES:
                break
            forced = {
                "status": "resolved", "metric": other,
                "matched_name": item.get("matched_name"), "score": item.get("score"),
                "candidates": [{key: value for key, value in item.items() if not key.startswith("_")}],
                "final": True,
            }
            notes = list(self.__dict__.get("_resolution_notes") or [])
            attempt_notes = []
            previous_exempt = self.__dict__.get("_sibling_exempt")
            self._sibling_exempt = {current}
            try:
                plan = self._build_plan(question, intent_result, forced_resolution=forced)
            except Exception:
                plan = None
            finally:
                self._sibling_exempt = previous_exempt
                if self.__dict__.get("_resolution_notes") is not None:
                    attempt_notes = self._resolution_notes[len(notes):]
                    self._resolution_notes[:] = notes
            if isinstance(plan, dict):
                plan["_attempt_notes"] = attempt_notes
            categorical = [
                entry for entry in (plan.get("filters") or [] if isinstance(plan, dict) else [])
                if entry.get("type") == "categorical" and not entry.get("temporal")
                and entry.get("source") != "query_plan_temporal"
            ]
            # Las palabras que el elegido no entendía deben ser valores de los
            # filtros del otro (no basta con que arme la consulta).
            value_tokens = {
                token for entry in categorical
                for value in [entry.get("value"), *(entry.get("values") or [])] if value is not None
                for token in canonical_tokens(value)
            }
            if (
                isinstance(plan, dict) and plan.get("status") == "ready" and not plan.get("unapplied_terms")
                and categorical
                and all(
                    any(_tokens_match_loosely(canonical_token(word), token) for token in value_tokens)
                    for word in unresolved
                )
            ):
                ready.append((item, plan))
        if len(ready) != 1:
            return None
        item, plan = ready[0]
        for note in plan.pop("_attempt_notes", None) or []:
            self._note(note)
        interpretation = (
            f"{metric.get('label')} no entiende «{' '.join(unresolved)}» como filtro; "
            f"{item['metric'].get('label')} ({item['metric'].get('semantic_model')}) sí: se usa"
        )
        self._note(interpretation)
        plan.setdefault("metric_match", {})["interpretation"] = interpretation
        return plan

    def _period_summary(self, temporal):
        """Periodo interpretado (para el razonamiento y la respuesta), o None."""
        period, granularity = temporal.get("period"), temporal.get("granularity")
        if not period and not granularity:
            return None
        summary = {"today": self._today().isoformat()}
        question = temporal.get("question") or ""
        if period:
            summary.update({
                "phrase": _original_phrase(question, period.get("phrase")),
                "label": period.get("label"),
                "kind": period.get("kind"), "relative": period.get("relative"),
                "start": as_date(period.get("start")).isoformat() if period.get("start") else None,
                "end": as_date(period.get("end")).isoformat() if period.get("end") else None,
                "months": period.get("months"),
            })
        if granularity:
            summary["granularity"] = granularity.get("unit")
            summary["granularity_phrase"] = _original_phrase(question, granularity.get("phrase"))
        return summary

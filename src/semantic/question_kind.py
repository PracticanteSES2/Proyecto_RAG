"""
Clasificación ligera de preguntas: ¿piden un VALOR o una EXPLICACIÓN?

«¿Cómo se calcula el porcentaje de ocupación de camas?», «¿cuáles son los rangos
del NEDOCS?» o «¿para qué sirve el tablero de farmacia?» piden documentación,
aunque contengan palabras numéricas («porcentaje», «total», «cuántos» en otra
parte de la frase). Las usan el Query Plan (`looks_numeric`), el IntentParser y
el QueryEngine para enviarlas al RAG documental en vez de a Power BI.

«¿Cuál es el porcentaje de ocupación de camas en marzo?» sigue siendo numérica:
ninguna de estas frases aparece en ella.
"""
import re
import unicodedata


def normalize_question(value):
    value = str(value or "").lower().strip()
    value = "".join(
        char for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    value = re.sub(r"[^a-z0-9%]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


# Fórmula / método: valen en cualquier parte de la pregunta.
_METHOD = (
    r"como\s+(?:se\s+|lo\s+|la\s+|los\s+|las\s+)?(?:calcula|calculan|calcular|calculo|calculamos"
    r"|obtiene|obtienen|obtener|determina|determinan|construye|construyen|define|definen"
    r"|mide|miden|medir|interpreta|interpretan|interpretar|lee|leen|leer|clasifica|clasifican"
    r"|sacan|saca|halla|hallan|computa|computan)",
    r"como\s+es\s+(?:el|la)\s+(?:calculo|formula|metodologia|definicion)",
    r"(?:cual|cuales)\s+es\s+(?:la|su)\s+(?:formula|definicion|metodologia)",
    r"(?:la|su)\s+formula\s+(?:de|del|para)",
    r"que\s+formula",
    r"(?:que|cual)\s+es\s+la\s+logica",
)

# Significado / propósito / origen: valen en cualquier parte.
_MEANING = (
    r"que\s+(?:significa|significan|quiere\s+decir|quieren\s+decir)",
    r"que\s+(?:mide|miden|indica|indican)\s+(?:el|la|los|las|este|esta|ese|esa)",
    r"para\s+que\s+(?:sirve|sirven|se\s+usa|se\s+usan|se\s+utiliza|se\s+utilizan)",
    r"de\s+donde\s+(?:sale|salen|se\s+obtiene|se\s+obtienen|viene|vienen|proviene|provienen"
    r"|se\s+toma|se\s+toman|toma|toman|se\s+saca|se\s+sacan)",
    r"(?:cual|que)\s+es\s+(?:la\s+)?fuente\s+de",
)

# Rangos / colores / criterios / semáforo: con artículo («los rangos del NEDOCS»).
# «por rangos de edad» es una agrupación, no una pregunta descriptiva: se exige
# el artículo plural y que no vaya precedido de «por» / «según».
_LEGEND_NOUNS = (
    r"rangos|colores|criterios|umbrales|convenciones|semaforos|semaforizacion"
    r"|categorias\s+de\s+clasificacion|puntos\s+de\s+corte|niveles\s+de\s+alerta"
)
_LEGEND = (
    r"(?<!por )(?<!segun )(?:los|las)\s+(?:" + _LEGEND_NOUNS + r")\s+(?:de|del|para|en)",
    r"(?:el|del|al)\s+semaforo\s+(?:de|del|en|para)",
    r"(?:que|cuales|como)\s+(?:son\s+|significan\s+|funcionan\s+)?(?:los|las|el|la)\s+"
    r"(?:" + _LEGEND_NOUNS + r"|semaforo)",
)

# Filtros / contenido del tablero.
_CONTENT = (
    r"(?:que|cuales)\s+(?:son\s+(?:los|las)\s+)?(?:filtros|segmentadores|segmentaciones|slicers)",
    r"con\s+que\s+(?:filtros|segmentadores)",
    r"que\s+(?:informacion|indicadores|graficos|visuales|paginas)\s+"
    r"(?:tiene|muestra|muestran|contiene|maneja|presenta)",
)

# Inicios de pregunta que, al COMIENZO, piden una explicación («¿qué es el
# NEDOCS?», «¿qué son las interconsultas?»). En medio de la frase («las que
# son programadas») no cuentan.
_LEADING = (
    r"que\s+(?:es|son)\s+(?:el|la|los|las|un|una|este|esta|ese|esa)?",
    r"(?:explica|explicame|explicanos|describe|describeme|define|defineme)",
    r"en\s+que\s+consiste",
)
_LEADING_FILLER = (
    r"(?:(?:y|oye|hola|bueno|entonces|disculpa|perdon|por\s+favor|porfa|sabes|me\s+puedes\s+decir"
    r"|me\s+podrias\s+decir|me\s+dices|dime|quisiera\s+saber|quiero\s+saber|necesito\s+saber"
    r"|podrias\s+decirme|puedes\s+decirme|una\s+pregunta)\s+)*"
)

# Cuantificadores al comienzo: «cuántos pacientes hay en los rangos de ...»
# pregunta por un número aunque nombre rangos o colores.
_QUANTITY_START = re.compile(
    r"^" + _LEADING_FILLER + r"(?:cuant[oa]s?|cantidad|numero|total|cuanto\s+es|cuanta)(?![a-z0-9])"
)


def _search(patterns, text):
    for pattern in patterns:
        match = re.search(r"(?<![a-z0-9])(?:" + pattern + r")(?![a-z0-9])", text)
        if match:
            return match.group(0).strip()
    return None


def descriptive_phrase(question):
    """Frase (normalizada) que vuelve descriptiva la pregunta, o None.

    Ejemplos: «como se calcula», «que significan», «los rangos del»,
    «para que sirve», «de donde sale», «que filtros», «que es el».
    """
    text = normalize_question(question)
    if not text:
        return None
    for patterns in (_METHOD, _MEANING, _CONTENT):
        found = _search(patterns, text)
        if found:
            return found
    leading = re.match(
        r"^" + _LEADING_FILLER + r"(?:" + "|".join(_LEADING) + r")(?![a-z0-9])", text,
    )
    if leading:
        return leading.group(0).strip()
    if _QUANTITY_START.match(text):
        return None
    return _search(_LEGEND, text)


def is_descriptive_question(question):
    return descriptive_phrase(question) is not None

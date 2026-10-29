"""
Frases de la pedida que no son parte del dato.

- Relleno de petición: «se me ha solicitado saber», «me piden», «necesito
  reportar», «nos pidieron averiguar». Dicen quién pide o para qué, no qué
  indicador ni qué filtro. Se quitan antes de resolver la pregunta.
- Agrupaciones dichas con «cada» o «desglose»: «cada una de las
  especialidades», «de cada especialidad», «por cada servicio», «desglose por
  sede», «discriminado por aseguradora», «según especialidad». Equivalen a
  «por <dimensión>» y se mueven al final de la pregunta, donde el Query Plan
  reconoce la agrupación.

Las reescrituras conservan mayúsculas y tildes del texto original (se buscan
sobre una copia «plegada» de la misma longitud) y devuelven notas para el
razonamiento del turno.
"""
import re
import unicodedata

# Dimensiones habituales (singular). El llamador puede pasar su propio
# reconocedor (p. ej. los alias de las dimensiones del catálogo).
DEFAULT_DIMENSIONS = {
    "especialidad", "servicio", "sede", "aseguradora", "eps", "area", "unidad",
    "turno", "colaborador", "medico", "cirujano", "profesional", "piso", "cama",
    "tipo", "estado", "causa", "modalidad", "sexo", "genero", "clasificacion",
    "triage", "mes", "ano", "trimestre", "semana", "dia", "diagnostico",
    "procedimiento", "pagador", "convenio", "municipio", "departamento",
}

_VERBS = (
    r"saber|conocer|consultar|reportar|informar|averiguar|revisar|entregar|"
    r"enviar|calcular|sacar|presentar|tener"
)
_FILLER_PATTERNS = (
    # «se me ha solicitado saber», «nos han pedido reportar», «me fue solicitado»
    r"(?:a\s+(?:mi|nosotros)\s+)?(?:se\s+)?(?:me|nos|le|les)\s+"
    r"(?:ha|han|habia|habian|hubiera|fue|fueron)\s+(?:solicitad[oa]s?|pedid[oa]s?|requerid[oa]s?|encargad[oa]s?)"
    r"(?:\s+(?:que\s+)?(?:" + _VERBS + r"))?",
    # «me piden», «nos pidieron averiguar», «me solicitan»
    r"(?:se\s+)?(?:me|nos)\s+(?:piden|pidieron|pide|pidio|solicitan|solicitaron|solicita|solicito|"
    r"requieren|requirieron|encargaron|encargan)(?:\s+(?:que\s+)?(?:" + _VERBS + r"))?",
    # «necesito reportar», «debo informar» (con «saber/conocer/consultar» ya
    # son palabras vacías del Query Plan y no hace falta tocarlas).
    r"(?:necesito|necesitamos|requiero|requerimos|debo|debemos|tengo\s+que|tenemos\s+que|"
    r"quisiera|quisieramos|quiero|queremos|me\s+gustaria|nos\s+gustaria)\s+"
    r"(?:reportar|informar|averiguar|entregar|enviar|sacar|presentar|revisar)",
)
_FILLER_RE = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(_FILLER_PATTERNS) + r")(?![a-z0-9])"
)
# «De urgencias se me ha solicitado...»: lo que va antes del relleno puede
# ser quien pide el dato.
_REQUESTER_RE = re.compile(r"^\s*(?:de|desde|del)\s+(?:la\s+|el\s+)?(?P<who>[a-z0-9 ]{3,40}?)\s*,?\s*$")

_DIM = r"(?P<dim>[a-z]{2,}(?:\s+(?:de\s+)?[a-z]{3,})?)"
_CADA_RE = re.compile(
    r"(?<![a-z0-9])"
    r"(?:(?:que\s+)?(?:tiene|tienen|tuvo|tuvieron|hay|hubo|habia|corresponde|corresponden|son|fueron|"
    r"pertenecen|pertenece|atendio|atendieron|registra|registran|lleva|llevan)\s+)?"
    r"(?:(?:a|de|en|para|por|segun)\s+)?"
    r"cada\s+(?:un[oa]\s+de\s+(?:l[oa]s\s+|sus\s+)?|un[oa]\s+)?" + _DIM
)
_BREAKDOWN_RE = re.compile(
    r"(?<![a-z0-9])"
    r"(?:(?:con\s+)?(?:el\s+|un\s+|su\s+)?desglose|desglosad[oa]s?|desglosar(?:l[oa]s?)?|desglosa(?:l[oa]s?)?|"
    r"desglosame(?:l[oa]s?)?|discriminad[oa]s?|discriminar(?:l[oa]s?)?|discrimina(?:l[oa]s?)?|"
    r"separad[oa]s?|separar(?:l[oa]s?)?|separa(?:l[oa]s?)?|agrupad[oa]s?|agrupar(?:l[oa]s?)?|"
    r"agrupa(?:l[oa]s?)?|clasificad[oa]s?|distribuid[oa]s?)"
    r"\s+(?:por|segun|de\s+acuerdo\s+(?:a|con))\s+(?:(?:cada|el|la|los|las|su|sus)\s+)?" + _DIM
)
_SEGUN_RE = re.compile(r"(?<![a-z0-9])segun\s+(?:(?:el|la|los|las|su|sus)\s+)?" + _DIM)
# «y su respectiva especialidad», «con sus respectivos servicios», «y su
# especialidad»: el dato de cada fila junto a su dimensión = «por <dimensión>».
_RESPECTIVE_RE = re.compile(
    r"(?<![a-z0-9])(?:(?:y|con|junto\s+con|ademas\s+de)\s+(?:(?:el|la|los|las)\s+)?(?:su|sus)\s+"
    r"(?:respectiv[oa]s?\s+|correspondientes?\s+)?"
    r"|(?:su|sus)\s+(?:respectiv[oa]s?|correspondientes?)\s+)" + _DIM
)
# «... que tiene cada una», «por cada uno», «de cada una» SIN nombrar la
# dimensión: se refiere a la dimensión plural nombrada antes en la pregunta
# («cuántas especialidades ... y los pacientes que tiene cada una»).
_ANAPHORIC_CADA_RE = re.compile(
    r"(?<![a-z0-9])"
    r"(?:(?:que\s+)?(?:tiene|tienen|tuvo|tuvieron|hay|hubo|habia|corresponde|corresponden|lleva|llevan|"
    r"registra|registran|atiende|atienden|maneja|manejan)\s+)?"
    r"(?:(?:a|de|en|para|por|segun)\s+)?"
    r"(?:en\s+)?cada\s+(?P<pron>un[oa])(?![a-z0-9])(?!\s+de\s)"
)
_ANTECEDENT_DETERMINERS = {
    "cuantas", "cuantos", "tantas", "tantos", "las", "los", "sus", "varias", "varios", "diferentes",
    "distintas", "distintos", "todas", "todos", "estas", "estos", "esas", "esos", "algunas", "algunos",
}
_FEMININE_END = re.compile(r"(?:a|as|dad|dades|cion|ciones|sion|siones|tud|tudes|ez)$")
_MASCULINE_END = re.compile(r"(?:o|os|or|ores|al|ales|el|eles)$")


def _gender(word):
    word = singular(word)
    if _FEMININE_END.search(word):
        return "f"
    if _MASCULINE_END.search(word):
        return "m"
    return None


def fold(text):
    """Copia de `text` de la MISMA longitud: minúsculas, sin tildes y con
    espacios en lugar de signos (las posiciones coinciden con el original)."""
    out = []
    for char in str(text or ""):
        base = "".join(
            c for c in unicodedata.normalize("NFD", char.lower())
            if unicodedata.category(c) != "Mn"
        )
        base = base[:1] if base else " "
        out.append(base if re.fullmatch(r"[a-z0-9]", base) else " ")
    return "".join(out)


def singular(word):
    """Singular sencillo del español («especialidades» -> «especialidad»)."""
    word = str(word or "")
    if len(word) > 4 and word.endswith("es") and word[-3] in "dlnrjzs":
        stem = word[:-2]
        return stem[:-1] + "c" if stem.endswith("z") else stem
    if len(word) > 3 and word.endswith("s") and not word.endswith("is"):
        return word[:-1]
    return word


def _default_dimension(text):
    words = str(text or "").split()
    if len(words) != 1:
        return None
    word = singular(words[0])
    return word if word in DEFAULT_DIMENSIONS else None


def _dimension_span(match, recognizer):
    """(inicio, fin, nombre) de la dimensión nombrada en el grupo «dim»: se
    prueba el texto completo (dos palabras) y luego solo la primera palabra."""
    start, end = match.span("dim")
    text = match.group("dim")
    words = text.split()
    attempts = [(text, end)]
    if len(words) > 1:
        attempts.append((words[0], start + len(words[0])))
    for candidate, stop in attempts:
        name = recognizer(candidate)
        if name:
            return start, stop, name
    return None


def _cleanup(text):
    text = re.sub(r"\s+([,;?.!])", r"\1", text)
    text = re.sub(r"([,;])\s*([,;?.!])", r"\2", text)
    text = re.sub(r"^\s*[,;]\s*", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _append_grouping(text, name):
    """Agrega « por <dimensión>» al final, antes de los signos finales."""
    match = re.search(r"[\s?¿.!]*$", text)
    tail = match.group(0).strip() if match else ""
    body = text[: match.start()] if match else text
    if fold(body).rstrip().endswith(" por " + name):
        return text
    return f"{body.rstrip(' ,;')} por {name}{tail}"


def requester(text):
    """«De urgencias se me ha solicitado...» -> {"phrase": "De urgencias",
    "who": "urgencias"}: lo que va antes del relleno de petición, que puede ser
    quien pide el dato (o un filtro). None si no hay relleno o nada antes."""
    original = str(text or "")
    folded = fold(original)
    match = _FILLER_RE.search(folded)
    if not match:
        return None
    before = _REQUESTER_RE.match(folded[: match.start()])
    if not before:
        return None
    return {
        "phrase": original[: match.start()].strip(" ,"),
        "who": original[before.start("who"): before.end("who")].strip(),
    }


def without_requester(text, phrase):
    """Quita `phrase` («De urgencias») del inicio de `text` (ya reescrito)."""
    text = str(text or "")
    folded_phrase = fold(phrase).strip()
    folded = fold(text)
    if not folded_phrase or not folded.lstrip().startswith(folded_phrase):
        return text
    start = len(folded) - len(folded.lstrip())
    rest = text[start + len(folded_phrase):]
    return _cleanup(rest.lstrip(" ,"))


def _anaphoric_grouping(text, recognizer):
    """(texto, nota) para «que tiene cada una» / «por cada uno» sin dimensión:
    el antecedente es el sustantivo plural más cercano ANTES de la frase que
    sea una dimensión y concuerde en género con «uno/una» («cuántas
    especialidades ... los pacientes que tiene cada una» -> por especialidad).
    Nunca es un valor de filtro. None si no hay antecedente claro."""
    folded = fold(text)
    for match in _ANAPHORIC_CADA_RE.finditer(folded):
        gender = "f" if match.group("pron") == "una" else "m"
        before = list(re.finditer(r"[a-z]+", folded[: match.start()]))
        found = []
        for position in range(len(before) - 1, -1, -1):
            word = before[position].group(0)
            if len(word) < 3 or not word.endswith("s") or _gender(word) != gender:
                continue
            name = recognizer(word)
            if name:
                previous = before[position - 1].group(0) if position else ""
                found.append((previous in _ANTECEDENT_DETERMINERS, name))
        # Primero el sustantivo introducido por un cuantificador o artículo
        # («qué tantas especialidades»), no el que va tras una preposición
        # («en el área de urgencias»); entre ellos, el más cercano.
        name = next((n for introduced, n in found if introduced), None) or (found[0][1] if found else None)
        if not name:
            continue
        phrase = text[match.start(): match.end()].strip()
        rewritten = _append_grouping(_cleanup(text[: match.start()] + " " + text[match.end():]), name)
        return rewritten, (
            f"«{phrase}» se refiere a la dimensión nombrada antes ({name}): se agrupa por {name} "
            "(no es un valor de filtro)"
        )
    return None


def rewrite_request(text, dimension=None):
    """(texto, notas). `dimension(texto) -> nombre o None` reconoce una
    dimensión (singular o plural); sin él se usa una lista de dimensiones
    habituales. Si nada cambia, devuelve el texto original y [] ."""
    original = str(text or "")
    recognizer = dimension or _default_dimension
    current = original
    notes = []

    # 1) Relleno de petición.
    folded = fold(current)
    fillers = list(_FILLER_RE.finditer(folded))
    if fillers:
        first = fillers[0]
        before = _REQUESTER_RE.match(folded[: first.start()])
        pieces = []
        for match in fillers:
            pieces.append(current[match.start(): match.end()].strip())
        for match in reversed(fillers):
            current = current[: match.start()] + " " + current[match.end():]
        notes.append(
            "«" + "», «".join(pieces) + "» es la forma de pedir el dato (quién lo pide o para qué): "
            "no es un indicador ni un filtro; se ignora"
        )
        if before:
            who = original[before.start("who"): before.end("who")].strip()
            notes.append(
                f"«{original[: first.start()].strip(' ,')}» va antes de la petición: puede ser quien "
                f"solicita el dato; se conserva por si es un filtro («{who}» como servicio o área) "
                "y la respuesta muestra si se aplicó"
            )

    # 2) Agrupación con «cada», «desglose por», «discriminado por», «según».
    grouped = False
    for pattern in (_CADA_RE, _BREAKDOWN_RE, _SEGUN_RE, _RESPECTIVE_RE):
        folded = fold(current)
        for match in pattern.finditer(folded):
            span = _dimension_span(match, recognizer)
            if span is None:
                continue
            _, stop, name = span
            phrase = current[match.start(): stop].strip()
            # «según especialidad» ya al final de la pregunta: el Query Plan lo
            # reconoce tal cual.
            if pattern is _SEGUN_RE and not folded[stop:].strip():
                break
            current = current[: match.start()] + " " + current[stop:]
            current = _append_grouping(_cleanup(current), name)
            notes.append(f"«{phrase}» pide el desglose por {name}: se agrupa por {name}")
            grouped = True
            break
        else:
            continue
        break

    # 3) «... que tiene cada una»: la dimensión es la nombrada antes.
    if not grouped:
        anaphoric = _anaphoric_grouping(current, recognizer)
        if anaphoric is not None:
            current, note = anaphoric
            notes.append(note)

    if not notes:
        return original, []
    return _cleanup(current), notes

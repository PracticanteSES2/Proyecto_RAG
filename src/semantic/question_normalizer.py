"""
Normalización del lenguaje de chat de la pregunta (un solo paso, al entrar).

Los usuarios escriben como en un chat: «camas x estado», «q antibióticos se
usan», «tiempo pa egreso», «kilos d ropa», «cirujias», «holaaa», «??». Antes
cada componente (normalize_text, _GROUP_TAIL_RE, looks_numeric, period_parser)
lo resolvía a su manera o no lo resolvía. Aquí se resuelve UNA vez, en
`QueryEngine.process`, y el resto del sistema recibe el texto normalizado
(la traza guarda el original y el normalizado).

Reglas (todas generales, ninguna por frase):

1. Signos y espacios: espacios repetidos, signos repetidos («??», «!!!»),
   espacio antes de la coma o del signo de cierre, espacio tras la coma.
2. Repeticiones de letras («holaaa», «cuantoooos»): tres o más iguales se
   reducen a una (o a dos si así la palabra existe: «leeer» -> «leer»).
   No toca números romanos en mayúsculas («III»).
3. Abreviaturas de chat, solo como palabra suelta: x -> por (salvo
   multiplicación: un número al lado, «3 x 4»), q/k/qe -> que, pa/pa' -> para,
   d -> de (no tras un número), xq/xk/pq/porq -> porque, tb/tmb -> también,
   cant -> cantidad, prom -> promedio.
4. Errores de tipeo SOLO contra el vocabulario del catálogo real (nombres de
   medidas, columnas, valores documentados, páginas, títulos de visual y
   tableros de data/catalog, data/model_metadata y docs_tableros/*/md, con las
   entradas de `_diccionario*.md`). Distancia de edición acotada (las
   confusiones fonéticas del español s/c/z, j/g, b/v, y/ll, i/y y la h muda
   pesan la mitad): <= 1 en palabras de 5 a 7 letras, <= 2 desde 8. Solo se
   corrige si hay UN candidato claramente mejor, la palabra no existe ya en el
   vocabulario (ni su singular / su otro género) ni en la prosa de la
   documentación, y empieza igual (o con una letra fonéticamente
   equivalente). Nunca toca números, fechas, códigos con dígitos, palabras en
   mayúsculas ni nombres propios (mayúscula inicial a mitad de frase), y nunca
   inventa palabras: el resultado siempre es una palabra del catálogo.

Uso:
    result = normalize_question("valor estimado x area de servicio", vocabulary_for(root))
    result.text      # "valor estimado por area de servicio"
    result.changes   # [{"kind": "abreviatura", "from": "x", "to": "por"}]
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


_FAST_FOLD = str.maketrans("áéíóúüñàèìòùâêîôû", "aeiouunaeiouaeiou")


def fold(text):
    """Minúsculas y sin tildes (la ñ pasa a n, como en normalize_text)."""
    text = str(text or "").lower()
    if text.isascii():
        return text
    text = text.translate(_FAST_FOLD)
    if text.isascii():
        return text
    text = unicodedata.normalize("NFD", text)
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


# ---------------------------------------------------------------- abreviaturas
# Solo palabras sueltas (token completo). Las que dependen de sus vecinos
# (x, d, k) se deciden en `_abbreviation`.
ABBREVIATIONS = {
    "x": "por",
    "q": "que", "k": "que", "qe": "que", "ke": "que",
    "pa": "para",
    "d": "de",
    "xq": "porque", "xk": "porque", "pq": "porque", "porq": "porque", "pk": "porque",
    "tb": "también", "tmb": "también", "tbn": "también", "tambn": "también",
    "cant": "cantidad",
    "prom": "promedio",
}
# «rayos x»: la x es parte del nombre, no «por».
_X_KEEP_AFTER = {"rayos", "rayo", "generacion", "tipo"}

# Palabras frecuentes de una pregunta que no están en la documentación y que
# no deben «corregirse» hacia un término del catálogo.
COMMON_WORDS = set("""
a al algo alguien algun alguna algunas alguno algunos ahi ahora ahorita aja alla alli aqui aca asi aun aunque
bien bueno buena buenas buenos buen cada casi como cual cuales cualquier cuando cuanto cuanta cuantos cuantas
con contra cosa cosas cual de del desde donde dos el ella ellas ellos en entre era eran es esa esas ese eso esos
esta estaba estaban estamos estan estar estas este esto estos estoy fue fueron gracias ha habia han hasta hay
hola hoy igual la las le les lo los mas me mejor menos mi mis mucho mucha muchos muchas muy nada ni no nos nosotros
o oye para pero poco pocos poder por porque pues que quien quienes se segun ser si siempre sin sobre solo son su
sus tal tambien tan tanto te tenemos tener tengo tiene tienen todo toda todos todas tu tus un una unas uno unos
usted ustedes va van vamos ver vez y ya yo
dame deme dime digame diga dimelo muestrame mostrar muestra quiero quisiera necesito necesitamos puedes podrias
porfa favor ayudas ayuda ayudame saber cuentame regalame pasame
llevamos lleva llevan llevaban tuvimos tuvo tuvieron hubo hubieron habra hicieron hizo hacen hace hacemos
paso pasa pasan pasaron suben sube subieron bajan baja bajaron quedan queda quedaron quedo salen sale salieron
entran entra entraron llegan llega llegaron llego van vienen viene vino estuvo estuvieron fueron sera seran
usando usan usa usaron usado usados dando dan dio dieron tenido tenia tenian hemos habido sido estado
repartidas repartidos repartido repartida distribuidas distribuidos comparado comparada comparados comparadas
versus contra frente cual cuales mes meses semana semanas dia dias ano anos anio anios hora horas minuto minutos
enero febrero marzo abril mayo junio julio agosto septiembre setiembre octubre noviembre diciembre
lunes martes miercoles jueves viernes sabado domingo ayer anteayer antier manana tarde noche
primero primera segundo segunda tercero tercera ultimo ultima ultimos ultimas pasado pasada anterior proximo
proxima siguiente actual actuales corriente vigente
total totales cantidad numero porcentaje promedio media mediana maximo minimo suma valor valores cifra cifras
top ranking mayor mayores menor menores alto alta altos altas bajo baja bajos bajas
ok okey vale listo bueno dale chao jefe jefa mensaje cumpleanos feliz dolar
""".split())

# Pares de letras que en español se confunden por sonido: pesan la mitad.
_PHONETIC = {
    frozenset("sc"), frozenset("sz"), frozenset("cz"), frozenset("jg"), frozenset("bv"),
    frozenset("iy"), frozenset("kc"), frozenset("kq"),
}
_FIRST_EQUIV = [set("csz"), set("kcq"), set("bv"), set("gj"), set("iy")]

_WORD_SPLIT_RE = re.compile(r"[a-z]+")
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_MD_ENTRY_RE = re.compile(r"^\s*-\s+\*\*(?P<key>[^*]+)\*\*\s*:")
_MD_FRONT_RE = re.compile(r"^(?:tablero|pagina|nombre_funcional|bloque|tablas)\s*:\s*(?P<value>.+)$", re.MULTILINE)
_MD_HEADING_RE = re.compile(r"^#{1,4}\s+(?P<title>.+)$", re.MULTILINE)
# Claves de los catálogos cuyos textos son NOMBRES (destinos de corrección).
_NAME_KEYS = {
    "Name", "name", "Table", "table", "column", "measure", "metric", "metric_name",
    "visual_title", "title", "page_display_name", "page_name_display", "report", "reports",
    "semantic_model", "native_query_ref", "aliases", "alias", "values", "display_name",
    "source_group", "board", "dashboard", "page", "pages",
}
# Claves cuyo texto es prosa: sus palabras existen (no se corrigen) pero no
# son destinos de corrección.
_PROSE_KEYS = {"Description", "description", "descripcion", "text", "content", "definition"}


@lru_cache(maxsize=65536)
def _name_words(text):
    """Palabras (plegadas, solo letras, >= 3) de un nombre del catálogo:
    «TIEMPO_EGRESO_OK» -> tiempo, egreso; «FechaRegistro» -> fecharegistro,
    fecha, registro."""
    text = str(text or "")
    words = set()
    for raw in re.split(r"[^\w]+|_", text):
        if not raw:
            continue
        pieces = [raw] + _CAMEL_RE.split(raw)
        for piece in pieces:
            for word in _WORD_SPLIT_RE.findall(fold(piece)):
                if len(word) >= 3:
                    words.add(word)
    return frozenset(words)


@dataclass
class Vocabulary:
    """Vocabulario del catálogo: `targets` (palabra plegada -> forma con
    tildes si se vio alguna) son destinos posibles de una corrección; `known`
    son las palabras que existen (destinos + prosa de la documentación + las
    frecuentes de una pregunta) y por eso nunca se corrigen."""
    targets: dict = field(default_factory=dict)
    known: set = field(default_factory=set)

    def __post_init__(self):
        self.known |= set(self.targets) | COMMON_WORDS
        self._by_length = {}
        for word in self.targets:
            self._by_length.setdefault(len(word), []).append(word)

    def candidates(self, length, spread):
        for size in range(length - spread, length + spread + 1):
            yield from self._by_length.get(size, ())

    def is_known(self, word):
        if word in self.known:
            return True
        # Singular / plural y otro género de una palabra conocida.
        variants = set()
        if word.endswith("es"):
            variants.add(word[:-2])
        if word.endswith("s"):
            variants.add(word[:-1])
            base = word[:-1]
        else:
            base = word
            variants.update({word + "s", word + "es"})
        if base[-1:] in ("o", "a"):
            other = base[:-1] + ("a" if base[-1] == "o" else "o")
            variants.update({other, other + "s"})
        return any(variant in self.known for variant in variants)


EMPTY_VOCABULARY = Vocabulary()


def _walk(node, targets, prose, key=None):
    if isinstance(node, dict):
        for child_key, value in node.items():
            if child_key in ("Expression", "expression", "dax", "source_file", "report_definition_dir",
                             "query_ref", "position", "LineageTag", "ID", "Model"):
                continue
            _walk(value, targets, prose, child_key)
    elif isinstance(node, list):
        for item in node:
            _walk(item, targets, prose, key)
    elif isinstance(node, str):
        if key in _NAME_KEYS and len(node) <= 160:
            if "RowNumber" in node or "LocalDateTable" in node or "DateTableTemplate" in node:
                return
            targets.update(_name_words(node))
        elif key in _PROSE_KEYS:
            prose.update(_WORD_SPLIT_RE.findall(fold(node)))


# Palabra con al menos una letra no ASCII («cirugías», «ocupación»).
_ACCENTED_WORD_RE = re.compile(r"[a-z]*[áéíóúüñàèìòù][^\W\d_]*")


def _accented_forms(text, forms):
    """Forma con tildes de cada palabra plegada vista en la documentación."""
    for word in set(_ACCENTED_WORD_RE.findall(str(text or "").lower())):
        folded = fold(word)
        if folded != word and folded not in forms:
            forms[folded] = word


@lru_cache(maxsize=8)
def _build_vocabulary(project_root, docs_root):
    targets, prose, forms = set(), set(), {}
    data = Path(project_root) / "data"
    json_files = []
    catalog = data / "catalog"
    if catalog.is_dir():
        for path in sorted(catalog.glob("*.json")):
            if path.stem.endswith(("_normalized", "_rag")) or path.stem in (
                    "documentation_import_report", "local_build_report", "semantic_knowledge", "report_links"):
                continue
            json_files.append(path)
        json_files.extend(sorted((catalog / "visuals").glob("*.json")))
    metadata = data / "model_metadata"
    if metadata.is_dir():
        json_files.extend(sorted(metadata.glob("*/_documented_values.json")))
    for path in json_files:
        try:
            _walk(json.loads(path.read_text(encoding="utf-8")), targets, prose)
        except (OSError, ValueError):
            continue
    docs = Path(docs_root) if docs_root else None
    if docs is not None and docs.is_dir():
        for path in sorted(docs.glob("*/md/*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            targets.update(_name_words(path.stem))
            targets.update(_name_words(path.parent.parent.name))
            for match in _MD_FRONT_RE.finditer(text[:3000]):
                targets.update(_name_words(match.group("value")))
            for match in _MD_HEADING_RE.finditer(text):
                targets.update(_name_words(match.group("title")))
            for line in text.splitlines():
                entry = _MD_ENTRY_RE.match(line)
                if entry:
                    targets.update(_name_words(entry.group("key")))
            prose.update(_WORD_SPLIT_RE.findall(fold(text)))
            _accented_forms(text, forms)
    target_map = {word: forms.get(word, word) for word in targets if word.isalpha()}
    return Vocabulary(targets=target_map, known=prose)


def _default_docs_root(project_root):
    candidate = Path(project_root) / "docs_tableros"
    if candidate.is_dir():
        return candidate
    try:
        from src.docs_md.repositorio import raiz_documentos

        return Path(raiz_documentos())
    except Exception:
        return PROJECT_ROOT / "docs_tableros"


def vocabulary_for(project_root=None, docs_root=None):
    """Vocabulario del catálogo de `project_root` (data/ y docs_tableros/),
    en caché por proceso. Sin catálogo devuelve un vocabulario vacío: solo se
    aplican abreviaturas, repeticiones y signos."""
    root = Path(project_root) if project_root else PROJECT_ROOT
    docs = Path(docs_root) if docs_root else _default_docs_root(root)
    try:
        return _build_vocabulary(str(root), str(docs))
    except Exception:
        return EMPTY_VOCABULARY


# ---------------------------------------------------------------- distancia
def _sub_cost(a, b):
    if a == b:
        return 0.0
    return 0.5 if frozenset((a, b)) in _PHONETIC else 1.0


def _indel_cost(char):
    return 0.5 if char == "h" else 1.0


def edit_distance(a, b, limit=2.0):
    """Damerau-Levenshtein ponderado (fonética española y h muda a la mitad).
    Corta en cuanto la distancia supera `limit` (devuelve limit + 1)."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous2 = None
    previous = [0.0]
    for j in range(1, len(b) + 1):
        previous.append(previous[-1] + _indel_cost(b[j - 1]))
    for i in range(1, len(a) + 1):
        current = [previous[0] + _indel_cost(a[i - 1])]
        for j in range(1, len(b) + 1):
            cost = min(
                previous[j] + _indel_cost(a[i - 1]),
                current[j - 1] + _indel_cost(b[j - 1]),
                previous[j - 1] + _sub_cost(a[i - 1], b[j - 1]),
            )
            if (previous2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                cost = min(cost, previous2[j - 2] + 1.0)
            current.append(cost)
        if min(current) > limit:
            return limit + 1
        previous2, previous = previous, current
    return previous[-1]


def _same_start(a, b):
    if a[0] == b[0]:
        return True
    if a[0] == "h" and a[1:2] == b[0:1] or b[0] == "h" and b[1:2] == a[0:1]:
        return True
    return any(a[0] in group and b[0] in group for group in _FIRST_EQUIV)


def _max_distance(length):
    if length < 5:
        return 0.0
    return 1.0 if length < 8 else 2.0


# Terminaciones de conjugación: «aceptamos» no es un tipeo de «aceptados».
_INFLECTIONS = (
    "amos", "emos", "imos", "aron", "ieron", "ando", "iendo", "aban", "aba", "ian", "ia",
    "aste", "iste", "ara", "aran", "era", "eran", "ira", "iran", "are", "ere", "ire",
    "aria", "eria", "iria", "an", "en", "ado", "ada", "ados", "adas", "ido", "ida", "idos", "idas",
)


def _inflection_only(word, target):
    """La diferencia está solo en la terminación y `word` termina en una
    conjugación que `target` no tiene: es otra forma de la palabra, no un tipeo."""
    prefix = 0
    for a, b in zip(word, target):
        if a != b:
            break
        prefix += 1
    if prefix < min(len(word), len(target)) - 4:
        return False
    return any(word.endswith(ending) and not target.endswith(ending) for ending in _INFLECTIONS)


def correct_word(word, vocabulary):
    """Palabra del catálogo a la que corresponde el tipeo `word` (plegada),
    o None si la palabra existe, es corta o no hay un único candidato claro."""
    limit = _max_distance(len(word))
    if not limit or not word.isalpha() or vocabulary.is_known(word):
        return None
    scored = []
    for target in vocabulary.candidates(len(word), int(limit)):
        if not _same_start(word, target) or _inflection_only(word, target):
            continue
        distance = edit_distance(word, target, limit)
        if distance <= limit:
            scored.append((distance, target))
    if not scored:
        return None
    scored.sort()
    best_distance, best = scored[0]
    # Varios candidatos igual de cerca: ambiguo, no se corrige.
    if len(scored) > 1 and scored[1][0] - best_distance < 0.5:
        return None
    return best


# ---------------------------------------------------------------- resultado
@dataclass
class NormalizedQuestion:
    original: str
    text: str
    changes: list = field(default_factory=list)

    @property
    def changed(self):
        return self.text != self.original

    def describe(self):
        labels = {"abreviatura": "abreviatura", "repeticion": "letras repetidas",
                  "tipeo": "tipeo corregido con el catálogo", "signos": "espacios y signos"}
        lines = []
        for change in self.changes:
            if change["kind"] == "signos":
                lines.append(labels["signos"])
            else:
                lines.append(f"{labels[change['kind']]}: «{change['from']}» → «{change['to']}»")
        return list(dict.fromkeys(lines))

    def to_dict(self):
        return {"original": self.original, "normalized": self.text, "changes": list(self.changes)}


# ---------------------------------------------------------------- pasos
def _clean_signs(text):
    text = str(text or "").replace(" ", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([?!¿¡,;:])\1+", r"\1", text)
    text = re.sub(r"\.{4,}", "...", text)
    # Espacio antes de la coma o del signo de cierre (no en decimales).
    text = re.sub(r"\s+([,;:?!])", r"\1", text)
    # Espacio después de la coma / signo de cierre si sigue una letra.
    text = re.sub(r"([,;?!])(?=[^\W\d_])", r"\1 ", text)
    # Espacio tras el signo de apertura.
    text = re.sub(r"([¿¡])\s+", r"\1", text)
    return text


_TOKEN_RE = re.compile(r"\w+|[^\w\s]+|\s+")
_ROMAN_RE = re.compile(r"^[IVXLCDM]+$")


def _is_number(token):
    return bool(token) and bool(re.fullmatch(r"\d+(?:[.,]\d+)*", token))


def _collapse_repeats(token, vocabulary):
    if _ROMAN_RE.match(token) or not re.search(r"(\w)\1\1", token, re.IGNORECASE):
        return token
    single = re.sub(r"(\w)\1{2,}", r"\1", token, flags=re.IGNORECASE)
    double = re.sub(r"(\w)\1{2,}", r"\1\1", token, flags=re.IGNORECASE)
    if not vocabulary.is_known(fold(single)) and vocabulary.is_known(fold(double)):
        return double
    return single


def _abbreviation(token, previous, following, previous_word, first):
    """Expansión de la abreviatura de chat `token`, o None."""
    lower = token.lower()
    if lower not in ABBREVIATIONS:
        return None
    # Una letra en mayúscula a mitad de frase es un nombre o un código
    # («vitamina D», «tipo K»), no una abreviatura.
    if len(token) == 1 and token.isupper() and not first:
        return None
    if lower == "x":
        if _is_number(previous) or _is_number(following):
            return None  # multiplicación: «3 x 4»
        if not following or not following[:1].isalpha():
            return None
        if previous_word in _X_KEEP_AFTER:
            return None
    if lower in ("d", "k") and _is_number(previous):
        return None  # «30 d», «500 k»
    if lower in ("d", "pa") and not (following and following[:1].isalpha()):
        return None
    return ABBREVIATIONS[lower]


def normalize_question(text, vocabulary=None):
    """Normaliza el lenguaje de chat de la pregunta (ver el docstring del módulo)."""
    original = "" if text is None else str(text)
    vocabulary = vocabulary or EMPTY_VOCABULARY
    changes = []
    cleaned = _clean_signs(original)
    # «pa'» / «pa’»: el apóstrofo es parte de la abreviatura.
    cleaned = re.sub(r"(?i)(?<![\w])pa['’](?=\s|$)", "para", cleaned)
    if cleaned != original.strip() or re.search(r"\s{2,}", original):
        changes.append({"kind": "signos", "from": original, "to": cleaned})

    tokens = _TOKEN_RE.findall(cleaned)
    words = [index for index, token in enumerate(tokens) if not token.isspace()]
    output = list(tokens)
    for position, index in enumerate(words):
        token = tokens[index]
        if not token.isalpha():
            continue
        previous = tokens[words[position - 1]] if position > 0 else ""
        following = tokens[words[position + 1]] if position + 1 < len(words) else ""
        previous_word = fold(output[words[position - 1]]) if position > 0 else ""
        first = position == 0 or previous in ("¿", "¡", ".", "?", "!")

        collapsed = _collapse_repeats(token, vocabulary)
        if collapsed != token:
            changes.append({"kind": "repeticion", "from": token, "to": collapsed})
            token = collapsed

        expanded = _abbreviation(token, previous, following, previous_word, first)
        if expanded is not None:
            changes.append({"kind": "abreviatura", "from": token, "to": expanded})
            output[index] = expanded
            continue

        folded = fold(token)
        proper = token[:1].isupper() and not first
        if not proper and not token.isupper():
            target = correct_word(folded, vocabulary)
            if target is not None:
                corrected = vocabulary.targets.get(target, target)
                changes.append({"kind": "tipeo", "from": token, "to": corrected})
                token = corrected
        output[index] = token

    normalized = "".join(output)
    return NormalizedQuestion(original=original, text=normalized, changes=changes)

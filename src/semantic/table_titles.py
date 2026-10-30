"""
Título de una tabla o matriz frente al nombre de la columna que agrega.

En una tarjeta el título es el nombre del dato («CAMAS OCUPADAS» = el número
de camas ocupadas). En una tabla o matriz el título describe las FILAS que
lista: la tabla «PACIENTES HOSPITALIZADOS» muestra, por paciente, la suma de
TIEMPO_PARA_HOSPITALIZACION; la tabla «CAMAS OCUPADAS» suma
PACIENTE_ACOSTADO. Ese título no es el nombre del valor agregado.

Regla: en una tabla/matriz, el título nombra al valor solo si el valor es un
conteo (COUNT/DISTINCTCOUNT: cuenta lo que la tabla lista) o si el título
explica todas las palabras de la columna agregada. Si no, el indicador se
rotula con su agregación («Suma de PACIENTE_ACOSTADO») y el título queda como
contexto, no como alias.
"""
import re
import unicodedata

TABLE_VISUAL_TYPES = {"tableex", "pivottable", "matrix", "table"}
COUNT_AGGREGATIONS = {"count", "countnonnull", "distinctcount", "countrows", "countdistinct"}
AGGREGATION_NAMES = {
    "sum": "Suma", "average": "Promedio", "avg": "Promedio", "min": "Mínimo", "max": "Máximo",
    "count": "Conteo", "countnonnull": "Conteo", "distinctcount": "Conteo distinto", "median": "Mediana",
}
_FRIENDLY_RE = re.compile(
    r"^(?:suma|promedio|conteo|recuento|minimo|maximo|mediana)\s+(?:distinto\s+)?de\s+", re.IGNORECASE,
)


def _plain(text):
    text = unicodedata.normalize("NFD", str(text or "").lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _stem(word):
    for suffix in ("aciones", "acion", "ados", "adas", "ado", "ada", "es", "os", "as", "s", "o", "a"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def is_table_visual(visual_type):
    return _plain(visual_type).replace(" ", "") in TABLE_VISUAL_TYPES


def title_names_value(visual_type, title, aggregation, column):
    """¿El título del visual puede ser el nombre del valor agregado?"""
    if not title:
        return False
    if not is_table_visual(visual_type):
        return True
    if _plain(aggregation).replace(" ", "") in COUNT_AGGREGATIONS:
        return True
    column_words = [word for word in _plain(str(column or "").replace("_", " ")).split()
                    if len(word) >= 3 and not word.isdigit()]
    if not column_words:
        return True
    title_stems = {_stem(word) for word in _plain(title).split() if len(word) >= 3}
    return all(_stem(word) in title_stems for word in column_words)


def friendly_label(aggregation, column, aliases=()):
    """«Suma de PACIENTE_ACOSTADO»: el alias amigable del catálogo si existe."""
    for alias in aliases or ():
        if alias and _FRIENDLY_RE.match(_plain(alias)):
            return str(alias)
    name = AGGREGATION_NAMES.get(_plain(aggregation).replace(" ", ""))
    if name and column:
        return f"{name} de {column}"
    return None

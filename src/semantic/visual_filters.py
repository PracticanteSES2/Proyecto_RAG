"""Filtros de nivel de visual (filterConfig de un visual.json de PBIR).

Una tarjeta como «MEDICAMENTOS EN VENCIMIENTO 0-30 DÍAS» muestra
DISTINCTCOUNT(IPRCODIGO) con el filtro del visual `mes <= 1`: sin ese filtro
el valor no es el de la tarjeta. Este módulo convierte la condición de PBIR
(`filter.Where[].Condition`) en una estructura simple y luego en DAX:

- {"op": "in", "values": [...]}            In (Categorical)
- {"op": "cmp", "cmp": "<=", "value": 1}   Comparison (Advanced); value None = blanco
- {"op": "contains"|"startswith"|"endswith", "value": "X"}
- {"op": "not", "arg": {...}}, {"op": "and"|"or", "args": [...]}

Solo se entienden condiciones sobre la propia columna del filtro (sin
agregaciones ni medidas); lo demás devuelve None y no se aplica.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

# ComparisonKind de PBIR (QueryComparisonKind).
_COMPARISONS = {0: "=", 1: ">", 2: ">=", 3: "<", 4: "<=", 5: "<>"}
_TEXT_FUNCTIONS = {"Contains": "contains", "StartsWith": "startswith", "EndsWith": "endswith"}


class UnsupportedCondition(ValueError):
    """La condición usa algo que no se traduce con seguridad (agregación, otra columna...)."""


def parse_literal(raw):
    """Literal de PBIR -> valor Python: 'texto' -> str, 1L -> int, 1.5D -> float,
    null -> None, true/false -> bool, datetime'2024-01-01T00:00:00' ->
    {"date": "2024-01-01"} (serializable en el catálogo)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("''", "'")
    lower = text.lower()
    if lower == "null":
        return None
    if lower in ("true", "false"):
        return lower == "true"
    match = re.fullmatch(r"datetime'([^']+)'", text, re.IGNORECASE)
    if match:
        try:
            return {"date": datetime.fromisoformat(match.group(1)[:19]).date().isoformat()}
        except ValueError as error:
            raise UnsupportedCondition(f"fecha no reconocida {text}") from error
    number = text[:-1] if text[-1:] in ("L", "D", "M") else text
    try:
        return float(number) if "." in number else int(number)
    except ValueError as error:
        raise UnsupportedCondition(f"literal no reconocido {text}") from error


def _column_property(node):
    """Nombre de la columna de un nodo {"Column": {...}} o error si es otra cosa."""
    if isinstance(node, dict) and isinstance(node.get("Column"), dict):
        return node["Column"].get("Property")
    raise UnsupportedCondition("la condición no es sobre una columna")


def _literal(node):
    if isinstance(node, dict) and isinstance(node.get("Literal"), dict):
        return parse_literal(node["Literal"].get("Value"))
    raise UnsupportedCondition("el lado derecho no es un literal")


def _parse_node(node, column):
    if not isinstance(node, dict) or len(node) != 1:
        raise UnsupportedCondition("nodo de condición desconocido")
    kind, body = next(iter(node.items()))
    if kind == "Not":
        return {"op": "not", "arg": _parse_node(body.get("Expression"), column)}
    if kind in ("And", "Or"):
        return {
            "op": kind.lower(),
            "args": [_parse_node(body.get("Left"), column), _parse_node(body.get("Right"), column)],
        }
    if kind == "In":
        expressions = body.get("Expressions") or []
        if len(expressions) != 1 or body.get("Table"):
            raise UnsupportedCondition("In con varias columnas")
        _check_column(_column_property(expressions[0]), column)
        values = []
        for row in body.get("Values") or []:
            if not isinstance(row, list) or len(row) != 1:
                raise UnsupportedCondition("In con tuplas")
            values.append(_literal(row[0]))
        return {"op": "in", "values": values}
    if kind == "Comparison":
        operator = _COMPARISONS.get(body.get("ComparisonKind"))
        if operator is None:
            raise UnsupportedCondition("comparación desconocida")
        _check_column(_column_property(body.get("Left")), column)
        return {"op": "cmp", "cmp": operator, "value": _literal(body.get("Right"))}
    if kind in _TEXT_FUNCTIONS:
        _check_column(_column_property(body.get("Left")), column)
        value = _literal(body.get("Right"))
        if not isinstance(value, str):
            raise UnsupportedCondition("búsqueda de texto sin texto")
        return {"op": _TEXT_FUNCTIONS[kind], "value": value}
    raise UnsupportedCondition(f"condición {kind} no soportada")


def _check_column(found, expected):
    if expected and found and str(found).strip().lower() != str(expected).strip().lower():
        raise UnsupportedCondition(f"la condición usa {found}, no {expected}")


def parse_condition(filter_json, column=None):
    """Condición (estructura simple) de un filtro de PBIR o None si no tiene.
    Lanza UnsupportedCondition si tiene una que no se entiende."""
    where = ((filter_json or {}).get("filter") or {}).get("Where") or []
    conditions = [
        _parse_node(item.get("Condition"), column)
        for item in where if isinstance(item, dict) and item.get("Condition") is not None
    ]
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"op": "and", "args": conditions}


def condition_from_visual_file(source_file, filter_name, column=None):
    """Condición del filtro `filter_name` leída del visual.json original (para
    catálogos generados antes de guardar la condición). None si no se puede."""
    try:
        path = Path(source_file)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    for item in ((payload.get("filterConfig") or {}).get("filters") or []):
        if item.get("name") == filter_name:
            return parse_condition(item, column)
    return None


# ---------------------------------------------------------------- DAX
def _dax_literal(value):
    if value is None:
        return "BLANK()"
    if isinstance(value, bool):
        return "TRUE()" if value else "FALSE()"
    if isinstance(value, (int, float)):
        return str(int(value)) if float(value).is_integer() else repr(value)
    if isinstance(value, dict) and value.get("date"):
        value = date.fromisoformat(str(value["date"])[:10])
    if isinstance(value, (date, datetime)):
        return f"DATE({value.year}, {value.month}, {value.day})"
    return '"' + str(value).replace('"', '""') + '"'


def condition_dax(condition, column_ref):
    """Expresión booleana DAX sobre `column_ref` ('T'[C])."""
    op = condition.get("op")
    if op == "not":
        return f"NOT ({condition_dax(condition['arg'], column_ref)})"
    if op in ("and", "or"):
        joiner = " && " if op == "and" else " || "
        return "(" + joiner.join(condition_dax(arg, column_ref) for arg in condition["args"]) + ")"
    if op == "in":
        values = condition.get("values") or []
        present = [value for value in values if value is not None]
        parts = []
        if present:
            parts.append(f"{column_ref} IN {{" + ", ".join(_dax_literal(v) for v in present) + "}")
        if len(present) < len(values):
            parts.append(f"ISBLANK({column_ref})")
        if not parts:
            return "FALSE()"
        return parts[0] if len(parts) == 1 else "(" + " || ".join(parts) + ")"
    if op == "cmp":
        value = condition.get("value")
        if value is None:
            if condition["cmp"] == "=":
                return f"ISBLANK({column_ref})"
            if condition["cmp"] == "<>":
                return f"NOT ISBLANK({column_ref})"
            raise UnsupportedCondition("comparación de orden con blanco")
        return f"{column_ref} {condition['cmp']} {_dax_literal(value)}"
    if op in ("contains", "startswith", "endswith"):
        literal = _dax_literal(condition.get("value"))
        if op == "contains":
            return f"CONTAINSSTRING({column_ref}, {literal})"
        length = len(str(condition.get("value")))
        side = "LEFT" if op == "startswith" else "RIGHT"
        return f"{side}({column_ref}, {length}) = {literal}"
    raise UnsupportedCondition(f"operación {op}")


def filter_dax(table, column, condition):
    """Argumento de CALCULATE que aplica la condición sin quitar los demás
    filtros de la columna (como un filtro de visual)."""
    table_ref = "'" + str(table).replace("'", "''") + "'"
    column_ref = f"{table_ref}[{str(column).replace(']', ']]')}]"
    return f"KEEPFILTERS(FILTER(ALL({column_ref}), {condition_dax(condition, column_ref)}))"


def _text(value):
    if value is None:
        return "(en blanco)"
    if isinstance(value, dict) and value.get("date"):
        return str(value["date"])
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value).strip()


def describe_condition(condition, column, max_values=4):
    """Texto corto para el razonamiento: «mes <= 1», «SERVICIO no es HOSPITALIZACION PARCIAL»."""
    op = condition.get("op")
    if op == "not":
        inner = condition["arg"]
        if inner.get("op") == "in":
            return f"{column} no es " + _values_text(inner.get("values"), max_values)
        if inner.get("op") == "cmp" and inner.get("value") is None and inner.get("cmp") == "=":
            return f"{column} no está en blanco"
        return f"no ({describe_condition(inner, column, max_values)})"
    if op in ("and", "or"):
        joiner = " y " if op == "and" else " o "
        return joiner.join(describe_condition(arg, column, max_values) for arg in condition["args"])
    if op == "in":
        return f"{column} es " + _values_text(condition.get("values"), max_values)
    if op == "cmp":
        if condition.get("value") is None:
            return f"{column} en blanco" if condition["cmp"] == "=" else f"{column} no está en blanco"
        return f"{column} {condition['cmp']} {_text(condition.get('value'))}"
    if op == "contains":
        return f"{column} contiene «{condition.get('value')}»"
    if op == "startswith":
        return f"{column} empieza por «{condition.get('value')}»"
    if op == "endswith":
        return f"{column} termina en «{condition.get('value')}»"
    return str(column)


def _values_text(values, max_values):
    values = list(values or [])
    shown = ", ".join(_text(value) for value in values[:max_values])
    if len(values) > max_values:
        shown += f" (y {len(values) - max_values} más)"
    return shown


def condition_signature(table, column, condition):
    """Clave estable para comparar filtros de visuales distintos."""
    return json.dumps(
        [str(table).lower(), str(column).lower(), condition], sort_keys=True, default=str, ensure_ascii=False,
    )

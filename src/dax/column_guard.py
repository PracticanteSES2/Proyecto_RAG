"""
Columnas del DAX contra la metadata del modelo semántico.

Dos defensas, antes de enviar nada a Power BI:

1. ``repair_plan``: la columna de fecha de un periodo se toma SIEMPRE del
   modelo de la medida. Si el plan trae una columna que no existe en ese
   modelo (TABLERO TIEMPOS URGENCIAS: el informe nombra la jerarquía de fechas
   como ``Calendario.Date.Variación…`` pero la columna real es
   ``Calendario[FECHA]``) o una tabla de fechas que no filtra la tabla de la
   medida, se usa la tabla de fechas relacionada con la tabla de la medida
   (``'INTERCONSULTA'[FECHA] -> 'Calendario'[FECHA]``) y su columna real; sin
   relación, la columna de fecha de la propia tabla. Si no hay ninguna, el
   plan no se puede consultar y se explica.
2. ``unknown_references``: toda referencia ``'Tabla'[Columna]`` /
   ``Tabla[Columna]`` del texto DAX debe existir en la metadata del modelo
   (columna o medida). Si no, la consulta no se envía.

El catálogo técnico es el de ``data/catalog/<modelo>_rag.json``
(``tables[].columns[].name/data_type``, ``tables[].measures[].name`` y
``relationships[]`` con FromTable/FromColumn/ToTable/ToColumn/IsActive).
"""
import copy
import re
import unicodedata

# Tablas automáticas de Power BI (no están en el catálogo y no se consultan).
_SYSTEM_TABLE_RE = re.compile(r"^(?:localdatetable|datetabletemplate)", re.IGNORECASE)
# Tabla de fechas por su nombre.
_CALENDAR_NAME_RE = re.compile(r"^(?:dim\s*)?(?:calendario|calendar|fecha|fechas|date|dates|tiempo)\b")
_DATE_TYPES = {"date", "datetime", "datetimeoffset"}

# 'Tabla con espacios'[Columna] o Tabla[Columna] (sin comillas: letras, dígitos, _).
_REFERENCE_RE = re.compile(
    r"(?:'(?P<quoted>(?:[^']|'')+)'\s*|(?<![\w\]'\"\.])(?P<bare>[^\W\d]\w*))\[(?P<column>(?:[^\]]|\]\])+)\]"
)
# Tabla sin comillas pegada al corchete: «ORDER BY [__orden]» o «ASC [x]» no son tablas.
_STRING_RE = re.compile(r'"(?:[^"]|"")*"')


def _fold(value):
    text = unicodedata.normalize("NFD", str(value or "")).casefold()
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


class ModelSchema:
    """Tablas, columnas, medidas y relaciones de UN modelo (insensible a mayúsculas)."""

    def __init__(self, catalog):
        catalog = catalog if isinstance(catalog, dict) else {}
        self.tables = {}      # fold(tabla) -> {"name", "columns": {fold: (nombre, tipo)}, "measures": {fold}}
        self.measures = set()
        for table in catalog.get("tables") or []:
            name = table.get("name") or table.get("Name")
            if not name:
                continue
            columns = {}
            for column in table.get("columns") or []:
                column_name = column.get("name") or column.get("Name")
                if column_name:
                    columns[_fold(column_name)] = (
                        column_name, str(column.get("data_type") or column.get("DataType") or "").casefold(),
                    )
            measures = {
                _fold(m.get("name") or m.get("Name")) for m in table.get("measures") or []
                if m.get("name") or m.get("Name")
            }
            self.measures |= measures
            self.tables[_fold(name)] = {"name": name, "columns": columns, "measures": measures}
        self.relationships = []
        for relation in catalog.get("relationships") or []:
            if relation.get("IsActive") is False or str(relation.get("IsActive")).casefold() == "false":
                continue
            source, target = relation.get("FromTable"), relation.get("ToTable")
            if source and target:
                self.relationships.append((
                    _fold(source), _fold(relation.get("FromColumn")),
                    _fold(target), _fold(relation.get("ToColumn")),
                ))

    def __bool__(self):
        return bool(self.tables)

    # ---------------- consultas básicas ----------------
    def table(self, name):
        return self.tables.get(_fold(name))

    def column(self, table, column):
        """(tabla, columna, tipo) con los nombres reales, o None."""
        entry = self.table(table)
        if not entry:
            return None
        found = entry["columns"].get(_fold(column))
        return (entry["name"], found[0], found[1]) if found else None

    def has_reference(self, table, name):
        """¿'T'[name] es una columna o una medida del modelo?"""
        if _SYSTEM_TABLE_RE.match(str(table or "")):
            return True
        entry = self.table(table)
        if not entry:
            return False
        key = _fold(name)
        return key in entry["columns"] or key in entry["measures"] or key in self.measures

    def is_date_column(self, table, column):
        found = self.column(table, column)
        return bool(found) and found[2] in _DATE_TYPES

    def related_tables(self, table, depth=2):
        """La tabla y las que la filtran (lado «uno» de sus relaciones activas)."""
        related = {_fold(table)}
        for _ in range(depth):
            related |= {target for source, _, target, _ in self.relationships if source in related}
        return related

    # ---------------- columna de fecha de una medida ----------------
    def date_column_for(self, fact_tables):
        """(tabla, columna, origen) de la fecha que filtra la medida, o None.

        1. Tabla de fechas relacionada con la tabla de la medida (relación
           activa hacia una columna de tipo fecha; primero las que se llaman
           Calendario/Fecha/Date).
        2. Sin relación: la columna de fecha de la propia tabla (la llamada
           FECHA/DATE o la única de tipo fecha).
        """
        facts = [_fold(name) for name in fact_tables or [] if self.table(name)]
        related = []
        for fact in facts:
            for source, _, target, target_column in self.relationships:
                if source != fact or _SYSTEM_TABLE_RE.match(target):
                    continue
                found = self.column(target, target_column)
                if found and found[2] in _DATE_TYPES:
                    related.append((found[0], found[1]))
        if related:
            related.sort(key=lambda item: (not _CALENDAR_NAME_RE.match(_fold(item[0])), _fold(item[0])))
            table, column = related[0]
            return table, column, "relationship"
        for fact in facts:
            entry = self.tables[fact]
            dates = [(name, kind) for name, kind in entry["columns"].values() if kind in _DATE_TYPES]
            named = [name for name, _ in dates if _fold(name) in {"fecha", "date"}]
            if named:
                return entry["name"], named[0], "own_table"
            if len(dates) == 1:
                return entry["name"], dates[0][0], "own_table"
        return None


def metric_fact_tables(plan, schema):
    """Tablas sobre las que se calcula la medida del plan: la suya (si no es
    un calendario) y las que nombra su expresión DAX."""
    metric = (plan or {}).get("metric") or {}
    tables = []
    own = metric.get("table")
    if own and schema.table(own) and not _CALENDAR_NAME_RE.match(_fold(own)):
        tables.append(schema.table(own)["name"])
    # Una medida explícita trae "[MEDIDA]" en dax_expression y su fórmula en model_expression.
    expression = " ".join(str(metric.get(key) or "") for key in ("dax_expression", "model_expression"))
    for table, _ in references(expression):
        entry = schema.table(table)
        if entry and entry["name"] not in tables and not _CALENDAR_NAME_RE.match(_fold(entry["name"])):
            tables.append(entry["name"])
    return tables


def references(dax):
    """[(tabla, columna)] calificadas del texto DAX (sin literales de texto)."""
    text = _STRING_RE.sub('""', str(dax or ""))
    found = []
    for match in _REFERENCE_RE.finditer(text):
        table = match.group("quoted")
        table = table.replace("''", "'") if table is not None else match.group("bare")
        column = match.group("column").replace("]]", "]")
        found.append((table, column))
    return found


def unknown_references(dax, schema):
    """«T[C]» del DAX que no existen en el modelo (vacío si todo existe o si
    no hay metadata con la que verificar)."""
    if not schema:
        return []
    missing = []
    for table, column in references(dax):
        label = f"{table}[{column}]"
        if not schema.has_reference(table, column) and label not in missing:
            missing.append(label)
    return missing


def _plan_columns(plan):
    """Referencias de columna del plan que van al DAX: (contenedor, rol)."""
    for item in plan.get("filters") or []:
        yield item, "temporal_set" if item.get("type") == "temporal_set" else item.get("type")
    for bucket in plan.get("temporal_buckets") or []:
        for item in bucket.get("filters") or []:
            yield item, "temporal_set" if item.get("type") == "temporal_set" else item.get("type")
    if not plan.get("temporal_buckets"):
        for item in plan.get("group_by") or []:
            yield item, "group"
    dimension = plan.get("share_dimension") or {}
    if dimension.get("column") and not dimension.get("temporal"):
        yield dimension, "share"


def repair_plan(plan, schema):
    """(plan, reparaciones, sin_resolver).

    `plan` es una copia con las columnas corregidas (o el mismo si no hubo
    cambios); `reparaciones` = [{"from": "T[C]", "to": "T[C]", "why": ...}];
    `sin_resolver` = ["T[C]"] que no existen y no tienen reemplazo seguro.
    Sin metadata no se cambia nada.
    """
    if not schema or not isinstance(plan, dict):
        return plan, [], []
    facts = metric_fact_tables(plan, schema)
    related = set()
    for fact in facts:
        related |= schema.related_tables(fact)
    date_choice = None
    repairs, unresolved = [], []
    working = None

    def target():
        nonlocal working
        if working is None:
            working = copy.deepcopy(plan)
        return working

    items = list(_plan_columns(plan))
    for index, (item, role) in enumerate(items):
        refs = item.get("columns") if role == "temporal_set" else [item]
        for position, ref in enumerate(refs or []):
            table, column = ref.get("table"), ref.get("column")
            if not table or not column:
                continue
            exists = schema.column(table, column)
            is_date = role == "date_range"
            unrelated = (
                is_date and exists and facts and _fold(table) not in related
            )
            if exists and not unrelated:
                continue
            if is_date:
                if date_choice is None:
                    date_choice = schema.date_column_for(facts) or False
                if date_choice:
                    new_table, new_column, origin = date_choice
                    # Misma ruta en la copia del plan.
                    copy_item = list(_plan_columns(target()))[index][0]
                    copy_item["table"], copy_item["column"] = new_table, new_column
                    repairs.append({
                        "from": f"{table}[{column}]", "to": f"{new_table}[{new_column}]",
                        "why": (
                            ("no existe en el modelo" if not exists else
                             "su tabla no filtra la tabla de la medida")
                            + (": se usa la tabla de fechas relacionada con "
                               if origin == "relationship" else ": se usa la fecha de la propia tabla ")
                            + ", ".join(facts)
                        ),
                    })
                    continue
            if not exists:
                unresolved.append(f"{table}[{column}]")
    return (working if working is not None else plan), repairs, unresolved


class GuardedQueryPlanDAXGenerator:
    """Envuelve el generador del Query Plan: repara las columnas del plan con
    la metadata de su modelo antes de generar y rechaza el plan si queda una
    columna inexistente («unknown_columns»)."""

    GUARDED = ("generate", "generate_ranked", "generate_share", "generate_detail", "generate_multi")

    def __init__(self, inner, catalog_provider):
        self._inner = inner
        self._catalog_provider = catalog_provider
        self._schemas = {}

    def schema(self, semantic_model):
        key = _fold(semantic_model)
        if key not in self._schemas:
            try:
                catalog = self._catalog_provider(semantic_model) if semantic_model else {}
            except Exception:
                catalog = {}
            self._schemas[key] = ModelSchema(catalog)
        return self._schemas[key]

    def _check(self, plan):
        schema = self.schema((plan or {}).get("semantic_model"))
        return repair_plan(plan, schema)

    @staticmethod
    def _rejected(plan, unresolved):
        return {
            "status": "rejected", "reason": "unknown_columns",
            "unknown_columns": unresolved, "semantic_model": (plan or {}).get("semantic_model"),
        }

    def __getattr__(self, name):
        attribute = getattr(self._inner, name)
        if name not in self.GUARDED or not callable(attribute):
            return attribute

        def guarded(*args, **kwargs):
            if name == "generate_multi":
                entries = args[0] if args else kwargs.get("entries")
                checked, repairs = [], []
                for entry in entries or []:
                    plan, fixed, unresolved = self._check(entry.get("plan"))
                    if unresolved:
                        return self._rejected(entry.get("plan"), unresolved)
                    repairs.extend(fixed)
                    checked.append({**entry, "plan": plan})
                rest = args[1:] if args else ()
                kwargs.pop("entries", None)
                result = attribute(checked, *rest, **kwargs)
            else:
                plan = args[0] if args else kwargs.get("plan")
                plan, repairs, unresolved = self._check(plan)
                if unresolved:
                    return self._rejected(plan, unresolved)
                if args:
                    args = (plan, *args[1:])
                else:
                    kwargs["plan"] = plan
                result = attribute(*args, **kwargs)
            if repairs and isinstance(result, dict):
                result = {**result, "column_repairs": repairs}
            return result

        return guarded

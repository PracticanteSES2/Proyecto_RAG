"""
Evaluador DAX del simulador: contexto de filtro, contexto de fila, transición de
contexto, propagación de filtros por relaciones y las funciones más usadas.

Semántica implementada (resumen):
  - Filtros = conjuntos de tuplas sobre columnas con linaje (tabla, columna). Un filtro
    sobre una tabla completa ('T' o FILTER('T', ...)) se guarda sobre la pseudo-columna
    (T, "__rowid").
  - CALCULATE: argumentos evaluados en el contexto original, transición de contexto,
    modificadores (ALL/REMOVEFILTERS/ALLEXCEPT/ALLSELECTED/USERELATIONSHIP) y luego
    filtros (reemplazan los existentes sobre las mismas columnas salvo KEEPFILTERS).
  - Relaciones activas: el filtro fluye del lado "uno" al lado "varios" y en ambos
    sentidos si CrossFilteringBehavior = BothDirections (o 1:1).
  - Texto: comparaciones sin distinguir mayúsculas (como VertiPaq).
  - Comparar Texto con número/fecha lanza el mismo error que Power BI; comparar fecha con
    número se permite (como DAX) pero se registra como TYPE MISMATCH.

Lo que el simulador no implementa lanza DaxUnsupported (no es un error "real"); en las
medidas del modelo se usa entonces un valor de respaldo determinista (aproximado).
"""
import calendar
import datetime as dt
import hashlib
import math
import re
from decimal import Decimal

from .dax_parser import (
    BinOp, Call, ColRef, DaxError, DaxUnsupported, Ident, InOp, Num, Str, TableCtor,
    TableRef, Unary, VarBlock, parse_expression, parse_query, walk,
)
from .metadata import TYPE_LABEL, Measure, key

ROWID = "__rowid"
EPOCH = dt.datetime(1899, 12, 30)

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Funciones DAX reales que el simulador no implementa (=> DaxUnsupported, no "nombre inválido").
KNOWN_UNSUPPORTED = {
    "EARLIER", "EARLIEST", "PATH", "PATHITEM", "PATHCONTAINS", "PATHLENGTH", "NATURALINNERJOIN",
    "NATURALLEFTOUTERJOIN", "SUBSTITUTEWITHINDEX", "GROUPBY", "CURRENTGROUP", "ROLLUP", "ROLLUPGROUP",
    "ROLLUPADDISSUBTOTAL", "ADDMISSINGITEMS", "IGNORE", "NONVISUAL", "WINDOW", "OFFSET", "INDEX",
    "RANK", "ROWNUMBER", "PARTITIONBY", "ORDERBY", "MATCHBY", "EVALUATEANDLOG", "PERCENTILE.INC",
    "PERCENTILE.EXC", "PERCENTILEX.INC", "PERCENTILEX.EXC", "XIRR", "XNPV", "SAMPLE", "DETAILROWS",
    "SELECTEDMEASURE", "SELECTEDMEASURENAME", "ISSELECTEDMEASURE", "CONTAINSROW", "CONTAINS",
    "TOPNSKIP", "EXTERNALMEASURE", "NETWORKDAYS", "STDEV.S", "STDEV.P", "VAR.S", "VAR.P",
    "STDEVX.S", "STDEVX.P", "GEOMEAN", "PRODUCT", "PRODUCTX", "NORM.DIST", "OPENINGBALANCEMONTH",
    "CLOSINGBALANCEMONTH", "OPENINGBALANCEYEAR", "CLOSINGBALANCEYEAR", "DATESWTD", "TOTALWTD",
    "ISONORAFTER", "FILTERS", "KEYWORDMATCH", "LINEST", "LINESTX", "CROSSFILTER",
}

# Funciones que agregan/iteran: sus columnas internas no definen el filtro booleano.
_AGGREGATING = {
    "SUM", "SUMX", "AVERAGE", "AVERAGEX", "AVERAGEA", "MIN", "MINX", "MINA", "MAX", "MAXX", "MAXA",
    "COUNT", "COUNTA", "COUNTX", "COUNTAX", "COUNTROWS", "COUNTBLANK", "DISTINCTCOUNT",
    "DISTINCTCOUNTNOBLANK", "CALCULATE", "CALCULATETABLE", "SELECTEDVALUE", "VALUES", "DISTINCT",
    "FILTER", "ALL", "ALLSELECTED", "ALLEXCEPT", "ALLNOBLANKROW", "REMOVEFILTERS", "MEDIAN", "MEDIANX",
    "FIRSTDATE", "LASTDATE", "FIRSTNONBLANK", "LASTNONBLANK", "RANKX", "CONCATENATEX", "LOOKUPVALUE",
    "HASONEVALUE", "ISFILTERED", "ISCROSSFILTERED", "TOTALYTD", "TOTALMTD", "TOTALQTD", "RELATEDTABLE",
}


# ----------------------------------------------------------------------------
# Valores
# ----------------------------------------------------------------------------

def vkey(value):
    """Clave de igualdad DAX: texto sin mayúsculas, decimales como float."""
    if isinstance(value, str):
        return value.casefold()
    if isinstance(value, bool):
        return ("b", value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return dt.datetime(value.year, value.month, value.day)
    return value


def type_label(value):
    if isinstance(value, bool):
        return "True/False"
    if isinstance(value, int):
        return "Integer"
    if isinstance(value, Decimal):
        return "Currency"
    if isinstance(value, float):
        return "Number"
    if isinstance(value, dt.datetime):
        return "Date"
    if isinstance(value, str):
        return "Text"
    return "Variant"


def serial(value):
    return (value - EPOCH).total_seconds() / 86400.0


def from_serial(number):
    return EPOCH + dt.timedelta(days=float(number))


def stable_fraction(*parts):
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _num(value):
    return float(value) if isinstance(value, Decimal) else value


def to_number(value, pos=None):
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float, Decimal)):
        return value
    if isinstance(value, dt.datetime):
        return serial(value)
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        try:
            return int(text) if re.fullmatch(r"-?\d+", text) else float(text)
        except ValueError:
            raise DaxError(f"Cannot convert value '{value}' of type Text to type Number.", "type", pos)
    raise DaxError(f"Cannot convert value of type {type_label(value)} to type Number.", "type", pos)


def to_bool(value, pos=None):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return value != 0
    if isinstance(value, dt.datetime):
        return True
    raise DaxError(f"Cannot convert value '{value}' of type Text to type True/False.", "type", pos)


def to_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, dt.datetime):
        if value.hour == value.minute == value.second == 0:
            return value.strftime("%d/%m/%Y")
        return value.strftime("%d/%m/%Y %H:%M:%S")
    return str(value)


def to_date(value, pos=None):
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return from_serial(value)
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return dt.datetime.strptime(text, fmt)
            except ValueError:
                continue
    raise DaxError(f"Cannot convert value '{value}' of type {type_label(value)} to type Date.", "type", pos)


def sort_key(value):
    if value is None:
        return (0, 0)
    if isinstance(value, str):
        return (2, value.casefold())
    if isinstance(value, dt.datetime):
        return (1, serial(value))
    if isinstance(value, bool):
        return (1, int(value))
    return (1, float(value))


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


# ----------------------------------------------------------------------------
# Estructuras de contexto
# ----------------------------------------------------------------------------

class Filter:
    __slots__ = ("cols", "keys")

    def __init__(self, cols, keys):
        self.cols = tuple(cols)
        self.keys = frozenset(keys)

    def tables(self):
        return {t for t, _ in self.cols}

    def signature(self):
        return (self.cols, self.keys)


class Row:
    """Contexto de fila: fila de una tabla del modelo (table/rowid) o fila de extensión."""
    __slots__ = ("table", "rowid", "values", "names")

    def __init__(self, table=None, rowid=None, values=None, names=None):
        self.table = table
        self.rowid = rowid
        self.values = values or {}
        self.names = names or {}


class Ctx:
    __slots__ = ("filters", "rel_on", "rel_off", "rows", "vars", "allselected", "cache")

    def __init__(self, filters=(), rel_on=frozenset(), rel_off=frozenset(), rows=(), vars=None,
                 allselected=None):
        self.filters = tuple(filters)
        self.rel_on = rel_on
        self.rel_off = rel_off
        self.rows = tuple(rows)
        self.vars = vars or {}
        self.allselected = allselected
        self.cache = {}

    def copy(self, **changes):
        data = {"filters": self.filters, "rel_on": self.rel_on, "rel_off": self.rel_off,
                "rows": self.rows, "vars": self.vars, "allselected": self.allselected}
        data.update(changes)
        new = Ctx(**data)
        if not any(k in changes for k in ("filters", "rel_on", "rel_off")):
            new.cache = self.cache   # mismo contexto de filtro: se comparte la caché de filas visibles
        return new

    def signature(self):
        return (tuple(sorted((f.signature() for f in self.filters), key=repr)),
                tuple(sorted(self.rel_on)), tuple(sorted(self.rel_off)))


class ColInfo:
    __slots__ = ("name", "lineage")

    def __init__(self, name=None, lineage=None):
        self.name = name          # nombre de columna de extensión ("Value") o None
        self.lineage = lineage    # (tkey, ckey) o None


class TableVal:
    """Tabla resultado. Si base != None, las filas son filas completas de esa tabla del modelo."""

    def __init__(self, cols, rows=None, base=None, rowids=None, runtime=None):
        self.cols = list(cols)
        self._rows = rows
        self.base = base
        self.rowids = rowids
        self._rt = runtime

    @property
    def rows(self):
        if self._rows is None:
            store = self._rt.store(self.base)
            ckeys = [c.lineage[1] for c in self.cols]
            self._rows = [tuple(store.value(i, c) for c in ckeys) for i in self.rowids]
        return self._rows

    def __len__(self):
        return len(self.rowids) if self.base is not None and self._rows is None else len(self.rows)

    def row_contexts(self):
        if self.base is not None and self._rows is None:
            for rid in self.rowids:
                yield Row(table=self.base, rowid=rid)
            return
        for values in self.rows:
            yield self.row_from_tuple(values)

    def row_from_tuple(self, values):
        lineage, names = {}, {}
        for col, value in zip(self.cols, values):
            if col.lineage:
                lineage[col.lineage] = value
            if col.name:
                names[col.name.casefold()] = value
        return Row(values=lineage, names=names)


# ----------------------------------------------------------------------------
# Evaluador
# ----------------------------------------------------------------------------

class Evaluator:
    """Evaluador ligado a un ModelRuntime (ver engine.py)."""

    def __init__(self, runtime):
        self.rt = runtime
        self.schema = runtime.schema
        self.query_measures = {}
        self.query_trees = {}
        self.memo = {}
        self.stack = []
        self._incoming = None

    # ======================================================================
    # Esquema
    # ======================================================================
    def table_schema(self, name, pos=None):
        table = self.schema.table(name)
        if table is None:
            raise DaxError(f"Cannot find table '{name}'.", "name", pos)
        return table

    def column_schema(self, table, column, pos=None):
        t = self.table_schema(table, pos)
        col = t.columns.get(key(column))
        if col is None or col.kind == "rownumber":
            raise DaxError(f"Column '{column}' in table '{t.name}' cannot be found or may not be used "
                           f"in this expression.", "name", pos)
        return t, col

    def lineage_of(self, node):
        t, c = self.column_schema(node.table, node.column, node.pos)
        return (key(t.name), key(c.name))

    def display(self, info):
        if info.name:
            return f"[{info.name}]"
        if info.lineage:
            t = self.schema.tables.get(info.lineage[0])
            c = t.columns.get(info.lineage[1]) if t else None
            if t and c:
                return f"{t.name}[{c.name}]"
        return "[Value]"

    def measure_of(self, name):
        return self.query_measures.get(key(name)) or self.schema.measure(name)

    def _relationships(self):
        if self._incoming is None:
            incoming = {}
            for rel in self.schema.relationships:
                ft, fc, tt, tc = key(rel.from_table), key(rel.from_column), key(rel.to_table), key(rel.to_column)
                if ft not in self.schema.tables or tt not in self.schema.tables:
                    continue
                # Filtro del lado "uno" (to) hacia el lado "varios" (from)
                incoming.setdefault(ft, []).append((rel, fc, tt, tc))
                if rel.both:
                    incoming.setdefault(tt, []).append((rel, tc, ft, fc))
            self._incoming = incoming
        return self._incoming

    @staticmethod
    def rel_active(rel, ctx):
        if rel.rid in ctx.rel_on:
            return True
        return rel.active and rel.rid not in ctx.rel_off

    def expanded_tables(self, tkey):
        """Tablas alcanzables siguiendo relaciones muchos-a-uno (tabla expandida)."""
        seen, todo = {tkey}, [tkey]
        while todo:
            current = todo.pop()
            for rel in self.schema.relationships:
                if key(rel.from_table) == current and rel.to_card.lower() == "one":
                    target = key(rel.to_table)
                    if target not in seen:
                        seen.add(target)
                        todo.append(target)
        return seen

    # ======================================================================
    # Filas visibles
    # ======================================================================
    def all_rowids(self, tkey):
        return range(self.rt.store(tkey).rowcount)

    def visible_rowids(self, tkey, ctx):
        cache_key = ("vis", tkey)
        if cache_key not in ctx.cache:
            result = self._visible(tkey, ctx, frozenset([tkey]))
            ctx.cache[cache_key] = result if result is not None else list(self.all_rowids(tkey))
        return ctx.cache[cache_key]

    def _direct_filters(self, tkey, ctx):
        return [f for f in ctx.filters if tkey in f.tables()]

    def _affected(self, tkey, ctx, path):
        memo_key = ("aff", tkey, path)
        if memo_key in ctx.cache:
            return ctx.cache[memo_key]
        ctx.cache[memo_key] = False
        result = bool(self._direct_filters(tkey, ctx))
        if not result:
            for rel, _, other, _ in self._relationships().get(tkey, []):
                if other in path or not self.rel_active(rel, ctx):
                    continue
                if self._affected(other, ctx, path | {tkey}):
                    result = True
                    break
        ctx.cache[memo_key] = result
        return result

    def _visible(self, tkey, ctx, path):
        """Lista de rowids visibles, o None si la tabla no está filtrada."""
        memo_key = ("visp", tkey, path)
        if memo_key in ctx.cache:
            return ctx.cache[memo_key]
        store = self.rt.store(tkey)
        ids = None
        for flt in self._direct_filters(tkey, ctx):
            idx = [i for i, (t, _) in enumerate(flt.cols) if t == tkey]
            cols = [flt.cols[i][1] for i in idx]
            keys = flt.keys if len(idx) == len(flt.cols) else {tuple(k[i] for i in idx) for k in flt.keys}
            if len(cols) == 1:
                ids = self._select(store, cols[0], {k[0] for k in keys}, ids)
            else:
                source = ids if ids is not None else range(store.rowcount)
                ids = [i for i in source
                       if tuple(i if c == ROWID else vkey(store.value(i, c)) for c in cols) in keys]
        for rel, my_col, other, other_col in self._relationships().get(tkey, []):
            if other in path or not self.rel_active(rel, ctx):
                continue
            if not self._affected(other, ctx, path | {tkey}):
                continue
            other_ids = self._visible(other, ctx, path | {tkey})
            if other_ids is None:
                continue
            other_store = self.rt.store(other)
            column = other_store.column(other_col)
            allowed = {vkey(column[i]) for i in other_ids}
            ids = self._select(store, my_col, allowed, ids)
        ctx.cache[memo_key] = ids
        return ids

    @staticmethod
    def _select(store, ckey, allowed, ids):
        """Filas (de ids, o de toda la tabla si ids es None) cuyo valor de ckey está en allowed."""
        if ckey == ROWID:
            if ids is None:
                return sorted(i for i in allowed if isinstance(i, int) and 0 <= i < store.rowcount)
            return [i for i in ids if i in allowed]
        if ids is None or len(ids) > 4 * len(allowed):
            index = store.index(ckey)
            found = []
            for k in allowed:
                found.extend(index.get(k, ()))
            if ids is None:
                return sorted(found)
            current = set(ids)
            return sorted(i for i in found if i in current)
        column = store.column(ckey)
        return [i for i in ids if vkey(column[i]) in allowed]

    def column_values(self, tkey, ckey, ctx, distinct=False):
        column = self.rt.store(tkey).column(ckey)
        values = [column[i] for i in self.visible_rowids(tkey, ctx)]
        if not distinct:
            return values
        seen, out = set(), []
        for value in values:
            k = vkey(value)
            if k not in seen:
                seen.add(k)
                out.append(value)
        return out

    def all_distinct(self, lineages):
        tkey = lineages[0][0]
        store = self.rt.store(tkey)
        columns = [list(range(store.rowcount)) if c == ROWID else store.column(c) for _, c in lineages]
        seen, out = set(), []
        for i in range(store.rowcount):
            values = tuple(col[i] for col in columns)
            k = tuple(vkey(v) for v in values)
            if k not in seen:
                seen.add(k)
                out.append(values)
        return out

    # ======================================================================
    # Modificación de contexto
    # ======================================================================
    def add_filter(self, ctx, flt, keep=False):
        if keep:
            return ctx.copy(filters=ctx.filters + (flt,))
        new_cols = set(flt.cols)
        new_tables_rowid = {t for t, c in flt.cols if c == ROWID}
        kept = []
        for existing in ctx.filters:
            overlap = bool(new_cols & set(existing.cols))
            if not overlap and new_tables_rowid:
                overlap = bool(existing.tables() & new_tables_rowid)
            if not overlap:
                rowid_tables = {t for t, c in existing.cols if c == ROWID}
                overlap = bool(rowid_tables & flt.tables())
            if not overlap:
                kept.append(existing)
        return ctx.copy(filters=tuple(kept) + (flt,))

    def remove_filters(self, ctx, lineages=None, tables=None, except_cols=None):
        kept = []
        for flt in ctx.filters:
            remove = False
            if lineages is None and tables is None:
                remove = True
            else:
                if lineages and set(flt.cols) & set(lineages):
                    remove = True
                if tables and flt.tables() & tables:
                    remove = True
                if remove and except_cols and set(flt.cols) <= set(except_cols):
                    remove = False
            if not remove:
                kept.append(flt)
        return ctx.copy(filters=tuple(kept))

    def transition(self, ctx):
        """Transición de contexto: las filas iteradas pasan a ser filtros."""
        if not ctx.rows:
            return ctx
        new = ctx
        for row in ctx.rows:
            if row.table is not None:
                new = self.add_filter(new, Filter([(row.table, ROWID)], [(row.rowid,)]))
            for lineage, value in row.values.items():
                new = self.add_filter(new, Filter([lineage], [(vkey(value),)]))
        return new.copy(rows=())

    # ======================================================================
    # Escalares
    # ======================================================================
    def scalar(self, node, ctx):
        if isinstance(node, Num):
            return node.value
        if isinstance(node, Str):
            return node.value
        if isinstance(node, ColRef):
            return self.colref_value(node, ctx)
        if isinstance(node, BinOp):
            return self.binop(node, ctx)
        if isinstance(node, Unary):
            if node.op == "NOT":
                return not to_bool(self.scalar(node.expr, ctx), node.pos)
            value = self.scalar(node.expr, ctx)
            if value is None:
                return None
            number = to_number(value, node.pos)
            return -number if node.op == "-" else number
        if isinstance(node, InOp):
            return self.in_op(node, ctx)
        if isinstance(node, Call):
            handler = getattr(self, "fn_" + node.name.replace(".", "_"), None)
            if handler:
                return handler(node, ctx)
            if getattr(self, "tf_" + node.name.replace(".", "_"), None):
                return self.table_to_scalar(self.table(node, ctx), node.pos)
            self._unknown_function(node)
        if isinstance(node, VarBlock):
            return self.scalar(node.body, self.bind_vars(node, ctx))
        if isinstance(node, Ident):
            if node.name.casefold() in ctx.vars:
                value = ctx.vars[node.name.casefold()]
                if isinstance(value, TableVal):
                    return self.table_to_scalar(value, node.pos)
                return value
            if node.name.upper() in ("TRUE", "FALSE"):
                return node.name.upper() == "TRUE"
            if self.schema.table(node.name):
                return self.table_to_scalar(self.table(node, ctx), node.pos)
            raise DaxError(f"Failed to resolve name '{node.name}'. It is not a valid table, variable, "
                           f"or function name.", "name", node.pos)
        if isinstance(node, (TableCtor, TableRef)):
            return self.table_to_scalar(self.table(node, ctx), node.pos)
        raise DaxUnsupported(f"nodo no soportado: {type(node).__name__}")

    def _unknown_function(self, node):
        if node.name in KNOWN_UNSUPPORTED:
            raise DaxUnsupported(f"la función {node.name} no está implementada en el simulador", node.pos)
        raise DaxError(f"Failed to resolve name '{node.name}'. It is not a valid table, variable, or "
                       f"function name.", "name", node.pos)

    def bind_vars(self, node, ctx):
        variables = dict(ctx.vars)
        for name, expr in node.vars:
            inner = ctx.copy(vars=dict(variables))
            if self.is_table_expr(expr, inner):
                variables[name.casefold()] = self.table(expr, inner)
            else:
                variables[name.casefold()] = self.scalar(expr, inner)
        return ctx.copy(vars=variables)

    def is_table_expr(self, node, ctx):
        if isinstance(node, (TableCtor, TableRef)):
            return True
        if isinstance(node, Ident):
            value = ctx.vars.get(node.name.casefold())
            if value is not None:
                return isinstance(value, TableVal)
            return self.schema.table(node.name) is not None
        if isinstance(node, Call):
            name = node.name.replace(".", "_")
            return hasattr(self, "tf_" + name) and not hasattr(self, "fn_" + name)
        if isinstance(node, VarBlock):
            return self.is_table_expr(node.body, ctx)
        return False

    def table_to_scalar(self, table, pos=None):
        if len(table.cols) != 1 and len(table) > 0:
            raise DaxError("The expression refers to multiple columns. Multiple columns cannot be "
                           "converted to a scalar value.", "value", pos)
        rows = table.rows
        if not rows:
            return None
        if len(rows) > 1:
            raise DaxError("A table of multiple values was supplied where a single value was expected.",
                           "value", pos)
        return rows[0][0]

    def colref_value(self, node, ctx):
        if node.table is None:
            name = node.column.casefold()
            for row in reversed(ctx.rows):
                if name in row.names:
                    return row.names[name]
            measure = self.measure_of(node.column)
            if measure is not None:
                return self.eval_measure(measure, ctx, node.pos)
            for row in reversed(ctx.rows):
                if row.table is not None:
                    col = self.schema.tables[row.table].columns.get(key(node.column))
                    if col is not None:
                        return self.rt.store(row.table).value(row.rowid, key(col.name))
                for (t, c), value in row.values.items():
                    if c == key(node.column):
                        return value
            raise DaxError(f"The value for '{node.column}' cannot be determined. Either the column doesn't "
                           f"exist, or there is no current row for this column.", "name", node.pos)
        tkey, ckey = self.lineage_of(node)
        for row in reversed(ctx.rows):
            if row.table == tkey:
                return self.rt.store(tkey).value(row.rowid, ckey)
            if (tkey, ckey) in row.values:
                return row.values[(tkey, ckey)]
        t = self.schema.tables[tkey]
        c = t.columns[ckey]
        raise DaxError(f"A single value for column '{c.name}' in table '{t.name}' cannot be determined. "
                       f"This can happen when a measure formula refers to a column that contains many "
                       f"values without specifying an aggregation such as min, max, count, or sum to get "
                       f"a single result.", "value", node.pos)

    # ---------- medidas ----------
    def eval_measure(self, measure, ctx, pos=None):
        ctx = self.transition(ctx) if ctx.rows else ctx
        ctx = ctx.copy(rows=(), vars={})
        memo_key = (key(measure.name), ctx.signature())
        if memo_key in self.memo:
            return self.memo[memo_key]
        if key(measure.name) in self.stack:
            raise DaxError(f"A circular dependency was detected: {measure.name}.", "value", pos)
        self.stack.append(key(measure.name))
        query_defined = key(measure.name) in self.query_measures
        try:
            if query_defined:
                tree = self.query_trees[key(measure.name)]
            else:
                tree = self.rt.parsed(("measure", measure.table, measure.name), measure.expression)
            value = self.scalar(tree, ctx)
            if isinstance(value, TableVal):
                value = self.table_to_scalar(value, pos)
        except DaxError as exc:
            if query_defined:
                raise
            value = self.rt.approximate_measure(self, measure, ctx, exc)
        except (ArithmeticError, TypeError, ValueError, AttributeError, IndexError, KeyError) as exc:
            # Fallo interno del simulador evaluando una medida del modelo: valor de respaldo.
            if query_defined:
                raise DaxUnsupported(f"[sim] error interno: {type(exc).__name__}: {exc}", pos)
            value = self.rt.approximate_measure(
                self, measure, ctx, DaxUnsupported(f"[sim] error interno: {type(exc).__name__}: {exc}"))
        finally:
            self.stack.pop()
        self.memo[memo_key] = value
        return value

    # ---------- operadores ----------
    def binop(self, node, ctx):
        op = node.op
        if op == "&&":
            return to_bool(self.scalar(node.left, ctx), node.pos) and to_bool(self.scalar(node.right, ctx), node.pos)
        if op == "||":
            return to_bool(self.scalar(node.left, ctx), node.pos) or to_bool(self.scalar(node.right, ctx), node.pos)
        left = self.scalar(node.left, ctx)
        right = self.scalar(node.right, ctx)
        if op in ("=", "==", "<>", "<", ">", "<=", ">="):
            return self.compare(op, left, right, node)
        if op == "&":
            return to_text(left) + to_text(right)
        return self.arith(op, left, right, node.pos)

    def arith(self, op, left, right, pos=None):
        if left is None and right is None:
            return None
        if op in ("+", "-"):
            if isinstance(left, dt.datetime) and not isinstance(right, dt.datetime):
                days = _num(to_number(right, pos))
                return left + dt.timedelta(days=days) if op == "+" else left - dt.timedelta(days=days)
            if isinstance(right, dt.datetime) and op == "+" and not isinstance(left, dt.datetime):
                return right + dt.timedelta(days=_num(to_number(left, pos)))
            if isinstance(left, dt.datetime) and isinstance(right, dt.datetime):
                return serial(left) - serial(right)
            a, b = to_number(left, pos), to_number(right, pos)
            if isinstance(a, Decimal) and isinstance(b, Decimal):
                return a + b if op == "+" else a - b
            a, b = _num(a), _num(b)
            return a + b if op == "+" else a - b
        if op == "*":
            if left is None or right is None:
                return None
            a, b = to_number(left, pos), to_number(right, pos)
            if isinstance(a, Decimal) and isinstance(b, Decimal):
                return a * b
            return _num(a) * _num(b)
        if op == "/":
            if left is None:
                return None
            a, b = _num(to_number(left, pos)), _num(to_number(right, pos))
            if b == 0:
                if a == 0:
                    return float("nan")
                return float("inf") if a > 0 else float("-inf")
            return a / b
        if op == "^":
            if left is None or right is None:
                return None
            return _num(to_number(left, pos)) ** _num(to_number(right, pos))
        raise DaxUnsupported(f"operador {op}", pos)

    def compare(self, op, left, right, node=None):
        pos = node.pos if node is not None else None
        if left is None and right is None:
            return op in ("=", "==", "<=", ">=")
        if op == "==" and (left is None) != (right is None):
            return False
        if left is None:
            left = self._blank_like(right)
        if right is None:
            right = self._blank_like(left)
        lt, rt_ = type_label(left), type_label(right)
        numeric = ("Integer", "Number", "Currency")
        if (lt == "Text") != (rt_ == "Text") or (lt == "True/False") != (rt_ == "True/False"):
            raise DaxError(f"DAX comparison operations do not support comparing values of type {lt} with "
                           f"values of type {rt_}. Consider using the VALUE or FORMAT function to convert "
                           f"one of the values.", "type", pos)
        if (lt == "Date") != (rt_ == "Date"):
            self._mismatch(node, left, right)
            left = serial(left) if isinstance(left, dt.datetime) else left
            right = serial(right) if isinstance(right, dt.datetime) else right
        if isinstance(left, str):
            a, b = left.casefold(), right.casefold()
        elif lt in numeric or isinstance(left, bool):
            a, b = _num(left), _num(right)
        else:
            a, b = left, right
        if op in ("=", "=="):
            return a == b
        if op == "<>":
            return a != b
        if op == "<":
            return a < b
        if op == ">":
            return a > b
        if op == "<=":
            return a <= b
        return a >= b

    @staticmethod
    def _blank_like(other):
        if isinstance(other, str):
            return ""
        if isinstance(other, bool):
            return False
        if isinstance(other, dt.datetime):
            return EPOCH
        return 0

    def _mismatch(self, node, left, right):
        column = None
        if node is not None:
            for side in (node.left, node.right):
                if isinstance(side, ColRef) and side.table:
                    column = f"{side.table}[{side.column}]"
                    break
                if isinstance(side, Call) and side.args and isinstance(side.args[0], ColRef):
                    column = f"{side.args[0].table}[{side.args[0].column}]"
        self.rt.warn_mismatch(
            f"TYPE MISMATCH: comparación de {type_label(left)} con {type_label(right)}"
            + (f" en {column}" if column else "")
            + " -> en Power BI real la fecha se compara como número de serie y el filtro no devuelve filas",
            column)

    def in_op(self, node, ctx):
        value = self.scalar(node.expr, ctx) if not isinstance(node.expr, TableCtor) else None
        if isinstance(node.expr, TableCtor):
            needle = tuple(self.scalar(e, ctx) for e in node.expr.rows[0])
        else:
            needle = (value,)
        table = self.table(node.target, ctx)
        for row in table.rows:
            if len(row) != len(needle):
                raise DaxError("The number of columns in the IN operator does not match.", "value", node.pos)
            if all(self.compare("=", a, b, None) for a, b in zip(needle, row)):
                return True
        return False

    # ======================================================================
    # Tablas
    # ======================================================================
    def table(self, node, ctx):
        if isinstance(node, TableRef):
            return self.model_table(node.name, ctx, node.pos)
        if isinstance(node, Ident):
            value = ctx.vars.get(node.name.casefold())
            if value is not None:
                if isinstance(value, TableVal):
                    return value
                return TableVal([ColInfo("Value")], [(value,)])
            if self.schema.table(node.name):
                return self.model_table(node.name, ctx, node.pos)
            raise DaxError(f"Failed to resolve name '{node.name}'. It is not a valid table, variable, or "
                           f"function name.", "name", node.pos)
        if isinstance(node, TableCtor):
            rows = [tuple(self.scalar(e, ctx) for e in row) for row in node.rows]
            width = max((len(r) for r in rows), default=1)
            names = ["Value"] if width == 1 else [f"Value{i + 1}" for i in range(width)]
            return TableVal([ColInfo(n) for n in names], rows)
        if isinstance(node, Call):
            handler = getattr(self, "tf_" + node.name.replace(".", "_"), None)
            if handler:
                return handler(node, ctx)
            if getattr(self, "fn_" + node.name.replace(".", "_"), None):
                raise DaxError("The expression specified in the query is not a valid table expression.",
                               "value", node.pos)
            self._unknown_function(node)
        if isinstance(node, VarBlock):
            return self.table(node.body, self.bind_vars(node, ctx))
        if isinstance(node, ColRef) and node.table:
            # Referencia de columna donde se espera tabla (p. ej. KEEPFILTERS('T'[C])): todos sus valores.
            lineage = self.lineage_of(node)
            return TableVal([ColInfo(None, lineage)], self.all_distinct([lineage]))
        raise DaxError("The expression specified in the query is not a valid table expression.", "value",
                       getattr(node, "pos", None))

    def model_table(self, name, ctx, pos=None, all_rows=False):
        t = self.table_schema(name, pos)
        tkey = key(t.name)
        cols = [ColInfo(None, (tkey, key(c.name))) for c in t.visible_columns()]
        ids = list(self.all_rowids(tkey)) if all_rows else self.visible_rowids(tkey, ctx)
        return TableVal(cols, base=tkey, rowids=list(ids), runtime=self.rt)

    def iterate(self, table, ctx):
        for row in table.row_contexts():
            yield ctx.copy(rows=ctx.rows + (row,))

    # ======================================================================
    # Argumentos de filtro (CALCULATE / CALCULATETABLE / SUMMARIZECOLUMNS)
    # ======================================================================
    def filter_ops(self, node, ctx, keep=False):
        """Lista de operaciones: ("remove", ...), ("filter", Filter, keep), ("userel", ...)."""
        if node is None:
            return []
        if isinstance(node, Call):
            name = node.name
            if name == "KEEPFILTERS":
                return self.filter_ops(node.args[0], ctx, keep=True)
            if name in ("ALL", "REMOVEFILTERS", "ALLNOBLANKROW"):
                if not node.args:
                    return [("remove_all",)]
                lineages, tables = [], set()
                for arg in node.args:
                    if isinstance(arg, ColRef) and arg.table:
                        lineages.append(self.lineage_of(arg))
                    else:
                        tname = arg.name if isinstance(arg, (TableRef, Ident)) else None
                        if tname is None:
                            raise DaxUnsupported("ALL sobre expresión de tabla", node.pos)
                        t = self.table_schema(tname, arg.pos)
                        tables |= self.expanded_tables(key(t.name))
                return [("remove", lineages, tables, None)]
            if name == "ALLEXCEPT":
                t = self.table_schema(node.args[0].name if isinstance(node.args[0], (TableRef, Ident))
                                      else node.args[0].table, node.pos)
                keep_cols = [self.lineage_of(a) for a in node.args[1:] if isinstance(a, ColRef)]
                return [("remove", None, self.expanded_tables(key(t.name)), keep_cols)]
            if name == "ALLSELECTED":
                return [("allselected", [self.lineage_of(a) for a in node.args if isinstance(a, ColRef)])]
            if name == "USERELATIONSHIP":
                a, b = (self.lineage_of(x) for x in node.args[:2])
                for rel in self.schema.relationships:
                    pair = {(key(rel.from_table), key(rel.from_column)), (key(rel.to_table), key(rel.to_column))}
                    if pair == {a, b}:
                        return [("userel", rel)]
                raise DaxError("USERELATIONSHIP function can only use the two columns references "
                               "participating in relationship.", "value", node.pos)
            if name == "CROSSFILTER":
                self.rt.note_approx("CROSSFILTER ignorado por el simulador")
                return []
        if self._is_boolean_filter(node, ctx):
            return [("filter", self.boolean_filter(node, ctx), keep)]
        table = self.table(node, ctx)
        return [("filter", self.table_filter(table, node), keep)]

    def _is_boolean_filter(self, node, ctx):
        if isinstance(node, (BinOp, Unary, InOp)):
            return True
        if isinstance(node, Call) and not self.is_table_expr(node, ctx):
            return True
        return False

    def _filter_columns(self, node):
        found = []

        def visit(n):
            if n is None:
                return
            if isinstance(n, ColRef) and n.table:
                lineage = self.lineage_of(n)
                if lineage not in found:
                    found.append(lineage)
                return
            if isinstance(n, Call):
                if n.name in _AGGREGATING:
                    return
                for arg in n.args:
                    visit(arg)
            elif isinstance(n, BinOp):
                visit(n.left)
                visit(n.right)
            elif isinstance(n, Unary):
                visit(n.expr)
            elif isinstance(n, InOp):
                visit(n.expr)
                visit(n.target)
            elif isinstance(n, TableCtor):
                for row in n.rows:
                    for item in row:
                        visit(item)
        visit(node)
        return found

    def boolean_filter(self, node, ctx):
        cols = self._filter_columns(node)
        if not cols:
            raise DaxError("The expression contains columns from multiple tables, or no columns, but only "
                           "a single table can be used in a True/False expression that is used as a table "
                           "filter expression.", "value", getattr(node, "pos", None))
        if len({t for t, _ in cols}) > 1:
            raise DaxError("The expression contains multiple columns, but only a single column can be used "
                           "in a True/False expression that is used as a table filter expression.",
                           "value", getattr(node, "pos", None))
        keys = []
        base = ctx.copy(rows=())
        for values in self.all_distinct(cols):
            row = Row(values=dict(zip(cols, values)))
            if to_bool(self.scalar(node, base.copy(rows=(row,))), getattr(node, "pos", None)):
                keys.append(tuple(vkey(v) for v in values))
        return Filter(cols, keys)

    def table_filter(self, table, node=None):
        if table.base is not None and table._rows is None:
            return Filter([(table.base, ROWID)], [(i,) for i in table.rowids])
        idx = [i for i, c in enumerate(table.cols) if c.lineage]
        if not idx:
            raise DaxError("The filter expression of CALCULATE must reference model columns.", "value",
                           getattr(node, "pos", None))
        cols = [table.cols[i].lineage for i in idx]
        return Filter(cols, {tuple(vkey(r[i]) for i in idx) for r in table.rows})

    def apply_filter_args(self, args, ctx):
        """Semántica de CALCULATE para la lista de argumentos de filtro."""
        ops = []
        for arg in args:
            ops.extend(self.filter_ops(arg, ctx))
        new = self.transition(ctx) if ctx.rows else ctx
        for op in ops:
            if op[0] == "remove_all":
                new = new.copy(filters=())
            elif op[0] == "remove":
                _, lineages, tables, except_cols = op
                new = self.remove_filters(new, lineages=lineages or None, tables=tables or None,
                                          except_cols=except_cols)
            elif op[0] == "allselected":
                lineages = op[1]
                base = ctx.allselected
                if not lineages:
                    new = new.copy(filters=base.filters if base else ())
                else:
                    new = self.remove_filters(new, lineages=lineages)
                    if base:
                        for flt in base.filters:
                            if set(flt.cols) & set(lineages):
                                new = self.add_filter(new, flt)
            elif op[0] == "userel":
                rel = op[1]
                pair = {key(rel.from_table), key(rel.to_table)}
                off = {r.rid for r in self.schema.relationships
                       if r.rid != rel.rid and {key(r.from_table), key(r.to_table)} == pair}
                new = new.copy(rel_on=new.rel_on | {rel.rid}, rel_off=new.rel_off | off)
        for op in ops:
            if op[0] == "filter":
                new = self.add_filter(new, op[1], keep=op[2])
        return new.copy(rows=())

    # ======================================================================
    # Funciones: contexto
    # ======================================================================
    def fn_CALCULATE(self, node, ctx):
        if not node.args:
            raise DaxError("Too few arguments were passed to the CALCULATE function.", "syntax", node.pos)
        # Dentro de CALCULATE la fila iterada ya es filtro (transición de contexto).
        return self.scalar(node.args[0], self.apply_filter_args(node.args[1:], ctx))

    def tf_CALCULATETABLE(self, node, ctx):
        new = self.apply_filter_args(node.args[1:], ctx)
        return self.table(node.args[0], new.copy(rows=()))

    def fn_SELECTEDVALUE(self, node, ctx):
        values = self.distinct_column(node.args[0], ctx)
        if len(values) == 1:
            return values[0]
        return self.scalar(node.args[1], ctx) if len(node.args) > 1 and node.args[1] is not None else None

    def fn_HASONEVALUE(self, node, ctx):
        return len(self.distinct_column(node.args[0], ctx)) == 1

    def fn_HASONEFILTER(self, node, ctx):
        return self.fn_ISFILTERED(node, ctx) and self.fn_HASONEVALUE(node, ctx)

    def distinct_column(self, arg, ctx):
        if not (isinstance(arg, ColRef) and arg.table):
            table = self.table(arg, ctx)
            return list({vkey(r[0]): r[0] for r in table.rows}.values())
        tkey, ckey = self.lineage_of(arg)
        return self.column_values(tkey, ckey, ctx, distinct=True)

    @staticmethod
    def _unwrap_level(arg):
        return arg.args[0] if isinstance(arg, Call) and arg.name == "__HIERLEVEL" else arg

    def fn___HIERLEVEL(self, node, ctx):
        """Nivel de la jerarquía automática de fechas: Año, Trimestre, Mes, Día."""
        value = to_date(self.scalar(node.args[0], ctx), node.pos)
        if value is None:
            return None
        level = node.args[1].value.casefold()
        if level in ("año", "ano", "year"):
            return value.year
        if level in ("trimestre", "quarter"):
            return f"Trim. {(value.month - 1) // 3 + 1}"
        if level in ("mes", "month"):
            return MESES[value.month - 1]
        if level in ("día", "dia", "day"):
            return value.day
        raise DaxError(f"Column '{node.args[1].value}' cannot be found in the date hierarchy.", "name", node.pos)

    def fn_ISFILTERED(self, node, ctx):
        node = Call(node.name, [self._unwrap_level(node.args[0])], node.pos)
        arg = node.args[0]
        if isinstance(arg, ColRef) and arg.table:
            lineage = self.lineage_of(arg)
            return any(lineage in f.cols or (lineage[0], ROWID) in f.cols for f in ctx.filters)
        t = self.table_schema(arg.name, arg.pos)
        return any(key(t.name) in f.tables() for f in ctx.filters)

    def fn_ISCROSSFILTERED(self, node, ctx):
        arg = self._unwrap_level(node.args[0])
        tname = arg.table if isinstance(arg, ColRef) else arg.name
        t = self.table_schema(tname, arg.pos)
        return self._affected(key(t.name), ctx, frozenset())

    def fn_ISINSCOPE(self, node, ctx):
        return self.fn_ISFILTERED(node, ctx) and self.fn_HASONEVALUE(node, ctx)

    def fn_RELATED(self, node, ctx):
        arg = node.args[0]
        target = self.lineage_of(arg)
        for row in reversed(ctx.rows):
            if row.table is None:
                if target in row.values:
                    return row.values[target]
                continue
            if row.table == target[0]:
                return self.rt.store(row.table).value(row.rowid, target[1])
            path = self._many_to_one_path(row.table, target[0], ctx)
            if path is None:
                continue
            current_table, current_id = row.table, row.rowid
            for rel_from_col, to_table, to_col in path:
                value = self.rt.store(current_table).value(current_id, rel_from_col)
                ids = self.rt.store(to_table).index(to_col).get(vkey(value))
                if not ids:
                    return None
                current_table, current_id = to_table, ids[0]
            return self.rt.store(current_table).value(current_id, target[1])
        t = self.schema.tables[target[0]]
        raise DaxError(f"The column '{t.name}[{arg.column}]' either doesn't exist or doesn't have a "
                       f"relationship to any table available in the current context.", "value", node.pos)

    def _many_to_one_path(self, start, target, ctx):
        todo = [(start, [])]
        seen = {start}
        while todo:
            current, path = todo.pop(0)
            if current == target:
                return path
            for rel in self.schema.relationships:
                if not self.rel_active(rel, ctx):
                    continue
                ft, tt = key(rel.from_table), key(rel.to_table)
                if ft == current and rel.to_card.lower() == "one" and tt not in seen:
                    seen.add(tt)
                    todo.append((tt, path + [(key(rel.from_column), tt, key(rel.to_column))]))
                elif tt == current and rel.from_card.lower() == "one" and ft not in seen:
                    seen.add(ft)
                    todo.append((ft, path + [(key(rel.to_column), ft, key(rel.from_column))]))
        return None

    def tf_RELATEDTABLE(self, node, ctx):
        return self.table(node.args[0], self.transition(ctx))

    def fn_LOOKUPVALUE(self, node, ctx):
        result = self.lineage_of(node.args[0])
        pairs = node.args[1:]
        alternate = None
        if len(pairs) % 2 == 1:
            alternate = pairs[-1]
            pairs = pairs[:-1]
        store = self.rt.store(result[0])
        candidates = range(store.rowcount)
        for i in range(0, len(pairs), 2):
            col = self.lineage_of(pairs[i])
            wanted = vkey(self.scalar(pairs[i + 1], ctx))
            candidates = [r for r in candidates if vkey(store.value(r, col[1])) == wanted]
        values = {vkey(store.value(r, result[1])): store.value(r, result[1]) for r in candidates}
        if not values:
            return self.scalar(alternate, ctx) if alternate is not None else None
        if len(values) > 1:
            if alternate is not None:
                return self.scalar(alternate, ctx)
            raise DaxError("A table of multiple values was supplied where a single value was expected.",
                           "value", node.pos)
        return next(iter(values.values()))

    # ======================================================================
    # Funciones: agregaciones
    # ======================================================================
    def _agg_values(self, node, ctx):
        arg = node.args[0] if node.args else None
        if isinstance(arg, ColRef) and arg.table:
            tkey, ckey = self.lineage_of(arg)
            # Las agregaciones ignoran el contexto de fila (sin transición, como DAX).
            return self.column_values(tkey, ckey, ctx)
        if isinstance(arg, ColRef):
            raise DaxError(f"The {node.name} function only accepts a column reference as an argument.",
                           "value", node.pos)
        table = self.table(arg, ctx)
        return [r[0] for r in table.rows]

    @staticmethod
    def _sum(values):
        values = [v for v in values if v is not None]
        if not values:
            return None
        if all(isinstance(v, Decimal) for v in values):
            return sum(values, Decimal(0))
        if all(isinstance(v, int) and not isinstance(v, bool) for v in values):
            return sum(values)
        return float(sum(_num(to_number(v)) for v in values))

    def fn_SUM(self, node, ctx):
        return self._sum(self._agg_values(node, ctx))

    def fn_AVERAGE(self, node, ctx):
        values = [_num(to_number(v)) for v in self._agg_values(node, ctx) if v is not None and not isinstance(v, str)]
        return sum(values) / len(values) if values else None

    fn_AVERAGEA = fn_AVERAGE

    def fn_MEDIAN(self, node, ctx):
        values = sorted(_num(to_number(v)) for v in self._agg_values(node, ctx) if v is not None)
        if not values:
            return None
        mid = len(values) // 2
        return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2

    def _minmax(self, node, ctx, func):
        if len(node.args) >= 2:
            values = [self.scalar(a, ctx) for a in node.args[:2]]
            values = [v for v in values if v is not None]
            if not values:
                return None
            return func(values, key=sort_key)
        values = [v for v in self._agg_values(node, ctx) if v is not None]
        return func(values, key=sort_key) if values else None

    def fn_MIN(self, node, ctx):
        return self._minmax(node, ctx, min)

    def fn_MAX(self, node, ctx):
        return self._minmax(node, ctx, max)

    fn_MINA = fn_MIN
    fn_MAXA = fn_MAX

    def fn_COUNT(self, node, ctx):
        count = sum(1 for v in self._agg_values(node, ctx) if v is not None)
        return count or None

    fn_COUNTA = fn_COUNT

    def fn_COUNTBLANK(self, node, ctx):
        count = sum(1 for v in self._agg_values(node, ctx) if v is None or v == "")
        return count or None

    def fn_DISTINCTCOUNT(self, node, ctx):
        values = self._agg_values(node, ctx)
        return len({vkey(v) for v in values}) or None

    def fn_DISTINCTCOUNTNOBLANK(self, node, ctx):
        values = self._agg_values(node, ctx)
        return len({vkey(v) for v in values if v is not None}) or None

    def fn_COUNTROWS(self, node, ctx):
        if not node.args:
            raise DaxError("Too few arguments were passed to the COUNTROWS function.", "syntax", node.pos)
        table = self.table(node.args[0], ctx)
        return len(table) or None

    def fn_ISEMPTY(self, node, ctx):
        return len(self.table(node.args[0], ctx)) == 0

    # ---------- iteradores X ----------
    def _x_values(self, node, ctx):
        table = self.table(node.args[0], ctx)
        return [self.scalar(node.args[1], inner) for inner in self.iterate(table, ctx)]

    def fn_SUMX(self, node, ctx):
        return self._sum(self._x_values(node, ctx))

    def fn_AVERAGEX(self, node, ctx):
        values = [_num(to_number(v)) for v in self._x_values(node, ctx) if v is not None]
        return sum(values) / len(values) if values else None

    def fn_MEDIANX(self, node, ctx):
        values = sorted(_num(to_number(v)) for v in self._x_values(node, ctx) if v is not None)
        if not values:
            return None
        mid = len(values) // 2
        return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2

    def fn_MINX(self, node, ctx):
        values = [v for v in self._x_values(node, ctx) if v is not None]
        return min(values, key=sort_key) if values else None

    def fn_MAXX(self, node, ctx):
        values = [v for v in self._x_values(node, ctx) if v is not None]
        return max(values, key=sort_key) if values else None

    def fn_COUNTX(self, node, ctx):
        return sum(1 for v in self._x_values(node, ctx) if v is not None) or None

    fn_COUNTAX = fn_COUNTX

    def fn_CONCATENATEX(self, node, ctx):
        table = self.table(node.args[0], ctx)
        delimiter = to_text(self.scalar(node.args[2], ctx)) if len(node.args) > 2 and node.args[2] else ""
        items = []
        for inner in self.iterate(table, ctx):
            order = self.scalar(node.args[3], inner) if len(node.args) > 3 and node.args[3] else None
            items.append((sort_key(order), to_text(self.scalar(node.args[1], inner))))
        if len(node.args) > 3:
            desc = len(node.args) > 4 and isinstance(node.args[4], Ident) and node.args[4].name.upper() == "DESC"
            items.sort(key=lambda x: x[0], reverse=desc)
        return delimiter.join(text for _, text in items)

    def fn_RANKX(self, node, ctx):
        table = self.table(node.args[0], ctx.copy(rows=()))
        values = [self.scalar(node.args[1], inner) for inner in self.iterate(table, ctx.copy(rows=()))]
        if len(node.args) > 2 and node.args[2] is not None:
            current = self.scalar(node.args[2], ctx)
        else:
            current = self.scalar(node.args[1], ctx)
        if current is None:
            return None
        ascending = (len(node.args) > 3 and isinstance(node.args[3], Ident)
                     and node.args[3].name.upper() == "ASC")
        dense = len(node.args) > 4 and isinstance(node.args[4], Ident) and node.args[4].name.upper() == "DENSE"
        numbers = [_num(to_number(v)) for v in values if v is not None]
        cur = _num(to_number(current))
        if dense:
            better = {v for v in numbers if (v < cur if ascending else v > cur)}
            return len(better) + 1
        return sum(1 for v in numbers if (v < cur if ascending else v > cur)) + 1

    def fn_FIRSTNONBLANK(self, node, ctx):
        return self._nonblank(node, ctx, first=True)

    def fn_LASTNONBLANK(self, node, ctx):
        return self._nonblank(node, ctx, first=False)

    def _nonblank(self, node, ctx, first):
        table = self.table(node.args[0], ctx) if not isinstance(node.args[0], ColRef) else \
            self.tf_VALUES(Call("VALUES", [node.args[0]], node.pos), ctx)
        rows = sorted(table.rows, key=lambda r: sort_key(r[0]), reverse=not first)
        for values in rows:
            inner = ctx.copy(rows=ctx.rows + (table.row_from_tuple(values),))
            if self.scalar(node.args[1], inner) is not None:
                return values[0]
        return None

    # ======================================================================
    # Funciones: lógicas e información
    # ======================================================================
    def fn_IF(self, node, ctx):
        cond = to_bool(self.scalar(node.args[0], ctx), node.pos)
        if cond:
            return self.scalar(node.args[1], ctx) if len(node.args) > 1 else None
        return self.scalar(node.args[2], ctx) if len(node.args) > 2 and node.args[2] is not None else None

    fn_IF_EAGER = fn_IF

    def fn_SWITCH(self, node, ctx):
        value = self.scalar(node.args[0], ctx)
        args = node.args[1:]
        for i in range(0, len(args) - 1, 2):
            candidate = self.scalar(args[i], ctx)
            if value is True or value is False:
                if to_bool(candidate) == value:
                    return self.scalar(args[i + 1], ctx)
            elif vkey(candidate) == vkey(value) or (candidate is None and value is None):
                return self.scalar(args[i + 1], ctx)
        if len(args) % 2 == 1:
            return self.scalar(args[-1], ctx)
        return None

    def fn_AND(self, node, ctx):
        return to_bool(self.scalar(node.args[0], ctx)) and to_bool(self.scalar(node.args[1], ctx))

    def fn_OR(self, node, ctx):
        return to_bool(self.scalar(node.args[0], ctx)) or to_bool(self.scalar(node.args[1], ctx))

    def fn_NOT(self, node, ctx):
        return not to_bool(self.scalar(node.args[0], ctx))

    def fn_TRUE(self, node, ctx):
        return True

    def fn_FALSE(self, node, ctx):
        return False

    def fn_BLANK(self, node, ctx):
        return None

    def fn_ISBLANK(self, node, ctx):
        return self.scalar(node.args[0], ctx) is None

    def fn_ISNUMBER(self, node, ctx):
        value = self.scalar(node.args[0], ctx)
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)

    def fn_ISTEXT(self, node, ctx):
        return isinstance(self.scalar(node.args[0], ctx), str)

    def fn_ISNONTEXT(self, node, ctx):
        return not self.fn_ISTEXT(node, ctx)

    def fn_ISLOGICAL(self, node, ctx):
        return isinstance(self.scalar(node.args[0], ctx), bool)

    def fn_ISERROR(self, node, ctx):
        try:
            self.scalar(node.args[0], ctx)
            return False
        except DaxUnsupported:
            raise
        except DaxError:
            return True

    def fn_IFERROR(self, node, ctx):
        try:
            return self.scalar(node.args[0], ctx)
        except DaxUnsupported:
            raise
        except DaxError:
            return self.scalar(node.args[1], ctx)

    def fn_COALESCE(self, node, ctx):
        for arg in node.args:
            value = self.scalar(arg, ctx)
            if value is not None:
                return value
        return None

    def fn_USERNAME(self, node, ctx):
        return "SIMULADO\\usuario"

    def fn_USERPRINCIPALNAME(self, node, ctx):
        return "usuario@simulado.local"

    fn_USEROBJECTID = fn_USERPRINCIPALNAME

    # ======================================================================
    # Funciones: matemáticas
    # ======================================================================
    def _n(self, node, ctx, index, default=None):
        if index >= len(node.args) or node.args[index] is None:
            return default
        value = self.scalar(node.args[index], ctx)
        return None if value is None else _num(to_number(value, node.pos))

    def fn_DIVIDE(self, node, ctx):
        num = self.scalar(node.args[0], ctx)
        den = self.scalar(node.args[1], ctx)
        alternate = self.scalar(node.args[2], ctx) if len(node.args) > 2 and node.args[2] is not None else None
        if den is None or _num(to_number(den)) == 0:
            return alternate
        if num is None:
            return None
        return _num(to_number(num)) / _num(to_number(den))

    def fn_ABS(self, node, ctx):
        v = self._n(node, ctx, 0)
        return None if v is None else abs(v)

    def fn_INT(self, node, ctx):
        v = self._n(node, ctx, 0)
        return None if v is None else int(math.floor(v))

    def fn_TRUNC(self, node, ctx):
        v = self._n(node, ctx, 0)
        digits = int(self._n(node, ctx, 1, 0) or 0)
        if v is None:
            return None
        factor = 10 ** digits
        return math.trunc(v * factor) / factor if digits else math.trunc(v)

    def fn_ROUND(self, node, ctx):
        v = self._n(node, ctx, 0)
        digits = int(self._n(node, ctx, 1, 0) or 0)
        if v is None:
            return None
        result = float(Decimal(str(v)).quantize(Decimal(1).scaleb(-digits), rounding="ROUND_HALF_UP")) \
            if not math.isinf(v) and not math.isnan(v) else v
        return int(result) if digits <= 0 and not math.isinf(result) and not math.isnan(result) else result

    def fn_ROUNDUP(self, node, ctx):
        v = self._n(node, ctx, 0)
        digits = int(self._n(node, ctx, 1, 0) or 0)
        if v is None:
            return None
        factor = 10 ** digits
        return math.copysign(math.ceil(abs(v) * factor) / factor, v)

    def fn_ROUNDDOWN(self, node, ctx):
        v = self._n(node, ctx, 0)
        digits = int(self._n(node, ctx, 1, 0) or 0)
        if v is None:
            return None
        factor = 10 ** digits
        return math.copysign(math.floor(abs(v) * factor) / factor, v)

    def fn_MOD(self, node, ctx):
        a, b = self._n(node, ctx, 0), self._n(node, ctx, 1)
        if b == 0:
            raise DaxError("An argument of function 'MOD' has the wrong data type or the result is too large "
                           "or too small.", "value", node.pos)
        return None if a is None or b is None else a - b * math.floor(a / b)

    def fn_POWER(self, node, ctx):
        return self._n(node, ctx, 0) ** self._n(node, ctx, 1)

    def fn_SQRT(self, node, ctx):
        return math.sqrt(self._n(node, ctx, 0))

    def fn_SIGN(self, node, ctx):
        v = self._n(node, ctx, 0) or 0
        return (v > 0) - (v < 0)

    def fn_CEILING(self, node, ctx):
        v, s = self._n(node, ctx, 0), self._n(node, ctx, 1, 1) or 1
        return None if v is None else math.ceil(v / s) * s

    def fn_FLOOR(self, node, ctx):
        v, s = self._n(node, ctx, 0), self._n(node, ctx, 1, 1) or 1
        return None if v is None else math.floor(v / s) * s

    def fn_EXP(self, node, ctx):
        return math.exp(self._n(node, ctx, 0))

    def fn_LN(self, node, ctx):
        return math.log(self._n(node, ctx, 0))

    def fn_LOG10(self, node, ctx):
        return math.log10(self._n(node, ctx, 0))

    def fn_PI(self, node, ctx):
        return math.pi

    def fn_VALUE(self, node, ctx):
        value = self.scalar(node.args[0], ctx)
        return None if value is None else to_number(value, node.pos)

    def fn_CURRENCY(self, node, ctx):
        value = self.scalar(node.args[0], ctx)
        return None if value is None else Decimal(str(round(_num(to_number(value)), 4)))

    def fn_CONVERT(self, node, ctx):
        value = self.scalar(node.args[0], ctx)
        kind = node.args[1].name.upper() if isinstance(node.args[1], Ident) else "STRING"
        if value is None:
            return None
        if kind in ("INTEGER", "INT64"):
            return int(to_number(value))
        if kind in ("DOUBLE", "DECIMAL"):
            return float(_num(to_number(value)))
        if kind == "CURRENCY":
            return Decimal(str(_num(to_number(value))))
        if kind == "STRING":
            return to_text(value)
        if kind == "DATETIME":
            return to_date(value)
        if kind == "BOOLEAN":
            return to_bool(value)
        return value

    # ======================================================================
    # Funciones: texto
    # ======================================================================
    def _t(self, node, ctx, index, default=""):
        if index >= len(node.args) or node.args[index] is None:
            return default
        return to_text(self.scalar(node.args[index], ctx))

    def fn_CONCATENATE(self, node, ctx):
        return self._t(node, ctx, 0) + self._t(node, ctx, 1)

    def fn_COMBINEVALUES(self, node, ctx):
        delimiter = self._t(node, ctx, 0)
        return delimiter.join(self._t(node, ctx, i) for i in range(1, len(node.args)))

    def fn_LEFT(self, node, ctx):
        return self._t(node, ctx, 0)[:int(self._n(node, ctx, 1, 1) or 0)]

    def fn_RIGHT(self, node, ctx):
        n = int(self._n(node, ctx, 1, 1) or 0)
        text = self._t(node, ctx, 0)
        return text[-n:] if n else ""

    def fn_MID(self, node, ctx):
        start = int(self._n(node, ctx, 1, 1) or 0)
        return self._t(node, ctx, 0)[start - 1:start - 1 + int(self._n(node, ctx, 2, 0) or 0)]

    def fn_LEN(self, node, ctx):
        return len(self._t(node, ctx, 0))

    def fn_UPPER(self, node, ctx):
        return self._t(node, ctx, 0).upper()

    def fn_LOWER(self, node, ctx):
        return self._t(node, ctx, 0).lower()

    def fn_TRIM(self, node, ctx):
        return re.sub(r" +", " ", self._t(node, ctx, 0).strip())

    def fn_SUBSTITUTE(self, node, ctx):
        return self._t(node, ctx, 0).replace(self._t(node, ctx, 1), self._t(node, ctx, 2))

    def fn_REPLACE(self, node, ctx):
        text = self._t(node, ctx, 0)
        start, length = int(self._n(node, ctx, 1, 1) or 0), int(self._n(node, ctx, 2, 0) or 0)
        return text[:start - 1] + self._t(node, ctx, 3) + text[start - 1 + length:]

    def fn_REPT(self, node, ctx):
        return self._t(node, ctx, 0) * int(self._n(node, ctx, 1, 0) or 0)

    def fn_EXACT(self, node, ctx):
        return self._t(node, ctx, 0) == self._t(node, ctx, 1)

    def fn_UNICHAR(self, node, ctx):
        return chr(int(self._n(node, ctx, 0)))

    def _search(self, node, ctx, case_sensitive):
        find = self._t(node, ctx, 0)
        within = self._t(node, ctx, 1)
        start = int(self._n(node, ctx, 2, 1) or 1)
        haystack, needle = (within, find) if case_sensitive else (within.casefold(), find.casefold())
        index = haystack.find(needle, start - 1)
        if index >= 0:
            return index + 1
        if len(node.args) > 3:
            return self.scalar(node.args[3], ctx)
        raise DaxError(f"The search Text provided to function '{'FIND' if case_sensitive else 'SEARCH'}' "
                       f"could not be found in the given text.", "value", node.pos)

    def fn_SEARCH(self, node, ctx):
        return self._search(node, ctx, False)

    def fn_FIND(self, node, ctx):
        return self._search(node, ctx, True)

    def fn_CONTAINSSTRING(self, node, ctx):
        return self._t(node, ctx, 1).casefold() in self._t(node, ctx, 0).casefold()

    def fn_CONTAINSSTRINGEXACT(self, node, ctx):
        return self._t(node, ctx, 1) in self._t(node, ctx, 0)

    def fn_FORMAT(self, node, ctx):
        value = self.scalar(node.args[0], ctx)
        fmt = self._t(node, ctx, 1)
        return format_value(value, fmt)

    def fn_FIXED(self, node, ctx):
        return format_value(self.scalar(node.args[0], ctx), "#,##0." + "0" * int(self._n(node, ctx, 1, 2) or 0))

    # ======================================================================
    # Funciones: fechas
    # ======================================================================
    def _d(self, node, ctx, index):
        if index >= len(node.args) or node.args[index] is None:
            return None
        return to_date(self.scalar(node.args[index], ctx), node.pos)

    def fn_DATE(self, node, ctx):
        y, m, d = (int(self._n(node, ctx, i, 0) or 0) for i in range(3))
        if not 1 <= y + (m - 1) // 12 <= 9999:
            raise DaxError("An argument of function 'DATE' has the wrong data type or the result is too "
                           "large or too small.", "value", node.pos)
        base = dt.datetime(y + (m - 1) // 12, (m - 1) % 12 + 1, 1)
        return base + dt.timedelta(days=d - 1)

    def fn_TIME(self, node, ctx):
        h, m, s = (int(self._n(node, ctx, i, 0) or 0) for i in range(3))
        return EPOCH + dt.timedelta(hours=h, minutes=m, seconds=s)

    def fn_DATEVALUE(self, node, ctx):
        return to_date(self._t(node, ctx, 0), node.pos)

    def fn_TODAY(self, node, ctx):
        return self.rt.today

    def fn_UTCTODAY(self, node, ctx):
        return self.rt.today

    def fn_NOW(self, node, ctx):
        return self.rt.today + dt.timedelta(hours=8)

    fn_UTCNOW = fn_NOW

    def fn_YEAR(self, node, ctx):
        d = self._d(node, ctx, 0)
        return None if d is None else d.year

    def fn_MONTH(self, node, ctx):
        d = self._d(node, ctx, 0)
        return None if d is None else d.month

    def fn_DAY(self, node, ctx):
        d = self._d(node, ctx, 0)
        return None if d is None else d.day

    def fn_QUARTER(self, node, ctx):
        d = self._d(node, ctx, 0)
        return None if d is None else (d.month - 1) // 3 + 1

    def fn_HOUR(self, node, ctx):
        d = self._d(node, ctx, 0)
        return None if d is None else d.hour

    def fn_MINUTE(self, node, ctx):
        d = self._d(node, ctx, 0)
        return None if d is None else d.minute

    def fn_SECOND(self, node, ctx):
        d = self._d(node, ctx, 0)
        return None if d is None else d.second

    def fn_WEEKDAY(self, node, ctx):
        d = self._d(node, ctx, 0)
        kind = int(self._n(node, ctx, 1, 1) or 1)
        if d is None:
            return None
        iso = d.isoweekday()  # lunes=1
        if kind == 2:
            return iso
        if kind == 3:
            return iso - 1
        return iso % 7 + 1

    def fn_WEEKNUM(self, node, ctx):
        d = self._d(node, ctx, 0)
        return None if d is None else int(d.strftime("%U")) + 1

    def fn_EOMONTH(self, node, ctx):
        d = self._d(node, ctx, 0)
        if d is None:
            return None
        target = add_months(d.replace(day=1), int(self._n(node, ctx, 1, 0) or 0))
        last = calendar.monthrange(target.year, target.month)[1]
        return dt.datetime(target.year, target.month, last)

    def fn_EDATE(self, node, ctx):
        d = self._d(node, ctx, 0)
        return None if d is None else add_months(d, int(self._n(node, ctx, 1, 0) or 0))

    def fn_DATEDIFF(self, node, ctx):
        a, b = self._d(node, ctx, 0), self._d(node, ctx, 1)
        unit = node.args[2].name.upper() if isinstance(node.args[2], Ident) else "DAY"
        if a is None or b is None:
            return None
        if unit == "YEAR":
            return b.year - a.year
        if unit == "QUARTER":
            return (b.year - a.year) * 4 + (b.month - 1) // 3 - (a.month - 1) // 3
        if unit == "MONTH":
            return (b.year - a.year) * 12 + b.month - a.month
        if unit == "WEEK":
            return (b.date() - a.date()).days // 7
        if unit == "DAY":
            return (b.date() - a.date()).days
        seconds = (b - a).total_seconds()
        if unit == "HOUR":
            return int((b.replace(minute=0, second=0, microsecond=0)
                        - a.replace(minute=0, second=0, microsecond=0)).total_seconds() // 3600)
        if unit == "MINUTE":
            return int((b.replace(second=0, microsecond=0) - a.replace(second=0, microsecond=0)).total_seconds() // 60)
        return int(seconds)

    # ---------- inteligencia de tiempo ----------
    def _dates(self, arg, ctx):
        """(linaje, fechas visibles) del argumento de fechas."""
        if isinstance(arg, ColRef) and arg.table:
            lineage = self.lineage_of(arg)
            c = self.schema.tables[lineage[0]].columns[lineage[1]]
            if c.dtype not in ("date", "variant"):
                raise DaxError(f"Function expects a column of type Date; '{c.name}' is of type "
                               f"{TYPE_LABEL.get(c.dtype)}.", "type", arg.pos)
            values = self.column_values(lineage[0], lineage[1], ctx, distinct=True)
            return lineage, [v for v in values if isinstance(v, dt.datetime)]
        table = self.table(arg, ctx)
        lineage = table.cols[0].lineage if table.cols else None
        return lineage, [r[0] for r in table.rows if isinstance(r[0], dt.datetime)]

    def _date_table(self, lineage, dates):
        if lineage is None:
            return TableVal([ColInfo("Date")], [(d,) for d in sorted(set(dates))])
        universe = {vkey(v): v for (v,) in self.all_distinct([lineage])}
        rows = sorted({vkey(d): universe[vkey(d)] for d in dates if vkey(d) in universe}.values(),
                      key=sort_key)
        return TableVal([ColInfo(None, lineage)], [(d,) for d in rows])

    def _universe(self, lineage):
        return sorted((v for (v,) in self.all_distinct([lineage]) if isinstance(v, dt.datetime)),
                      key=sort_key)

    @staticmethod
    def _shift(value, n, unit):
        if unit == "YEAR":
            return add_months(value, 12 * n)
        if unit == "QUARTER":
            return add_months(value, 3 * n)
        if unit == "MONTH":
            return add_months(value, n)
        return value + dt.timedelta(days=n)

    def tf_DATEADD(self, node, ctx):
        lineage, dates = self._dates(node.args[0], ctx)
        n = int(self._n(node, ctx, 1, 0) or 0)
        unit = node.args[2].name.upper()
        return self._date_table(lineage, [self._shift(d, n, unit) for d in dates])

    def tf_SAMEPERIODLASTYEAR(self, node, ctx):
        lineage, dates = self._dates(node.args[0], ctx)
        return self._date_table(lineage, [self._shift(d, -1, "YEAR") for d in dates])

    def _period_bounds(self, value, unit):
        if unit == "YEAR":
            return dt.datetime(value.year, 1, 1), dt.datetime(value.year, 12, 31)
        if unit == "QUARTER":
            start = dt.datetime(value.year, (value.month - 1) // 3 * 3 + 1, 1)
            end = add_months(start, 3) - dt.timedelta(days=1)
            return start, end
        if unit == "MONTH":
            start = value.replace(day=1, hour=0, minute=0, second=0)
            return start, add_months(start, 1) - dt.timedelta(days=1)
        day = value.replace(hour=0, minute=0, second=0)
        return day, day

    def _period_table(self, node, ctx, n, unit, anchor="min"):
        lineage, dates = self._dates(node.args[0], ctx)
        if not dates:
            return self._date_table(lineage, [])
        ref = min(dates) if anchor == "min" else max(dates)
        start, _ = self._period_bounds(self._shift(ref, n, unit), unit)
        if anchor == "span":
            start, _ = self._period_bounds(self._shift(min(dates), n, unit), unit)
            _, end = self._period_bounds(self._shift(max(dates), n, unit), unit)
        else:
            _, end = self._period_bounds(self._shift(ref, n, unit), unit)
        universe = self._universe(lineage) if lineage else []
        return self._date_table(lineage, [d for d in universe if start <= d <= end])

    def tf_PREVIOUSMONTH(self, node, ctx):
        return self._period_table(node, ctx, -1, "MONTH")

    def tf_PREVIOUSYEAR(self, node, ctx):
        return self._period_table(node, ctx, -1, "YEAR")

    def tf_PREVIOUSQUARTER(self, node, ctx):
        return self._period_table(node, ctx, -1, "QUARTER")

    def tf_PREVIOUSDAY(self, node, ctx):
        return self._period_table(node, ctx, -1, "DAY")

    def tf_NEXTMONTH(self, node, ctx):
        return self._period_table(node, ctx, 1, "MONTH", anchor="max")

    def tf_NEXTYEAR(self, node, ctx):
        return self._period_table(node, ctx, 1, "YEAR", anchor="max")

    def tf_PARALLELPERIOD(self, node, ctx):
        n = int(self._n(node, ctx, 1, 0) or 0)
        unit = node.args[2].name.upper()
        return self._period_table(node, ctx, n, unit, anchor="span")

    def _to_date_table(self, node, ctx, unit):
        lineage, dates = self._dates(node.args[0], ctx)
        if not dates:
            return self._date_table(lineage, [])
        end = max(dates)
        start, _ = self._period_bounds(end, unit)
        universe = self._universe(lineage) if lineage else dates
        return self._date_table(lineage, [d for d in universe if start <= d <= end])

    def tf_DATESYTD(self, node, ctx):
        return self._to_date_table(node, ctx, "YEAR")

    def tf_DATESMTD(self, node, ctx):
        return self._to_date_table(node, ctx, "MONTH")

    def tf_DATESQTD(self, node, ctx):
        return self._to_date_table(node, ctx, "QUARTER")

    def _total_to_date(self, node, ctx, unit):
        dates_node = node.args[1]
        table = self._to_date_table(Call("X", [dates_node], node.pos), ctx, unit)
        new = self.transition(ctx) if ctx.rows else ctx
        new = self.add_filter(new, self.table_filter(table, node))
        for extra in node.args[2:]:
            if extra is not None and not isinstance(extra, Str):
                new = self.apply_filter_args([extra], new)
        return self.scalar(node.args[0], new.copy(rows=()))

    def fn_TOTALYTD(self, node, ctx):
        return self._total_to_date(node, ctx, "YEAR")

    def fn_TOTALMTD(self, node, ctx):
        return self._total_to_date(node, ctx, "MONTH")

    def fn_TOTALQTD(self, node, ctx):
        return self._total_to_date(node, ctx, "QUARTER")

    def tf_DATESBETWEEN(self, node, ctx):
        lineage = self.lineage_of(node.args[0])
        start = self._d(node, ctx, 1)
        end = self._d(node, ctx, 2)
        universe = self._universe(lineage)
        return self._date_table(lineage, [d for d in universe
                                          if (start is None or d >= start) and (end is None or d <= end)])

    def tf_DATESINPERIOD(self, node, ctx):
        lineage = self.lineage_of(node.args[0])
        start = self._d(node, ctx, 1)
        n = int(self._n(node, ctx, 2, 0) or 0)
        unit = node.args[3].name.upper()
        other = self._shift(start, n, unit)
        if n < 0:
            low, high = other + dt.timedelta(days=1), start
        else:
            low, high = start, other - dt.timedelta(days=1)
        return self._date_table(lineage, [d for d in self._universe(lineage) if low <= d <= high])

    def tf_FIRSTDATE(self, node, ctx):
        lineage, dates = self._dates(node.args[0], ctx)
        return self._date_table(lineage, [min(dates)] if dates else [])

    def tf_LASTDATE(self, node, ctx):
        lineage, dates = self._dates(node.args[0], ctx)
        return self._date_table(lineage, [max(dates)] if dates else [])

    def _edge(self, node, ctx, unit, start):
        lineage, dates = self._dates(node.args[0], ctx)
        if not dates:
            return self._date_table(lineage, [])
        ref = min(dates) if start else max(dates)
        low, high = self._period_bounds(ref, unit)
        universe = self._universe(lineage) if lineage else dates
        inside = [d for d in universe if low <= d <= high]
        if not inside:
            return self._date_table(lineage, [])
        return self._date_table(lineage, [min(inside) if start else max(inside)])

    def tf_STARTOFMONTH(self, node, ctx):
        return self._edge(node, ctx, "MONTH", True)

    def tf_ENDOFMONTH(self, node, ctx):
        return self._edge(node, ctx, "MONTH", False)

    def tf_STARTOFYEAR(self, node, ctx):
        return self._edge(node, ctx, "YEAR", True)

    def tf_ENDOFYEAR(self, node, ctx):
        return self._edge(node, ctx, "YEAR", False)

    def tf_STARTOFQUARTER(self, node, ctx):
        return self._edge(node, ctx, "QUARTER", True)

    def tf_ENDOFQUARTER(self, node, ctx):
        return self._edge(node, ctx, "QUARTER", False)

    # ======================================================================
    # Funciones de tabla
    # ======================================================================
    def tf_FILTER(self, node, ctx):
        table = self.table(node.args[0], ctx)
        cond = node.args[1]
        if table.base is not None and table._rows is None:
            keep = [rid for rid, inner in zip(table.rowids, self.iterate(table, ctx))
                    if to_bool(self.scalar(cond, inner), node.pos)]
            return TableVal(table.cols, base=table.base, rowids=keep, runtime=self.rt)
        rows = [values for values in table.rows
                if to_bool(self.scalar(cond, ctx.copy(rows=ctx.rows + (table.row_from_tuple(values),))), node.pos)]
        return TableVal(table.cols, rows)

    def _all_table(self, node, ctx):
        if not node.args:
            raise DaxError("ALL() without arguments can only be used as a CALCULATE filter.", "value", node.pos)
        first = node.args[0]
        if isinstance(first, (TableRef, Ident)) and not (isinstance(first, Ident) and first.name.casefold() in ctx.vars):
            return self.model_table(first.name, ctx, first.pos, all_rows=True)
        lineages = [self.lineage_of(a) for a in node.args]
        if len({t for t, _ in lineages}) > 1:
            raise DaxError("All column arguments of the ALL/ALLNOBLANKROW function must be from the same table.",
                           "value", node.pos)
        return TableVal([ColInfo(None, lin) for lin in lineages], self.all_distinct(lineages))

    def tf_ALL(self, node, ctx):
        return self._all_table(node, ctx)

    tf_ALLNOBLANKROW = tf_ALL

    def tf_REMOVEFILTERS(self, node, ctx):
        return self._all_table(node, ctx)

    def tf_ALLSELECTED(self, node, ctx):
        base = ctx.allselected or Ctx()
        if not node.args:
            raise DaxUnsupported("ALLSELECTED() sin argumentos como tabla", node.pos)
        return self.tf_VALUES(Call("VALUES", node.args[:1], node.pos), base)

    def tf_ALLEXCEPT(self, node, ctx):
        t = self.table_schema(node.args[0].name, node.pos)
        keep = [self.lineage_of(a) for a in node.args[1:]]
        new = self.remove_filters(ctx, tables=self.expanded_tables(key(t.name)), except_cols=keep)
        return self.model_table(t.name, new, node.pos)

    def tf_VALUES(self, node, ctx):
        arg = node.args[0]
        if isinstance(arg, ColRef) and arg.table:
            lineage = self.lineage_of(arg)
            values = self.column_values(lineage[0], lineage[1], ctx, distinct=True)
            return TableVal([ColInfo(None, lineage)], [(v,) for v in values])
        if isinstance(arg, (TableRef, Ident)) and self.schema.table(arg.name) and \
                arg.name.casefold() not in ctx.vars:
            return self.model_table(arg.name, ctx, arg.pos)
        table = self.table(arg, ctx)
        return self._distinct(table)

    def tf_DISTINCT(self, node, ctx):
        arg = node.args[0]
        if isinstance(arg, ColRef):
            return self.tf_VALUES(node, ctx)
        return self._distinct(self.table(arg, ctx))

    @staticmethod
    def _distinct(table):
        seen, rows = set(), []
        for values in table.rows:
            k = tuple(vkey(v) for v in values)
            if k not in seen:
                seen.add(k)
                rows.append(values)
        return TableVal(table.cols, rows)

    def tf_FILTERS(self, node, ctx):
        return self.tf_VALUES(node, ctx)

    def tf_KEEPFILTERS(self, node, ctx):
        return self.table(node.args[0], ctx)

    def tf_TREATAS(self, node, ctx):
        source = self.table(node.args[0], ctx)
        targets = [self.lineage_of(a) for a in node.args[1:]]
        if len(targets) != len(source.cols):
            raise DaxError("The number of columns in the table expression must match the number of columns "
                           "specified in TREATAS.", "value", node.pos)
        rows = source.rows
        for index, lineage in enumerate(targets):
            column = self.schema.tables[lineage[0]].columns[lineage[1]]
            for values in rows:
                value = values[index]
                if value is None:
                    continue
                if not _type_compatible(column.dtype, value):
                    self.rt.warn_mismatch(
                        f"TYPE MISMATCH: TREATAS aplica {type_label(value)} ({value!r}) a "
                        f"{self.display(ColInfo(None, lineage))} de tipo {TYPE_LABEL.get(column.dtype)} -> "
                        f"en Power BI real el valor no coincide con ninguna fila (resultado vacío)",
                        self.display(ColInfo(None, lineage)))
                    break
        return TableVal([ColInfo(None, lin) for lin in targets], rows)

    def tf_SELECTCOLUMNS(self, node, ctx):
        table = self.table(node.args[0], ctx)
        specs = []
        args = node.args[1:]
        i = 0
        while i < len(args):
            if isinstance(args[i], Str):
                specs.append((args[i].value, args[i + 1]))
                i += 2
            else:
                expr = args[i]
                if not isinstance(expr, ColRef):
                    raise self._syntax(expr)
                specs.append((None, expr))
                i += 1
        cols = []
        for name, expr in specs:
            lineage = self.lineage_of(expr) if isinstance(expr, ColRef) and expr.table else None
            cols.append(ColInfo(name, lineage))
        rows = [tuple(self.scalar(expr, inner) for _, expr in specs) for inner in self.iterate(table, ctx)]
        return TableVal(cols, rows)

    def _syntax(self, node):
        return DaxError("The syntax for the expression is incorrect.", "syntax", getattr(node, "pos", None))

    def tf_ADDCOLUMNS(self, node, ctx):
        table = self.table(node.args[0], ctx)
        pairs = [(node.args[i].value, node.args[i + 1]) for i in range(1, len(node.args) - 1, 2)]
        rows = []
        for values, inner in zip(table.rows, self.iterate(table, ctx)):
            rows.append(tuple(values) + tuple(self.scalar(expr, inner) for _, expr in pairs))
        return TableVal(table.cols + [ColInfo(name) for name, _ in pairs], rows)

    def tf_ROW(self, node, ctx):
        if len(node.args) < 2 or len(node.args) % 2:
            raise DaxError("Too few arguments were passed to the ROW function.", "syntax", node.pos)
        names, values = [], []
        for i in range(0, len(node.args), 2):
            if not isinstance(node.args[i], Str):
                raise self._syntax(node.args[i])
            names.append(node.args[i].value)
            values.append(self.scalar(node.args[i + 1], ctx))
        return TableVal([ColInfo(n) for n in names], [tuple(values)])

    def tf_TOPN(self, node, ctx):
        n = int(self._n(node, ctx, 0, 0) or 0)
        table = self.table(node.args[1], ctx)
        orders = []
        args = node.args[2:]
        i = 0
        while i < len(args):
            expr = args[i]
            descending = True
            if i + 1 < len(args) and isinstance(args[i + 1], (Ident, Num)):
                flag = args[i + 1]
                descending = (flag.name.upper() == "DESC") if isinstance(flag, Ident) else flag.value == 0
                i += 2
            else:
                i += 1
            orders.append((expr, descending))
        materialized = list(zip(table.rows, (r for r in table.row_contexts())))
        if not orders:
            return TableVal(table.cols, [r for r, _ in materialized[:n]])
        scored = []
        for values, row in materialized:
            inner = ctx.copy(rows=ctx.rows + (row,))
            scored.append((values, [self.scalar(expr, inner) for expr, _ in orders]))
        for index in reversed(range(len(orders))):
            scored.sort(key=lambda item: sort_key(item[1][index]), reverse=orders[index][1])
        if n <= 0:
            return TableVal(table.cols, [])
        cut = scored[:n]
        if len(scored) > n:
            last = [sort_key(v) for v in scored[n - 1][1]]
            cut += [s for s in scored[n:] if [sort_key(v) for v in s[1]] == last]
        return TableVal(table.cols, [values for values, _ in cut])

    def tf_SUMMARIZECOLUMNS(self, node, ctx):
        groups, filter_args, exprs = [], [], []
        args = node.args
        i = 0
        while i < len(args):
            arg = args[i]
            if isinstance(arg, Str):
                if i + 1 >= len(args):
                    raise self._syntax(arg)
                exprs.append((arg.value, args[i + 1]))
                i += 2
                continue
            if exprs:
                raise self._syntax(arg)
            if isinstance(arg, ColRef) and arg.table:
                groups.append(self.lineage_of(arg))
            elif isinstance(arg, Call) and arg.name in ("ROLLUPADDISSUBTOTAL", "ROLLUPGROUP", "NONVISUAL",
                                                        "IGNORE"):
                raise DaxUnsupported(f"{arg.name} dentro de SUMMARIZECOLUMNS", arg.pos)
            else:
                if self._is_boolean_filter(arg, ctx) and not (isinstance(arg, Call) and arg.name in (
                        "KEEPFILTERS", "TREATAS", "FILTER", "VALUES", "ALL", "DATESBETWEEN")):
                    raise DaxError("Function SUMMARIZECOLUMNS expects a table expression for argument "
                                   f"'{i + 1}', but a string or numeric expression was used.", "value",
                                   getattr(arg, "pos", node.pos))
                filter_args.append(arg)
            i += 1
        fctx = self.apply_filter_args(filter_args, ctx) if filter_args else ctx
        fctx = fctx.copy(rows=())
        fctx = fctx.copy(allselected=fctx)

        # Combinaciones de agrupación: tuplas existentes por tabla, producto entre tablas.
        by_table = {}
        for lineage in groups:
            by_table.setdefault(lineage[0], []).append(lineage)
        per_table = []
        for tkey, lineages in by_table.items():
            store = self.rt.store(tkey)
            seen, combos = set(), []
            for rid in self.visible_rowids(tkey, fctx):
                values = tuple(store.value(rid, c) for _, c in lineages)
                k = tuple(vkey(v) for v in values)
                if k not in seen:
                    seen.add(k)
                    combos.append(values)
            per_table.append((lineages, combos))
        combos = [((), ())]
        for lineages, values_list in per_table:
            combos = [(lin + tuple(lineages), vals + values) for lin, vals in combos for values in values_list]
            if len(combos) > 200_000:
                raise DaxError("The query exceeded the resources available (simulador: demasiadas "
                               "combinaciones en SUMMARIZECOLUMNS).", "value", node.pos)
        out_rows = []
        for lineages, values in combos:
            gctx = fctx
            for tkey, cols in by_table.items():
                idx = [j for j, lin in enumerate(lineages) if lin[0] == tkey]
                gctx = self.add_filter(gctx, Filter([lineages[j] for j in idx],
                                                    [tuple(vkey(values[j]) for j in idx)]))
            gctx = gctx.copy(allselected=fctx)
            measures = [self.scalar(expr, gctx) for _, expr in exprs]
            if exprs and all(m is None for m in measures):
                continue
            ordered = [values[lineages.index(lin)] for lin in groups]
            out_rows.append(tuple(ordered) + tuple(measures))
        cols = [ColInfo(None, lin) for lin in groups] + [ColInfo(name) for name, _ in exprs]
        return TableVal(cols, out_rows)

    def tf_SUMMARIZE(self, node, ctx):
        table = self.table(node.args[0], ctx)
        groups, exprs = [], []
        args = node.args[1:]
        i = 0
        while i < len(args):
            if isinstance(args[i], Str):
                exprs.append((args[i].value, args[i + 1]))
                i += 2
            else:
                groups.append(self.lineage_of(args[i]))
                i += 1
        seen, out = {}, []
        for row in table.row_contexts():
            values = []
            for lineage in groups:
                if row.table == lineage[0]:
                    values.append(self.rt.store(row.table).value(row.rowid, lineage[1]))
                elif lineage in row.values:
                    values.append(row.values[lineage])
                else:
                    values.append(self.scalar(ColRef(lineage[0], lineage[1], None), ctx.copy(rows=(row,)))
                                  if row.table else None)
            k = tuple(vkey(v) for v in values)
            if k not in seen:
                seen[k] = values
                out.append(values)
        rows = []
        for values in out:
            gctx = ctx
            for lineage, value in zip(groups, values):
                gctx = self.add_filter(gctx, Filter([lineage], [(vkey(value),)]))
            rows.append(tuple(values) + tuple(self.scalar(expr, gctx) for _, expr in exprs))
        return TableVal([ColInfo(None, lin) for lin in groups] + [ColInfo(n) for n, _ in exprs], rows)

    def tf_DATATABLE(self, node, ctx):
        args = node.args
        data = args[-1]
        specs = []
        for i in range(0, len(args) - 1, 2):
            specs.append((args[i].value, args[i + 1].name.upper() if isinstance(args[i + 1], Ident) else "STRING"))
        rows = []
        for row in getattr(data, "rows", []):
            items = row
            if len(row) == 1 and isinstance(row[0], TableCtor):
                items = [r[0] for r in row[0].rows]
            values = []
            for (_, kind), item in zip(specs, items):
                value = self.scalar(item, ctx)
                if kind in ("DATETIME",) and value is not None:
                    value = to_date(value)
                values.append(value)
            rows.append(tuple(values))
        return TableVal([ColInfo(name) for name, _ in specs], rows)

    def tf_UNION(self, node, ctx):
        tables = [self.table(a, ctx) for a in node.args]
        width = len(tables[0].cols)
        rows = []
        for table in tables:
            if len(table.cols) != width:
                raise DaxError("Each table argument of 'UNION' must have the same number of columns.",
                               "value", node.pos)
            rows.extend(table.rows)
        cols = []
        for index, col in enumerate(tables[0].cols):
            same = all(t.cols[index].lineage == col.lineage for t in tables)
            cols.append(ColInfo(col.name or (self.display(col).split("[")[-1].rstrip("]") if col.lineage else None),
                                col.lineage if same else None))
        return TableVal(cols, rows)

    def tf_EXCEPT(self, node, ctx):
        a, b = self.table(node.args[0], ctx), self.table(node.args[1], ctx)
        other = {tuple(vkey(v) for v in r) for r in b.rows}
        return TableVal(a.cols, [r for r in a.rows if tuple(vkey(v) for v in r) not in other])

    def tf_INTERSECT(self, node, ctx):
        a, b = self.table(node.args[0], ctx), self.table(node.args[1], ctx)
        other = {tuple(vkey(v) for v in r) for r in b.rows}
        return TableVal(a.cols, [r for r in a.rows if tuple(vkey(v) for v in r) in other])

    def tf_CROSSJOIN(self, node, ctx):
        tables = [self.table(a, ctx) for a in node.args]
        rows = [()]
        cols = []
        for table in tables:
            cols.extend(table.cols)
            rows = [r + tuple(t) for r in rows for t in table.rows]
        return TableVal(cols, rows)

    def tf_GENERATE(self, node, ctx):
        left = self.table(node.args[0], ctx)
        rows, cols = [], None
        for values, inner in zip(left.rows, self.iterate(left, ctx)):
            right = self.table(node.args[1], inner)
            cols = left.cols + right.cols
            rows.extend(tuple(values) + tuple(r) for r in right.rows)
        return TableVal(cols or left.cols, rows)

    def tf_GENERATESERIES(self, node, ctx):
        start, end = self._n(node, ctx, 0), self._n(node, ctx, 1)
        step = self._n(node, ctx, 2, 1) or 1
        rows, value = [], start
        while value <= end + 1e-9 and len(rows) < 100_000:
            rows.append((value,))
            value += step
        return TableVal([ColInfo("Value")], rows)

    def tf_CALENDAR(self, node, ctx):
        start, end = self._d(node, ctx, 0), self._d(node, ctx, 1)
        if start is None or end is None:
            raise DaxError("The arguments in CALENDAR function cannot be BLANK.", "value", node.pos)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        days = (end.date() - start.date()).days
        if days < 0:
            raise DaxError("The start date in Calendar function can not be later than the end date.",
                           "value", node.pos)
        return TableVal([ColInfo("Date")], [(start + dt.timedelta(days=d),) for d in range(days + 1)])

    def tf_CALENDARAUTO(self, node, ctx):
        start, end = self.rt.data_range
        return TableVal([ColInfo("Date")], [(dt.datetime(start.year, 1, 1) + dt.timedelta(days=d),)
                                            for d in range((dt.datetime(end.year, 12, 31)
                                                            - dt.datetime(start.year, 1, 1)).days + 1)])

    # ---------- INFO.VIEW.* (sync_powerbi_metadata.py) ----------
    def _info(self, name):
        headers, rows = self.schema.info_rows.get(name, ([], []))
        out = []
        for row in rows:
            values = []
            for h in headers:
                value = row.get(h, "")
                if value in ("True", "False"):
                    value = value == "True"
                elif h == "ID" and re.fullmatch(r"\d+", str(value)):
                    value = int(value)
                elif value == "":
                    value = None
                values.append(value)
            out.append(tuple(values))
        return TableVal([ColInfo(h) for h in headers], out)

    def tf_INFO_VIEW_TABLES(self, node, ctx):
        return self._info("tables")

    def tf_INFO_VIEW_COLUMNS(self, node, ctx):
        return self._info("columns")

    def tf_INFO_VIEW_MEASURES(self, node, ctx):
        return self._info("measures")

    def tf_INFO_VIEW_RELATIONSHIPS(self, node, ctx):
        return self._info("relationships")

    # ======================================================================
    # Consulta
    # ======================================================================
    def run_query(self, text):
        query = parse_query(text)
        self.query_measures = {}
        self.query_trees = {}
        for table, name, expr in query.measures:
            self.query_measures[key(name)] = Measure(name=name, table=table, expression="")
            self.query_trees[key(name)] = expr
        self.validate(query)
        ctx = Ctx()
        if query.vars:
            ctx = self.bind_vars(VarBlock(query.vars, None, None), ctx)
        evaluate = query.evaluates[0]
        if not self.is_table_expr(evaluate.table, ctx):
            raise DaxError("The expression specified in the query is not a valid table expression.",
                           "value", evaluate.pos)
        table = self.table(evaluate.table, ctx)
        rows = list(table.rows)
        if evaluate.order_by:
            keyed = []
            for values in rows:
                row = table.row_from_tuple(values)
                inner = ctx.copy(rows=(row,))
                keyed.append((values, [self.scalar(expr, inner) for expr, _ in evaluate.order_by]))
            for index in reversed(range(len(evaluate.order_by))):
                ascending = evaluate.order_by[index][1]
                keyed.sort(key=lambda item: sort_key(item[1][index]), reverse=not ascending)
            rows = [values for values, _ in keyed]
        columns = [self.display(c) for c in table.cols]
        types = [self._column_type(c) for c in table.cols]
        return columns, [list(r) for r in rows], types

    def _column_type(self, info):
        if info.lineage:
            column = self.schema.tables[info.lineage[0]].columns.get(info.lineage[1])
            return column.dtype if column else "variant"
        return "variant"

    # ---------- validación (enlace de nombres) ----------
    _KEYWORD_ARGS = {
        "ASC", "DESC", "YEAR", "QUARTER", "MONTH", "WEEK", "DAY", "HOUR", "MINUTE", "SECOND", "STRING",
        "INTEGER", "INT64", "DOUBLE", "DECIMAL", "DATETIME", "BOOLEAN", "CURRENCY", "SKIP", "DENSE",
        "TRUE", "FALSE", "BOTH", "NONE", "ONEWAY", "ONEWAY_RIGHTFILTERSLEFT", "ONEWAY_LEFTFILTERSRIGHT",
    }

    def validate(self, query):
        variables = {name.casefold() for name, _ in query.vars}
        extension_names = set()
        for node in walk(query):
            if isinstance(node, VarBlock):
                variables |= {name.casefold() for name, _ in node.vars}
            if isinstance(node, Call):
                for arg in node.args:
                    if isinstance(arg, Str):
                        extension_names.add(arg.value.casefold())
                if node.name in ("CALENDAR", "CALENDARAUTO"):
                    extension_names.add("date")
                if node.name in ("GENERATESERIES",) or node.name == "DATATABLE":
                    extension_names.add("value")
            if isinstance(node, TableCtor):
                extension_names |= {"value", "value1", "value2", "value3", "value4"}
        for node in walk(query):
            if isinstance(node, ColRef):
                if node.table is None:
                    name = node.column.casefold()
                    if self.measure_of(node.column) is None and name not in extension_names:
                        if not any(key(node.column) in t.columns for t in self.schema.tables.values()):
                            raise DaxError(f"The value for '{node.column}' cannot be determined. Either the "
                                           f"column doesn't exist, or there is no current row for this column.",
                                           "name", node.pos)
                else:
                    self.column_schema(node.table, node.column, node.pos)
            elif isinstance(node, TableRef):
                self.table_schema(node.name, node.pos)
            elif isinstance(node, Ident):
                name = node.name
                if name.casefold() in variables or name.upper() in self._KEYWORD_ARGS:
                    continue
                if self.schema.table(name) is None:
                    raise DaxError(f"Failed to resolve name '{name}'. It is not a valid table, variable, "
                                   f"or function name.", "name", node.pos)
            elif isinstance(node, Call):
                attr = node.name.replace(".", "_")
                if not (hasattr(self, "fn_" + attr) or hasattr(self, "tf_" + attr)):
                    self._unknown_function(node)


def _type_compatible(dtype, value):
    if dtype in ("variant",):
        return True
    if dtype == "text":
        return isinstance(value, str)
    if dtype in ("int", "float", "decimal"):
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
    if dtype == "date":
        return isinstance(value, dt.datetime)
    if dtype == "bool":
        return isinstance(value, bool)
    return True


# ----------------------------------------------------------------------------
# FORMAT (cultura del modelo: es-ES)
# ----------------------------------------------------------------------------

def _group(number_text):
    integer, _, decimals = number_text.partition(".")
    sign = ""
    if integer.startswith("-"):
        sign, integer = "-", integer[1:]
    parts = []
    while len(integer) > 3:
        parts.insert(0, integer[-3:])
        integer = integer[:-3]
    parts.insert(0, integer)
    return sign + ".".join(parts) + ("," + decimals if decimals else "")


def format_value(value, fmt):
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        named = {"short date": "dd/MM/yyyy", "long date": "dddd, d 'de' MMMM 'de' yyyy",
                 "general date": "dd/MM/yyyy H:mm:ss", "short time": "H:mm", "long time": "H:mm:ss"}
        pattern = named.get(fmt.strip().lower(), fmt or "dd/MM/yyyy")

        def repl(m):
            token = m.group(0)
            if token.startswith("'"):
                return token.strip("'")
            return {
                "yyyy": f"{value.year:04d}", "yy": f"{value.year % 100:02d}",
                "MMMM": MESES[value.month - 1], "MMM": MESES[value.month - 1][:3],
                "MM": f"{value.month:02d}", "M": str(value.month),
                "dddd": DIAS[value.weekday()], "ddd": DIAS[value.weekday()][:3],
                "dd": f"{value.day:02d}", "d": str(value.day),
                "HH": f"{value.hour:02d}", "H": str(value.hour), "hh": f"{(value.hour % 12) or 12:02d}",
                "h": str((value.hour % 12) or 12), "nn": f"{value.minute:02d}", "mm": f"{value.minute:02d}",
                "ss": f"{value.second:02d}", "q": str((value.month - 1) // 3 + 1),
            }.get(token, token)
        return re.sub(r"'[^']*'|yyyy|yy|MMMM|MMM|MM|M|dddd|ddd|dd|d|HH|H|hh|h|nn|mm|ss|q", repl, pattern)
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = float(value)
        lower = fmt.strip().lower()
        if lower in ("percent",):
            fmt = "0.00%"
        elif lower in ("standard",):
            fmt = "#,##0.00"
        elif lower in ("fixed",):
            fmt = "0.00"
        elif lower in ("general number", ""):
            return to_text(value).replace(".", ",")
        elif lower == "currency":
            fmt = "$ #,##0.00"
        percent = "%" in fmt
        if percent:
            number *= 100
        core = re.search(r"[#0][#0,]*(?:\.[0#]+)?", fmt)
        decimals = 0
        thousands = False
        if core:
            spec = core.group(0)
            if "." in spec:
                decimals = len(spec.split(".")[1])
            thousands = "," in spec.split(".")[0]
        rounded = Decimal(str(number)).quantize(Decimal(1).scaleb(-decimals), rounding="ROUND_HALF_UP")
        text = f"{rounded:.{decimals}f}"
        text = _group(text) if thousands else text.replace(".", ",")
        prefix = fmt[:core.start()] if core else ""
        suffix = fmt[core.end():] if core else ""
        return f"{prefix}{text}{suffix}".replace('"', "")
    return to_text(value)

"""
Generación determinista de datos sintéticos para un modelo semántico.

Reglas principales:
  - Semilla = (semilla global, nombre del modelo, tabla, mes): mismos datos siempre;
    ampliar el rango de fechas solo agrega meses nuevos (los anteriores no cambian).
  - Tablas calendario (LocalDateTable_*, CALENDAR(...), columnas fecha destino de relaciones):
    se evalúa su expresión DAX real; si no se puede, un día por fila.
  - Dimensiones (lado "uno" de relaciones con clave no fecha): claves 1..N o los valores
    del dominio de la columna clave; las columnas descriptivas reciben un valor distinto por fila.
  - Hechos: filas por mes (2023 -> ayer), FK muestreadas de las dimensiones con sesgo,
    columnas AÑO/MES coherentes con la fecha principal, ~1.5 % de blancos.
  - Columnas calculadas: se evalúa su expresión DAX fila a fila si es "barata"
    (sin CALCULATE, iteradores ni medidas); si no, valores por tipo (aproximado).
"""
import datetime as dt
import hashlib
import random
from decimal import Decimal

from .dax_parser import Call, ColRef, DaxError, walk
from .domains import MESES, is_person_column, person_kind, synthetic_person, text_domain
from .metadata import key, normalize_text

ROWID = "__rowid"

_EXPENSIVE = {
    "CALCULATE", "CALCULATETABLE", "FILTER", "SUMX", "AVERAGEX", "COUNTX", "MAXX", "MINX", "COUNTROWS",
    "LOOKUPVALUE", "RELATEDTABLE", "EARLIER", "EARLIEST", "SUM", "COUNT", "COUNTA", "AVERAGE",
    "DISTINCTCOUNT", "VALUES", "SELECTEDVALUE", "ALL", "ALLEXCEPT", "ALLSELECTED", "RANKX", "TOPN",
    "SUMMARIZE", "CONCATENATEX", "FIRSTNONBLANK", "LASTNONBLANK", "PATH", "PATHITEM",
}


def seed_int(*parts):
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16], 16)


def _has(name, *needles):
    norm = normalize_text(name).replace(" ", "_")
    return any(n in norm for n in needles)


def _months(start, end):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


class TableStore:
    """Datos de una tabla en columnas. Las columnas calculadas se materializan al usarse."""

    def __init__(self, runtime, table, rowcount, data):
        self.rt = runtime
        self.table = table
        self.rowcount = rowcount
        self.data = data            # key(columna) -> lista
        self._index = {}

    def value(self, rowid, ckey):
        if ckey == ROWID:
            return rowid
        column = self.data.get(ckey)
        if column is None:
            column = self.rt.generator.materialize(self, ckey)
        return column[rowid]

    def column(self, ckey):
        if ckey not in self.data:
            self.rt.generator.materialize(self, ckey)
        return self.data[ckey]

    def index(self, ckey):
        if ckey not in self._index:
            from .dax_eval import vkey
            idx = {}
            for i, value in enumerate(self.column(ckey)):
                idx.setdefault(vkey(value), []).append(i)
            self._index[ckey] = idx
        return self._index[ckey]


class DataGenerator:

    def __init__(self, runtime):
        self.rt = runtime
        self.schema = runtime.schema
        self.harvest = runtime.harvest
        self.seed = runtime.seed
        self._plans = {}
        self._classify()

    # ------------------------------------------------------------------
    # Clasificación de tablas y columnas
    # ------------------------------------------------------------------
    def _classify(self):
        self.fk = {}          # (tkey, ckey) -> (tkey destino, ckey destino)
        self.key_cols = {}    # tkey -> [ckey] claves (lado uno)
        self.calendar_date_cols = {}   # tkey -> ckey de fecha (tablas calendario)
        self.date_links = {}  # (tkey, ckey) fecha de hecho -> tabla calendario
        tables = self.schema.tables
        for rel in self.schema.relationships:
            ft, fc, tt, tc = key(rel.from_table), key(rel.from_column), key(rel.to_table), key(rel.to_column)
            if ft not in tables or tt not in tables:
                continue
            fcol, tcol = tables[ft].columns.get(fc), tables[tt].columns.get(tc)
            if fcol is None or tcol is None:
                continue
            many_from = rel.from_card.lower() == "many"
            many_to = rel.to_card.lower() == "many"
            if tcol.dtype == "date" or fcol.dtype == "date":
                # La tabla del lado "uno" (o la que no es hecho) es el calendario.
                if not many_to:
                    self.calendar_date_cols.setdefault(tt, tc)
                    self.date_links.setdefault((ft, fc), tt)
                elif not many_from:
                    self.calendar_date_cols.setdefault(ft, fc)
                    self.date_links.setdefault((tt, tc), ft)
                continue
            if many_from and not many_to:
                self.fk.setdefault((ft, fc), (tt, tc))
                self.key_cols.setdefault(tt, []).append(tc)
            elif many_to and not many_from:
                self.fk.setdefault((tt, tc), (ft, fc))
                self.key_cols.setdefault(ft, []).append(fc)
            elif not many_from and not many_to:
                # 1:1 -> la tabla de nombre "mayor" copia las claves de la otra
                primary, secondary = sorted([(ft, fc), (tt, tc)])
                self.fk.setdefault(secondary, primary)
                self.key_cols.setdefault(primary[0], []).append(primary[1])
            else:
                self.fk.setdefault((ft, fc), (tt, tc))
        for tkey, table in tables.items():
            if table.is_auto_date or table.expression.strip().upper().startswith(("CALENDAR", "CALENDARAUTO")):
                date_col = next((key(c.name) for c in table.columns.values() if c.dtype == "date"), None)
                if date_col:
                    self.calendar_date_cols.setdefault(tkey, date_col)

    def kind(self, tkey):
        table = self.schema.tables[tkey]
        if tkey in self.calendar_date_cols:
            return "calendar"
        if table.expression.strip():
            return "calculated"
        if tkey in self.key_cols and not any((tkey, c) in self.date_links for c in table.columns):
            return "dimension"
        return "fact"

    # ------------------------------------------------------------------
    # Entrada principal
    # ------------------------------------------------------------------
    def generate(self, tkey):
        kind = self.kind(tkey)
        table = self.schema.tables[tkey]
        if table.expression.strip():
            store = self._from_expression(tkey)
            if store is not None:
                return store
        if kind == "calendar":
            return self._calendar(tkey)
        if kind == "dimension":
            return self._dimension(tkey)
        return self._fact(tkey)

    def _data_columns(self, tkey):
        table = self.schema.tables[tkey]
        return [c for c in table.columns.values() if c.kind in ("data", "calctable")]

    # ---------- tablas calculadas ----------
    def _from_expression(self, tkey):
        from .dax_eval import Ctx, Evaluator
        table = self.schema.tables[tkey]
        try:
            tree = self.rt.parsed(("table", tkey), table.expression)
            ev = Evaluator(self.rt)
            result = ev.table(tree, Ctx())
            rows = result.rows
        except DaxError as exc:
            self.rt.generation_notes.append(f"tabla calculada {table.name}: {exc.message[:160]} -> datos genéricos")
            return None
        targets = self._data_columns(tkey)
        data = {}
        by_name = {}
        for index, info in enumerate(result.cols):
            name = info.name or (ev.display(info).split("[")[-1].rstrip("]"))
            by_name[key(name)] = index
        unmatched = [c for c in targets if key(c.name) not in by_name]
        free = [i for i in range(len(result.cols)) if i not in by_name.values()]
        for column in targets:
            index = by_name.get(key(column.name))
            if index is None and unmatched and free:
                index = free.pop(0)
            if index is None:
                continue
            data[key(column.name)] = [r[index] for r in rows]
        return TableStore(self.rt, table, len(rows), data)

    # ---------- calendario ----------
    def _calendar(self, tkey):
        table = self.schema.tables[tkey]
        start, end = self.rt.data_range
        first = dt.datetime(start.year, 1, 1)
        last = dt.datetime(end.year, 12, 31)
        days = [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]
        date_col = self.calendar_date_cols.get(tkey)
        data = {}
        for column in self._data_columns(tkey):
            ckey = key(column.name)
            if ckey == date_col or (column.dtype == "date" and date_col is None):
                data[ckey] = list(days)
            else:
                data[ckey] = [self._date_part(column, d) for d in days]
        return TableStore(self.rt, table, len(days), data)

    @staticmethod
    def _date_part(column, day):
        name = normalize_text(column.name)
        if column.dtype == "date":
            return day
        if _has(name, "ano", "anio", "year") and "mes" not in name:
            return day.year if column.dtype != "text" else str(day.year)
        if _has(name, "trimestre", "quarter"):
            q = (day.month - 1) // 3 + 1
            return q if column.dtype != "text" else f"Trim. {q}"
        if _has(name, "nromes", "mesnum", "num_mes", "month_no", "monthnumber") or (
                _has(name, "mes", "month") and column.dtype in ("int", "float")):
            if _has(name, "ano", "anio"):
                return day.year * 100 + day.month
            return day.month
        if _has(name, "mes", "month"):
            return MESES[day.month - 1]
        if _has(name, "semana", "week"):
            return int(day.strftime("%U")) + 1
        if _has(name, "dia", "day"):
            return day.day if column.dtype != "text" else ["lunes", "martes", "miércoles", "jueves",
                                                            "viernes", "sábado", "domingo"][day.weekday()]
        return None

    # ---------- dimensiones ----------
    def _domain(self, table, column, extra=()):
        harvested = self.harvest.get(table.name, column.name)
        for value in extra:
            if value not in harvested:
                harvested.append(value)
        generic = text_domain(table.name, column.name) or []
        if len(harvested) >= 3:
            return harvested
        merged = list(harvested)
        for value in generic:
            if value not in merged:
                merged.append(value)
        return merged

    def _dimension(self, tkey):
        table = self.schema.tables[tkey]
        keys = [ckey for ckey in self.key_cols.get(tkey, []) if ckey in table.columns]
        main_key = keys[0]
        key_column = table.columns[main_key]
        # Valores pedidos por las FK que apuntan a esta clave (literales cosechados en los hechos)
        extra = []
        for (ft, fc), (tt, tc) in self.fk.items():
            if tt == tkey and tc == main_key:
                source = self.schema.tables[ft]
                extra.extend(self.harvest.get(source.name, source.columns[fc].name))
        copy_from = self.fk.get((tkey, main_key))
        if copy_from and copy_from[0] != tkey and copy_from[0] not in self.rt.generating:
            values = list(self.rt.store(copy_from[0]).column(copy_from[1]))
        elif key_column.dtype == "text":
            values = self._domain(table, key_column, extra)
            if not values:
                values = [f"{key_column.name.upper()} {i:02d}" for i in range(1, self._dim_size(table) + 1)]
        else:
            values = list(range(1, self._dim_size(table) + 1))
        rng = random.Random(seed_int(self.seed, self.schema.name, table.name, "dim"))
        rowcount = len(values)
        data = {main_key: values}
        for column in self._data_columns(tkey):
            ckey = key(column.name)
            if ckey in data:
                continue
            if ckey in keys and column.dtype == "int":
                data[ckey] = list(range(1, rowcount + 1))
                continue
            if (tkey, ckey) in self.fk:
                data[ckey] = self._sample_fk(tkey, ckey, rng, rowcount)
                continue
            domain = self._domain(table, column) if column.dtype == "text" else None
            if domain and not is_person_column(table.name, column.name):
                data[ckey] = [domain[i % len(domain)] for i in range(rowcount)]
            else:
                data[ckey] = [self._value(table, column, rng, i, None) for i in range(rowcount)]
        return TableStore(self.rt, table, rowcount, data)

    @staticmethod
    def _dim_size(table):
        name = table.name
        if _has(name, "asegura", "tercero", "entidad", "eps", "pagador", "convenio"):
            return 18
        if _has(name, "servicio", "unidad", "area", "piso"):
            return 14
        if _has(name, "cama"):
            return 60
        if _has(name, "especialidad"):
            return 18
        if _has(name, "sede"):
            return 4
        if _has(name, "medico", "profesional"):
            return 40
        return 12

    def _sample_fk(self, tkey, ckey, rng, count):
        target_table, target_col = self.fk[(tkey, ckey)]
        if target_table in self.rt.generating:
            return None
        keys = [v for v in self.rt.store(target_table).column(target_col) if v is not None]
        if not keys:
            return [None] * count
        weights = self._weights(len(keys), tkey, ckey)
        return rng.choices(keys, cum_weights=weights, k=count)

    def _weights(self, n, *salt):
        order = list(range(n))
        random.Random(seed_int(self.seed, "w", *salt)).shuffle(order)
        cumulative, total = [], 0.0
        for rank in order:
            total += 1.0 / (rank + 1) ** 0.85
            cumulative.append(total)
        return cumulative

    # ---------- hechos ----------
    def _primary_date(self, tkey):
        table = self.schema.tables[tkey]
        candidates = [c for c in self._data_columns(tkey) if c.dtype == "date"]
        linked = [c for c in candidates if (tkey, key(c.name)) in self.date_links]
        if linked:
            return key(linked[0].name)
        preferred = [c for c in candidates if _has(c.name, "fecha")]
        if preferred:
            return key(preferred[0].name)
        return key(candidates[0].name) if candidates else None

    def _fact(self, tkey):
        table = self.schema.tables[tkey]
        columns = self._data_columns(tkey)
        primary = self._primary_date(tkey)
        start, end = self.rt.data_range
        base = 25 + seed_int(self.seed, self.schema.name, table.name, "base") % 70
        data = {key(c.name): [] for c in columns}
        rowcount = 0
        fk_cols = [key(c.name) for c in columns if (tkey, key(c.name)) in self.fk]
        if primary is None:
            months = [None]
        else:
            months = list(_months(start, end))
        for month_index, ym in enumerate(months):
            rng = random.Random(seed_int(self.seed, self.schema.name, table.name, ym))
            if ym is None:
                n = 60 + base * 3
            else:
                season = 1 + 0.15 * ((ym[1] * 7 + base) % 5 - 2) / 2
                trend = 1 + 0.05 * (ym[0] - start.year)
                n = max(1, int(round(base * season * trend)))
            for i in range(n):
                day = None
                if ym is not None:
                    days_in_month = (dt.date(ym[0] + ym[1] // 12, ym[1] % 12 + 1, 1) - dt.date(*ym, 1)).days
                    day = dt.datetime(ym[0], ym[1], 1 + rng.randrange(days_in_month))
                    if day.date() > end.date():
                        continue
                serial = month_index * 10_000 + i + 1
                for column in columns:
                    ckey = key(column.name)
                    if ckey in fk_cols:
                        data[ckey].append(("__fk__", rng.random()))
                        continue
                    if ckey == primary:
                        value = day
                        if _has(column.name, "hora") or "h" in column.format_string.lower():
                            value = day + dt.timedelta(minutes=rng.randrange(24 * 60))
                    else:
                        value = self._value(table, column, rng, serial, day)
                    data[ckey].append(value)
                rowcount += 1
        # FK: se resuelven al final para no depender del orden de generación
        for ckey in fk_cols:
            target_table, target_col = self.fk[(tkey, ckey)]
            if target_table in self.rt.generating:
                column = table.columns[ckey]
                rng = random.Random(seed_int(self.seed, table.name, ckey, "fk"))
                data[ckey] = [self._value(table, column, rng, i, None) for i in range(rowcount)]
                continue
            keys = [v for v in self.rt.store(target_table).column(target_col) if v is not None]
            weights = self._weights(len(keys), tkey, ckey) if keys else None
            resolved = []
            for marker, u in data[ckey]:
                if not keys:
                    resolved.append(None)
                    continue
                target = u * weights[-1]
                lo, hi = 0, len(weights) - 1
                while lo < hi:
                    mid = (lo + hi) // 2
                    if weights[mid] < target:
                        lo = mid + 1
                    else:
                        hi = mid
                resolved.append(keys[lo])
            data[ckey] = resolved
        return TableStore(self.rt, table, rowcount, data)

    # ---------- valor de una celda ----------
    def _value(self, table, column, rng, serial, day):
        plan = self._plans.get((table.name, column.name))
        if plan is None:
            plan = self._plans[(table.name, column.name)] = self._plan(table, column)
        blankable, generate = plan
        if blankable and rng.random() < 0.015:
            return None
        return generate(rng, serial, day)

    def _plan(self, table, column):
        """Analiza la columna una sola vez y devuelve (admite_blancos, generador(rng, serial, día))."""
        name = column.name
        dtype = column.dtype
        norm = normalize_text(name)
        is_key_like = column.unique or norm in ("id", "oid") or (
            _has(name, "id_", "_id", "oid") and not _has(name, "paciente", "ingreso", "historia"))
        blankable = not is_key_like and dtype != "date"
        if dtype == "date":
            if _has(name, "hora", "llegada", "triage", "atencion", "ingreso", "inicio", "fin", "salida"):
                offset = lambda rng: dt.timedelta(minutes=rng.randrange(8 * 60, 20 * 60) + rng.randrange(0, 240))
            elif _has(name, "egreso", "alta", "cierre", "entrega"):
                offset = lambda rng: dt.timedelta(days=rng.randrange(0, 12))
            else:
                offset = lambda rng: dt.timedelta(days=rng.randrange(0, 3))

            def gen_date(rng, serial, day):
                base = day or dt.datetime(2024, 1, 1) + dt.timedelta(days=rng.randrange(900))
                return base + offset(rng)
            return blankable, gen_date
        if dtype == "bool":
            return blankable, lambda rng, serial, day: rng.random() < 0.5
        if dtype in ("int", "float", "decimal"):
            return blankable, self._number_plan(table, column, is_key_like)
        if dtype == "text":
            if is_person_column(table.name, name):
                pooled = _has(name, "paciente", "documento", "identificacion", "historia")
                kind = person_kind(name)
                return blankable, lambda rng, serial, day: synthetic_person(
                    kind, (1 + serial % 997) if pooled else serial)
            if norm in ("mes", "nombre mes", "mes nombre"):
                return blankable, lambda rng, serial, day: (MESES[day.month - 1] if day is not None
                                                            else MESES[rng.randrange(12)])
            if norm in ("ano", "anio", "year"):
                return blankable, lambda rng, serial, day: str(day.year if day is not None else 2024)
            if is_key_like:
                prefix = norm[:3].upper()
                return False, lambda rng, serial, day: f"{prefix}{serial:07d}"
            domain = self._domain(table, column) or [f"{name.upper()} {i}" for i in range(1, 7)]
            weights = self._weights(len(domain), table.name, name)
            return blankable, lambda rng, serial, day: rng.choices(domain, cum_weights=weights, k=1)[0]
        return blankable, lambda rng, serial, day: None

    def _number_plan(self, table, column, is_key_like):
        n = normalize_text(column.name)
        dtype = column.dtype
        harvested = [v for v in self.harvest.get(table.name, column.name) if isinstance(v, (int, float))]

        def cast(value):
            if dtype == "int":
                return int(value)
            if dtype == "decimal":
                return Decimal(str(round(float(value), 2)))
            return float(value)

        if is_key_like:
            raw = lambda rng, serial, day: serial
        elif _has(n, "ano", "anio", "year") and not _has(n, "mes"):
            raw = lambda rng, serial, day: day.year if day is not None else rng.choice((2023, 2024, 2025, 2026))
        elif n in ("mes", "month", "nromes", "mes num", "num mes"):
            raw = lambda rng, serial, day: day.month if day is not None else rng.randrange(1, 13)
        elif n in ("dia", "day"):
            raw = lambda rng, serial, day: day.day if day is not None else rng.randrange(1, 29)
        elif _has(n, "hora"):
            raw = lambda rng, serial, day: rng.randrange(24)
        elif _has(n, "edad"):
            raw = lambda rng, serial, day: int(min(98, abs(rng.gauss(42, 22))))
        elif _has(n, "porc", "pct", "tasa", "proporcion", "ocupacion"):
            raw = lambda rng, serial, day: round(rng.uniform(0.45, 0.98), 4)
        elif _has(n, "valor", "costo", "precio", "factur", "monto", "pago", "tarifa", "glosa"):
            raw = lambda rng, serial, day: round(rng.uniform(50_000, 3_000_000), 0)
        elif _has(n, "peso"):
            raw = lambda rng, serial, day: round(rng.uniform(0.5, 40), 1)
        elif _has(n, "dias", "estancia"):
            raw = lambda rng, serial, day: int(abs(rng.gauss(4, 4)))
        elif _has(n, "min", "tiempo", "oportunidad", "espera", "duracion"):
            raw = lambda rng, serial, day: int(rng.uniform(5, 240))
        elif _has(n, "cant", "numero", "num_", "total", "camas", "cirugias", "egresos", "consultas"):
            raw = lambda rng, serial, day: rng.randrange(1, 12)
        elif _has(n, "ingreso", "historia", "documento", "identificacion", "paciente"):
            raw = lambda rng, serial, day: 100_000 + serial % 9973
        elif harvested:
            raw = lambda rng, serial, day: rng.choice(harvested)
        elif _has(n, "estado", "tipo", "codigo", "cod"):
            raw = lambda rng, serial, day: rng.randrange(0, 4)
        else:
            raw = lambda rng, serial, day: rng.randrange(0, 100)
        return lambda rng, serial, day: cast(raw(rng, serial, day))

    # ------------------------------------------------------------------
    # Columnas calculadas (perezosas)
    # ------------------------------------------------------------------
    def materialize(self, store, ckey):
        table = store.table
        column = table.columns.get(ckey)
        if column is None:
            raise DaxError(f"Column '{ckey}' in table '{table.name}' cannot be found or may not be used in "
                           f"this expression.", "name")
        if ckey in store.data:
            return store.data[ckey]
        marker = ("calc", key(table.name), ckey)
        if marker in self.rt.generating:
            raise DaxError(f"A circular dependency was detected: {table.name}[{column.name}].", "value")
        self.rt.generating.add(marker)
        try:
            values = None
            if column.kind == "calculated" and column.expression.strip():
                values = self._evaluate_column(store, column)
            if values is None:
                rng = random.Random(seed_int(self.seed, self.schema.name, table.name, column.name, "calc"))
                values = []
                date_col = self._primary_date(key(table.name)) if key(table.name) in self.schema.tables else None
                for i in range(store.rowcount):
                    day = store.value(i, date_col) if date_col and date_col in store.data else None
                    values.append(self._value(table, column, rng, i + 1, day if isinstance(day, dt.datetime) else None))
            store.data[ckey] = values
        finally:
            self.rt.generating.discard(marker)
        return store.data[ckey]

    def _cheap(self, tree):
        for node in walk(tree):
            if isinstance(node, Call):
                if node.name in ("MIN", "MAX") and len(node.args) == 2:
                    continue
                if node.name in _EXPENSIVE:
                    return False
            if isinstance(node, ColRef) and node.table is None and self.schema.measure(node.column):
                return False
        return True

    def _evaluate_column(self, store, column):
        from .dax_eval import Ctx, Evaluator, Row
        table = store.table
        try:
            tree = self.rt.parsed(("column", table.name, column.name), column.expression)
        except DaxError as exc:
            self.rt.generation_notes.append(f"columna calculada {table.name}[{column.name}]: {exc.message[:120]}")
            return None
        if not self._cheap(tree):
            self.rt.generation_notes.append(
                f"columna calculada {table.name}[{column.name}] no evaluada (expresión costosa) -> valores sintéticos")
            return None
        ev = Evaluator(self.rt)
        base = Ctx()
        tkey = key(table.name)
        values = []
        try:
            for i in range(store.rowcount):
                values.append(ev.scalar(tree, base.copy(rows=(Row(table=tkey, rowid=i),))))
        except DaxError as exc:
            self.rt.generation_notes.append(
                f"columna calculada {table.name}[{column.name}]: {exc.message[:120]} -> valores sintéticos")
            return None
        if column.dtype == "int":
            values = [int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and
                      abs(v) != float("inf") else v for v in values]
        return values

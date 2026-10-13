"""
Caché compartida de dominios de columnas (los valores de `VALUES(T[c])`) que se
consultan a Power BI para reconocer valores nombrados en la pregunta
(«urgencias», «nueva eps», «ortopedia»).

Contra Power BI real cada consulta XMLA cuesta ~0,3-1,5 s, y al explorar una
pregunta se revisan muchas columnas (valores implícitos, calificativos
aproximados, filtros de negocio). Esta caché:

- guarda el dominio de cada (modelo, tabla, columna) con vida limitada
  (POWERBI_DOMAIN_TTL_S, por defecto 1 hora; 0 = sin vencimiento) y la
  comparten QueryPlanBuilder y BusinessFilterResolver (una sola por proveedor);
- consulta en LOTE las columnas de texto que se van a revisar juntas: una sola
  consulta `EVALUATE UNION(SELECTCOLUMNS(TOPN(...VALUES(T[c1])...), "__columna", 0,
  "Value", [Value]), ...)` en lugar de una por columna (POWERBI_DOMAIN_BATCH
  columnas por consulta, por defecto 12; 1 = sin lote). Cada rama es la misma
  consulta de una columna, así que los valores son idénticos; solo se agrupan
  columnas del mismo tipo de dato (texto) para que UNION no convierta tipos. Si
  el lote falla o su resultado no tiene la forma esperada, se consulta cada
  columna por separado (como antes);
- limita las consultas de exploración por turno (POWERBI_DOMAIN_BUDGET, por
  defecto 12; 0 = sin límite; un lote cuenta como una): pasado el límite, las
  columnas que faltan no se consultan en ese turno (se tratan como dominio no
  disponible). Los llamadores piden las columnas en orden de plausibilidad
  (propias del indicador, plausibles para un valor suelto, el resto), así que lo
  que se omite es lo menos probable. Los filtros que el usuario nombró con su
  columna y los meses/años del periodo (`essential=True`) no tienen límite;
- un fallo no se guarda como dominio vacío: se reintenta en el turno siguiente
  (dentro del mismo turno no se repite la consulta fallida);
- cuenta consultas, columnas, aciertos y segundos por turno (`turn_stats()`)
  para el razonamiento del turno.

La consulta de una columna es exactamente la que usaba QueryPlanBuilder:

    EVALUATE TOPN(2500, FILTER(SELECTCOLUMNS(VALUES('T'[c]), "Value", 'T'[c]),
                               NOT ISBLANK([Value])), [Value], ASC)
"""
import os
import threading
import time

DEFAULT_LIMIT = 2500
BATCH_MARKER = "__columna"
_TEXT_TYPES = {"string", "text", "texto", "str"}


def _env_number(name, default, cast=float):
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return cast(str(raw).strip())
    except ValueError:
        return default


def table_ref(table):
    return "'" + str(table).replace("'", "''") + "'"


def column_ref(column):
    return "[" + str(column).replace("]", "]]") + "]"


def single_domain_dax(table, column, limit=DEFAULT_LIMIT):
    """Consulta del dominio de una columna (idéntica a la histórica del planificador)."""
    ref = f"{table_ref(table)}{column_ref(column)}"
    return (
        f'EVALUATE\nTOPN(\n    {int(limit)},\n    FILTER(\n        SELECTCOLUMNS(\n'
        f'            VALUES({ref}),\n            "Value", {ref}\n        ),\n'
        f'        NOT ISBLANK([Value])\n    ),\n    [Value], ASC\n)'
    )


def batch_domain_dax(columns, limit=DEFAULT_LIMIT):
    """Una consulta con el dominio de varias columnas: cada rama es la consulta
    de una columna con su índice en "__columna"."""
    branches = []
    for index, (table, column) in enumerate(columns):
        ref = f"{table_ref(table)}{column_ref(column)}"
        branches.append(
            f'    SELECTCOLUMNS(\n'
            f'        TOPN({int(limit)}, FILTER(SELECTCOLUMNS(VALUES({ref}), "Value", {ref}), '
            f'NOT ISBLANK([Value])), [Value], ASC),\n'
            f'        "{BATCH_MARKER}", {index},\n'
            f'        "Value", [Value]\n'
            f'    )'
        )
    # Sin ORDER BY: cada columna conserva el orden de su TOPN, como en la
    # consulta individual (las filas se separan por "__columna").
    return "EVALUATE\nUNION(\n" + ",\n".join(branches) + "\n)"


def is_text_type(data_type):
    """¿Tipo de dato de texto? (solo esas columnas se agrupan en un lote)."""
    return str(data_type or "").strip().lower() in _TEXT_TYPES


def _row_key(row, name):
    """Clave de la columna `name` en una fila de PowerBIProvider ("[name]", "T[name]" o "name")."""
    for key in row:
        text = str(key)
        if text == name or text.endswith(f"[{name}]"):
            return key
    return None


class DomainCache:
    """Dominios de columnas con TTL, lote, presupuesto por turno y métricas."""

    def __init__(self, provider, ttl_s=None, batch_size=None, turn_budget=None, clock=None):
        self.provider = provider
        self.ttl_s = float(ttl_s if ttl_s is not None else _env_number("POWERBI_DOMAIN_TTL_S", 3600.0))
        self.batch_size = int(batch_size if batch_size is not None
                              else _env_number("POWERBI_DOMAIN_BATCH", 12, int))
        self.turn_budget = int(turn_budget if turn_budget is not None
                               else _env_number("POWERBI_DOMAIN_BUDGET", 12, int))
        self.clock = clock or time.monotonic
        self._entries = {}        # clave -> (momento, [valores como texto])
        self._failed_turn = {}    # clave -> número de turno del fallo (no se reintenta en ese turno)
        self.errors = {}          # clave -> detalle del último fallo
        self._lock = threading.RLock()
        self._turn_id = 0
        self._in_turn = False
        # Tras dos lotes fallidos seguidos (p. ej. un servidor que no acepta la
        # forma de la consulta) se deja de intentar el lote en este proceso.
        self._batch_failures = 0
        self.turn = self._empty_stats()
        self.totals = self._empty_stats()

    # ---------------- claves y frescura ----------------
    @staticmethod
    def key(semantic_model, table, column):
        # DAX no distingue mayúsculas en nombres de tablas/columnas/modelos.
        return (str(semantic_model or "").casefold(), str(table or "").casefold(), str(column or "").casefold())

    def _fresh(self, entry):
        return entry is not None and (self.ttl_s <= 0 or self.clock() - entry[0] < self.ttl_s)

    def cached(self, semantic_model, table, column):
        """Dominio en caché y vigente (sin consultar), o None."""
        with self._lock:
            entry = self._entries.get(self.key(semantic_model, table, column))
            return entry[1] if self._fresh(entry) else None

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._failed_turn.clear()
            self.errors.clear()

    def __len__(self):
        return len(self._entries)

    # ---------------- turno ----------------
    @staticmethod
    def _empty_stats():
        return {"queries": 0, "batch_queries": 0, "columns": 0, "hits": 0, "seconds": 0.0,
                "errors": 0, "skipped": 0}

    def begin_turn(self):
        """Inicio de un turno del chat: reinicia las métricas y el presupuesto."""
        with self._lock:
            self._turn_id += 1
            self._in_turn = True
            self._failed_turn.clear()
            self.turn = self._empty_stats()

    def end_turn(self):
        with self._lock:
            self._in_turn = False
            self._failed_turn.clear()
            return dict(self.turn)

    def turn_stats(self):
        return dict(self.turn)

    def _count(self, field, amount=1):
        self.turn[field] += amount
        self.totals[field] += amount

    def _budget_left(self):
        if not self._in_turn or self.turn_budget <= 0:
            return True
        return self.turn["queries"] < self.turn_budget

    def _skip_failed(self, key):
        return self._in_turn and self._failed_turn.get(key) == self._turn_id

    # ---------------- consultas ----------------
    def _execute(self, dax, semantic_model):
        started = time.perf_counter()
        try:
            result = self.provider.execute_dax(dax=dax, semantic_model=semantic_model)
        except Exception as exc:  # proveedores de prueba que lanzan en lugar de devolver error
            result = {"status": "error", "error": str(exc), "error_type": type(exc).__name__}
        self._count("seconds", time.perf_counter() - started)
        self._count("queries")
        return result if isinstance(result, dict) else {"status": "error", "error": "respuesta inválida"}

    def _store(self, key, values):
        self._entries[key] = (self.clock(), values)
        self.errors.pop(key, None)
        self._failed_turn.pop(key, None)

    def _fail(self, key, result):
        self.errors[key] = {
            "status": result.get("status"),
            "error_type": result.get("error_type"),
            "message": str(result.get("error") or result.get("message") or "Sin detalle")[:300],
        }
        self._failed_turn[key] = self._turn_id
        self._count("errors")

    @staticmethod
    def _values_from_rows(rows):
        values = []
        for row in rows or []:
            if not row:
                continue
            value = next(iter(row.values()), None)
            if value is not None:
                values.append(str(value))
        return values

    def _fetch_one(self, semantic_model, table, column):
        key = self.key(semantic_model, table, column)
        result = self._execute(single_domain_dax(table, column), semantic_model)
        self._count("columns")
        if result.get("status") != "success":
            self._fail(key, result)
            return None
        values = self._values_from_rows(result.get("rows"))
        self._store(key, values)
        return values

    def _fetch_batch(self, semantic_model, columns):
        """Dominio de varias columnas en una consulta. True si se guardaron todas."""
        result = self._execute(batch_domain_dax(columns), semantic_model)
        self._count("batch_queries")
        if result.get("status") != "success":
            return False
        rows = result.get("rows") or []
        buckets = {index: [] for index in range(len(columns))}
        for row in rows:
            if not row:
                continue
            marker = _row_key(row, BATCH_MARKER)
            value_key = _row_key(row, "Value")
            if marker is None or value_key is None:
                return False  # forma inesperada: mejor consultar columna por columna
            try:
                index = int(float(row[marker]))
            except (TypeError, ValueError):
                return False
            if index not in buckets:
                return False
            if row[value_key] is not None:
                buckets[index].append(str(row[value_key]))
        for index, (table, column) in enumerate(columns):
            self._store(self.key(semantic_model, table, column), buckets[index])
        self._count("columns", len(columns))
        return True

    def get(self, semantic_model, table, column, essential=False):
        """Dominio de la columna (lista de textos, orden de Power BI) o None si
        no se pudo consultar (fallo de XMLA o presupuesto del turno agotado).
        `essential=True` (filtro que el usuario pidió con su columna, mes o año
        del periodo) no está sujeto al presupuesto de exploración."""
        key = self.key(semantic_model, table, column)
        with self._lock:
            entry = self._entries.get(key)
            if self._fresh(entry):
                self._count("hits")
                return entry[1]
            if self._skip_failed(key):
                return None
            if not essential and not self._budget_left():
                self._count("skipped")
                return None
            return self._fetch_one(semantic_model, table, column)

    def prefetch(self, semantic_model, columns):
        """Trae en lote los dominios que faltan de `columns` = [(tabla, columna,
        tipo_de_dato)] (en orden de prioridad). Solo agrupa columnas de texto;
        las demás se consultan cuando se pidan con get(). No devuelve nada: los
        valores se leen después con get()."""
        if self.batch_size <= 1 or not semantic_model or self._batch_failures >= 2:
            return
        with self._lock:
            pending, seen = [], set()
            for item in columns or []:
                table, column = item[0], item[1]
                data_type = item[2] if len(item) > 2 else None
                key = self.key(semantic_model, table, column)
                if key in seen or not is_text_type(data_type):
                    continue
                seen.add(key)
                if self._fresh(self._entries.get(key)) or self._skip_failed(key):
                    continue
                pending.append((table, column))
            for start in range(0, len(pending), self.batch_size):
                chunk = pending[start:start + self.batch_size]
                if len(chunk) < 2:
                    break  # una sola columna: la consulta normal cuando se pida
                if not self._budget_left():
                    break
                if self._fetch_batch(semantic_model, chunk):
                    self._batch_failures = 0
                    continue
                # El lote falló: cada columna por separado (como antes). Si
                # todas responden, el problema era la forma del lote (no una
                # columna inexistente) y cuenta para dejar de usar el lote.
                fetched = [self._fetch_one(semantic_model, table, column) for table, column in chunk
                           if self._budget_left()]
                if len(fetched) == len(chunk) and all(values is not None for values in fetched):
                    self._batch_failures += 1
                break


def domain_cache_for(provider):
    """La caché de dominios del proveedor (se crea la primera vez y se guarda en
    `provider.domain_cache`, así la comparten todos los componentes)."""
    if provider is None:
        return None
    cache = getattr(provider, "domain_cache", None)
    if isinstance(cache, DomainCache):
        return cache
    cache = DomainCache(provider)
    try:
        provider.domain_cache = cache
    except Exception:
        pass
    return cache

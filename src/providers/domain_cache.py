"""
Caché compartida de dominios de columnas (los valores de `VALUES(T[c])`) que se
consultan a Power BI para reconocer valores nombrados en la pregunta
(«urgencias», «nueva eps», «ortopedia»).

Contra Power BI real cada consulta XMLA cuesta ~0,3-1,5 s de ida y vuelta, y
además el servidor recorre y ordena todos los valores distintos de cada columna:
una columna de alta cardinalidad (documentos, números de ingreso, nombres)
cuesta segundos. Turno del propietario del 2026-10-13: UN lote de 9 columnas
(TOPN 2500 de VALUES de cada una, UNION) tardó 20,8 s porque incluía columnas así.
Esta caché:

- guarda el dominio de cada (modelo, tabla, columna) con vida limitada
  (POWERBI_DOMAIN_TTL_S, por defecto 1 hora; 0 = sin vencimiento) y la
  comparten QueryPlanBuilder y BusinessFilterResolver (una sola por proveedor).
  Cada dominio recuerda el TOPN con que se pidió: si devolvió menos valores que
  ese tope es el dominio completo y sirve para cualquier pedido; si no, solo
  para pedidos con un tope igual o menor;
- estima la cardinalidad de las columnas antes de agruparlas: por el nombre
  (identificadores y datos de personas: documento, ingreso, OID, consecutivo,
  historia... son siempre de alta cardinalidad) y con UNA consulta barata
  `EVALUATE ROW("__card0", COUNTROWS(VALUES(T[c1])), ...)` para las demás
  (POWERBI_DOMAIN_CARD_PROBE=1 por defecto; se guarda POWERBI_DOMAIN_CARD_TTL_S,
  por defecto 24 h). En Import, contar valores distintos lo resuelve el motor de
  almacenamiento sin ordenar ni devolver valores: es mucho más barato que el TOPN;
- consulta en LOTE solo columnas de texto de BAJA cardinalidad (hasta
  POWERBI_DOMAIN_LOWCARD = 500 valores distintos) y en lotes pequeños
  (POWERBI_DOMAIN_BATCH columnas por consulta, por defecto 4; 1 = sin lote):
  `EVALUATE UNION(SELECTCOLUMNS(TOPN(...VALUES(T[c1])...), "__columna", 0,
  "Value", [Value]), ...)`. Cada rama es la misma consulta de una columna, así
  que los valores son idénticos; solo se agrupan columnas de texto para que
  UNION no convierta tipos. Las columnas de alta cardinalidad se consultan solas
  y solo si el llamador llega a necesitarlas. Si el lote falla o su resultado no
  tiene la forma esperada, se consulta cada columna por separado;
- `prefetch(..., max_batches=1)` permite buscar de forma incremental: el
  llamador pide el siguiente lote solo cuando lo va a leer y deja de pedir al
  encontrar una coincidencia fuerte;
- cancela las consultas de exploración que superan POWERBI_DOMAIN_TIMEOUT_S
  segundos (por defecto 8; 0 = sin límite; `CommandTimeout` de ADOMD): se sigue
  sin esa columna (dominio no disponible en el turno) y queda en el razonamiento.
  Los filtros que el usuario nombró con su columna y los meses/años del periodo
  (`essential=True`) no tienen límite de tiempo ni de presupuesto;
- limita las consultas de exploración por turno (POWERBI_DOMAIN_BUDGET, por
  defecto 12; 0 = sin límite; un lote cuenta como una): pasado el límite, las
  columnas que faltan no se consultan en ese turno (se tratan como dominio no
  disponible). Los llamadores piden las columnas en orden de plausibilidad;
- un fallo no se guarda como dominio vacío: se reintenta en el turno siguiente
  (dentro del mismo turno no se repite la consulta fallida);
- cuenta consultas, columnas, aciertos y segundos por turno (`turn_stats()`) y
  anota cada consulta lenta (más de POWERBI_DOMAIN_SLOW_S = 2 s) con sus
  columnas y su tiempo, para el razonamiento del turno (`describe_turn()`);
- `background()`: consultas de un hilo de precalentamiento, que no cuentan en el
  turno del usuario ni gastan su presupuesto.

Turnos del propietario del 2026-10-14 (BRIEFING HOSPITALARIO, DEMANDA
INSATISFECHA): la consulta de cardinalidad NO fue barata (3 columnas en 6,40 s;
5 columnas canceladas «a los 13,48 s con límite de 8 s») y la exploración costó
17,55 s de un turno de 25 s cuya respuesta tardó menos de 1 s. Por eso:

- los CÓDIGOS (HCACODIGO, COD_SERV, codcama, NRO_CAMA...: `code_column`) no se
  cuentan ni entran a un lote, y si la pregunta del turno (`begin_turn(question)`)
  no trae un código («403», «UCI-06», «III») tampoco se exploran: ningún valor de
  un código puede ser lo que el usuario nombró (`get` devuelve [] sin consultar;
  un filtro pedido con su columna, `essential=True`, sí se consulta);
- la consulta de cardinalidad tiene su propio límite, corto
  (POWERBI_DOMAIN_CARD_TIMEOUT_S, por defecto 3 s): existe para ser barata; si no
  lo es, se sigue con las reglas por nombre (como cuando falla). Si se cancela o
  tarda más de POWERBI_DOMAIN_SLOW_S, ese modelo no vuelve a contarse durante
  POWERBI_DOMAIN_TTL_S (ni en el turno siguiente) y sus columnas quedan con
  cardinalidad «desconocida» en la caché;
- el tiempo de ABRIR la conexión del modelo (y de esperar el candado de la
  conexión) lo informa PowerBIProvider (`connect_s`, `wait_s`) y se descuenta:
  el «13,48 s con límite de 8 s» eran ~5,5 s abriendo la conexión (fuera del
  CommandTimeout de ADOMD) + 8 s de consulta. Se muestra aparte en el
  razonamiento y no hace «lenta» una consulta.

La consulta de una columna (con el tope histórico de 2500) es exactamente la que
usaba QueryPlanBuilder:

    EVALUATE TOPN(2500, FILTER(SELECTCOLUMNS(VALUES('T'[c]), "Value", 'T'[c]),
                               NOT ISBLANK([Value])), [Value], ASC)
"""
import contextlib
import inspect
import os
import re
import threading
import time
import unicodedata

DEFAULT_LIMIT = 2500
BATCH_MARKER = "__columna"
CARD_MARKER = "__card"
CARD_PROBE_MAX_COLUMNS = 24
_TEXT_TYPES = {"string", "text", "texto", "str"}
_TIMEOUT_WORDS = ("timed out", "timeout", "time out", "tiempo de espera", "tiempo agotado")

# Columnas que en una base hospitalaria son siempre de alta cardinalidad
# (identificadores y datos de personas): nunca entran a un lote. Solo nombres
# inequívocos: «NOMBRE», «TERNOMCOM» (aseguradora) o «INGRESO» (vía de ingreso)
# pueden ser categóricas y las decide la consulta de cardinalidad.
_IDENTIFIER_PARTS = (
    "rownumber", "numdoc", "nrodoc", "documento", "cedula", "identif", "adningreso", "numingreso",
    "noingreso", "nroingreso", "consecutivo", "consec", "historia", "pacnom", "nombrepaciente",
    "pacientenombre", "apellido", "telefon", "celular", "direccion", "correo", "email",
)
_IDENTIFIER_RE = re.compile(r"^oid|oid$|(^|_)id($|_)", re.I)
# Textos de fecha u hora: muchos valores distintos; no entran a un lote (se
# consultan solos si se necesitan).
_DATE_TEXT_PARTS = ("fecha", "hora", "timestamp")
# Códigos (de cama, servicio, aseguradora, diagnóstico...): HCACODIGO,
# GDECODIGO, CODIGO_CIE10, COD_SERV, codcama, NRO_CAMA. Un valor así solo se
# nombra escribiendo el código.
_CODE_RE = re.compile(r"codigo|^cod|cod$|(^|_)(nro|numero|code)(_|$)")
# Palabra de la pregunta que puede ser un código: letras y dígitos mezclados
# («UCI-06», «A12»), un número de 3+ cifras que no es un año («403») o un
# numeral romano («III», como las clasificaciones de triage).
_CODE_TOKEN_RE = re.compile(
    r"^(?=[a-z0-9\-/.]*[a-z])(?=[a-z0-9\-/.]*\d)[a-z0-9][a-z0-9\-/.]*$"
    r"|^\d{3,}$"
    r"|^(?:i{1,3}|iv|v|vi{1,3}|ix)$"      # sin «x» sola: «pacientes x aseguradora»
)
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")


def _env_number(name, default, cast=float):
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return cast(str(raw).strip())
    except ValueError:
        return default


def _env_flag(name, default):
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "si", "sí", "yes", "on")


def _compact(name):
    text = unicodedata.normalize("NFD", str(name or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", text)


def identifier_column(column):
    """¿Identificador o dato de persona (documento, ingreso, OID, consecutivo,
    historia, nombre/apellido de paciente, teléfono...)? Siempre de alta
    cardinalidad: no entra a un lote y no puede ser un calificativo."""
    compact = _compact(column)
    return any(part in compact for part in _IDENTIFIER_PARTS) or bool(_IDENTIFIER_RE.search(str(column or "")))


def likely_high_cardinality(column):
    """Identificadores, personas, códigos y textos de fecha/hora (por el nombre)."""
    compact = _compact(column)
    return (identifier_column(column) or code_column(column)
            or any(part in compact for part in _DATE_TEXT_PARTS))


def _plain(text):
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def code_column(column):
    """¿Columna de códigos (HCACODIGO, COD_SERV, codcama, NRO_CAMA...)? No entra
    a un lote ni a la consulta de cardinalidad y solo se explora si la pregunta
    trae un código (`has_code_token`)."""
    text = re.sub(r"[^a-z0-9]+", "_", _plain(column)).strip("_")
    return bool(text) and bool(_CODE_RE.search(text))


def has_code_token(text):
    """¿La pregunta trae algo que puede ser un código? («cama 403», «UCI-06»,
    «triage III»). Un año («2025») o una cantidad corta («3 meses», «top 10») no."""
    for token in re.split(r"[\s,;:()\[\]{}¿?¡!\"'«»]+", _plain(text)):
        token = token.strip(".-/")
        if token and not _YEAR_RE.match(token) and _CODE_TOKEN_RE.match(token):
            return True
    return False


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


def cardinality_dax(columns):
    """Una fila con la cantidad de valores distintos (blanco incluido) de cada
    columna: "__card0", "__card1"...  Barata: no ordena ni devuelve valores."""
    parts = [
        f'    "{CARD_MARKER}{index}", COUNTROWS(VALUES({table_ref(table)}{column_ref(column)}))'
        for index, (table, column) in enumerate(columns)
    ]
    return "EVALUATE\nROW(\n" + ",\n".join(parts) + "\n)"


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


def _is_timeout(result, elapsed, timeout_s):
    if result.get("timed_out"):
        return True
    message = str(result.get("error") or result.get("message") or "").lower()
    if any(word in message for word in _TIMEOUT_WORDS):
        return True
    return bool(timeout_s) and elapsed >= 0.98 * float(timeout_s)


def _accepts_timeout(provider):
    """¿`provider.execute_dax` recibe `timeout_s`? (los proveedores de prueba no)."""
    method = getattr(provider, "execute_dax", None)
    if method is None:
        return False
    try:
        return "timeout_s" in inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False


def connection_open(provider, semantic_model):
    """¿El proveedor ya tiene abierta la conexión de ese modelo? (el precalentamiento
    en segundo plano nunca abre una conexión: con Interactive Login la ventana de
    inicio de sesión no debe salir de un hilo secundario). Proveedores sin
    `_connections` (pruebas): sí."""
    connections = getattr(provider, "_connections", None)
    if connections is None:
        return True
    checker = getattr(provider, "_is_connection_open", None)
    wanted = str(semantic_model or "").casefold()
    for name, connection in list(connections.items()):
        if str(name).casefold() == wanted:
            try:
                return bool(checker(connection)) if callable(checker) else connection is not None
            except Exception:
                return False
    return False


class DomainCache:
    """Dominios de columnas con TTL, cardinalidad, lotes pequeños, tiempo límite,
    presupuesto por turno y métricas."""

    def __init__(self, provider, ttl_s=None, batch_size=None, turn_budget=None, clock=None,
                 low_cardinality=None, card_probe=None, card_ttl_s=None, timeout_s=None, slow_s=None,
                 timer=None, card_timeout_s=None):
        self.provider = provider
        self.ttl_s = float(ttl_s if ttl_s is not None else _env_number("POWERBI_DOMAIN_TTL_S", 3600.0))
        self.batch_size = int(batch_size if batch_size is not None
                              else _env_number("POWERBI_DOMAIN_BATCH", 4, int))
        self.turn_budget = int(turn_budget if turn_budget is not None
                               else _env_number("POWERBI_DOMAIN_BUDGET", 12, int))
        self.low_cardinality = int(low_cardinality if low_cardinality is not None
                                   else _env_number("POWERBI_DOMAIN_LOWCARD", 500, int))
        self.card_probe = bool(card_probe if card_probe is not None
                               else _env_flag("POWERBI_DOMAIN_CARD_PROBE", True))
        self.card_ttl_s = float(card_ttl_s if card_ttl_s is not None
                                else _env_number("POWERBI_DOMAIN_CARD_TTL_S", 86400.0))
        self.timeout_s = float(timeout_s if timeout_s is not None
                               else _env_number("POWERBI_DOMAIN_TIMEOUT_S", 8.0))
        self.slow_s = float(slow_s if slow_s is not None else _env_number("POWERBI_DOMAIN_SLOW_S", 2.0))
        # La consulta de cardinalidad existe para ser barata: límite propio y corto.
        self.card_timeout_s = float(card_timeout_s if card_timeout_s is not None
                                    else _env_number("POWERBI_DOMAIN_CARD_TIMEOUT_S", 3.0))
        self.clock = clock or time.monotonic
        self.timer = timer or time.perf_counter
        self._entries = {}        # clave -> (momento, [valores como texto], tope TOPN)
        self._cards = {}          # clave -> (momento, valores distintos con el blanco)
        self._slow_columns = set()  # claves cuya consulta venció el tiempo límite
        self._timed_out_at = {}     # clave -> momento del último vencimiento
        self._failed_turn = {}    # clave -> número de turno del fallo (no se reintenta en ese turno)
        self._avoided_turn = set()  # columnas no exploradas en el turno (alta cardinalidad)
        self._card_unknown = {}   # clave -> momento: su cardinalidad no se pudo contar (no se reintenta)
        self._slow_probe = {}     # modelo -> (momento, segundos, ¿cancelada?): no se vuelve a contar
        self._turn_has_code = None  # ¿la pregunta del turno trae un código? (None = no se sabe)
        self.errors = {}          # clave -> detalle del último fallo
        self._lock = threading.RLock()
        self._local = threading.local()
        self._turn_id = 0
        self._in_turn = False
        # Tras dos lotes (o consultas de cardinalidad) fallidos seguidos (p. ej.
        # un servidor que no acepta la forma de la consulta) se dejan de intentar.
        self._batch_failures = 0
        self._probe_failures = 0
        self._probe_failed_turn = None
        self._timeout_ok = _accepts_timeout(provider)
        self.turn = self._empty_stats()
        self.totals = self._empty_stats()

    # ---------------- claves y frescura ----------------
    @staticmethod
    def key(semantic_model, table, column):
        # DAX no distingue mayúsculas en nombres de tablas/columnas/modelos.
        return (str(semantic_model or "").casefold(), str(table or "").casefold(), str(column or "").casefold())

    def _fresh(self, entry, limit=DEFAULT_LIMIT):
        """¿Entrada vigente que sirve para un pedido con ese tope? Un dominio
        completo (menos valores que su tope) sirve para cualquiera."""
        if entry is None or not (self.ttl_s <= 0 or self.clock() - entry[0] < self.ttl_s):
            return False
        values, entry_limit = entry[1], entry[2]
        return len(values) < entry_limit or entry_limit >= int(limit or DEFAULT_LIMIT)

    def cached(self, semantic_model, table, column, limit=DEFAULT_LIMIT):
        """Dominio en caché y vigente (sin consultar), o None."""
        with self._lock:
            entry = self._entries.get(self.key(semantic_model, table, column))
            return entry[1] if self._fresh(entry, limit) else None

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._cards.clear()
            self._card_unknown.clear()
            self._slow_probe.clear()
            self._slow_columns.clear()
            self._timed_out_at.clear()
            self._failed_turn.clear()
            self.errors.clear()

    def __len__(self):
        return len(self._entries)

    # ---------------- cardinalidad ----------------
    def cardinality(self, semantic_model, table, column):
        """Valores distintos conocidos de la columna (blanco incluido) o None."""
        key = self.key(semantic_model, table, column)
        with self._lock:
            entry = self._cards.get(key)
            if entry is not None and (self.card_ttl_s <= 0 or self.clock() - entry[0] < self.card_ttl_s):
                return entry[1]
            dom = self._entries.get(key)
            if dom is not None and len(dom[1]) < dom[2]:
                return len(dom[1])   # dominio completo: su tamaño (sin el blanco)
            return None

    def exceeds(self, semantic_model, table, column, count):
        """¿Se sabe (sin consultar) que la columna tiene más de `count` valores no
        vacíos? Por la consulta de cardinalidad (que cuenta el blanco: se descuenta)
        o por un dominio ya traído."""
        key = self.key(semantic_model, table, column)
        with self._lock:
            entry = self._cards.get(key)
            if entry is not None and (self.card_ttl_s <= 0 or self.clock() - entry[0] < self.card_ttl_s):
                if entry[1] - 1 > count:
                    return True
            dom = self._entries.get(key)
            return dom is not None and len(dom[1]) > count

    def classify(self, semantic_model, table, column):
        """'low' (entra a un lote), 'high' (se consulta sola) o 'unknown'."""
        key = self.key(semantic_model, table, column)
        if key in self._slow_columns:
            return "high"
        card = self.cardinality(semantic_model, table, column)
        if card is not None:
            return "low" if card <= self.low_cardinality else "high"
        dom = self._entries.get(key)
        if dom is not None and len(dom[1]) > self.low_cardinality:
            return "high"
        if identifier_column(column) or code_column(column):
            return "high"
        return "unknown"

    def _fresh_moment(self, moment):
        return moment is not None and (self.ttl_s <= 0 or self.clock() - moment < self.ttl_s)

    def _probe_unknown(self, semantic_model, table, column):
        """¿Ya se intentó contar esta columna y no se pudo (consulta cancelada)?"""
        return self._fresh_moment(self._card_unknown.get(self.key(semantic_model, table, column)))

    def slow_probe(self, semantic_model):
        """(segundos, ¿cancelada?) de la última consulta de cardinalidad lenta del
        modelo si sigue vigente (no se vuelve a contar en ese modelo), o None."""
        entry = self._slow_probe.get(str(semantic_model or "").casefold())
        if entry is None or not self._fresh_moment(entry[0]):
            return None
        return entry[1], entry[2]

    def _probe(self, semantic_model, columns):
        """Cardinalidad de `columns` = [(tabla, columna)] en una consulta barata."""
        if not columns:
            return
        if self._in_turn and self._probe_failed_turn == self._turn_id:
            return
        dax = cardinality_dax(columns)
        result, elapsed, timed_out = self._execute(dax, semantic_model, timeout=True,
                                                   kind="cardinalidad", columns=columns,
                                                   limit_s=self.card_timeout_s or self.timeout_s)
        self._count("card_queries")
        if timed_out or elapsed > self.slow_s:
            # No fue barata (el 2026-10-14: 6,40 s y una cancelada): en este modelo
            # no se vuelve a contar durante POWERBI_DOMAIN_TTL_S; las columnas se
            # deciden por el nombre, como cuando la consulta falla.
            self._slow_probe[str(semantic_model or "").casefold()] = (self.clock(), round(elapsed, 2), timed_out)
        if result.get("status") != "success" or timed_out:
            if not timed_out:
                self._probe_failures += 1
            else:
                now = self.clock()
                for table, column in columns:
                    self._card_unknown[self.key(semantic_model, table, column)] = now
            self._probe_failed_turn = self._turn_id
            return
        rows = result.get("rows") or []
        row = rows[0] if rows else None
        if not row:
            self._probe_failures += 1
            return
        now = self.clock()
        stored = 0
        for index, (table, column) in enumerate(columns):
            value_key = _row_key(row, f"{CARD_MARKER}{index}")
            if value_key is None:
                continue
            try:
                count = int(float(row[value_key] if row[value_key] is not None else 0))
            except (TypeError, ValueError):
                continue
            self._cards[self.key(semantic_model, table, column)] = (now, count)
            stored += 1
        if stored:
            self._probe_failures = 0
        else:
            self._probe_failures += 1

    # ---------------- turno ----------------
    @staticmethod
    def _empty_stats():
        return {"queries": 0, "batch_queries": 0, "card_queries": 0, "columns": 0, "hits": 0,
                "seconds": 0.0, "errors": 0, "skipped": 0, "timeouts": 0, "skipped_slow": 0, "avoided": 0,
                "card_skipped": 0, "connect_seconds": 0.0, "slow": []}

    def begin_turn(self, question=None):
        """Inicio de un turno del chat: reinicia las métricas y el presupuesto.
        `question`: texto del turno (y de la pregunta pendiente si es un botón);
        sin un código en él, las columnas de códigos no se exploran. None (no
        se sabe): se exploran como siempre."""
        with self._lock:
            self._turn_id += 1
            self._in_turn = True
            self._failed_turn.clear()
            self._avoided_turn.clear()
            self._turn_has_code = None if question is None else has_code_token(question)
            self.turn = self._empty_stats()

    def end_turn(self):
        with self._lock:
            self._in_turn = False
            self._failed_turn.clear()
            self._turn_has_code = None
            return self.turn_stats()

    @property
    def turn_has_code(self):
        return self._turn_has_code

    def turn_stats(self):
        stats = dict(self.turn)
        stats["slow"] = list(self.turn["slow"])
        return stats

    @contextlib.contextmanager
    def background(self):
        """Consultas de un hilo de precalentamiento: no cuentan en el turno del
        usuario ni gastan su presupuesto (sí en `totals`)."""
        previous = getattr(self._local, "background", False)
        self._local.background = True
        try:
            yield self
        finally:
            self._local.background = previous

    def _is_background(self):
        return getattr(self._local, "background", False)

    def _count(self, field, amount=1):
        if not self._is_background():
            self.turn[field] += amount
        self.totals[field] += amount

    def note_avoided(self, semantic_model, table, column):
        """El llamador no consultó una columna que sabe inútil (alta cardinalidad):
        se cuenta una vez por turno, para el razonamiento."""
        key = self.key(semantic_model, table, column)
        with self._lock:
            if key in self._avoided_turn:
                return
            self._avoided_turn.add(key)
            self._count("avoided")

    def _budget_left(self):
        if self._is_background() or not self._in_turn or self.turn_budget <= 0:
            return True
        return self.turn["queries"] < self.turn_budget

    def _skip_failed(self, key):
        return self._in_turn and self._failed_turn.get(key) == self._turn_id

    # ---------------- consultas ----------------
    def _execute(self, dax, semantic_model, timeout=False, kind="columna", columns=(), limit_s=None):
        """(resultado, segundos de la consulta, ¿venció el tiempo límite?). Los
        segundos no incluyen abrir la conexión ni esperar su candado (los informa
        PowerBIProvider: `connect_s`, `wait_s`): el CommandTimeout de ADOMD
        tampoco los cuenta y la respuesta los pagaría igual."""
        limit_s = self.timeout_s if limit_s is None else limit_s
        limit = limit_s if (timeout and limit_s > 0 and self._timeout_ok) else None
        started = self.timer()
        try:
            if limit:
                result = self.provider.execute_dax(dax=dax, semantic_model=semantic_model, timeout_s=limit)
            else:
                result = self.provider.execute_dax(dax=dax, semantic_model=semantic_model)
        except Exception as exc:  # proveedores de prueba que lanzan en lugar de devolver error
            result = {"status": "error", "error": str(exc), "error_type": type(exc).__name__}
        total = self.timer() - started
        if not isinstance(result, dict):
            result = {"status": "error", "error": "respuesta inválida"}
        overhead = 0.0
        for name in ("connect_s", "wait_s"):
            try:
                overhead += max(0.0, float(result.get(name) or 0.0))
            except (TypeError, ValueError):
                pass
        overhead = min(overhead, total)
        elapsed = total - overhead
        timed_out = bool(limit) and result.get("status") != "success" and _is_timeout(result, elapsed, limit)
        self._count("seconds", elapsed)
        self._count("connect_seconds", overhead)
        if kind != "cardinalidad":
            self._count("queries")
        if timed_out:
            self._count("timeouts")
        if (elapsed > self.slow_s or timed_out) and not self._is_background():
            self.turn["slow"].append({
                "kind": kind, "seconds": round(elapsed, 2), "timed_out": timed_out,
                "limit_s": limit, "columns": [f"{table}[{column}]" for table, column in columns],
                "connect_s": round(overhead, 2),
            })
        return result, elapsed, timed_out

    def _store(self, key, values, limit):
        self._entries[key] = (self.clock(), values, int(limit))
        self.errors.pop(key, None)
        self._failed_turn.pop(key, None)

    def _fail(self, key, result, timed_out=False):
        message = str(result.get("error") or result.get("message") or "Sin detalle")[:300]
        if timed_out:
            message = (f"consulta de valores cancelada al superar {self.timeout_s:g} s "
                       f"(POWERBI_DOMAIN_TIMEOUT_S): se sigue sin esta columna")
            self._slow_columns.add(key)
            self._timed_out_at[key] = self.clock()
        self.errors[key] = {
            "status": "timeout" if timed_out else result.get("status"),
            "error_type": "timeout" if timed_out else result.get("error_type"),
            "message": message,
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

    def _fetch_one(self, semantic_model, table, column, limit=DEFAULT_LIMIT, timeout=True):
        key = self.key(semantic_model, table, column)
        result, _, timed_out = self._execute(single_domain_dax(table, column, limit), semantic_model,
                                             timeout=timeout, columns=[(table, column)])
        self._count("columns")
        if result.get("status") != "success":
            self._fail(key, result, timed_out)
            return None
        values = self._values_from_rows(result.get("rows"))
        self._store(key, values, limit)
        return values

    def _fetch_batch(self, semantic_model, columns, limit=DEFAULT_LIMIT):
        """Dominio de varias columnas en una consulta. True si se guardaron todas,
        False si falló la forma, "timeout" si venció el tiempo límite."""
        result, _, timed_out = self._execute(batch_domain_dax(columns, limit), semantic_model,
                                             timeout=True, kind="lote", columns=columns)
        self._count("batch_queries")
        if timed_out:
            return "timeout"
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
            self._store(self.key(semantic_model, table, column), buckets[index], limit)
        self._count("columns", len(columns))
        return True

    def get(self, semantic_model, table, column, essential=False, limit=None):
        """Dominio de la columna (lista de textos, orden de Power BI) o None si
        no se pudo consultar (fallo de XMLA, tiempo límite vencido o presupuesto
        del turno agotado). `limit`: tope TOPN (por defecto 2500, el histórico);
        un tope menor basta para saber si el dominio pasa de cierto tamaño.
        `essential=True` (filtro que el usuario pidió con su columna, mes o año
        del periodo) no está sujeto al presupuesto ni al tiempo límite.
        Una columna de códigos (`code_column`) en un turno cuya pregunta no trae
        ningún código devuelve [] sin consultar (ningún valor suyo coincide con
        lo nombrado; «uci» no es la cama UCI-06)."""
        limit = int(limit or DEFAULT_LIMIT)
        key = self.key(semantic_model, table, column)
        if not essential and self._turn_has_code is False and code_column(column):
            self.note_avoided(semantic_model, table, column)
            return []
        with self._lock:
            entry = self._entries.get(key)
            if self._fresh(entry, limit):
                self._count("hits")
                return entry[1]
            if self._skip_failed(key) and not (essential and key in self._timed_out_at):
                return None   # (un filtro esencial sí reintenta, sin límite, lo que venció el tiempo)
            if not essential and self._unverifiable_high(semantic_model, table, column):
                # Por el nombre es de alta cardinalidad (fecha/hora en texto,
                # código, identificador) y en este modelo no se pudo contar
                # barato: consultarla sola costaría segundos (o vencería el
                # límite) para un valor que nadie nombra así.
                self.note_avoided(semantic_model, table, column)
                return []
            if not essential and self._recently_timed_out(key):
                # Venció el tiempo límite hace poco: no se vuelve a esperar en cada
                # turno (se reintenta al pasar POWERBI_DOMAIN_TTL_S).
                self._count("skipped_slow")
                return None
            if not essential and not self._budget_left():
                self._count("skipped")
                return None
            return self._fetch_one(semantic_model, table, column, limit, timeout=not essential)

    def _unverifiable_high(self, semantic_model, table, column):
        """¿Columna de alta cardinalidad por el nombre cuya cardinalidad no se
        conoce porque en su modelo la consulta de cardinalidad no es barata (o
        se canceló para ella)? (Un código con un código en la pregunta, no.)"""
        if not likely_high_cardinality(column) or (code_column(column) and self._turn_has_code):
            return False
        key = self.key(semantic_model, table, column)
        if key in self._entries or self.cardinality(semantic_model, table, column) is not None:
            return False
        return self.slow_probe(semantic_model) is not None or self._probe_unknown(semantic_model, table, column)

    def _recently_timed_out(self, key):
        moment = self._timed_out_at.get(key)
        if moment is None:
            return False
        if self.ttl_s > 0 and self.clock() - moment >= self.ttl_s:
            self._timed_out_at.pop(key, None)
            return False
        return True

    def prefetch(self, semantic_model, columns, limit=None, max_batches=None, lead=False):
        """Trae en lote los dominios que faltan de `columns` = [(tabla, columna,
        tipo_de_dato)] (en orden de prioridad). Solo agrupa columnas de texto de
        baja cardinalidad (conocida o estimada); las demás se consultan solas
        cuando se pidan con get(). `max_batches`: cuántos lotes traer (None =
        todos; 1 = solo el siguiente, para buscar de forma incremental). `lead`:
        solo si la PRIMERA columna entra a un lote (si no, el llamador la
        consulta sola y vuelve a pedir el siguiente lote al avanzar). No
        devuelve nada: los valores se leen después con get()."""
        if self.batch_size <= 1 or not semantic_model or self._batch_failures >= 2:
            return
        limit = int(limit or DEFAULT_LIMIT)
        first = self.key(semantic_model, columns[0][0], columns[0][1]) if columns else None
        with self._lock:
            pending, seen = [], set()
            for item in columns or []:
                table, column = item[0], item[1]
                data_type = item[2] if len(item) > 2 else None
                key = self.key(semantic_model, table, column)
                if key in seen or not is_text_type(data_type):
                    continue
                seen.add(key)
                if self._fresh(self._entries.get(key), limit) or self._skip_failed(key):
                    continue
                pending.append((table, column))
            if len(pending) < 2:
                return  # una sola columna: la consulta normal cuando se pida
            # Cardinalidad de las que no se conocen (una consulta barata para todas).
            # (Contar solo las de los próximos lotes se midió: más consultas en
            # las búsquedas largas y ninguna ganancia en los turnos del 2026-10-14.)
            if self.card_probe and self._probe_failures < 2:
                unknown = [(t, c) for t, c in pending
                           if self.classify(semantic_model, t, c) == "unknown"
                           and not self._probe_unknown(semantic_model, t, c)]
                if unknown:
                    if self.slow_probe(semantic_model) is not None:
                        self._count("card_skipped")   # en este modelo no es barata: por el nombre
                    else:
                        self._probe(semantic_model, unknown[:CARD_PROBE_MAX_COLUMNS])
            batchable = [
                (t, c) for t, c in pending
                if self.classify(semantic_model, t, c) == "low"
                or (self.classify(semantic_model, t, c) == "unknown" and not likely_high_cardinality(c))
            ]
            if lead and (not batchable or self.key(semantic_model, *batchable[0]) != first):
                return
        done = 0
        for start in range(0, len(batchable), self.batch_size):
            if max_batches is not None and done >= max_batches:
                break
            with self._lock:
                chunk = [(t, c) for t, c in batchable[start:start + self.batch_size]
                         if not self._fresh(self._entries.get(self.key(semantic_model, t, c)), limit)]
                if len(chunk) < 2:
                    break  # una sola columna: la consulta normal cuando se pida
                if not self._budget_left():
                    break
                done += 1
                outcome = self._fetch_batch(semantic_model, chunk, limit)
                if outcome is True:
                    self._batch_failures = 0
                    continue
                if outcome == "timeout":
                    # El lote venció el tiempo: no se sabe cuál columna es la lenta.
                    # Ninguna vuelve a un lote (si no, el siguiente lote incremental
                    # la repetiría); cada una se pedirá sola, con su propio límite,
                    # cuando el llamador la necesite.
                    self._slow_columns.update(self.key(semantic_model, t, c) for t, c in chunk)
                    break
                # El lote falló: cada columna por separado (como antes). Si
                # todas responden, el problema era la forma del lote (no una
                # columna inexistente) y cuenta para dejar de usar el lote.
                fetched = [self._fetch_one(semantic_model, table, column, limit) for table, column in chunk
                           if self._budget_left()]
                if len(fetched) == len(chunk) and all(values is not None for values in fetched):
                    self._batch_failures += 1
                break

    # ---------------- razonamiento ----------------
    def describe_turn(self, stats=None):
        """Líneas del paso «Consultas de exploración a Power BI» del turno, o None
        si no hubo consultas: totales y, por cada consulta lenta (más de
        POWERBI_DOMAIN_SLOW_S) o cancelada, sus columnas y su tiempo."""
        stats = stats or self.turn_stats()
        if not (stats["queries"] or stats["skipped"] or stats.get("card_queries") or stats.get("avoided")
                or stats.get("skipped_slow") or stats.get("card_skipped")):
            return None
        line = (
            f"{stats['queries']} consulta(s) de valores de columnas"
            + (f" ({stats['batch_queries']} en lote)" if stats["batch_queries"] else "")
            + f" · {stats['columns']} columna(s) · {stats['seconds']:.2f} s"
            + f" · {stats['hits']} lectura(s) desde caché"
        )
        extra = []
        if stats.get("card_queries"):
            extra.append(f"{stats['card_queries']} consulta(s) de cardinalidad (cuántos valores tiene cada columna)")
        if stats.get("card_skipped"):
            extra.append(
                "sin consulta de cardinalidad: en este modelo no fue barata (se decide por el nombre de la columna)"
            )
        if stats.get("avoided"):
            extra.append(
                f"{stats['avoided']} columna(s) sin explorar (identificadores, códigos sin un código en la "
                "pregunta o más valores de los que un calificativo puede nombrar)"
            )
        if stats["errors"]:
            extra.append(f"{stats['errors']} con error")
        if stats.get("timeouts"):
            extra.append(f"{stats['timeouts']} cancelada(s) por tiempo")
        if stats.get("skipped_slow"):
            extra.append(
                f"{stats['skipped_slow']} columna(s) sin consultar porque hace poco superaron "
                f"{self.timeout_s:g} s"
            )
        if stats["skipped"]:
            extra.append(
                f"{stats['skipped']} omitida(s) por el límite de {self.turn_budget} consultas de exploración"
            )
        lines = [line]
        if extra:
            lines.append(" · ".join(extra))
        if stats.get("connect_seconds", 0) >= 0.5:
            lines.append(
                f"además {stats['connect_seconds']:.2f} s para abrir la conexión con Power BI (o esperar a que "
                "se liberara): no cuentan en el límite de tiempo de las consultas y la respuesta los pagaría igual"
            )
        for item in stats.get("slow") or []:
            names = ", ".join(item["columns"][:8]) + ("…" if len(item["columns"]) > 8 else "")
            what = {"lote": "lote", "cardinalidad": "cardinalidad", "columna": "columna"}.get(item["kind"], item["kind"])
            opening = (f" (+ {item['connect_s']:.2f} s abriendo la conexión)"
                       if (item.get("connect_s") or 0) >= 0.5 else "")
            if item.get("timed_out"):
                after = {
                    "lote": "sus columnas se consultan por separado si se necesitan",
                    "cardinalidad": "se siguió sin saber su cardinalidad (no se vuelve a contar en este modelo)",
                }.get(item["kind"], "se siguió sin esa columna")
                lines.append(
                    f"consulta de {what} cancelada a los {item['seconds']:.2f} s "
                    f"(límite {item.get('limit_s') or self.timeout_s:g} s){opening}: {names} — {after}"
                )
            else:
                note = (" — no se vuelve a contar en este modelo (se decide por el nombre)"
                        if item["kind"] == "cardinalidad" else "")
                lines.append(f"consulta lenta de {what} ({item['seconds']:.2f} s){opening}: {names}{note}")
        return lines


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

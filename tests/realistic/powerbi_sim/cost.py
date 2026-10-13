"""
Modelo de coste de Power BI real para el simulador (consultas XMLA).

El simulador responde en milisegundos con tablas pequeñas, así que no reproduce
que en Power BI real una consulta de dominio (`TOPN(2500, VALUES(T[c]))`) sobre
una columna de alta cardinalidad (documentos, números de ingreso, nombres) cueste
segundos, ni que un lote UNION que la incluya concentre ese coste (turno del
propietario del 2026-10-13: un lote de 9 columnas tardó 20,8 s).

Coste estimado de una consulta = base (latencia de ida y vuelta XMLA)
    + por cada rama `VALUES(T[c])` de dominio (TOPN/SELECTCOLUMNS):
          columna_ms + cardinalidad_real × valor_us + min(TOPN, cardinalidad_real) × fila_us
    + por cada `COUNTROWS(VALUES(T[c]))` / `DISTINCTCOUNT(T[c])` (cardinalidad):
          cardinalidad_real × conteo_us        (motor de almacenamiento: barato)
    + filas devueltas de cualquier otra consulta × fila_us

La cardinalidad «real» se estima desde los datos simulados:
- valor explícito en SIM_DAX_CARDINALIDAD («TABLA[COLUMNA]=N;...», sin
  distinguir mayúsculas) o en `overrides`;
- columnas de identificadores/personas (documento, ingreso, OID, consecutivo,
  historia, nombre de paciente...) o casi únicas en el simulador (distintos ≥
  50 % de las filas): filas del simulador × SIM_DAX_ESCALA (en real las tablas
  tienen muchas más filas que en el simulador y estas columnas crecen con ellas);
- el resto (categóricas): los valores distintos del simulador (no crecen con la tabla).

Parámetros (variables de entorno o `CostModel(**params)`), calibrados para que
el lote local equivalente al del propietario cueste ~20 s:

    SIM_DAX_BASE_MS        500    base por consulta (si SIM_DAX_LATENCY_MS > 0, esa)
    SIM_DAX_COLUMNA_MS     30     sobrecoste por rama de dominio
    SIM_DAX_VALOR_US       100    µs por valor distinto que TOPN/VALUES recorre y ordena
    SIM_DAX_FILA_US        100    µs por fila devuelta
    SIM_DAX_CONTEO_US      0.5    µs por valor distinto en COUNTROWS(VALUES())
    SIM_DAX_ESCALA         50     filas reales por fila simulada (columnas que crecen con la tabla)

Solo se usa cuando SIM_DAX_COST=1 (o `adomd.install(..., cost_model=True)`):
entonces cada consulta del registro trae `cost_ms` (estimado total) y
`cost_detail`, la espera simulada (SIM_DAX_LATENCY_MS > 0) dura ese coste y un
`CommandTimeout` menor que el coste cancela la consulta como lo haría ADOMD.
"""
import os
import re

from .metadata import key, normalize_text

_REF = r"(?:'(?:[^']|'')+'|[A-Za-z_][\w ]*?)\[(?:[^\]]|\]\])+\]"
_VALUES_RE = re.compile(r"VALUES\(\s*(" + _REF + r")\s*\)", re.I)
_DISTINCTCOUNT_RE = re.compile(r"DISTINCTCOUNT\(\s*(" + _REF + r")\s*\)", re.I)
_TOPN_RE = re.compile(r"TOPN\(\s*(\d+)", re.I)
_SPLIT_RE = re.compile(r"^'?(.*?)'?\[(.*)\]$", re.S)

# Columnas que en una base hospitalaria real crecen con la tabla (identificadores y personas).
_GROWING_PARTS = (
    "rownumber", "numdoc", "docume", "cedula", "identif", "adningreso", "ningreso", "numingreso",
    "consec", "historia", "pacnom", "nombrepaciente", "apell", "telefon", "direcc", "correo", "email",
)
_GROWING_RE = re.compile(r"^oid|oid$|^id$|^id_|_id$", re.I)

DEFAULTS = {
    "base_ms": 500.0,
    "columna_ms": 30.0,
    "valor_us": 100.0,
    "fila_us": 100.0,
    "conteo_us": 0.5,
    "escala": 50.0,
}
_ENV = {
    "base_ms": "SIM_DAX_BASE_MS",
    "columna_ms": "SIM_DAX_COLUMNA_MS",
    "valor_us": "SIM_DAX_VALOR_US",
    "fila_us": "SIM_DAX_FILA_US",
    "conteo_us": "SIM_DAX_CONTEO_US",
    "escala": "SIM_DAX_ESCALA",
}


def cost_model_enabled():
    return str(os.getenv("SIM_DAX_COST") or "").strip().lower() in ("1", "true", "si", "sí", "yes")


def _env_float(name, default):
    raw = os.getenv(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def parse_overrides(text):
    """«TABLA[COLUMNA]=N;OTRA[COL]=M» -> {(tabla, columna): N} (claves normalizadas)."""
    out = {}
    for part in str(text or "").split(";"):
        if "=" not in part:
            continue
        ref, _, number = part.rpartition("=")
        match = _SPLIT_RE.match(ref.strip())
        if not match:
            continue
        try:
            out[(normalize_text(match.group(1)), normalize_text(match.group(2)))] = int(float(number))
        except ValueError:
            continue
    return out


def _split_ref(ref):
    match = _SPLIT_RE.match(ref.strip())
    if not match:
        return None, None
    return match.group(1).replace("''", "'"), match.group(2).replace("]]", "]")


class CostModel:

    def __init__(self, simulator, overrides=None, **params):
        self.sim = simulator
        self.params = {name: _env_float(_ENV[name], value) for name, value in DEFAULTS.items()}
        self.params.update({k: float(v) for k, v in params.items() if v is not None})
        self.overrides = parse_overrides(os.getenv("SIM_DAX_CARDINALIDAD"))
        for (table, column), number in (overrides or {}).items():
            self.overrides[(normalize_text(table), normalize_text(column))] = int(number)
        self._cards = {}

    # ---------- cardinalidad «real» estimada ----------
    def real_cardinality(self, model, table, column):
        cache_key = (str(model).casefold(), normalize_text(table), normalize_text(column))
        if cache_key in self._cards:
            return self._cards[cache_key]
        card = self.overrides.get(cache_key[1:])
        if card is None:
            card = self._estimate(model, table, column)
        self._cards[cache_key] = card
        return card

    def _estimate(self, model, table, column):
        try:
            runtime = self.sim.runtime(model)
            store = runtime.store(table)
            values = store.column(key(column))
        except Exception:  # noqa: BLE001 - tabla/columna inexistente: la consulta fallará igual
            return 0
        rows = store.rowcount or 0
        distinct = len({repr(v) for v in values if v is not None})
        compact = normalize_text(column).replace(" ", "").replace("_", "")
        growing = any(part in compact for part in _GROWING_PARTS) or bool(_GROWING_RE.search(str(column)))
        if growing or (rows >= 20 and distinct >= 0.5 * rows):
            return int(round(max(rows, distinct) * self.params["escala"]))
        return distinct

    # ---------- coste de una consulta ----------
    def estimate(self, model, dax, rows_returned, base_ms=None):
        """{"cost_ms": total, "base_ms", "detail": [(tipo, 'T'[c], cardinalidad, ms)]}."""
        p = self.params
        base = p["base_ms"] if base_ms is None else float(base_ms)
        text = str(dax or "")
        detail = []
        branch_rows = 0
        for match in _VALUES_RE.finditer(text):
            table, column = _split_ref(match.group(1))
            if table is None:
                continue
            card = self.real_cardinality(model, table, column)
            before = text[:match.start()].rstrip().upper()
            if before.endswith("COUNTROWS("):
                ms = card * p["conteo_us"] / 1000.0
                detail.append(("cardinalidad", match.group(1), card, round(ms, 1)))
                continue
            tops = _TOPN_RE.findall(text[:match.start()])
            limit = int(tops[-1]) if tops else card
            returned = min(limit, card)
            branch_rows += returned
            ms = p["columna_ms"] + card * p["valor_us"] / 1000.0 + returned * p["fila_us"] / 1000.0
            detail.append(("dominio", match.group(1), card, round(ms, 1)))
        for match in _DISTINCTCOUNT_RE.finditer(text):
            table, column = _split_ref(match.group(1))
            if table is None or "__card" not in text:
                continue   # solo la consulta de cardinalidad; en medidas es parte del cálculo
            card = self.real_cardinality(model, table, column)
            ms = card * p["conteo_us"] / 1000.0
            detail.append(("cardinalidad", match.group(1), card, round(ms, 1)))
        extra_rows = 0 if branch_rows else int(rows_returned or 0)
        total = base + sum(item[3] for item in detail) + extra_rows * p["fila_us"] / 1000.0
        return {"cost_ms": round(total, 1), "base_ms": base, "detail": detail}

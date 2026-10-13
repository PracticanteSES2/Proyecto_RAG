"""
Pruebas de la caché de dominios de columnas (src/providers/domain_cache.py):
caché con vencimiento, lote de varias columnas en una consulta (validado con el
simulador de Power BI de tests/realistic), vuelta a la consulta por columna si
el lote falla, presupuesto de consultas por turno, integración con
QueryPlanBuilder/BusinessFilterResolver y la línea del razonamiento.

Ejecutar:  python -m tests.perf.test_domain_cache      (o con pytest)

No necesitan data/, Qdrant ni Ollama (el simulador usa los modelos sintéticos
versionados en tests/realistic/synthetic_models).
"""
import datetime as dt
import os
import sys
import types
from pathlib import Path

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.providers.domain_cache import (  # noqa: E402
    DomainCache,
    batch_domain_dax,
    domain_cache_for,
    single_domain_dax,
)

CONSOLIDADO = "CONSOLIDADO DE ATENCIONES INSTITUCIONALES"
TEXT_COLUMNS = [
    ("CIRUGIAS", "ESPECIALIDAD", "Text"),
    ("CIRUGIAS", "ESTADO_CIRUGIA", "Text"),
    ("ASEGURADORAS", "NOMBRE", "Text"),
    ("DIM_SERVICIO", "SERVICIO_HOMOLOGADO", "Text"),
    ("EGRESOS", "SEXO", "Text"),
]
_CACHE = {}


# ----------------------------------------------------------------------------
# Proveedores
# ----------------------------------------------------------------------------

def simulated_provider():
    """PowerBIProvider REAL contra el simulador (cliente ADOMD falso)."""
    if "provider" in _CACHE:
        return _CACHE["provider"], _CACHE["backend"]
    if "dotenv" not in sys.modules:   # PowerBIProvider llama load_dotenv al importarse: nunca leer .env
        stub = types.ModuleType("dotenv")
        stub.load_dotenv = lambda *a, **k: False
        sys.modules["dotenv"] = stub
    from tests.realistic.powerbi_sim import PowerBISimulator, adomd
    simulator = PowerBISimulator([(REPO_ROOT / "tests" / "realistic" / "synthetic_models", "synthetic")],
                                 today=dt.date(2026, 9, 30))
    backend = adomd.install(simulator, latency_ms=0)
    adomd_dir = REPO_ROOT / "tests" / "sim" / "fixtures" / "adomd"
    os.environ.update(POWERBI_XMLA_ENDPOINT="powerbi://api.powerbi.com/v1.0/myorg/SIMULADO",
                      POWERBI_SEMANTIC_MODEL=CONSOLIDADO, ADOMD_PATH=str(adomd_dir), IDENTITY_PATH=str(adomd_dir))
    from src.providers.powerbi_provider import PowerBIProvider
    provider = PowerBIProvider()
    _CACHE.update(provider=provider, backend=backend)
    return provider, backend


class CountingProvider:
    """Proveedor de prueba: dominios fijos por columna; cuenta las consultas."""

    def __init__(self, domains, fail_batch=False, fail_columns=(), down=False):
        self.domains = domains          # {(tabla, columna): [valores]}
        self.fail_batch = fail_batch
        self.fail_columns = set(fail_columns)
        self.down = down
        self.queries = []

    def execute_dax(self, dax, semantic_model=None):
        self.queries.append(dax)
        if self.down:
            return {"status": "error", "error": "XMLA caído", "error_type": "AdomdConnectionException"}
        refs = [(t, c) for (t, c) in self.domains if f"'{t}'[{c}]" in dax]
        if "UNION(" in dax:
            if self.fail_batch or any(ref in self.fail_columns for ref in refs):
                return {"status": "error", "error": "lote no soportado"}
            rows = []
            order = sorted(refs, key=lambda ref: dax.index(f"'{ref[0]}'[{ref[1]}]"))
            for index, ref in enumerate(order):
                rows += [{"[__columna]": index, "[Value]": v} for v in self.domains[ref]]
            return {"status": "success", "rows": rows}
        ref = refs[0]
        if ref in self.fail_columns:
            return {"status": "error", "error": "columna no encontrada"}
        return {"status": "success", "rows": [{"[Value]": v} for v in self.domains[ref]]}


DOMAINS = {
    ("T", "A"): ["URGENCIAS", "HOSPITALIZACION"],
    ("T", "B"): ["SURA", "NUEVA EPS"],
    ("T", "C"): ["M", "F"],
    ("T", "N"): [1, 2, 3],
}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# ----------------------------------------------------------------------------
# Caché, lote y presupuesto
# ----------------------------------------------------------------------------

def test_get_caches_and_ttl_expires():
    provider, clock = CountingProvider(DOMAINS), Clock()
    cache = DomainCache(provider, ttl_s=60, clock=clock)
    assert cache.get("M", "T", "A") == ["URGENCIAS", "HOSPITALIZACION"]
    assert cache.get("m", "t", "a") == ["URGENCIAS", "HOSPITALIZACION"]   # DAX no distingue mayúsculas
    assert len(provider.queries) == 1
    assert provider.queries[0] == single_domain_dax("T", "A")
    clock.now += 61
    cache.get("M", "T", "A")
    assert len(provider.queries) == 2, "vencido el TTL se vuelve a consultar"
    forever = DomainCache(CountingProvider(DOMAINS), ttl_s=0, clock=clock)
    forever.get("M", "T", "A")
    clock.now += 10 ** 6
    forever.get("M", "T", "A")
    assert len(forever.provider.queries) == 1, "ttl 0 = sin vencimiento"


def test_single_query_is_the_historic_one():
    dax = single_domain_dax("CIRUGIAS", "ESTADO_CIRUGIA")
    assert dax == ("EVALUATE\nTOPN(\n    2500,\n    FILTER(\n        SELECTCOLUMNS(\n            VALUES('CIRUGIAS'"
                   "[ESTADO_CIRUGIA]),\n            \"Value\", 'CIRUGIAS'[ESTADO_CIRUGIA]\n        ),\n"
                   "        NOT ISBLANK([Value])\n    ),\n    [Value], ASC\n)")


def test_prefetch_batches_text_columns_only():
    provider = CountingProvider(DOMAINS)
    cache = DomainCache(provider, ttl_s=0, batch_size=12)
    cache.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text"), ("T", "C", "String"), ("T", "N", "Integer")])
    assert len(provider.queries) == 1 and "UNION(" in provider.queries[0]
    assert "'T'[N]" not in provider.queries[0], "una columna numérica no entra al lote (UNION convertiría tipos)"
    assert cache.get("M", "T", "B") == ["SURA", "NUEVA EPS"]
    assert cache.get("M", "T", "C") == ["M", "F"]
    assert len(provider.queries) == 1
    assert cache.get("M", "T", "N") == ["1", "2", "3"]
    assert len(provider.queries) == 2
    # Ya en caché: no se vuelve a consultar; una sola columna pendiente no hace lote.
    cache.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text")])
    assert len(provider.queries) == 2


def test_batch_size_splits_and_one_disables():
    provider = CountingProvider(DOMAINS)
    cache = DomainCache(provider, ttl_s=0, batch_size=2)
    cache.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text"), ("T", "C", "Text")])
    assert len(provider.queries) == 1, "3 columnas con lote de 2: un lote y la última queda para get()"
    off = DomainCache(CountingProvider(DOMAINS), ttl_s=0, batch_size=1)
    off.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text")])
    assert off.provider.queries == []


def test_failed_batch_falls_back_to_single_queries():
    provider = CountingProvider(DOMAINS, fail_columns={("T", "B")})
    cache = DomainCache(provider, ttl_s=0)
    cache.begin_turn()
    cache.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text"), ("T", "C", "Text")])
    # lote fallido + una consulta por columna
    assert len(provider.queries) == 4
    assert cache.get("M", "T", "A") == ["URGENCIAS", "HOSPITALIZACION"]
    assert cache.get("M", "T", "B") is None and cache.errors
    assert len(provider.queries) == 4, "en el mismo turno no se reintenta la columna fallida"
    cache.end_turn()
    cache.begin_turn()
    assert cache.get("M", "T", "B") is None
    assert len(provider.queries) == 5, "en el turno siguiente sí se reintenta"
    assert cache._batch_failures == 0, "una columna inexistente no desactiva el lote"


def test_unsupported_batch_shape_is_disabled_after_two_failures():
    domains = {**DOMAINS, ("X", "Y"): ["Z"], ("X", "W"): ["Q"], ("X", "V"): ["R"]}
    provider = CountingProvider(domains, fail_batch=True)
    cache = DomainCache(provider, ttl_s=0)
    cache.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text")])
    cache.prefetch("M", [("T", "C", "Text"), ("X", "Y", "Text")])
    assert cache._batch_failures == 2
    assert cache.get("M", "X", "Y") == ["Z"], "tras el lote fallido cada columna se consultó por separado"
    before = len(provider.queries)
    cache.prefetch("M", [("X", "W", "Text"), ("X", "V", "Text")])
    assert len(provider.queries) == before, "tras dos lotes rechazados ya no se intenta el lote"
    assert cache.get("M", "X", "W") == ["Q"]


def test_unexpected_batch_result_is_not_trusted():
    class Weird(CountingProvider):
        def execute_dax(self, dax, semantic_model=None):
            self.queries.append(dax)
            if "UNION(" in dax:
                return {"status": "success", "rows": [{"[Value]": "X"}]}   # sin __columna
            return {"status": "success", "rows": [{"[Value]": "OK"}]}
    provider = Weird(DOMAINS)
    cache = DomainCache(provider, ttl_s=0)
    cache.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text")])
    assert cache.get("M", "T", "A") == ["OK"], "un resultado sin __columna no se usa: consulta por columna"


def test_turn_budget_skips_and_counts():
    provider = CountingProvider(DOMAINS)
    cache = DomainCache(provider, ttl_s=0, turn_budget=2, batch_size=1)
    cache.begin_turn()
    assert cache.get("M", "T", "A") and cache.get("M", "T", "B")
    assert cache.get("M", "T", "C") is None, "presupuesto agotado"
    assert cache.get("M", "T", "N", essential=True) == ["1", "2", "3"],         "un filtro pedido con su columna (o el periodo) no está sujeto al presupuesto"
    stats = cache.end_turn()
    assert stats["queries"] == 3 and stats["skipped"] == 1 and stats["columns"] == 3
    cache.begin_turn()
    assert cache.get("M", "T", "C") == ["M", "F"], "el presupuesto es por turno"
    assert cache.get("M", "T", "A") and cache.turn_stats()["hits"] == 1
    # Fuera de un turno del chat (pruebas, scripts) no hay límite.
    cache.end_turn()
    unlimited = DomainCache(CountingProvider(DOMAINS), ttl_s=0, turn_budget=1, batch_size=1)
    assert all(unlimited.get("M", "T", c) for c in ("A", "B", "C"))


def test_domain_cache_for_is_shared_per_provider():
    provider = CountingProvider(DOMAINS)
    assert domain_cache_for(provider) is domain_cache_for(provider)
    assert domain_cache_for(None) is None


# ----------------------------------------------------------------------------
# Lote contra el simulador de Power BI (PowerBIProvider real)
# ----------------------------------------------------------------------------

def test_batch_values_identical_to_single_queries_in_simulator():
    provider, backend = simulated_provider()
    single = DomainCache(provider, ttl_s=0, batch_size=1)
    expected = {(t, c): single.get(CONSOLIDADO, t, c) for t, c, _ in TEXT_COLUMNS}
    assert all(expected.values()), expected
    batched = DomainCache(provider, ttl_s=0, batch_size=12)
    before = len(backend.log["dax"])
    batched.prefetch(CONSOLIDADO, TEXT_COLUMNS)
    assert len(backend.log["dax"]) == before + 1, "una sola consulta para todas las columnas"
    entry = backend.log["dax"][-1]
    assert not entry.get("error"), entry.get("error")
    assert entry["dax"] == batch_domain_dax([(t, c) for t, c, _ in TEXT_COLUMNS])
    for (t, c), values in expected.items():
        assert batched.get(CONSOLIDADO, t, c) == values, (t, c)
    assert len(backend.log["dax"]) == before + 1


def test_live_query_listener_hears_each_real_query_not_cache_hits():
    """El razonamiento en vivo (PowerBIProvider.query_listener) recibe un aviso
    por consulta real a Power BI (el lote es una) y ninguno por lecturas de caché."""
    provider, backend = simulated_provider()
    heard = []
    previous = getattr(provider, "query_listener", None)
    provider.query_listener = lambda model, dax: heard.append(dax)
    try:
        cache = DomainCache(provider, ttl_s=0, batch_size=12)
        before = len(backend.log["dax"])
        cache.prefetch(CONSOLIDADO, TEXT_COLUMNS)
        for table, column, _ in TEXT_COLUMNS:
            cache.get(CONSOLIDADO, table, column)
        cache.get(CONSOLIDADO, "EGRESOS", "DIAS_ESTANCIA")   # numérica: consulta individual
        cache.get(CONSOLIDADO, "EGRESOS", "DIAS_ESTANCIA")   # ya en caché
    finally:
        provider.query_listener = previous
    assert len(heard) == len(backend.log["dax"]) - before == 2, heard
    assert "UNION(" in heard[0]


def test_simulated_latency_option():
    from tests.realistic.powerbi_sim import adomd
    _, backend = simulated_provider()
    previous = os.environ.get("SIM_DAX_LATENCY_MS")
    os.environ["SIM_DAX_LATENCY_MS"] = "25"
    try:
        slow = adomd.SimulatorBackend(backend.sim)
    finally:
        if previous is None:
            os.environ.pop("SIM_DAX_LATENCY_MS", None)
        else:
            os.environ["SIM_DAX_LATENCY_MS"] = previous
    assert slow.config["latency_ms"] == 25.0
    import time
    started = time.perf_counter()
    slow.execute(CONSOLIDADO, 'EVALUATE ROW("v", 1)')
    assert time.perf_counter() - started >= 0.02
    assert slow.log["dax"][-1]["latency_ms"] == 25.0
    assert adomd.SimulatorBackend(backend.sim, latency_ms=0).config["latency_ms"] == 0.0


# ----------------------------------------------------------------------------
# Integración: planificador, filtros de negocio y razonamiento
# ----------------------------------------------------------------------------

def _bare_builder(provider, static=None, types_by_column=None):
    from src.semantic.query_plan_builder import QueryPlanBuilder
    builder = QueryPlanBuilder.__new__(QueryPlanBuilder)
    builder.powerbi_provider = provider
    builder.value_cache = {}
    builder.domain_errors = {}
    builder.static_values = static or {}
    builder._raw_column_type_cache = {"m": types_by_column or {}}
    return builder


def test_builder_merges_static_values_and_shares_cache_with_business_resolver():
    from src.semantic.business_filter_resolver import BusinessFilterResolver
    provider = CountingProvider(DOMAINS)
    builder = _bare_builder(provider, static={("m", "t", "a"): ["URGENCIAS ADULTOS", "URGENCIAS"]})
    values = builder._get_values("M", "T", "A")
    assert values == ["URGENCIAS ADULTOS", "URGENCIAS", "HOSPITALIZACION"]
    assert builder._get_values("M", "T", "A") is values
    resolver = BusinessFilterResolver.__new__(BusinessFilterResolver)
    resolver.powerbi_provider = provider
    resolver.value_cache = {}
    assert resolver._get_values("M", "T", "A") == ["URGENCIAS", "HOSPITALIZACION"]
    assert len(provider.queries) == 1, "el resolvedor de filtros reutiliza el dominio del planificador"


def test_builder_failure_is_not_cached_and_reports_error():
    provider = CountingProvider(DOMAINS, down=True)
    builder = _bare_builder(provider)
    assert builder._get_values("M", "T", "A") is None
    assert builder.domain_errors[("M", "T", "A")]["error_type"] == "AdomdConnectionException"
    provider.down = False
    assert builder._get_values("M", "T", "A") == ["URGENCIAS", "HOSPITALIZACION"]
    assert ("M", "T", "A") not in builder.domain_errors


def test_builder_prefetch_uses_catalog_types():
    provider = CountingProvider(DOMAINS)
    builder = _bare_builder(provider, types_by_column={("t", "a"): "Text", ("t", "b"): "Text", ("t", "n"): "Integer"})
    fields = [{"table": "T", "column": "A"}, {"table": "T", "column": "B"}, {"table": "T", "column": "N"}]
    builder._prefetch_values("M", fields)
    assert len(provider.queries) == 1 and "UNION(" in provider.queries[0] and "'T'[N]" not in provider.queries[0]
    assert builder._get_values("M", "T", "B") == ["SURA", "NUEVA EPS"]
    assert len(provider.queries) == 1


def test_prewarm_fetches_plausible_columns_in_one_batch_per_model():
    domains = {("T", "SERVICIO"): ["URGENCIAS"], ("T", "ESPECIALIDAD"): ["ORTOPEDIA"],
               ("T", "SERVICIO PACIENTE"): ["X"], ("T", "CODIGO"): ["1"]}
    provider = CountingProvider(domains)
    builder = _bare_builder(provider, types_by_column={(t.lower(), c.lower()): "Text" for t, c in domains})
    builder._column_type_cache = {"m": {(t.lower(), c.lower()): "text" for t, c in domains}}
    builder.dimension_fields = [
        {"semantic_model": "M", "table": "T", "column": column, "kind": "column", "aliases": [column.lower()]}
        for column in ("SERVICIO", "ESPECIALIDAD", "SERVICIO PACIENTE", "CODIGO", "SERVICIO")
    ]
    assert builder.prewarm_domains() == {"M": 2}
    assert len(provider.queries) == 1 and "UNION(" in provider.queries[0]
    assert "PACIENTE" not in provider.queries[0], "nunca columnas de personas"
    assert builder._get_values("M", "T", "ESPECIALIDAD") == ["ORTOPEDIA"] and len(provider.queries) == 1
    previous = os.environ.pop("POWERBI_DOMAIN_PREWARM", None)
    try:
        assert builder._maybe_prewarm_domains() is None, "desactivado por defecto"
    finally:
        if previous is not None:
            os.environ["POWERBI_DOMAIN_PREWARM"] = previous


def test_value_token_index_follows_domain_renewal():
    provider, clock = CountingProvider(DOMAINS), Clock()
    builder = _bare_builder(provider)
    provider.domain_cache = DomainCache(provider, ttl_s=60, clock=clock)
    field = {"table": "T", "column": "A"}
    first = builder._value_token_index("M", field)
    assert [value for value, _ in first] == ["URGENCIAS", "HOSPITALIZACION"]
    assert builder._value_token_index("M", field) is first
    provider.domains[("T", "A")] = ["URGENCIAS", "UCI"]
    clock.now += 61
    assert [value for value, _ in builder._value_token_index("M", field)] == ["URGENCIAS", "UCI"]


def test_engine_reasoning_reports_exploration_queries():
    from src.chatbot.query_engine import QueryEngine
    provider = CountingProvider(DOMAINS)
    engine = QueryEngine.__new__(QueryEngine)
    engine.powerbi_provider = provider
    engine._trace = None
    engine.last_reasoning = None

    def runner():
        cache = domain_cache_for(provider)
        cache.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text")])
        cache.get("M", "T", "A")
        cache.get("M", "T", "N")
        return {"status": "success", "route": "powerbi"}

    result = engine._traced("question", "pregunta", runner)
    steps = {step["title"]: step["lines"] for step in result["reasoning"]["steps"]}
    line = steps["Consultas de exploración a Power BI"][0]
    assert line.startswith("2 consulta(s) de valores de columnas (1 en lote) · 3 columna(s)"), line
    assert "1 lectura(s) desde caché" in line
    assert result["reasoning"]["steps"][-1]["title"] == "Resultado del turno"

    def quiet():
        domain_cache_for(provider).get("M", "T", "A")   # ya en caché: sin consultas, sin línea
        return {"status": "success", "route": "powerbi"}

    titles = [step["title"] for step in engine._traced("question", "otra", quiet)["reasoning"]["steps"]]
    assert "Consultas de exploración a Power BI" not in titles


def _run_all():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, func in tests:
        try:
            func()
            print("PASS ", name)
        except Exception as error:  # noqa: BLE001
            failed += 1
            print("FAIL ", name, "->", type(error).__name__, error)
    print(f"{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())

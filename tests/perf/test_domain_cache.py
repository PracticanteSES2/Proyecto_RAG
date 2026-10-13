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
import re
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
        if '"__card' in dax:   # cardinalidad: ROW("__card0", COUNTROWS(VALUES(...)), ...)
            order = sorted(refs, key=lambda ref: dax.index(f"'{ref[0]}'[{ref[1]}]"))
            return {"status": "success",
                    "rows": [{f"[__card{i}]": len(self.domains[ref]) for i, ref in enumerate(order)}]}
        limit = re.search(r"TOPN\(\s*(\d+)", dax)
        limit = int(limit.group(1)) if limit else None
        if "UNION(" in dax:
            if self.fail_batch or any(ref in self.fail_columns for ref in refs):
                return {"status": "error", "error": "lote no soportado"}
            rows = []
            order = sorted(refs, key=lambda ref: dax.index(f"'{ref[0]}'[{ref[1]}]"))
            for index, ref in enumerate(order):
                rows += [{"[__columna]": index, "[Value]": v} for v in self.domains[ref][:limit]]
            return {"status": "success", "rows": rows}
        ref = refs[0]
        if ref in self.fail_columns:
            return {"status": "error", "error": "columna no encontrada"}
        return {"status": "success", "rows": [{"[Value]": v} for v in self.domains[ref][:limit]]}


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
    cache = DomainCache(provider, ttl_s=0, batch_size=12, card_probe=False)
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
    cache = DomainCache(provider, ttl_s=0, batch_size=2, card_probe=False)
    cache.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text"), ("T", "C", "Text")])
    assert len(provider.queries) == 1, "3 columnas con lote de 2: un lote y la última queda para get()"
    off = DomainCache(CountingProvider(DOMAINS), ttl_s=0, batch_size=1)
    off.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text")])
    assert off.provider.queries == []


def test_failed_batch_falls_back_to_single_queries():
    provider = CountingProvider(DOMAINS, fail_columns={("T", "B")})
    cache = DomainCache(provider, ttl_s=0, card_probe=False)
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
    cache = DomainCache(provider, ttl_s=0, card_probe=False)
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
    cache = DomainCache(provider, ttl_s=0, card_probe=False)
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
    batched = DomainCache(provider, ttl_s=0, batch_size=12, card_probe=False)
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
        cache = DomainCache(provider, ttl_s=0, batch_size=12, card_probe=False)
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
    # Cardinalidad de las columnas de texto (barata) y luego el lote (sin la numérica).
    assert len(provider.queries) == 2 and '"__card' in provider.queries[0]
    assert "UNION(" in provider.queries[1] and "'T'[N]" not in provider.queries[1]
    assert builder._get_values("M", "T", "B") == ["SURA", "NUEVA EPS"]
    assert len(provider.queries) == 2
    builder._prefetch_values("M", fields)
    assert len(provider.queries) == 2, "cardinalidad y dominios quedan en caché"


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
    assert len(provider.queries) == 2 and '"__card' in provider.queries[0] and "UNION(" in provider.queries[1]
    assert all("PACIENTE" not in query for query in provider.queries), "nunca columnas de personas"
    assert builder._get_values("M", "T", "ESPECIALIDAD") == ["ORTOPEDIA"] and len(provider.queries) == 2
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


# ----------------------------------------------------------------------------
# Cardinalidad, lotes pequeños, tope TOPN, tiempo límite y consultas lentas
# ----------------------------------------------------------------------------

BIG = [f"VALOR {i:04d}" for i in range(700)]
WIDE = {**DOMAINS, ("T", "D"): ["X", "Y"], ("T", "E"): ["Z"], ("T", "BIG"): BIG,
        ("T", "PACNUMDOC"): ["1", "2"], ("T", "FECHA_TEXTO"): ["2026-01-01"]}


def test_identifier_and_date_names_are_high_cardinality():
    from src.providers.domain_cache import identifier_column, likely_high_cardinality
    for name in ("PACNUMDOC", "ADNINGRESO", "OIDSERVICIO", "AINCONSEC", "NUMERO_DOCUMENTO", "ID", "ID_PACIENTE",
                 "HISTORIA_CLINICA", "PACNOMBRE", "RowNumber-2662979B"):
        assert identifier_column(name), name
    for name in ("HSUNOMBRE", "TERNOMCOM", "NOMBRE", "ESPECIALIDAD", "INGRESO", "TIPO_INGRESO", "SERVICIO",
                 "TIEMPO_ESTANCIA", "SEXO"):
        assert not identifier_column(name), name
    assert likely_high_cardinality("FECHA_TEXTO") and not likely_high_cardinality("ESPECIALIDAD")


def test_cardinality_probe_keeps_high_columns_out_of_small_batches():
    provider = CountingProvider(WIDE)
    cache = DomainCache(provider, ttl_s=0, batch_size=2)
    columns = [("T", "A", "Text"), ("T", "BIG", "Text"), ("T", "PACNUMDOC", "Text"), ("T", "B", "Text"),
               ("T", "C", "Text"), ("T", "D", "Text")]
    cache.prefetch("M", columns, max_batches=1)
    probe, batch = provider.queries
    assert '"__card' in probe and "'T'[BIG]" in probe and "PACNUMDOC" not in probe, \
        "los identificadores no se cuentan: ya se sabe que son de alta cardinalidad"
    assert "UNION(" in batch and "'T'[A]" in batch and "'T'[B]" in batch
    assert "'T'[BIG]" not in batch and "PACNUMDOC" not in batch and "'T'[C]" not in batch, \
        "lote de 2 columnas de baja cardinalidad; max_batches=1 trae solo el siguiente"
    assert cache.classify("M", "T", "BIG") == "high" and cache.classify("M", "T", "PACNUMDOC") == "high"
    assert cache.classify("M", "T", "C") == "low" and cache.exceeds("M", "T", "BIG", 500)
    assert not cache.exceeds("M", "T", "A", 500)
    # Siguiente lote: la cardinalidad ya se conoce (no se vuelve a contar).
    cache.prefetch("M", columns)
    assert len(provider.queries) == 3 and "'T'[C]" in provider.queries[2] and "'T'[D]" in provider.queries[2]
    # lead=True: si la primera columna es de alta cardinalidad no se adelanta ningún lote.
    lead = DomainCache(CountingProvider(WIDE), ttl_s=0, batch_size=2)
    lead.prefetch("M", [("T", "BIG", "Text"), ("T", "A", "Text"), ("T", "B", "Text")], max_batches=1, lead=True)
    assert not any("UNION(" in q for q in lead.provider.queries)


def test_probe_failure_is_harmless_and_disabled_after_two():
    class NoProbe(CountingProvider):
        def execute_dax(self, dax, semantic_model=None):
            if '"__card' in dax:
                self.queries.append(dax)
                return {"status": "error", "error": "función no soportada"}
            return super().execute_dax(dax, semantic_model)
    provider = NoProbe(WIDE)
    cache = DomainCache(provider, ttl_s=0, batch_size=4)
    cache.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text")])
    assert cache.get("M", "T", "A") == ["URGENCIAS", "HOSPITALIZACION"]
    cache.prefetch("M", [("T", "C", "Text"), ("T", "D", "Text")])
    cache.prefetch("M", [("T", "E", "Text"), ("X", "Y", "Text")])
    assert sum('"__card' in q for q in provider.queries) == 2, "tras dos fallos no se vuelve a contar"


def test_topn_limit_entries_serve_smaller_requests_and_complete_domains():
    provider = CountingProvider(WIDE)
    cache = DomainCache(provider, ttl_s=0)
    assert len(cache.get("M", "T", "BIG", limit=501)) == 501
    assert "TOPN(\n    501," in provider.queries[-1]
    assert cache.exceeds("M", "T", "BIG", 500)
    assert len(cache.get("M", "T", "BIG", limit=300)) == 501, "un tope mayor sirve para un pedido menor"
    assert len(provider.queries) == 1
    assert len(cache.get("M", "T", "BIG")) == 700, "el dominio truncado no sirve para el pedido completo"
    assert len(provider.queries) == 2 and "TOPN(\n    2500," in provider.queries[-1]
    assert cache.get("M", "T", "A", limit=501) == ["URGENCIAS", "HOSPITALIZACION"]
    assert cache.get("M", "T", "A") == ["URGENCIAS", "HOSPITALIZACION"]
    assert len(provider.queries) == 3, "un dominio completo (menos valores que el tope) sirve para todo"


class TimeoutProvider(CountingProvider):
    """Proveedor con tiempo límite: las columnas de `slow` lo vencen."""

    def __init__(self, domains, slow=(), seconds=None):
        super().__init__(domains)
        self.slow = set(slow)
        self.timeouts = []

    def execute_dax(self, dax, semantic_model=None, timeout_s=None):
        self.timeouts.append(timeout_s)
        if timeout_s and any(f"'{t}'[{c}]" in dax for t, c in self.slow) and '"__card' not in dax:
            self.queries.append(dax)
            return {"status": "error", "error": "XML for Analysis request timed out before it was completed.",
                    "error_type": "AdomdConnectionException", "timed_out": True}
        return super().execute_dax(dax, semantic_model)


def test_timeout_drops_column_reports_it_and_essential_has_no_limit():
    provider = TimeoutProvider(WIDE, slow={("T", "BIG")})
    clock = Clock()
    cache = DomainCache(provider, ttl_s=600, timeout_s=8, clock=clock)
    cache.begin_turn()
    assert cache.get("M", "T", "BIG") is None
    assert provider.timeouts[-1] == 8
    assert cache.errors[cache.key("M", "T", "BIG")]["error_type"] == "timeout"
    stats = cache.turn_stats()
    assert stats["timeouts"] == 1 and stats["slow"][0]["timed_out"] and stats["slow"][0]["columns"] == ["T[BIG]"]
    lines = cache.describe_turn()
    assert any("cancelada" in line and "T[BIG]" in line and "se siguió sin" in line for line in lines), lines
    cache.end_turn()
    cache.begin_turn()
    before = len(provider.queries)
    assert cache.get("M", "T", "BIG") is None and len(provider.queries) == before, \
        "no se vuelve a esperar el tiempo límite en cada turno"
    assert cache.turn_stats()["skipped_slow"] == 1
    assert cache.classify("M", "T", "BIG") == "high", "nunca vuelve a un lote"
    assert len(cache.get("M", "T", "BIG", essential=True)) == 700, "un filtro pedido con su columna no tiene límite"
    assert provider.timeouts[-1] is None
    cache.end_turn()
    clock.now += 601
    cache.begin_turn()
    assert cache.get("M", "T", "A") and provider.timeouts[-1] == 8


def test_batch_timeout_leaves_columns_for_single_queries():
    provider = TimeoutProvider(WIDE, slow={("T", "B")})
    cache = DomainCache(provider, ttl_s=0, timeout_s=8, card_probe=False)
    cache.begin_turn()
    cache.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text"), ("T", "C", "Text")])
    assert cache.turn_stats()["timeouts"] == 1 and cache._batch_failures == 0
    # El siguiente lote incremental no repite las columnas del lote vencido.
    before = len(provider.queries)
    cache.prefetch("M", [("T", "B", "Text"), ("T", "C", "Text"), ("T", "D", "Text")])
    assert len(provider.queries) == before, "B y C ya no entran a un lote; D sola no hace lote"
    assert cache.get("M", "T", "A") == ["URGENCIAS", "HOSPITALIZACION"], "las demás se consultan solas"
    assert cache.get("M", "T", "B") is None


def test_slow_queries_are_listed_with_their_columns():
    class SlowTimer:
        def __init__(self):
            self.now, self.calls = 0.0, 0

        def __call__(self):
            self.calls += 1
            if self.calls % 2 == 0:
                self.now += 3.25   # cada consulta tarda 3,25 s
            return self.now
    cache = DomainCache(CountingProvider(WIDE), ttl_s=0, card_probe=False, timer=SlowTimer())
    cache.begin_turn()
    cache.prefetch("M", [("T", "A", "Text"), ("T", "B", "Text")])
    cache.get("M", "T", "C")
    lines = cache.describe_turn()
    assert lines[0].startswith("2 consulta(s) de valores de columnas (1 en lote) · 3 columna(s) · 6.50 s"), lines
    assert "consulta lenta de lote (3.25 s): T[A], T[B]" in lines
    assert "consulta lenta de columna (3.25 s): T[C]" in lines


def test_background_queries_do_not_count_in_the_user_turn():
    provider = CountingProvider(WIDE)
    cache = DomainCache(provider, ttl_s=0, turn_budget=1, batch_size=1)
    cache.begin_turn()
    with cache.background():
        assert cache.get("M", "T", "A") and cache.get("M", "T", "B")
    assert cache.turn_stats()["queries"] == 0 and cache.totals["queries"] == 2
    assert cache.get("M", "T", "C"), "el presupuesto del usuario sigue intacto"


def test_prewarm_only_uses_already_open_connections():
    class Conn:
        def __init__(self, state):
            self.state = state
    provider = CountingProvider({("T", "SERVICIO"): ["URGENCIAS"], ("T", "SEDE"): ["NORTE"]})
    provider._connections = {"M": Conn("Open"), "OTRO": Conn("Closed")}
    provider._is_connection_open = lambda connection: connection.state == "Open"
    from src.providers.domain_cache import connection_open
    assert connection_open(provider, "m") and not connection_open(provider, "OTRO")
    assert not connection_open(provider, "NUEVO")
    builder = _bare_builder(provider, types_by_column={("t", "servicio"): "Text", ("t", "sede"): "Text"})
    builder._raw_column_type_cache["otro"] = {("t", "servicio"): "Text", ("t", "sede"): "Text"}
    builder._column_type_cache = {m: {("t", "servicio"): "text", ("t", "sede"): "text"} for m in ("m", "otro")}
    builder.dimension_fields = [
        {"semantic_model": model, "table": "T", "column": column, "kind": "column", "aliases": [column.lower()]}
        for model in ("M", "OTRO") for column in ("SERVICIO", "SEDE")
    ]
    assert builder.prewarm_domains(only_open_connections=True) == {"M": 2}


def test_value_token_index_skips_high_cardinality_without_querying():
    provider = CountingProvider(WIDE)
    builder = _bare_builder(provider)
    provider.domain_cache = DomainCache(provider, ttl_s=0)
    provider.domain_cache.begin_turn()
    assert builder._value_token_index("M", {"table": "T", "column": "PACNUMDOC"}) == []
    assert provider.queries == [], "un identificador no puede ser un calificativo: no se consulta"
    assert builder._value_token_index("M", {"table": "T", "column": "BIG"}) == []
    assert "TOPN(\n    501," in provider.queries[-1], "basta saber si pasa de 500 valores"
    assert builder._value_token_index("M", {"table": "T", "column": "BIG"}) == []
    assert len(provider.queries) == 1
    assert provider.domain_cache.turn_stats()["avoided"] == 2


def test_simulator_cost_model_and_command_timeout():
    """Modelo de coste del simulador: un lote con una columna de alta cardinalidad
    concentra el coste; PowerBIProvider pasa CommandTimeout y el simulador cancela."""
    from tests.realistic.powerbi_sim.cost import CostModel
    provider, backend = simulated_provider()
    saved = (dict(backend.config), backend.costs)
    backend.config["cost_model"] = True
    backend.costs = CostModel(backend.sim, overrides={("CIRUGIAS", "ESPECIALIDAD"): 200_000},
                              base_ms=500, valor_us=100, fila_us=100, columna_ms=30, conteo_us=0.5)
    try:
        heavy = batch_domain_dax([("CIRUGIAS", "ESPECIALIDAD"), ("EGRESOS", "SEXO")])
        light = batch_domain_dax([("CIRUGIAS", "ESTADO_CIRUGIA"), ("EGRESOS", "SEXO")])
        assert backend.costs.estimate(CONSOLIDADO, heavy, 0)["cost_ms"] > 20_000
        assert backend.costs.estimate(CONSOLIDADO, light, 0)["cost_ms"] < 700
        from src.providers.domain_cache import cardinality_dax
        probe = cardinality_dax([("CIRUGIAS", "ESPECIALIDAD"), ("EGRESOS", "SEXO")])
        assert backend.costs.estimate(CONSOLIDADO, probe, 1)["cost_ms"] < 700, "contar valores es barato"
        result = provider.execute_dax(heavy, semantic_model=CONSOLIDADO, timeout_s=8)
        assert result["status"] == "error" and result["timed_out"], result
        assert backend.log["dax"][-1]["timeout_s"] == 8 and backend.log["dax"][-1]["timed_out"]
        ok = provider.execute_dax(light, semantic_model=CONSOLIDADO, timeout_s=8)
        assert ok["status"] == "success" and backend.log["dax"][-1]["cost_ms"] < 700
        cache = DomainCache(provider, ttl_s=0, timeout_s=8)
        cache.begin_turn()
        assert cache.get(CONSOLIDADO, "CIRUGIAS", "ESPECIALIDAD") is None
        assert cache.turn_stats()["timeouts"] == 1
        assert cache.get(CONSOLIDADO, "CIRUGIAS", "ESPECIALIDAD", essential=True), "sin límite: responde"
    finally:
        backend.config.clear()
        backend.config.update(saved[0])
        backend.costs = saved[1]


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

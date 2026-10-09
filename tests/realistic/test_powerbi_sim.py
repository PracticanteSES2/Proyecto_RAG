"""
Pruebas del simulador de Power BI (tests/realistic/powerbi_sim).

Ejecutar:  python -m tests.realistic.test_powerbi_sim      (o con pytest)

Usan el overlay versionado tests/realistic/synthetic_models (y un modelo mínimo escrito en un
directorio temporal); no necesitan data/, Qdrant ni Ollama. Si existe data/model_metadata real
(checkout principal) se valida además la redundancia y que sus medidas se evalúen.
"""
import csv
import datetime as dt
import os
import sys
import tempfile
import types
from pathlib import Path

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.realistic.powerbi_sim import PowerBISimulator, SimulatedPowerBIError  # noqa: E402
from tests.realistic.powerbi_sim import adomd  # noqa: E402

SYNTHETIC = REPO_ROOT / "tests" / "realistic" / "synthetic_models"
TODAY = dt.date(2026, 9, 30)
CONSOLIDADO = "CONSOLIDADO DE ATENCIONES INSTITUCIONALES"
CONSULTA = "TABLERO CONSULTA EXTERNA"
EJECUTIVO = "INFORMES EJECUTIVOS 2026"
CAMAS = "TABLERO GESTION CAMAS"

_CACHE = {}


def sim():
    if "sim" not in _CACHE:
        _CACHE["sim"] = PowerBISimulator([(SYNTHETIC, "synthetic")], today=TODAY)
    return _CACHE["sim"]


def value(model, expression, simulator=None):
    out = (simulator or sim()).execute(model, f'EVALUATE ROW("v", {expression})')
    return out["rows"][0][0]


def table(model, dax, simulator=None):
    return (simulator or sim()).execute(model, dax)


def expect_error(model, dax, *fragments, simulator=None):
    try:
        (simulator or sim()).execute(model, dax)
    except SimulatedPowerBIError as error:
        text = str(error)
        for fragment in fragments:
            assert fragment in text, f"{fragment!r} no está en {text!r}"
        return text
    raise AssertionError(f"se esperaba error para: {dax}")


# ----------------------------------------------------------------------------
# Modelo mínimo (formato SSMS: punto y coma, cabeceras sin corchetes)
# ----------------------------------------------------------------------------

def mini_model_root():
    if "mini" in _CACHE:
        return _CACHE["mini"]
    root = Path(tempfile.mkdtemp(prefix="pbi_sim_test_"))
    folder = root / "mini_modelo"
    folder.mkdir()

    def write(name, headers, rows):
        with open(folder / name, "w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(headers)
            writer.writerows(rows)

    write("tables.csv", ["ID", "Name", "IsHidden", "Expression"],
          [[1, "VENTAS", "False", ""], [2, "Calendario", "False", 'CALENDAR(DATE(2023,1,1), DATE(2026,12,31))']])
    write("columns.csv", ["ID", "Name", "Table", "DataType", "Type", "Expression", "FormatString"], [
        [10, "FECHA", "VENTAS", "Date", "Data", "", ""],
        [11, "VALOR", "VENTAS", "Decimal", "Data", "", "$ #,0.00"],
        [12, "SEDE", "VENTAS", "Text", "Data", "", ""],
        [13, "Date", "Calendario", "Date", "CalculatedTableColumn", "", ""],
        [14, "AÑO", "Calendario", "Integer", "Calculated", "YEAR([Date])", "0"],
    ])
    write("measures.csv", ["ID", "Name", "Table", "DataType", "Expression", "FormatString"], [
        [20, "Ventas", "VENTAS", "Decimal", "SUM(VENTAS[VALOR])", "$ #,0"],
        [21, "Filas", "VENTAS", "Integer", "COUNTROWS(VENTAS)", "0"],
        [22, "Raro", "VENTAS", "Integer", "PATHLENGTH(\"a|b\") * [Filas]", "0"],
        [23, "Ventas Norte", "VENTAS", "Decimal", 'CALCULATE([Ventas], VENTAS[SEDE] = "SEDE NORTE")', "0"],
    ])
    write("relationships.csv", ["ID", "FromTable", "FromColumn", "FromCardinality", "ToTable", "ToColumn",
                                "ToCardinality", "IsActive", "CrossFilteringBehavior"],
          [[30, "VENTAS", "FECHA", "Many", "Calendario", "Date", "One", "True", "OneDirection"]])
    _CACHE["mini"] = root
    return root


def mini_sim():
    if "mini_sim" not in _CACHE:
        _CACHE["mini_sim"] = PowerBISimulator([mini_model_root()], today=TODAY)
    return _CACHE["mini_sim"]


# ----------------------------------------------------------------------------
# Evaluación de medidas
# ----------------------------------------------------------------------------

def test_count_measure_matches_rows_and_is_additive():
    total = value(CONSULTA, "[Total Consultas]")
    manual = value(CONSULTA, "COUNTROWS(FILTER('CONSULTAS_AMBULATORIAS', "
                             "NOT ISBLANK('CONSULTAS_AMBULATORIAS'[IDENTIFICACION])))")
    assert total == manual and total > 500
    grouped = table(CONSULTA, "EVALUATE SUMMARIZECOLUMNS('CONSULTAS_AMBULATORIAS'[ESPECIALIDAD], "
                              "\"__value\", [Total Consultas]) ORDER BY [__value] DESC")
    assert grouped["columns"] == ["CONSULTAS_AMBULATORIAS[ESPECIALIDAD]", "[__value]"]
    values = [r[1] for r in grouped["rows"]]
    assert values == sorted(values, reverse=True)
    assert sum(values) == total, "BLANK es un grupo más (como en Power BI)"
    assert None in [r[0] for r in grouped["rows"]]


def test_calculate_literal_filter_and_measure_references():
    total = value(CONSOLIDADO, "[TOTAL_CIRUGIAS]")
    realizadas = value(CONSOLIDADO, "[Cirugías realizadas]")
    manual = value(CONSOLIDADO, "CALCULATE([TOTAL_CIRUGIAS], 'CIRUGIAS'[ESTADO_CIRUGIA] = \"REALIZADA\")")
    assert 0 < realizadas == manual < total
    # Medida que suma otras medidas
    atenciones = value(CONSOLIDADO, "[Total Atenciones]")
    parts = sum(value(CONSOLIDADO, f"[{m}]") for m in ("Total Egresos", "TOTAL_CIRUGIAS", "Total_consultas_urgencias"))
    assert atenciones == parts


def test_keepfilters_vs_override():
    realizadas = value(CONSOLIDADO, "[Cirugías realizadas]")
    # El CALCULATE interno de la medida reemplaza el filtro externo del mismo campo.
    override = value(CONSOLIDADO, "CALCULATE([Cirugías realizadas], 'CIRUGIAS'[ESTADO_CIRUGIA] = \"CANCELADA\")")
    assert override == realizadas
    # KEEPFILTERS en el nivel interno intersecta con el filtro externo => BLANK
    keep = value(CONSOLIDADO, "CALCULATE(CALCULATE([TOTAL_CIRUGIAS], KEEPFILTERS('CIRUGIAS'[ESTADO_CIRUGIA] = "
                              "\"CANCELADA\")), 'CIRUGIAS'[ESTADO_CIRUGIA] = \"REALIZADA\")")
    plain = value(CONSOLIDADO, "CALCULATE(CALCULATE([TOTAL_CIRUGIAS], 'CIRUGIAS'[ESTADO_CIRUGIA] = "
                               "\"CANCELADA\"), 'CIRUGIAS'[ESTADO_CIRUGIA] = \"REALIZADA\")")
    assert keep is None and plain and plain > 0


def test_divide_percentage_and_average():
    ocupacion = value(CONSOLIDADO, "[% Ocupación]")
    assert 0 < ocupacion < 1.5
    estancia = value(CONSOLIDADO, "[PROMEDIO_ESTANCIA]")
    manual = value(CONSOLIDADO, "DIVIDE(SUM('EGRESOS'[DIAS_ESTANCIA]), COUNTROWS('EGRESOS'))")
    assert abs(estancia - manual) < 1e-9
    assert value(CONSULTA, "DIVIDE(1, 0)") is None and value(CONSULTA, "DIVIDE(1, 0, -1)") == -1


def test_time_intelligence_sameperiodlastyear():
    anterior_2025 = value(CONSOLIDADO, "CALCULATE([EGRESOS AÑO ANTERIOR], TREATAS({2025}, 'Calendario'[AÑO]))")
    egresos_2024 = value(CONSOLIDADO, "CALCULATE([Total Egresos], TREATAS({2024}, 'Calendario'[AÑO]))")
    assert anterior_2025 == egresos_2024 > 0
    variacion = value(EJECUTIVO, "CALCULATE([Variación Egresos vs Año Anterior], TREATAS({2025}, 'Calendario'[AÑO]))")
    actual = value(EJECUTIVO, "CALCULATE([Egresos], TREATAS({2025}, 'Calendario'[AÑO]))")
    previo = value(EJECUTIVO, "CALCULATE([Egresos], TREATAS({2024}, 'Calendario'[AÑO]))")
    assert abs(variacion - (actual - previo) / previo) < 1e-9


# ----------------------------------------------------------------------------
# Filtros y agrupaciones (patrones del QueryPlanDAXGenerator real)
# ----------------------------------------------------------------------------

def test_year_filters_partition_the_total():
    total = value(CONSOLIDADO, "[Total Egresos]")
    by_year = table(CONSOLIDADO, "EVALUATE SUMMARIZECOLUMNS('Calendario'[AÑO], \"__value\", [Total Egresos])")
    years = {r[0]: r[1] for r in by_year["rows"]}
    assert set(years) == {2023, 2024, 2025, 2026} and sum(years.values()) == total
    treatas = value(CONSOLIDADO, "CALCULATE([Total Egresos], TREATAS({2025}, 'Calendario'[AÑO]))")
    date_range = value(CONSOLIDADO, "CALCULATE([Total Egresos], FILTER(ALL('Calendario'[Date]), "
                                    "'Calendario'[Date] >= DATE(2025, 1, 1) && 'Calendario'[Date] < DATE(2026, 1, 1)))")
    assert treatas == date_range == years[2025]
    months = sum(value(CONSOLIDADO, f"CALCULATE([Total Egresos], FILTER(ALL('Calendario'[Date]), "
                                    f"'Calendario'[Date] >= DATE(2025, {m}, 1) && 'Calendario'[Date] < "
                                    f"DATE({2025 + m // 12}, {m % 12 + 1}, 1)))") or 0 for m in range(1, 13))
    assert months == years[2025]


def test_relationship_propagation_from_dimension():
    s = sim()
    rt = s.runtime(CONSULTA)
    aseguradoras = rt.store("ASEGURADORAS")
    nombre = aseguradoras.column("nombre")[0]
    oids = {aseguradoras.column("oid")[i] for i in range(aseguradoras.rowcount)
            if aseguradoras.column("nombre")[i] == nombre}
    fact = rt.store("CONSULTAS_AMBULATORIAS")
    expected = sum(1 for i in range(fact.rowcount)
                   if fact.column("oid_aseguradora")[i] in oids and fact.column("identificacion")[i] is not None)
    got = value(CONSULTA, f"CALCULATE([Total Consultas], TREATAS({{\"{nombre}\"}}, 'ASEGURADORAS'[NOMBRE]))")
    assert got == expected > 0


def test_project_generators_scalar_grouped_and_share():
    from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator
    generator = QueryPlanDAXGenerator()
    plan = {"status": "ready", "mode": "scalar",
            "metric": {"dax_expression": "[Total Consultas]", "validation_status": "approved"},
            "filters": [{"type": "categorical", "table": "Calendario", "column": "AÑO", "value": 2025,
                         "data_type": "number"},
                        {"type": "date_range", "table": "Calendario", "column": "Date", "year": 2025, "month": 3}]}
    scalar = table(CONSULTA, generator.generate(plan)["dax"])
    assert scalar["columns"] == ["[__value]"] and scalar["rows"][0][0] > 0
    grouped_plan = dict(plan, mode="grouped",
                        group_by=[{"table": "CONSULTAS_AMBULATORIAS", "column": "ESPECIALIDAD"}])
    grouped = table(CONSULTA, generator.generate(grouped_plan)["dax"])
    assert sum(r[1] for r in grouped["rows"]) == scalar["rows"][0][0]
    share_plan = dict(plan, share_dimension={"table": "CONSULTAS_AMBULATORIAS", "column": "ESPECIALIDAD",
                                             "scope": "group"})
    shares = table(CONSULTA, generator.generate_share(share_plan)["dax"])
    assert abs(sum(r[1] for r in shares["rows"]) - 1.0) < 1e-9


def test_project_generators_ranking_temporal_sets():
    """Patrones nuevos del generador: TOPN/ORDER BY, UNION de ROW por periodo, MONTH IN y pares AÑO-MES."""
    from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator
    generator = QueryPlanDAXGenerator()
    metric = {"dax_expression": "[Total Consultas]", "validation_status": "approved"}
    group = [{"table": "CONSULTAS_AMBULATORIAS", "column": "ESPECIALIDAD"}]
    ranked = generator.generate_ranked({"status": "ready", "mode": "grouped", "metric": metric, "group_by": group,
                                        "filters": [], "ranking": {"direction": "desc", "limit": 3}})
    top = table(CONSULTA, ranked["dax"])
    full = table(CONSULTA, generator.generate({"status": "ready", "mode": "grouped", "metric": metric,
                                               "group_by": group, "filters": []})["dax"])
    assert [r[1] for r in top["rows"]] == [r[1] for r in full["rows"]][:len(top["rows"])] and len(top["rows"]) >= 3
    pairs = {"type": "temporal_set", "columns": [{"table": "Calendario", "column": "AÑO"},
                                                 {"table": "Calendario", "column": "MES"}],
             "values": [[2024, 11], [2025, 1]]}
    scalar = lambda filters: table(CONSULTA, generator.generate(
        {"status": "ready", "mode": "scalar", "metric": metric, "filters": filters})["dax"])["rows"][0][0]
    nov = scalar([{"type": "date_range", "table": "Calendario", "column": "Date", "year": 2024, "month": 11}])
    jan = scalar([{"type": "date_range", "table": "Calendario", "column": "Date", "year": 2025, "month": 1}])
    assert scalar([pairs]) == nov + jan
    months = scalar([{"type": "date_range", "table": "Calendario", "column": "Date", "months": [1, 2, 3]}])
    years = scalar([{"type": "categorical", "table": "Calendario", "column": "MES", "values": [1, 2, 3],
                     "data_type": "number"}])
    assert months == years > 0
    union_dax = (
        "EVALUATE\nUNION(\n"
        "    ROW(\"__orden\", 2, \"MES\", \"enero 2025\", \"__value\", CALCULATE([Total Consultas], "
        "TREATAS({(2025, 1)}, 'Calendario'[AÑO], 'Calendario'[MES]))),\n"
        "    ROW(\"__orden\", 1, \"MES\", \"noviembre 2024\", \"__value\", CALCULATE([Total Consultas], "
        "TREATAS({(2024, 11)}, 'Calendario'[AÑO], 'Calendario'[MES])))\n"
        ")\nORDER BY [__orden] ASC"
    )
    union = table(CONSULTA, union_dax)
    assert union["columns"] == ["[__orden]", "[MES]", "[__value]"]
    assert [r[1] for r in union["rows"]] == ["noviembre 2024", "enero 2025"] and [r[2] for r in union["rows"]] == [nov, jan]


def test_domain_query_like_query_plan_builder():
    dax = ("EVALUATE\nTOPN(\n    2500,\n    FILTER(\n        SELECTCOLUMNS(\n            VALUES('CIRUGIAS'[ESTADO_CIRUGIA]),\n"
           "            \"Value\", 'CIRUGIAS'[ESTADO_CIRUGIA]\n        ),\n        NOT ISBLANK([Value])\n    ),\n"
           "    [Value], ASC\n)")
    out = table(CONSOLIDADO, dax)
    values = [r[0] for r in out["rows"]]
    assert out["columns"] == ["[Value]"]
    assert values == sorted(values) and "REALIZADA" in values and None not in values


def test_master_metric_keepfilters_pattern_and_case_insensitive_text():
    lower = value(CONSOLIDADO, "CALCULATE([TOTAL_CIRUGIAS], KEEPFILTERS('CIRUGIAS'[ESTADO_CIRUGIA] = \"realizada\"))")
    upper = value(CONSOLIDADO, "CALCULATE([TOTAL_CIRUGIAS], KEEPFILTERS('CIRUGIAS'[ESTADO_CIRUGIA] = \"REALIZADA\"))")
    assert lower == upper > 0, "VertiPaq compara texto sin distinguir mayúsculas"


def test_hierarchy_level_syntax():
    año = value(CONSOLIDADO, "CALCULATE([Total Egresos], 'Calendario'[Date].[Año] = 2024)")
    assert año == value(CONSOLIDADO, "CALCULATE([Total Egresos], TREATAS({2024}, 'Calendario'[AÑO]))")


# ----------------------------------------------------------------------------
# Errores como Power BI
# ----------------------------------------------------------------------------

def test_errors_like_adomd():
    expect_error(CONSULTA, "EVALUATE ROW(\"v\", COUNTROWS('NO_EXISTE'))", "Query (1, ", "Cannot find table 'NO_EXISTE'")
    expect_error(CONSULTA, "EVALUATE ROW(\"v\", SUM('CONSULTAS_AMBULATORIAS'[NO_EXISTE]))",
                 "Column 'NO_EXISTE' in table 'CONSULTAS_AMBULATORIAS' cannot be found")
    expect_error(CONSULTA, "EVALUATE ROW(\"v\", [Medida Inexistente])", "The value for 'Medida Inexistente' cannot be determined")
    expect_error(CONSULTA, "EVALUATE ROW(\"v\", FUNCIONRARA(1))", "Failed to resolve name 'FUNCIONRARA'")
    expect_error(CONSULTA, "EVALUATE ROW(\"v\", [Total Consultas]", "The syntax for")
    expect_error(CONSULTA, "EVALUATE 1", "not a valid table expression")
    expect_error(CONSULTA, "EVALUATE ROW(\"v\", CALCULATE([Total Consultas], 'Calendario'[AÑO] = \"2025\"))",
                 "DAX comparison operations do not support comparing values of type Integer with values of type Text")
    expect_error("MODELO QUE NO EXISTE", "EVALUATE ROW(\"v\", 1)", "was not found")
    expect_error(CONSULTA, "EVALUATE ROW(\"v\", 'CONSULTAS_AMBULATORIAS'[ESPECIALIDAD])", "A single value for column")


def test_type_mismatch_is_reported_like_tests_sim():
    out = table(CONSOLIDADO, "EVALUATE ROW(\"v\", CALCULATE([Total Egresos], FILTER(ALL('Calendario'[AÑO]), "
                             "'Calendario'[AÑO] >= DATE(2025, 1, 1) && 'Calendario'[AÑO] < DATE(2026, 1, 1))))")
    assert out["rows"][0][0] is None and out["type_mismatch"], "entero vs DATE(): vacío + TYPE MISMATCH"
    out = table(CONSOLIDADO, "EVALUATE ROW(\"v\", CALCULATE([Total Egresos], TREATAS({\"2025\"}, 'Calendario'[AÑO])))")
    assert out["rows"][0][0] is None and "TREATAS" in out["type_mismatch"][0]["message"]


# ----------------------------------------------------------------------------
# Determinismo, respaldo aproximado y formato de metadata
# ----------------------------------------------------------------------------

def test_determinism_and_stable_months():
    a = PowerBISimulator([(SYNTHETIC, "synthetic")], today=TODAY)
    b = PowerBISimulator([(SYNTHETIC, "synthetic")], today=dt.date(2026, 12, 15))
    query = "CALCULATE([Total Egresos], TREATAS({2025}, 'Calendario'[AÑO]))"
    assert value(CONSOLIDADO, query, a) == value(CONSOLIDADO, query) == value(CONSOLIDADO, query, b), \
        "ampliar el rango de fechas no cambia los meses ya generados"
    assert value(CONSOLIDADO, "[Total Egresos]", b) > value(CONSOLIDADO, "[Total Egresos]", a)


def test_semicolon_metadata_decimal_and_fallback():
    s = mini_sim()
    model = s.list_models()[0]
    assert model == "MINI MODELO"
    ventas = value(model, "[Ventas]", s)
    assert ventas.__class__.__name__ == "Decimal", "SUM de columna Decimal (moneda) devuelve Decimal"
    assert value(model, "[Ventas Norte]", s) <= ventas
    out = table(model, 'EVALUATE ROW("v", [Raro])', s)
    assert out["approximate"] and out["approximate"][0]["measure"] == "Raro"
    total = out["rows"][0][0]
    filtered = value(model, "CALCULATE([Raro], TREATAS({2024}, 'Calendario'[AÑO]))", s)
    assert 0 < filtered < total, "el respaldo aproximado respeta los filtros"
    assert table(model, 'EVALUATE ROW("v", [Raro])', s)["rows"][0][0] == total


def test_info_view_and_sync_roundtrip_with_real_provider():
    """sync_powerbi_metadata.MetadataSynchronizer + PowerBIProvider reales contra el simulador."""
    if "dotenv" not in sys.modules:   # PowerBIProvider llama load_dotenv al importarse: nunca leer .env
        stub = types.ModuleType("dotenv")
        stub.load_dotenv = lambda *a, **k: False
        sys.modules["dotenv"] = stub
    backend = adomd.install(sim())
    adomd_dir = REPO_ROOT / "tests" / "sim" / "fixtures" / "adomd"
    os.environ.update(POWERBI_XMLA_ENDPOINT="powerbi://api.powerbi.com/v1.0/myorg/SIMULADO",
                      POWERBI_SEMANTIC_MODEL=CONSULTA, ADOMD_PATH=str(adomd_dir), IDENTITY_PATH=str(adomd_dir))
    from src.providers.powerbi_provider import PowerBIProvider
    from sync_powerbi_metadata import MetadataSynchronizer
    provider = PowerBIProvider()
    assert provider.connect()["status"] == "success"
    assert set(provider.list_semantic_models()["models"]) == set(sim().list_models())
    with tempfile.TemporaryDirectory() as tmp:
        result = MetadataSynchronizer(provider=provider, project_root=tmp).export_model(
            CONSULTA, Path(tmp) / "data" / "model_metadata" / "x", force=True)
        assert result["status"] == "success", result
        copy = PowerBISimulator([Path(tmp) / "data" / "model_metadata"], today=TODAY)
        assert copy.list_models() == [CONSULTA]   # nombre desde _metadata_sync.json
        assert value(CONSULTA, "[Total Consultas]", copy) == value(CONSULTA, "[Total Consultas]")
    # Tipos .NET como los entrega pythonnet (cultura es-CO): el proveedor los
    # convierte sin depender de la cultura de Windows.
    rows = provider.execute_dax("EVALUATE TOPN(1, 'Calendario', 'Calendario'[Date], ASC)", CONSULTA)["rows"]
    assert rows[0]["Calendario[Date]"] == "2023-01-01", rows[0]
    from decimal import Decimal
    from src.providers.powerbi_provider import _net_to_python
    for culture in ("es-CO", "en-US"):
        assert _net_to_python(adomd.to_net(Decimal("3906.4"), culture)) == 3906.4
        assert _net_to_python(adomd.to_net(Decimal("0.125"), culture)) == 0.125
        assert _net_to_python(adomd.to_net(dt.datetime(2025, 3, 7, 14, 5), culture)) == "2025-03-07 14:05:00"
    error = provider.execute_dax("EVALUATE ROW(\"v\", [Nada])", CONSULTA)
    assert error["status"] == "error" and error["error_type"] == "AdomdErrorResponseException"
    backend.config["powerbi_up"] = False
    provider.close()
    assert provider.connect()["status"] == "error"


# ----------------------------------------------------------------------------
# Redundancia (ambigüedad entre tableros)
# ----------------------------------------------------------------------------

def _models_with_measure(simulator, name):
    return sorted(m for m, schema in simulator.models.items() if schema.measure(name))


def test_redundant_models_share_indicator_names():
    s = sim()
    assert {CONSOLIDADO, CONSULTA, EJECUTIVO, CAMAS} <= set(s.list_models())
    assert len(_models_with_measure(s, "Total Atenciones")) >= 3
    assert len(_models_with_measure(s, "% Ocupación")) >= 3
    assert len(_models_with_measure(s, "Egresos")) >= 3
    assert len(_models_with_measure(s, "Cirugías realizadas")) >= 2
    values = {m: value(m, "[Total Atenciones]") for m in _models_with_measure(s, "Total Atenciones")}
    assert len(set(values.values())) == len(values), "mismo nombre, distinto valor en cada modelo"


def test_real_metadata_if_present():
    from tests.realistic.harness import main_checkout
    data = main_checkout() / "data"
    if not (data / "model_metadata").exists():
        print("      (sin data/model_metadata real: se omite)")
        return
    s = PowerBISimulator([data / "model_metadata", (SYNTHETIC, "synthetic")],
                         registry_path=data / "catalog" / "model_registry.json", today=TODAY)
    assert "TABLERO DE ATENCIONES INSTITUCIONALES" in s.list_models()
    assert {CONSOLIDADO, CAMAS} <= set(s.list_models())
    assert len(_models_with_measure(s, "Total Egresos")) >= 3
    model = "TABLERO DE ATENCIONES INSTITUCIONALES"
    schema = s.models[model]
    approximate = 0
    for measure in list(schema.measures.values())[:60]:
        out = s.execute(model, f'EVALUATE ROW("v", [{measure.name}])')
        approximate += bool(out["approximate"])
    assert approximate <= 10, f"demasiadas medidas aproximadas: {approximate}"


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

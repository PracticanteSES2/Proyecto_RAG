"""
Pruebas del simulador de Power BI (tests/realistic/powerbi_sim).

Ejecutar:  python -m tests.realistic.test_powerbi_sim      (o con pytest)

Usan el overlay versionado tests/realistic/synthetic_models (y un modelo mínimo escrito en un
directorio temporal); no necesitan data/, Qdrant ni Ollama. Si existe data/model_metadata real
(checkout principal) se valida además la redundancia y que sus medidas se evalúen.
"""
import csv
import datetime as dt
import json
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


def _values(model, column, simulator):
    out = table(model, f"EVALUATE VALUES({column})", simulator)
    return sorted(str(row[0]) for row in out["rows"] if row[0] is not None)


def test_documented_values_and_realistic_domains():
    """_documented_values.json (tools/local_data) y dominios genéricos realistas."""
    import json

    root = Path(tempfile.mkdtemp(prefix="pbi_sim_docvalues_"))
    folder = root / "tablero_lavanderia"
    folder.mkdir()

    def write(name, headers, rows):
        with open(folder / name, "w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(headers)
            writer.writerows(rows)

    write("tables.csv", ["ID", "Name", "IsHidden", "Expression"],
          [[1, "LAVANDERIA", "False", ""], [2, "TRIAGES", "False", ""]])
    write("columns.csv", ["ID", "Name", "Table", "DataType", "Type", "Expression", "FormatString"], [
        [10, "Fecha", "LAVANDERIA", "Date", "Data", "", ""],
        [11, "Peso", "LAVANDERIA", "Integer", "Data", "", "0"],
        [12, "SERVICIO", "LAVANDERIA", "Text", "Data", "", ""],
        [13, "FECHA", "TRIAGES", "Date", "Data", "", ""],
        [14, "ASEGURADORA", "TRIAGES", "Text", "Data", "", ""],
        [15, "MENORES", "TRIAGES", "Text", "Data", "", ""],
        [16, "ServicioOid", "TRIAGES", "Text", "Data", "", ""],
    ])
    write("measures.csv", ["ID", "Name", "Table", "DataType", "Expression", "FormatString"],
          [[20, "Triages", "TRIAGES", "Integer", "COUNTROWS(TRIAGES)", "0"]])
    write("relationships.csv", ["ID", "FromTable", "FromColumn", "ToTable", "ToColumn"], [])
    (folder / "_documented_values.json").write_text(json.dumps({"columns": [
        # Tabla conocida: el dominio documentado reemplaza al genérico.
        {"table": "TRIAGES", "column": "ASEGURADORA", "values": ["NUEVA EPS", "SURA", "SANITAS", "MALLAMAS"]},
        # Sin tabla: se suma al genérico de las columnas con ese nombre.
        {"table": None, "column": "SERVICIO", "values": ["ANTIFLUIDOS ESPECIALES"]},
    ]}), encoding="utf-8")

    s = PowerBISimulator([root], today=TODAY)
    model = s.list_models()[0]
    assert _values(model, "'TRIAGES'[ASEGURADORA]", s) == ["MALLAMAS", "NUEVA EPS", "SANITAS", "SURA"]
    assert _values(model, "'TRIAGES'[MENORES]", s) == ["MAYORES DE EDAD", "MENORES DE EDAD"]
    oids = _values(model, "'TRIAGES'[ServicioOid]", s)
    assert oids and not set(oids) & {"URGENCIAS", "HOSPITALIZACION"}, f"OID: códigos, no nombres {oids[:5]}"
    servicios = _values(model, "'LAVANDERIA'[SERVICIO]", s)
    assert {"ANTIFLUIDOS", "URGENCIAS", "UCI ADULTOS", "ANTIFLUIDOS ESPECIALES"} <= set(servicios), servicios
    assert not any("CARDIO" in v for v in servicios), servicios


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
    approximate, invalid = 0, []
    for measure in list(schema.measures.values())[:60]:
        out = s.execute(model, f'EVALUATE ROW("v", [{measure.name}])')
        reasons = " ".join(str(n.get("reason")) for n in out.get("notes") or [] if isinstance(n, dict))
        # El TMDL real (2026-10-28) trae medidas rotas que también fallan en Power BI: columnas que
        # ya no existen (CONSULTA_URGENCIAS[OID_TRIAGE], IMAGENES_CARDIOLOGIA[Column1]) o sin
        # expresión (PROYECCIÓN_QX). No son límites del simulador.
        if out["approximate"] and ("cannot be found" in reasons or not measure.expression.strip()):
            invalid.append(measure.name)
            continue
        approximate += bool(out["approximate"])
    assert approximate <= 10, f"demasiadas medidas aproximadas: {approximate}"


# ----------------------------------------------------------------------------
# Tablas con filas fijas (_sim_tables.json): detalle y conteo coherentes
# ----------------------------------------------------------------------------

_FILTRO_CAMAS = (
    "NOT CONTAINSSTRING(LOWER('CAMAS DISPONIBLES'[HCACODIGO]), \"EXP\") && "
    "NOT CONTAINSSTRING(LOWER('CAMAS DISPONIBLES'[HCACODIGO]), \"OH\") && "
    "'CAMAS DISPONIBLES'[MOSTRAR] = \"MOSTRAR\" && 'CAMAS DISPONIBLES'[MOSTRAR_6TO] <> 0 && "
    "'CAMAS DISPONIBLES'[HCACODIGO] <> \"321\" && 'CAMAS DISPONIBLES'[HCACODIGO] <> \"322\"")


def briefing_root():
    """Modelo mínimo con CAMAS DISPONIBLES y PACIENTES X ASEGURADORA como en BRIEFING HOSPITALARIO
    (columnas calculadas y medidas reales) + las filas fijas de catalog_patches."""
    if "briefing" in _CACHE:
        return _CACHE["briefing"]
    from tests.realistic import catalog_patches
    root = Path(tempfile.mkdtemp(prefix="pbi_sim_briefing_"))
    folder = root / "briefing_hospitalario"
    folder.mkdir()

    def write(name, headers, rows):
        with open(folder / name, "w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(headers)
            writer.writerows(rows)

    camas, pacientes = "CAMAS DISPONIBLES", "PACIENTES X ASEGURADORA"
    write("tables.csv", ["ID", "Name", "IsHidden", "Expression"], [[1, camas, "False", ""], [2, pacientes, "False", ""]])
    columns = [
        [10, "HCACODIGO", camas, "Text", "Data", ""], [11, "SERVICIOS", camas, "Text", "Data", ""],
        [12, "ESTADO", camas, "Number", "Data", ""], [13, "HCAESTADO", camas, "Number", "Data", ""],
        [14, "MOSTRAR_6TO", camas, "Integer", "Data", ""], [15, "Orden", camas, "Text", "Data", ""],
        [16, "RUTA_ACV", camas, "Text", "Data", ""],
        [17, "MOSTRAR", camas, "Text", "Calculated",
         "IF(SEARCH(\"EXP\",'CAMAS DISPONIBLES'[HCACODIGO],1,0)<>0 && ('CAMAS DISPONIBLES'[HCAESTADO]=2), "
         "\"MOSTRAR\", IF(SEARCH(\"EXP\",'CAMAS DISPONIBLES'[HCACODIGO],1,0)=0, \"MOSTRAR\", \"NO MOSTRAR\"))"],
        [18, "ESTADOS_CAM", camas, "Text", "Calculated",
         "IF('CAMAS DISPONIBLES'[ESTADO]=1,\"DISPONIBLE\", IF('CAMAS DISPONIBLES'[ESTADO]=2,\"OCUPADA\", "
         "IF('CAMAS DISPONIBLES'[ESTADO]=3,\"BLOQUEADA\", IF('CAMAS DISPONIBLES'[ESTADO]=5,\"EN TRANSICIÓN\", "
         "IF('CAMAS DISPONIBLES'[ESTADO]=100,\"CAMA SOLICITADA\")))))"],
        [19, "OCUPADAS", camas, "Integer", "Calculated",
         "IF('CAMAS DISPONIBLES'[ESTADO]=2 || 'CAMAS DISPONIBLES'[ESTADO]=100, 1, 0)"],
    ]
    for index, name in enumerate(["PACNUMDOC", "GPANOMCOM", "HCACODIGO", "HSUNOMBRE", "TERNOMCOM", "GDENOMBRE",
                                  "ESPECIALIDAD", "ADNINGRESO", "HSUCODIGO", "EGRESO_EFECTIVO_HOY"]):
        columns.append([30 + index, name, pacientes, "Text", "Data", ""])
    columns += [[45, "DIAS_ESTANCIA", pacientes, "Integer", "Data", ""],
                [46, "FechaSalida", pacientes, "Date", "Data", ""],
                [47, "FECHA_EPICRISIS", pacientes, "Date", "Data", ""],
                [48, "FECHA_ORDEN_SALIDA", pacientes, "Date", "Data", ""]]
    write("columns.csv", ["ID", "Name", "Table", "DataType", "Type", "Expression"], columns)
    write("measures.csv", ["ID", "Name", "Table", "DataType", "Expression", "FormatString"], [
        [60, "%OCUPACION", camas, "Number", "DIVIDE(SUM('CAMAS DISPONIBLES'[OCUPADAS]), CALCULATE("
         "DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO]), FILTER('CAMAS DISPONIBLES', " + _FILTRO_CAMAS + ")))", ""],
        [61, "CamasFiltradas", camas, "Integer", "CALCULATE(DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO]), "
         "FILTER('CAMAS DISPONIBLES', " + _FILTRO_CAMAS + "))", ""],
        [62, "CAMAS", camas, "Integer", "COUNT('CAMAS DISPONIBLES'[HCACODIGO])", "0"],
    ])
    write("relationships.csv", ["ID", "FromTable", "FromColumn", "ToTable", "ToColumn"], [])
    (folder / "_sim_tables.json").write_text(
        json.dumps(catalog_patches.briefing_sim_tables(), ensure_ascii=False), encoding="utf-8")
    (folder / "_metadata_sync.json").write_text('{"semantic_model": "BRIEFING HOSPITALARIO"}', encoding="utf-8")
    _CACHE["briefing"] = root
    return root


def briefing_sim():
    if "briefing_sim" not in _CACHE:
        _CACHE["briefing_sim"] = PowerBISimulator([briefing_root()], today=TODAY)
    return _CACHE["briefing_sim"]


BRIEFING = "BRIEFING HOSPITALARIO"


def test_fixed_tables_bed_detail_matches_filtered_count():
    from tests.realistic import catalog_patches
    s = briefing_sim()
    expected = sorted(c["HCACODIGO"] for c in catalog_patches.camas()
                      if c["ESTADOS_CAM"] == "DISPONIBLE" and c["SERVICIOS"] == "HOSPITALIZACIÓN GENERAL")
    assert expected == ["403", "407", "411", "415", "419", "422"]
    # Detalle: camas disponibles con su servicio (sin medida, como una tabla de detalle).
    detail = table(BRIEFING, "EVALUATE SUMMARIZECOLUMNS('CAMAS DISPONIBLES'[SERVICIOS], "
                             "'CAMAS DISPONIBLES'[HCACODIGO], TREATAS({\"DISPONIBLE\"}, "
                             "'CAMAS DISPONIBLES'[ESTADOS_CAM]))", s)
    general = sorted(row[1] for row in detail["rows"] if row[0] == "HOSPITALIZACIÓN GENERAL")
    assert general == expected, general
    total_disponibles = sum(1 for c in catalog_patches.camas() if c["ESTADOS_CAM"] == "DISPONIBLE")
    assert len(detail["rows"]) == total_disponibles == 18
    # Conteo filtrado con la medida CAMAS y con COUNTROWS: igual a las filas del detalle.
    count = value(BRIEFING, "CALCULATE([CAMAS], 'CAMAS DISPONIBLES'[ESTADOS_CAM] = \"DISPONIBLE\", "
                            "'CAMAS DISPONIBLES'[SERVICIOS] = \"HOSPITALIZACIÓN GENERAL\")", s)
    rows = value(BRIEFING, "COUNTROWS(FILTER('CAMAS DISPONIBLES', 'CAMAS DISPONIBLES'[ESTADOS_CAM] = \"DISPONIBLE\" "
                           "&& 'CAMAS DISPONIBLES'[SERVICIOS] = \"HOSPITALIZACIÓN GENERAL\"))", s)
    assert count == rows == len(expected) == 6
    # Detalle con la medida (lo que generaría el chatbot): 1 por cama y suma = conteo.
    per_bed = table(BRIEFING, "EVALUATE SUMMARIZECOLUMNS('CAMAS DISPONIBLES'[SERVICIOS], "
                              "'CAMAS DISPONIBLES'[HCACODIGO], TREATAS({\"DISPONIBLE\"}, "
                              "'CAMAS DISPONIBLES'[ESTADOS_CAM]), TREATAS({\"HOSPITALIZACIÓN GENERAL\"}, "
                              "'CAMAS DISPONIBLES'[SERVICIOS]), \"__value\", [CAMAS])", s)
    assert sorted(r[1] for r in per_bed["rows"]) == expected and {r[2] for r in per_bed["rows"]} == {1}
    by_state = table(BRIEFING, "EVALUATE SUMMARIZECOLUMNS('CAMAS DISPONIBLES'[ESTADOS_CAM], \"n\", [CAMAS])", s)
    assert {r[0] for r in by_state["rows"]} == set(catalog_patches.ESTADOS)
    assert sum(r[1] for r in by_state["rows"]) == len(catalog_patches.camas())


def test_detail_listing_generated_by_project():
    """Listado de detalle del chatbot (TOPN + SUMMARIZECOLUMNS con la medida): coincide con el
    conteo, respeta los filtros internos de la medida y el tope de filas."""
    from tests.realistic import catalog_patches
    from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator
    s = briefing_sim()
    generator = QueryPlanDAXGenerator()
    camas = "CAMAS DISPONIBLES"
    columns = [{"table": camas, "column": "SERVICIOS"}, {"table": camas, "column": "HCACODIGO"}]

    def plan(measure, **values):
        return {"status": "ready", "mode": "scalar",
                "metric": {"dax_expression": f"[{measure}]", "validation_status": "approved"},
                "filters": [{"type": "categorical", "table": camas, "column": column, "value": value}
                            for column, value in values.items()]}

    disponibles = plan("CAMAS", ESTADOS_CAM="DISPONIBLE", SERVICIOS="HOSPITALIZACIÓN GENERAL")
    total = table(BRIEFING, generator.generate(disponibles)["dax"], s)["rows"][0][0]
    detail = table(BRIEFING, generator.generate_detail(disponibles, columns, 51)["dax"], s)
    assert [r[1] for r in detail["rows"]] == ["403", "407", "411", "415", "419", "422"] == sorted(
        c["HCACODIGO"] for c in catalog_patches.camas()
        if c["ESTADOS_CAM"] == "DISPONIBLE" and c["SERVICIOS"] == "HOSPITALIZACIÓN GENERAL")
    assert sum(r[2] for r in detail["rows"]) == total == 6
    # CAMAS (COUNT) lista las 7 bloqueadas; CamasFiltradas excluye 321/322 (administrativas) y
    # 609/610 (sexto piso no habilitado): la lista sigue los filtros internos de la medida.
    bloqueadas = table(BRIEFING, generator.generate_detail(
        plan("CAMAS", ESTADOS_CAM="BLOQUEADA"), columns, 51)["dax"], s)
    assert sorted(r[1] for r in bloqueadas["rows"]) == ["321", "322", "412", "609", "610", "708", "UCI-10"]
    filtradas = table(BRIEFING, generator.generate_detail(
        plan("CamasFiltradas", ESTADOS_CAM="BLOQUEADA"), columns, 51)["dax"], s)
    assert sorted(r[1] for r in filtradas["rows"]) == ["412", "708", "UCI-10"]
    # Orden por servicio y cama, y TOPN corta en el tope pedido.
    first = table(BRIEFING, generator.generate_detail(plan("CAMAS", ESTADOS_CAM="BLOQUEADA"), columns, 3)["dax"], s)
    assert [(r[0], r[1]) for r in first["rows"]] == [
        ("GINECOBSTETRICIA", "708"), ("HOSPITALIZACIÓN GENERAL", "321"), ("HOSPITALIZACIÓN GENERAL", "322")]


def test_fixed_tables_occupancy_and_patients_by_insurer():
    from tests.realistic import catalog_patches
    s = briefing_sim()
    camas = catalog_patches.camas()
    occupied = sum(1 for c in camas if c["ESTADO"] in (2, 100))
    assert value(BRIEFING, "[CamasFiltradas]", s) == 62
    assert abs(value(BRIEFING, "[%OCUPACION]", s) - occupied / 62) < 1e-9
    grouped = table(BRIEFING, "EVALUATE SUMMARIZECOLUMNS('PACIENTES X ASEGURADORA'[TERNOMCOM], \"__value\", "
                              "DISTINCTCOUNT('PACIENTES X ASEGURADORA'[ADNINGRESO])) ORDER BY [__value] DESC", s)
    assert {r[0]: r[1] for r in grouped["rows"]} == {name: n for name, n, _ in catalog_patches.ASEGURADORAS}
    total = value(BRIEFING, "DISTINCTCOUNT('PACIENTES X ASEGURADORA'[ADNINGRESO])", s)
    assert sum(r[1] for r in grouped["rows"]) == total == 43
    # Cada paciente está en una cama OCUPADA y cada cama OCUPADA tiene un paciente.
    beds = table(BRIEFING, "EVALUATE CALCULATETABLE(VALUES('CAMAS DISPONIBLES'[HCACODIGO]), "
                           "'CAMAS DISPONIBLES'[ESTADOS_CAM] = \"OCUPADA\")", s)
    patients = table(BRIEFING, "EVALUATE VALUES('PACIENTES X ASEGURADORA'[HCACODIGO])", s)
    assert {r[0] for r in beds["rows"]} == {r[0] for r in patients["rows"]}
    # Columnas no fijadas: se generan (una por fila); fechas relativas a hoy.
    codes = table(BRIEFING, "EVALUATE SELECTCOLUMNS('PACIENTES X ASEGURADORA', \"c\", "
                            "'PACIENTES X ASEGURADORA'[HSUCODIGO], \"f\", 'PACIENTES X ASEGURADORA'[FechaSalida])", s)
    assert len(codes["rows"]) == 43
    assert all(r[1] is not None and r[1].date() > TODAY for r in codes["rows"])
    assert all(str(name).startswith("PACIENTE SIMULADO") for name in
               (r[0] for r in table(BRIEFING, "EVALUATE VALUES('PACIENTES X ASEGURADORA'[GPANOMCOM])", s)["rows"]))


def test_catalog_patches_apply_on_copy():
    """El parche agrega la medida, las filas fijas y las páginas/visuales al PBIR copiado (sin tocar el original)."""
    import shutil
    from tests.realistic import catalog_patches
    base = Path(tempfile.mkdtemp(prefix="pbi_patch_"))
    data_root = base / "orig" / "data"
    shutil.copytree(briefing_root() / "briefing_hospitalario", data_root / "model_metadata" / "briefing_hospitalario")
    report = data_root / "pbir" / "BRIEFING HOSPITALARIO.Report"
    page = report / "definition" / "pages" / "p1"
    (page / "visuals").mkdir(parents=True)
    (page / "page.json").write_text(json.dumps({"name": "p1", "displayName": "GESTIÓN DE CAMAS"}), encoding="utf-8")
    (report / ".pbi").mkdir()
    (report / ".pbi" / "cache.abf").write_text("no copiar", encoding="utf-8")
    raw = data_root / "raw" / "tablero_briefing_hospitalario"
    raw.mkdir(parents=True)
    raw.joinpath("manifest.json").write_text(json.dumps({
        "report": "BRIEFING HOSPITALARIO", "semantic_model": "BRIEFING HOSPITALARIO",
        "semantic_model_key": "briefing_hospitalario", "source_group": "tablero_briefing_hospitalario"}),
        encoding="utf-8")
    root = base / "cache" / "root"
    shutil.copytree(data_root / "model_metadata", root / "data" / "model_metadata")
    (root / "data" / "catalog").mkdir(parents=True)
    patches = [p for p in catalog_patches.PATCHES if p["semantic_model_key"] == "briefing_hospitalario"]
    done = catalog_patches.apply_patches(data_root, root, patches)
    assert done[0]["status"] == "metadata+pbir", done
    patched = PowerBISimulator([root / "data" / "model_metadata"], today=TODAY)
    assert patched.models[BRIEFING].measure("CAMAS") is not None
    assert value(BRIEFING, "[CAMAS]", patched) == len(catalog_patches.camas())
    copy = root / "data" / "pbir" / "BRIEFING HOSPITALARIO.Report"
    assert not (copy / ".pbi").exists(), "nunca se copia .pbi (cache.abf)"
    names = {json.loads(p.read_text(encoding="utf-8"))["displayName"]
             for p in (copy / "definition" / "pages").glob("*/page.json")}
    assert names == {"GESTIÓN CAMAS", "INICIO"}, names
    visuals = [json.loads(v.read_text(encoding="utf-8")) for v in (copy / "definition").rglob("visual.json")]
    bars = [v for v in visuals if v["visual"]["visualType"] == "clusteredBarChart"]
    y = bars[0]["visual"]["query"]["queryState"]["Y"]["projections"][0]["field"]
    assert y["Aggregation"]["Function"] == 2, "DistinctCount en PBIR"
    manifest = json.loads((root / "data" / "raw" / "tablero_briefing_hospitalario" / "manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest["pbir_path"] == "data/pbir/BRIEFING HOSPITALARIO.Report"
    original = json.loads((page / "page.json").read_text(encoding="utf-8"))
    assert original["displayName"] == "GESTIÓN DE CAMAS", "el PBIR original no cambia"


def _demanda_fixture(base, table_name):
    """data/ con Demanda Insatisfecha (modelo real: 'SOLICITUD DE CAMAS', o inferido: SOLICITUD_CAMAS)
    y su PBIR en <base>/checkout/tableros (fuera de la data, como en el checkout principal)."""
    data_root = base / "copia" / "data"
    folder = data_root / "model_metadata" / "demanda_insatisfecha"
    folder.mkdir(parents=True)

    def write(name, headers, rows):
        with open(folder / name, "w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(headers)
            writer.writerows(rows)

    real = table_name == "SOLICITUD DE CAMAS"
    tables = [[1, table_name, "False", ""]] + ([[2, "TERCEROS", "False", ""], [3, "CALENDARIO", "False", ""]]
                                               if real else [])
    write("tables.csv", ["ID", "Name", "IsHidden", "Expression"], tables)
    columns = [[10, "Oid", table_name, "Integer", "Data", ""], [11, "OID_TERCERO", table_name, "Integer", "Data", ""]]
    if real:
        columns += [[12, "DEMANDA_INS", table_name, "Integer", "Data", ""], [13, "OID", "TERCEROS", "Integer", "Data", ""],
                    [14, "TERNOMCOM", "TERCEROS", "Text", "Data", ""], [15, "Date", "CALENDARIO", "Date", "Data", ""]]
    write("columns.csv", ["ID", "Name", "Table", "DataType", "Type", "Expression"], columns)
    measures = [[20, "TOTAL_SOLICITUD_CAMAS", "CALENDARIO", "Integer",
                 "DISTINCTCOUNT('SOLICITUD DE CAMAS'[Oid])", "0"]] if real else []
    write("measures.csv", ["ID", "Name", "Table", "DataType", "Expression", "FormatString"], measures)
    relationships = [[30, "SOLICITUD DE CAMAS", "OID_TERCERO", "TERCEROS", "OID"]] if real else []
    write("relationships.csv", ["ID", "FromTable", "FromColumn", "ToTable", "ToColumn"], relationships)
    (folder / "_metadata_sync.json").write_text('{"semantic_model": "Demanda Insatisfecha"}', encoding="utf-8")

    report = base / "checkout" / "tableros" / "Demanda Insatisfecha" / "Demanda Insatisfecha.Report"
    pages = report / "definition" / "pages"

    def visual(page, name, refs):
        target = pages / page / "visuals" / name
        target.mkdir(parents=True)
        projections = [{"field": {}, "queryRef": ref} for ref in refs]
        (target / "visual.json").write_text(json.dumps({"name": name, "visual": {
            "visualType": "card", "query": {"queryState": {"Values": {"projections": projections}}}}}),
            encoding="utf-8")

    for page in ("CONSOLIDADO", "SOLICITUD CAMAS"):
        (pages / page).mkdir(parents=True)
        (pages / page / "page.json").write_text(json.dumps({"name": page, "displayName": page}), encoding="utf-8")
    if real:
        visual("CONSOLIDADO", "v1", ["Sum(SOLICITUD DE CAMAS.DEMANDA_INS)"])
        visual("CONSOLIDADO", "v2", ["CountNonNull(TRIAGE.OID)", "CALENDARIO.TOTAL_SOLICITUD_CAMAS"])
        visual("CONSOLIDADO", "v3", ["TERCEROS.TERNOMCOM", "CALENDARIO.TOTAL_DEMANDA_INSATISFECHA"])
        visual("SOLICITUD CAMAS", "v4", ["Sum(SOLICITUD DE CAMAS.DEMANDA_INS)"])
    raw = data_root / "raw" / "tablero_demanda_insatisfecha"
    raw.mkdir(parents=True)
    (raw / "manifest.json").write_text(json.dumps({
        "report": "DEMANDA INSATISFECHA", "semantic_model_key": "demanda_insatisfecha",
        "source_group": "tablero_demanda_insatisfecha",
        "pbir_path": "tableros/Demanda Insatisfecha/Demanda Insatisfecha.Report"}), encoding="utf-8")
    return data_root, report


def _apply_demanda(table_name):
    import shutil
    from tests.realistic import catalog_patches, harness
    base = Path(tempfile.mkdtemp(prefix="pbi_patch_demanda_"))
    data_root, report = _demanda_fixture(base, table_name)
    root = base / "cache" / "root"
    shutil.copytree(data_root / "model_metadata", root / "data" / "model_metadata")
    (root / "data" / "catalog").mkdir(parents=True)
    patches = [p for p in catalog_patches.PATCHES if p["semantic_model_key"] == "demanda_insatisfecha"]
    original = harness.main_checkout
    harness.main_checkout = lambda: base / "checkout"   # la copia de data/ no está junto a tableros/
    try:
        done = catalog_patches.apply_patches(data_root, root, patches)[0]
    finally:
        harness.main_checkout = original
    return done, data_root, root


def test_catalog_patches_skip_what_the_real_model_has():
    """Modelo real de Demanda Insatisfecha: tablas, columnas, medida (en CALENDARIO), relación y
    visuales ya existen -> no se duplica nada ni se reconstruye el catálogo. El pbir_path relativo de
    una copia de data/ se resuelve contra el checkout principal."""
    done, data_root, root = _apply_demanda("SOLICITUD DE CAMAS")
    folder = root / "data" / "model_metadata" / "demanda_insatisfecha"
    for name in ("tables.csv", "columns.csv", "measures.csv", "relationships.csv"):
        assert (folder / name).read_bytes() == (data_root / "model_metadata" / "demanda_insatisfecha" / name).read_bytes(), name
    assert done["metadata_added"] == [] and done["status"] == "metadata", done
    assert done["reason"] == "el informe ya trae los visuales del parche", done
    assert len(done["visuals_skipped"]) == 4, done
    assert not list((root / "data" / "pbir").glob("*.Report")), "sin copia del informe"


def test_catalog_patches_alias_for_inferred_table():
    """Data inferida anterior (SOLICITUD_CAMAS): se agrega lo que falta sobre la tabla existente."""
    done, _data_root, root = _apply_demanda("SOLICITUD_CAMAS")
    assert done["status"] == "metadata+pbir", done
    assert "columna SOLICITUD_CAMAS[DEMANDA_INS]" in done["metadata_added"], done
    assert "columna SOLICITUD_CAMAS[OID_TERCERO]" not in done["metadata_added"], done
    assert "medida SOLICITUD_CAMAS[TOTAL_SOLICITUD_CAMAS]" in done["metadata_added"], done
    tables = (root / "data" / "model_metadata" / "demanda_insatisfecha" / "tables.csv").read_text(encoding="utf-8")
    assert "SOLICITUD DE CAMAS" not in tables, "no se crea la tabla real junto a la inferida"
    refs = {p["queryRef"] for v in (root / "data" / "pbir").rglob("visual.json")
            for role in json.loads(v.read_text(encoding="utf-8"))["visual"]["query"]["queryState"].values()
            for p in role["projections"]}
    assert "Sum(SOLICITUD_CAMAS.DEMANDA_INS)" in refs and "SOLICITUD_CAMAS.TOTAL_SOLICITUD_CAMAS" in refs, refs


def test_fixed_hospitalized_patients_match_insurer_patients():
    """PACIENTES HOSPITALIZADOS (tabla propia en el modelo real) = los mismos 43 pacientes."""
    from tests.realistic import catalog_patches
    tables = catalog_patches.briefing_sim_tables()["tables"]
    hosp, pac = tables["PACIENTES HOSPITALIZADOS"], tables["PACIENTES X ASEGURADORA"]
    docs = lambda spec: {row[spec["columns"].index("PACNUMDOC")] for row in spec["rows"]}
    assert docs(hosp) == docs(pac) and len(docs(hosp)) == 43


FARMACIA = "TABLERO_FARMACIA"


def test_fixed_tables_pharmacy_list_matches_card_filter():
    """Parche solo de filas fijas (TABLERO FARMACIA): sin páginas no copia el PBIR; el listado con el
    filtro de la tarjeta «0-30 DÍAS» (mes <= 1) coincide con su conteo."""
    import shutil
    from tests.realistic import catalog_patches
    base = Path(tempfile.mkdtemp(prefix="pbi_farmacia_"))
    folder = base / "orig" / "data" / "model_metadata" / "tablero_farmacia"
    folder.mkdir(parents=True)

    def write(name, headers, rows):
        with open(folder / name, "w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(headers)
            writer.writerows(rows)

    vencidos, proximos = "PRODUCTOS_VENCIDOS", "VENCIMIENTO_PRODUCTOS"
    write("tables.csv", ["ID", "Name", "IsHidden", "Expression"], [[1, vencidos, "False", ""], [2, proximos, "False", ""]])
    write("columns.csv", ["ID", "Name", "Table", "DataType", "Type", "Expression"], [
        [10, "iddcantid", vencidos, "Integer", "Data", ""], [11, "IPRCODIGO", vencidos, "Text", "Data", ""],
        [12, "iprdescor", vencidos, "Text", "Data", ""], [13, "IDFECDOC", vencidos, "Text", "Data", ""],
        [20, "mes", proximos, "Integer", "Data", ""], [21, "IFICANTID", proximos, "Integer", "Data", ""],
        [22, "ilsfecven", proximos, "Text", "Data", ""], [23, "IPRCODIGO", proximos, "Text", "Data", ""],
        [24, "IPRDESCOR", proximos, "Text", "Data", ""], [25, "ILSCODIGO", proximos, "Text", "Data", ""],
        [26, "NombreZona", proximos, "Text", "Data", ""]])
    write("measures.csv", ["ID", "Name", "Table", "DataType", "Expression", "FormatString"], [])
    write("relationships.csv", ["ID", "FromTable", "FromColumn", "ToTable", "ToColumn"], [])
    (folder / "_metadata_sync.json").write_text('{"semantic_model": "TABLERO_FARMACIA"}', encoding="utf-8")
    root = base / "cache" / "root"
    shutil.copytree(folder.parent, root / "data" / "model_metadata")
    (root / "data" / "catalog").mkdir(parents=True)
    patches = [p for p in catalog_patches.PATCHES if p["semantic_model_key"] == "tablero_farmacia"]
    done = catalog_patches.apply_patches(folder.parent.parent, root, patches)
    assert done[0]["status"] == "metadata", done
    assert not (root / "data" / "pbir").exists() and not (root / "data" / "raw").exists()
    s = PowerBISimulator([root / "data" / "model_metadata"], today=TODAY)
    assert value(FARMACIA, "SUM('PRODUCTOS_VENCIDOS'[iddcantid])", s) == sum(
        p[2] for p in catalog_patches.PRODUCTOS_VENCIDOS) == 79
    detail = table(FARMACIA, "EVALUATE CALCULATETABLE(SUMMARIZECOLUMNS('VENCIMIENTO_PRODUCTOS'[IPRDESCOR], "
                             "'VENCIMIENTO_PRODUCTOS'[ilsfecven]), 'VENCIMIENTO_PRODUCTOS'[mes] <= 1)", s)
    expected = sorted(p[1] for p in catalog_patches.PRODUCTOS_EN_VENCIMIENTO if p[2] <= 1)
    assert sorted(r[0] for r in detail["rows"]) == expected and len(expected) == 3, detail["rows"]
    count = value(FARMACIA, "CALCULATE(DISTINCTCOUNT('VENCIMIENTO_PRODUCTOS'[IPRCODIGO]), "
                            "'VENCIMIENTO_PRODUCTOS'[mes] <= 1)", s)
    assert count == 3


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

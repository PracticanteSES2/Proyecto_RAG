"""
Periodos de tiempo en las preguntas (offline, con fecha de referencia FIJA).

- PeriodParser: «entre enero y marzo de 2025», «este año», «mes pasado»,
  «primer trimestre», «últimos 3 meses», «hoy»... -> rango [inicio, fin).
- Agrupación temporal: «por mes», «mensual», «mes a mes», «por trimestre».
- QueryPlanBuilder + QueryPlanDAXGenerator sobre los catálogos mínimos de
  tests/selection (Alfa: jerarquía de FECHA; Beta: AÑO/MES enteros).
- Formato en español del periodo aplicado (respuesta y razonamiento).

Nunca se usa la fecha real: todo es relativo a HOY = 9-oct-2026 (o la que
fije cada prueba).

Ejecutar:  python -m tests.periods.test_periods      (o pytest tests/periods)
"""
import sys
import tempfile
import traceback
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.intent_parser import IntentParser  # noqa: E402
from src.chatbot.query_engine import QueryEngine  # noqa: E402
from src.chatbot.response_formatter import format_filters_line  # noqa: E402
from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator  # noqa: E402
from src.semantic.period_parser import PeriodParser, split_period  # noqa: E402
from src.semantic.query_plan_builder import QueryPlanBuilder, normalize_text  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.selection.test_selection import FakeProvider, _build_fixture  # noqa: E402

HOY = date(2026, 10, 9)


def parse(text, today=HOY):
    return PeriodParser(today).parse(normalize_text(text))


def span(text, today=HOY):
    period = parse(text, today)
    assert period, f"sin periodo: {text!r}"
    return period["start"].isoformat(), period["end"].isoformat(), period["label"]


# ---------------------------------------------------------------- detección
def test_explicit_month_range():
    assert span("peso de lavanderia entre enero y marzo de 2025") == (
        "2025-01-01", "2025-04-01", "enero–marzo 2025")
    assert span("de enero a marzo del 2025") == ("2025-01-01", "2025-04-01", "enero–marzo 2025")
    assert span("desde noviembre de 2024 hasta febrero de 2025") == (
        "2024-11-01", "2025-03-01", "noviembre 2024–febrero 2025")
    assert span("entre 2023 y 2025") == ("2023-01-01", "2026-01-01", "2023–2025")


def test_month_range_without_year_is_all_years():
    period = parse("entre enero y marzo")
    assert period["kind"] == "months_any_year" and period["months"] == [1, 2, 3]
    assert "todos los años" in period["label"]


def test_two_loose_months_are_not_a_range_and_the_other_is_declared():
    period = parse("enero y marzo de 2025")
    assert (period["year"], period["month"]) == (2025, 3)
    assert period["ignored"] == ["enero"]


def test_relative_years_and_months():
    assert span("cuanto peso lleva la lavanderia este año") == ("2026-01-01", "2026-10-10", "2026 hasta hoy")
    assert span("en lo que va del año") == ("2026-01-01", "2026-10-10", "2026 hasta hoy")
    assert span("el año pasado") == ("2025-01-01", "2026-01-01", "2025 (año pasado)")
    assert span("el año antepasado")[:2] == ("2024-01-01", "2025-01-01")
    assert span("este mes") == ("2026-10-01", "2026-10-10", "octubre 2026 hasta hoy")
    assert span("el mes pasado") == ("2026-09-01", "2026-10-01", "septiembre 2026 (mes pasado)")
    assert span("marzo del año pasado") == ("2025-03-01", "2025-04-01", "marzo 2025")
    assert span("este año en marzo")[:2] == ("2026-03-01", "2026-04-01")


def test_quarters_and_semesters():
    assert span("primer trimestre de 2025") == (
        "2025-01-01", "2025-04-01", "enero–marzo 2025 (1.er trimestre)")
    assert span("el 1.er trimestre")[:2] == ("2026-01-01", "2026-04-01")
    assert span("segundo trimestre del 2024")[:2] == ("2024-04-01", "2024-07-01")
    # El trimestre en curso se recorta a hoy.
    assert span("cuarto trimestre")[:2] == ("2026-10-01", "2026-10-10")
    assert span("primer semestre") == ("2026-01-01", "2026-07-01", "enero–junio 2026 (1.er semestre)")
    assert span("trimestre pasado")[:2] == ("2026-07-01", "2026-10-01")
    assert span("ultimo trimestre de 2025")[:2] == ("2025-10-01", "2026-01-01")
    assert span("q1 2025")[:2] == ("2025-01-01", "2025-04-01")
    # «tercer trimestre» en febrero aún no empieza: el del año pasado.
    assert span("tercer trimestre", date(2026, 2, 10))[:2] == ("2025-07-01", "2025-10-01")


def test_last_n_units_are_complete_units():
    assert span("ultimos 3 meses") == (
        "2026-07-01", "2026-10-01", "julio–septiembre 2026 (últimos 3 meses)")
    assert span("los últimos doce meses")[:2] == ("2025-10-01", "2026-10-01")
    assert span("ultimos 2 años")[:2] == ("2024-01-01", "2026-01-01")
    assert span("ultimos 7 dias") == ("2026-10-03", "2026-10-10", "3–9 de octubre de 2026 (últimos 7 días)")


def test_days():
    assert span("hoy") == ("2026-10-09", "2026-10-10", "9 de octubre de 2026 (hoy)")
    assert span("ayer") == ("2026-10-08", "2026-10-09", "8 de octubre de 2026 (ayer)")
    assert span("15 de marzo de 2025")[:2] == ("2025-03-15", "2025-03-16")
    assert span("del 1 al 15 de marzo de 2025")[:2] == ("2025-03-01", "2025-03-16")
    assert parse("hoy")["daily"] and not parse("este mes")["daily"]
    assert span("semana pasada")[:2] == ("2026-09-28", "2026-10-05")


def test_since_until_today():
    assert span("desde marzo") == ("2026-03-01", "2026-10-10", "desde marzo 2026 hasta hoy")
    assert span("desde 2024")[:2] == ("2024-01-01", "2026-10-10")
    assert parse("cuanto peso hasta hoy") is None  # «hasta hoy» solo = todo el histórico


def test_legacy_month_and_year():
    assert span("peso 2025 junio")[:2] == ("2025-06-01", "2025-07-01")
    assert span("en el mes de enero de 2026") == ("2026-01-01", "2026-02-01", "enero 2026")
    assert parse("en enero")["months"] == [1]
    # Un año / mes nombrado se respeta completo (puede haber datos programados a futuro).
    assert span("cirugias programadas 2026") == ("2026-01-01", "2027-01-01", "2026")
    assert span("octubre de 2026") == ("2026-10-01", "2026-11-01", "octubre 2026")


def test_mayores_is_not_may():
    assert parse("pacientes mayores de edad") is None
    assert IntentParser.detect_month(object.__new__(IntentParser), "pacientes mayores de edad") is None
    assert IntentParser.detect_month(object.__new__(IntentParser), "cirugias de mayo") == 5


def test_granularity():
    parser = PeriodParser(HOY)

    def unit(text):
        found = parser.granularity(normalize_text(text))
        return found and found["unit"]

    assert unit("peso lavanderia 2025 por mes") == "month"
    assert unit("evolucion mensual del peso") == "month"
    assert unit("mes a mes") == "month"
    assert unit("por trimestre") == "quarter"
    assert unit("por año") == "year"
    assert unit("promedio mensual de cirugias") is None  # nombre de un indicador
    assert unit("por mes de enero") is None
    assert unit("por servicio") is None


def test_split_period_clips_to_today():
    buckets = split_period(parse("este año"), "month", HOY)
    assert [b["label"] for b in buckets][-1] == "octubre 2026 (hasta hoy)" and len(buckets) == 10
    quarters = split_period(parse("2025"), "quarter", HOY)
    assert [b["label"] for b in quarters] == [
        "1.er trimestre 2025", "2.º trimestre 2025", "3.er trimestre 2025", "4.º trimestre 2025"]


# ---------------------------------------------------------------- DAX
def test_dax_date_range_months_and_sets():
    generator = QueryPlanDAXGenerator()
    date_range = {"type": "date_range", "table": "C", "column": "Date",
                  "start": "2025-01-01", "end": "2025-04-01"}
    assert generator._date_filter(date_range) == (
        "FILTER(ALL('C'[Date]), 'C'[Date] >= DATE(2025, 1, 1) && 'C'[Date] < DATE(2025, 4, 1))")
    months = {"type": "date_range", "table": "C", "column": "Date", "months": [1, 2, 3], "month": None}
    assert generator._date_filter(months) == "FILTER(ALL('C'[Date]), MONTH('C'[Date]) IN {1, 2, 3})"
    values = {"type": "categorical", "table": "C", "column": "MES", "value": None,
              "values": [1, 2, 3], "data_type": "number"}
    assert generator._categorical_filter(values) == "TREATAS({1, 2, 3}, 'C'[MES])"
    pairs = {"type": "temporal_set", "columns": [{"table": "C", "column": "AÑO"}, {"table": "C", "column": "MES"}],
             "values": [[2024, 12], [2025, 1]]}
    assert generator._temporal_set_filter(pairs) == "TREATAS({(2024, 12), (2025, 1)}, 'C'[AÑO], 'C'[MES])"


def test_dax_grouped_by_period_keeps_other_filters():
    plan = {
        "status": "ready", "mode": "grouped",
        "metric": {"dax_expression": "[M]", "validation_status": "approved"},
        "filters": [
            {"type": "categorical", "table": "T", "column": "SEDE", "value": "NORTE", "data_type": "text"},
            {"type": "date_range", "table": "C", "column": "Date", "start": "2025-01-01",
             "end": "2025-03-01", "source": "query_plan_temporal"},
        ],
        "group_by": [{"table": "C", "column": "Mes", "label": "Mes", "temporal": "month"}],
        "temporal_buckets": [
            {"order": 1, "label": "enero 2025", "filters": [
                {"type": "date_range", "table": "C", "column": "Date", "start": "2025-01-01", "end": "2025-02-01"}]},
            {"order": 2, "label": "febrero 2025", "filters": [
                {"type": "date_range", "table": "C", "column": "Date", "start": "2025-02-01", "end": "2025-03-01"}]},
        ],
    }
    result = QueryPlanDAXGenerator().generate(plan)
    assert result["status"] == "generated" and result["mode"] == "grouped", result
    dax = result["dax"]
    assert dax.startswith("EVALUATE\nUNION(") and dax.endswith("ORDER BY [__orden] ASC"), dax
    assert 'ROW("__orden", 1, "Mes", "enero 2025", "__value", CALCULATE([M], ' in dax
    assert dax.count("TREATAS({\"NORTE\"}, 'T'[SEDE])") == 2
    # El periodo total no se repite dentro de cada fila (cada fila ya es un subperiodo).
    assert "DATE(2025, 3, 1)) && " not in dax and dax.count("DATE(2025, 1, 1)") == 1
    share = QueryPlanDAXGenerator().generate_share({**plan, "share_dimension": {**plan["group_by"][0]}})
    assert share["status"] == "rejected"


# ---------------------------------------------------------------- QueryPlanBuilder
_STATE = {}


def builder(today=HOY):
    if "root" not in _STATE:
        tmp = tempfile.TemporaryDirectory()
        _STATE["tmp"] = tmp
        _STATE["root"] = Path(tmp.name)
        _build_fixture(_STATE["root"])
    root = _STATE["root"]
    router = SourceModelRouter(
        root / "data" / "catalog" / "source_registry.json",
        root / "data" / "rag" / "visual_metrics_catalog.json", project_root=root,
    )
    return QueryPlanBuilder(
        root / "data" / "rag" / "master_metrics.json",
        root / "data" / "rag" / "visual_metrics_catalog.json",
        router, FakeProvider(), project_root=root, today=today,
    )


def plan_for(question, today=HOY):
    plan = builder(today).build(question)
    assert plan["status"] == "ready", (question, plan.get("status"), plan.get("reason"),
                                       plan.get("unresolved_text"))
    return plan


def dax_for(plan):
    result = QueryPlanDAXGenerator().generate(plan)
    assert result["status"] == "generated", result
    return result["dax"]


def test_builder_range_on_date_column_is_not_an_unknown_filter():
    plan = plan_for("¿Cuántas cirugías realizadas entre enero y marzo de 2024 en el Tablero Alfa?")
    assert plan["unapplied_terms"] == [], plan["unapplied_terms"]
    dax = dax_for(plan)
    assert "DATE(2024, 1, 1)" in dax and "DATE(2024, 4, 1)" in dax, dax
    assert plan["period"]["label"] == "enero–marzo 2024"
    assert format_filters_line(plan["filters"]) == "Filtros: enero–marzo 2024"


def test_builder_range_on_integer_columns():
    plan = plan_for("¿Cuántas cirugías realizadas entre enero y marzo de 2024 en el Tablero Beta?")
    dax = dax_for(plan)
    assert "DATE(" not in dax
    assert "TREATAS({2024}, 'Calendario'[AÑO])" in dax and "TREATAS({1, 2, 3}, 'Calendario'[MES])" in dax, dax
    # AÑO y MES muestran UNA vez el periodo aplicado.
    assert format_filters_line(plan["filters"]) == "Filtros: enero–marzo 2024"


def test_builder_relative_periods_use_the_injected_date():
    plan = plan_for("cirugías realizadas este año en el Tablero Beta", today=date(2026, 3, 15))
    dax = dax_for(plan)
    assert "TREATAS({2026}, 'Calendario'[AÑO])" in dax and "TREATAS({1, 2, 3}, 'Calendario'[MES])" in dax, dax
    plan = plan_for("cirugías realizadas el mes pasado en el Tablero Alfa", today=date(2026, 3, 15))
    dax = dax_for(plan)
    assert "DATE(2026, 2, 1)" in dax and "DATE(2026, 3, 1)" in dax, dax
    plan = plan_for("cirugías realizadas de hoy en el Tablero Alfa", today=date(2026, 3, 15))
    assert "DATE(2026, 3, 15)" in dax_for(plan) and "DATE(2026, 3, 16)" in dax_for(plan)


def test_builder_quarter_label_and_dax():
    plan = plan_for("cirugías realizadas en el primer trimestre de 2024 en el Tablero Alfa")
    assert plan["period"]["label"] == "enero–marzo 2024 (1.er trimestre)"
    assert "DATE(2024, 4, 1)" in dax_for(plan)


def test_builder_day_period_without_date_column_is_unsupported():
    plan = builder().build("cirugías realizadas de hoy en el Tablero Beta")
    assert plan["status"] == "unsupported_filter" and plan["stage"] == "temporal_filters", plan.get("status")
    assert plan["requested_period"] == "9 de octubre de 2026 (hoy)"


def test_builder_group_by_month_on_date_hierarchy():
    plan = plan_for("cirugías realizadas por mes en 2024 en el Tablero Alfa")
    assert plan["mode"] == "grouped" and plan["group_by"][0]["column"] == "Mes"
    assert len(plan["temporal_buckets"]) == 12
    dax = dax_for(plan)
    assert dax.count("ROW(\"__orden\"") == 12 and '"diciembre 2024"' in dax
    assert "DATE(2024, 12, 1)" in dax and "DATE(2025, 1, 1)" in dax


def test_builder_group_by_quarter_on_integer_columns():
    plan = plan_for("cirugías realizadas por trimestre en 2024 en el Tablero Beta")
    dax = dax_for(plan)
    assert len(plan["temporal_buckets"]) == 4 and "DATE(" not in dax
    assert "TREATAS({10, 11, 12}, 'Calendario'[MES])" in dax, dax


def test_builder_group_by_month_without_period_uses_declared_window():
    plan = plan_for("cirugías realizadas mes a mes en el Tablero Alfa")
    assert len(plan["temporal_buckets"]) == 12
    assert plan["temporal_buckets"][0]["label"] == "octubre 2025"
    assert plan["temporal_buckets"][-1]["label"] == "septiembre 2026"
    assert any("últimos 12 meses" in note for note in plan["notes"]), plan["notes"]


def test_builder_declares_extra_month_and_period_words_are_not_filters():
    plan = plan_for("cirugías realizadas en enero y marzo de 2024 en el Tablero Alfa")
    assert any("enero" in term for term in plan["unapplied_terms"]), plan["unapplied_terms"]
    plan = plan_for("cirugías realizadas en los últimos 3 meses en el Tablero Alfa")
    assert plan["unapplied_terms"] == [] and plan["period"]["label"].endswith("(últimos 3 meses)")


def test_period_inside_metric_name_is_not_a_filter():
    analysis = builder()._analyze_periods(
        "egresos año anterior", metric={"label": "Egresos año anterior"},
    )
    assert analysis["period"] is None
    analysis = builder()._analyze_periods(
        "promedio mensual de estancia", metric={"label": "Promedio mensual de estancia"},
    )
    assert analysis["granularity"] is None


def test_reasoning_line_shows_the_applied_period():
    line = QueryEngine._filter_line({
        "type": "date_range", "table": "LAVANDERIA", "column": "Fecha", "label": "enero–marzo 2025",
        "start": "2025-01-01", "end": "2025-04-01",
    })
    assert line == "periodo enero–marzo 2025 · LAVANDERIA[Fecha] >= 2025-01-01 y < 2025-04-01", line
    assert format_filters_line([
        {"type": "date_range", "label": "2026 hasta hoy", "year": 2026},
        {"type": "categorical", "concept": "servicio", "value": "UCI"},
    ]) == "Filtros: 2026 hasta hoy · SERVICIO = UCI"
    # Filtros antiguos (sin etiqueta) siguen funcionando.
    assert format_filters_line([{"type": "date_range", "month": 1, "year": 2026}]) == "Filtros: enero 2026"


# ---------------------------------------------------------------- runner
def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print("-" * 70)
    print(f"PASS={len(tests) - failed} FAIL={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

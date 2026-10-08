"""
Selección de métrica, filtros y fechas de QueryPlanBuilder (offline).

Catálogos mínimos en un directorio temporal + proveedor Power BI falso.
Dos modelos con medidas de nombres casi idénticos:

  Gestion Alfa  / Tablero Alfa : «Cirugías Realizadas», «Cirugías» (auxiliar sin visual),
                                 «Total Cirugías». Calendario con jerarquía de FECHA.
  Gestion Beta  / Tablero Beta : «Cirugías Realizadas», «Cirugías Programadas»
                                 (página «Programación Quirúrgica»). Calendario con AÑO/MES enteros.

Ejecutar:  python -m tests.selection.test_selection      (o pytest tests/selection)
"""
import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator  # noqa: E402
from src.semantic.query_plan_builder import QueryPlanBuilder  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402

ALFA, BETA = "Gestion Alfa", "Gestion Beta"

DOMAINS = {
    (ALFA, "TABLA_A", "ESPECIALIDAD"): ["CIRUGIA PLASTICA", "ORTOPEDIA", "CIRUGIA GENERAL"],
    (ALFA, "TABLA_A", "SEDE"): ["SEDE NORTE", "SEDE SUR"],
    (ALFA, "TABLA_A", "SEXO"): ["M", "F"],
    (ALFA, "TABLA_A", "MODALIDAD"): ["PROGRAMACION", "HOSPITALIZACION", "CONSULTORIO"],
    (BETA, "TABLA_B", "ESPECIALIDAD"): ["CIRUGIA PLASTICA", "ORTOPEDIA"],
}


def _field(role, kind, table, name, **extra):
    item = {"role": role, "kind": kind, "table": table,
            "display_name": name, "native_query_ref": name, "query_ref": f"{table}.{name}"}
    if kind in ("measure", "column"):
        item["measure" if kind == "measure" else "column"] = name
    item.update(extra)
    return item


def _column(table, name):
    return _field("Values", "column", table, name)


def _metric(metric_id, model, report, label, dax, table, titles, pages):
    return {
        "metric_id": metric_id, "label": label, "measure": label, "aliases": [label],
        "semantic_model": model, "report": report, "reports": [report], "table": table,
        "dax_expression": dax, "validation_status": "approved",
        "appearances": [{"report": report, "page_display_name": page, "visual_id": f"{metric_id}_{i}",
                         "visual_title": title}
                        for i, (title, page) in enumerate(zip(titles, pages))],
    }


def _build_fixture(root):
    catalog = root / "data" / "catalog"
    rag = root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)

    registry = {
        "models": [
            {"semantic_model": ALFA, "semantic_model_key": "alfa", "technical_catalog": "data/catalog/alfa_rag.json"},
            {"semantic_model": BETA, "semantic_model_key": "beta", "technical_catalog": "data/catalog/beta_rag.json"},
        ],
        "sources": [
            {"source_group": "tablero_alfa", "report": "Tablero Alfa", "semantic_model": ALFA,
             "default_dashboard": "Resumen", "aliases": ["tablero alfa"],
             "technical_catalog": "data/catalog/alfa_rag.json"},
            {"source_group": "tablero_beta", "report": "Tablero Beta", "semantic_model": BETA,
             "default_dashboard": "Resumen", "aliases": ["tablero beta"],
             "technical_catalog": "data/catalog/beta_rag.json"},
        ],
    }
    technical_a = {"semantic_model": ALFA, "tables": [
        {"name": "TABLA_A", "columns": [
            {"name": "ESPECIALIDAD", "data_type": "String"}, {"name": "SEDE", "data_type": "String"},
            {"name": "SEXO", "data_type": "String"}, {"name": "MODALIDAD", "data_type": "String"}]},
        {"name": "Calendario", "columns": [{"name": "Date", "data_type": "DateTime"}]},
    ]}
    technical_b = {"semantic_model": BETA, "tables": [
        {"name": "TABLA_B", "columns": [{"name": "ESPECIALIDAD", "data_type": "String"}]},
        {"name": "Calendario", "columns": [{"name": "AÑO", "data_type": "Int64"},
                                           {"name": "MES", "data_type": "Int64"}]},
    ]}
    hierarchy = "Calendario.Date.Variación.Jerarquía de fechas."
    visuals_catalog = {"schema_version": 2, "reports": [
        {"report": "Tablero Alfa", "semantic_model": ALFA, "source_group": "tablero_alfa", "pages": [
            {"page_name": "p1", "page_display_name": "Resumen", "filters": {}, "visuals": [
                {"visual_id": "a_esp", "visual_type": "slicer", "fields": [_column("TABLA_A", "ESPECIALIDAD")]},
                {"visual_id": "a_sede", "visual_type": "slicer", "fields": [_column("TABLA_A", "SEDE")]},
                {"visual_id": "a_sexo", "visual_type": "slicer", "fields": [_column("TABLA_A", "SEXO")]},
                {"visual_id": "a_mod", "visual_type": "tableEx", "fields": [_column("TABLA_A", "MODALIDAD")]},
                {"visual_id": "a_anio", "visual_type": "slicer", "fields": [
                    _field("Values", "hierarchy_level", "Calendario", "Año", level="Año",
                           query_ref=hierarchy + "Año")]},
                {"visual_id": "a_mes", "visual_type": "slicer", "fields": [
                    _field("Values", "hierarchy_level", "Calendario", "Mes", level="Mes",
                           query_ref=hierarchy + "Mes")]},
            ]}]},
        {"report": "Tablero Beta", "semantic_model": BETA, "source_group": "tablero_beta", "pages": [
            {"page_name": "p2", "page_display_name": "Programación Quirúrgica", "filters": {}, "visuals": [
                {"visual_id": "b_esp", "visual_type": "slicer", "fields": [_column("TABLA_B", "ESPECIALIDAD")]},
                {"visual_id": "b_anio", "visual_type": "slicer", "fields": [_column("Calendario", "AÑO")]},
                {"visual_id": "b_mes", "visual_type": "slicer", "fields": [_column("Calendario", "MES")]},
            ]}]},
    ]}
    metrics = [
        _metric("a_real", ALFA, "Tablero Alfa", "CIRUGÍAS REALIZADAS", "[Cirugías Realizadas]", "TABLA_A",
                ["Cirugías realizadas"], ["Resumen"]),
        _metric("a_helper", ALFA, "Tablero Alfa", "CIRUGÍAS", "[Cx Auxiliar]", "TABLA_A", [], []),
        _metric("a_total", ALFA, "Tablero Alfa", "TOTAL CIRUGÍAS", "[Total Cirugías]", "TABLA_A",
                ["Total cirugías"], ["Resumen"]),
        _metric("b_real", BETA, "Tablero Beta", "CIRUGÍAS REALIZADAS", "[Cirugías Realizadas]", "TABLA_B",
                ["Cirugías realizadas"], ["Programación Quirúrgica"]),
        _metric("b_prog", BETA, "Tablero Beta", "CIRUGÍAS PROGRAMADAS", "[Cirugías Programadas]", "TABLA_B",
                ["Cirugías programadas"], ["Programación Quirúrgica"]),
    ]
    files = {
        catalog / "source_registry.json": registry,
        catalog / "alfa_rag.json": technical_a,
        catalog / "beta_rag.json": technical_b,
        rag / "visual_metrics_catalog.json": visuals_catalog,
        rag / "master_metrics.json": {"metrics": metrics},
    }
    for path, data in files.items():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class FakeProvider:
    """execute_dax para los VALUES(...) que usa el builder."""

    def execute_dax(self, dax, semantic_model=None):
        for (model, table, column), values in DOMAINS.items():
            if model == semantic_model and f"VALUES('{table}'[{column}])" in dax.replace("\n", "").replace(" ", ""):
                return {"status": "success", "rows": [{"[Value]": value} for value in values]}
        return {"status": "success", "rows": []}


_STATE = {}


def builder():
    if "builder" not in _STATE:
        tmp = tempfile.TemporaryDirectory()
        _STATE["tmp"] = tmp
        root = Path(tmp.name)
        _build_fixture(root)
        router = SourceModelRouter(
            root / "data" / "catalog" / "source_registry.json",
            root / "data" / "rag" / "visual_metrics_catalog.json", project_root=root,
        )
        _STATE["builder"] = QueryPlanBuilder(
            root / "data" / "rag" / "master_metrics.json",
            root / "data" / "rag" / "visual_metrics_catalog.json",
            router, FakeProvider(), project_root=root,
        )
    return _STATE["builder"]


def plan_for(question):
    return builder().build(question)


def dax_for(plan):
    result = QueryPlanDAXGenerator().generate(plan)
    assert result["status"] == "generated", result
    return result["dax"]


def values(plan):
    return {str(item.get("value")).upper() for item in plan.get("filters", []) if item.get("type") == "categorical"}


# ---------------------------------------------------------------- métrica
def test_specific_label_beats_generic_helper():
    plan = plan_for("¿Cuántas cirugías realizadas en el tablero alfa?")
    assert plan["status"] == "ready", plan.get("status")
    assert plan["metric"]["metric_id"] == "a_real", plan["metric"]["metric_id"]


def test_total_label_is_preferred_when_the_user_says_total():
    plan = plan_for("¿Cuál es el total de cirugías en el tablero alfa?")
    assert plan["status"] == "ready" and plan["metric"]["metric_id"] == "a_total", plan.get("status")


def test_naming_the_dashboard_picks_that_model():
    alfa = plan_for("¿Cuántas cirugías realizadas hubo en el Tablero Alfa?")
    beta = plan_for("¿Cuántas cirugías realizadas hubo en el Tablero Beta?")
    assert alfa["status"] == "ready" and alfa["semantic_model"] == ALFA
    assert beta["status"] == "ready" and beta["semantic_model"] == BETA


def test_true_tie_is_ambiguous_with_all_tied_candidates():
    result = builder().build("¿Cuántas cirugías realizadas hubo?")
    assert result["status"] == "ambiguous", result["status"]
    ids = {c["metric"]["metric_id"] for c in result["metric_resolution"]["candidates"][:2]}
    assert ids == {"a_real", "b_real"}, ids


def test_ambiguity_is_deterministic():
    first = [c["metric"]["metric_id"] for c in plan_for("cirugías realizadas")["metric_resolution"]["candidates"]]
    for _ in range(3):
        again = [c["metric"]["metric_id"] for c in plan_for("cirugías realizadas")["metric_resolution"]["candidates"]]
        assert again == first


def test_page_name_breaks_ties_between_models():
    plan = plan_for("¿Cuántas cirugías programadas en programación quirúrgica?")
    assert plan["status"] == "ready" and plan["metric"]["metric_id"] == "b_prog"


def test_programacion_is_not_programada():
    # programada/programacion y hospitalario/hospitalizacion no son la misma palabra
    from src.semantic.query_plan_builder import _token_similarity
    assert _token_similarity("programada", "programacion") < 0.82
    assert _token_similarity("hospitalario", "hospitalizacion") < 0.82
    assert _token_similarity("consulta", "consultorio") < 0.82
    assert _token_similarity("mayo", "mayor") < 0.82


# ---------------------------------------------------------------- filtros
def test_multiple_filters_all_applied():
    plan = plan_for("¿Cuántas cirugías realizadas de cirugía plástica en la sede norte en 2024 en el Tablero Alfa?")
    assert plan["status"] == "ready", plan.get("status")
    assert {"CIRUGIA PLASTICA", "SEDE NORTE"} <= values(plan), values(plan)
    assert not plan["unapplied_terms"], plan["unapplied_terms"]
    dax = dax_for(plan)
    assert "DATE(2024, 1, 1)" in dax and "'TABLA_A'[SEDE]" in dax and "'TABLA_A'[ESPECIALIDAD]" in dax


def test_one_mention_makes_one_filter():
    plan = plan_for("¿Cuántas cirugías realizadas en la sede norte en el Tablero Alfa?")
    sede = [f for f in plan["filters"] if f["column"] == "SEDE"]
    assert len(sede) == 1, sede


def test_short_value_does_not_match_inside_words():
    plan = plan_for("¿Cuántas cirugías realizadas ambulatoria programada en el Tablero Alfa?")
    assert "M" not in values(plan) and "F" not in values(plan), values(plan)
    assert plan["status"] != "ready" or "ambulatoria" in " ".join(plan["unapplied_terms"])


def test_explicit_short_value_still_works():
    plan = plan_for("¿Cuántas cirugías realizadas con sexo M en el Tablero Alfa?")
    assert plan["status"] == "ready" and "M" in values(plan), plan.get("status")


def test_table_visual_columns_are_eligible_for_implicit_values():
    plan = plan_for("cirugías realizadas hospitalizacion tablero alfa")
    assert plan["status"] == "ready" and "HOSPITALIZACION" in values(plan), plan.get("status")


def test_similar_value_prefix_is_not_equated():
    # «programada» no debe resolverse a la modalidad PROGRAMACION
    plan = plan_for("cirugías realizadas programada tablero alfa")
    assert "PROGRAMACION" not in values(plan), values(plan)


def test_unapplied_terms_when_a_word_cannot_be_applied():
    plan = plan_for("¿Cuántas cirugías realizadas de oncología en la sede norte en el Tablero Alfa?")
    assert plan["status"] == "ready", plan.get("status")
    assert "SEDE NORTE" in values(plan)
    assert any("oncologia" in term for term in plan["unapplied_terms"]), plan["unapplied_terms"]


def test_unresolved_word_without_filters_does_not_return_a_total():
    result = plan_for("¿Cuántas cirugías realizadas de oncología en el Tablero Alfa?")
    assert result["status"] == "unsupported_filter", result["status"]


# ---------------------------------------------------------------- fechas
def test_mayor_is_not_may():
    b = builder()
    assert b._detect_year_month("cirugías con mayor volumen")[1] is None
    assert b._detect_year_month("cirugías en mayo de 2024")[:2] == (2024, 5)


def test_month_only_on_date_column_filters_the_month():
    plan = plan_for("¿Cuántas cirugías realizadas en marzo en el Tablero Alfa?")
    assert plan["status"] == "ready"
    assert "MONTH('Calendario'[Date]) = 3" in dax_for(plan)
    assert any("todos los años" in note for note in plan["notes"]), plan["notes"]


def test_year_and_month_on_date_column_use_date_range():
    dax = dax_for(plan_for("¿Cuántas cirugías realizadas en marzo de 2024 en el Tablero Alfa?"))
    assert "DATE(2024, 3, 1)" in dax and "DATE(2024, 4, 1)" in dax


def test_integer_year_month_columns_are_not_compared_with_dates():
    plan = plan_for("¿Cuántas cirugías realizadas en marzo de 2024 en el Tablero Beta?")
    assert plan["status"] == "ready", plan.get("status")
    dax = dax_for(plan)
    assert "DATE(" not in dax
    assert "TREATAS({2024}, 'Calendario'[AÑO])" in dax and "TREATAS({3}, 'Calendario'[MES])" in dax, dax


def test_month_only_on_integer_columns_filters_the_month_column():
    plan = plan_for("¿Cuántas cirugías realizadas en marzo en el Tablero Beta?")
    dax = dax_for(plan)
    assert "TREATAS({3}, 'Calendario'[MES])" in dax and "[AÑO]" not in dax
    assert plan["notes"], "debe avisar que el mes aplica a todos los años"


# ---------------------------------------------------------------- DAX tipado
def test_typed_treatas_literals():
    generator = QueryPlanDAXGenerator()
    base = {"table": "T", "column": "C", "type": "categorical"}
    assert generator._categorical_filter({**base, "value": 2024, "data_type": "number"}) == "TREATAS({2024}, 'T'[C])"
    assert generator._categorical_filter({**base, "value": "2024", "data_type": "number"}) == "TREATAS({2024}, 'T'[C])"
    assert generator._categorical_filter({**base, "value": "2024", "data_type": "text"}) == 'TREATAS({"2024"}, \'T\'[C])'
    assert generator._categorical_filter({**base, "value": 'A "x"'}) == 'TREATAS({"A ""x"""}, \'T\'[C])'
    assert generator._categorical_filter({**base, "value": "abc", "data_type": "number"}) == 'TREATAS({"abc"}, \'T\'[C])'


def test_none_is_never_emitted_as_text():
    generator = QueryPlanDAXGenerator()
    assert "None" not in generator._string_literal(None)
    assert generator._categorical_filter({"table": "T", "column": "C", "value": None}) == "TREATAS({BLANK()}, 'T'[C])"


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

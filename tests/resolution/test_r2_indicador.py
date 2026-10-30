"""
Ronda 2 del banco real — indicador equivocado, periodo que la tabla no trae y
agregaciones implícitas documentadas (offline, catálogo mínimo):

  LAV   modelo sin medidas; su informe local se reconstruyó de la documentación
        y el visual «PESO TOTAL por Mes» quedó como DISTINCTCOUNT(OID); la
        documentación dice «suma de LAVANDERIA[Peso]»  (LV01, LV02, LV03)
  BRIEF TRIAGES sobre la tabla «Triages del día anterior»  (AI04, TU04)
  ATEN  TOTAL_TRIAGES (medida sin visual) sobre «Triages desde 2022-01-01»;
        «Promedio Mensual Año Pasado» (medida sin visual)
  FAC   modelo con un visual REAL que agrega otra columna: no se corrige

Ejecutar:  python -m tests.resolution.test_r2_indicador
"""
import json
import sys
import tempfile
import traceback
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.semantic.documented_aggregations import (  # noqa: E402
    aggregations_in_text, documented_aggregations, indicator_name, text_cites_title,
)
from src.semantic.query_plan_builder import QueryPlanBuilder  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from src.semantic.table_coverage import coverage_window, covers  # noqa: E402
from tests.resolution.test_resolution import _source  # noqa: E402

TODAY = date(2026, 10, 30)
LAV, BRIEF, ATEN, FAC = "Tablero_lavanderia", "BRIEFING HOSPITALARIO", "TABLERO DE ATENCIONES", "FACTURACION"


def _appearance(report, page, visual_id, title=None, visual_type="card"):
    return {"report": report, "page_display_name": page, "page_name": page, "visual_id": visual_id,
            "visual_title": title, "visual_type": visual_type}


METRICS = [
    {"metric_id": "lav_oid", "label": "PESO TOTAL por Mes", "measure": None,
     "aliases": ["PESO TOTAL por Mes", "OID", "Conteo distinto de OID", "PESO TOTAL"],
     "source_type": "visual_aggregation", "semantic_model": LAV, "report": "TABLERO LAVANDERIA",
     "reports": ["TABLERO LAVANDERIA"], "table": "LAVANDERIA", "column": "OID", "aggregation": "DistinctCount",
     "dax_expression": "DISTINCTCOUNT('LAVANDERIA'[OID])", "validation_status": "approved",
     "appearances": [_appearance("TABLERO LAVANDERIA", "Página 1", "v_lav", "PESO TOTAL por Mes")]},
    {"metric_id": "b_triages", "label": "TRIAGES", "measure": None, "aliases": ["TRIAGES"],
     "source_type": "visual_aggregation", "semantic_model": BRIEF, "report": BRIEF, "reports": [BRIEF],
     "table": "TRIAGES", "column": "OID_TRIAGE", "aggregation": "DistinctCount",
     "dax_expression": "DISTINCTCOUNT('TRIAGES'[OID_TRIAGE])", "validation_status": "approved",
     "appearances": [_appearance(BRIEF, "INICIO", "v_tri")]},
    {"metric_id": "a_total", "label": "TOTAL_TRIAGES", "measure": "TOTAL_TRIAGES", "aliases": ["TOTAL_TRIAGES"],
     "source_type": "explicit_measure", "semantic_model": ATEN, "table": "OPORTUNIDAD_TRIAGE",
     "dax_expression": "[TOTAL_TRIAGES]", "model_expression": "DISTINCTCOUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE])",
     "validation_status": "approved", "appearances": []},
    {"metric_id": "a_prom", "label": "Promedio Mensual Año Pasado", "measure": "Promedio Mensual Año Pasado",
     "aliases": ["Promedio Mensual Año Pasado"], "source_type": "explicit_measure", "semantic_model": ATEN,
     "table": "Calendario", "dax_expression": "[Promedio Mensual Año Pasado]",
     "model_expression": "AVERAGEX(VALUES(Calendario[Mes]), [TOTAL_TRIAGES])",
     "validation_status": "approved", "appearances": []},
    {"metric_id": "f_real", "label": "VALOR FACTURADO", "measure": None, "aliases": ["VALOR FACTURADO"],
     "source_type": "visual_aggregation", "semantic_model": FAC, "report": FAC, "reports": [FAC],
     "table": "FACTURAS", "column": "VALOR", "aggregation": "Sum",
     "dax_expression": "SUM('FACTURAS'[VALOR])", "validation_status": "approved",
     "appearances": [_appearance(FAC, "RESUMEN", "v_fac", "VALOR FACTURADO")]},
]
# Otros «TOTAL ...» del catálogo: «total» es una palabra común (peso IDF bajo).
METRICS += [
    {"metric_id": f"otro_{i}", "label": f"TOTAL {name}", "measure": f"TOTAL_{name}", "aliases": [],
     "source_type": "explicit_measure", "semantic_model": ATEN, "table": "OPORTUNIDAD_TRIAGE",
     "dax_expression": f"[TOTAL_{name}]", "validation_status": "approved", "appearances": []}
    for i, name in enumerate(["CIRUGIAS", "EGRESOS", "INGRESOS", "CITAS", "PARTOS", "CONSULTAS"])
]

TECHNICAL = {
    "lav": {"semantic_model": LAV, "relationships": [], "tables": [{"name": "LAVANDERIA", "measures": [], "columns": [
        {"name": "OID", "data_type": "Int64"}, {"name": "Peso", "data_type": "Double"},
        {"name": "Turno", "data_type": "Int64"}, {"name": "TURNO_OK", "data_type": "String"},
        {"name": "SERVICIO", "data_type": "String"}, {"name": "Fecha", "data_type": "DateTime"}]}]},
    "brief": {"semantic_model": BRIEF, "relationships": [], "tables": [{"name": "TRIAGES", "measures": [], "columns": [
        {"name": "OID_TRIAGE", "data_type": "Int64"}, {"name": "FECHA", "data_type": "DateTime"}]}]},
    "aten": {"semantic_model": ATEN, "relationships": [], "tables": [
        {"name": "OPORTUNIDAD_TRIAGE", "measures": [
            {"name": "TOTAL_TRIAGES", "expression": "DISTINCTCOUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE])"}],
         "columns": [{"name": "OID_TRIAGE", "data_type": "Int64"}, {"name": "FECHA", "data_type": "DateTime"}]},
        {"name": "Calendario", "measures": [], "columns": [{"name": "Date", "data_type": "DateTime"}]}]},
    "fac": {"semantic_model": FAC, "relationships": [], "tables": [{"name": "FACTURAS", "measures": [], "columns": [
        {"name": "VALOR", "data_type": "Double"}, {"name": "COPAGO", "data_type": "Double"}]}]},
}

DOCS = {
    "lav/md/_diccionario.json": {"semantic_model": "TABLERO LAVANDERIA", "dashboards": [{
        "name": "DICCIONARIO TABLERO LAVANDERIA", "is_dictionary": True,
        "description": "El modelo no tiene medidas DAX; los totales se obtienen sumando LAVANDERIA[Peso].",
        "other_sections": [
            {"section": "other", "heading": "Columnas clave",
             "text": "LAVANDERIA[Peso]: Peso de ropa registrado en cada pesaje. Tipo: decimal. Se usa en: "
                     "PESO por TURNO y PESO TOTAL por Mes (suma de la columna)"},
            {"section": "other", "heading": "Columnas clave",
             "text": "LAVANDERIA[Turno]: Código del turno. Tipo: entero."},
        ],
        "data_sources": ["LAVANDERIA: Cada fila es un pesaje de ropa hospitalaria que ingresa a lavandería. "
                         "Origen: consulta SQL."],
    }]},
    "lav/md/pagina_1.json": {"semantic_model": "TABLERO LAVANDERIA", "dashboards": [{
        "name": "Página 1",
        "indicators": [
            "Peso: Peso total de ropa registrado: suma de LAVANDERIA[Peso] en el contexto del visual.",
            "Peso total mensual: Suma de LAVANDERIA[Peso] por mes en las columnas de PESO TOTAL por Mes.",
            "Peso por turno: Peso total de cada turno (LAVANDERIA[TURNO_OK]).",
        ],
    }]},
    "brief/md/_diccionario.json": {"semantic_model": BRIEF, "dashboards": [{
        "name": "DICCIONARIO BRIEFING", "is_dictionary": True,
        "data_sources": ["TRIAGES: Triages del día anterior (DIM_TRIAGE) con clasificación y fecha. Origen: SQL."],
    }]},
    "aten/md/_diccionario.json": {"semantic_model": ATEN, "dashboards": [{
        "name": "DICCIONARIO ATENCIONES", "is_dictionary": True,
        "data_sources": ["OPORTUNIDAD_TRIAGE: Triages realizados en urgencias desde 2022-01-01 hasta hoy. "
                         "Origen: SQL."],
    }]},
    # Un visual REAL suma VALOR; la documentación habla de sumar COPAGO: no se toca el visual.
    "fac/md/pagina.json": {"semantic_model": FAC, "dashboards": [{
        "name": "RESUMEN",
        "indicators": ["Copago: suma de FACTURAS[COPAGO] de VALOR FACTURADO."],
    }]},
}


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    keys = {LAV: "lav", BRIEF: "brief", ATEN: "aten", FAC: "fac"}
    sources = [_source(key, model, model, [model.lower()]) for model, key in keys.items()]
    sources[0]["report"] = "TABLERO LAVANDERIA"
    registry = {
        "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                    "technical_catalog": s["technical_catalog"]} for s in sources],
        "sources": sources,
    }
    # Informe de lavandería reconstruido de la documentación (marca de complete_reports).
    definition = root / "data" / "pbir" / "Tablero_lavanderia.Report" / "definition"
    definition.mkdir(parents=True)
    (definition / "_completed_from_documentation.json").write_text(
        json.dumps({"origin": "inferred_from_documentation", "inferred_pages": ["Página 1"]}), encoding="utf-8")
    visuals = {"schema_version": 2, "reports": [
        {"report": "TABLERO LAVANDERIA", "semantic_model": LAV, "source_group": "lav",
         "report_definition_dir": str(definition),
         "pages": [{"page_name": "p1", "page_display_name": "Página 1", "filters": [], "visuals": []}]},
        {"report": FAC, "semantic_model": FAC, "source_group": "fac", "report_definition_dir": str(root / "nada"),
         "pages": [{"page_name": "r", "page_display_name": "RESUMEN", "filters": [], "visuals": []}]},
    ]}
    files = {
        catalog / "source_registry.json": registry,
        rag / "visual_metrics_catalog.json": visuals,
        rag / "master_metrics.json": {"metrics": METRICS},
    }
    for key, data in TECHNICAL.items():
        files[catalog / f"{key}_rag.json"] = data
    for relative, data in DOCS.items():
        files[root / "data" / "semantic_documents" / relative] = data
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class FakeProvider:
    def execute_dax(self, dax, semantic_model=None):
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
            router, FakeProvider(), project_root=root, today=TODAY,
        )
    return _STATE["builder"]


def resolve(question):
    qpb = builder()
    return qpb._resolve_metric_flexible(question, qpb._source_context(question))


def _metric(metric_id):
    return next(m for m in builder().metrics if m.get("metric_id") == metric_id)


def _ranking(resolution):
    return [(item["metric"].get("label"), item["score"]) for item in resolution.get("candidates") or []]


# ---------------------------------------------------------------- 1. textos documentados
def test_explicit_aggregation_phrases_are_found():
    assert aggregations_in_text("Peso total: suma de LAVANDERIA[Peso] en el visual.") == [
        ("LAVANDERIA", "Peso", "Sum")]
    assert aggregations_in_text("los totales se obtienen sumando LAVANDERIA[Peso].") == [
        ("LAVANDERIA", "Peso", "Sum")]
    assert aggregations_in_text("Tiempo: promedio de 'TIEMPOS'[MINUTOS].") == [("TIEMPOS", "MINUTOS", "Average")]
    # Entrada del diccionario que dice «(suma de la columna)».
    assert aggregations_in_text("LAVANDERIA[Peso]: Peso. Se usa en: PESO TOTAL (suma de la columna)") == [
        ("LAVANDERIA", "Peso", "Sum")]


def test_mentions_without_aggregation_verb_are_not_indicators():
    assert aggregations_in_text("Peso por turno: Peso total de cada turno (LAVANDERIA[TURNO_OK]).") == []
    assert aggregations_in_text("LAVANDERIA[Turno]: Código del turno. Tipo: entero.") == []
    assert aggregations_in_text("el total de LAVANDERIA[OID]") == []


def test_indicator_name_and_title_citation():
    assert indicator_name("Peso total mensual: Suma de LAVANDERIA[Peso] por mes", "LAVANDERIA", "Peso") == \
        "Peso total mensual"
    assert text_cites_title(["... en las columnas de PESO TOTAL por Mes."], "PESO TOTAL por Mes")
    assert not text_cites_title(["... PESO TOTAL por Mes."], "PESO por TURNO")
    assert not text_cites_title(["... PESO TOTAL por Mes."], "MES")   # título demasiado corto
    entries = documented_aggregations(DOCS.values())
    peso = [e for e in entries if e["column"] == "Peso"]
    assert len(peso) == 1 and peso[0]["aggregation"] == "Sum", entries
    assert peso[0]["names"] == ["Peso", "Peso total mensual"], peso[0]["names"]
    assert peso[0]["pages"] == ["Página 1"], peso[0]["pages"]


# ---------------------------------------------------------------- 2. ventana documentada de una tabla
def test_coverage_windows_from_table_descriptions():
    today = TODAY
    assert coverage_window("Triages del día anterior (DIM_TRIAGE) con clasificación", today) == (
        date(2026, 10, 29), None)
    assert coverage_window("Ingresos entre las 7:00 de ayer y las 7:00 de hoy", today)[0] == date(2026, 10, 29)
    assert coverage_window("Interconsultas. Solicitudes de los últimos 10 días.", today)[0] == date(2026, 10, 20)
    assert coverage_window("Triages desde el 01/01/2023, excepto el código UA", today) == (date(2023, 1, 1), None)
    assert coverage_window("Turnos desde el 1 de enero de 2026 de los prefijos PPE", today)[0] == date(2026, 1, 1)
    assert coverage_window("Agenda desde 2024-04-01 hasta 60 días después de hoy", today) == (
        date(2024, 4, 1), None)
    assert coverage_window("Citas desde 2024-01-01 hasta el último día del mes anterior", today) == (
        date(2024, 1, 1), date(2026, 10, 1))
    assert coverage_window("Triages registrados hoy, excepto el código UA", today)[0] == today
    # Sin ventana: «hasta hoy» solo, o nada.
    assert coverage_window("Calendario de fechas hasta hoy", today) is None
    assert coverage_window("Catálogo de servicios con su código", today) is None


def test_covers_period():
    yesterday = (date(2026, 10, 29), None)
    assert not covers(yesterday, date(2025, 1, 1), date(2026, 1, 1), TODAY)       # 2025
    assert not covers(yesterday, date(2026, 10, 1), date(2026, 10, 31), TODAY)    # este mes
    assert covers(yesterday, date(2026, 10, 29), date(2026, 10, 30), TODAY)       # ayer
    assert covers(yesterday, date(2026, 10, 30), date(2026, 10, 31), TODAY)       # hoy
    assert covers((date(2022, 1, 1), None), date(2025, 1, 1), date(2026, 1, 1), TODAY)
    assert not covers((date(2024, 1, 1), date(2026, 10, 1)), date(2026, 10, 1), date(2026, 10, 31), TODAY)
    assert covers(None, date(2025, 1, 1), date(2026, 1, 1), TODAY)


# ---------------------------------------------------------------- 3. agregación implícita documentada
def test_inferred_visual_is_corrected_by_the_documentation():
    metric = _metric("lav_oid")
    assert metric["dax_expression"] == "SUM('LAVANDERIA'[Peso])", metric["dax_expression"]
    assert metric["column"] == "Peso" and metric["aggregation"] == "Sum"
    assert metric["documented_correction"]["previous_dax"] == "DISTINCTCOUNT('LAVANDERIA'[OID])"
    aliases = {a.lower() for a in metric["aliases"]}
    assert "oid" not in aliases and "conteo distinto de oid" not in aliases, aliases
    assert {"peso", "peso total mensual", "suma de peso"} <= aliases, aliases
    # No queda un segundo indicador con la misma suma.
    same = [m for m in builder().metrics if m.get("dax_expression") == "SUM('LAVANDERIA'[Peso])"]
    assert len(same) == 1, [m["metric_id"] for m in same]


def test_real_visual_is_not_corrected_and_documented_sum_is_added():
    assert _metric("f_real")["dax_expression"] == "SUM('FACTURAS'[VALOR])"
    added = [m for m in builder().metrics if m.get("source_type") == "documented_aggregation"]
    assert [m["dax_expression"] for m in added] == ["SUM('FACTURAS'[COPAGO])"], added
    assert added[0]["label"] == "Copago" and added[0]["semantic_model"] == FAC
    assert [a["page_display_name"] for a in added[0]["appearances"]] == ["RESUMEN"]


def test_undocumented_numeric_column_is_not_an_indicator():
    assert not any("[Turno]" in str(m.get("dax_expression")) for m in builder().metrics)


def test_kilos_last_month_resolve_to_documented_weight():
    resolution = resolve("cuantos kilos de ropa se lavaron el mes pasado")
    assert resolution.get("status") == "resolved", (resolution.get("status"), _ranking(resolution))
    assert resolution["metric"]["metric_id"] == "lav_oid", _ranking(resolution)


def test_name_that_only_repeats_the_period_is_discarded():
    qpb = builder()
    assert qpb._matches_only_period("kilos de ropa del mes pasado", "Promedio Mensual Año Pasado")
    assert not qpb._matches_only_period("promedio mensual del año pasado", "Promedio Mensual Año Pasado")
    assert not qpb._matches_only_period("triages del mes pasado", "TRIAGES")


def test_ranking_by_shift_uses_the_dictionary_description():
    resolution = resolve("en que turno se lava mas ropa?")
    assert resolution.get("status") == "resolved", (resolution.get("status"), _ranking(resolution))
    assert resolution["metric"]["metric_id"] == "lav_oid"
    assert resolution.get("dictionary_match")


def test_ranking_by_shift_plans_a_grouped_top_one():
    plan = builder().build("en que turno se lava mas ropa?")
    assert plan.get("status") == "ready", (plan.get("status"), plan.get("reason"), plan.get("resolution_notes"))
    assert [field.get("column") for field in plan.get("group_by") or []] == ["TURNO_OK"]
    ranking = plan.get("ranking") or {}
    assert ranking.get("direction") == "desc" and ranking.get("limit") == 1, ranking


def test_asked_dimension_is_not_a_dimension_value_filter():
    qpb = builder()
    candidates = qpb._metric_dimensions(_metric("lav_oid"))
    specs = qpb._detect_explicit_dimension_filters("en que turno se lava mas ropa", candidates)
    assert not specs, [(spec["field"].get("column"), spec["value_hint"]) for spec in specs]


def test_dictionary_does_not_invent_when_nothing_describes_the_question():
    resolution = resolve("en que turno se atienden mas partos?")
    assert resolution.get("status") != "resolved" or resolution["metric"]["metric_id"] != "lav_oid"


# ---------------------------------------------------------------- 4. periodo que la tabla no trae
def test_year_not_in_yesterday_table_prefers_measure_that_covers_it():
    # TRIAGES (tabla del día anterior) y TOTAL_TRIAGES son el mismo indicador
    # en dos tableros; solo el segundo trae 2025, aunque no tenga visual.
    plan = builder().build("cuantos triages hubo en 2025")
    metric = plan.get("metric") or {}
    if not metric:
        candidates = (plan.get("metric_resolution") or {}).get("candidates") or []
        assert len(candidates) == 1, (plan.get("status"), _ranking(plan.get("metric_resolution") or {}))
        metric = candidates[0]["metric"]
    assert metric.get("metric_id") == "a_total", (plan.get("status"), metric.get("label"),
                                                   plan.get("resolution_notes"))


def test_recent_period_keeps_the_board_metric():
    qpb = builder()
    assert qpb._metric_misses_period(_metric("b_triages"), date(2026, 10, 29), date(2026, 10, 30)) is None
    assert qpb._metric_misses_period(_metric("b_triages"), date(2026, 10, 1), date(2026, 10, 31)) == "TRIAGES"
    assert qpb._metric_misses_period(_metric("a_total"), date(2025, 1, 1), date(2026, 1, 1)) is None
    resolution = resolve("cuantos triages hubo ayer")
    labels = [item["metric"]["metric_id"] for item in resolution.get("candidates") or []]
    assert labels and labels[0] == "b_triages", _ranking(resolution)


TESTS = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]


def main():
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} pruebas correctas")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

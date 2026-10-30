"""
Filtros del tablero y columna de fecha (auditoría del banco real, 2026-10-29),
offline con un catálogo mínimo:

1. La cifra de un indicador lleva los filtros de su visual Y de su página
   (BH01: %OCUPACION 75 % sin filtros frente a 92 % en la tarjeta de GESTIÓN
   CAMAS). Vale para medidas explícitas y agregaciones de visual.
2. Si aparece en varios visuales con filtros distintos se usa la tarjeta
   (o el visual de la página principal); si ninguno es canónico, el valor
   general y se dice por qué.
3. Filtros de otras tablas que no filtran la del indicador no cuentan; el
   orden de «y» no hace distintos dos filtros iguales (BH15).
4. Un filtro de fecha «en blanco» es un estado (FM01: FECHA_CIERRE en
   blanco = pendiente) y sí se aplica; uno de fecha relativa no bloquea.
5. La pregunta manda sobre la misma columna; la respuesta dice qué filtros
   del tablero aplicó.
6. Columna de fecha (TU04/AI04, BH14, AI03): la de la tabla del indicador o
   la de su calendario relacionado; la del evento que mide (EGRESOS →
   FECHA_EGRESO); nunca la de una tabla ligada por muchos-a-muchos.

Ejecutar:  python -m tests.resolution.test_filtros_tablero
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

from src.semantic.query_plan_builder import QueryPlanBuilder  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.resolution.test_resolution import _column, _source  # noqa: E402

BRIEF, FARM, ATEN = "BRIEFING", "FARMACIA", "ATENCIONES"
CAMAS, SERV, TRI, CP, EGR = "CAMAS DISPONIBLES", "SERVICIOS", "TRIAGES", "CONSULTAS PRIORITARIAS", "EGRESOS"
PEND = "PENDIENTES_FARMACIA"
FACT, PROM, CAL = "FACT_EGRESOS", "PROMEDIO_ESTANCIA", "Calendario"

EXCLUIDOS = {"op": "not", "arg": {"op": "in", "values": [None, "BLOQUEAR", "QUIROFANO"]}}
SIN_CE = {"op": "not", "arg": {"op": "in", "values": ["CUIDADO ESPECIAL"]}}
MOSTRAR = {"op": "not", "arg": {"op": "in", "values": ["NO MOSTRAR"]}}
TRIAGE_A = {"op": "and", "args": [{"op": "not", "arg": {"op": "contains", "value": "MUERTO"}},
                                  {"op": "not", "arg": {"op": "contains", "value": "OBSTETRICA"}}]}
TRIAGE_B = {"op": "and", "args": [{"op": "not", "arg": {"op": "contains", "value": "OBSTETRICA"}},
                                  {"op": "not", "arg": {"op": "contains", "value": "MUERTO"}}]}


def _metric(metric_id, model, label, table, expression, appearances, source_type="explicit_measure"):
    return {
        "metric_id": metric_id, "label": label,
        "measure": label if source_type == "explicit_measure" else None,
        "aliases": [label], "source_type": source_type, "semantic_model": model, "report": model,
        "reports": [model], "table": table,
        "dax_expression": f"[{label}]" if source_type == "explicit_measure" else expression,
        "model_expression": expression if source_type == "explicit_measure" else None,
        "validation_status": "approved",
        "appearances": [
            {"report": model, "page_display_name": page, "visual_id": visual_id, "visual_type": kind,
             "visual_title": None}
            for page, visual_id, kind in appearances
        ],
    }


METRICS = [
    _metric("ocup", BRIEF, "%OCUPACION", CAMAS, "DIVIDE(SUM('CAMAS DISPONIBLES'[OCUPADAS]), "
            "DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO]))",
            [("INICIO", "combo", "lineClusteredColumnComboChart"), ("GESTIÓN CAMAS", "card_ocup", "card")]),
    _metric("triages", BRIEF, "TRIAGES", TRI, "DISTINCTCOUNT('TRIAGES'[OID_TRIAGE])",
            [("INICIO", "dona", "donutChart"), ("URGENCIAS", "matriz_tri", "pivotTable")],
            source_type="visual_aggregation"),
    _metric("dos_tarjetas", BRIEF, "CAMAS LIBRES", CAMAS, "COUNT('CAMAS DISPONIBLES'[HCACODIGO])",
            [("PISO 4", "card_p4", "card"), ("PISO 5", "card_p5", "card")]),
    _metric("egresos", BRIEF, "EGRESOS", EGR, "DISTINCTCOUNT('EGRESOS'[INGRESO])",
            [("INGRESOS Y EGRESOS", "card_egr", "card")], source_type="visual_aggregation"),
    _metric("pend", FARM, "NÚMERO DE SUMINISTROS PENDIENTES", PEND, "DISTINCTCOUNT('PENDIENTES_FARMACIA'[HCNFOLIO])",
            [("INICIO", "card_pend", "card")], source_type="visual_aggregation"),
    _metric("giro", ATEN, "GIRO_CAMA", FACT, "DIVIDE(COUNTROWS('FACT_EGRESOS'), 10)",
            [("INDICADORES", "card_giro", "card")]),
]


def _filter(scope, table, column, condition, error=None, kind="Categorical"):
    item = {"scope": scope, "name": f"{table}.{column}", "type": kind,
            "field": {"kind": "column", "table": table, "column": column, "model_valid": True},
            "values": [], "has_condition": condition is not None or bool(error), "condition": condition}
    if error:
        item["condition_error"] = error
    return item


def _visual(visual_id, kind, page_filters, visual_filters=(), fields=()):
    return {"visual_id": visual_id, "visual_type": kind, "fields": list(fields),
            "filters": {"inherited": {"report": [], "page": list(page_filters)}, "visual": list(visual_filters)}}


def _page(name, filters, visuals):
    return {"page_name": name, "page_display_name": name, "filters": list(filters), "visuals": visuals}


INICIO_F = [_filter("page", CAMAS, "MOSTRAR", MOSTRAR)]
GESTION_F = [_filter("page", SERV, "HSUNOMBRE", EXCLUIDOS), _filter("page", CAMAS, "MOSTRAR", MOSTRAR),
             _filter("page", CAMAS, "FECHA", None, error="condición Between no soportada", kind="RelativeDate"),
             _filter("page", CAMAS, "RUTA_ACV", None)]
EGR_F = [_filter("page", EGR, "SERVICIO", {"op": "not", "arg": {"op": "in", "values": ["HOSPITALIZACION PARCIAL"]}})]


def _relation(source, source_column, target, target_column, to_cardinality="One", both=False):
    return {"FromTable": source, "FromColumn": source_column, "ToTable": target, "ToColumn": target_column,
            "IsActive": True, "ToCardinality": to_cardinality,
            "CrossFilteringBehavior": "BothDirections" if both else "OneDirection"}


def _table(name, columns):
    return {"name": name, "columns": [
        {"name": column, "data_type": "DateTime" if kind == "d" else "String"} for column, kind in columns]}


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    keys = {BRIEF: "brief", FARM: "farm", ATEN: "aten"}
    sources = [_source(key, model, model, [model.lower()]) for model, key in keys.items()]
    registry = {
        "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                    "technical_catalog": s["technical_catalog"]} for s in sources],
        "sources": sources,
    }
    technical = {
        "brief": {"semantic_model": BRIEF, "tables": [
            _table(CAMAS, [("HCACODIGO", "s"), ("MOSTRAR", "s"), ("OCUPADAS", "s"), ("HPNSUBGRU", "s"),
                           ("FECHA", "d"), ("RUTA_ACV", "s")]),
            _table(SERV, [("OID", "s"), ("HSUNOMBRE", "s")]),
            _table(TRI, [("OID_TRIAGE", "s"), ("DESCRI_TRIGE", "s"), ("GPADOCUME", "s"), ("FECHA", "d"),
                         ("FECHA_TRIAGE", "d"), ("TramoHorario", "d")]),
            _table(CP, [("PACNUMDOC", "s"), ("FECHA", "d")]),
            _table(EGR, [("INGRESO", "s"), ("SERVICIO", "s"), ("FECHA_INGRESO", "d"), ("FECHA_EGRESO", "d")]),
        ], "relationships": [
            _relation(CAMAS, "HPNSUBGRU", SERV, "OID"),
            _relation(TRI, "GPADOCUME", CP, "PACNUMDOC", to_cardinality="Many", both=True),
        ]},
        "farm": {"semantic_model": FARM, "tables": [
            _table(PEND, [("HCNFOLIO", "s"), ("FECHA_CIERRE", "d"), ("SERVICIO", "s")]),
        ], "relationships": []},
        "aten": {"semantic_model": ATEN, "tables": [
            _table(FACT, [("OID", "s"), ("FECHA", "d")]),
            _table(PROM, [("FECHA", "d"), ("DIAS", "s")]),
            _table(CAL, [("Date", "d")]),
        ], "relationships": [_relation(FACT, "FECHA", CAL, "Date")]},
    }
    for model, entry in technical.items():
        for table in entry["tables"]:
            table["measures"] = [
                {"name": m["label"], "expression": m["model_expression"]} for m in METRICS
                if keys[m["semantic_model"]] == model and m["table"] == table["name"] and m["model_expression"]
            ]
    visuals = {"schema_version": 2, "reports": [
        {"report": BRIEF, "semantic_model": BRIEF, "source_group": "brief", "pages": [
            _page("INICIO", INICIO_F, [
                _visual("combo", "lineClusteredColumnComboChart", INICIO_F,
                        [_filter("visual", SERV, "HSUNOMBRE", SIN_CE)]),
                _visual("dona", "donutChart", INICIO_F, [_filter("visual", TRI, "DESCRI_TRIGE", TRIAGE_A)]),
            ]),
            _page("GESTIÓN CAMAS", GESTION_F, [_visual("card_ocup", "card", GESTION_F)]),
            _page("URGENCIAS", [], [_visual("matriz_tri", "pivotTable", [],
                                            [_filter("visual", TRI, "DESCRI_TRIGE", TRIAGE_B)])]),
            _page("PISO 4", [], [_visual("card_p4", "card", [], [_filter("visual", CAMAS, "MOSTRAR", MOSTRAR)])]),
            _page("PISO 5", [], [_visual("card_p5", "card", [], [_filter("visual", SERV, "HSUNOMBRE", SIN_CE)])]),
            _page("INGRESOS Y EGRESOS", EGR_F, [_visual("card_egr", "card", EGR_F)]),
        ]},
        {"report": FARM, "semantic_model": FARM, "source_group": "farm", "pages": [
            _page("INICIO", [], [_visual("card_pend", "card", [], [
                _filter("visual", PEND, "FECHA_CIERRE", {"op": "in", "values": [None]})])]),
        ]},
        {"report": ATEN, "semantic_model": ATEN, "source_group": "aten", "pages": [
            _page("INDICADORES", [], [_visual("card_giro", "card", [], [], fields=[_column(CAL, "Date")])]),
        ]},
    ]}
    files = {
        catalog / "source_registry.json": registry,
        rag / "visual_metrics_catalog.json": visuals,
        rag / "master_metrics.json": {"metrics": METRICS},
        **{catalog / f"{key}_rag.json": value for key, value in technical.items()},
    }
    for path, data in files.items():
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
            router, FakeProvider(), project_root=root,
        )
    return _STATE["builder"]


def loaded(metric_id):
    return next(item for item in builder().metrics if item["metric_id"] == metric_id)


def columns(metric):
    return {(item["table"], item["column"], item.get("scope")) for item in metric.get("visual_filters") or []}


def best_date(metric_id, candidates):
    qpb = builder()
    model = loaded(metric_id)["semantic_model"]
    fields = [{"table": table, "column": column, "aliases": [column], "kind": "column", "relevance_score": 0}
              for table, column in candidates]
    qpb._date_metric = loaded(metric_id)
    try:
        chosen = qpb._best_date_field(fields, model)
    finally:
        qpb._date_metric = None
    return None if chosen is None else (chosen["table"], chosen["column"])


# ---------------------------------------------------------------- 1-2. visual + página, el canónico
def test_measure_takes_card_and_page_filters():
    metric = loaded("ocup")
    # La tarjeta de GESTIÓN CAMAS (no el gráfico de INICIO) con los filtros de su página.
    assert columns(metric) == {(SERV, "HSUNOMBRE", "page"), (CAMAS, "MOSTRAR", "page")}, columns(metric)
    assert metric["base_dax_expression"] == "[%OCUPACION]"
    assert metric["dax_expression"].startswith("CALCULATE([%OCUPACION], KEEPFILTERS(FILTER(ALL('SERVICIOS'[HSUNOMBRE])")
    assert "ISBLANK('SERVICIOS'[HSUNOMBRE])" in metric["dax_expression"]
    assert metric["board_filters_source"]["page"] == "GESTIÓN CAMAS"
    # Fecha relativa de la página (sin traducir) y filtro sin condición: no bloquean ni se aplican.
    assert "FECHA" not in metric["dax_expression"] and "RUTA_ACV" not in metric["dax_expression"]


def test_same_filters_in_any_order_and_unrelated_page_filters():
    metric = loaded("triages")
    # El filtro de página de INICIO es de CAMAS DISPONIBLES, que no filtra TRIAGES;
    # las dos apariciones piden lo mismo (MUERTO y OBSTETRICA en distinto orden).
    assert columns(metric) == {(TRI, "DESCRI_TRIGE", "visual")}, columns(metric)
    assert "MOSTRAR" not in metric["dax_expression"]


def test_two_cards_with_different_filters_keep_general_value():
    metric = loaded("dos_tarjetas")
    assert not metric.get("visual_filters") and metric["dax_expression"] == "[CAMAS LIBRES]"
    assert metric.get("board_filters_note") == "filtros distintos en cada visual"


# ---------------------------------------------------------------- 4. fechas como estado
def test_blank_date_filter_is_a_state():
    metric = loaded("pend")
    assert columns(metric) == {(PEND, "FECHA_CIERRE", "visual")}, columns(metric)
    assert "ISBLANK('PENDIENTES_FARMACIA'[FECHA_CIERRE])" in metric["dax_expression"]


# ---------------------------------------------------------------- 5. la pregunta manda y se informa
def test_question_filter_replaces_board_filter_and_note_is_shown():
    qpb = builder()
    plan = {"status": "ready", "metric": loaded("ocup"), "notes": [], "group_by": [],
            "filters": [{"type": "categorical", "table": SERV, "column": "HSUNOMBRE", "value": "QUIROFANO"}]}
    plan = qpb._apply_board_filter_context(plan)
    metric = plan["metric"]
    assert columns(metric) == {(CAMAS, "MOSTRAR", "page")}, columns(metric)
    assert "HSUNOMBRE" not in metric["dax_expression"]
    assert loaded("ocup")["visual_filters"][0]["column"] == "HSUNOMBRE"  # el catálogo no cambia
    assert any("reemplazado" in note and "HSUNOMBRE" in note for note in plan["notes"]), plan["notes"]
    note = next(note for note in plan["notes"] if note.startswith("Filtros del tablero aplicados"))
    assert "tarjeta de la página GESTIÓN CAMAS" in note and "MOSTRAR no es NO MOSTRAR" in note, note

    plain = qpb._apply_board_filter_context(
        {"status": "ready", "metric": loaded("ocup"), "notes": [], "filters": [], "group_by": []})
    text = plain["notes"][-1]
    assert text.startswith("Filtros del tablero aplicados (tarjeta de la página GESTIÓN CAMAS): HSUNOMBRE no es"), text


def test_built_plan_carries_board_filters():
    plan = builder().build("cual es el nivel de ocupacion del briefing")
    assert plan.get("status") == "ready", plan.get("status")
    assert (plan["metric"].get("visual_filters") or []), plan["metric"]
    assert any(str(note).startswith("Filtros del tablero aplicados") for note in plan.get("notes") or []), plan.get("notes")


# ---------------------------------------------------------------- 6. columna de fecha
def test_date_of_metric_table_not_many_to_many_table():
    # TU04/AI04: CONSULTAS PRIORITARIAS solo se liga a TRIAGES por el documento del paciente.
    # Aunque no esté entre las candidatas, compite la fecha de TRIAGES (la del triage gana).
    assert best_date("triages", [(CP, "FECHA")]) == (TRI, "FECHA_TRIAGE")
    assert best_date("triages", [(CP, "FECHA"), (TRI, "FECHA_TRIAGE")]) == (TRI, "FECHA_TRIAGE")


def test_date_of_the_measured_event():
    # BH14: EGRESOS se cuenta por la fecha de egreso, no la de ingreso.
    assert best_date("egresos", [(EGR, "FECHA_INGRESO"), (EGR, "FECHA_EGRESO")]) == (EGR, "FECHA_EGRESO")
    assert best_date("egresos", [(EGR, "FECHA_EGRESO"), (EGR, "FECHA_INGRESO")]) == (EGR, "FECHA_EGRESO")


def test_time_of_day_is_not_the_period_and_synonyms_count():
    # TU04: TRIAGES[TramoHorario] es la hora del día, no la fecha del periodo.
    qpb = builder()
    tramo = {"table": TRI, "column": "TramoHorario", "aliases": ["TramoHorario", "fecha"], "kind": "column",
             "relevance_score": 100}
    qpb._date_metric = loaded("triages")
    try:
        chosen = qpb._best_date_field([tramo], BRIEF)
    finally:
        qpb._date_metric = None
    assert (chosen["table"], chosen["column"]) == (TRI, "FECHA_TRIAGE"), chosen
    # BH14: EGRESOS de BRIEFING solo tiene SALIDA_SERV (= fecha de egreso).
    named, _ = builder()._metric_event_stems(loaded("egresos"))
    salida = builder()._date_column_stems("SALIDA_SERV") & builder()._EVENT_STEMS
    assert salida and salida <= named and not builder()._stem_in("ingres", named), (salida, named)


def test_related_calendar_beats_unrelated_table_date():
    # AI03: PROMEDIO_ESTANCIA no filtra FACT_EGRESOS; el calendario sí (y es el del visual).
    assert best_date("giro", [(PROM, "FECHA"), (CAL, "Date")]) == (CAL, "Date")
    assert best_date("giro", [(PROM, "FECHA")]) == (CAL, "Date")


def test_without_metric_context_nothing_changes():
    qpb = builder()
    fields = [{"table": CP, "column": "FECHA", "aliases": ["FECHA"], "kind": "column", "relevance_score": 0}]
    assert qpb._best_date_field(fields, BRIEF)["table"] == CP


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
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

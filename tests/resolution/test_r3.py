"""
Ronda r3 del banco real, offline con catálogos mínimos:

  AI01/AI08  «egresos el mes pasado»: EGRESOS del BRIEFING solo se ve en páginas
             del bloque «Día» (foto del día) y su tabla no documenta ventana: no
             compite con Total Egresos para un periodo pasado.
  TU08       «IMÁGENES TOMADAS» en tarjeta (SUM) y gráfico (DISTINCTCOUNT) de la
             misma página y tabla: un solo indicador; «semana en curso» es una
             ventana documentada.
  BH18       la agrupación por una columna que ya se llama ESPECIALIDAD no toma el
             nombre calificado de un visual («ESPECIALIDAD CIRUGÍA»).
  AI05       el calendario que filtra una dimensión de la tabla del indicador
             (Calendario → OPORTUNIDAD_TRIAGE → CONSULTA_URGENCIAS) es su fecha.
  EP02       informe nombrado + una página suya por su nombre completo.
  AB04       «¿cuál es el antibiótico que más se usa?»: el indicador del gráfico
             agrupado por esa entidad.
  TU10       «agosto contra el mes pasado» = dos meses comparados (rango agrupado
             por mes); en un empate no compite quien no explica una palabra que
             el mejor nombra («triage»).

Ejecutar:  python -m tests.resolution.test_r3
"""
import json
import sys
import tempfile
import traceback
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.semantic.query_plan_builder import QueryPlanBuilder  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from src.semantic.period_parser import PeriodParser  # noqa: E402
from src.semantic.table_coverage import coverage_window  # noqa: E402
from tests.resolution.test_resolution import _source  # noqa: E402

BRIEF = "BRIEFING HOSPITALARIO"
ATEN = "TABLERO DE ATENCIONES INSTITUCIONALES"
TODAY = date(2026, 10, 30)


def _metric(metric_id, label, model, table, dax, pages, visual_type="card", measure=None):
    return {
        "metric_id": metric_id, "label": label, "measure": measure, "aliases": [label],
        "source_type": "visual_aggregation" if not measure else "measure",
        "semantic_model": model, "report": model, "reports": [model],
        "table": table, "column": "X", "aggregation": "DistinctCount", "dax_expression": dax,
        "validation_status": "approved",
        "appearances": [{"report": model, "page_display_name": page, "page_name": page,
                         "visual_id": f"v_{metric_id}_{index}", "visual_title": None, "visual_type": visual_type}
                        for index, page in enumerate(pages)],
    }


METRICS = [
    _metric("eg_brief", "EGRESOS", BRIEF, "EGRESOS", "DISTINCTCOUNT('EGRESOS'[INGRESO])",
            ["INICIO", "INGRESOS Y EGRESOS"]),
    _metric("eg_hist", "EGRESOS HISTORICOS", BRIEF, "EGRESOS_HIST", "DISTINCTCOUNT('EGRESOS_HIST'[INGRESO])",
            ["INICIO"]),
    _metric("eg_aten", "Total Egresos", ATEN, "FACT_EGRESOS", "[Total Egresos]", ["EGRESOS"]),
]


def _page_doc(model, page, block):
    return {"semantic_model": model, "dashboards": [{
        "name": page, "md_metadata": {"tablero": model, "pagina": page, "bloque": block}}]}


DICTIONARY = {"semantic_model": BRIEF, "dashboards": [{
    "name": "DICCIONARIO BRIEFING", "is_dictionary": True,
    "data_sources": [
        "EGRESOS: Vista CD_EGRESOS con servicio, cama, ingreso y fecha de salida. Origen: SQL.",
        "EGRESOS_HIST: Egresos desde el 1 de enero de 2024. Origen: SQL.",
    ],
}]}


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    sources = [_source("brief", BRIEF, BRIEF, ["briefing"]), _source("aten", ATEN, ATEN, ["atenciones"])]
    docs = root / "data" / "semantic_documents"
    files = {
        catalog / "source_registry.json": {
            "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                        "technical_catalog": s["technical_catalog"]} for s in sources],
            "sources": sources},
        rag / "visual_metrics_catalog.json": {"schema_version": 2, "reports": []},
        rag / "master_metrics.json": {"metrics": METRICS},
        catalog / "brief_rag.json": {"semantic_model": BRIEF, "relationships": [], "tables": []},
        catalog / "aten_rag.json": {"semantic_model": ATEN, "relationships": [], "tables": []},
        docs / "brief" / "md" / "_diccionario.json": DICTIONARY,
        docs / "brief" / "md" / "inicio.json": _page_doc(BRIEF, "INICIO", "Día"),
        docs / "brief" / "md" / "ingresos_y_egresos.json": _page_doc(BRIEF, "INGRESOS Y EGRESOS", "Día"),
        docs / "aten" / "md" / "egresos.json": _page_doc(ATEN, "EGRESOS", "Histórico"),
    }
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
        router = SourceModelRouter(root / "data" / "catalog" / "source_registry.json",
                                   root / "data" / "rag" / "visual_metrics_catalog.json", project_root=root)
        _STATE["builder"] = QueryPlanBuilder(
            root / "data" / "rag" / "master_metrics.json", root / "data" / "rag" / "visual_metrics_catalog.json",
            router, FakeProvider(), project_root=root, today=TODAY,
        )
    return _STATE["builder"]


def _by_id(metric_id):
    return next(metric for metric in METRICS if metric["metric_id"] == metric_id)


# ---------------------------------------------------------------- AI01 / AI08
def test_day_block_pages_do_not_answer_last_month():
    qpb = builder()
    last_month = (date(2026, 9, 1), date(2026, 10, 1))
    missing = qpb._metric_misses_period(_by_id("eg_brief"), *last_month, pages=True)
    assert missing and "INGRESOS Y EGRESOS" in missing, missing
    # Ayer sí lo trae la foto del día.
    yesterday = TODAY - timedelta(days=1)
    assert qpb._metric_misses_period(_by_id("eg_brief"), yesterday, TODAY, pages=True) is None
    # Sin pages=True (descartar el único candidato) la página no basta.
    assert qpb._metric_misses_period(_by_id("eg_brief"), *last_month) is None


def test_documented_table_window_wins_over_the_page_block():
    qpb = builder()
    # EGRESOS_HIST documenta «desde el 1 de enero de 2024» aunque se vea en INICIO (bloque Día).
    assert qpb._metric_misses_period(_by_id("eg_hist"), date(2026, 9, 1), date(2026, 10, 1), pages=True) is None


def test_historic_page_is_not_a_day_snapshot():
    qpb = builder()
    assert qpb._metric_misses_period(_by_id("eg_aten"), date(2026, 9, 1), date(2026, 10, 1), pages=True) is None


def test_homonyms_keep_only_the_ones_that_cover_last_month():
    qpb = builder()
    items = [{"metric": _by_id("eg_brief")}, {"metric": _by_id("eg_aten")}]
    kept = qpb._items_covering_period("cuantos egresos hubo el mes pasado", items)
    assert [item["metric"]["metric_id"] for item in kept] == ["eg_aten"], kept
    assert qpb._items_covering_period("cuantos egresos hubo ayer", items) is None


def test_metric_without_appearances_has_no_page_window():
    qpb = builder()
    metric = {**_by_id("eg_brief"), "appearances": []}
    assert qpb._metric_misses_period(metric, date(2026, 9, 1), date(2026, 10, 1), pages=True) is None


# ---------------------------------------------------------------- TU08
def test_week_in_course_is_a_documented_window():
    window = coverage_window("Estudios de imágenes realizados. Periodo de la semana en curso. Origen: SQL.", TODAY)
    assert window == (date(2026, 10, 26), None), window


def _img(metric_id, label, dax, page, visual_type, table="IMAGENES", model="TABLERO TIEMPOS URGENCIAS"):
    return {"metric_id": metric_id, "label": label, "semantic_model": model, "table": table,
            "dax_expression": dax, "appearances": [{"page_display_name": page, "visual_type": visual_type}]}


def test_card_and_chart_of_the_same_page_are_one_indicator():
    qpb = builder()
    chart = _img("a", "IMÁGENES TOMADAS", "DISTINCTCOUNT('IMAGENES'[OID_SOLICITUD])", "IMAGENES",
                 "lineClusteredColumnComboChart")
    card = _img("b", "IMAGENES TOMADAS", "SUM('IMAGENES'[SOLICITUDES_CANT])", "IMAGENES", "card")
    assert qpb._page_twins(chart, card)
    kept = qpb._collapse_page_twins([{"metric": chart}, {"metric": card}])
    assert [item["metric"]["metric_id"] for item in kept] == ["b"], kept  # se queda la tarjeta


def test_same_name_on_other_pages_or_tables_are_not_twins():
    qpb = builder()
    inicio = _img("c", "CONSULTAS ASIGNADAS", "DISTINCTCOUNT('CITAS_ASIGNADAS'[OID_CITA])", "INICIO", "card",
                  table="CITAS_ASIGNADAS", model="ASIGNACION DE CITAS")
    asignadas = _img("d", "CONSULTAS ASIGNADAS", "DISTINCTCOUNT('EN_ESPERA'[OID_CITA])", "ASIGNADAS", "card",
                     table="EN_ESPERA", model="ASIGNACION DE CITAS")
    assert not qpb._page_twins(inicio, asignadas)
    other_page = _img("e", "IMAGENES TOMADAS", "SUM('IMAGENES'[SOLICITUDES_CANT])", "RESUMEN", "card")
    chart = _img("a", "IMÁGENES TOMADAS", "DISTINCTCOUNT('IMAGENES'[OID_SOLICITUD])", "IMAGENES", "barChart")
    assert not qpb._page_twins(chart, other_page)


# ---------------------------------------------------------------- BH18
def test_group_label_keeps_a_column_already_named_as_the_business_word():
    qpb = builder()
    original = qpb._column_business_names
    qpb._column_business_names = lambda model, column, table=None: ["ESPECIALIDAD CIRUGÍA"]
    try:
        field = {"table": "PACIENTES X ASEGURADORA", "column": "ESPECIALIDAD", "aliases": ["ESPECIALIDAD"],
                 "semantic_model": BRIEF}
        assert qpb._group_label(field) == "ESPECIALIDAD"
        qualified = {**field, "aliases": ["ESPECIALIDAD CIRUGÍA", "ESPECIALIDAD"]}
        assert qpb._group_label(qualified) == "ESPECIALIDAD"
        # Un código técnico sí toma el nombre de negocio del visual.
        qpb._column_business_names = lambda model, column, table=None: ["ESPECIALIDAD"]
        technical = {"table": "INTERCONSULTA", "column": "GEEDESCRI", "aliases": ["GEEDESCRI"],
                     "semantic_model": BRIEF}
        assert qpb._group_label(technical) == "ESPECIALIDAD"
    finally:
        qpb._column_business_names = original


# ---------------------------------------------------------------- AI05
EPS_RELATIONS = [
    {"FromTable": "CONSULTA_URGENCIAS", "FromColumn": "OID_TRIAGE", "ToTable": "OPORTUNIDAD_TRIAGE",
     "ToColumn": "OID_TRIAGE", "ToCardinality": "One", "IsActive": True},
    {"FromTable": "OPORTUNIDAD_TRIAGE", "FromColumn": "FECHA", "ToTable": "Calendario", "ToColumn": "Fecha",
     "ToCardinality": "One", "IsActive": True},
    {"FromTable": "OPORTUNIDAD_TRIAGE", "FromColumn": "HH", "ToTable": "LocalDateTable_x", "ToColumn": "Date",
     "ToCardinality": "One", "IsActive": True},
]


def _with_eps_model(qpb, test):
    names = ("_has_relationship_metadata", "_technical_catalog", "_expression_tables")
    original = {name: getattr(qpb, name) for name in names}
    qpb._has_relationship_metadata = lambda model: True
    qpb._technical_catalog = lambda model: {"relationships": EPS_RELATIONS, "tables": []}
    qpb._expression_tables = lambda model, metric: {"CONSULTA_URGENCIAS"}
    try:
        return test()
    finally:
        for name, value in original.items():
            setattr(qpb, name, value)


def test_calendar_of_a_dimension_filters_the_metric():
    qpb = builder()
    metric = {"metric_id": "cu", "label": "Consultas urgencias", "semantic_model": "TABLERO EPS",
              "table": "CONSULTA_URGENCIAS", "dax_expression": "DISTINCTCOUNT('CONSULTA_URGENCIAS'[OID_TRIAGE])"}

    def check():
        tables, dimensions, calendars = qpb._metric_date_tables(metric, "TABLERO EPS")
        assert "oportunidad triage" in dimensions or "oportunidad_triage" in {d.replace(" ", "_") for d in dimensions}
        assert "calendario" in calendars and calendars["calendario"].get("via"), calendars
        assert not any(name.startswith("localdatetable") for name in calendars), calendars
        qpb._date_metric = metric
        try:
            field = qpb._best_date_field([], "TABLERO EPS")
        finally:
            qpb._date_metric = None
        assert field and field["table"] == "Calendario" and field["column"] == "Fecha", field

    _with_eps_model(qpb, check)


# ---------------------------------------------------------------- EP02
def test_page_named_in_full_inside_the_named_report():
    qpb = builder()
    pages = {
        ("tablero eps", "triages atendidos"): {"page": "TRIAGES ATENDIDOS", "semantic_model": "TABLERO EPS",
                                               "report": "TABLERO EPS", "visual": True, "members": {}},
        ("tablero eps", "dispersion general"): {"page": "DISPERSION GENERAL", "semantic_model": "TABLERO EPS",
                                                "report": "TABLERO EPS", "visual": True, "members": {}},
        ("tablero eps", "triages"): {"page": "TRIAGES", "semantic_model": "TABLERO EPS",
                                     "report": "TABLERO EPS", "visual": True, "members": {}},
    }
    context = {"status": "resolved", "routing_strength": "strong", "semantic_model": "TABLERO EPS",
               "report": "TABLERO EPS", "board_kind": "report"}
    original = (qpb._page_index, qpb._is_report_page)
    qpb._page_index = lambda: pages
    qpb._is_report_page = lambda page: False
    try:
        page = qpb._page_named_in_report("cuantos triages atendidos hay en el tablero eps", context)
        assert page and page["page"] == "TRIAGES ATENDIDOS", page
        # Una sola palabra («triages») no basta para fijar la página.
        assert qpb._page_named_in_report("cuantos triages hay en el tablero eps", context) is None
        # Sin informe nombrado no se fija ninguna página.
        assert qpb._page_named_in_report("cuantos triages atendidos hay", {"status": "unresolved"}) is None
    finally:
        qpb._page_index, qpb._is_report_page = original


# ---------------------------------------------------------------- AB04
def test_informal_ranking_uses_the_chart_grouped_by_the_entity():
    qpb = builder()
    chart = {"metric_id": "pac", "label": "PAC_ACT", "semantic_model": "TABLERO_ANTIBIOTICOS",
             "table": "ANTIBIOTICOS", "validation_status": "approved",
             "appearances": [{"visual_id": "bar", "visual_type": "barChart",
                              "visual_title": "PACIENTES ACTIVOS POR TIPO DE ANTIBIÓTICO"}]}
    detail = {"metric_id": "dias", "label": "Dias Suministrados", "semantic_model": "TABLERO_ANTIBIOTICOS",
              "table": "ANTIBIOTICOS", "validation_status": "approved",
              "appearances": [{"visual_id": "tbl", "visual_type": "tableEx", "visual_title": None}]}
    visuals = {
        ("tablero antibioticos", "bar"): {"fields": [{"kind": "column", "table": "ANTIBIOTICOS",
                                                      "column": "ANTIBIOTICO"}]},
        ("tablero antibioticos", "tbl"): {"fields": [{"kind": "column", "table": "ANTIBIOTICOS",
                                                      "column": "ANTIBIOTICO"}]},
    }
    forced = []
    names = ("metrics", "_visual_index", "_build_plan")
    original = {name: qpb.__dict__.get(name, getattr(qpb, name)) for name in names}
    qpb.metrics = [chart, detail]
    qpb._visual_index = lambda: visuals
    qpb._build_plan = lambda question, intent, forced_resolution=None: (
        forced.append(forced_resolution) or {"status": "ready", "group_by": [{"column": "ANTIBIOTICO"}]})
    try:
        plan = qpb._ranked_entity_metric("cual es el antibiotico que mas se esta usando?", {})
        assert plan and plan["status"] == "ready", plan
        assert forced[0]["metric"]["metric_id"] == "pac", forced
        assert {"usando"} & {token for token in forced[0]["consumed_tokens"]} or forced[0]["consumed_tokens"]
        # Sin ranking no aplica.
        assert qpb._ranked_entity_metric("cuantos antibioticos hay", {}) is None
    finally:
        for name, value in original.items():
            if name == "metrics":
                qpb.metrics = value
            else:
                qpb.__dict__.pop(name, None)


# ---------------------------------------------------------------- TU10
def test_two_months_compared_become_a_monthly_range():
    parser = PeriodParser(today=TODAY)
    question = "compara el tiempo promedio de triage de agosto contra el del mes pasado"
    period = parser.parse(question)
    assert (period["start"], period["end"]) == (date(2026, 8, 1), date(2026, 10, 1)), period
    assert parser.granularity(question)["unit"] == "month"
    # El año dicho en un lado vale para el mes sin año del otro.
    period = parser.parse("egresos de marzo frente a abril de 2025")
    assert (period["start"], period["end"]) == (date(2025, 3, 1), date(2025, 5, 1)), period
    # Sin comparación, nada cambia.
    assert parser.granularity("triages del mes pasado") is None
    assert parser.parse("triages del mes pasado")["start"] == date(2026, 9, 1)


def test_tie_without_the_word_the_best_names_does_not_compete():
    qpb = builder()
    best = {"metric": {"metric_id": "tt", "label": "TIEMPO PARA TRIAGE", "semantic_model": "T", "table": "OPORTUNIDAD_TRIAGE"}}
    rival = {"metric": {"metric_id": "tg", "label": "TIEMPO GESTION FACTURACION", "semantic_model": "F",
                        "table": "FACTURACION PERFILES"}}
    other = {"metric": {"metric_id": "ct", "label": "TIEMPO DE TRIAGE A ADMISION", "semantic_model": "T",
                        "table": "ADMISIONES"}}
    kept = qpb._ties_naming_the_same("tiempo promedio de triage del mes pasado", best, [best, rival, other])
    assert [item["metric"]["metric_id"] for item in kept] == ["tt", "ct"], kept


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

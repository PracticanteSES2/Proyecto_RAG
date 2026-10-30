"""
Ronda r4 del banco real (regresiones de r2-indicador-2/r3), offline con
catálogos mínimos:

  FC05  «cuánto se facturó el mes pasado»: el «indicador general» del tablero
        no puede ser TIEMPO PROMEDIO GESTION FACTURA (un tiempo, no un monto);
        y VALOR ESTIMADO de INICIO (página del bloque «Día») sí responde un mes
        pasado porque su tabla ULT_GESTION es «sin límite de fechas».
  AC01  «¿cuántas citas hay en espera?»: TOTAL GESTIÓN CITA EN ESPERA (en
        espera + asignadas, CCEESTADO 0 o 1) no es el general de «citas en
        espera» (CCEESTADO = 0); se queda CITAS EN ESPERA.
  AC04  «citas en espera por especialidad»: lo mismo agrupado.

Ejecutar:  python -m tests.resolution.test_r4
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

from src.semantic.query_plan_builder import QueryPlanBuilder  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from src.semantic.table_coverage import coverage_window, covers  # noqa: E402
from tests.resolution.test_resolution import _source  # noqa: E402

CITAS = "ASIGNACION DE CITAS"
FACT = "Tablero Control Facturacion"
TODAY = date(2026, 10, 30)
LAST_MONTH = (date(2026, 9, 1), date(2026, 10, 1))


def _metric(metric_id, label, model, table, dax, appearances, aggregation="DistinctCount"):
    return {
        "metric_id": metric_id, "label": label, "measure": None, "aliases": [label],
        "source_type": "visual_aggregation", "semantic_model": model, "report": model, "reports": [model],
        "table": table, "column": "X", "aggregation": aggregation, "dax_expression": dax,
        "validation_status": "approved",
        "appearances": [{"report": model, "page_display_name": page, "page_name": page,
                         "visual_id": f"v_{metric_id}_{index}", "visual_title": None, "visual_type": visual_type}
                        for index, (page, visual_type) in enumerate(appearances)],
    }


METRICS = [
    # ASIGNACION DE CITAS
    _metric("citas_espera", "CITAS EN ESPERA", CITAS, "EN_ESPERA", "SUM('EN_ESPERA'[PENDIENTES])",
            [("DISPO X ESPECIALIDAD", "card"), ("DISPONIBILIDAD X ESPECIALIDAD", "card")], "Sum"),
    _metric("en_espera", "EN ESPERA", CITAS, "EN_ESPERA", "SUM('EN_ESPERA'[PENDIENTES])",
            [("INICIO", "pieChart")], "Sum"),
    _metric("total_gestion", "TOTAL GESTIÓN CITA EN ESPERA", CITAS, "EN_ESPERA",
            "CALCULATE(DISTINCTCOUNT('EN_ESPERA'[OID_CITA]), 'EN_ESPERA'[CCEESTADO] IN {0, 1})",
            [("INICIO", "card")]),
    # Tablero Control Facturacion
    _metric("valor_estimado", "VALOR ESTIMADO", FACT, "ULT_GESTION", "SUM('ULT_GESTION'[FACTURADO])",
            [("INICIO", "card"), ("TRAZABILIDAD", "card")], "Sum"),
    _metric("monto_area", "MONTO FACTURADO POR ÁREA DE SERVICIO", FACT, "ULT_GESTION",
            "SUM('ULT_GESTION'[FACTURADO])", [("TRAZABILIDAD FACTURACION", "clusteredBarChart")], "Sum"),
    _metric("tiempo_factura", "TIEMPO PROMEDIO GESTION FACTURA", FACT, "FACTURACION PERFILES",
            "AVERAGE('FACTURACION PERFILES'[TIEMPO])", [("RESUMEN FACTURACION", "card")], "Average"),
]

DICTIONARIES = {
    "citas": {"semantic_model": CITAS, "dashboards": [{
        "name": "DICCIONARIO CITAS", "is_dictionary": True,
        "data_sources": [
            "EN_ESPERA: Solicitudes de cita por especialidad (lista de espera). Una fila por solicitud, "
            "registradas desde 2024-04-01 hasta hoy. Origen: SQL.",
        ],
    }]},
    "fact": {"semantic_model": FACT, "dashboards": [{
        "name": "DICCIONARIO FACTURACION", "is_dictionary": True,
        "data_sources": [
            "ULT_GESTION: Última gestión de cada ingreso abierto: perfil, servicio, área de servicio y valor "
            "estimado de los servicios cargados. Sin límite de fechas. Alimenta INICIO, TRAZABILIDAD y "
            "TRAZABILIDAD FACTURACION. Origen: SQL.",
            "FACTURACION PERFILES: Tiempos de gestión de la factura por perfil. Origen: SQL.",
        ],
    }]},
}


def _page_doc(model, page, block):
    return {"semantic_model": model, "dashboards": [{
        "name": page, "md_metadata": {"tablero": model, "pagina": page, "bloque": block}}]}


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    sources = [_source("citas", CITAS, CITAS, ["asignacion de citas"]),
               _source("fact", FACT, FACT, ["control facturacion"])]
    docs = root / "data" / "semantic_documents"
    files = {
        catalog / "source_registry.json": {
            "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                        "technical_catalog": s["technical_catalog"]} for s in sources],
            "sources": sources},
        rag / "visual_metrics_catalog.json": {"schema_version": 2, "reports": []},
        rag / "master_metrics.json": {"metrics": METRICS},
        catalog / "citas_rag.json": {"semantic_model": CITAS, "relationships": [], "tables": []},
        catalog / "fact_rag.json": {"semantic_model": FACT, "relationships": [], "tables": []},
        docs / "citas" / "md" / "_diccionario.json": DICTIONARIES["citas"],
        docs / "fact" / "md" / "_diccionario.json": DICTIONARIES["fact"],
        docs / "fact" / "md" / "inicio.json": _page_doc(FACT, "INICIO", "Día"),
        docs / "fact" / "md" / "trazabilidad.json": _page_doc(FACT, "TRAZABILIDAD", "Día"),
        docs / "fact" / "md" / "trazabilidad_facturacion.json": _page_doc(FACT, "TRAZABILIDAD FACTURACION", "Día"),
        docs / "fact" / "md" / "resumen_facturacion.json": _page_doc(FACT, "RESUMEN FACTURACION", "Histórico"),
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


def _tokens(question):
    from src.semantic.query_plan_builder import canonical_tokens
    return set(canonical_tokens(question))


def resolve(question):
    qpb = builder()
    return qpb._resolve_metric_flexible(question, qpb._source_context(question))


# ---------------------------------------------------------------- nombre del general
def test_general_name_that_says_more_than_the_question_is_not_general():
    qpb = builder()
    assert qpb._general_name_adds_words(_by_id("tiempo_factura"), _tokens("cuanto se facturo el mes pasado"))
    extra = qpb._general_name_adds_words(_by_id("total_gestion"), _tokens("cuantas citas hay en espera"))
    assert extra and "gestion" in extra, extra


def test_general_name_with_only_total_is_still_general():
    qpb = builder()
    metric = {"label": "TOTAL PACIENTES", "measure": None}
    assert qpb._general_name_adds_words(metric, _tokens("cuantos pacientes hay hospitalizados")) == []


def _general(question, metric_id):
    qpb = builder()
    best = {"metric": _by_id(metric_id), "score": 1.35, "business_score": 1.35,
            "matched_name": _by_id(metric_id)["label"]}
    return qpb._general_indicator(question, qpb._source_context(question), best)


def test_total_management_card_is_not_the_general_of_waiting_appointments():
    # Camino real de AC01/AC04: CITAS EN ESPERA (tarjeta de DISPO X
    # ESPECIALIDAD) cedía ante la tarjeta de INICIO TOTAL GESTIÓN CITA EN ESPERA.
    for question in ("cuantas citas hay en espera?", "citas en espera por especialidad"):
        general = _general(question, "citas_espera")
        assert general is None, (question, general and general["metric"].get("label"))


def test_average_time_card_is_not_the_general_of_billed_amount():
    # Camino real de FC05: MONTO FACTURADO POR ÁREA DE SERVICIO cedía ante
    # TIEMPO PROMEDIO GESTION FACTURA (tarjeta de RESUMEN FACTURACION).
    general = _general("cuanto se facturo el mes pasado", "monto_area")
    assert general is None, general and general["metric"].get("label")


# ---------------------------------------------------------------- AC01 / AC04
def test_waiting_appointments_are_not_total_management():
    resolution = resolve("cuantas citas hay en espera?")
    metric = resolution.get("metric") or {}
    assert metric.get("metric_id") != "total_gestion", (resolution.get("status"), metric.get("label"))
    assert not resolution.get("general_indicator"), metric.get("label")


def test_waiting_appointments_by_specialty_are_not_total_management():
    resolution = resolve("citas en espera por especialidad")
    metric = resolution.get("metric") or {}
    assert metric.get("metric_id") != "total_gestion", (resolution.get("status"), metric.get("label"))


# ---------------------------------------------------------------- FC05
def test_no_date_limit_is_a_documented_full_window():
    window = coverage_window("Última gestión de cada ingreso abierto. Sin límite de fechas. Origen: SQL.", TODAY)
    assert window is not None and covers(window, *LAST_MONTH, TODAY), window
    assert coverage_window("La consulta no limita fechas.", TODAY) is not None
    # Una ventana corta sigue sin cubrir el mes pasado.
    assert not covers(coverage_window("Ingresos del día anterior.", TODAY), *LAST_MONTH, TODAY)


def test_day_block_page_over_an_unlimited_table_answers_last_month():
    qpb = builder()
    assert qpb._metric_misses_period(_by_id("valor_estimado"), *LAST_MONTH, pages=True) is None


def test_billed_last_month_is_an_amount_not_a_time():
    resolution = resolve("cuanto se facturo el mes pasado")
    metric = resolution.get("metric") or {}
    assert metric.get("metric_id") != "tiempo_factura", (resolution.get("status"), metric.get("label"))
    labels = [item["metric"].get("label") for item in resolution.get("candidates") or []]
    if resolution.get("status") == "resolved":
        assert "FACTURADO" in str(metric.get("dax_expression")), metric.get("label")
    else:
        assert "TIEMPO PROMEDIO GESTION FACTURA" not in labels, labels


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

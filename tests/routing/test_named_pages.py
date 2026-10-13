"""
Páginas nombradas (offline): «hospitalizaciones parciales de marzo», «partos
de 2025», «cirugías ... en el tablero de cirugías», «promedio mensual ... en el
tablero de triage».

Ejecutar:  python -m tests.routing.test_named_pages   (también lo corre
           python -m tests.routing.test_routing)

Fixture en un directorio temporal, con el SourceModelRouter REAL:

  Atenciones / TABLERO DE ATENCIONES : páginas SOLO documentadas (sin visuales):
      TRIAGE (medidas documentadas TOTAL_TRIAGES y PROMEDIO_TRIAGE_2025),
      PARTOS (Total_Partos_Dinamico y Promedio_Partos_Dinamico), ABORTOS (sin
      medidas), HOSPITALIZACIÓN PARCIAL (sin medidas; tabla HOSPITALIZACION_PARCIAL)
      y CIRUGÍAS (TOTAL_CIRUGIAS guardada en Calendario = COUNT(CIRUGIAS[CEDULA])).
      PROMEDIO_MENSUAL está en la página CONSULTAS PRIORITARIAS (tarjeta).
  Consolidado / CONSOLIDADO   : página «Cirugías» (tarjeta «Total cirugías» y gráfico
      «Cirugías realizadas»).
  Demanda / DEMANDA INSATISFECHA : página CIRUGIAS (tarjeta «Total de cirugías
      registradas») y TRIAGES («Total de triages no atendidos»).
  Informes / INFORMES EJECUTIVOS : «Cirugías realizadas» en «Indicadores trazadores».
  Eps / TABLERO EPS           : «Total de triages atendidos».
"""
import json
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.semantic.query_plan_builder import QueryPlanBuilder  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402

ATE, CON, DEM, INF, EPS = "Atenciones", "Consolidado", "Demanda", "Informes", "Eps"
REPORTS = {
    ATE: "TABLERO DE ATENCIONES", CON: "CONSOLIDADO", DEM: "DEMANDA INSATISFECHA",
    INF: "INFORMES EJECUTIVOS", EPS: "TABLERO EPS",
}
GROUPS = {model: f"g_{model.lower()}" for model in REPORTS}

DOMAINS = {
    (ATE, "CIRUGIAS", "ESPECIALIDAD"): ["ORTOPEDIA Y TRAUMATOLOGIA", "UROLOGIA"],
    (ATE, "CIRUGIAS", "ASEGURADOR"): ["SURA EPS", "NUEVA EPS"],
}


class FakeProvider:
    def execute_dax(self, dax, semantic_model=None):
        flat = dax.replace("\n", "").replace(" ", "")
        for (model, table, column), values in DOMAINS.items():
            if model == semantic_model and f"VALUES('{table}'[{column}])" in flat:
                return {"status": "success", "rows": [{"[Value]": value} for value in values]}
        return {"status": "success", "rows": [{"[__value]": 7}]}


def _metric(metric_id, model, label, table, visuals=()):
    """visuals: [(página, tipo, título)]."""
    report = REPORTS[model]
    return {
        "metric_id": metric_id, "label": label, "measure": label, "aliases": [label],
        "semantic_model": model, "report": report if visuals else None,
        "reports": [report] if visuals else [], "table": table,
        "dax_expression": f"[{label}]", "validation_status": "approved",
        "appearances": [
            {"report": report, "page_display_name": page, "visual_id": f"{metric_id}_{index}",
             "visual_type": visual_type, "visual_title": title}
            for index, (page, visual_type, title) in enumerate(visuals)
        ],
    }


METRICS = [
    _metric("a_total_triages", ATE, "TOTAL_TRIAGES", "OPORTUNIDAD_TRIAGE"),
    {**_metric("a_prom_triage_2025", ATE, "PROMEDIO_TRIAGE_2025", "OPORTUNIDAD_TRIAGE"),
     "description": "Promedio mensual de triages del año 2025."},
    _metric("a_prom_mensual", ATE, "PROMEDIO_MENSUAL", "CONSULTAS PRIORITARIAS",
            visuals=[("CONSULTAS PRIORITARIAS", "card", "Promedio mensual")]),
    _metric("a_prioritarias", ATE, "PRIORITARIAS_ACT", "CONSULTAS PRIORITARIAS",
            visuals=[("CONSULTAS PRIORITARIAS", "card", "Consultas prioritarias")]),
    _metric("a_total_partos", ATE, "Total_Partos_Dinamico", "PARTOS_DRIVE"),
    _metric("a_prom_partos", ATE, "Promedio_Partos_Dinamico", "PARTOS_DRIVE"),
    _metric("a_atencion_hp", ATE, "ATENCION_HP", "HOSPITALIZACION_PARCIAL"),
    _metric("a_atehp2024", ATE, "ATEHP2024", "HOSPITALIZACION_PARCIAL"),
    _metric("a_atehp2025", ATE, "ATEHP2025", "HOSPITALIZACION_PARCIAL"),
    _metric("a_total_cx", ATE, "TOTAL_CIRUGIAS", "Calendario"),
    _metric("c_total_cx", CON, "TOTAL_CIRUGIAS", "CIRUGIAS",
            visuals=[("Cirugías", "card", "Total cirugías")]),
    _metric("c_cx_realizadas", CON, "Cirugías realizadas", "CIRUGIAS",
            visuals=[("Cirugías", "clusteredColumnChart", "Cirugías realizadas")]),
    _metric("d_total_cx", DEM, "Total de cirugías registradas", "CIRUGIAS",
            visuals=[("CIRUGIAS", "card", "Total de cirugías registradas")]),
    _metric("d_no_atendidos", DEM, "Total de triages no atendidos", "TRIAGES",
            visuals=[("TRIAGES", "card", "Total de triages no atendidos")]),
    _metric("i_cx_realizadas", INF, "Cirugías realizadas", "FACT_INDICADORES",
            visuals=[("Indicadores trazadores", "card", "Cirugías realizadas")]),
    _metric("e_atendidos", EPS, "Total de triages atendidos", "ATENCIONES",
            visuals=[("CONSOLIDADO DE ATENCIONES DE URGENCIAS", "card", "Total de triages atendidos")]),
]

DOCUMENTS = {"semantic_model": ATE, "dashboards": [
    {"name": "TRIAGE", "documented_measures": [
        {"name": "TOTAL_TRIAGES"}, {"name": "PROMEDIO_TRIAGE_2025"}, {"name": "MEDIDA_QUE_NO_EXISTE"}]},
    {"name": "PARTOS", "documented_measures": [
        {"name": "Total_Partos_Dinamico"}, {"name": "Promedio_Partos_Dinamico"}]},
    {"name": "ABORTOS", "documented_measures": []},
    {"name": "HOSPITALIZACIÓN PARCIAL", "documented_measures": []},
    {"name": "CIRUGÍAS", "documented_measures": []},
    # Página documentada con el nombre del informe: no es una página.
    {"name": "TABLERO DE ATENCIONES", "documented_measures": [{"name": "ATENCION_HP"}]},
]}


def _build(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    docs = root / "data" / "semantic_documents" / "ate"
    for folder in (catalog, rag, docs):
        folder.mkdir(parents=True)
    sources = [
        {"source_group": GROUPS[model], "report": REPORTS[model], "semantic_model": model,
         "default_dashboard": REPORTS[model], "aliases": [REPORTS[model]],
         "technical_catalog": f"data/catalog/{GROUPS[model]}_rag.json"}
        for model in REPORTS
    ]
    registry = {"models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                            "technical_catalog": s["technical_catalog"]} for s in sources],
                "sources": sources}
    technical = {model: {"semantic_model": model, "tables": [], "relationships": []} for model in REPORTS}
    fecha = [{"name": "FECHA", "data_type": "DateTime"}]
    for model, table in ((CON, "CIRUGIAS"), (DEM, "CIRUGIAS"), (DEM, "TRIAGES"), (INF, "FACT_INDICADORES"),
                         (EPS, "ATENCIONES")):
        technical[model]["tables"].append({"name": table, "columns": list(fecha)})
    for table in ("OPORTUNIDAD_TRIAGE", "PARTOS_DRIVE", "HOSPITALIZACION_PARCIAL", "CONSULTAS PRIORITARIAS"):
        technical[ATE]["tables"].append({"name": table, "columns": list(fecha)})
    technical[ATE]["tables"] += [
        {"name": "Calendario", "columns": [{"name": "Date", "data_type": "DateTime"},
                                           {"name": "Año", "data_type": "Int64"}],
         "measures": [{"name": "TOTAL_CIRUGIAS", "expression": "COUNT(CIRUGIAS[CEDULA])"}]},
        {"name": "CIRUGIAS", "columns": [{"name": "CEDULA", "data_type": "String"},
                                         {"name": "ESPECIALIDAD", "data_type": "String"},
                                         {"name": "ASEGURADOR", "data_type": "String"},
                                         {"name": "FECHA", "data_type": "DateTime"}]},
        {"name": "LABORATORIOS", "columns": [{"name": "Aseguradora", "data_type": "String"}]},
    ]
    technical[ATE]["relationships"] = [
        {"FromTable": "CIRUGIAS", "ToTable": "Calendario", "IsActive": True},
        {"FromTable": "LABORATORIOS", "ToTable": "Calendario", "IsActive": True},
    ]
    visuals = {"schema_version": 2, "reports": []}
    for model in REPORTS:
        pages = {}
        for metric in METRICS:
            if metric["semantic_model"] != model:
                continue
            for appearance in metric["appearances"]:
                page = pages.setdefault(appearance["page_display_name"], [])
                page.append({
                    "visual_id": appearance["visual_id"], "visual_type": appearance["visual_type"],
                    "fields": [{"role": "Values", "kind": "measure", "table": metric["table"],
                                "measure": metric["measure"], "query_ref": f"{metric['table']}.{metric['measure']}"}],
                })
                # Segmentador de fecha de la página (periodos de la pregunta).
                page.append({
                    "visual_id": f"{appearance['visual_id']}_fecha", "visual_type": "slicer",
                    "fields": [{"role": "Values", "kind": "column", "table": metric["table"], "column": "FECHA",
                                "display_name": "FECHA", "native_query_ref": "FECHA",
                                "query_ref": f"{metric['table']}.FECHA"}],
                })
        visuals["reports"].append({
            "report": REPORTS[model], "semantic_model": model, "source_group": GROUPS[model],
            "pages": [{"page_name": f"p{index}", "page_display_name": page, "filters": {}, "visuals": items}
                      for index, (page, items) in enumerate(pages.items())],
        })
    files = {
        catalog / "source_registry.json": registry,
        rag / "visual_metrics_catalog.json": visuals,
        rag / "master_metrics.json": {"metrics": METRICS},
        docs / "documentacion.json": DOCUMENTS,
    }
    for model in REPORTS:
        files[catalog / f"{GROUPS[model]}_rag.json"] = technical[model]
    for path, data in files.items():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    router = SourceModelRouter(catalog / "source_registry.json", rag / "visual_metrics_catalog.json",
                               project_root=root)
    router.register_documentation_dashboards([
        (dashboard["name"], GROUPS[ATE]) for dashboard in DOCUMENTS["dashboards"]
    ])
    builder = QueryPlanBuilder(rag / "master_metrics.json", rag / "visual_metrics_catalog.json",
                               router, FakeProvider(), project_root=root)
    return router, builder


_STATE = {}


def system():
    if "system" not in _STATE:
        tmp = tempfile.TemporaryDirectory()
        _STATE["tmp"] = tmp
        _STATE["system"] = _build(Path(tmp.name))
    return _STATE["system"]


def _ids(plan):
    resolution = plan.get("metric_resolution") or {}
    return [item["metric"]["metric_id"] for item in resolution.get("candidates") or resolution.get("suggestions") or []]


def _categorical(plan):
    return {(f["table"], f["column"], f["value"]) for f in plan.get("filters") or [] if f.get("type") == "categorical"}


# ---------------------------------------------------------------- índice de páginas
def test_page_members_come_from_visuals_documentation_and_topic():
    _, builder = system()
    members = builder._page_members({"semantic_model": CON, "page": "Cirugías"})
    assert [m["metric"]["metric_id"] for m in members] == ["c_total_cx", "c_cx_realizadas"], members
    assert members[0]["visual_type"] == "card"  # tarjetas primero
    triage = {m["metric"]["metric_id"]: m["source"] for m in builder._page_members({"semantic_model": ATE, "page": "TRIAGE"})}
    assert triage["a_total_triages"] == "documentation" and triage["a_prom_triage_2025"] == "documentation", triage
    hp = [m["metric"]["metric_id"] for m in builder._page_members({"semantic_model": ATE, "page": "HOSPITALIZACIÓN PARCIAL"})]
    assert set(hp) == {"a_atencion_hp", "a_atehp2024", "a_atehp2025"}, hp  # por tema (tabla)
    assert builder._page_members({"semantic_model": ATE, "page": "ABORTOS"}) == []


def test_topic_mentions_tolerate_plurals_and_skip_generic_names():
    router, builder = system()
    names = [p["page"] for p in builder._topic_pages("hospitalizaciones parciales de marzo")]
    assert names == ["HOSPITALIZACIÓN PARCIAL"], names
    assert [p["page"] for p in builder._topic_pages("partos de 2025")] == ["PARTOS"]
    # Una página con el nombre del informe no es una página.
    assert not builder._topic_pages("tablero de atenciones en 2025")
    mentions = router.page_topic_mentions("total de abortos", ignored_words={"total"})
    assert [m["phrase"] for m in mentions] == ["abortos"], mentions


# ---------------------------------------------------------------- 1. página por su tema
def test_page_named_by_topic_answers_its_principal_indicator():
    _, builder = system()
    assert builder.looks_numeric("partos de 2025")
    plan = builder.build("partos de 2025")
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"), _ids(plan))
    assert plan["metric"]["metric_id"] == "a_total_partos", plan["metric"]["metric_id"]
    assert any("indicador principal de la página PARTOS" in note for note in plan.get("notes") or []), plan.get("notes")
    assert any(f.get("type") == "date_range" or f.get("temporal") for f in plan["filters"]), plan["filters"]


def test_requested_aggregation_chooses_among_page_indicators():
    _, builder = system()
    plan = builder.build("promedio de partos en 2025")
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"), _ids(plan))
    assert plan["metric"]["metric_id"] == "a_prom_partos", plan["metric"]["metric_id"]
    assert not plan.get("unapplied_terms"), plan.get("unapplied_terms")


def test_page_named_by_topic_offers_its_indicators():
    _, builder = system()
    assert builder.looks_numeric("hospitalizaciones parciales de marzo de 2025")
    plan = builder.build("hospitalizaciones parciales de marzo de 2025")
    assert plan["status"] == "ambiguous" and plan["reason"] == "options_from_named_page", plan.get("reason")
    # ATEHP2024/ATEHP2025 cuentan como una opción: la del año pedido.
    assert set(_ids(plan)) == {"a_atencion_hp", "a_atehp2025"}, _ids(plan)
    assert plan["named_page"] == "HOSPITALIZACIÓN PARCIAL"


def test_page_without_indicators_is_declared_for_the_documentary_answer():
    _, builder = system()
    assert builder.named_page_without_metrics("abortos por aseguradora en 2025") == ["ABORTOS (TABLERO DE ATENCIONES)"]
    # Pregunta descriptiva o sin pedir un dato: no aplica.
    assert builder.named_page_without_metrics("que muestra la pagina de abortos") == []
    assert builder.named_page_without_metrics("abortos") == []
    # Página con indicadores: no aplica.
    assert builder.named_page_without_metrics("partos de 2025") == []


def test_topic_does_not_override_options_from_other_pages():
    _, builder = system()
    # «cirugías» nombra páginas, pero hay opciones con ese tema en otras
    # páginas (Indicadores trazadores): se mantiene la contrapregunta normal.
    plan = builder.build("cuantas cirugias hubo en 2024")
    assert plan.get("reason") != "options_from_named_page", (plan.get("reason"), _ids(plan))


# ---------------------------------------------------------------- 2. «tablero de X» = página
def test_named_page_in_several_models_offers_only_their_indicators():
    _, builder = system()
    plan = builder.build("cirugias de ortopedia de sura en 2025 en el tablero de cirugias")
    assert plan["status"] == "ambiguous" and plan["reason"] == "options_from_named_page", (
        plan["status"], plan.get("reason"), _ids(plan))
    assert set(_ids(plan)) == {"c_total_cx", "d_total_cx", "a_total_cx"}, _ids(plan)  # sin INFORMES
    assert plan["named_page_models"] == 3


def test_selected_page_indicator_applies_the_filters_of_the_question():
    _, builder = system()
    plan = builder.build("cirugias de ortopedia de sura en 2025 en el tablero de cirugias",
                         selected_metric_id="a_total_cx")
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"))
    # TOTAL_CIRUGIAS está guardada en Calendario pero se calcula sobre CIRUGIAS.
    assert ("CIRUGIAS", "ESPECIALIDAD", "ORTOPEDIA Y TRAUMATOLOGIA") in _categorical(plan), _categorical(plan)
    assert ("CIRUGIAS", "ASEGURADOR", "SURA EPS") in _categorical(plan), _categorical(plan)
    assert not plan.get("unapplied_terms"), plan.get("unapplied_terms")


def test_selected_indicator_declares_what_it_could_not_apply():
    _, builder = system()
    plan = builder.build("cirugias de ortopedia de sura en 2025 en el tablero de cirugias",
                         selected_metric_id="d_total_cx")
    assert plan["status"] == "ready", plan["status"]
    assert plan.get("unapplied_terms"), "ortopedia/sura no pueden desaparecer en silencio"


# ---------------------------------------------------------------- 3. página nombrada fija el indicador
def test_named_page_beats_indicator_of_another_page():
    _, builder = system()
    plan = builder.build("promedio mensual de triages en 2025 en el tablero de triage")
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"), _ids(plan))
    assert plan["metric"]["metric_id"] == "a_prom_triage_2025", plan["metric"]["metric_id"]
    assert any("no aparecen en ella" in note for note in plan.get("resolution_notes") or []), \
        plan.get("resolution_notes")


def test_named_page_without_the_indicator_says_so():
    _, builder = system()
    plan = builder.build("consultas prioritarias en el tablero de triage")
    assert plan["status"] == "not_found" and plan["reason"] == "metric_not_in_named_page", (
        plan["status"], plan.get("reason"), _ids(plan))
    assert plan["named_page"] == "TRIAGE"
    assert _ids(plan) == ["a_prioritarias"], _ids(plan)  # el de otra página, solo como opción


def test_composite_part_uses_the_named_page():
    _, builder = system()
    composite = builder.build_composite("total de triages y promedio mensual de triages en 2025 en el tablero de triage")
    assert composite and composite.get("status") == "composite", composite and composite.get("status")
    ids = [item["plan"]["metric"]["metric_id"] for item in composite["items"]]
    assert ids == ["a_total_triages", "a_prom_triage_2025"], ids


# ---------------------------------------------------------------- polaridad en nombres casi iguales
def test_negated_name_is_not_ambiguous_with_its_opposite():
    _, builder = system()
    plan = builder.build("cuantos triages no atendidos hubo en 2025")
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"), _ids(plan))
    assert plan["metric"]["metric_id"] == "d_no_atendidos"
    positive = builder.build("cuantos triages atendidos hubo en 2025")
    assert positive["status"] == "ready" and positive["metric"]["metric_id"] == "e_atendidos", (
        positive["status"], _ids(positive))


# tests.routing.test_routing importa solo las pruebas (no el fixture).
__all__ = [name for name in list(globals()) if name.startswith("test_")]


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

"""
Ronda 2 de contrapreguntas innecesarias y filtros espurios (banco real, commit ab0c94d).

Reglas generales que se prueban:
1) Solo se contrapregunta entre fuentes que pueden dar una cifra para la pregunta TAL COMO
   ESTÁ: un homónimo sin fecha no responde «el mes pasado» (sale); sin periodo, una medida
   que ningún visual muestra no compite con la del tablero (BH02, BH03). Dos fuentes que
   sí responden se siguen preguntando (contrapregunta legítima).
2) Páginas homónimas de varios tableros: se queda la opción que explica más palabras de
   la pregunta («interconsultas PENDIENTES» -> SIN RESPUESTA; «%ATENDIDO» explica
   «atendidas») (BH07, TU05).
3) Un valor de filtro exige que la pregunta nombre el valor:
   - lo que empieza por un verbo conjugado no es valor («de cama ESTÁN pendientes») (BH11);
   - la palabra distintiva del tablero es el tablero («en el briefing») (BH16);
   - «por aseguradora, las 5 más altas» es un ranking, no un valor (FC02).
4) Lo que se cuenta y ningún indicador nombra es la unidad del conteo («cuántas CUENTAS
   hay en proceso de facturación»), no el sustantivo que falta (FC04).

Ejecutar:  python -m tests.resolution.test_r2_contrapreguntas
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

from src.semantic.query_plan_builder import QueryPlanBuilder, normalize_text  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.resolution.test_resolution import _column, _metric, _source  # noqa: E402

DIARIO, HIST = "Modelo Diario", "Modelo Historico"
R_DIARIO, R_HIST = "Tablero Diario", "Tablero Historico"
DOMAINS = {
    ("ASEGURADORAS", "ASEGURADORA"): ["NUEVA EPS", "SURA", "SALUD TOTAL EPS"],
    ("SOLICITUDES", "CAMA"): ["CAMA 1", "CAMA 2"],
    ("ATENCIONES", "SERVICIO"): ["URGENCIAS", "HOSPITALIZACION"],
    ("EN_PROCESO", "PERFIL"): ["CUENTAS", "FACTURACION"],
}


def _slicer(visual_id, table, column):
    return {"visual_id": visual_id, "visual_type": "slicer", "fields": [_column(table, column)]}


def _card(metric_id, label, page):
    return {"report": None, "page_display_name": page, "visual_id": f"{metric_id}_card",
            "visual_title": label, "visual_type": "card"}


def _build_fixture(root):
    catalog = root / "data" / "catalog"
    rag = root / "data" / "rag"
    for folder in (catalog, rag):
        folder.mkdir(parents=True)
    sources = [
        _source("diario", R_DIARIO, DIARIO, ["tablero diario", "diario"]),
        _source("hist", R_HIST, HIST, ["tablero historico", "historico"]),
    ]
    registry = {
        "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                    "technical_catalog": s["technical_catalog"]} for s in sources],
        "sources": sources,
    }
    technical = {
        "diario": {"semantic_model": DIARIO, "tables": [
            {"name": "CAMAS", "columns": [{"name": "ESTADO", "data_type": "String"}]},
            {"name": "TRIAGES_DIA", "columns": [{"name": "CLASIFICACION", "data_type": "String"}]},
            {"name": "SOLICITUDES", "columns": [{"name": "CAMA", "data_type": "String"}]},
            {"name": "ATENCIONES", "columns": [{"name": "SERVICIO", "data_type": "String"}]},
            {"name": "INTERCONSULTAS", "columns": [{"name": "ESPECIALIDAD", "data_type": "String"}]},
        ]},
        "hist": {"semantic_model": HIST, "tables": [
            {"name": "OCUPACION", "columns": [{"name": "FECHA", "data_type": "DateTime"}]},
            {"name": "TRIAGES", "columns": [{"name": "FECHA", "data_type": "DateTime"}]},
            {"name": "ASEGURADORAS", "columns": [{"name": "ASEGURADORA", "data_type": "String"}]},
            {"name": "EN_PROCESO", "columns": [{"name": "PERFIL", "data_type": "String"}]},
            {"name": "INTERCONSULTA", "columns": [{"name": "ESPECIALIDAD", "data_type": "String"}]},
        ]},
    }
    visuals = {"schema_version": 2, "reports": [
        {"report": R_DIARIO, "semantic_model": DIARIO, "source_group": "diario", "pages": [
            {"page_name": "d1", "page_display_name": "Camas", "filters": {}, "visuals": []},
            {"page_name": "d2", "page_display_name": "Solicitudes", "filters": {}, "visuals": [
                _slicer("d_cama", "SOLICITUDES", "CAMA")]},
            {"page_name": "d3", "page_display_name": "Atenciones", "filters": {}, "visuals": [
                _slicer("d_serv", "ATENCIONES", "SERVICIO")]},
        ]},
        {"report": R_HIST, "semantic_model": HIST, "source_group": "hist", "pages": [
            {"page_name": "h1", "page_display_name": "Ocupacion", "filters": {}, "visuals": [
                _slicer("h_fecha", "OCUPACION", "FECHA"), _slicer("h_tfecha", "TRIAGES", "FECHA")]},
            {"page_name": "h2", "page_display_name": "Facturacion", "filters": {}, "visuals": [
                _slicer("h_perfil", "EN_PROCESO", "PERFIL"),
                _slicer("h_aseg", "ASEGURADORAS", "ASEGURADORA")]},
        ]},
    ]}
    metrics = [
        _metric("d_camas", DIARIO, R_DIARIO, "CAMAS DISPONIBLES", "CAMAS", pages=["Camas"]),
        _metric("h_camas", HIST, R_HIST, "CAMAS DISPONIBLES", "OCUPACION", visible=False),
        _metric("d_triages", DIARIO, R_DIARIO, "TRIAGES", "TRIAGES_DIA", pages=["Camas"]),
        _metric("h_triages", HIST, R_HIST, "TRIAGES", "TRIAGES", pages=["Ocupacion"]),
        _metric("h_ocupadas", HIST, R_HIST, "CAMAS OCUPADAS", "OCUPACION", pages=["Ocupacion"]),
        _metric("d_ocupadas", DIARIO, R_DIARIO, "CAMAS OCUPADAS", "CAMAS", pages=["Camas"]),
        _metric("d_solicitudes", DIARIO, R_DIARIO, "SOLICITUDES", "SOLICITUDES", pages=["Solicitudes"]),
        _metric("d_atenciones", DIARIO, R_DIARIO, "ATENCIONES", "ATENCIONES", pages=["Atenciones"]),
        _metric("h_proceso", HIST, R_HIST, "EN PROCESO DE FACTURACION", "EN_PROCESO", pages=["Facturacion"]),
        _metric("h_valor", HIST, R_HIST, "VALOR ESTIMADO", "ASEGURADORAS", pages=["Facturacion"]),
        _metric("d_sinresp", DIARIO, R_DIARIO, "INTERCONSULTAS SIN RESPUESTA", "INTERCONSULTAS"),
        _metric("h_atendido", HIST, R_HIST, "%ATENDIDO", "INTERCONSULTA"),
        _metric("h_respondidas", HIST, R_HIST, "INTERCONSULTAS RESPONDIDAS", "INTERCONSULTA"),
    ]
    files = {
        catalog / "source_registry.json": registry,
        rag / "visual_metrics_catalog.json": visuals,
        rag / "master_metrics.json": {"metrics": metrics},
        catalog / "diario_rag.json": technical["diario"],
        catalog / "hist_rag.json": technical["hist"],
    }
    for path, data in files.items():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class FakeProvider:
    def execute_dax(self, dax, semantic_model=None):
        compact = dax.replace("\n", "").replace(" ", "")
        for (table, column), values in DOMAINS.items():
            if f"VALUES('{table}'[{column}])".replace(" ", "") in compact:
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


def metric(metric_id):
    return next(m for m in builder().metrics if m.get("metric_id") == metric_id)


def item(metric_id):
    m = metric(metric_id)
    return {"metric": m, "score": 1.0, "business_score": 1.0, "matched_name": m.get("label")}


def chosen_ids(plan):
    if plan.get("status") == "ready":
        return [(plan.get("metric") or {}).get("metric_id")]
    return [c["metric"].get("metric_id") for c in (plan.get("metric_resolution") or {}).get("candidates") or []]


def filters_of(plan):
    return {
        f["column"]: f.get("value") or tuple(f.get("values") or ())
        for f in plan.get("filters", [])
        if f.get("type") == "categorical" and f.get("source") != "query_plan_temporal"
    }


# ------------------------------------------------- 1) homónimos: solo los que responden
def test_hidden_homonym_does_not_compete_without_period():
    qpb = builder()
    result = {"matched_name": "CAMAS DISPONIBLES"}
    kept = qpb._homonyms_that_answer(
        "cuantas camas disponibles hay ahorita", result, [item("d_camas"), item("h_camas")],
    )
    assert [i["metric"]["metric_id"] for i in kept] == ["d_camas"], kept


def test_plain_hay_or_past_tense_is_not_current_state():
    qpb = builder()
    for question in ("cuantas camas disponibles hay", "cuantas camas disponibles hubo"):
        kept = qpb._homonyms_that_answer(
            question, {"matched_name": "CAMAS DISPONIBLES"}, [item("d_camas"), item("h_camas")],
        )
        assert kept is None, (question, kept)  # sin «ahorita/tenemos/están»: se sigue preguntando
    kept = qpb._homonyms_that_answer(
        "cuantas camas disponibles tenemos", {"matched_name": "CAMAS DISPONIBLES"},
        [item("d_camas"), item("h_camas")],
    )
    assert [i["metric"]["metric_id"] for i in kept] == ["d_camas"], kept


def test_two_visible_homonyms_without_period_are_kept():
    qpb = builder()
    kept = qpb._homonyms_that_answer(
        "cuantas camas ocupadas hay", {"matched_name": "CAMAS OCUPADAS"},
        [item("d_ocupadas"), item("h_ocupadas")],
    )
    assert kept is None, kept  # contrapregunta legítima: las dos están en un tablero


def test_question_end_to_end_answers_with_the_visible_board():
    plan = builder().build("cuantas camas disponibles hay ahorita")
    assert plan["status"] == "ready", (plan.get("status"), plan.get("reason"), chosen_ids(plan))
    assert plan["metric"]["metric_id"] == "d_camas", plan["metric"].get("metric_id")


def test_homonym_without_date_does_not_answer_last_month():
    qpb = builder()
    kept = qpb._homonyms_that_answer(
        "cuantos triages hubo el mes pasado", {"matched_name": "TRIAGES"},
        [item("d_triages"), item("h_triages")],
    )
    assert kept is not None and [i["metric"]["metric_id"] for i in kept] == ["h_triages"], kept


# ------------------------------------------------- 2) opciones de páginas homónimas
def test_pending_metric_explains_pendientes():
    qpb = builder()
    words = ["interconsulta", "pendiente"]
    assert len(qpb._option_coverage(metric("d_sinresp"), words)) == 2
    assert len(qpb._option_coverage(metric("h_respondidas"), words)) == 1


def test_percent_sign_is_not_part_of_the_word():
    qpb = builder()
    covered = qpb._option_coverage(metric("h_atendido"), ["atendida"])
    assert covered == {"atendida"}, covered


# ------------------------------------------------- 3) el valor debe nombrarse
def test_conjugated_verb_never_starts_a_value():
    qpb = builder()
    m = metric("d_solicitudes")
    candidates = qpb._metric_dimensions(m)
    specs = qpb._detect_explicit_dimension_filters(
        "cuantas solicitudes de cama estan pendientes", candidates, metric=m, source_context={},
    )
    assert not specs, specs
    # Un valor nombrado sigue siendo filtro.
    specs = qpb._detect_explicit_dimension_filters(
        "cuantas solicitudes de cama 2", candidates, metric=m, source_context={},
    )
    assert specs and specs[0]["value_hint"] == "2", specs


def test_board_short_name_is_the_board_not_a_value():
    qpb = builder()
    m = metric("d_atenciones")
    qpb_names = qpb._board_name_phrases({}, m)
    assert "tablero diario" in qpb_names or "diario" in qpb_names
    assert qpb._names_board("el diario", {}, m, loose=True)
    assert not qpb._names_board("urgencias", {}, m, loose=True)
    plan = qpb.build("atenciones por servicio en el diario")
    assert plan["status"] == "ready", (plan.get("status"), plan.get("reason"))
    assert "SERVICIO" not in filters_of(plan), filters_of(plan)
    assert [g["column"] for g in plan.get("group_by", [])] == ["SERVICIO"], plan.get("group_by")


def test_postfix_top_is_a_ranking_not_a_value():
    qpb = builder()
    plan = qpb.build("valor estimado por aseguradora, las 2 mas altas")
    assert plan["status"] == "ready", (plan.get("status"), plan.get("reason"), plan.get("requested_value"))
    assert "ASEGURADORA" not in filters_of(plan), filters_of(plan)
    assert [g["column"] for g in plan.get("group_by", [])] == ["ASEGURADORA"], plan.get("group_by")
    match, direction = qpb._postfix_top("por servicio los 3 menores")
    assert match is not None and direction == "asc"
    assert qpb._postfix_top("con mas de 3 dias")[0] is None


# ------------------------------------------------- 4) lo contado es la unidad
def test_counted_noun_unknown_to_catalog_is_the_unit():
    qpb = builder()
    plan = qpb.build("cuantas cuentas hay en proceso de facturacion")
    assert plan["status"] == "ready", (plan.get("status"), plan.get("reason"), plan.get("unresolved_text"))
    assert plan["metric"]["metric_id"] == "h_proceso"
    assert "PERFIL" not in filters_of(plan), filters_of(plan)


def test_counted_noun_that_is_a_concept_still_matters():
    qpb = builder()
    # «triages» es un indicador del catálogo: no es la unidad de EN PROCESO DE FACTURACION.
    unit = qpb._counted_unit("cuantos triages hay en proceso de facturacion", metric("h_proceso"), {})
    assert unit is None, unit


# ---------------------------------------------------------------- Runner mínimo
def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
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

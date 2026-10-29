"""
Elección del indicador con los modelos TMDL reales (2026-10-29): más tablas,
columnas y medidas de nombre casi igual. Catálogo mínimo offline que reproduce
cada situación del banco tests/eval con la data real:

  ATEN   TRIAGES_PEDIATRICOS_2025, PROMEDIO_TRIAGES_PEDIATRICOS_2025 y
         PROM_TRIAGE_PEDIATRICOS (medidas sin visual, tabla OPORTUNIDAD_TRIAGE);
         PACIENTES OBSERVADOS POR MES (CONSULTAS PRIORITARIAS, con ASEGURADOR).
  BRIEF  PACIENTES OBSERVADOS (OBSERV_HIST, sin aseguradora).
  NAOS   PACIENTES = DISTINCTCOUNT(AINCONSEC) en una tarjeta y
         DISTINCTCOUNT(ADNINGRESO) en una dona por HSUNOMBRE (servicio), las
         dos de la tabla PACIENTES en la página LISTADO.

1. Desempate por la frase que nombra la pregunta.
2. «M por X»: variantes del mismo conteo -> la que el tablero muestra por X.
3. Rivales de nombre parecido que no se desglosan por X no se ofrecen.
4. «areas de servicio» nombra AREA_SERVICIO (conector entre palabras).
5. Intención analítica: opciones que solo comparten una palabra suelta.

Ejecutar:  python -m tests.resolution.test_tmdl_real
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

from src.semantic.query_plan_builder import QueryPlanBuilder, _alias_prefix  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.resolution.test_resolution import _column, _source  # noqa: E402

ATEN, BRIEF, NAOS, REF, LAV, EPS = "ATENCIONES", "BRIEFING", "NAOS", "REFERENCIA", "LAVANDERIA", "TABLERO EPS"


def _metric(metric_id, model, label, table, expression=None, appearances=(), source_type="explicit_measure"):
    explicit = source_type == "explicit_measure"
    return {
        "metric_id": metric_id, "label": label, "measure": label if explicit else None,
        "aliases": [label, f"{table}.{label}"], "source_type": source_type,
        "semantic_model": model, "report": model if appearances else None,
        "reports": [model] if appearances else [], "table": table,
        "dax_expression": f"[{label}]" if explicit else expression,
        "model_expression": expression if explicit else None,
        "validation_status": "approved",
        "appearances": [
            {"report": model, "page_display_name": page, "visual_id": visual_id,
             "visual_title": None, "visual_type": visual_type}
            for page, visual_id, visual_type in appearances
        ],
    }


METRICS = [
    _metric("t_ped", ATEN, "TRIAGES_PEDIATRICOS_2025", "OPORTUNIDAD_TRIAGE", "COUNT('OPORTUNIDAD_TRIAGE'[ID])"),
    _metric("t_prom", ATEN, "PROMEDIO_TRIAGES_PEDIATRICOS_2025", "OPORTUNIDAD_TRIAGE",
            "[TRIAGES_PEDIATRICOS_2025] / 12"),
    _metric("t_prom2", ATEN, "PROM_TRIAGE_PEDIATRICOS", "OPORTUNIDAD_TRIAGE", "AVERAGE('OPORTUNIDAD_TRIAGE'[N])"),
    _metric("o_mes", ATEN, "PACIENTES OBSERVADOS POR MES", "CONSULTAS PRIORITARIAS",
            "COUNT('CONSULTAS PRIORITARIAS'[ASEGURADOR])",
            appearances=[("CONSULTAS PRIORITARIAS", "o_card", "card")]),
    _metric("o_brief", BRIEF, "PACIENTES OBSERVADOS", "OBSERV_HIST", "COUNT('OBSERV_HIST'[ID])",
            appearances=[("URGENCIAS", "ob_card", "card")]),
    _metric("n_card", NAOS, "PACIENTES", "PACIENTES", "DISTINCTCOUNT('PACIENTES'[AINCONSEC])",
            appearances=[("LISTADO", "n_card", "card")], source_type="visual_aggregation"),
    _metric("n_pie", NAOS, "PACIENTES", "PACIENTES", "DISTINCTCOUNT('PACIENTES'[ADNINGRESO])",
            appearances=[("LISTADO", "n_pie", "pieChart")], source_type="visual_aggregation"),
    _metric("r_sol", REF, "Cantidad de SOLICITUDES", "DETALLE_RECEPCIONES",
            "DISTINCTCOUNT('DETALLE_RECEPCIONES'[Oid])",
            appearances=[("DETALLE_RECEPCIONES", "r_card", "card")], source_type="visual_aggregation"),
    _metric("l_peso", LAV, "PESO TOTAL por Mes", "LAVANDERIA", "DISTINCTCOUNT('LAVANDERIA'[OID])",
            appearances=[("Página 1", "l_card", "card")], source_type="visual_aggregation"),
    _metric("e_pct", EPS, "%ATENCIONES", "OPORTUNIDAD_TRIAGE",
            "DISTINCTCOUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE])/DISTINCTCOUNT(ADMISIONES_TRIAGE[Oid])",
            appearances=[("INICIO", "e_card", "card")]),
    _metric("e_tot", EPS, "TOTAL ATENCIONES", "OPORTUNIDAD_TRIAGE", "DISTINCTCOUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE])",
            appearances=[("INICIO", "e_card2", "card")]),
    _metric("h_pac", BRIEF, "PACIENTES HOSPITALIZADOS", "PACIENTES HOSPITALIZADOS",
            "DISTINCTCOUNT('PACIENTES HOSPITALIZADOS'[PACNUMDOC])",
            appearances=[("URGENCIAS", "h_card", "card")], source_type="visual_aggregation"),
    _metric("h_tiempo", ATEN, "PACIENTES HOSPITALIZADOS", "HOSPITALIZACION_DIA",
            "SUM('HOSPITALIZACION_DIA'[TIEMPO_PARA_HOSPITALIZACION])",
            appearances=[("HOSPITALIZACION DIA", "h_bar", "card")], source_type="visual_aggregation"),
]

TABLES = {
    ATEN: [("OPORTUNIDAD_TRIAGE", ["ID", "N", "ESPECIALIDAD"]),
           ("CONSULTAS PRIORITARIAS", ["ASEGURADOR", "SERVICIO", "GEEDESCRI"]), ("Calendario", ["Date"]),
           ("HOSPITALIZACION_DIA", ["TIEMPO_PARA_HOSPITALIZACION"])],
    BRIEF: [("OBSERV_HIST", ["ID", "CAMA"]), ("PACIENTES HOSPITALIZADOS", ["PACNUMDOC", "ASEGURADORA"])],
    NAOS: [("PACIENTES", ["AINCONSEC", "ADNINGRESO", "HSUNOMBRE", "GDENOMBRE"])],
    REF: [("DETALLE_RECEPCIONES", ["Oid", "RecepcionSegOid", "ESTADO_RECEPCION"]),
          ("REFERENCIA", ["OID", "GEEDESCRI", "ESTADO"])],
    LAV: [("LAVANDERIA", ["OID", "SERVICIO", "TURNO_OK"])],
    EPS: [("OPORTUNIDAD_TRIAGE", ["OID_TRIAGE", "ASEGURADORA"])],
}
# REFERENCIA filtra DETALLE_RECEPCIONES (relación muchos a muchos del modelo real).
RELATIONSHIPS = {REF: [{"FromTable": "DETALLE_RECEPCIONES", "FromColumn": "RecepcionSegOid",
                        "ToTable": "REFERENCIA", "ToColumn": "OID", "IsActive": True}]}


def _role(field, role):
    return {**field, "role": role}


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    keys = {ATEN: "aten", BRIEF: "brief", NAOS: "naos", REF: "ref", LAV: "lav", EPS: "eps"}
    sources = [_source(key, model, model, [f"tablero {model.lower()}", model.lower()]) for model, key in keys.items()]
    registry = {
        "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                    "technical_catalog": s["technical_catalog"]} for s in sources],
        "sources": sources,
    }
    technical = {
        key: {"semantic_model": model, "relationships": RELATIONSHIPS.get(model, []), "tables": [
            {"name": name, "columns": [{"name": column, "data_type": "DateTime" if column == "Date" else "String"}
                         for column in columns],
             "measures": [{"name": m["label"], "expression": m["model_expression"]}
                          for m in METRICS if m["semantic_model"] == model and m["table"] == name
                          and m["model_expression"]]}
            for name, columns in TABLES[model]
        ]}
        for model, key in keys.items()
    }
    visuals = {"schema_version": 2, "reports": [
        {"report": NAOS, "semantic_model": NAOS, "source_group": "naos", "pages": [
            {"page_name": "p1", "page_display_name": "LISTADO", "filters": {}, "visuals": [
                {"visual_id": "n_card", "visual_type": "card", "fields": []},
                {"visual_id": "n_pie", "visual_type": "pieChart",
                 "fields": [_role(_column("PACIENTES", "HSUNOMBRE"), "Category")]},
                {"visual_id": "n_tabla", "visual_type": "tableEx", "fields": [
                    {**_column("PACIENTES", "HSUNOMBRE"), "display_name": "SERVICIO"},
                    {**_column("PACIENTES", "GDENOMBRE"), "display_name": "EPS"}]},
            ]}]},
        {"report": ATEN, "semantic_model": ATEN, "source_group": "aten", "pages": [
            {"page_name": "p2", "page_display_name": "CONSULTAS PRIORITARIAS", "filters": {}, "visuals": [
                {"visual_id": "o_card", "visual_type": "card", "fields": []},
                {"visual_id": "o_aseg", "visual_type": "slicer", "fields": [
                    {**_column("CONSULTAS PRIORITARIAS", "ASEGURADOR"), "display_name": "ASEGURADORA"}]},
                {"visual_id": "o_esp", "visual_type": "slicer", "fields": [
                    {**_column("CONSULTAS PRIORITARIAS", "GEEDESCRI"), "display_name": "ESPECIALIDAD"}]},
            ]}]},
        {"report": REF, "semantic_model": REF, "source_group": "ref", "pages": [
            {"page_name": "p4", "page_display_name": "DETALLE_RECEPCIONES", "filters": {}, "visuals": [
                {"visual_id": "r_card", "visual_type": "card", "fields": []},
                {"visual_id": "r_estado", "visual_type": "slicer", "fields": [_column("REFERENCIA", "ESTADO")]},
            ]}]},
        {"report": LAV, "semantic_model": LAV, "source_group": "lav", "pages": [
            {"page_name": "p5", "page_display_name": "Página 1", "filters": {}, "visuals": [
                {"visual_id": "l_card", "visual_type": "card", "fields": []},
            ]}]},
        {"report": EPS, "semantic_model": EPS, "source_group": "eps", "pages": [
            {"page_name": "p6", "page_display_name": "INICIO", "filters": {}, "visuals": [
                {"visual_id": "e_card", "visual_type": "card", "fields": []},
                {"visual_id": "e_card2", "visual_type": "card", "fields": []},
            ]}]},
        {"report": BRIEF, "semantic_model": BRIEF, "source_group": "brief", "pages": [
            {"page_name": "p3", "page_display_name": "URGENCIAS", "filters": {}, "visuals": [
                {"visual_id": "ob_card", "visual_type": "card", "fields": []},
            ]}]},
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


def _item(metric_id, score=1.3, business=1.0):
    metric = next(m for m in builder().metrics if m["metric_id"] == metric_id)
    return {"metric": metric, "score": score, "business_score": business, "matched_name": metric["label"]}


# ---------------------------------------------------------------- 1. frase que nombra la pregunta
def test_question_names_one_option_entirely():
    qpb = builder()
    question = "cuantos triages pediatricos hubo en 2025"
    context = qpb._source_context(question)
    options = [_item("t_ped"), _item("t_prom"), _item("t_prom2")]
    named = qpb._options_named_by_question(question, context, options)
    assert [item["metric"]["metric_id"] for item in named] == ["t_ped"], named
    # «promedio» dicho en la pregunta: el plano ya no se nombra entero y gana el promedio.
    question = "promedio de triages pediatricos 2025"
    named = qpb._options_named_by_question(question, qpb._source_context(question), options)
    assert [item["metric"]["metric_id"] for item in named] == ["t_prom"], named


def test_same_name_in_two_boards_is_still_ambiguous():
    qpb = builder()
    question = "cuantos pacientes observados hay"
    options = [_item("o_mes"), _item("o_brief")]
    # PACIENTES OBSERVADOS POR MES y PACIENTES OBSERVADOS: el nombre del
    # segundo está entero en la pregunta, pero «por mes» no es una palabra del
    # indicador (_name_key la ignora): los dos tienen la misma clave y la
    # pregunta no decide.
    assert qpb._options_named_by_question(question, qpb._source_context(question), options) == []
    # Un nombre de una sola palabra no decide («cuántos pacientes hay»: PACIENTES de NAOS
    # frente a PACIENTES OBSERVADOS, que añade «observados»).
    question = "cuantos pacientes hay"
    options = [_item("n_card"), _item("o_brief")]
    assert qpb._options_named_by_question(question, qpb._source_context(question), options) == []


def test_plan_answers_with_the_named_option():
    # (el fixture no tiene datos de fecha: el periodo puede quedar sin aplicar;
    # lo que se prueba es que no se contrapregunta y se elige la medida nombrada)
    plan = builder().build("cuantos triages pediatricos hubo en 2025")
    assert plan["status"] != "ambiguous", plan.get("resolution_notes")
    metric = plan.get("metric") or (plan.get("metric_resolution") or {}).get("metric") or {}
    assert metric.get("metric_id") == "t_ped", (plan.get("status"), metric.get("metric_id"))


# ---------------------------------------------------------------- 2. variante mostrada por X
def test_count_variant_shown_by_the_requested_dimension():
    qpb = builder()
    pie, card = _item("n_pie")["metric"], _item("n_card")["metric"]
    field = qpb._group_field_in("servicio", qpb._metric_dimensions(pie))
    assert field is not None and field["column"] == "HSUNOMBRE", field
    assert qpb._shown_by_field(pie, field)
    assert not qpb._shown_by_field(card, qpb._group_field_in("servicio", qpb._metric_dimensions(card)))
    plan = qpb.build("pacientes en naos por servicio")
    assert plan["status"] == "ready", (plan.get("status"), plan.get("resolution_notes"))
    assert plan["metric"]["metric_id"] == "n_pie", plan["metric"]["metric_id"]
    assert [g["column"] for g in plan.get("group_by") or []] == ["HSUNOMBRE"], plan.get("group_by")


def test_variants_of_different_tables_are_not_collapsed():
    qpb = builder()
    plan = {"status": "ambiguous", "reason": None, "source_context": {},
            "metric_resolution": {"candidates": [_item("o_mes"), _item("n_pie")]}}
    assert qpb._group_shown_option("x por servicio", {}, plan, plan["metric_resolution"]["candidates"],
                                   "servicio") is None


# ---------------------------------------------------------------- 3. rivales que no se desglosan
def test_rival_without_the_requested_dimension_is_not_offered():
    qpb = builder()
    best = _item("o_mes")["metric"]
    keep = qpb._rival_group_check("cuantos pacientes observados hay por aseguradora", best)
    assert not keep(_item("o_brief")["metric"])
    # Sin agrupación pedida, el rival sigue compitiendo (mismo nombre en otro tablero).
    assert qpb._rival_group_check("cuantos pacientes observados hay", best)(_item("o_brief")["metric"])
    plan = qpb.build("cuantos pacientes observados hay por aseguradora")
    assert plan["status"] == "ready", (plan.get("status"), plan.get("resolution_notes"))
    assert plan["metric"]["metric_id"] == "o_mes"
    assert [g["column"] for g in plan.get("group_by") or []] == ["ASEGURADOR"], plan.get("group_by")


# ---------------------------------------------------------------- 4. conector en el nombre técnico
def test_connector_inside_technical_column_name():
    assert _alias_prefix("areas de servicio", "AREA_SERVICIO") == "areas de servicio"
    assert _alias_prefix("area servicio urgencias", "AREA SERVICIO") == "area servicio"
    assert _alias_prefix("de servicio", "SERVICIO") is None          # antes de la primera palabra no
    assert _alias_prefix("areas de urgencias", "AREA_SERVICIO") is None


# ---------------------------------------------------------------- 5. intención analítica
def test_loose_word_is_not_analytic_intent():
    qpb = builder()
    options = [_item("n_card"), _item("o_brief")]
    assert not qpb.options_explain_question("que medicamento le doy a un paciente con fiebre y dolor de cabeza",
                                            options)
    assert qpb.options_explain_question("pacientes observados de urgencias", [_item("o_brief")])


def test_engine_answers_out_of_scope_without_analytic_intent():
    from src.chatbot.query_engine import QueryEngine

    engine = QueryEngine.__new__(QueryEngine)
    engine.query_plan_builder = builder()
    engine._think = lambda *args, **kwargs: None
    response = {"status": "needs_clarification",
                "query_plan": {"metric_resolution": {"candidates": [_item("n_card")]}}}
    assert not engine._fallback_has_analytic_intent("escribeme un codigo para ordenar una lista de pacientes",
                                                    response)
    response["query_plan"]["metric_resolution"]["candidates"] = [_item("o_brief")]
    assert engine._fallback_has_analytic_intent("pacientes observados", response)


# ---------------------------------------------------------------- 6. columnas de tablas relacionadas
def test_related_table_column_is_a_group_dimension():
    qpb = builder()
    metric = _item("r_sol")["metric"]
    field = qpb._group_field_in("especialidades", qpb._metric_dimensions(metric))
    assert field is not None and (field["table"], field["column"]) == ("REFERENCIA", "GEEDESCRI"), field
    plan = qpb.build("solicitudes de referencia por especialidades")
    assert plan["status"] == "ready", (plan.get("status"), plan.get("resolution_notes"))
    assert [(g["table"], g["column"]) for g in plan.get("group_by") or []] == [("REFERENCIA", "GEEDESCRI")]
    # Sin relación declarada no se supone ninguna: la NAOS no gana columnas ajenas.
    assert all(d["table"] == "PACIENTES" for d in qpb._metric_dimensions(_item("n_card")["metric"]))


# ---------------------------------------------------------------- 7. tablero nombrado + dimensión
def test_named_board_metric_with_dimension_is_numeric():
    qpb = builder()
    question = "peso por servicio en lavanderia"
    assert qpb.looks_numeric(question)
    plan = qpb.build(question)
    assert plan["status"] == "ready", (plan.get("status"), plan.get("resolution_notes"))
    assert plan["metric"]["metric_id"] == "l_peso"
    assert [g["column"] for g in plan.get("group_by") or []] == ["SERVICIO"], plan.get("group_by")
    # Sin dimensión ni periodo sigue siendo una pregunta para la documentación.
    assert not qpb._names_metric_of_named_board("que es el peso", qpb._source_context("que es el peso"))


# ---------------------------------------------------------------- 8. base de una participación
def test_ratio_metric_is_not_a_share_base():
    qpb = builder()
    assert qpb._is_ratio_metric(_item("e_pct")["metric"])       # «/» entre conteos y «%» en el nombre
    assert not qpb._is_ratio_metric(_item("e_tot")["metric"])
    assert not qpb._is_ratio_metric(_item("n_card")["metric"])
    context = {"status": "resolved", "routing_strength": "strong", "semantic_model": EPS, "report": EPS}
    default = qpb._default_share_metric(context)
    assert default.get("status") == "resolved" and default["metric"]["metric_id"] == "e_tot", default


# ---------------------------------------------------------------- 9. «cuántos» pide un conteo
def test_count_question_drops_time_sums_and_averages():
    qpb = builder()
    options = [_item("h_pac"), _item("h_tiempo")]
    kept = qpb._count_question_options("cuantos pacientes hospitalizados hay en el hospital", options)
    assert [item["metric"]["metric_id"] for item in kept] == ["h_pac"], kept
    # Pide un tiempo o no pide un conteo: no se descarta nada.
    assert qpb._count_question_options("cuantos minutos tardan los pacientes hospitalizados", options) == []
    assert qpb._count_question_options("pacientes hospitalizados", options) == []
    assert qpb._is_duration_or_ratio(_item("t_prom2")["metric"])   # AVERAGE
    assert not qpb._is_duration_or_ratio(_item("n_card")["metric"])
    # En el plan: «cuántos pacientes hospitalizados» responde con el conteo.
    plan = qpb.build("cuantos pacientes hospitalizados hay en el hospital")
    assert plan["status"] == "ready" and plan["metric"]["metric_id"] == "h_pac", (
        plan.get("status"), plan.get("resolution_notes"))


def test_generic_word_count_question_still_asks():
    """«cuántos pendientes hay» solo dice una palabra genérica: aunque descartar
    el porcentaje deje una opción, se sigue preguntando (no se elige por descarte)."""
    import src.semantic.query_plan_builder as module

    qpb = builder()
    pend = {**_item("n_card")["metric"], "metric_id": "p_cnt", "label": "PENDIENTES1", "measure": "PENDIENTES1"}
    pct = {**_item("e_pct")["metric"], "metric_id": "p_pct", "label": "%PENDIENTE", "measure": "%PENDIENTE"}
    plan = {"status": "ambiguous", "reason": None, "source_context": {}, "question": "cuantos pendientes hay",
            "metric_resolution": {"status": "ambiguous", "candidates": [
                {"metric": pend, "score": 1.0, "business_score": 1.0, "matched_name": "PENDIENTES1"},
                {"metric": pct, "score": 1.0, "business_score": 1.0, "matched_name": "%PENDIENTE"}]}}
    assert module.QueryPlanBuilder._count_question_options(qpb, "cuantos pendientes hay",
                                                           plan["metric_resolution"]["candidates"])
    refined = qpb._refine_options("cuantos pendientes hay", {}, plan)
    assert refined["status"] == "ambiguous", refined.get("status")


# ---------------------------------------------------------------- 10. alcance y dimensiones en las opciones
def test_scope_place_is_not_an_option_word():
    qpb = builder()
    question = "cual es el tiempo promedio de atencion en triage en el hospital"
    words = qpb._option_words(question, qpb._source_context(question))
    assert "hospital" not in words and "triage" in words, words
    # «hospital día» sí puede ser un valor: no se quita.
    question = "atenciones de hospital dia"
    assert "hospital" in qpb._option_words(question, qpb._source_context(question))


def test_named_board_ranking_word_names_a_dimension():
    plan = builder().build("cual fue el servicio con mas peso en lavanderia")
    assert plan["status"] == "ready", (plan.get("status"), plan.get("resolution_notes"))
    assert plan["metric"]["metric_id"] == "l_peso"


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

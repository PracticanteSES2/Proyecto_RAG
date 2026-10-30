"""
Contrapreguntas innecesarias y filtros espurios (auditoría del banco real).

1) Filtros espurios por coincidencia parcial de palabras:
   - «por asegurador en total» agrupa; «total» no es SALUD TOTAL EPS (BH17);
   - «interconsultas» no es INTERCONSULTAS SAS: el valor debe nombrarse completo (BH07);
   - «cuántas CUENTAS hay en proceso» no filtra PERFIL = CUENTAS: es lo que se cuenta (FC04);
   - los valores legítimos siguen («de urgencias», «de nueva eps», «salud total»).
2) Verbos y adverbios de la pregunta («en este momento», «se demoran», «duran»,
   «tomaron») no son palabras sin interpretar (BH09, TU13, AC05).
3) Opciones: la misma agregación con un nombre equivalente es UNA opción (TU02); una sola
   opción razonable se responde sin «¿Te refieres a X?» (AI07), y la que no explica la
   pregunta se sigue preguntando (FC05, LV01).

Ejecutar:  python -m tests.resolution.test_contrapreguntas      (o pytest tests/resolution)
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

from src.chatbot.query_engine import QueryEngine  # noqa: E402
from src.semantic.query_plan_builder import QueryPlanBuilder, _is_question_form_word  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.resolution.test_resolution import _column, _metric, _source  # noqa: E402

MODEL, REPORT = "Modelo Hospital", "Tablero Hospital"
DOMAINS = {
    ("ATENCIONES", "ASEGURADOR"): ["SALUD TOTAL EPS", "NUEVA EPS", "SURA"],
    ("ATENCIONES", "SERVICIO"): ["URGENCIAS", "HOSPITALIZACION"],
    ("ATENCIONES", "TIPO"): ["INTERCONSULTAS SAS", "CONSULTA EXTERNA"],
    ("EN_PROCESO", "PERFIL"): ["CUENTAS", "FACTURACION"],
}


def _slicer(visual_id, table, column):
    return {"visual_id": visual_id, "visual_type": "slicer", "fields": [_column(table, column)]}


def _build_fixture(root):
    catalog = root / "data" / "catalog"
    rag = root / "data" / "rag"
    for folder in (catalog, rag):
        folder.mkdir(parents=True)
    source = _source("hosp", REPORT, MODEL, ["tablero hospital"])
    registry = {
        "models": [{"semantic_model": MODEL, "semantic_model_key": "hosp",
                    "technical_catalog": source["technical_catalog"]}],
        "sources": [source],
    }
    technical = {"semantic_model": MODEL, "tables": [
        {"name": "ATENCIONES", "columns": [
            {"name": column, "data_type": "String"} for column in ("ASEGURADOR", "SERVICIO", "TIPO")]},
        {"name": "EN_PROCESO", "columns": [{"name": "PERFIL", "data_type": "String"}]},
        {"name": "INTERCONSULTAS", "columns": []},
    ]}
    visuals = {"schema_version": 2, "reports": [
        {"report": REPORT, "semantic_model": MODEL, "source_group": "hosp", "pages": [
            {"page_name": "p1", "page_display_name": "Inicio", "filters": {}, "visuals": [
                _slicer("v_aseg", "ATENCIONES", "ASEGURADOR"),
                _slicer("v_serv", "ATENCIONES", "SERVICIO"),
                _slicer("v_tipo", "ATENCIONES", "TIPO"),
            ]},
            {"page_name": "p2", "page_display_name": "Facturacion", "filters": {}, "visuals": [
                _slicer("v_perfil", "EN_PROCESO", "PERFIL"),
            ]},
        ]},
    ]}
    metrics = [
        _metric("h_atenciones", MODEL, REPORT, "ATENCIONES", "ATENCIONES", pages=["Inicio"]),
        _metric("h_proceso", MODEL, REPORT, "EN PROCESO DE FACTURACION", "EN_PROCESO", pages=["Facturacion"]),
        _metric("h_inter", MODEL, REPORT, "INTERCONSULTAS RESPONDIDAS", "INTERCONSULTAS", pages=["Interconsultas"]),
    ]
    files = {
        catalog / "source_registry.json": registry,
        rag / "visual_metrics_catalog.json": visuals,
        rag / "master_metrics.json": {"metrics": metrics},
        catalog / "hosp_rag.json": technical,
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


def filters_of(plan):
    return {
        item["column"]: item.get("value") or tuple(item.get("values") or ())
        for item in plan.get("filters", [])
        if item.get("type") == "categorical" and not item.get("temporal")
        and item.get("source") != "query_plan_temporal"
    }


# ------------------------------------------------- 1) filtros espurios
def test_total_alone_never_scores_a_value():
    qpb = builder()
    assert qpb._value_match_score("total", "SALUD TOTAL EPS", value_hint="total") == 0.0
    assert qpb._value_match_score("salud total", "SALUD TOTAL EPS", value_hint="salud total") >= 0.94


def test_by_dimension_in_total_groups_instead_of_filtering():
    plan = builder().build("cuantas atenciones hubo por asegurador en total")
    assert plan["status"] == "ready", plan.get("status")
    assert "ASEGURADOR" not in filters_of(plan), filters_of(plan)
    assert [g["column"] for g in plan.get("group_by", [])] == ["ASEGURADOR"], plan.get("group_by")


def test_shared_concept_word_is_not_a_partial_value():
    # «interconsultas» es un concepto de los indicadores y el valor
    # INTERCONSULTAS SAS no se nombra completo (falta «sas»).
    plan = builder().build("cuantas atenciones de interconsultas")
    assert filters_of(plan).get("TIPO") != "INTERCONSULTAS SAS", filters_of(plan)


def test_counted_noun_is_not_a_value_of_an_unusual_column():
    plan = builder().build("cuantas cuentas hay en proceso de facturacion")
    assert filters_of(plan).get("PERFIL") != "CUENTAS", filters_of(plan)


def test_legitimate_values_still_apply():
    qpb = builder()
    assert filters_of(qpb.build("cuantas atenciones de urgencias hubo")).get("SERVICIO") == "URGENCIAS"
    assert filters_of(qpb.build("cuantas atenciones de nueva eps hubo")).get("ASEGURADOR") == "NUEVA EPS"
    assert filters_of(qpb.build("cuantas atenciones de salud total hubo")).get("ASEGURADOR") == "SALUD TOTAL EPS"


# ------------------------------------------------- 2) verbos y adverbios
def test_question_form_words():
    for word in ("momento", "ahorita", "duran", "demora", "demoran", "tardan", "tomaron", "lavaron", "atendieron"):
        assert _is_question_form_word(word), word
    for word in ("urgencias", "ortopedia", "sura", "cuentas", "hospitalizacion"):
        assert not _is_question_form_word(word), word


def test_verbs_and_now_are_not_unresolved_words():
    qpb = builder()
    for question in (
        "cuantas atenciones hay en este momento",
        "cuantas atenciones hay ahorita",
        "cuanto se demoran las atenciones",
    ):
        plan = qpb.build(question)
        assert plan["status"] == "ready", (question, plan.get("status"), plan.get("unresolved_text"))
        assert not filters_of(plan), (question, filters_of(plan))


# ------------------------------------------------- 3) opciones
def _engine(fake_builder):
    return QueryEngine(
        conversation_manager=None, master_metric_resolver=None,
        master_metric_dax_generator=None, metric_resolver=None,
        filter_resolver=None, business_filter_resolver=None,
        dax_generator=None, dax_validator=None,
        powerbi_provider=None, rag_answer_engine=None,
        query_plan_builder=fake_builder, query_plan_dax_generator=None,
    )


def _option(metric_id, label, table, expression, model="TABLERO TIEMPOS URGENCIAS", page="RESUMEN"):
    return {
        "metric_id": metric_id, "label": label, "measure": label, "semantic_model": model,
        "report": model, "reports": [model], "table": table, "dax_expression": expression,
        "appearances": [{"report": model, "page_display_name": page, "visual_title": label}],
    }


class _Builder:
    def __init__(self, metrics, covers=True):
        self.metrics = {m["metric_id"]: m for m in metrics}
        self.covers = covers
        self.built = []

    def _logical_key(self, metric):
        return (metric.get("semantic_model"), metric.get("table"), metric.get("dax_expression"))

    def metric_covers_question(self, question, metric):
        return self.covers

    def build(self, question, intent_result=None, selected_metric_id=None):
        self.built.append(selected_metric_id)
        return {"status": "ready", "mode": "scalar", "question": question,
                "metric": self.metrics[selected_metric_id], "filters": [], "group_by": []}


def _answering(engine):
    engine._execute_query_plan = lambda plan: {
        "status": "success", "route": "powerbi", "metric": plan["metric"]["label"],
    }
    engine._note_same_measure_pages = lambda plan: None
    return engine


def test_same_aggregation_with_equivalent_name_is_one_option():
    promedio = _option("t1", "TIEMPO PROMEDIO PARA ATENCIÓN EN CONSULTA", "CONSULTA_URGENCIAS",
                       "AVERAGE('CONSULTA_URGENCIAS'[MINUTOS_CONSULTA])")
    filtrado = _option("t2", "TIEMPO PARA ATENCIÓN EN CONSULTA", "CONSULTA_URGENCIAS",
                       "CALCULATE(AVERAGE('CONSULTA_URGENCIAS'[MINUTOS_CONSULTA]), "
                       "KEEPFILTERS(FILTER(ALL('TIEMPO_PARA_EGRESO'[TiempoMinutos2]), "
                       "NOT ('TIEMPO_PARA_EGRESO'[TiempoMinutos2] IN {0}))))")
    otro = _option("t3", "TIEMPO PROMEDIO PARA CONSULTA URGENCIAS", "CONSULTAS_DIA",
                   "AVERAGE('CONSULTAS_DIA'[TIEMPO_CONSULTA])")
    engine = _engine(_Builder([promedio, filtrado, otro]))
    choices = engine._build_clarification_choices(
        [{"metric": m, "score": 1.0} for m in (promedio, filtrado, otro)], margin=None,
    )
    assert [c["id"] for c in choices] == ["t1", "t3"], [c["label"] for c in choices]


def test_same_name_different_computation_still_asks():
    # Contrapregunta legítima: mismo nombre, cálculo distinto (conteo frente a suma).
    conteo = _option("e1", "CONSULTAS EN ESPERA", "EN_ESPERA", "DISTINCTCOUNT('EN_ESPERA'[OID_CITA])")
    suma = _option("e2", "CONSULTAS EN ESPERA", "EN_ESPERA", "SUM('EN_ESPERA'[PENDIENTES])", page="OTRA")
    engine = _engine(_Builder([conteo, suma]))
    choices = engine._build_clarification_choices(
        [{"metric": m, "score": 1.0} for m in (conteo, suma)], margin=None,
    )
    assert len(choices) == 2, [c["label"] for c in choices]


def test_ambiguity_of_one_repeated_measure_is_answered():
    promedio = _option("t1", "TIEMPO PROMEDIO PARA ATENCIÓN EN CONSULTA", "CONSULTA_URGENCIAS",
                       "AVERAGE('CONSULTA_URGENCIAS'[MINUTOS_CONSULTA])")
    gemela = _option("t2", "TIEMPO PARA ATENCION EN CONSULTA", "CONSULTA_URGENCIAS",
                     "CALCULATE(AVERAGE('CONSULTA_URGENCIAS'[MINUTOS_CONSULTA]))")
    fake = _Builder([promedio, gemela])
    engine = _answering(_engine(fake))
    plan = {"status": "ambiguous", "question": "tiempo promedio de atencion en consulta",
            "metric_resolution": {"candidates": [
                {"metric": promedio, "score": 1.0}, {"metric": gemela, "score": 0.99}]}}
    result = engine._query_plan_failure(plan)
    assert result["status"] == "success", result.get("status")
    assert fake.built == ["t1"], fake.built


def test_single_reasonable_suggestion_is_answered_without_confirmation():
    patologia = _option("p1", "TOTAL DE REPORTES DE PATOLOGÍA EN EL PERIODO", "LAB",
                        "COUNT('LAB'[Consecutivo])", model="TABLERO DE ATENCIONES")
    fake = _Builder([patologia], covers=True)
    engine = _answering(_engine(fake))
    plan = {"status": "not_found", "question": "cuantos reportes de patologia van este año",
            "metric_resolution": {"suggestions": [{"metric": patologia, "score": 0.99}]}}
    result = engine._query_plan_failure(plan)
    assert result["status"] == "success" and result.get("single_option"), result
    assert fake.built == ["p1"]


def test_single_suggestion_that_does_not_explain_the_question_still_asks():
    promedio = _option("x1", "Promedio Mensual Año Pasado", "Calendario",
                       "[Promedio Mensual Año Pasado]", model="TABLERO DE ATENCIONES")
    fake = _Builder([promedio], covers=False)
    engine = _answering(_engine(fake))
    plan = {"status": "not_found", "question": "cuantos kilos de ropa se lavaron el mes pasado",
            "metric_resolution": {"suggestions": [{"metric": promedio, "score": 0.75}]}}
    result = engine._query_plan_failure(plan)
    assert result["status"] == "needs_clarification", result.get("status")
    assert fake.built == []


def test_real_builder_coverage_rule():
    qpb = builder()
    patologia = {"label": "TOTAL DE REPORTES DE PATOLOGÍA EN EL PERIODO", "measure": "TOTAL DE REPORTES"}
    promedio = {"label": "Promedio Mensual Año Pasado", "measure": "Promedio Mensual Año Pasado"}
    assert qpb.metric_covers_question("cuantos reportes de patologia van este año", patologia)
    assert not qpb.metric_covers_question("cuantos kilos de ropa se lavaron el mes pasado", promedio)
    assert not qpb.metric_covers_question("cuanto se facturo el mes pasado", promedio)


def test_only_question_form_words_left_are_answered_directly():
    pacientes = _option("b1", "PACIENTES HOSPITALIZADOS", "PACIENTES", "DISTINCTCOUNT('PACIENTES'[ID])",
                        model="BRIEFING HOSPITALARIO")
    fake = _Builder([pacientes])
    engine = _answering(_engine(fake))
    plan = {"status": "unsupported_filter", "reason": "possible_dimension_value_not_resolved",
            "question": "cuantos pacientes hay hospitalizados en este momento", "unresolved_text": "momento",
            "metric_resolution": {"metric": pacientes}}
    result = engine._query_plan_failure(plan)
    assert result["status"] == "success", result.get("status")
    # Un pretérito («se tomaron») tampoco es un filtro.
    assert engine._query_plan_failure(dict(plan, unresolved_text="tomaron"))["status"] == "success"
    # Una palabra que sí puede ser un filtro se sigue preguntando.
    plan = dict(plan, unresolved_text="piso azul")
    assert engine._query_plan_failure(plan)["status"] == "needs_clarification"


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

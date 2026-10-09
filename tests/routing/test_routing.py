"""
Pruebas de enrutamiento de preguntas (detección numérica, participación,
multi-métrica y fallback RAG <-> Query Plan) con fixtures en memoria.

Ejecutar:  python -m tests.routing.test_routing      (o con pytest)
No depende de Power BI, Qdrant, Ollama ni del arnés tests/sim.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

from src.chatbot.query_engine import QueryEngine
from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator
from src.semantic.query_plan_builder import QueryPlanBuilder

MODEL = "Lavanderia"
REPORT = "Tablero Lavanderia"
GROUP = "tablero_lavanderia"
SERVICIOS = {
    "ANTIFLUIDOS": 488.3, "CIRUGIA": 781.3, "URGENCIAS": 703.1,
    "HOSPITALIZACION": 585.9, "UCI ADULTOS": 820.3, "CONSULTA EXTERNA": 527.5,
}  # enero 2026; suma 3906.4 -> ANTIFLUIDOS = 12,5 %


def _col(column, role="Values"):
    return {"role": role, "kind": "column", "table": "LAVANDERIA", "column": column,
            "display_name": column, "native_query_ref": column,
            "query_ref": f"LAVANDERIA.{column}"}


def _hier(level):
    return {"role": "Values", "kind": "hierarchy_level", "table": "LAVANDERIA", "level": level,
            "query_ref": f"LAVANDERIA.Fecha.Variación.Jerarquía de fechas.{level}",
            "native_query_ref": f"Fecha {level}", "display_name": level}


def _agg(column, aggregation="Sum"):
    return {"role": "Values", "kind": "aggregation", "table": "LAVANDERIA", "column": column,
            "query_ref": f"{aggregation}(LAVANDERIA.{column})",
            "native_query_ref": f"{aggregation} of {column}"}


def _metric(label, dax, aliases, visual_ids):
    return {
        "metric_id": label.lower().replace(" ", "_"), "label": label, "aliases": aliases,
        "source_type": "visual_aggregation", "semantic_model": MODEL, "report": REPORT,
        "source_group": GROUP, "table": "LAVANDERIA", "dax_expression": dax,
        "validation_status": "approved", "reports": [REPORT], "source_groups": [GROUP],
        "appearances": [
            {"report": REPORT, "page_name": "p1", "page_display_name": "Lavanderia",
             "visual_id": vid, "visual_title": title, "visual_type": "tableEx",
             "role": "Values", "query_ref": "x"}
            for vid, title in visual_ids
        ],
    }


MASTER = {"metrics": [
    _metric("PESO", "SUM('LAVANDERIA'[Peso])", ["Sum of Peso", "Suma de Peso"],
            [("v_part", "Tabla de Participación por Servicio"), ("v_user", None)]),
    _metric("REGISTROS", "COUNTROWS('LAVANDERIA')", ["Count of OID"], [("v_user", None)]),
]}
CATALOG = {"reports": [{
    "report": REPORT, "semantic_model": MODEL, "source_group": GROUP, "metrics": [],
    "pages": [{"page_name": "p1", "page_display_name": "Lavanderia", "filters": {}, "visuals": [
        {"visual_id": "s_anio", "visual_type": "slicer", "fields": [_hier("Año")]},
        {"visual_id": "s_mes", "visual_type": "slicer", "fields": [_hier("Mes")]},
        {"visual_id": "v_part", "visual_type": "tableEx", "fields": [_col("SERVICIO"), _agg("Peso")]},
        {"visual_id": "v_user", "visual_type": "tableEx", "fields": [_col("NOMBRE_COMPLETO"), _agg("Peso")]},
    ]}],
}]}


class FakeRouter:
    def resolve(self, question=None, dashboard=None, **kwargs):
        if "lavanderia" in (question or "").lower().replace("í", "i"):
            return {"status": "resolved", "routing_strength": "strong",
                    "semantic_model": MODEL, "report": REPORT, "source_group": GROUP}
        return {"status": "unresolved", "routing_strength": "none"}


class FakeProvider:
    """Calcula el DAX generado sobre datos de enero 2026 (solo lo que las pruebas usan)."""

    def __init__(self):
        self.queries = []

    def execute_dax(self, dax, semantic_model=None):
        self.queries.append(dax)
        if "VALUES(" in dax:
            return {"status": "success", "rows": [{"[Value]": v} for v in SERVICIOS]}
        if "SUMMARIZECOLUMNS" in dax:
            return {"status": "error", "error": "no soportado por el fake"}
        in_january = bool(re.search(r"DATE\(2026, 1, 1\)", dax))
        if "COUNTROWS" in dax:
            return {"status": "success", "rows": [{"[__value]": 12 if in_january else None}]}
        if not in_january:
            return {"status": "success", "rows": [{"[__value]": None}]}
        if "DIVIDE(" in dax:
            numerator, denominator = dax.split("REMOVEFILTERS", 1)
            wanted = re.findall(r'TREATAS\(\{"([^"]+)"\}', numerator)
            top = sum(SERVICIOS[w] for w in wanted) if wanted else sum(SERVICIOS.values())
            bottom = sum(SERVICIOS.values())
            assert "TREATAS" not in denominator.split("DATE(")[0], "el denominador no debe filtrar la dimensión"
            return {"status": "success", "rows": [{"[__value]": top / bottom}]}
        wanted = re.findall(r'TREATAS\(\{"([^"]+)"\}', dax)
        value = sum(SERVICIOS[w] for w in wanted) if wanted else sum(SERVICIOS.values())
        return {"status": "success", "rows": [{"[__value]": round(value, 1)}]}


class FakeConversation:
    def handle_message(self, message):
        return {"status": "ready", "intent": "general_question",
                "original_question": message, "dashboard": None}


class FakeRAG:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"status": "success", "answer": "Respuesta documental",
                                 "sources": [], "synthesis_mode": "extractive"}

    def answer(self, intent_result):
        self.calls.append(intent_result.get("original_question"))
        return self.result


_NOT_FOUND = {"status": "not_found",
              "answer": "No encuentro evidencia suficiente en la documentación disponible."}


def make_system(rag_result=None):
    tmp = Path(tempfile.mkdtemp(prefix="routing_test_"))
    (tmp / "data" / "catalog").mkdir(parents=True)
    master = tmp / "data" / "catalog" / "master_metrics.json"
    catalog = tmp / "data" / "catalog" / "visual_catalog.json"
    master.write_text(json.dumps(MASTER, ensure_ascii=False), encoding="utf-8")
    catalog.write_text(json.dumps(CATALOG, ensure_ascii=False), encoding="utf-8")
    provider = FakeProvider()
    builder = QueryPlanBuilder(master, catalog, FakeRouter(), provider, project_root=tmp)
    rag = FakeRAG(rag_result)
    engine = QueryEngine(
        conversation_manager=FakeConversation(), master_metric_resolver=None,
        master_metric_dax_generator=None, metric_resolver=None, filter_resolver=None,
        business_filter_resolver=None, dax_generator=None, dax_validator=None,
        powerbi_provider=provider, rag_answer_engine=rag, source_router=FakeRouter(),
        query_plan_builder=builder, query_plan_dax_generator=QueryPlanDAXGenerator(),
    )
    return engine, builder, provider, rag


Q1 = ("En el mes de enero de 2026 en el servicio de antifluidos de la lavanderia, "
      "cuanta participacion y peso tuvo?")
Q2 = ("Cuanta participacion y peso tuvo el servicio de antifluidos en la lavanderia "
      "en el mes de enero de 2026?")
Q3 = "Cuanto peso tuvo el servicio de antifluidos en la lavanderia en el mes de enero de 2026?"
Q4 = "Que participacion tuvo el servicio de antifluidos en enero de 2026 en lavanderia?"


def _measures(result):
    return {m["label"]: m for m in result.get("measures", [])}


# ---------------------------------------------------------------- detección
def test_looks_numeric_all_forms():
    _, builder, _, _ = make_system()
    positivas = [
        "Cuanta participacion y peso tuvo antifluidos", "cuántas veces", "Cuántos registros hubo",
        "¿Cuál fue el peso de lavandería en enero de 2026?", "Qué fue el peso del servicio de antifluidos",
        "Dime el peso por turno en lavanderia en enero de 2026", "dame el peso de lavanderia",
        "muéstrame el peso de antifluidos en enero 2026", "indica el peso de lavanderia",
        "peso de antifluidos enero 2026 lavanderia", "peso por servicio lavanderia",
        "porcentaje del total de antifluidos", "proporción de antifluidos", "promedio de peso",
        "tasa de registros", "variación del peso",
    ]
    for texto in positivas:
        assert builder.looks_numeric(texto), texto


def test_looks_numeric_descriptive_goes_to_rag():
    _, builder, _, _ = make_system()
    negativas = [
        "¿Qué muestra el tablero de lavandería?", "¿Cómo se calcula el peso por turno?",
        "¿Qué significa el indicador peso?", "Para qué sirve el tablero de lavandería",
        "¿Qué filtros tiene el tablero de lavandería?", "Explica el peso por turno",
        "hola, buenos días",
    ]
    for texto in negativas:
        assert not builder.looks_numeric(texto), texto


# ---------------------------------------------------------------- compuestas
def test_q1_q2_answer_peso_and_participacion():
    for question in (Q1, Q2):
        engine, _, _, rag = make_system()
        result = engine.process(question)
        assert result["status"] == "success" and result["route"] == "powerbi", question
        medidas = _measures(result)
        assert set(medidas) == {"PESO", "Participación"}, medidas
        assert medidas["PESO"]["value"] == 488.3 and medidas["PESO"]["format"] == "number"
        assert medidas["Participación"]["format"] == "percent"
        assert abs(medidas["Participación"]["value"] - 0.125) < 1e-9  # fracción
        assert "DIVIDE(" in medidas["Participación"]["dax"] and "REMOVEFILTERS(" in medidas["Participación"]["dax"]
        assert result["metric"] == "PESO" and result["value"] == 488.3
        assert "488,3" in result["answer"] and "12,5 %" in result["answer"], result["answer"]
        assert "enero de 2026" in result["answer"] and "ANTIFLUIDOS" in result["answer"]
        assert result["query_plan"] and not rag.calls


def test_participation_only():
    engine, _, _, _ = make_system()
    result = engine.process(Q4)
    assert result["status"] == "success"
    assert [m["label"] for m in result["measures"]] == ["Participación"]
    assert abs(result["value"] - 0.125) < 1e-9 and "12,5 %" in result["answer"]


def test_share_dax_removes_only_the_dimension_filter():
    _, builder, _, _ = make_system()
    composite = builder.build_composite(Q1)
    share = [i for i in composite["items"] if i["kind"] == "share"][0]["plan"]
    dax = QueryPlanDAXGenerator().generate_share(share)["dax"]
    numerador, denominador = dax.split("REMOVEFILTERS", 1)
    assert 'TREATAS({"ANTIFLUIDOS"}' in numerador and "DATE(2026, 1, 1)" in numerador
    assert "TREATAS" not in denominador and "DATE(2026, 1, 1)" in denominador
    assert "'LAVANDERIA'[SERVICIO]" in denominador


def test_grouped_share_dax():
    _, builder, _, _ = make_system()
    composite = builder.build_composite("Cuanta participacion por servicio en lavanderia en enero de 2026")
    assert composite and composite["status"] == "composite"
    plan = composite["items"][0]["plan"]
    dax = QueryPlanDAXGenerator().generate_share(plan)["dax"]
    assert "SUMMARIZECOLUMNS" in dax and "DIVIDE(" in dax and "REMOVEFILTERS('LAVANDERIA'[SERVICIO])" in dax


def test_single_metric_question_is_not_composite():
    engine, builder, _, _ = make_system()
    assert builder.build_composite(Q3) is None
    result = engine.process(Q3)
    assert result["status"] == "success" and result["value"] == 488.3
    assert "measures" not in result


def test_multi_metric_split():
    engine, _, _, _ = make_system()
    result = engine.process("Cuantos registros y cuanto peso hubo en enero de 2026 en lavanderia")
    assert result["status"] == "success"
    medidas = _measures(result)
    assert medidas["REGISTROS"]["value"] == 12 and medidas["PESO"]["value"] == 3906.4, medidas
    assert "3.906,4" in result["answer"]


def test_unresolved_part_is_reported():
    engine, _, _, _ = make_system()
    result = engine.process("participacion y zzqx del servicio de antifluidos en enero de 2026 lavanderia")
    assert result["status"] == "success" and [m["label"] for m in result["measures"]] == ["Participación"]
    assert "zzqx" in result["answer"]


# ---------------------------------------------------------------- fallback
def test_definitional_questions_stay_in_rag():
    for texto in ("¿Qué muestra el tablero de lavandería?", "¿Cómo se calcula el peso por turno?"):
        engine, _, provider, rag = make_system()
        result = engine.process(texto)
        assert result["route"] == "rag" and rag.calls == [texto], result
        assert not provider.queries


def test_fallback_rag_not_found_uses_query_plan():
    engine, builder, _, rag = make_system(_NOT_FOUND)
    builder.looks_numeric = lambda *a, **k: False  # fuerza la ruta RAG primero
    result = engine.process(Q3)
    assert rag.calls, "debía intentar el RAG primero"
    assert result["status"] == "success" and result["route"] == "powerbi" and result["value"] == 488.3


def test_fallback_both_fail_returns_not_found():
    engine, _, _, rag = make_system(_NOT_FOUND)
    result = engine.process("¿Cuál es la capital de Francia?")
    assert result["status"] == "not_found" and rag.calls


def test_numeric_looking_but_unresolved_tries_rag_before_failing():
    engine, _, _, rag = make_system()
    result = engine.process("Cuanta gente vive en la luna")
    assert rag.calls, "no resolvió métrica: debe intentar el RAG"
    assert result["route"] == "rag"


# ---------------------------------------------------------------- ranking
def test_ranking_is_numeric_and_groups_by_the_named_dimension():
    _, builder, _, _ = make_system()
    for texto in ("que servicio tuvo mas peso en lavanderia", "top 3 servicios con mas peso",
                  "cual fue el servicio con menor peso en lavanderia"):
        assert builder.looks_numeric(texto), texto
    # «con más de 3» compara con una cifra: no es un ranking.
    assert not builder.is_ranking("registros del servicio con mas de 3 kilos")
    assert not builder.is_ranking("peso que tiene mas que antes")
    plan = builder.build("cual fue el servicio con mas peso en lavanderia en enero de 2026")
    assert plan["status"] == "ready" and plan["mode"] == "grouped", plan.get("status")
    assert [g["column"] for g in plan["group_by"]] == ["SERVICIO"]
    assert plan["ranking"]["direction"] == "desc" and plan["ranking"]["limit"] == 1
    assert not plan["unapplied_terms"], plan["unapplied_terms"]
    dax = QueryPlanDAXGenerator().generate_ranked(plan)["dax"]
    assert dax.startswith("EVALUATE\nTOPN(\n    1,") and "[__value], DESC" in dax, dax
    assert dax.rstrip().endswith("ORDER BY [__value] DESC")
    top = builder.build("top 3 servicios con menos peso en lavanderia en enero de 2026")
    assert top["ranking"] == {"direction": "asc", "limit": 3, "phrase": top["ranking"]["phrase"]}
    assert "[__value], ASC" in QueryPlanDAXGenerator().generate_ranked(top)["dax"]
    plural = builder.build("los servicios con mas peso en lavanderia en enero de 2026")
    assert plural["ranking"]["limit"] is None
    unranked = QueryPlanDAXGenerator().generate_ranked(plural)["dax"]
    assert "TOPN" not in unranked and unranked.endswith("ORDER BY [__value] DESC")
    # Sin ranking, generate_ranked == generate.
    plain = builder.build("peso por servicio en lavanderia en enero de 2026")
    assert plain["ranking"] is None
    assert QueryPlanDAXGenerator().generate_ranked(plain) == QueryPlanDAXGenerator().generate(plain)


def test_engine_orders_and_limits_rows_even_without_topn():
    engine, _, _, _ = make_system()
    rows = [{"S": "A", "[__value]": 2}, {"S": "B", "[__value]": 9}, {"S": "C", "[__value]": 5}]
    top = engine._apply_ranking({"ranking": {"direction": "desc", "limit": 2}}, rows)
    assert [r["S"] for r in top] == ["B", "C"]
    low = engine._apply_ranking({"ranking": {"direction": "asc", "limit": None}}, rows)
    assert [r["S"] for r in low] == ["A", "C", "B"]
    assert engine._apply_ranking({}, rows) == rows


# ---------------------------------------------------------------- palabras corrientes y sinónimos
def test_common_verbs_are_not_unresolved_filters():
    for texto in ("cuanto peso total hay registrado en lavanderia en enero de 2026",
                  "cuanto peso llevamos en lavanderia en enero de 2026",
                  "cuantos kilos se hicieron en lavanderia en enero de 2026",
                  "cuanto pesaron en lavanderia en enero de 2026"):
        engine, _, _, _ = make_system()
        result = engine.process(texto)
        assert result["status"] == "success" and result["value"] == 3906.4, (texto, result.get("status"))
        assert not result["unapplied_terms"], (texto, result["unapplied_terms"])


def test_colaborador_is_a_synonym_of_nombre_completo():
    _, builder, _, _ = make_system()
    plan = builder.build("peso por colaborador en lavanderia en enero de 2026")
    assert plan["status"] == "ready" and [g["column"] for g in plan["group_by"]] == ["NOMBRE_COMPLETO"]


# ---------------------------------------------------------------- preguntas sin indicador
def test_describe_unresolved_kinds_and_examples():
    _, builder, _, _ = make_system()
    out = builder.describe_unresolved("cuanto gana un medico general en colombia")
    assert out["kind"] == "out_of_scope" and "colombia" in out["words"], out
    assert builder.describe_unresolved("cual es el promedio mensual")["kind"] == "generic"
    assert builder.describe_unresolved("cuantas citas por servicio")["kind"] == "unknown"
    examples = out["examples"]
    assert examples and all(not any(ch.isdigit() for ch in e["label"]) for e in examples)
    assert examples[0]["report"] == REPORT


def test_metric_words_ignore_dimension_aliases():
    _, builder, _, _ = make_system()
    assert builder.metric_words("y por servicio") == []
    assert builder.metric_words("y de urgencias") == []
    assert builder.metric_words("y el peso en 2025") == ["peso"]


# ---------------------------------------------------------------- descriptivas con palabras numéricas
def test_descriptive_question_marked_numeric_by_the_intent_goes_to_rag():
    engine, _, provider, rag = make_system()

    class NumericIntent:
        def handle_message(self, message):
            return {"status": "ready", "intent": "query_metric",
                    "original_question": message, "dashboard": None}

    engine.conversation_manager = NumericIntent()
    question = "¿Cómo se calcula el porcentaje de peso por servicio en la lavandería?"
    result = engine.process(question)
    assert result["route"] == "rag" and rag.calls == [question], result.get("route")
    assert not provider.queries
    titles = [step.get("title") for step in (result.get("reasoning") or {}).get("steps", [])]
    assert "Pregunta descriptiva" in titles, titles


def test_numeric_question_with_percentage_stays_numeric():
    _, builder, _, _ = make_system()
    for texto in ("cual es el porcentaje de participacion de antifluidos en enero de 2026",
                  "cuales son los servicios con mas peso en lavanderia"):
        assert builder.looks_numeric(texto), texto
    assert not builder.looks_numeric("cuales son los rangos del peso en lavanderia")


def test_implicit_filter_reason_in_plan_and_reasoning():
    engine, _, _, _ = make_system()
    result = engine.process(Q3.replace("el servicio de ", ""))
    assert result["status"] == "success" and result["value"] == 488.3, result.get("status")
    implicit = [f for f in result["query_plan"]["filters"] if f.get("source") == "query_plan_implicit_value"]
    assert implicit and "ANTIFLUIDOS" in implicit[0]["reason"], implicit
    lines = [line for step in result["reasoning"]["steps"] for line in step.get("lines", [])]
    assert any("por qué:" in line and "ANTIFLUIDOS" in line for line in lines), lines


# Pruebas de enrutamiento v2 (tablero nombrado, «por X» técnico, valores
# implícitos estrictos): se ejecutan también con este módulo.
from tests.routing.test_board_routing import *  # noqa: E402,F401,F403


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

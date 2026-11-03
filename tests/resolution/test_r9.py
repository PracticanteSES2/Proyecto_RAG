"""
Ronda r9: generalización con preguntas realmente nuevas (auditoría holdout 2 y multiturno).

Reglas generales (cada una con 2 o 3 preguntas NUEVAS, que no están en ningún banco):

1. El RAG nunca da cifras, tendencias ni listas que no estén en la documentación recuperada
   (src/rag/grounding.py, en AnswerSynthesizer.synthesize_rag y RAGAnswerEngine para el respaldo
   extractivo). Comparación de periodos, top N, «agrupados/separados por», «por X», «en qué X
   están» son forma de pregunta de DATOS (data_shape_reason) y no caen al RAG.
2. Verbos con clítico o conjugados frente al sustantivo de acción del catálogo («asignarle» /
   ASIGNACIÓN, «admitieron» / ADMISIÓN); cualquier forma de tardar/demorar/durar = TIEMPO.
4. El complemento agente («canceladas por el paciente») no es un desglose; «sin contar X»,
   «excepto X», «salvo X» excluyen el valor (NOT IN).
5. Multiturno: mensaje corto sin «y» tras datos se intenta primero como seguimiento; un RAG en
   medio no borra el último turno de datos; «el mes/año anterior (a ese)» se cuenta desde el
   periodo anterior; «¿y el de X?» cambia el calificativo del indicador anterior.

Las pruebas de extremo a extremo usan el arnés realista (Power BI simulado, LLM falso) y se
omiten si no hay data/ real.

Ejecutar:  python -m tests.resolution.test_r9
"""
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.rag_answer_engine import RAGAnswerEngine  # noqa: E402
from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator  # noqa: E402
from src.rag.grounding import ground_answer  # noqa: E402
from src.semantic.resolucion.texto import (  # noqa: E402
    _token_similarity,
    canonical_phrases,
    canonical_token,
)
from src.semantic.resolucion.tipo_pregunta import TipoPreguntaMixin  # noqa: E402


# ---------------------------------------------------------------- 1. RAG sin cifras inventadas
SOURCE = ("Tablero: FARMACIA Indicador documentado: Oportunidad de dispensación: horas entre la orden y "
          "la entrega del medicamento. Meta institucional: 24 horas. Se calcula con DATEDIFF en horas.")


def test_rag_drops_numbers_not_in_sources():
    answer = ("La oportunidad de dispensación mide las horas entre la orden y la entrega. "
              "En septiembre fue de 37,5 horas. La meta institucional es de 24 horas.")
    grounded, removed = ground_answer(answer, [SOURCE], "cual fue la oportunidad de dispensacion en septiembre")
    assert "37,5" not in grounded and "24 horas" in grounded, grounded
    assert [kind for _, kind in removed] == ["cifra"], removed


def test_rag_drops_invented_trend_and_list():
    answer = "La oportunidad de dispensación subió de agosto a septiembre."
    grounded, removed = ground_answer(answer, [SOURCE], "la dispensacion subio o bajo de agosto a septiembre")
    assert not grounded.strip() and removed[0][1] == "tendencia", (grounded, removed)
    listing = "Los servicios que más piden son:\n- Neonatos\n- Ortopedia\n- Neumología"
    grounded, removed = ground_answer(listing, [SOURCE], "que servicios piden mas medicamentos")
    assert not grounded.strip() and len(removed) == 3, (grounded, removed)


def test_rag_keeps_supported_numbers_in_any_format():
    source = "Rango verde: menos de 1.440 minutos; rojo: 2.880 o más."
    answer = "El rango verde es menos de 1440 minutos y el rojo desde 2.880 minutos."
    grounded, removed = ground_answer(answer, [source], "cuales son los rangos")
    assert grounded == answer and not removed, (grounded, removed)


class _Retriever:
    def search_general(self, question, limit=5, dashboard=None):
        return [{"text": SOURCE, "score": 0.9, "dashboard": "FARMACIA"}]


class _InventingSynthesizer:
    def synthesize_rag(self, question, sources, history=None):
        return {"status": "success", "answer": "En octubre hubo 412 dispensaciones y 88 quedaron pendientes."}


def test_rag_engine_rejects_answer_made_only_of_invented_numbers():
    engine = RAGAnswerEngine(_Retriever(), answer_synthesizer=_InventingSynthesizer())
    result = engine.answer({"original_question": "cuantas dispensaciones hubo en octubre", "intent": "general_question"})
    assert result["status"] == "not_found" and result["not_found_reason"] == "unsupported_claims", result
    assert "412" not in result["answer"]


class _Shape(TipoPreguntaMixin):
    def _is_descriptive(self, normalized):
        return "como se calcula" in normalized


def test_data_shape_questions_are_data():
    shape = _Shape()
    for question in (
        "la ocupacion estuvo mas alta en abril o en mayo",          # comparación de periodos
        "los 3 servicios que mas egresos tuvieron en 2025",          # top N
        "interconsultas pendientes separadas por especialidad",      # agrupación
        "en que areas estan los pacientes de naos",                  # distribución
        "cirugias realizadas por quirofano",                         # desglose por X
    ):
        assert shape.data_shape_reason(question), question
    for question in (
        "como se calcula la ocupacion por servicio",                 # descriptiva
        "citas confirmadas por el paciente",                         # complemento agente
        "me ayudas por favor con los egresos",
    ):
        assert not shape.data_shape_reason(question), question


# ---------------------------------------------------------------- 2. verbos frente al catálogo
def test_verb_with_clitic_matches_action_noun():
    pairs = (("programarle", "programacion"), ("autorizaron", "autorizacion"), ("remitieron", "remision"),
             ("verificarse", "verificacion"))
    for verb, noun in pairs:
        assert _token_similarity(canonical_token(verb), canonical_token(noun)) >= 0.85, (verb, noun)
    for left, right in (("estacion", "estar"), ("nacion", "nacer"), ("cama", "camion")):
        assert _token_similarity(canonical_token(left), canonical_token(right)) < 0.85, (left, right)


def test_time_verbs_are_time():
    for word in ("tardaban", "demoramos", "demorarse", "duraron"):
        assert canonical_token(word) == "tiempo", word
    assert canonical_token("tarde") != "tiempo"   # «turno de la tarde»


# ---------------------------------------------------------------- 4. agente y negación
def test_agent_complement_is_not_a_breakdown():
    for question, kept in (
        ("cuantas ordenes fueron anuladas por el medico", "anuladas el medico"),
        ("facturas radicadas por los auxiliares este mes", "radicadas los auxiliares"),
    ):
        text, changes = canonical_phrases(question)
        assert kept in text and " por " not in f" {text} ", (question, text)
        assert changes, question
    for question in ("pacientes agrupados por el servicio", "egresos por servicio"):
        assert " por " in f" {canonical_phrases(question)[0]} ", question


def _negation_plan(question, value="SANITAS"):
    from src.semantic.query_plan_builder import QueryPlanBuilder
    plan = {"status": "ready", "filters": [
        {"type": "categorical", "table": "T", "column": "ASEGURADORA", "operator": "=", "value": value},
        {"type": "date_range", "source": "query_plan_temporal", "start": "2026-01-01", "end": "2026-02-01"},
    ]}
    notes = []
    QueryPlanBuilder._apply_negations(QueryPlanBuilder.__new__(QueryPlanBuilder), question, plan, notes)
    return plan["filters"][0], notes


def test_negation_excludes_the_value():
    for question in ("consultas de enero sin contar las de sanitas", "triages de enero excepto los de sanitas",
                     "egresos salvo sanitas en enero"):
        item, notes = _negation_plan(question)
        assert item.get("negated") and item["operator"] == "not in", (question, item)
        assert notes
    item, _ = _negation_plan("consultas de sanitas con menos espera")
    assert not item.get("negated"), item
    dax = QueryPlanDAXGenerator()._categorical_filter(
        {"table": "T", "column": "ASEGURADORA", "value": "SANITAS", "negated": True})
    assert "NOT ('T'[ASEGURADORA] IN {\"SANITAS\"})" in dax, dax


# ---------------------------------------------------------------- 5. multiturno (unidad)
def _engine():
    from src.chatbot.query_engine import QueryEngine
    return QueryEngine.__new__(QueryEngine)


def test_previous_period_counts_from_previous_turn():
    engine = _engine()
    last = {"filters": [{"type": "date_range", "source": "query_plan_temporal",
                         "start": "2025-03-01", "end": "2025-04-01"}]}
    text, why = engine._shift_from_previous_period("el mes anterior a ese", last)
    assert "febrero de 2025" in text and why, text
    january = {"filters": [{"type": "date_range", "source": "query_plan_temporal",
                            "start": "2026-01-01", "end": "2026-02-01"}]}
    assert "diciembre de 2025" in engine._shift_from_previous_period("y un mes antes", january)[0]
    assert "2024" in engine._shift_from_previous_period("el ano anterior", last)[0]
    assert engine._shift_from_previous_period("y por servicio", last)[1] is None


# ---------------------------------------------------------------- extremo a extremo (arnés realista)
_SYSTEM = {}


def _system():
    if "engine" not in _SYSTEM:
        try:
            from tests.realistic import harness
            harness.resolve_data_root()
            engine, cm, formatter, *_ = harness.build_engine(llm="fake")
        except Exception as error:  # sin data/ real
            _SYSTEM["engine"] = None
            _SYSTEM["error"] = str(error)
        else:
            _SYSTEM.update(engine=engine, cm=cm, formatter=formatter, harness=harness)
    return _SYSTEM if _SYSTEM.get("engine") else None


def _conversation(*messages):
    system = _system()
    if system is None:
        return None
    harness = system["harness"]
    harness.new_conversation(system["engine"], system["cm"])
    results = []
    for message in messages:
        result, _ = harness.ask(system["engine"], system["cm"], system["formatter"], message)
        results.append(result)
    return results


def _period_labels(result):
    from tests.eval import expectations as ex
    return [str(item.get("label") or "") for item in ex.applied_filters(result)]


def test_e2e_comparison_and_top_n_never_go_to_rag():
    for question in ("el peso de ropa lavada fue mayor en marzo o en abril de 2025",
                     "los 3 turnos de lavanderia con mas kilos en 2025"):
        results = _conversation(question)
        if results is None:
            print("  (omitido: sin data/ real)")
            return
        assert results[0].get("route") != "rag", (question, results[0].get("route"), results[0].get("answer"))


def test_e2e_previous_month_and_bare_followup():
    results = _conversation("kilos de ropa lavada en junio de 2025", "el mes anterior?", "segun turno?")
    if results is None:
        print("  (omitido: sin data/ real)")
        return
    assert any("mayo 2025" in label for label in _period_labels(results[1])), _period_labels(results[1])
    assert results[2].get("route") == "powerbi" and (results[2].get("query_plan") or {}).get("group_by"), results[2]


def test_e2e_rag_in_between_keeps_data_context():
    results = _conversation("kilos de ropa lavada en junio de 2025", "que mide el peso total por mes?",
                            "y por servicio?")
    if results is None:
        return
    assert results[1].get("route") == "rag", results[1].get("route")
    plan = results[2].get("query_plan") or {}
    assert results[2].get("route") == "powerbi" and plan.get("group_by"), results[2].get("route")


def test_e2e_qualifier_swap():
    results = _conversation("tiempo promedio para triage en urgencias este mes", "y el de consulta?")
    if results is None:
        return
    assert "CONSULTA" in str(results[1].get("metric") or "").upper(), results[1].get("metric")


def test_e2e_negation_and_agent():
    results = _conversation("cuantas atenciones de urgencias hubo en octubre sin contar las de nueva eps")
    if results is None:
        return
    plan = results[0].get("query_plan") or {}
    negated = [item for item in plan.get("filters") or [] if item.get("negated")]
    assert negated, plan.get("filters")
    results = _conversation("cuantas citas confirmadas ya por los pacientes hay")
    assert results[0].get("status") != "unsupported_filter", results[0].get("status")


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
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

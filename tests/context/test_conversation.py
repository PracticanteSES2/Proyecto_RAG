"""
Conversación con contexto: memoria de turnos y reescritura contextual.

Caso del propietario (2026-10-13, Power BI real): tras la tabla de pacientes
por especialidad, «Y en el mes pasado?» se trató como pregunta nueva («nombra un
indicador (pasado)») y respondió con la documentación de cancelaciones. Debe
dar la misma tabla con septiembre 2026.

Cubre:
- ConversationMemory: turnos, resumen de la respuesta, opciones ofrecidas y
  elegida, historial para la redacción, límite, borrado con «Nueva conversación»;
- señales deterministas (`contextual_rewriter.analyze`);
- reescritura con LLM (falso): validación (sin cifras ni indicadores nuevos),
  tiempo máximo;
- conversaciones multi-turno con el arnés offline (tests/sim): el caso del
  propietario completo (texto -> botón -> «Y en el mes pasado?»), mensajes sin
  forma de pregunta, corrección «no, me refería a...», documental <-> numérica,
  cambio de tema y regreso, comparación, total, y que una pregunta nueva no
  herede nada.

Ejecutar:
  PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 python -m tests.context.test_conversation
"""
import sys
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.contextual_rewriter import LLMContextRewriter, analyze  # noqa: E402
from src.chatbot.conversation_memory import ConversationMemory  # noqa: E402
from src.chatbot.response_formatter import clarification_buttons, format_filters_line  # noqa: E402


# ---------------------------------------------------------------------------
# Memoria
# ---------------------------------------------------------------------------

def _pbi_scalar(value=1076, metric="Egresos"):
    return {
        "status": "success", "route": "powerbi", "result_type": "scalar", "metric": metric,
        "metric_id": "m1", "value": value, "semantic_model": "INFORMES", "report": "INFORMES EJECUTIVOS",
        "filters": [{"type": "date_range", "label": "2025", "start": "2025-01-01", "end": "2026-01-01"},
                    {"type": "categorical", "column": "SERVICIO", "value": "URGENCIAS"}],
        "group_by": [], "query_plan": {"status": "ready"},
    }


def _pbi_table():
    return {
        "status": "success", "route": "powerbi", "result_type": "table", "metric": "CANTIDAD DE PACIENTES",
        "metric_id": "m2", "group_by": [{"label": "ESPECIALIDAD", "column": "ESPECIALIDAD"}],
        "rows": [{"T[ESPECIALIDAD]": None, "[__value]": 34}, {"T[ESPECIALIDAD]": "NEUROCIRUGIA", "[__value]": 1}],
        "total_rows": 2, "filters": [{"type": "date_range", "label": "octubre 2026 hasta hoy"}],
        "query_plan": {"status": "ready"},
    }


def test_memory_records_turns_options_and_history():
    memory = ConversationMemory(max_turns=3)
    memory.record("¿Cuántos egresos hubo?", {
        "status": "needs_clarification", "route": "clarification", "prompt": "¿Cuál necesitas?",
        "clarification_options": [{"id": "a", "label": "Egresos — INFORMES"}, {"id": "b", "label": "Total Egresos"}],
    })
    memory.record("Egresos — INFORMES", _pbi_scalar(), via="botón", topic={"metric_id": "m1", "question": "q"})
    first, second = memory.turns()
    assert first["meta"]["options"] == ["Egresos — INFORMES", "Total Egresos"]
    assert first["meta"]["chosen"] == "Egresos — INFORMES", first["meta"]
    assert second["assistant"].startswith("Egresos: 1.076") and "SERVICIO = URGENCIAS" in second["assistant"]
    assert second["meta"]["period"] == "2025" and second["meta"]["filters"] == "SERVICIO = URGENCIAS", second["meta"]
    memory.record("y por especialidad", _pbi_table(), interpreted="CANTIDAD DE PACIENTES por ESPECIALIDAD")
    table = memory.last()
    assert table["assistant"].startswith("Tabla de CANTIDAD DE PACIENTES por ESPECIALIDAD (2 filas; (en blanco): 34")
    history = memory.history(2)
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    assert history[2]["meta"]["interpreted"] == "CANTIDAD DE PACIENTES por ESPECIALIDAD"
    assert history[3]["meta"]["group_by"] == ["ESPECIALIDAD"] and history[3]["meta"]["rows"] == 2
    memory.record("¿qué muestra el tablero?", {
        "status": "success", "route": "rag", "dashboard": "LAVANDERIA", "answer": "Muestra el peso.",
        "sources": [{"dashboard": "LAVANDERIA", "chunk_type": "dashboard_overview", "page": "Inicio"}],
    })
    assert len(memory) == 3  # acotada
    rag = memory.last()
    assert rag["meta"]["dashboard"] == "LAVANDERIA" and rag["meta"]["pages"] == ["Inicio"], rag["meta"]
    assert [t["metric_id"] for t in memory.numeric_topics()] == ["m1"]
    assert "Usuario: ¿qué muestra el tablero?" in memory.transcript(2)
    memory.clear()
    assert not len(memory) and memory.history() == []


# ---------------------------------------------------------------------------
# Señales deterministas
# ---------------------------------------------------------------------------

def test_analyze_detects_context_cues_and_keeps_complement():
    cases = {
        "Y en el mes pasado?": ({"conector"}, "en el mes pasado"),
        "necesito eso mismo pero de septiembre": ({"lo mismo", "pero"}, "de septiembre"),
        "para el comité, los de urgencias": ({"propósito", "elipsis"}, "de urgencias"),
        "muéstrame solo los de Sura": ({"solo", "elipsis"}, "de Sura"),
        "ok, y el total?": ({"conector", "total"}, ""),
        "¿cómo se calcula ese indicador?": ({"referencia"}, "cómo se calcula"),
        "volviendo al peso, ¿y en marzo de 2026?": ({"volver a un tema"}, "peso, ¿y en marzo de 2026"),
    }
    for message, (cues, complement) in cases.items():
        result = analyze(message)
        assert set(result["cues"]) == cues and result["complement"] == complement, (message, result)
    correction = analyze("no, me refería a hospitalización")
    assert correction["correction"] == "hospitalización" and "corrección" in correction["cues"]
    compare = analyze("compáralo con el año pasado")
    assert compare["compare"] == "el año pasado"
    assert analyze("¿por qué tan alto?")["why"]
    assert analyze("gracias")["courtesy"] and not analyze("gracias")["cues"]
    # Preguntas completas: sin señales.
    for message in ("¿Cuántos egresos hubo en 2025?", "cirugias programadas de urologia en 2024",
                    "no hay datos de 2025?", "¿qué es el NEDOCS?"):
        assert not analyze(message)["cues"], (message, analyze(message))


# ---------------------------------------------------------------------------
# Reescritura con LLM (falso)
# ---------------------------------------------------------------------------

class FakeLLM:
    def __init__(self, answer, delay=0.0):
        self.answer = answer
        self.delay = delay
        self.calls = []

    def chat(self, messages, temperature=0.1, max_tokens=450, think=False):
        self.calls.append(messages)
        if self.delay:
            time.sleep(self.delay)
        return {"status": "success", "answer": self.answer}


HISTORY = "¿Cuántas cirugías programadas hubo en 2024? CIRUGÍAS PROGRAMADAS: 6.803. Filtros: 2024"


def _metric_words(text):
    return [w for w in text.lower().replace("í", "i").split() if w.strip("¿?") in ("cirugias", "programadas", "egresos")]


def test_llm_rewrite_is_validated():
    ok = LLMContextRewriter(FakeLLM("Pregunta reescrita: «¿Cuántas cirugías programadas de urología hubo en 2024?»"))
    outcome = ok.rewrite("y las de urología?", "Usuario: ...", HISTORY, metric_words=_metric_words)
    assert outcome["status"] == "success", outcome
    assert outcome["question"] == "¿Cuántas cirugías programadas de urología hubo en 2024?"
    prompt = ok.llm_provider.calls[0][1]["content"]
    assert "ÚLTIMO MENSAJE: y las de urología?" in prompt and "CONVERSACIÓN:" in prompt
    rejected = {
        "OK": "corta",
        "¿Cuántas cirugías programadas hubo en 2023?": "cifras",
        "¿Cuántos egresos de urología hubo en 2024?": "indicadores",
        "¿Cuántas cirugías programadas ambulatorias pediátricas nocturnas hubo en 2024?": "palabras",
    }
    for answer, reason in rejected.items():
        outcome = LLMContextRewriter(FakeLLM(answer)).rewrite(
            "y las de urología?", "", HISTORY, metric_words=_metric_words)
        assert outcome["status"] == "rejected" and reason in outcome["reason"], (answer, outcome)


def test_llm_rewrite_has_a_time_limit():
    outcome = LLMContextRewriter(FakeLLM("¿Cuántas cirugías programadas hubo en 2024?", delay=0.5),
                                 timeout=0.05).rewrite("y eso?", "", HISTORY)
    assert outcome["status"] == "timeout", outcome


# ---------------------------------------------------------------------------
# QueryEngine con fakes: el periodo se reconoce antes que el nombre de indicador
# ---------------------------------------------------------------------------

def test_period_words_are_not_taken_as_metric_names():
    from tests.clarification import test_clarification as tc

    engine, builder = tc.followup_engine()
    engine.reset()
    base_build = builder.build

    def build(question, intent_result=None, selected_metric_id=None):
        plan = base_build(question, intent_result, selected_metric_id)
        if "mes pasado" in question.lower():
            plan["filters"] = [*plan["filters"], {
                "type": "date_range", "table": "Calendario", "column": "Fecha", "year": 2026, "month": 9,
                "label": "septiembre 2026 (mes pasado)", "start": "2026-09-01", "end": "2026-10-01",
                "source": "query_plan_temporal"}]
        return plan

    builder.build = build
    # El catálogo real tiene indicadores con «pasado», «anterior» y «actual» en el nombre.
    builder.metric_words = lambda text: [w for w in text.split() if w in ("pasado", "anterior", "actual", "peso")]
    result = engine.process("Y en el mes pasado?")
    assert result["status"] == "success", result
    steps = [step["title"] for step in result["reasoning"]["steps"]]
    assert "Seguimiento de la consulta anterior" in steps, steps
    assert "Interpretación con el contexto de la conversación" in steps
    assert "septiembre 2026" in format_filters_line(result["filters"]), result["filters"]
    assert ("ESPECIALIDAD", "UROLOGIA") in [(f.get("column"), f.get("value")) for f in result["filters"]]
    assert result["interpreted_as"].startswith("CIRUGÍAS PROGRAMADAS"), result.get("interpreted_as")
    # Un indicador de verdad sigue siendo pregunta nueva.
    assert engine._followup_plan("y el peso en 2025") is None


def test_memory_survives_reset_and_full_reset_clears_it():
    from tests.clarification import test_clarification as tc

    engine, _ = tc.followup_engine()
    assert len(engine.conversation_memory) == 1
    engine.reset()
    assert len(engine.conversation_memory) == 1 and engine.conversation_history(1)[0]["meta"]["via"] == "botón"
    engine.reset(full=True)
    assert not len(engine.conversation_memory) and engine.conversation_history() == []


# ---------------------------------------------------------------------------
# Conversaciones con el arnés offline (tests/sim)
# ---------------------------------------------------------------------------

def _ctx():
    from tests.context import test_context
    return test_context


def interpretation(result):
    for step in (result.get("reasoning") or {}).get("steps") or []:
        if step["title"] == "Interpretación con el contexto de la conversación":
            return step["lines"][0]
    return None


def period(result):
    return format_filters_line(result.get("filters") or (result.get("query_plan") or {}).get("filters"))


_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre")


def _relative_months():
    """(«octubre 2026», «septiembre 2026», año del mes pasado) según hoy."""
    from datetime import date

    today = date.today()
    previous = today.year * 12 + today.month - 2
    return (f"{_MESES[today.month - 1]} {today.year}",
            f"{_MESES[previous % 12]} {previous // 12}", previous // 12)


def test_sim_owner_case_text_button_then_previous_month():
    ctx = _ctx()
    this_month, last_month, last_year = _relative_months()
    engine, cm, ask, choose = ctx.conversation()
    first, _ = ask(
        "Se me ha solicitado saber la cantidad de cirugias realizadas que tiene cada una de las "
        "especialidades en este mes"
    )
    assert first["status"] == "needs_clarification", first.get("status")
    second, _ = choose(clarification_buttons(first)[0]["id"])
    assert second["status"] == "success" and ctx.groups(second) == ["ESPECIALIDAD"], second.get("status")
    assert this_month in period(second), period(second)
    third, ui = ask("Y en el mes pasado?")
    assert third["status"] == "success" and third["route"] == "powerbi", (third.get("status"), ui)
    assert third["metric"] == second["metric"] and ctx.groups(third) == ["ESPECIALIDAD"], third["metric"]
    assert last_month in period(third) and this_month.split()[0] not in period(third), period(third)
    assert "Interpreté tu mensaje como" in (interpretation(third) or ""), ctx.steps(third)
    assert "nombra un indicador" not in ctx.reasoning(third)
    # Sin forma de pregunta: «eso mismo pero de agosto» toma el año de la consulta anterior.
    fourth, _ = ask("necesito eso mismo pero de agosto")
    assert fourth["metric"] == second["metric"] and ctx.groups(fourth) == ["ESPECIALIDAD"]
    assert f"agosto {last_year}" in period(fourth), period(fourth)
    # «ok, y el total?»: misma consulta sin desglose.
    total, _ = ask("ok, y el total?")
    assert total["status"] in ("success", "empty_result") and not total.get("group_by"), total.get("status")
    assert f"agosto {last_year}" in period(total)
    # La memoria lo registró todo (el botón y la interpretación).
    history = engine.conversation_history(10)
    assert history[2]["meta"]["via"] == "botón" and history[1]["meta"].get("chosen")
    assert history[4]["meta"]["interpreted"].startswith("CIRUGÍAS REALIZADAS por ESPECIALIDAD")


def test_sim_messages_without_question_form_and_comparison():
    ctx = _ctx()
    engine, cm, ask, _ = ctx.conversation()
    ask("cirugias programadas por especialidad en 2024")
    result, ui = ask("para el comité, los de urologia")
    assert ctx.categorical(result) == [("ESPECIALIDAD", "UROLOGIA")] and ctx.years(result) == [2024], ui
    assert "PROGRAMADAS" in str(result["metric"]).upper()
    result, ui = ask("compáralo con el año pasado")
    assert result["status"] == "success" and len(result.get("measures") or []) == 2, ui
    assert "(2024)" in ui and "(2023)" in ui and "Diferencia" in ui, ui
    assert "Comparación con otro periodo" in ctx.steps(result)
    # La comparación no cambia el tema: «y en 2025?» sigue siendo urología.
    result, ui = ask("y en 2025?")
    assert ctx.categorical(result) == [("ESPECIALIDAD", "UROLOGIA")] and ctx.years(result) == [2025], ui


def test_sim_correction_of_filter_and_of_metric():
    ctx = _ctx()
    engine, cm, ask, _ = ctx.conversation()
    ask("cirugias programadas de urologia en 2024")
    result, ui = ask("no, me refería a ortopedia")
    assert [value for _, value in ctx.categorical(result)] == ["ORTOPEDIA Y TRAUMATOLOGIA"], ui
    assert ctx.years(result) == [2024] and "PROGRAMADAS" in str(result["metric"]).upper()
    # Corrige el indicador: misma consulta (2024, ortopedia) con «realizadas».
    result, ui = ask("no, me refería a las realizadas")
    assert "realizadas" in (interpretation(result) or "").lower(), ctx.steps(result)
    assert "2024" in interpretation(result) and "ORTOPEDIA" in interpretation(result)
    assert result["status"] in ("needs_clarification", "success"), result.get("status")


def test_sim_numeric_to_documentation_and_back():
    ctx = _ctx()
    engine, cm, ask, _ = ctx.conversation()
    captured = []
    original = engine.rag_answer_engine.answer

    def answer(intent_data, history=None):
        captured.append(history)
        return original(intent_data)

    engine.rag_answer_engine.answer = answer
    try:
        ask("cuanto peso hubo en lavanderia en enero de 2026")
        result, ui = ask("¿cómo se calcula ese indicador?")
    finally:
        engine.rag_answer_engine.answer = original
    assert result["route"] == "rag", result.get("route")
    assert "¿cómo se calcula el indicador peso" in (interpretation(result) or "").lower(), interpretation(result)
    # El RAG recibe el historial (interfaz acordada answer(intent_data, history=None)).
    assert captured and captured[-1][0]["role"] == "user" and "peso" in captured[-1][0]["text"].lower()
    assert captured[-1][1]["meta"]["metric"].upper() == "PESO"
    # El tema sigue: «y en febrero de 2026?» vuelve al dato.
    result, ui = ask("y en febrero de 2026?")
    assert "PESO" in str(result["metric"]).upper() and "febrero 2026" in period(result), ui
    # «¿por qué tan alto?»: documentación del indicador (no una búsqueda suelta).
    result, _ = ask("¿por qué tan alto?")
    assert result["route"] in ("rag", "out_of_scope") and "PESO" in (interpretation(result) or "").upper()


def test_sim_documentation_to_numeric_uses_board_main_indicator():
    ctx = _ctx()
    engine, cm, ask, _ = ctx.conversation()
    first, _ = ask("¿qué muestra el tablero de lavandería?")
    assert first["route"] == "rag"
    result, ui = ask("¿y cuánto hubo en enero de 2026?")
    assert result["route"] == "powerbi" and "PESO" in str(result["metric"]).upper(), ui
    assert "3.906,4" in ui and "indicador principal" in ctx.reasoning(result), ui
    # «¿y qué filtros tiene?» tras hablar del dato: documentación de ese indicador / tablero.
    result, _ = ask("¿y qué filtros tiene?")
    assert result["route"] in ("rag", "clarification") and interpretation(result), ctx.steps(result)


def test_sim_topic_change_and_return():
    ctx = _ctx()
    engine, cm, ask, _ = ctx.conversation()
    ask("cuanto peso hubo en lavanderia en enero de 2026")
    other, _ = ask("¿Qué filtros tiene el tablero quirurgico?")
    assert other["route"] == "rag" and interpretation(other) is None  # tema nuevo: sin reescritura
    result, ui = ask("volviendo al peso, ¿y en febrero de 2026?")
    assert "PESO" in str(result["metric"]).upper() and "febrero 2026" in period(result), ui
    assert "vuelve a un tema anterior" in ctx.reasoning(result)


def test_sim_new_question_inherits_nothing():
    ctx = _ctx()
    engine, cm, ask, _ = ctx.conversation()
    ask("cirugias programadas de urologia en 2024")
    for text, metric in (("cuanto peso hubo en lavanderia en enero de 2026", "PESO"),
                         ("total atenciones por servicio en 2024", "ATENCIONES"),
                         ("cirugias programadas en 2025", "PROGRAMADAS")):
        result, ui = ask(text)
        assert result["status"] == "success" and metric in str(result["metric"]).upper(), (text, ui)
        assert interpretation(result) is None, (text, interpretation(result))
        assert "Seguimiento de la consulta anterior" not in ctx.steps(result), text
        assert ("ESPECIALIDAD", "UROLOGIA") not in ctx.categorical(result), (text, ctx.categorical(result))


def test_sim_llm_rewrite_is_used_only_when_rules_fail():
    ctx = _ctx()
    engine, cm, ask, _ = ctx.conversation()
    llm = FakeLLM("¿Cuántas cirugías programadas de urología hubo en 2024?")
    engine.context_llm = llm
    try:
        ask("cirugias programadas en 2024")
        # Las reglas bastan: no se llama al LLM.
        result, _ = ask("y en 2025?")
        assert not llm.calls and ctx.years(result) == [2025]
        ask("cirugias programadas en 2024")
        result, ui = ask("pero lo que operaron los colegas de urologia")
        assert llm.calls, ctx.steps(result)
        assert "MedGemma" in ctx.reasoning(result), ctx.steps(result)
        assert ctx.categorical(result) == [("ESPECIALIDAD", "UROLOGIA")] and ctx.years(result) == [2024], ui
        # Una propuesta que inventa un indicador se descarta.
        engine.context_llm = FakeLLM("¿Cuánto peso de lavandería hubo en 2024?")
        ask("cirugias programadas en 2024")
        result, _ = ask("pero lo que operaron los colegas de urologia")
        assert "Reescritura con MedGemma descartada" in ctx.steps(result), ctx.steps(result)
        assert "PESO" not in str(result.get("metric")).upper()
    finally:
        engine.context_llm = None


def test_llm_rewrite_keeps_the_message_and_metrics_come_from_the_user():
    """Caso con MedGemma real: tras «egresos 2025» y una respuesta documental que
    nombraba ingresos, «ok, ahora los de hospitalizacion» se reescribió como
    «¿Cuántos ingresos hubo en 2025?» (otro indicador y sin hospitalización)."""
    history = "Usuario: cuantos egresos hubo en 2025 Asistente: el tablero muestra ingresos y egresos"
    users = "cuantos egresos hubo en 2025 Egresos"
    rewriter = LLMContextRewriter(FakeLLM("¿Cuántos ingresos hubo en 2025?"))
    outcome = rewriter.rewrite(
        "ok, ahora los de hospitalizacion", "", history,
        metric_words=lambda t: [w for w in norm_words(t) if w in ("ingresos", "egresos")],
        metric_text=users, required_text="de hospitalizacion",
    )
    assert outcome["status"] == "rejected" and "omite" in outcome["reason"], outcome
    rewriter = LLMContextRewriter(FakeLLM("¿Cuántos ingresos de hospitalizacion hubo en 2025?"))
    outcome = rewriter.rewrite(
        "ok, ahora los de hospitalizacion", "", history,
        metric_words=lambda t: [w for w in norm_words(t) if w in ("ingresos", "egresos")],
        metric_text=users, required_text="de hospitalizacion",
    )
    assert outcome["status"] == "rejected" and "indicadores" in outcome["reason"], outcome
    rewriter = LLMContextRewriter(FakeLLM("¿Cuántos egresos de hospitalización hubo en 2025?"))
    outcome = rewriter.rewrite(
        "ok, ahora los de hospitalizacion", "", history,
        metric_words=lambda t: [w for w in norm_words(t) if w in ("ingresos", "egresos")],
        metric_text=users, required_text="de hospitalizacion",
    )
    assert outcome["status"] == "success", outcome


def norm_words(text):
    from src.chatbot.contextual_rewriter import norm
    return norm(text).split()


def test_sim_context_message_while_clarification_is_pending():
    """«Y en el mes pasado?» ANTES de elegir el indicador: no es una pregunta
    nueva; se vuelve a preguntar y, con el botón, se responde el mes pasado."""
    ctx = _ctx()
    this_month, last_month, _ = _relative_months()
    engine, cm, ask, choose = ctx.conversation()
    first, _ = ask(
        "Se me ha solicitado saber la cantidad de cirugias realizadas que tiene cada una de las "
        "especialidades en este mes"
    )
    assert first["status"] == "needs_clarification"
    again, ui = ask("Y en el mes pasado?")
    assert again["status"] == "needs_clarification", (again.get("status"), ui)
    assert "Y en el mes pasado?" in str(again.get("prompt") or again.get("question")), again.get("prompt")
    assert "Mensaje que depende de la contrapregunta pendiente" in ctx.steps(again)
    result, ui = choose(clarification_buttons(again)[0]["id"])
    assert result["route"] == "powerbi" and result["status"] in ("success", "empty_result"), ui
    assert ctx.groups(result) == ["ESPECIALIDAD"] and last_month in period(result), period(result)
    assert "Mensaje pendiente aplicado a la opción elegida" in ctx.steps(result)
    # Una pregunta nueva escrita en lugar del botón sigue descartando la contrapregunta.
    first, _ = ask(
        "Se me ha solicitado saber la cantidad de cirugias realizadas que tiene cada una de las "
        "especialidades en este mes"
    )
    result, _ = ask("cuanto peso hubo en lavanderia en enero de 2026")
    assert "PESO" in str(result.get("metric")).upper(), result.get("status")


def test_sim_where_is_the_previous_indicator():
    ctx = _ctx()
    engine, cm, ask, _ = ctx.conversation()
    ask("cirugias programadas de urologia en 2024")
    result, ui = ask("y eso en que tablero lo veo?")
    assert result["route"] == "rag" and "Tablero Quirurgico" in ui and "CIRUGÍAS PROGRAMADAS" in ui, ui
    assert "Programacion Quirurgica" in ui, ui
    # El tema sigue: «y en 2025?» vuelve al dato con el mismo filtro.
    result, ui = ask("y en 2025?")
    assert ctx.categorical(result) == [("ESPECIALIDAD", "UROLOGIA")] and ctx.years(result) == [2025], ui
    # Nombrar otro indicador es una pregunta nueva (documental).
    result, ui = ask("¿en qué tablero está el peso de lavandería?")
    assert "CIRUGÍAS PROGRAMADAS" not in ui, ui


# ---------------------------------------------------------------------------
# Runner mínimo
# ---------------------------------------------------------------------------

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

"""
Contexto entre turnos: qué se hereda y qué no.

Regresiones del caso del propietario (2026-10-13) y de la queja «una vez elige o
descarta una tabla/documentación se queda centrado en ella»:

- una pregunta nueva completa se resuelve desde cero (sin tablero, intención,
  indicador ni exclusiones de la pregunta anterior), aunque haya una
  contrapregunta pendiente y comparta palabras con alguna opción;
- «Ninguna de las anteriores» solo excluye opciones dentro de esa contrapregunta;
- los seguimientos anafóricos («de esos 33», «de esta cantidad de pacientes»,
  «desglósalo por», «ahora por») reutilizan la consulta anterior y lo dicen en
  el razonamiento; una pregunta que nombra otro indicador no es seguimiento;
- «cada una de las especialidades», «se me ha solicitado saber»...

Ejecutar:
  PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 python -m tests.context.test_context
(también compatible con pytest). Usa fakes en memoria y el arnés offline de tests/sim.
"""
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.conversation_manager import ConversationManager  # noqa: E402
from src.chatbot.response_formatter import NONE_OF_THE_ABOVE_ID, clarification_buttons  # noqa: E402
from src.semantic.request_phrases import fold, requester, rewrite_request, without_requester  # noqa: E402


# ---------------------------------------------------------------------------
# Reescritura de la pedida
# ---------------------------------------------------------------------------

OWNER_QUESTION = (
    "De urgencias se me ha solicitado saber la cantidad de pacientes que tiene cada una "
    "de las especialidades en hospitalizacion en este mes"
)


def test_fold_keeps_length_and_positions():
    text = "¿Cuántas cirugías hubo en ORTOPEDIA?"
    folded = fold(text)
    assert len(folded) == len(text)
    assert folded.split() == ["cuantas", "cirugias", "hubo", "en", "ortopedia"]


def test_owner_question_drops_request_filler_and_groups_by_specialty():
    text, notes = rewrite_request(OWNER_QUESTION)
    assert text == "De urgencias la cantidad de pacientes en hospitalizacion en este mes por especialidad", text
    joined = " ".join(notes)
    assert "«se me ha solicitado saber»" in joined and "no es un indicador ni un filtro" in joined
    assert "puede ser quien solicita el dato" in joined
    assert "«que tiene cada una de las especialidades» pide el desglose por especialidad" in joined


def test_grouping_phrases_become_por_dimension():
    cases = {
        "Cuantos de esos 33 tiene cada especialidad?": "Cuantos de esos 33 por especialidad?",
        "De esta cantidad de pacientes, cuantos hay de cada especialidad?":
            "De esta cantidad de pacientes, cuantos por especialidad?",
        "me piden el total de atenciones por cada sede en 2024": "el total de atenciones en 2024 por sede",
        "necesito reportar las cirugías realizadas en 2024 desglosadas por especialidad":
            "las cirugías realizadas en 2024 por especialidad",
        "peso de lavanderia discriminado por servicio en enero 2026":
            "peso de lavanderia en enero 2026 por servicio",
        "total atenciones según sede en 2024": "total atenciones en 2024 por sede",
        "desglósalo por especialidad": "por especialidad",
    }
    for question, expected in cases.items():
        text, notes = rewrite_request(question)
        assert text == expected and notes, (question, text)


def test_rewrite_leaves_other_questions_untouched():
    for question in ("¿Cuántos egresos hubo en 2025?", "cada cuanto se actualiza el tablero",
                     "total atenciones en 2024 según sede", "quiero saber el peso de enero",
                     "cuantas cirugias por cada paciente"):
        text, notes = rewrite_request(question)
        assert text == question and not notes, (question, text, notes)


def test_requester_phrase_is_detected_and_removable():
    who = requester(OWNER_QUESTION)
    assert who == {"phrase": "De urgencias", "who": "urgencias"}, who
    assert requester("cuantas cirugias hubo en 2024") is None
    assert requester("me piden las cirugias de 2024") is None  # nada antes del relleno
    rewritten, _ = rewrite_request(OWNER_QUESTION)
    assert without_requester(rewritten, who["phrase"]) == (
        "la cantidad de pacientes en hospitalizacion en este mes por especialidad"
    )


# ---------------------------------------------------------------------------
# ConversationManager: una pregunta nueva no hereda tablero ni intención
# ---------------------------------------------------------------------------

class FakeParser:
    """IntentParser mínimo: tablero por nombre y «¿a qué tablero?» si falta."""
    BOARDS = {"lavanderia": "Tablero Lavanderia", "farmacia": "Tablero Farmacia"}

    def detect_dashboard(self, question):
        text = str(question).lower()
        return next((board for key, board in self.BOARDS.items() if key in text), None)

    def detect_metric_type(self, question):
        return "total" if "cuant" in str(question).lower() else None

    def detect_year(self, question):
        return 2024 if "2024" in str(question) else None

    def detect_month(self, question):
        return None

    def determine_missing_fields(self, intent, dashboard, metric_type):
        return ["dashboard"] if intent == "get_filters" and not dashboard else []

    def get_candidate_dashboards(self, question):
        return list(self.BOARDS.values())

    def build_clarification_question(self, missing, candidates):
        return "¿A qué tablero o servicio te refieres?"

    def parse(self, question):
        from src.chatbot.intent_parser import ParsedIntent
        text = str(question).lower()
        intent = "get_filters" if "filtro" in text else (
            "query_metric" if "cuant" in text else "general_question")
        dashboard = self.detect_dashboard(question)
        missing = self.determine_missing_fields(intent, dashboard, None)
        return ParsedIntent(
            status="needs_clarification" if missing else "ready", intent=intent,
            dashboard=dashboard, metric_type=self.detect_metric_type(question),
            year=self.detect_year(question), month=None, missing_fields=missing,
            clarification_question="¿A qué tablero?" if missing else None,
            candidate_dashboards=self.get_candidate_dashboards(question) if missing else [],
            original_question=question,
            dashboard_reason="nombre del tablero" if dashboard else None,
        )


def test_new_question_does_not_inherit_dashboard_or_period_without_reset():
    cm = ConversationManager(FakeParser())
    first = cm.handle_message("cuantas cirugias hubo en 2024 en el tablero de lavanderia")
    assert first["dashboard"] == "Tablero Lavanderia" and first["year"] == 2024
    # Sin reset (la respuesta anterior fue una contrapregunta del Query Plan).
    second = cm.handle_message("como se calcula el porcentaje de ocupacion")
    assert second["status"] == "ready", second
    assert second["dashboard"] is None and second["year"] is None and second["metric_type"] is None, second
    assert second["original_question"] == "como se calcula el porcentaje de ocupacion"


def test_pending_dashboard_question_does_not_capture_a_new_question():
    cm = ConversationManager(FakeParser())
    assert cm.handle_message("que filtros tiene")["status"] == "needs_clarification"
    assert cm.is_reply_to_clarification("lavanderia")
    assert cm.is_reply_to_clarification("el tablero de lavanderia")
    assert cm.is_reply_to_clarification("2")
    assert cm.is_reply_to_clarification("que filtros tiene")  # reejecución tras el botón
    assert not cm.is_reply_to_clarification("¿Qué muestra el tablero de farmacia?")
    assert not cm.is_reply_to_clarification("cuantas cirugias hubo en 2024 en urgencias")
    result = cm.handle_message("¿Qué muestra el tablero de farmacia?")
    assert result["status"] == "ready", result
    assert result["original_question"] == "¿Qué muestra el tablero de farmacia?", result
    assert result["intent"] == "general_question" and result["dashboard"] == "Tablero Farmacia", result
    # Una respuesta corta sí completa la contrapregunta.
    cm.reset()
    cm.handle_message("que filtros tiene")
    reply = cm.handle_message("lavanderia")
    assert reply["status"] == "ready" and reply["original_question"] == "que filtros tiene"
    assert reply["dashboard"] == "Tablero Lavanderia"


# ---------------------------------------------------------------------------
# QueryEngine con fakes: contrapregunta pendiente, seguimiento anafórico
# ---------------------------------------------------------------------------

def _clarification_fakes():
    from tests.clarification import test_clarification as tc
    return tc


def test_full_question_is_not_taken_as_an_option():
    tc = _clarification_fakes()
    engine, builder = tc.make_engine()
    tc.clarify(engine)  # opciones: CIRUGÍAS REALIZADAS (x2), CIRUGÍAS PROGRAMADAS
    # Comparte «programadas» con una opción, pero es una pregunta completa.
    assert engine._continue_query_plan("¿cuántas cirugías programadas de urología hubo en 2024?") is None
    assert engine._pending_query_plan is None and not builder.calls
    # Nombra una opción pero pide además otra cosa (especialidad y año): pregunta nueva.
    tc.clarify(engine)
    result = engine._continue_query_plan("cirugias programadas de urologia en 2024")
    assert result is None and engine._pending_query_plan is None and not builder.calls, result
    # Respuestas que sí son opciones.
    for reply, expected in (("programadas", "q_prog"), ("la 2", "a_cx"),
                            ("quiero la de cirugias realizadas del tablero de atenciones institucionales", "a_cx")):
        engine, builder = tc.make_engine()
        tc.clarify(engine)
        result = engine._continue_query_plan(reply)
        assert result and result["status"] == "success" and builder.calls[-1]["selected"] == expected, reply


def test_none_exclusions_live_only_inside_that_clarification():
    tc = _clarification_fakes()
    engine, builder = tc.make_engine()
    tc.clarify(engine)
    engine.select_clarification_option(NONE_OF_THE_ABOVE_ID)
    assert set(engine._pending_query_plan["excluded"]) == {"q_cx", "a_cx", "q_prog"}
    # Pregunta nueva: la contrapregunta (y sus exclusiones) se descarta.
    assert engine._continue_query_plan("¿cuántas consultas hubo en total este año?") is None
    assert engine._pending_query_plan is None
    tc.clarify(engine)
    assert engine._pending_query_plan["excluded"] == []
    assert [c["id"] for c in engine._pending_query_plan["choices"]] == ["q_cx", "a_cx", "q_prog"]


def _followup_engine():
    tc = _clarification_fakes()
    engine, builder = tc.followup_engine()
    engine.reset()  # app.py::reset_if_finished tras la respuesta final
    return engine, builder


def test_anaphoric_followups_reuse_previous_query():
    engine, builder = _followup_engine()
    last = engine._last_success
    assert last["metric_id"] == "q_prog" and last["value"] == 3906.4, last
    for text in ("de esos cuantos hay en 2025", "de esta cantidad, cuantas en 2025",
                 "de los 3.906,4 cuantos en 2025", "ahora en 2025", "lo mismo en 2025"):
        plan = engine._followup_plan(text)
        assert plan is not None and plan["followup_of"]["anaphora"], text
        assert builder.calls[-1]["selected"] == "q_prog", (text, builder.calls[-1])
    # El nombre del MISMO indicador no lo convierte en pregunta nueva.
    assert engine._followup_plan("de esta cantidad de cirugias programadas, cuantas en 2025") is not None


def test_anaphora_is_bounded():
    engine, builder = _followup_engine()
    calls = len(builder.calls)
    # Sin referencia ni «y»: no es seguimiento (como antes).
    assert engine._followup_plan("en 2025") is None
    # «de los 50» con otro número (sin demostrativo): no se refiere a la respuesta.
    assert engine._followup_plan("de los 50 cuantos en 2025") is None
    # Nombra otro indicador: pregunta nueva aunque diga «de esos».
    engine.query_plan_builder.metric_words = lambda text: [w for w in text.split() if w in ("consultas", "peso")]
    assert engine._followup_plan("de esos cuantas consultas hubo en 2025") is None
    assert len(builder.calls) == calls
    # Con una contrapregunta pendiente manda la contrapregunta.
    _clarification_fakes().clarify(engine)
    assert engine._followup_plan("de esos cuantos en 2025") is None


def test_qualifier_prompt_cites_only_words_in_other_names():
    tc = _clarification_fakes()
    engine, _ = tc.make_engine()

    def cand(label):
        return {"metric": {"metric_id": label, "label": label}, "matched_name": label}
    plan = {
        "reason": "qualifier_matches_other_metrics",
        "unresolved_text": "urgencias solicitado cada especialidades hospitalizacion",
        "metric_resolution": {"candidates": [cand("PACIENTES INTUBADOS EN URGENCIAS"),
                                             cand("CANTIDAD DE PACIENTES")]},
    }
    prompt = engine._resolution_prompt(plan)
    assert prompt == "«urgencias» aparece en el nombre de varios indicadores. ¿Cuál necesitas?", prompt
    plan["unresolved_text"] = "solicitado cada"
    assert "solicitado" not in engine._resolution_prompt(plan)


def test_same_measure_pages_note_only_when_unfiltered_and_shorter():
    tc = _clarification_fakes()
    builder = tc.options_builder()
    engine, _ = tc.make_engine()
    engine.query_plan_builder = builder
    plan = builder.build("tiempo promedio gestion factura")
    engine._note_same_measure_pages(plan)
    note = plan["notes"][-1]
    assert note.startswith("Este indicador aparece en 3 páginas"), note
    assert note.endswith("es el valor general, sin los filtros propios de cada página."), note
    assert "cada página puede aplicar" not in note
    filtered = builder.build("tiempo promedio gestion factura")
    filtered["filters"] = [{"type": "categorical", "table": "T", "column": "AREA", "value": "X"}]
    filtered["notes"] = []
    engine._note_same_measure_pages(filtered)
    assert not filtered["notes"], filtered["notes"]


# ---------------------------------------------------------------------------
# Conversaciones largas con el arnés offline (tests/sim)
# ---------------------------------------------------------------------------

_SIM = {}


def sim():
    if "system" not in _SIM:
        from tests.sim import harness
        _SIM["harness"] = harness
        _SIM["system"] = harness.build_engine()
    return _SIM["harness"], _SIM["system"]


def conversation():
    harness, (engine, cm, formatter, *_) = sim()
    harness.new_conversation(engine, cm)

    def ask(text):
        return harness.ask(engine, cm, formatter, text)

    def choose(option_id):
        result = engine.select_clarification_option(option_id)
        ui = harness._APP_NS["get_display_answer"](result, formatter)
        harness._APP_NS["reset_if_finished"](result, engine, cm)
        return result, ui

    return engine, cm, ask, choose


def steps(result):
    return [step["title"] for step in (result.get("reasoning") or {}).get("steps") or []]


def reasoning(result):
    return " ".join(
        line for step in (result.get("reasoning") or {}).get("steps") or [] for line in step.get("lines") or []
    )


def categorical(result):
    return [(f.get("column"), f.get("value")) for f in result.get("filters") or []
            if f.get("type") == "categorical" and f.get("column") not in ("AÑO", "MES")]


def years(result):
    return [f.get("value") for f in result.get("filters") or [] if f.get("column") == "AÑO"]


def groups(result):
    return [str(g.get("column")).upper() for g in result.get("group_by") or []]


def test_sim_owner_style_question_is_a_breakdown_and_requester_is_not_a_filter():
    engine, cm, ask, _ = conversation()
    result, ui = ask(
        "Del quirofano se me ha solicitado saber la cantidad de cirugias programadas que tiene "
        "cada una de las especialidades en 2024"
    )
    assert result["status"] == "success" and result["result_type"] == "table", (result.get("status"), ui)
    assert groups(result) == ["ESPECIALIDAD"] and years(result) == [2024], (groups(result), result["filters"])
    assert categorical(result) == [], categorical(result)  # «Del quirófano» no es ESTADO = Paciente en Quirófano
    assert "Frases de la pedida reinterpretadas" in steps(result)
    assert "Quién pide el dato o filtro" in steps(result)
    assert "solicitado" not in ui and "cada especialidades" not in ui, ui
    # «De urologia me piden...»: coincide exactamente con un valor -> filtro.
    result, ui = ask("De urologia me piden saber las cirugias programadas en 2024")
    assert categorical(result) == [("ESPECIALIDAD", "UROLOGIA")], categorical(result)


def test_sim_anaphoric_followups_add_the_grouping_to_the_previous_query():
    engine, cm, ask, _ = conversation()
    first, _ = ask("cirugias programadas en 2024")
    assert first["status"] == "success" and first["result_type"] == "scalar", first.get("status")
    for text in ("Cuantas de esas tiene cada especialidad?",
                 "De esta cantidad de cirugias programadas, cuantas hay de cada especialidad?",
                 "desglosalo por especialidad", "ahora por especialidad"):
        ask("cirugias programadas en 2024")
        result, ui = ask(text)
        assert result["status"] == "success" and result["result_type"] == "table", (text, result.get("status"), ui)
        assert groups(result) == ["ESPECIALIDAD"] and years(result) == [2024], (text, result["filters"])
        assert "PROGRAMADAS" in str(result["metric"]).upper(), (text, result["metric"])
        assert "Seguimiento de la consulta anterior" in steps(result), (text, steps(result))
        assert "se refiere a la respuesta anterior" in reasoning(result), text
    # Desglose de un valor escalar: la respuesta dice cuánto suman las filas.
    ask("cirugias programadas en 2024")
    result, ui = ask("Cuantas de esas 6.803 tiene cada especialidad?")
    assert "Desglose por ESPECIALIDAD" in ui, ui


def test_sim_new_question_with_other_metric_is_not_a_followup():
    engine, cm, ask, _ = conversation()
    ask("cirugias programadas en 2024")
    result, ui = ask("y de esos cuanto peso hubo en lavanderia en enero de 2026?")
    assert result["status"] == "success" and "PESO" in str(result["metric"]).upper(), (result.get("metric"), ui)
    assert "Seguimiento de la consulta anterior" not in steps(result)


def test_sim_pending_metric_question_does_not_capture_new_questions():
    engine, cm, ask, _ = conversation()
    first, _ = ask("top 5 especialidades con mas cirugias")
    assert first["status"] == "needs_clarification"
    result, ui = ask("cuanto peso hubo en lavanderia en enero de 2026")
    assert result["status"] == "success" and "PESO" in str(result["metric"]).upper(), ui
    assert "3.906,4" in ui, ui
    assert "Pregunta nueva: se descarta la contrapregunta pendiente" in steps(result)
    second, _ = ask("cuantas cirugias realizadas hubo en 2024")
    assert second["status"] == "needs_clarification"
    result, ui = ask("¿cuántas cirugías programadas de urología hubo en 2024?")
    assert result["status"] == "success" and "PROGRAMADAS" in str(result["metric"]).upper(), ui
    assert categorical(result) == [("ESPECIALIDAD", "UROLOGIA")] and years(result) == [2024]


def test_sim_pending_dashboard_question_does_not_capture_new_questions():
    engine, cm, ask, choose = conversation()
    first, _ = ask("que filtros tiene")
    assert first["status"] == "needs_clarification" and first.get("clarification_type") == "dashboard"
    result, ui = ask("¿Qué muestra el tablero de lavandería?")
    assert result["route"] == "rag" and "Lavanderia" in str(result.get("dashboard")), result.get("dashboard")
    assert "Contrapregunta de tablero descartada" in steps(result)
    assert engine._pending_dashboard_clarification is None and not cm.state.awaiting_clarification
    # Justo después de hablar del tablero de lavandería, «que filtros tiene» se
    # entiende con el contexto (los filtros de ESE tablero), no se contrapregunta.
    result, ui = ask("que filtros tiene")
    assert result["route"] == "rag" and "Lavanderia" in str(result.get("dashboard")), result.get("dashboard")
    assert "Interpretación con el contexto de la conversación" in steps(result)
    # El botón de tablero sigue funcionando (conversación nueva: sin contexto).
    engine, cm, ask, choose = conversation()
    first, _ = ask("que filtros tiene")
    buttons = clarification_buttons(first)
    result, ui = choose(buttons[1]["id"])
    assert result["route"] == "rag" and result.get("dashboard") == buttons[1]["id"], result.get("dashboard")


def test_sim_documentary_question_does_not_keep_previous_dashboard():
    engine, cm, ask, _ = conversation()
    first, _ = ask("cuantas cirugias hubo en el tablero de lavanderia")
    assert first["status"] == "needs_clarification"
    result, _ = ask("como se calcula el porcentaje de ocupacion")
    assert result["route"] in ("rag", "out_of_scope"), result.get("route")
    assert result.get("dashboard") != "Tablero Lavanderia", result.get("dashboard")
    intent_lines = [
        line for step in result["reasoning"]["steps"] if step["title"] == "Analizador de intención"
        for line in step["lines"]
    ]
    assert not any(line.startswith("tablero:") for line in intent_lines), intent_lines


def test_sim_long_conversation_with_topic_changes():
    engine, cm, ask, choose = conversation()
    # 1. Lavandería (numérica) y su seguimiento.
    result, ui = ask("cuanto peso hubo en lavanderia en enero de 2026")
    assert "PESO" in str(result["metric"]).upper() and "3.906,4" in ui
    result, ui = ask("y en febrero de 2026?")
    assert "PESO" in str(result["metric"]).upper() and "Seguimiento de la consulta anterior" in steps(result)
    # 2. Otro indicador de otro tablero: pregunta nueva (no hereda Lavandería).
    result, ui = ask("total atenciones por servicio en 2024")
    assert result["status"] == "success" and "ATENCIONES" in str(result["metric"]).upper(), ui
    assert "Seguimiento de la consulta anterior" not in steps(result)
    assert "lavanderia" not in str(result.get("semantic_model")).lower()
    # 3. Documental de otro tablero.
    result, ui = ask("¿Qué filtros tiene el tablero de lavandería?")
    assert result["route"] == "rag"
    # 4. Contrapregunta + «Ninguna de las anteriores».
    result, _ = ask("top 5 especialidades con mas cirugias")
    shown = {option["id"] for option in result.get("clarification_options") or []}
    result, _ = choose(NONE_OF_THE_ABOVE_ID)
    if result.get("status") == "needs_clarification":
        assert not shown & {option["id"] for option in result.get("clarification_options") or []}
    # 5. Pregunta nueva: desde cero, sin exclusiones, tablero ni indicador heredados.
    result, ui = ask("cirugias programadas de urologia en 2024")
    assert result["status"] == "success" and "PROGRAMADAS" in str(result["metric"]).upper(), ui
    assert categorical(result) == [("ESPECIALIDAD", "UROLOGIA")] and years(result) == [2024]
    # 6. Seguimiento de la última respuesta (no de las anteriores).
    result, ui = ask("y por especialidad")
    assert result["result_type"] == "table" and "PROGRAMADAS" in str(result["metric"]).upper()
    # 7. La misma pregunta con opciones vuelve a ofrecer todas (sin exclusiones viejas).
    again, _ = ask("top 5 especialidades con mas cirugias")
    assert {option["id"] for option in again.get("clarification_options") or []} == shown


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

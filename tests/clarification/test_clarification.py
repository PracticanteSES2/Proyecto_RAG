"""
Pruebas de las contrapreguntas seleccionables y del formato de respuestas.

Ejecutar:
  PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 python -m tests.clarification.test_clarification
(también compatible con pytest). Usa fakes en memoria y, para los flujos de
extremo a extremo, el arnés offline de tests/sim.
"""
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.conversation_manager import ConversationManager  # noqa: E402
from src.chatbot.query_engine import QueryEngine  # noqa: E402
from src.chatbot.response_formatter import (  # noqa: E402
    EMPTY_RESULT_MESSAGE,
    NONE_OF_THE_ABOVE_ID,
    clarification_buttons,
    clarification_prompt,
    format_filters_line,
    format_number_es,
    format_percent_es,
    format_query_plan_answer,
)


# ---------------------------------------------------------------------------
# Fakes en memoria
# ---------------------------------------------------------------------------

def metric(metric_id, label, model, report, page, description=""):
    return {
        "metric_id": metric_id, "label": label, "measure": label.title(),
        "semantic_model": model, "report": report, "reports": [report],
        "table": "Medidas", "description": description,
        "appearances": [{"report": report, "page_display_name": page,
                        "visual_id": metric_id + "_v", "visual_title": label}],
    }


M_QUIR = metric("q_cx", "CIRUGÍAS REALIZADAS", "Gestion Quirurgica",
                "Tablero Quirurgico", "Cirugias Realizadas", "Cirugías hechas en quirófano")
M_ATEN = metric("a_cx", "CIRUGÍAS REALIZADAS", "Atenciones Institucionales",
                "Tablero de Atenciones Institucionales", "Cirugias")
M_PROG = metric("q_prog", "CIRUGÍAS PROGRAMADAS", "Gestion Quirurgica",
                "Tablero Quirurgico", "Programacion")
M_NOISE = metric("n_x", "CONSULTAS", "Otro Modelo", "Tablero Otro", "Inicio")


def ambiguous_plan(question="¿Cuántas cirugías realizadas hubo?"):
    def cand(m, score):
        return {"metric": m, "score": score, "business_score": score}
    return {
        "status": "ambiguous", "question": question,
        "metric_resolution": {"candidates": [
            cand(M_QUIR, 1.30), cand(M_ATEN, 1.28), cand(M_PROG, 1.10), cand(M_NOISE, 0.30),
        ]},
    }


class FakeBuilder:
    def __init__(self, alternatives=None):
        self.calls = []
        self.alternatives = alternatives if alternatives is not None else [M_NOISE]
        self.alternative_calls = []

    def alternative_metrics(self, question, intent_result=None, exclude_ids=(), limit=6):
        self.alternative_calls.append({"question": question, "exclude": list(exclude_ids)})
        return [
            {"metric": m, "score": 0.5, "business_score": 0.5}
            for m in self.alternatives if m["metric_id"] not in exclude_ids
        ][:limit]

    def build(self, question, intent_result=None, selected_metric_id=None):
        self.calls.append({"question": question, "selected": selected_metric_id})
        chosen = {m["metric_id"]: m for m in (M_QUIR, M_ATEN, M_PROG, M_NOISE)}[selected_metric_id]
        return {
            "status": "ready", "mode": "scalar", "question": question,
            "semantic_model": chosen["semantic_model"], "report": chosen["report"],
            "dashboard": "Inicio", "metric": chosen, "filters": [], "group_by": [],
        }


class FakeDax:
    def generate(self, plan):
        return {"status": "generated", "dax": "EVALUATE ROW(\"__value\", 1)"}


class FakePowerBI:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else [{"__value": 3906.4}]

    def execute_dax(self, dax, semantic_model=None):
        return {"status": "success", "rows": self.rows}


def make_engine(rows=None, describer=None, alternatives=None):
    builder = FakeBuilder(alternatives)
    engine = QueryEngine(
        conversation_manager=None, master_metric_resolver=None,
        master_metric_dax_generator=None, metric_resolver=None,
        filter_resolver=None, business_filter_resolver=None,
        dax_generator=None, dax_validator=None,
        powerbi_provider=FakePowerBI(rows), rag_answer_engine=None,
        query_plan_builder=builder, query_plan_dax_generator=FakeDax(),
        option_describer=describer,
    )
    return engine, builder


def clarify(engine):
    return engine._query_plan_failure(ambiguous_plan())


# ---------------------------------------------------------------------------
# Opciones
# ---------------------------------------------------------------------------

def test_options_are_distinguishable_carry_ids_and_drop_noise():
    engine, _ = make_engine()
    result = clarify(engine)
    assert result["status"] == "needs_clarification"
    assert result["clarification_type"] == "query_plan_metric"
    options = result["clarification_options"]
    assert [o["id"] for o in options] == ["q_cx", "a_cx", "q_prog"], options
    labels = [o["label"] for o in options]
    assert len(set(l.casefold() for l in labels)) == len(labels), labels
    assert all("Medidas" not in l for l in labels)
    assert "Tablero Quirurgico" in options[0]["label"] or "Gestion Quirurgica" in options[0]["label"]
    assert options[0]["detail"] == "Tablero Quirurgico › Cirugias Realizadas · Gestion Quirurgica"
    assert options[0]["description"] == "Cirugías hechas en quirófano"
    # el texto numerado se conserva para el historial del chat
    assert "1. " in result["question"] and "3. " in result["question"]


def test_options_are_limited_to_six():
    engine, _ = make_engine()
    plan = ambiguous_plan()
    plan["metric_resolution"]["candidates"] = [
        {"metric": metric(f"m{i}", f"Metrica {i}", "M", "R", "P"), "score": 1.0}
        for i in range(10)
    ]
    assert len(engine._query_plan_failure(plan)["clarification_options"]) == 6


def test_button_model_from_result():
    engine, _ = make_engine()
    buttons = clarification_buttons(clarify(engine))
    assert [b["id"] for b in buttons] == ["q_cx", "a_cx", "q_prog", NONE_OF_THE_ABOVE_ID]
    assert buttons[-1]["label"] == "Ninguna de las anteriores"
    # Descripción corta visible bajo el botón, sin repetir lo que dice la etiqueta.
    assert buttons[0]["caption"] == "Cirugías hechas en quirófano", buttons[0]
    assert "Tablero Quirurgico" in buttons[0]["label"]
    prog = next(b for b in buttons if b["id"] == "q_prog")
    assert prog["caption"] == "Tablero Quirurgico › página Programacion", prog
    assert clarification_buttons({"status": "success"}) == []
    assert clarification_buttons({"status": "needs_clarification",
                                  "clarification_options": ["a", "b"]}) == []


def test_prompt_shows_only_the_question_when_there_are_buttons():
    engine, _ = make_engine()
    result = clarify(engine)
    prompt = clarification_prompt(result)
    assert prompt == "Encontré varios indicadores. ¿Cuál necesitas?", prompt
    # La lista numerada sigue disponible para quien responde escribiendo.
    assert "1. " in result["question"]
    plain = {"status": "needs_clarification", "question": "¿Qué año?"}
    assert clarification_prompt(plain) == "¿Qué año?"


def test_suggestions_on_not_found_become_options():
    engine, _ = make_engine()

    def cand(m, score):
        return {"metric": m, "score": score, "business_score": score}

    plan = {
        "status": "not_found", "question": "¿cuántas cirugías?",
        "metric_resolution": {"candidates": [], "suggestions": [
            cand(M_PROG, 0.6), cand(M_QUIR, 0.6), cand(M_NOISE, 0.1),
        ]},
    }
    result = engine._query_plan_failure(plan)
    assert result["status"] == "needs_clarification"
    # Sin margen: se ofrecen todas las sugerencias que vienen del planificador.
    assert [o["id"] for o in result["clarification_options"]] == ["q_prog", "q_cx", "n_x"]
    empty = engine._query_plan_failure({**plan, "metric_resolution": {"candidates": []}})
    assert empty["status"] == "metric_not_resolved"


def test_request_words_tolerate_typos_but_not_real_values():
    from src.semantic.query_plan_builder import _is_request_word, canonical_token
    for word in ("necesito", "necsito", "nesecito", "quisiera", "informacion", "podrias", "datos"):
        assert _is_request_word(canonical_token(word)), word
    for word in ("consulta", "ayudas", "cirugias", "urgencias", "hospitalizacion", "necropsia"):
        assert not _is_request_word(canonical_token(word)), word


# ---------------------------------------------------------------------------
# Selección por botón
# ---------------------------------------------------------------------------

def test_select_option_pins_chosen_metric_and_clears_pending():
    engine, builder = make_engine()
    clarify(engine)
    result = engine.select_clarification_option("a_cx")
    assert result["status"] == "success", result
    assert builder.calls[-1] == {"question": "¿Cuántas cirugías realizadas hubo?", "selected": "a_cx"}
    assert result["metric_id"] == "a_cx" and result["semantic_model"] == "Atenciones Institucionales"
    assert engine._pending_query_plan is None


def test_select_option_rejects_unknown_id():
    engine, builder = make_engine()
    clarify(engine)
    result = engine.select_clarification_option("hack")
    assert result["status"] == "error" and not builder.calls
    engine.reset()
    assert engine.select_clarification_option("q_cx")["status"] == "error"  # sin pendiente


# ---------------------------------------------------------------------------
# Respuesta escrita
# ---------------------------------------------------------------------------

def typed(text):
    engine, builder = make_engine()
    clarify(engine)
    result = engine._continue_query_plan(text)
    return result, builder


def test_typed_numbers_and_variants():
    for text, expected in [("2", "a_cx"), ("2.", "a_cx"), ("opción 2", "a_cx"),
                           ("Opcion 1", "q_cx"), ("la 3", "q_prog"), ("el 1", "q_cx")]:
        result, builder = typed(text)
        assert result["status"] == "success" and builder.calls[-1]["selected"] == expected, (text, result)


def test_typed_report_or_page_words():
    result, builder = typed("la del tablero quirurgico realizadas")
    assert builder.calls[-1]["selected"] == "q_cx", result
    result, builder = typed("atenciones institucionales")
    assert builder.calls[-1]["selected"] == "a_cx", result
    result, builder = typed("programadas")
    assert builder.calls[-1]["selected"] == "q_prog", result


def test_typed_exact_label():
    engine, builder = make_engine()
    options = clarify(engine)["clarification_options"]
    result = engine._continue_query_plan(options[1]["label"])
    assert builder.calls[-1]["selected"] == "a_cx", result


def test_long_reply_matching_option_is_not_a_new_question():
    result, builder = typed("quiero la de cirugias realizadas del tablero de atenciones institucionales por favor")
    assert result is not None and result["status"] == "success", result
    assert builder.calls[-1]["selected"] == "a_cx"


def test_unmatched_new_question_drops_pending_and_unmatched_short_reasks():
    engine, _ = make_engine()
    clarify(engine)
    assert engine._continue_query_plan("cuantas consultas hubo en total este año") is None
    assert engine._pending_query_plan is None
    clarify(engine)
    again = engine._continue_query_plan("xyz")
    assert again["status"] == "needs_clarification" and again["clarification_options"]
    assert engine._pending_query_plan is not None


def test_ambiguous_ambiguous_words_do_not_guess():
    # "cirugias realizadas" aparece en dos opciones: no se adivina
    result, builder = typed("cirugias realizadas")
    assert result["status"] == "needs_clarification" and not builder.calls


def test_reset_clears_pending():
    engine, _ = make_engine()
    clarify(engine)
    engine.reset()
    assert engine._pending_query_plan is None and engine._pending_dashboard_clarification is None


# ---------------------------------------------------------------------------
# «Ninguna de las anteriores»
# ---------------------------------------------------------------------------

def test_none_button_searches_alternatives_excluding_shown_options():
    engine, builder = make_engine()
    clarify(engine)
    result = engine.select_clarification_option(NONE_OF_THE_ABOVE_ID)
    assert result["status"] == "needs_clarification", result
    assert [o["id"] for o in result["clarification_options"]] == ["n_x"]
    assert builder.alternative_calls[-1] == {
        "question": "¿Cuántas cirugías realizadas hubo?", "exclude": ["q_cx", "a_cx", "q_prog"],
    }
    assert result["prompt"].startswith("Busqué otros indicadores")
    assert clarification_buttons(result)[-1]["id"] == NONE_OF_THE_ABOVE_ID
    # Elegir la alternativa ejecuta la pregunta original con ese indicador.
    chosen = engine.select_clarification_option("n_x")
    assert chosen["status"] == "success" and builder.calls[-1]["selected"] == "n_x"


def test_none_again_without_more_alternatives_asks_to_rephrase():
    engine, builder = make_engine()
    clarify(engine)
    engine.select_clarification_option(NONE_OF_THE_ABOVE_ID)
    result = engine.select_clarification_option(NONE_OF_THE_ABOVE_ID)
    assert result["status"] == "not_found" and "Reformula" in result["answer"], result
    assert builder.alternative_calls[-1]["exclude"] == ["q_cx", "a_cx", "q_prog", "n_x"]
    assert engine._pending_query_plan is None


def test_typed_none_replies():
    for text in ("ninguna", "Ninguna de las anteriores", "ninguno me sirve", "otra opción",
                 "buscar otro indicador", "4", "opción 4"):
        result, builder = typed(text)
        assert result["status"] == "needs_clarification", (text, result)
        assert builder.alternative_calls and not builder.calls, text
    # «5» no existe: no es «ninguna» ni una opción.
    result, builder = typed("5")
    assert not builder.alternative_calls


def test_unresolved_words_offers_search_other_metric():
    engine, builder = make_engine()
    plan = {
        "status": "unsupported_filter", "reason": "possible_dimension_value_not_resolved",
        "question": "¿cuántas cirugías realizadas en el piso azul?", "unresolved_text": "piso azul",
        "metric_resolution": {"metric": M_QUIR},
    }
    result = engine._query_plan_failure(plan)
    buttons = clarification_buttons(result)
    assert [b["id"] for b in buttons] == ["q_cx", NONE_OF_THE_ABOVE_ID]
    assert buttons[-1]["label"] == "No, buscar otro indicador"
    other = engine._continue_query_plan("no")
    assert other["status"] == "needs_clarification" and builder.alternative_calls


# ---------------------------------------------------------------------------
# Descripciones redactadas por el LLM
# ---------------------------------------------------------------------------

class FakeDescriber:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def describe(self, question, options):
        self.calls.append((question, options))
        if self.fail:
            raise ConnectionError("LLM caído")
        return {"status": "success", "elapsed_s": 0.1, "raw": "...",
                "descriptions": {o["id"]: f"Cuenta las {o['label'].lower()} del tablero"
                                 for o in options if o["id"] != "q_prog"}}


def test_llm_descriptions_become_captions_with_catalog_fallback():
    describer = FakeDescriber()
    engine, _ = make_engine(describer=describer)
    result = clarify(engine)
    question, options = describer.calls[-1]
    assert question == "¿Cuántas cirugías realizadas hubo?"
    assert options[0]["report"] == "Tablero Quirurgico" and options[0]["page"] == "Cirugias Realizadas"
    by_id = {o["id"]: o for o in result["clarification_options"]}
    assert by_id["q_cx"]["summary"].startswith("Cuenta las cirugías realizadas del tablero")
    assert by_id["q_cx"]["summary_source"] == "modelo"
    # Sin descripción del LLM para esta opción: queda la del catálogo.
    assert by_id["q_prog"]["summary_source"] == "catálogo"
    assert by_id["q_prog"]["summary"] == "Tablero Quirurgico › página Programacion"


def test_llm_failure_keeps_catalog_descriptions():
    engine, _ = make_engine(describer=FakeDescriber(fail=True))
    buttons = clarification_buttons(clarify(engine))
    assert buttons[0]["caption"] == "Cirugías hechas en quirófano", buttons


def test_option_describer_prompt_and_parsing():
    from src.chatbot.option_describer import OptionDescriber

    class Provider:
        def __init__(self, answer, status="success"):
            self.answer, self.status, self.messages = answer, status, None

        def chat(self, messages, **kwargs):
            self.messages = messages
            return {"status": self.status, "answer": self.answer, "model": "fake"}

    options = [{"id": "a", "label": "Total cirugías", "measure": "Total Cirugias",
                "report": "Tablero Quirúrgico", "page": "Inicio"},
               {"id": "b", "label": "Cirugías programadas"}]
    provider = Provider("1. **Número total de cirugías** del tablero quirúrgico.\n"
                        "2) \"Cirugías agendadas por especialidad\"\nnota extra")
    outcome = OptionDescriber(provider).describe("¿cuántas cirugías?", options)
    assert outcome["status"] == "success"
    assert outcome["descriptions"] == {
        "a": "Número total de cirugías del tablero quirúrgico.",
        "b": "Cirugías agendadas por especialidad",
    }, outcome
    prompt = provider.messages[-1]["content"]
    assert "¿cuántas cirugías?" in prompt and "Informe: Tablero Quirúrgico" in prompt
    down = OptionDescriber(Provider(None, "ollama_error")).describe("x", options)
    assert down["status"] == "ollama_error" and down["descriptions"] == {}


# ---------------------------------------------------------------------------
# Razonamiento visible
# ---------------------------------------------------------------------------

def test_selection_reasoning_lists_choice_dax_and_result():
    from src.chatbot.reasoning_trace import format_reasoning_text
    engine, _ = make_engine()
    clarify(engine)
    result = engine.select_clarification_option("a_cx")
    reasoning = result["reasoning"]
    titles = [step["title"] for step in reasoning["steps"]]
    assert "El usuario eligió una opción" in titles
    assert "Consulta a Power BI" in titles and titles[-1] == "Resultado del turno"
    text = format_reasoning_text(reasoning, "**CIRUGÍAS REALIZADAS**: 3.906,4")
    assert "Opción elegida: a_cx" in text and "EVALUATE ROW" in text
    assert text.rstrip().endswith("3.906,4")
    assert engine.last_reasoning["steps"] == reasoning["steps"]


# ---------------------------------------------------------------------------
# Resultado vacío / formato
# ---------------------------------------------------------------------------

def test_blank_scalar_is_empty_result():
    for rows in ([{"__value": None}], [{"__value": ""}], [{"__value": "BLANK"}]):
        engine, _ = make_engine(rows)
        clarify(engine)
        result = engine.select_clarification_option("q_cx")
        assert result["status"] == "empty_result", rows


def test_number_formatting_es():
    assert format_number_es(3906.4) == "3.906,4"
    assert format_number_es(1200.0) == "1.200"
    assert format_number_es(1234567) == "1.234.567"
    assert format_number_es("3906.4") == "3.906,4"
    assert format_percent_es(12.5) == "12,5 %"
    assert format_percent_es(0.125) == "12,5 %"


def test_answer_formatting_scalar_percent_filters_and_unapplied():
    text = format_query_plan_answer({
        "value": 3906.4, "metric": "PESO",
        "filters": [{"type": "categorical", "concept": "servicio", "value": "ANTIFLUIDOS"},
                    {"type": "date_range", "month": 1, "year": 2026}],
        "unapplied_terms": ["turno noche"],
    })
    assert text.startswith("**PESO**: 3.906,4")
    assert "Filtros: SERVICIO = ANTIFLUIDOS · enero 2026" in text
    assert "No pude aplicar: turno noche" in text
    pct = format_query_plan_answer({"value": 12.5, "metric": "% de participación"})
    assert "12,5 %" in pct
    pct2 = format_query_plan_answer({"value": 0.125, "metric": "Participación", "metric_format": "0.0%"})
    assert "12,5 %" in pct2
    assert format_query_plan_answer({"value": 42, "metric": "Cirugías"}).endswith("42")


def test_answer_formatting_measures_and_empty_and_never_none():
    text = format_query_plan_answer({"measures": [
        {"label": "Peso", "value": 488.3, "format": "number", "unit": "kg"},
        {"label": "Participación", "value": 12.5, "format": "percent"},
        {"label": "Vacío", "value": None, "format": "number"},
    ]})
    assert "- **Peso**: 488,3 kg" in text and "- **Participación**: 12,5 %" in text
    assert "None" not in text and "Vacío" not in text
    for value in (None, "", "BLANK"):
        out = format_query_plan_answer({"value": value, "metric": "X"})
        assert EMPTY_RESULT_MESSAGE in out and "None" not in out
    assert format_filters_line([]) == ""


def test_grouped_truncation_message():
    engine, _ = make_engine()
    rows = [{"SEDE": f"S{i}", "__value": i} for i in range(60)]
    plan = {"group_by": [{"column": "SEDE", "label": "Sede"}], "metric": {"label": "Total"}}
    answer = engine._format_grouped_answer(plan, rows)
    assert "Mostrando 50 de 60 filas." in answer


# ---------------------------------------------------------------------------
# Tablero (ConversationManager)
# ---------------------------------------------------------------------------

class FakeParsed:
    status = "needs_clarification"
    missing_fields = ["dashboard"]
    clarification_question = "¿A qué tablero o servicio te refieres? Por ejemplo: A, B."
    candidate_dashboards = ["Tablero de Lavandería", "Tablero Quirúrgico"]

    def to_dict(self):
        return {"intent": "describe_dashboard", "status": self.status,
                "missing_fields": self.missing_fields, "original_question": "¿Qué muestra?"}


class FakeIntentParser:
    def parse(self, message):
        return FakeParsed()

    def detect_dashboard(self, message):
        return None

    def detect_metric_type(self, message):
        return None

    def detect_year(self, message):
        return None

    def detect_month(self, message):
        return None

    def get_candidate_dashboards(self, question, limit=3):
        return FakeParsed.candidate_dashboards

    def determine_missing_fields(self, intent, dashboard, metric_type):
        return [] if dashboard else ["dashboard"]

    def build_clarification_question(self, missing, candidates):
        return FakeParsed.clarification_question


def test_conversation_manager_returns_real_question_and_candidates():
    cm = ConversationManager(FakeIntentParser())
    result = cm.handle_message("¿Qué muestra?")
    assert result["question"].startswith("¿A qué tablero")
    assert result["candidates"] == FakeParsed.candidate_dashboards


def test_dashboard_partial_name_and_number_are_accepted():
    for reply in ("lavandería", "la de lavanderia", "tablero quirurgico", "2", "quirurgico"):
        cm = ConversationManager(FakeIntentParser())
        cm.handle_message("¿Qué muestra?")
        result = cm.handle_message(reply)
        assert result["status"] == "ready", (reply, result)
        expected = "Tablero Quirúrgico" if reply in ("tablero quirurgico", "2", "quirurgico") else "Tablero de Lavandería"
        assert result["dashboard"] == expected, (reply, result)


def test_dashboard_unknown_reply_asks_again_with_candidates():
    cm = ConversationManager(FakeIntentParser())
    cm.handle_message("¿Qué muestra?")
    result = cm.handle_message("otra cosa")
    assert result["status"] == "needs_clarification"
    assert result["candidates"] == FakeParsed.candidate_dashboards


# ---------------------------------------------------------------------------
# Extremo a extremo con el arnés offline (app.py real, Power BI/Ollama falsos)
# ---------------------------------------------------------------------------

_SYSTEM = {}


def system():
    if "s" not in _SYSTEM:
        from tests.sim import harness
        _SYSTEM["s"] = (harness, harness.build_engine())
    return _SYSTEM["s"]


def test_e2e_metric_clarification_buttons_then_select():
    harness, (engine, cm, formatter, *_rest) = system()
    harness.new_conversation(engine, cm)
    first, ui = harness.ask(engine, cm, formatter, "¿Cuántas cirugías realizadas hubo en 2024?")
    assert first["status"] == "needs_clarification"
    buttons = clarification_buttons(first)
    assert len(buttons) == 3 and buttons[-1]["id"] == NONE_OF_THE_ABOVE_ID
    assert len({b["label"] for b in buttons}) == 3, buttons
    # Descripción redactada por el LLM (falso) en la simulación.
    assert all(b["caption"].startswith("[FakeLLM]") for b in buttons[:-1]), buttons
    target = next(b for b in buttons if b["id"] == "a_cx_realizadas")
    result = engine.select_clarification_option(target["id"])
    assert result["status"] in ("success", "empty_result")
    assert result["query_plan"]["metric"]["metric_id"] == "a_cx_realizadas"
    assert result["query_plan"]["semantic_model"] == "Atenciones Institucionales"
    harness.new_conversation(engine, cm)


def test_e2e_none_of_the_above_offers_other_metrics_and_reasoning():
    from src.chatbot.reasoning_trace import format_reasoning_text
    harness, (engine, cm, formatter, *_rest) = system()
    harness.new_conversation(engine, cm)
    first, ui = harness.ask(engine, cm, formatter, "¿Cuántas cirugías realizadas hubo en 2024?")
    shown = [o["id"] for o in first["clarification_options"]]
    text = format_reasoning_text(first["reasoning"], ui)
    assert "Indicadores evaluados" in text and "puntaje" in text, text
    assert "Descripción de las opciones con el LLM" in text, text
    other = engine.select_clarification_option(NONE_OF_THE_ABOVE_ID)
    if other["status"] == "needs_clarification":
        assert not set(shown) & {o["id"] for o in other["clarification_options"]}, other
    else:
        assert other["status"] == "not_found" and other["answer"], other
    assert other["reasoning"]["steps"][0]["title"] == "El usuario descartó las opciones ofrecidas"
    harness.new_conversation(engine, cm)


def test_builder_alternatives_exclude_shown_metrics():
    harness, (engine, *_rest) = system()
    builder = engine.query_plan_builder
    question = "¿Cuántas cirugías hubo?"
    first = builder.alternative_metrics(question)
    assert first, "debe haber indicadores relacionados con cirugías"
    ids = [item["metric"]["metric_id"] for item in first]
    rest = builder.alternative_metrics(question, exclude_ids=ids[:1])
    assert ids[0] not in [item["metric"]["metric_id"] for item in rest]
    assert all(not key.startswith("_") for item in rest for key in item)


def test_e2e_dashboard_clarification_shows_real_question_and_button_reruns():
    harness, (engine, cm, formatter, *_rest) = system()
    harness.new_conversation(engine, cm)
    first, ui = harness.ask(engine, cm, formatter, "¿Qué muestra el tablero de atenciones?")
    assert first["status"] == "needs_clarification"
    assert ui.startswith("¿A qué tablero"), ui
    assert first["clarification_type"] == "dashboard"
    buttons = clarification_buttons(first)
    assert buttons, first
    result = engine.select_clarification_option(buttons[0]["id"])
    assert result["status"] == "success" and result["route"] == "rag", result
    assert result["dashboard"] == buttons[0]["id"]
    harness.new_conversation(engine, cm)


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

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


def test_typed_ordinals():
    for text, expected in [("la primera", "q_cx"), ("el segundo", "a_cx"), ("primera opción", "q_cx"),
                           ("la tercera", "q_prog"), ("la última", "q_prog"), ("Quiero la segunda", "a_cx"),
                           ("la 2da opcion", "a_cx")]:
        result, builder = typed(text)
        assert result["status"] == "success" and builder.calls[-1]["selected"] == expected, (text, result)
        titles = [step["title"] for step in result["reasoning"]["steps"]] if "reasoning" in result else []
        assert not titles or "La respuesta es un ordinal" in titles
    # Fuera de rango: no adivina, vuelve a preguntar.
    result, builder = typed("la cuarta")
    assert result["status"] == "needs_clarification" and not builder.calls
    # Una palabra de una etiqueta no es un ordinal: «primera» con «Primera vez».
    engine, _ = make_engine()
    choices = [{"id": "a", "label": "Consulta de control"}, {"id": "b", "label": "Primera vez"}]
    assert engine._match_query_plan_choice("primera", choices)["id"] == "b"
    assert engine._match_query_plan_choice("la primera", choices)["id"] == "a"


def test_ordinal_choice_index_helper():
    from src.chatbot.intent_parser import ordinal_choice_index
    assert ordinal_choice_index("la primera", 3) == 0
    assert ordinal_choice_index("el tercero", 3) == 2
    assert ordinal_choice_index("la ultima", 4) == 3
    assert ordinal_choice_index("segunda opcion por favor", 2) == 1
    assert ordinal_choice_index("la quinta", 3) is None
    assert ordinal_choice_index("la primera cirugia", 3) is None
    assert ordinal_choice_index("primera vez que", 3) is None
    assert ordinal_choice_index("", 3) is None


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
        # Una llamada por opción: responde según el indicador del prompt.
        def __init__(self, answers, status="success"):
            self.answers, self.status, self.prompts = answers, status, []

        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            self.prompts.append(prompt)
            answer = next((a for key, a in self.answers.items() if key in prompt), None)
            return {"status": self.status, "answer": answer, "model": "fake"}

    options = [{"id": "a", "label": "Total cirugías", "measure": "Total Cirugias",
                "dax_expression": "COUNTROWS(CIRUGIAS)", "report": "Tablero Quirúrgico"},
               {"id": "b", "label": "Cirugías programadas"}]
    provider = Provider({
        "Total cirugías": "1. **Cuenta todas las cirugías** del tablero. Está en Inicio.",
        "Cirugías programadas": "El indicador Cirugías programadas cuenta las agendadas\nnota",
    })
    outcome = OptionDescriber(provider).describe("¿cuántas cirugías en marzo?", options)
    assert outcome["status"] == "success"
    assert outcome["descriptions"] == {
        "a": "Cuenta todas las cirugías del tablero.",
        "b": "Cuenta las agendadas",
    }, outcome
    assert len(provider.prompts) == 2
    # La pregunta no se envía: sesgaba al modelo a describir todas igual.
    assert all("marzo" not in prompt for prompt in provider.prompts)
    assert any("Expresión DAX: COUNTROWS(CIRUGIAS)" in prompt for prompt in provider.prompts)
    # Misma frase para dos opciones: se distinguen por su DAX.
    twins = [
        {"id": "t", "label": "TOTAL CIRUGÍAS", "dax_expression": "COUNTROWS(CIRUGIAS)"},
        {"id": "r", "label": "CIRUGÍAS REALIZADAS",
         "dax_expression": "CALCULATE(COUNTROWS(PROGRAMACION), PROGRAMACION[ESTADO] = \"REALIZADA\")"},
    ]
    same = OptionDescriber(Provider({"CIRUG": "Muestra el número de cirugías."})).describe("x", twins)
    assert same["descriptions"] == {
        "t": "Muestra el número de cirugías (tabla CIRUGIAS).",
        "r": "Muestra el número de cirugías (tabla PROGRAMACION, ESTADO = REALIZADA).",
    }, same
    partial = OptionDescriber(Provider({"Total cirugías": "Cuenta todo."})).describe("x", options)
    assert partial["status"] == "partial" and list(partial["descriptions"]) == ["a"]
    down = OptionDescriber(Provider({}, "ollama_error")).describe("x", options)
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
# Seguimiento («¿y en 2025?») con un planificador falso
# ---------------------------------------------------------------------------

class FollowupBuilder(FakeBuilder):
    """Interpreta año, especialidad y «por especialidad» del texto."""

    def metric_words(self, question):
        return [w for w in question.lower().split() if w in ("peso", "programadas")]

    def build(self, question, intent_result=None, selected_metric_id=None):
        import re as _re
        plan = super().build(question, intent_result, selected_metric_id)
        text = question.lower()
        filters, group_by = [], []
        for year in _re.findall(r"20\d\d", text):
            filters.append({"type": "categorical", "table": "Calendario", "column": "AÑO",
                            "value": int(year), "temporal": "year", "source": "query_plan_temporal"})
        for value in ("urologia", "ortopedia"):
            if value in text:
                filters.append({"type": "categorical", "table": "QX", "column": "ESPECIALIDAD",
                                "value": value.upper(), "source": "query_plan_implicit_value"})
        if "por especialidad" in text:
            group_by.append({"table": "QX", "column": "ESPECIALIDAD", "label": "especialidad"})
        return {**plan, "status": "ready", "filters": filters, "group_by": group_by,
                "mode": "grouped" if group_by else "scalar"}


def followup_engine():
    engine, _ = make_engine()
    builder = FollowupBuilder()
    engine.query_plan_builder = builder
    engine._pending_query_plan = {
        "type": "query_plan_metric", "question": "cirugias programadas de urologia en 2024",
        "choices": [{"id": "q_prog", "label": "CIRUGÍAS PROGRAMADAS"}], "excluded": [],
    }
    first = engine.select_clarification_option("q_prog")
    assert first["status"] == "success", first
    return engine, builder


def test_followup_inherits_metric_and_filters_and_survives_reset():
    engine, builder = followup_engine()
    engine.reset()  # app.py::reset_if_finished tras cada respuesta final
    result = engine.process("¿y en 2025?")
    assert result["status"] == "success", result
    assert builder.calls[-1] == {"question": "en 2025", "selected": "q_prog"}
    values = [(f["column"], f["value"]) for f in result["filters"]]
    assert values == [("ESPECIALIDAD", "UROLOGIA"), ("AÑO", 2025)], values
    titles = [step["title"] for step in result["reasoning"]["steps"]]
    assert "Seguimiento de la consulta anterior" in titles
    text = " ".join(line for step in result["reasoning"]["steps"] for line in step["lines"])
    assert "como seguimiento de «cirugias programadas de urologia en 2024»" in text
    assert result["followup_of"]["question"] == "cirugias programadas de urologia en 2024"
    # Encadenado: «y por especialidad» agrupa y deja de filtrar la especialidad.
    grouped = engine.process("y por especialidad")
    assert grouped["result_type"] == "table" and [(f["column"], f["value"]) for f in grouped["filters"]] == [
        ("AÑO", 2025)], grouped["filters"]


def test_followup_is_bounded():
    engine, builder = followup_engine()
    calls = len(builder.calls)
    # No empieza con «y», nombra otro indicador o es largo: no es seguimiento.
    for text in ("en 2025", "y cuantas programadas hubo en 2025",
                 "y en 2025 en la sede norte de la ciudad para la especialidad de urologia"):
        assert engine._followup_plan(text) is None, text
    # Sin período, filtro ni agrupación reconocibles: no es seguimiento.
    assert engine._followup_plan("y la luna?") is None
    assert len(builder.calls) == calls + 1  # solo «y la luna?» llegó a construir un plan
    # Con una contrapregunta pendiente manda la contrapregunta.
    clarify(engine)
    assert engine._followup_plan("y en 2025") is None
    # «Nueva conversación» olvida el contexto.
    engine.reset(full=True)
    assert engine._last_success is None and engine._followup_plan("y en 2025") is None


def test_final_non_powerbi_answer_clears_followup_context():
    engine, _ = followup_engine()
    engine._remember_success({"status": "not_found", "route": "out_of_scope"})
    assert engine._last_success is None
    engine, _ = followup_engine()
    engine._remember_success({"status": "needs_clarification"})
    engine._remember_success({"status": "empty_result", "route": "powerbi"})
    assert engine._last_success is not None


# ---------------------------------------------------------------------------
# Indicador no resuelto: fuera de alcance / genérico / desconocido
# ---------------------------------------------------------------------------

class DescribingBuilder(FakeBuilder):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind

    def describe_unresolved(self, question):
        return {"kind": self.kind, "words": ["gana", "colombia"], "known_words": [],
                "examples": [{"label": "PESO", "report": "Tablero Lavanderia"},
                             {"label": "TOTAL ATENCIONES", "report": "Tablero de Atenciones"}]}


def unresolved(kind):
    engine, _ = make_engine()
    engine.query_plan_builder = DescribingBuilder(kind)
    plan = {"status": "not_found", "question": "cuanto gana un medico",
            "metric_resolution": {"candidates": [], "suggestions": []}}
    return engine._query_plan_failure(plan)


def test_unresolved_metric_messages_distinguish_out_of_scope_and_generic():
    out = unresolved("out_of_scope")
    assert out["status"] == "not_found" and out["route"] == "out_of_scope"
    assert "fuera del alcance" in out["answer"] and "Incluye la sección" not in out["answer"]
    assert "«PESO» (Tablero Lavanderia) o «TOTAL ATENCIONES»" in out["answer"]
    generic = unresolved("generic")
    assert generic["status"] == "metric_not_resolved" and "no menciona un indicador" in generic["answer"]
    unknown = unresolved("unknown")
    assert unknown["status"] == "metric_not_resolved" and "«gana», «colombia»" in unknown["answer"]


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


def test_dashboard_ordinal_reply():
    for reply, expected in (("la primera", "Tablero de Lavandería"), ("el segundo", "Tablero Quirúrgico"),
                            ("la última", "Tablero Quirúrgico")):
        cm = ConversationManager(FakeIntentParser())
        cm.handle_message("¿Qué muestra?")
        result = cm.handle_message(reply)
        assert result["status"] == "ready" and result["dashboard"] == expected, (reply, result)


class FakeRetriever:
    dashboards = ["Tablero Lavanderia", "Tablero Quirurgico", "Tablero de Atenciones Institucionales"]
    dashboard_aliases = {"lavanderia": "Tablero Lavanderia", "tablero de cirugias": "Tablero Quirurgico"}

    def __init__(self, found=None):
        self.found = found or []

    def search(self, question, limit=10):
        return [{"dashboard": name} for name in self.found]


class FakeRegistry:
    sources = [
        {"report": "Tablero de Atenciones Institucionales",
         "aliases": ["atenciones institucionales", "tablero de atenciones"]},
        {"report": "Informe que no está en el RAG", "aliases": ["otro"]},
    ]


def test_intent_parser_detects_dashboard_by_alias_and_typo():
    from src.chatbot.intent_parser import IntentParser
    parser = IntentParser(FakeRetriever(), source_router=FakeRegistry())
    cases = {
        "¿Qué muestra el tablero de lavandería?": "Tablero Lavanderia",
        "que filtros tiene el tablero de atenciones": "Tablero de Atenciones Institucionales",
        "¿Qué muestra el tablero de lavandria?": "Tablero Lavanderia",       # error de tipeo
        "describe el tablero de cirugías": "Tablero Quirurgico",
        "que muestra el Tablero Quirurgico": "Tablero Quirurgico",           # nombre exacto
    }
    for question, expected in cases.items():
        assert parser.detect_dashboard(question) == expected, question
        assert parser.last_dashboard_reason, question
    # Una palabra suelta con error de tipeo y sin «tablero» no fija tablero;
    # tampoco el alias de un informe que no está en el índice RAG.
    assert parser.detect_dashboard("cuantas cirugias hubo") is None
    assert parser.detect_dashboard("que hay en el tablero otro") is None
    parsed = parser.parse("¿Qué muestra el tablero de lavandería?")
    assert parsed.status == "ready" and parsed.dashboard == "Tablero Lavanderia"
    assert parsed.dashboard_reason == "alias del tablero"


def test_intent_parser_single_candidate_does_not_ask():
    from src.chatbot.intent_parser import IntentParser
    parsed = IntentParser(FakeRetriever(found=["Tablero Lavanderia"])).parse("¿Qué muestra el tablero?")
    assert parsed.status == "ready" and parsed.dashboard == "Tablero Lavanderia", parsed
    assert "único" in parsed.dashboard_reason
    several = IntentParser(FakeRetriever(found=["Tablero Lavanderia", "Tablero Quirurgico"]))
    parsed = several.parse("¿Qué muestra el tablero?")
    assert parsed.status == "needs_clarification" and len(parsed.candidate_dashboards) == 2


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
    # Sin nombrar el tablero («tablero de atenciones» ya es un alias).
    first, ui = harness.ask(engine, cm, formatter, "¿Qué muestra el tablero?")
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
# Resolución del indicador: opciones distinguibles, «el de X», mensajes
# ---------------------------------------------------------------------------

def _hidden_metric(metric_id, label, model):
    """Medida técnica sin visual (sin informe ni página), como en el modelo real."""
    return {"metric_id": metric_id, "label": label, "measure": label, "semantic_model": model,
            "report": None, "reports": [], "table": "Calendario", "appearances": []}


class PickingBuilder(FakeBuilder):
    """Construye el plan de cualquier métrica conocida por id."""

    def __init__(self, metrics):
        super().__init__(alternatives=[])
        self.by_id = {m["metric_id"]: m for m in metrics}

    def build(self, question, intent_result=None, selected_metric_id=None):
        self.calls.append({"question": question, "selected": selected_metric_id})
        chosen = self.by_id[selected_metric_id]
        return {"status": "ready", "mode": "scalar", "question": question,
                "semantic_model": chosen["semantic_model"], "report": chosen.get("report"),
                "dashboard": None, "metric": chosen, "filters": [], "group_by": []}


def test_labels_equal_without_accents_or_underscores_are_disambiguated():
    total = metric("c_total", "Total cirugías", "CONSOLIDADO", "CONSOLIDADO", "Cirugías")
    hidden = _hidden_metric("t_total", "TOTAL_CIRUGIAS", "TABLERO DE ATENCIONES INSTITUCIONALES")
    engine, _ = make_engine()
    plan = {"status": "ambiguous", "question": "cuantas cirugias hay",
            "metric_resolution": {"candidates": [
                {"metric": total, "score": 1.0}, {"metric": hidden, "score": 1.0}]}}
    options = engine._query_plan_failure(plan)["clarification_options"]
    labels = [o["label"] for o in options]
    assert labels[0] != labels[1] and "TABLERO DE ATENCIONES INSTITUCIONALES" in labels[1], labels
    # Sin página ni informe, la descripción muestra al menos el modelo.
    lone = engine._query_plan_failure({**plan, "metric_resolution": {"candidates": [
        {"metric": hidden, "score": 1.0}, {"metric": M_NOISE, "score": 1.0}]}})["clarification_options"]
    assert "TABLERO DE ATENCIONES INSTITUCIONALES" in (lone[0]["summary"] + lone[0]["label"]), lone[0]


def test_typed_board_name_selects_the_option():
    referencia = metric("r_t", "TIEMPO PROMEDIO DE RESPUESTA", "REFERENCIA", "TABLERO REFERENCIA", "Inicio")
    factura = metric("f_t", "TIEMPO GESTION FACTURACION", "Control Facturacion",
                     "TABLERO CONTROL FACTURACION", "Escaneo")
    for reply, expected in [("el de referencia", "r_t"), ("la del tablero de facturación", "f_t"),
                            ("el de referencias", "r_t")]:
        engine, builder = make_engine()
        engine.query_plan_builder = PickingBuilder([referencia, factura])
        plan = {"status": "ambiguous", "question": "tiempo promedio de respuesta",
                "metric_resolution": {"candidates": [
                    {"metric": factura, "score": 1.0}, {"metric": referencia, "score": 1.0}]}}
        engine._query_plan_failure(plan)
        result = engine._continue_query_plan(reply)
        assert result["status"] == "success", (reply, result)
        assert engine.query_plan_builder.calls[-1]["selected"] == expected, reply


def test_resolution_reasons_have_their_own_prompt_and_reasoning():
    engine, _ = make_engine()
    engine._trace = None
    same = {"status": "ambiguous", "reason": "same_name_in_several_boards", "question": "triages",
            "resolution_notes": ["«TRIAGES» existe con el mismo nombre en varios tableros"],
            "metric_resolution": {"candidates": [{"metric": M_QUIR, "score": 1}, {"metric": M_ATEN, "score": 1}]}}
    result = engine._query_plan_failure(same)
    assert result["prompt"] == "Ese indicador existe en varios tableros. ¿Cuál necesitas?", result["prompt"]
    outweigh = {"status": "not_found", "reason": "unresolved_words_outweigh_metric", "question": "peso",
                "unresolved_text": "peso", "metric_resolution": {"candidates": [], "suggestions": [
                    {"metric": M_PROG, "score": 0.5}]}}
    result = engine._query_plan_failure(outweigh)
    assert "«peso»" in result["prompt"] and "sin" not in result["prompt"], result["prompt"]
    assert [b["id"] for b in clarification_buttons(result)][-1] == NONE_OF_THE_ABOVE_ID
    # Las decisiones del planificador quedan en el razonamiento del turno.
    traced = engine._traced("question", "triages", lambda: engine._trace_plan(same) or {"status": "x"})
    titles = [step["title"] for step in traced["reasoning"]["steps"]]
    assert "Decisiones al resolver el indicador" in titles, titles


def test_named_board_without_metric_is_not_out_of_scope():
    engine, _ = make_engine()
    engine.query_plan_builder = DescribingBuilder("out_of_scope")
    plan = {"status": "not_found", "question": "cuanto peso hay en lavanderia",
            "named_report": "TABLERO LAVANDERIA",
            "metric_resolution": {"candidates": [], "suggestions": []}}
    result = engine._query_plan_failure(plan)
    assert result["route"] != "out_of_scope", result
    assert result["answer"].startswith("En el tablero TABLERO LAVANDERIA no encontré"), result["answer"]
    # Si el planificador ya decidió que es fuera de alcance, eso manda.
    plan["unresolved_kind"] = "out_of_scope"
    assert engine._query_plan_failure(plan)["route"] == "out_of_scope"


# ---------------------------------------------------------------------------
# Opciones de la contrapregunta (agente opciones-v3)
# ---------------------------------------------------------------------------

def test_single_option_asks_do_you_mean_it_not_several():
    engine, _ = make_engine()
    one = {"status": "ambiguous", "question": "cirugías realizadas",
           "metric_resolution": {"candidates": [{"metric": M_QUIR, "score": 1.0}]}}
    result = engine._query_plan_failure(one)
    assert result["prompt"] == "¿Te refieres a CIRUGÍAS REALIZADAS?", result["prompt"]
    assert "varios" not in result["question"]
    # Sugerencia única tras «no encontré»: también en singular.
    suggestion = {"status": "not_found", "question": "cirugias",
                  "metric_resolution": {"candidates": [], "suggestions": [{"metric": M_PROG, "score": 0.5}]}}
    prompt = engine._query_plan_failure(suggestion)["prompt"]
    assert prompt == "No identifiqué con certeza el indicador. ¿Te refieres a CIRUGÍAS PROGRAMADAS?", prompt
    # Con varias opciones no cambia.
    assert clarify(engine)["prompt"] == "Encontré varios indicadores. ¿Cuál necesitas?"


def test_technical_labels_show_visual_title_or_readable_name_and_keep_id():
    engine, _ = make_engine()
    pend = {**_hidden_metric("f_pend1", "PENDIENTES1", "TABLERO FARMACIA"),
            "appearances": [{"report": "TABLERO FARMACIA", "page_display_name": "INICIO", "visual_title": None}]}
    triage = _hidden_metric("t_tot", "total_triage", "TABLERO DE ATENCIONES INSTITUCIONALES")
    pac = {**_hidden_metric("n_pac", "Pac_act", "TABLERO NAOS"),
           "appearances": [{"report": "TABLERO NAOS", "page_display_name": "Listado",
                            "visual_title": "Pacientes activos con pendientes"}]}
    plain = metric("p_ok", "Total de consultas", "TABLERO EPS", "TABLERO EPS", "Consultas prioritarias")
    plan = {"status": "ambiguous", "question": "pendientes", "metric_resolution": {"candidates": [
        {"metric": m, "score": 1.0} for m in (pend, triage, pac, plain)]}}
    options = engine._query_plan_failure(plan)["clarification_options"]
    assert [o["id"] for o in options] == ["f_pend1", "t_tot", "n_pac", "p_ok"], options
    assert [o["label"] for o in options] == [
        "PENDIENTES", "Total triage", "Pacientes activos con pendientes", "Total de consultas"], options
    # Escribir el nombre técnico sigue eligiendo la opción.
    assert engine._match_query_plan_choice("total_triage", options)["id"] == "t_tot"


class BoardRouter:
    """board_mentions mínimo: conoce el tablero «referencia»."""

    def board_mentions(self, question):
        text = question.lower()
        if text.endswith("referencia"):
            return [{"phrase": "tablero referencia", "name": "referencia", "tokens": ["referencia"],
                     "known": True, "contexts": [{"semantic_model": "TABLERO REFERENCIA",
                                                   "report": "TABLERO REFERENCIA", "name": "REFERENCIA",
                                                   "kind": "report"}]}]
        return []


def test_reply_naming_a_board_without_options_searches_there():
    referencia = metric("r_sol", "CANTIDAD DE SOLICITUDES", "TABLERO REFERENCIA", "TABLERO REFERENCIA", "Inicio")
    factura = metric("f_t", "TIEMPO GESTION FACTURACION", "Control Facturacion",
                     "TABLERO CONTROL FACTURACION", "Escaneo")
    espera = metric("b_t", "TIEMPO EN ESPERA", "BRIEFING", "BRIEFING", "Interconsultas")

    class SearchingBuilder(PickingBuilder):
        def __init__(self, found):
            super().__init__([referencia, factura, espera])
            self.source_router = BoardRouter()
            self.found = found

        def build_composite(self, question, intent_result=None):
            return None

        def build(self, question, intent_result=None, selected_metric_id=None):
            if selected_metric_id is not None:
                return super().build(question, intent_result, selected_metric_id)
            self.calls.append({"question": question, "selected": None})
            if self.found:
                return {"status": "ready", "mode": "scalar", "question": question, "metric": referencia,
                        "semantic_model": "TABLERO REFERENCIA", "report": "TABLERO REFERENCIA",
                        "filters": [], "group_by": [], "notes": []}
            return {"status": "not_found", "question": question, "named_report": "TABLERO REFERENCIA",
                    "metric_resolution": {"candidates": [], "suggestions": [{"metric": factura, "score": 1.0}]}}

    def ask(found):
        engine, _ = make_engine()
        engine.query_plan_builder = SearchingBuilder(found)
        plan = {"status": "ambiguous", "question": "tiempo promedio de respuesta",
                "metric_resolution": {"candidates": [
                    {"metric": espera, "score": 1.0}, {"metric": factura, "score": 1.0}]}}
        engine._query_plan_failure(plan)
        return engine, engine._continue_query_plan("el de referencia")

    # Allí tampoco está (solo ofrecería el de otro tablero): se dice y se re-ofrecen las opciones.
    engine, result = ask(found=False)
    assert result["status"] == "needs_clarification", result
    assert result["prompt"].startswith("Ninguna de las opciones es del TABLERO REFERENCIA."), result["prompt"]
    assert "Indica el número" not in result["prompt"]
    assert [o["id"] for o in result["clarification_options"]] == ["b_t", "f_t"]
    assert engine.query_plan_builder.calls[-1]["question"].endswith("en el tablero REFERENCIA")
    assert engine._pending_query_plan is not None  # se puede seguir eligiendo
    # Existe en ese tablero: se responde y la respuesta lo dice.
    engine, result = ask(found=True)
    assert result["status"] == "success", result
    assert result["query_plan"]["notes"][0].startswith("Ninguna de las opciones es del TABLERO REFERENCIA")
    # Una respuesta que nombra el tablero de una opción la elige (no busca en otro lado).
    engine, _ = make_engine()
    engine.query_plan_builder = SearchingBuilder(False)
    engine._query_plan_failure({"status": "ambiguous", "question": "tiempo", "metric_resolution": {
        "candidates": [{"metric": referencia, "score": 1.0}, {"metric": factura, "score": 1.0}]}})
    assert engine._continue_query_plan("el de referencia")["status"] == "success"
    assert engine.query_plan_builder.calls[-1]["selected"] == "r_sol"


def test_new_resolution_reasons_have_their_prompts():
    engine, _ = make_engine()
    candidates = [{"metric": M_QUIR, "score": 1}, {"metric": M_ATEN, "score": 1}]
    similar = {"status": "ambiguous", "reason": "similar_name_in_several_boards", "question": "imagenes",
               "metric_resolution": {"candidates": candidates}}
    assert engine._query_plan_failure(similar)["prompt"].startswith("Hay varios indicadores con un nombre casi igual")
    board = {"status": "ambiguous", "reason": "options_from_named_board", "named_report": "TABLERO NAOS",
             "question": "pendientes en naos", "metric_resolution": {"candidates": candidates}}
    assert "del tablero TABLERO NAOS" in engine._query_plan_failure(board)["prompt"]
    elsewhere = {"status": "ambiguous", "reason": "metric_not_in_named_report", "named_report": "TABLERO NAOS",
                 "question": "x en naos", "source_context": {"semantic_model": "TABLERO NAOS"},
                 "metric_resolution": {"candidates": candidates}}
    assert "Estos son los más parecidos de otros tableros" in engine._query_plan_failure(elsewhere)["prompt"]


# --- QueryPlanBuilder real con un catálogo mínimo ---------------------------

OPT_ATEN, OPT_BRIEF, OPT_NAOS, OPT_CITAS = "ATENCIONES", "BRIEFING", "TABLERO NAOS", "ASIGNACION CITAS"
OPT_CAMAS, OPT_FACT, OPT_EPS, OPT_EXT = "GESTION CAMAS", "CONTROL FACTURACION", "TABLERO EPS", "CONSULTA EXTERNA"


def _opt_metric(metric_id, model, label, table, pages=(), titles=None, dax=None):
    visible = bool(pages)
    return {
        "metric_id": metric_id, "label": label, "measure": label, "aliases": [label],
        "semantic_model": model, "report": model if visible else None, "reports": [model] if visible else [],
        "table": table, "dax_expression": dax or f"[{label}]", "validation_status": "approved",
        "appearances": [
            {"report": model, "page_display_name": page, "visual_id": f"{metric_id}_{i}",
             "visual_title": (titles or {}).get(page, label)}
            for i, page in enumerate(pages)
        ],
    }


OPTION_METRICS = [
    _opt_metric("a_total_triage", OPT_ATEN, "total_triage", "OPORTUNIDAD_TRIAGE"),
    _opt_metric("a_total_triages", OPT_ATEN, "TOTAL_TRIAGES", "OPORTUNIDAD_TRIAGE"),
    _opt_metric("a_imagenes", OPT_ATEN, "IMAGENES", "CONSOLIDADO_IMAGENES"),
    _opt_metric("a_observados_mes", OPT_ATEN, "PACIENTES OBSERVADOS POR MES", "CONSULTAS PRIORITARIAS",
                pages=["Consultas prioritarias"], dax="COUNT('CONSULTAS PRIORITARIAS'[ASEGURADOR])",
                titles={"Consultas prioritarias": "PACIENTES OBSERVADOS"}),
    _opt_metric("a_observados_2025", OPT_ATEN, "OBSERVADOS_2025", "OBSERVADOS"),
    _opt_metric("a_prioritarias_2025", OPT_ATEN, "PRIORITARIAS_2025", "CONSULTA_URGENCIAS"),
    _opt_metric("b_imagenes_tomadas", OPT_BRIEF, "IMAGENES TOMADAS", "IMAGENES_TOMADAS",
                pages=["Imagenes diagnosticas"]),
    _opt_metric("n_pacientes", OPT_NAOS, "Total de pacientes con pendientes activos", "PACIENTES",
                pages=["NAOS listado"]),
    _opt_metric("n_cirugias", OPT_NAOS, "Total de cirugías pendientes", "NAOS_CIRUGIAS_PENDIENTES",
                pages=["NAOS cirugias pendientes"]),
    _opt_metric("c_pendiente", OPT_CITAS, "%PENDIENTE", "CITAS_ASIGNADAS", pages=["Oferta especialidades"]),
    _opt_metric("c_citas_asignadas", OPT_CITAS, "CITAS ASIGNADAS", "AGENDA_ESPECIALISTAS", pages=["Dispo"]),
    _opt_metric("c_asignadas", OPT_CITAS, "ASIGNADAS", "CITAS_ASIGNADAS", pages=["Dispo"]),
    _opt_metric("k_ocupacion", OPT_CAMAS, "% Ocupación", "OCUPACION", pages=["Ocupacion"],
                titles={"Ocupacion": "Ocupación por servicio"}),
    _opt_metric("f_tiempo_prom", OPT_FACT, "TIEMPO PROMEDIO GESTION FACTURA", "FACTURACION PERFILES",
                pages=["Escaneo fotocopias"], dax="AVERAGE('FACTURACION PERFILES'[TIEMPO])"),
    _opt_metric("f_tiempo", OPT_FACT, "TIEMPO GESTION FACTURACION", "FACTURACION PERFILES",
                pages=["Escaneo fotocopias", "Estacion enfermeria", "Urgencias"],
                dax="AVERAGE('FACTURACION PERFILES'[TIEMPO])"),
    _opt_metric("e_consultas", OPT_EPS, "Total de consultas", "CONSULTAS_PRIORITARIAS",
                pages=["Consultas prioritarias"], titles={"Consultas prioritarias": "Consultas"}),
    _opt_metric("x_consultas", OPT_EXT, "Consultas", "CONSULTAS_EXTERNAS", pages=["Consulta externa"]),
]

_OPTIONS_STATE = {}


def options_builder():
    """QueryPlanBuilder real sobre un catálogo temporal mínimo (sin Power BI real)."""
    if "builder" in _OPTIONS_STATE:
        return _OPTIONS_STATE["builder"]
    import json
    import tempfile
    from src.semantic.query_plan_builder import QueryPlanBuilder
    from src.semantic.source_model_router import SourceModelRouter

    tmp = tempfile.TemporaryDirectory()
    _OPTIONS_STATE["tmp"] = tmp
    root = Path(tmp.name)
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    models = [OPT_ATEN, OPT_BRIEF, OPT_NAOS, OPT_CITAS, OPT_CAMAS, OPT_FACT, OPT_EPS, OPT_EXT]
    keys = {model: f"m{i}" for i, model in enumerate(models)}
    sources = [{"source_group": keys[m], "report": m, "semantic_model": m, "default_dashboard": "Inicio",
                "aliases": [m.lower()] + (["naos"] if m == OPT_NAOS else []),
                "technical_catalog": f"data/catalog/{keys[m]}_rag.json"} for m in models]
    registry = {"models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                            "technical_catalog": s["technical_catalog"]} for s in sources],
                "sources": sources}
    tables = {OPT_NAOS: [{"name": "PACIENTES", "columns": [{"name": "SERVICIO", "data_type": "String"}]}]}
    field = {"role": "Values", "kind": "column", "table": "PACIENTES", "column": "SERVICIO",
             "display_name": "SERVICIO", "native_query_ref": "SERVICIO", "query_ref": "PACIENTES.SERVICIO"}
    visuals = {"schema_version": 2, "reports": [
        {"report": OPT_NAOS, "semantic_model": OPT_NAOS, "source_group": keys[OPT_NAOS], "pages": [
            {"page_name": "p1", "page_display_name": "NAOS listado", "filters": {}, "visuals": [
                {"visual_id": "n_serv", "visual_type": "slicer", "fields": [field]}]}]}]}
    files = {catalog / "source_registry.json": registry, rag / "visual_metrics_catalog.json": visuals,
             rag / "master_metrics.json": {"metrics": OPTION_METRICS}}
    for model in models:
        files[catalog / f"{keys[model]}_rag.json"] = {"semantic_model": model, "tables": tables.get(model, [])}
    for path, data in files.items():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    class Provider:
        def execute_dax(self, dax, semantic_model=None):
            if "VALUES('PACIENTES'[SERVICIO])" in dax.replace(" ", ""):
                return {"status": "success", "rows": [{"[Value]": "CIRUGIA"}, {"[Value]": "PEDIATRIA"}]}
            return {"status": "success", "rows": []}

    router = SourceModelRouter(catalog / "source_registry.json", rag / "visual_metrics_catalog.json",
                               project_root=root)
    _OPTIONS_STATE["builder"] = QueryPlanBuilder(
        rag / "master_metrics.json", rag / "visual_metrics_catalog.json", router, Provider(), project_root=root,
    )
    return _OPTIONS_STATE["builder"]


def _option_ids(plan):
    resolution = plan.get("metric_resolution") or {}
    return [item["metric"]["metric_id"] for item in resolution.get("candidates") or resolution.get("suggestions") or []]


def test_builder_single_option_after_grouping_is_answered_and_noted():
    plan = options_builder().build("dame el total de triages del tablero atenciones")
    assert plan["status"] == "ready", (plan["status"], _option_ids(plan))
    assert plan["metric"]["metric_id"] in ("a_total_triage", "a_total_triages")
    assert any("única opción" in note for note in plan.get("resolution_notes") or []), plan.get("resolution_notes")


def test_builder_named_board_options_come_from_that_board():
    plan = options_builder().build("pacientes con pendientes en naos por servicio")
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"), _option_ids(plan))
    assert plan["metric"]["metric_id"] == "n_pacientes"
    assert [g["column"] for g in plan["group_by"]] == ["SERVICIO"], plan["group_by"]
    assert any("tablero nombrado" in note for note in plan["resolution_notes"]), plan["resolution_notes"]


def test_builder_prunes_options_without_the_distinctive_words():
    plan = options_builder().build("consultas prioritarias de 2025")
    assert plan["status"] == "ambiguous", plan["status"]
    assert set(_option_ids(plan)) == {"e_consultas", "a_prioritarias_2025"}, _option_ids(plan)
    scores = {item["score"] for item in plan["metric_resolution"]["candidates"]}
    assert len(scores) == 1, scores  # la pregunta no decide entre ellas: se muestran todas
    assert any("opciones depuradas" in note for note in plan["resolution_notes"])


def test_builder_similar_names_in_other_tables_are_asked():
    builder = options_builder()
    imagenes = builder.build("cuantas imagenes se tomaron")
    assert imagenes["status"] == "ambiguous" and imagenes["reason"] == "similar_name_in_several_boards", \
        (imagenes["status"], imagenes.get("reason"))
    assert set(_option_ids(imagenes)) == {"b_imagenes_tomadas", "a_imagenes"}, _option_ids(imagenes)
    observados = builder.build("cuantos pacientes observados hay")
    assert observados.get("reason") == "similar_name_in_several_boards", observados["status"]
    assert set(_option_ids(observados)) == {"a_observados_mes", "a_observados_2025"}, _option_ids(observados)
    # Tarjetas parecidas del MISMO tablero no se preguntan.
    citas = builder.build("citas asignadas")
    assert citas["status"] == "ready" and citas["metric"]["metric_id"] == "c_citas_asignadas", citas["status"]
    # Nombrando el tablero tampoco.
    named = builder.build("cuantas imagenes se tomaron en el tablero briefing")
    assert named["status"] == "ready" and named["metric"]["metric_id"] == "b_imagenes_tomadas", named["status"]


def test_same_measure_on_several_pages_is_answered_once_with_its_pages():
    builder = options_builder()
    plan = builder.build("tiempo promedio gestion factura")
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"), _option_ids(plan))
    engine, _ = make_engine()
    engine.query_plan_builder = builder
    engine._note_same_measure_pages(plan)
    note = plan["notes"][-1]
    assert note.startswith("Este indicador aparece en 3 páginas del tablero CONTROL FACTURACION"), note
    for page in ("Escaneo fotocopias", "Estacion enfermeria", "Urgencias"):
        assert page in note, note
    # Una medida en una sola página no lleva la nota.
    single = builder.build("citas asignadas")
    engine._note_same_measure_pages(single)
    assert not single.get("notes"), single.get("notes")


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

"""
Pruebas de humo del chatbot contra el Power BI / Ollama / Qdrant SIMULADOS.

Funciona de dos formas:
  python -m tests.sim.test_smoke      # runner propio: PASS / FAIL / XFAIL / XPASS
  pytest tests/sim/test_smoke.py      # si algún día se instala pytest

Los tests marcados con @xfail("motivo") describen comportamiento DESEADO que hoy
falla por un bug real del proyecto (no se corrige aquí). Cuando uno empiece a
pasar, el runner lo reporta como XPASS para que se quite la marca.
"""
import json
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

sys.dont_write_bytecode = True

from . import harness
from .cases import CASES

try:  # pytest es opcional
    import pytest as _pytest
except Exception:  # pragma: no cover
    _pytest = None


def xfail(reason):
    """Marca un test como fallo esperado (mapea a pytest.mark.xfail si pytest existe)."""
    def decorator(fn):
        fn.__xfail_reason__ = reason
        if _pytest is not None:
            return _pytest.mark.xfail(reason=reason, strict=False)(fn)
        return fn
    return decorator


# ----------------------------------------------------------------------------
# Infraestructura compartida (un sistema por combinación ollama/powerbi)
# ----------------------------------------------------------------------------

_SYSTEMS = {}
_RUNS = {}
GENERIC_CLARIFICATION = "Necesito una aclaración para continuar."
MODEL_FILE = harness.DEFAULT_SIM_ROOT / "powerbi_model.json"


def system(ollama_up=True, powerbi_up=True):
    key = (ollama_up, powerbi_up)
    if key not in _SYSTEMS:
        _SYSTEMS[key] = harness.build_engine(ollama_up=ollama_up, powerbi_up=powerbi_up)
    return _SYSTEMS[key]


def run(case_name):
    """Corre (una sola vez) un caso del archivo cases.py. -> [(texto, result, ui)]."""
    if case_name not in _RUNS:
        engine, cm, formatter, *_ = system()
        _RUNS[case_name] = harness.run_case(CASES[case_name], engine, cm, formatter)
    return _RUNS[case_name]


def last(case_name):
    _, result, ui = run(case_name)[-1]
    return result, ui


def all_turns():
    for name in CASES:
        for text, result, ui in run(name):
            yield name, text, result, ui


def dax_of(result):
    return result.get("dax") or " ".join(q["dax"] for q in result["_sim"]["dax_log"])


def lav_rows():
    model = json.loads(MODEL_FILE.read_text(encoding="utf-8"))
    return model["models"]["Lavanderia"]["data"]["LAVANDERIA"]


def lav_sum(servicio=None, year=2026, month=1, turno=None):
    total = 0
    for r in lav_rows():
        d = datetime.fromisoformat(r["Fecha"])
        if (d.year, d.month) != (year, month):
            continue
        if servicio and r["SERVICIO"] != servicio:
            continue
        if turno and r["Turno"] != turno:
            continue
        total += round(r["Peso"] * 10)
    return total / 10


def num_in(text, number):
    """True si `number` (p. ej. 1382.8) aparece en el texto (1382.8, 1382,8 o 1.382,8)."""
    s = f"{number:.1f}".rstrip("0").rstrip(".") if isinstance(number, float) else str(number)
    integer, _, decimals = s.partition(".")
    grouped = f"{int(integer):,}".replace(",", ".") + (f",{decimals}" if decimals else "")
    return s in text or s.replace(".", ",") in text or grouped in text


# ----------------------------------------------------------------------------
# Arnés y fixtures
# ----------------------------------------------------------------------------

def test_harness_builds_and_never_loads_dotenv():
    import sys as _sys
    engine, cm, formatter, ollama_status, pbi, dax_log = system()
    assert ollama_status["status"] == "ready", ollama_status
    assert pbi["status"] == "success", pbi
    assert getattr(_sys.modules["dotenv"], "__sim_fake__", False), "dotenv debe estar stubbeado (.env jamás se lee)"
    assert isinstance(dax_log, list)


def test_lavanderia_fixture_numbers():
    assert lav_sum("ANTIFLUIDOS", 2026, 1) == 488.3
    assert lav_sum(None, 2026, 1) == 3906.4
    assert round(100 * lav_sum("ANTIFLUIDOS", 2026, 1) / lav_sum(None, 2026, 1), 1) == 12.5
    assert lav_sum(None, 2025, 1) != lav_sum(None, 2026, 1), "debe haber datos de otros meses/años"
    assert lav_sum(None, 2025, 6) > 0


def test_harness_reports_dax_and_result_in_log():
    result, _ = last("lav_q3")
    log = result["_sim"]["dax_log"]
    assert log and log[-1]["result"] == [[488.3]], log
    assert log[-1]["type_mismatch"] == []


def test_powerbi_down_does_not_crash():
    engine, cm, formatter, ollama_status, pbi, _ = system(powerbi_up=False)
    assert pbi["status"] != "success"
    harness.new_conversation(engine, cm)
    result, ui = harness.ask(engine, cm, formatter, CASES["lav_q3"]["turns"][0])
    assert result["_sim"]["exception"] is None, result["_sim"]["traceback"]
    assert result["status"] != "success" and "488" not in ui


def test_ollama_down_rag_falls_back_to_extractive():
    engine, cm, formatter, ollama_status, pbi, _ = system(ollama_up=False)
    assert ollama_status["status"] != "ready"
    harness.new_conversation(engine, cm)
    result, ui = harness.ask(engine, cm, formatter, "¿Qué significa el indicador cirugías programadas?")
    assert result["_sim"]["exception"] is None, result["_sim"]["traceback"]
    assert result["route"] == "rag" and result["status"] == "success"
    assert "[FakeLLM]" not in ui


# ----------------------------------------------------------------------------
# Casos base (prototipo)
# ----------------------------------------------------------------------------

def test_base_grouped_by_sede():
    result, ui = last("base_dato_agrupado")
    assert result["status"] == "success" and result["route"] == "powerbi"
    assert "SEDE NORTE" in ui and "SEDE SUR" in ui and "SEDE PRINCIPAL" in ui


def test_base_out_of_scope():
    result, ui = last("base_fuera_de_alcance")
    assert result["status"] == "not_found" and result["route"] == "out_of_scope"


def test_base_ambiguous_question_asks_for_specificity():
    # «¿Cuántas cirugías hay?» no nombra un indicador concreto: en lugar de
    # «no encontré» se ofrecen los indicadores de cirugías como opciones.
    result, ui = last("base_ambigua")
    assert result["status"] == "needs_clarification", result["status"]
    ids = [o["id"] for o in result["clarification_options"]]
    assert ids[0] == "b_total_cx", ids
    assert {"b_cx_programadas", "a_cx_realizadas", "b_cx_realizadas"} <= set(ids), ids
    assert "b_cx_canceladas" not in ids  # pendiente de revisión
    assert "indicador" in ui


def test_base_ambiguous_metric_offers_options_and_resolves_by_number():
    (_, first, ui1), (_, second, ui2) = run("base_dato_aclaracion")
    assert first["status"] == "needs_clarification"
    assert len(first["clarification_options"]) == 2
    # La interfaz muestra solo la pregunta (las opciones van en botones); la
    # lista numerada se conserva en `question` para quien responde escribiendo.
    assert "1." not in ui1 and "1." in first["question"], ui1
    # La selección fija la métrica; el valor puede venir vacío (BLANK) por el
    # bug de DATE() vs columna entera, que ahora se informa como empty_result.
    assert second["status"] in ("success", "empty_result") and second["route"] == "powerbi"
    assert second["query_plan"]["metric"]["metric_id"] == "b_cx_realizadas"


def test_request_words_and_typos_are_not_filters():
    # «necsito saber ...» no es un valor de dimensión: antes detenía la consulta.
    result, ui = last("req_necesito_typo")
    assert result["status"] == "success", (result["status"], ui)
    assert result["query_plan"]["metric"]["metric_id"] == "b_total_cx"
    assert [(f["column"], f["value"]) for f in result["filters"]] == [("AÑO", 2024)]
    assert not result["query_plan"].get("unapplied_terms"), result["query_plan"]


def test_unspecific_metric_offers_suggestions_then_resolves_by_number():
    (_, first, ui1), (_, second, ui2) = run("req_sugerencias")
    assert first["status"] == "needs_clarification", (first["status"], ui1)
    assert first["clarification_options"][0]["id"] == "b_total_cx"
    assert "No encontré" not in ui1 and "1." not in ui1, ui1
    assert second["status"] == "success", (second["status"], ui2)
    assert second["query_plan"]["metric"]["metric_id"] == "b_total_cx"
    assert [(f["column"], f["value"]) for f in second["filters"]] == [("AÑO", 2024)]


def test_unknown_word_asks_to_query_without_it():
    (_, first, ui1), (_, second, ui2) = run("req_palabra_no_entendida")
    assert first["status"] == "needs_clarification", (first["status"], ui1)
    assert "azules" in ui1
    assert [o["id"] for o in first["clarification_options"]] == ["b_total_cx"]
    assert second["status"] == "success", (second["status"], ui2)
    assert [(f["column"], f["value"]) for f in second["filters"]] == [("AÑO", 2024)]


def test_abandoned_suggestions_do_not_hijack_new_question():
    (_, first, _), (_, second, ui2) = run("req_sugerencias_abandonadas")
    assert first["status"] == "needs_clarification"
    assert second["status"] == "not_found", (second["status"], ui2)


def test_base_definition_goes_to_rag():
    result, ui = last("base_definicion_rag")
    assert result["route"] == "rag" and result["status"] == "success"


# ----------------------------------------------------------------------------
# Tablero Lavandería (chat real)
# ----------------------------------------------------------------------------

def test_lav_q3_peso_servicio_mes():
    """Hoy ya responde bien: 'PESO: 488.3'."""
    result, ui = last("lav_q3")
    assert result["status"] == "success" and result["route"] == "powerbi", result.get("route")
    assert result["metric"] == "PESO" and result["semantic_model"] == "Lavanderia"
    assert ui.startswith("**PESO**: 488,3"), ui
    assert "SERVICIO = ANTIFLUIDOS" in ui and "enero 2026" in ui, ui
    dax = dax_of(result)
    assert "SUM('LAVANDERIA'[Peso])" in dax
    assert 'TREATAS({"ANTIFLUIDOS"}, \'LAVANDERIA\'[SERVICIO])' in dax
    assert "DATE(2026, 1, 1)" in dax and "DATE(2026, 2, 1)" in dax
    assert result["_sim"]["type_mismatch"] == []


def test_lav_control_grouped_by_servicio_adds_up():
    """Control positivo: el agrupado por servicio ya funciona y suma 3906.4 (base de la participación)."""
    result, ui = last("lav_por_servicio")
    assert result["status"] == "success"
    assert num_in(ui, 488.3)
    rows = result["_sim"]["dax_log"][-1]["result"]
    assert round(sum(r[1] for r in rows), 1) == 3906.4
    assert round(100 * dict(rows)["ANTIFLUIDOS"] / 3906.4, 1) == 12.5


def test_lav_q1_answers_peso_and_participacion():
    result, ui = last("lav_q1")
    assert result["route"] == "powerbi", f"route={result['route']} (respondió con RAG)"
    assert num_in(ui, 488.3), ui
    assert "12.5" in ui or "12,5" in ui, ui


def test_lav_q2_answers_peso_and_participacion():
    result, ui = last("lav_q2")
    assert result["route"] == "powerbi", f"route={result['route']} (respondió con RAG)"
    assert num_in(ui, 488.3), ui
    assert "12.5" in ui or "12,5" in ui, ui


def test_lav_q4_answers_participacion():
    result, ui = last("lav_q4")
    assert result["route"] == "powerbi", f"route={result['route']} (respondió con RAG)"
    assert "12.5" in ui or "12,5" in ui, ui


def test_lav_q5_telegraphic_peso():
    result, ui = last("lav_q5")
    assert result["route"] == "powerbi", f"route={result['route']} (respondió con RAG)"
    assert "488,3" in ui, ui


def test_lav_q6_breakdown_by_turno():
    result, ui = last("lav_q6")
    assert result["route"] == "powerbi", f"route={result['route']} (respondió con RAG)"
    assert "TURNO_OK" in dax_of(result)
    for etiqueta, turno in (("MAÑANA", 1), ("TARDE", 2), ("NOCHE", 3)):
        assert etiqueta in ui and num_in(ui, lav_sum(None, 2026, 1, turno)), (etiqueta, ui)


def test_lav_control_grouped_by_turno_ok_works():
    """Control positivo: con el nombre técnico TURNO_OK el desglose sí funciona."""
    result, ui = last("lav_por_turno_ok")
    assert result["status"] == "success"
    rows = dict(result["_sim"]["dax_log"][-1]["result"])
    for etiqueta, turno in (("MAÑANA", 1), ("TARDE", 2), ("NOCHE", 3)):
        assert rows[etiqueta] == lav_sum(None, 2026, 1, turno)


# ----------------------------------------------------------------------------
# Tablero por alias, ordinales, seguimiento, ranking y mensajes sin indicador
# ----------------------------------------------------------------------------

def reasoning_text(result):
    return "\n".join(
        " ".join([step.get("title") or "", *[str(line) for line in step.get("lines") or []]])
        for step in (result.get("reasoning") or {}).get("steps") or []
    )


def categorical(result):
    return [(f["column"], f["value"]) for f in result.get("filters") or [] if f.get("type") == "categorical"
            and f.get("source") != "query_plan_temporal"]


def test_dashboard_named_by_alias_does_not_ask():
    for case, dashboard in (("tablero_por_alias", "Tablero de Atenciones Institucionales"),
                            ("tablero_alias_typo", "Tablero Lavanderia")):
        result, ui = last(case)
        assert result["status"] == "success" and result["route"] == "rag", (case, result["status"], ui)
        assert result["dashboard"] == dashboard, (case, result["dashboard"])
        assert "alias del tablero" in reasoning_text(result), case


def test_dashboard_clarification_accepts_ordinal():
    (_, first, _), (_, second, ui2) = run("tablero_ordinal")
    assert first["clarification_type"] == "dashboard"
    expected = first["clarification_options"][1]["id"]
    assert second["route"] == "rag" and second["dashboard"] == expected, (second, ui2)


def test_metric_clarification_accepts_ordinals():
    (_, first, _), (_, second, ui2) = run("ordinal_metrica")
    assert second["status"] in ("success", "empty_result"), (second["status"], ui2)
    assert second["query_plan"]["metric"]["metric_id"] == first["clarification_options"][0]["id"]
    assert "ordinal" in reasoning_text(second)
    (_, first, _), (_, second, ui2) = run("ordinal_ultima")
    assert second["status"] == "success", (second["status"], ui2)
    assert second["query_plan"]["metric"]["metric_id"] == first["clarification_options"][-1]["id"]


def test_common_verbs_are_not_filters():
    result, ui = last("verbo_registrado")
    assert result["status"] == "success" and result["metric"] == "PESO", (result["status"], ui)
    assert not result.get("unapplied_terms"), result.get("unapplied_terms")
    result, ui = last("verbo_llevamos")
    assert result["status"] == "success", (result["status"], ui)
    assert result["query_plan"]["metric"]["metric_id"] == "b_cx_programadas"
    assert not result.get("unapplied_terms"), result.get("unapplied_terms")


def test_business_synonyms_kilos_and_colaborador():
    result, ui = last("sinonimo_kilos")
    assert result["status"] == "success" and result["metric"] == "PESO", (result["status"], ui)
    assert num_in(ui, lav_sum(None, 2026, 1)), ui
    result, ui = last("sinonimo_colaborador")
    assert result["status"] == "success" and result["result_type"] == "table", (result["status"], ui)
    assert [g["column"] for g in result["group_by"]] == ["NOMBRE_COMPLETO"]


def test_count_question_resolves_total_metric_with_filters():
    result, ui = last("conteo_como_total")
    assert result["status"] == "success", (result["status"], ui)
    assert result["query_plan"]["metric"]["metric_id"] == "a_total_atenciones"
    assert set(categorical(result)) == {("SEDE", "SEDE SUR"), ("SERVICIO", "URGENCIAS")}
    assert "se interpretó como «total de" in reasoning_text(result)
    result, ui = last("atenciones_urgencias")
    assert result["route"] == "powerbi" and result["status"] == "success", (result["route"], ui)
    assert categorical(result) == [("SERVICIO", "URGENCIAS")]
    assert "DATE(2024, 1, 1)" in result["dax"]


def test_metric_matched_only_by_grouping_is_not_answered():
    result, ui = last("metrica_sin_respaldo")
    assert result["status"] != "success", (result["status"], ui)
    assert "CIRUG" not in ui.upper() or "por ejemplo" in ui.lower(), ui
    assert "citas" in ui and "Incluye la sección" not in ui, ui
    assert "solo por las palabras de la agrupación" in reasoning_text(result)
    result, ui = last("agrupacion_no_elige_indicador")
    assert result["status"] == "success" and result["query_plan"]["metric"]["metric_id"] == "b_total_cx", ui
    assert [g["column"] for g in result["group_by"]] == ["ESPECIALIDAD"]
    assert "sin la agrupación" in reasoning_text(result)


def test_out_of_scope_and_generic_messages():
    result, ui = last("fuera_alcance_numerico")
    assert result["route"] == "out_of_scope" and result["status"] == "not_found", (result, ui)
    assert "fuera del alcance" in ui and "Incluye la sección" not in ui, ui
    assert not any(ch.isdigit() for ch in ui), ui
    result, ui = last("pregunta_generica")
    assert result["status"] == "metric_not_resolved", (result["status"], ui)
    assert "no menciona un indicador" in ui and "Por ejemplo: «" in ui, ui


def test_ranking_single_top_and_ascending():
    result, ui = last("ranking_servicio")
    assert result["status"] == "success" and result["result_type"] == "table", (result["status"], ui)
    assert [g["column"] for g in result["group_by"]] == ["SERVICIO"]
    assert len(result["rows"]) == 1 and "UCI ADULTOS" in ui, ui
    assert "TOPN(" in result["dax"] and "mayor valor" in ui
    result, ui = last("ranking_menos")
    assert len(result["rows"]) == 1 and "ANTIFLUIDOS" in ui, ui
    assert "ASC" in result["dax"]
    (_, first, ui1), (_, second, ui2) = run("ranking_top")
    assert first["status"] == "needs_clarification" and first["route"] == "clarification", ui1
    assert second["status"] == "success" and len(second["rows"]) == 5, (second["status"], ui2)
    assert [g["column"] for g in second["group_by"]] == ["ESPECIALIDAD"]
    values = [row["[__value]"] for row in second["rows"]]
    assert values == sorted(values, reverse=True), values
    assert "5 primeros" in ui2


def test_followup_reuses_previous_metric_and_filters():
    turns = run("seguimiento")
    (_, first, _), (_, second, ui2), (_, third, ui3), (_, fourth, ui4) = turns
    metric = first["query_plan"]["metric"]["metric_id"]
    assert second["status"] == "success", (second["status"], ui2)
    assert second["query_plan"]["metric"]["metric_id"] == metric
    assert categorical(second) == [("ESPECIALIDAD", "UROLOGIA")]
    assert "2025" in second["dax"] and "2024" not in second["dax"], second["dax"]
    assert "se interpretó «y en 2025?» como seguimiento" in reasoning_text(second)
    # «y por especialidad»: agrupa y deja de filtrar por urología.
    assert third["result_type"] == "table" and [g["column"] for g in third["group_by"]] == ["ESPECIALIDAD"]
    assert categorical(third) == [] and "2025" in third["dax"], third["dax"]
    # «y de ortopedia?»: el filtro nuevo reemplaza la agrupación por especialidad.
    assert fourth["result_type"] == "scalar", ui4
    assert categorical(fourth) == [("ESPECIALIDAD", "ORTOPEDIA Y TRAUMATOLOGIA")]


def test_followup_context_is_bounded():
    (_, _, _), (_, other, _), (_, third, ui3) = run("seguimiento_tras_otro_tema")
    assert other["route"] == "out_of_scope"
    assert third["route"] != "powerbi", (third["route"], ui3)
    (_, _, _), (_, second, ui2) = run("seguimiento_pregunta_nueva")
    assert second["status"] == "success" and second["metric"] == "PESO", (second["status"], ui2)
    assert categorical(second) == [] and "como seguimiento de" not in reasoning_text(second)
    assert "nombra un indicador" in reasoning_text(second)


# ----------------------------------------------------------------------------
# Periodos: rangos, relativos («este año») y agrupación temporal («por mes»)
# ----------------------------------------------------------------------------

def run_on(case_name, today):
    """Corre un caso con la fecha de referencia del Query Plan fijada (sin caché)."""
    engine, cm, formatter, *_ = system()
    builder = engine.query_plan_builder
    previous = builder.today
    builder.today = today
    try:
        return harness.run_case(CASES[case_name], engine, cm, formatter)
    finally:
        builder.today = previous


def lav_total(start, end):
    """Peso de Lavandería con Fecha en [start, end)."""
    total = 0
    for r in lav_rows():
        if start <= datetime.fromisoformat(r["Fecha"]) < end:
            total += round(r["Peso"] * 10)
    return total / 10


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def test_period_month_range_applies_the_whole_range():
    result, ui = last("per_lav_rango_meses")
    assert result["status"] == "success", (result["status"], ui)
    dax = dax_of(result)
    assert "DATE(2025, 1, 1)" in dax and "DATE(2025, 4, 1)" in dax, dax
    assert num_in(ui, lav_total(datetime(2025, 1, 1), datetime(2025, 4, 1))), ui
    assert "Filtros: enero–marzo 2025" in ui and "entre" not in ui, ui


def test_period_this_year_is_relative_to_the_reference_date():
    ((_, result, ui),) = run_on("per_lav_este_anio", date(2026, 3, 20))
    assert result["status"] == "success", (result["status"], ui)
    dax = dax_of(result)
    assert "DATE(2026, 1, 1)" in dax and "DATE(2026, 3, 21)" in dax, dax
    assert num_in(ui, lav_total(datetime(2026, 1, 1), datetime(2026, 3, 21))), ui
    assert "2026 hasta hoy" in ui, ui
    assert "este año" in format_reasoning(result), "el razonamiento debe citar el periodo pedido"


def format_reasoning(result):
    from src.chatbot.reasoning_trace import format_reasoning_text
    return format_reasoning_text(result.get("reasoning"))


def test_period_grouped_by_month_adds_up_to_the_year():
    result, ui = last("per_lav_por_mes_2025")
    assert result["status"] == "success" and result["result_type"] == "table", (result["status"], ui)
    rows = result["_sim"]["dax_log"][-1]["result"]
    assert [row[1] for row in rows] == [f"{mes} 2025" for mes in MESES], rows
    for month, row in enumerate(rows, 1):
        assert round(row[2], 1) == lav_sum(None, 2025, month), (month, row)
    assert "| Mes | PESO |" in ui and "diciembre 2025" in ui, ui
    assert result["_sim"]["type_mismatch"] == []


def test_period_grouped_by_month_on_integer_year_month_columns():
    result, ui = last("per_qx_por_mes_2024")
    assert result["status"] == "success" and result["result_type"] == "table", (result["status"], ui)
    dax = dax_of(result)
    assert "DATE(" not in dax, dax
    assert "TREATAS({2024}, 'Calendario'[AÑO])" in dax and "TREATAS({12}, 'Calendario'[MES])" in dax
    assert len(result["_sim"]["dax_log"][-1]["result"]) == 12
    assert result["_sim"]["type_mismatch"] == []


def test_period_range_across_years_on_integer_columns():
    result, ui = last("per_qx_rango_cruzado")
    assert result["status"] == "success", (result["status"], ui)
    assert ("TREATAS({(2024, 11), (2024, 12), (2025, 1), (2025, 2)}, "
            "'Calendario'[AÑO], 'Calendario'[MES])") in dax_of(result)
    assert "Filtros: noviembre 2024–febrero 2025" in ui, ui


def test_period_by_day_without_date_column_is_declared():
    result, ui = last("per_qx_hoy")
    assert result["status"] == "unsupported_filter", (result["status"], ui)
    assert "hoy" in ui and "período" in ui, ui


# ----------------------------------------------------------------------------
# Bugs conocidos
# ----------------------------------------------------------------------------

def test_clarification_question_is_not_the_generic_text():
    first, ui = run("base_descriptivo")[0][1:]
    assert first["status"] == "needs_clarification"
    real_question = (first.get("intent") or {}).get("question")
    assert real_question, "el ConversationManager debía producir una pregunta"
    assert ui != GENERIC_CLARIFICATION, ui
    # Sin «Por ejemplo: ...»: los tableros ya se muestran como botones.
    assert real_question.startswith(ui) and "Por ejemplo" not in ui, ui


def test_displayed_answer_never_contains_none():
    offenders = [(name, text, ui) for name, text, result, ui in all_turns() if "None" in ui]
    assert not offenders, offenders


def test_integer_year_columns_are_not_compared_with_date():
    offenders = [(name, m["message"]) for name, text, result, ui in all_turns()
                 for m in result["_sim"]["type_mismatch"]]
    assert not offenders, offenders


def test_month_only_questions_do_not_silently_drop_the_month():
    for name in ("lav_mes_sin_anio", "qx_mes_sin_anio"):
        result, ui = last(name)
        if result["status"] != "success":
            continue  # pedir el año o declarar la limitación también es válido
        dax = dax_of(result)
        applied = "DATE(" in dax or "MONTH(" in dax.upper() or "[MES])" in dax.upper()
        said = any(w in ui.lower() for w in ("año", "ano", "mes"))
        assert applied or said, f"{name}: el mes se perdió. UI={ui!r} DAX={dax!r}"


def test_all_requested_filters_are_applied_or_declared():
    result, ui = last("base_enrutado_fuerte")
    values = [str(f["value"]).upper() for f in result.get("filters", []) if f.get("value") is not None]
    assert any("SEDE NORTE" in v for v in values), values
    plastica_applied = any("PLASTICA" in v for v in values)
    declared = any(w in ui.lower() for w in ("plástica", "plastica", "no pude aplicar", "no se aplic"))
    assert plastica_applied or declared, f"filtros={values} UI={ui!r}"


# ----------------------------------------------------------------------------
# Runner propio
# ----------------------------------------------------------------------------

def _collect():
    mod = sys.modules[__name__]
    return [(n, f) for n, f in vars(mod).items() if n.startswith("test_") and callable(f)]


def main():
    counts = {"PASS": [], "FAIL": [], "XFAIL": [], "XPASS": []}
    for name, fn in _collect():
        reason = getattr(fn, "__xfail_reason__", None)
        try:
            fn()
            outcome, detail = ("XPASS" if reason else "PASS"), ""
        except BaseException as exc:  # noqa: BLE001 - queremos reportar todo
            if isinstance(exc, KeyboardInterrupt):
                raise
            first = (str(exc).strip().splitlines() or [type(exc).__name__])[0][:160]
            outcome = "XFAIL" if reason else "FAIL"
            detail = f"{type(exc).__name__}: {first}"
            if outcome == "FAIL":
                detail += "\n" + traceback.format_exc()
        counts[outcome].append(name)
        line = f"{outcome:5s} {name}"
        if outcome == "XFAIL":
            line += f"\n        motivo del bug: {reason}\n        falla con: {detail}"
        elif outcome == "XPASS":
            line += "   <-- ahora PASA: quita @xfail"
        elif outcome == "FAIL":
            line += f"\n        {detail}"
        print(line)
    print("-" * 80)
    print(f"PASS={len(counts['PASS'])} FAIL={len(counts['FAIL'])} "
          f"XFAIL={len(counts['XFAIL'])} XPASS={len(counts['XPASS'])}")
    if counts["XPASS"]:
        print("XPASS (bugs corregidos, quita la marca xfail):", ", ".join(counts["XPASS"]))
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())

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
from datetime import datetime
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
    """True si `number` (p. ej. 488.3) aparece escrito en el texto (488.3 o 488,3)."""
    s = f"{number:.1f}".rstrip("0").rstrip(".") if isinstance(number, float) else str(number)
    return s in text or s.replace(".", ",") in text


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
    result, ui = last("base_ambigua")
    assert result["status"] == "metric_not_resolved"
    assert "indicador" in ui


def test_base_ambiguous_metric_offers_options_and_resolves_by_number():
    (_, first, ui1), (_, second, ui2) = run("base_dato_aclaracion")
    assert first["status"] == "needs_clarification"
    assert len(first["clarification_options"]) == 2 and "1." in ui1
    # La selección fija la métrica; el valor puede venir vacío (BLANK) por el
    # bug de DATE() vs columna entera, que ahora se informa como empty_result.
    assert second["status"] in ("success", "empty_result") and second["route"] == "powerbi"
    assert second["query_plan"]["metric"]["metric_id"] == "b_cx_realizadas"


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
# Bugs conocidos
# ----------------------------------------------------------------------------

def test_clarification_question_is_not_the_generic_text():
    first, ui = run("base_descriptivo")[0][1:]
    assert first["status"] == "needs_clarification"
    real_question = (first.get("intent") or {}).get("question")
    assert real_question, "el ConversationManager debía producir una pregunta"
    assert ui != GENERIC_CLARIFICATION, ui
    assert ui == real_question


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

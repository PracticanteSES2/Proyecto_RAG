"""
Pruebas del propio evaluador (tests/eval): banco de preguntas, expectativas,
métricas de calidad, puntuación y runner.

Ejecutar:
  PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 python -m tests.eval.test_eval
(también compatible con pytest). Las pruebas de extremo a extremo usan el arnés
offline de tests/sim; la salida se escribe en una carpeta temporal.
"""
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.eval import expectations as ex  # noqa: E402
from tests.eval import quality  # noqa: E402
from tests.eval import run as runner  # noqa: E402
from tests.eval.report import build_summary, write_reports  # noqa: E402


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def powerbi_result(filters=(), metric="PESO", model="Lavanderia", **extra):
    result = {
        "status": "success", "route": "powerbi", "metric": metric, "metric_id": "m1",
        "semantic_model": model, "report": f"Tablero {model}", "filters": list(filters),
        "result_type": "scalar", "_sim": {"exception": None, "dax_log": []},
    }
    result.update(extra)
    return result


def rag_result(answer, sources):
    return {
        "status": "success", "route": "rag", "answer": answer,
        "sources": [{"text": text, "dashboard": "Tablero X"} for text in sources],
        "_sim": {"exception": None},
    }


def clarification_result():
    return {
        "status": "needs_clarification", "route": "clarification",
        "prompt": "Encontré varios indicadores. ¿Cuál necesitas?",
        "clarification_options": [
            {"id": "a", "label": "Cirugías realizadas — Tablero Quirurgico", "summary": "Quirúrgico"},
            {"id": "b", "label": "Cirugías realizadas — Atenciones", "summary": "Atenciones"},
        ],
        "none_option": {"id": "__none__", "label": "Ninguna de las anteriores"},
        "_sim": {"exception": None},
    }


def failed(checks):
    return [c["check"] for c in checks if c["ok"] is False]


SERVICIO = {"type": "categorical", "table": "LAVANDERIA", "column": "SERVICIO", "value": "ANTIFLUIDOS"}
ENERO_2026 = {"type": "date_range", "table": "LAVANDERIA", "column": "Fecha", "year": 2026, "month": 1}


# ---------------------------------------------------------------------------
# Banco de preguntas
# ---------------------------------------------------------------------------

def test_question_bank_is_valid_and_covers_all_categories():
    data = runner.load_questions()
    cases = data["cases"]
    assert 80 <= len(cases) <= 130, len(cases)
    for category in runner.CATEGORIES:
        count = sum(1 for c in cases if c["category"] == category)
        assert count >= 8, (category, count)
    sim_cases = [c for c in cases if runner.is_applicable(c, "sim")]
    assert len(sim_cases) >= 20, len(sim_cases)
    for case in cases:
        if case["category"] != "g_fuera_alcance":
            assert case["fuente"]["docx"].endswith(".docx"), case["id"]
    # Hay conversaciones de varios turnos con botón, número, nombre y «ninguna».
    multi = [c for c in cases if c["category"] == "i_multiturno"]
    kinds = {("button" if "button" in t else "text") for c in multi for t in c["turns"][1:]}
    assert kinds == {"button", "text"}, kinds
    assert any(t.get("button") == "none" for c in multi for t in c["turns"])


def test_validation_reports_broken_cases():
    data = {"cases": [
        {"id": "x", "category": "zz", "turns": [{"user": "a", "button": 1}]},
        {"id": "x", "category": "a_kpi_simple", "turns": [{"user": "a", "expect": {"rutas": []}}],
         "fuente": {"docx": "a.docx"}, "arneses": ["otro"]},
    ]}
    problems = "\n".join(runner.validate_questions(data))
    for fragment in ("categoría desconocida", "'user' o 'button'", "id repetido",
                     "claves de expect desconocidas", "arneses desconocidos", "falta fuente.docx"):
        assert fragment in problems, (fragment, problems)


# ---------------------------------------------------------------------------
# Expectativas
# ---------------------------------------------------------------------------

def test_classify_result_kinds():
    assert ex.classify(powerbi_result()) == "powerbi"
    assert ex.classify({"status": "empty_result", "route": "powerbi"}) == "powerbi_empty"
    assert ex.classify(rag_result("x", [])) == "rag"
    assert ex.classify(clarification_result()) == "clarification"
    assert ex.classify({"status": "not_found", "route": "out_of_scope"}) == "out_of_scope"
    assert ex.classify({"status": "not_found", "route": "clarification"}) == "not_found"
    assert ex.classify({"status": "metric_not_resolved", "route": "powerbi"}) == "metric_not_resolved"
    assert ex.classify({}) == "otro"


def test_number_in_accepts_spanish_and_english_formats():
    assert ex.number_in("**PESO**: 488,3", 488.3)
    assert ex.number_in("total 3.906,4 kg", 3906.4)
    assert ex.number_in("participación del 12,5 %", 12.5)
    assert ex.number_in("**TOTAL ATENCIONES**: 152.340", 152340)
    assert ex.number_in("value 1,382.8", 1382.8)
    assert not ex.number_in("**PESO**: 48,3", 488.3)


def test_route_metric_and_model_are_tolerant():
    expect = {"route": ["powerbi", "powerbi_empty"], "metrics_any": ["peso", "kilos"],
              "models_any": ["lavandería"]}
    kind, checks = ex.evaluate_turn(expect, powerbi_result(), "**PESO**: 1", [])
    assert kind == "powerbi" and not failed(checks), checks
    kind, checks = ex.evaluate_turn(expect, powerbi_result(metric="TOTAL", model="Farmacia"), "x: 1", [])
    assert set(failed(checks)) == {"metric", "model"}, checks
    # Si terminó en contrapregunta solo falla la ruta: la métrica «no aplica».
    kind, checks = ex.evaluate_turn(expect, clarification_result(), "¿Cuál?", [])
    assert failed(checks) == ["route"], checks


def test_filters_applied_declared_or_hidden():
    expect = {"route": ["powerbi"], "filters": [{"column": "SERVICIO", "value": "antifluidos"},
                                                {"year": 2026, "month": 1}]}
    _, checks = ex.evaluate_turn(expect, powerbi_result([SERVICIO, ENERO_2026]), "**PESO**: 488,3", [])
    assert not failed(checks), checks

    # Sin el filtro de servicio pero avisándolo: aceptado.
    declared = powerbi_result([ENERO_2026], unapplied_terms=["antifluidos"])
    _, checks = ex.evaluate_turn(expect, declared, "**PESO**: 3.906,4\n\nNo pude aplicar: antifluidos", [])
    assert not failed(checks), checks

    # Sin el filtro y sin avisar: falla el filtro y la prohibición de dar el total.
    _, checks = ex.evaluate_turn(expect, powerbi_result([ENERO_2026]), "**PESO**: 3.906,4", [])
    assert set(failed(checks)) == {"filter SERVICIO=antifluidos", "forbid total_without_filter"}, checks


def test_year_filter_accepts_integer_year_column_and_month_only():
    year_column = {"type": "categorical", "column": "AÑO", "value": 2024}
    _, checks = ex.evaluate_turn({"filters": [{"year": 2024}]}, powerbi_result([year_column]), "x: 1", [])
    assert not failed(checks), checks
    month_only = {"type": "date_range", "column": "Fecha", "year": None, "month": 1}
    _, checks = ex.evaluate_turn({"filters": [{"month": 1}]}, powerbi_result([month_only]), "x: 1", [])
    assert not failed(checks), checks
    _, checks = ex.evaluate_turn({"filters": [{"year": 2025}]}, powerbi_result([year_column]), "x: 1", [])
    assert "filter periodo 2025" in failed(checks), checks
    # Periodos relativos: "actual" = año en curso.
    from datetime import date
    this_year = {"type": "date_range", "column": "Fecha", "year": date.today().year, "month": None}
    _, checks = ex.evaluate_turn({"filters": [{"year": "actual"}]}, powerbi_result([this_year]), "x: 1", [])
    assert not failed(checks), checks


def test_group_by_and_result_type():
    grouped = powerbi_result(result_type="table", group_by=[{"column": "TURNO_OK", "label": "turno"}])
    _, checks = ex.evaluate_turn({"group_by_any": ["turno"], "result_type": "table"}, grouped, "| a |", [])
    assert not failed(checks), checks
    _, checks = ex.evaluate_turn({"group_by_any": ["mes"], "result_type": "table"}, powerbi_result(), "x", [])
    assert set(failed(checks)) == {"group_by", "result_type"}, checks


def test_clarification_expectations_use_buttons():
    from src.chatbot.response_formatter import clarification_buttons

    result = clarification_result()
    buttons = clarification_buttons(result)
    expect = {"route": ["clarification"], "options_any": ["realizad"], "min_options": 2,
              "has_none_option": True, "prompt_any": ["indicadores"]}
    _, checks = ex.evaluate_turn(expect, result, result["prompt"], buttons)
    assert not failed(checks), checks
    _, checks = ex.evaluate_turn({"options_any": ["triage"], "min_options": 3}, result, "x", buttons)
    assert set(failed(checks)) == {"options", "min_options"}, checks


def test_default_prohibitions():
    result = powerbi_result()
    _, checks = ex.evaluate_turn({}, result, "**PESO**: None", [])
    assert "forbid none_text" in failed(checks)
    _, checks = ex.evaluate_turn({}, rag_result("Según el chunk 3 del embedding...", []), "Según el chunk 3", [])
    assert "forbid internal_terms" in failed(checks)
    broken = {"status": "error", "_sim": {"exception": "KeyError: 'x'"}}
    _, checks = ex.evaluate_turn({}, broken, "Ocurrió un error", [])
    assert "forbid exception" in failed(checks)
    _, checks = ex.evaluate_turn({}, result, "", [])
    assert "forbid empty_answer" in failed(checks)
    # `allow` desactiva una prohibición; `forbid` agrega opcionales.
    _, checks = ex.evaluate_turn({"allow": ["none_text"]}, result, "**PESO**: None", [])
    assert "forbid none_text" not in failed(checks)
    _, checks = ex.evaluate_turn({"forbid": ["numbers", "powerbi_answer"]}, result, "**PESO**: 488,3", [],
                                 question="peso")
    assert {"forbid numbers", "forbid powerbi_answer"} <= set(failed(checks)), checks


def test_invented_numbers_only_checked_in_rag_answers():
    sources = ["El NEDOCS = -20 + 85.8 * (A1/A2) + 600 * (B1/B2). Rangos de 0 a 7 días."]
    ok = rag_result("La fórmula usa 85,8 y 600.", sources)
    _, checks = ex.evaluate_turn({}, ok, ok["answer"], [], question="como se calcula el nedocs")
    assert not failed(checks), checks
    bad = rag_result("El NEDOCS promedio de 2025 fue 143,2.", sources)
    _, checks = ex.evaluate_turn({}, bad, bad["answer"], [], question="nedocs")
    assert "forbid invented_numbers" in failed(checks), checks
    detail = next(c["detail"] for c in checks if c["check"] == "forbid invented_numbers")
    assert "143,2" in detail and "2025" in detail, detail
    # El año de la pregunta cuenta como evidencia.
    _, checks = ex.evaluate_turn({}, bad, bad["answer"], [], question="nedocs 2025 143,2")
    assert "forbid invented_numbers" not in failed(checks)
    # En Power BI las cifras no se comparan con fuentes documentales.
    _, checks = ex.evaluate_turn({}, powerbi_result(), "**PESO**: 488,3", [])
    assert "forbid invented_numbers" not in [c["check"] for c in checks]


def test_keyword_coverage_only_for_documental_answers():
    answer = "Muestra el peso de ropa por turno laboral (MAÑANA, TARDE, NOCHE)."
    expect = {"keywords": ["peso", "turno", "mañana", "aseguradora"], "min_keyword_coverage": 0.75}
    _, checks = ex.evaluate_turn(expect, rag_result(answer, [answer]), answer, [])
    assert not failed(checks), checks
    _, checks = ex.evaluate_turn({**expect, "min_keyword_coverage": 1.0}, rag_result(answer, [answer]), answer, [])
    assert failed(checks) == ["keywords"], checks
    _, checks = ex.evaluate_turn(expect, powerbi_result(), "**PESO**: 1", [])
    assert next(c for c in checks if c["check"] == "keywords")["ok"] is None


# ---------------------------------------------------------------------------
# Métricas de calidad
# ---------------------------------------------------------------------------

def test_quality_metrics():
    assert quality.spanish_ratio("Este tablero muestra el total de atenciones por mes y año") > 0.8
    assert quality.spanish_ratio("This dashboard shows the total of the month and the year") < 0.5
    assert quality.spanish_ratio("PESO: 488,3") is None
    assert quality.internal_terms("Según los chunks recuperados de Qdrant y el prompt") == \
        ["chunks", "qdrant", "prompt"]
    assert quality.extract_numbers("1. Opción\n2. Otra con 12,5 % y 3.906,4") == ["12,5", "3.906,4"]
    coverage, found, missing = quality.keyword_coverage("Filtros por Aseguradora, Año y Mes", ["aseguradora", "ano", "sede"])
    assert round(coverage, 2) == 0.67 and missing == ["sede"], (coverage, found, missing)
    metrics = quality.quality_metrics("Muestra 5 visuales y 1234 registros.", rag_result("x", ["5 visuales"]),
                                      question="q", keywords=["visuales"])
    assert metrics["keyword_coverage"] == 1.0 and metrics["unsupported_numbers"] == ["1234"], metrics


def _dummy_judge(case, turn, result, ui):
    return {"score": 1.0, "comment": "ok"}


def test_judge_hook_is_optional():
    assert quality.load_judge(None) is None
    judge = quality.load_judge("tests.eval.test_eval:_dummy_judge")
    assert judge(None, None, None, None)["score"] == 1.0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def test_resolve_button():
    buttons = [{"id": "a", "label": "Cirugías realizadas — Tablero Quirurgico"},
               {"id": "b", "label": "Cirugías realizadas — Atenciones"},
               {"id": "__none__", "label": "Ninguna de las anteriores"}]
    assert runner.resolve_button(2, buttons)["id"] == "b"
    assert runner.resolve_button("none", buttons)["id"] == "__none__"
    assert runner.resolve_button({"label_any": ["quirurgico"]}, buttons)["id"] == "a"
    assert runner.resolve_button("atenciones", buttons)["id"] == "b"
    assert runner.resolve_button(4, buttons) is None
    assert runner.resolve_button(1, []) is None


def test_outcomes_and_xfail():
    assert runner.outcome_of(True, None) == "pass"
    assert runner.outcome_of(False, None) == "fail"
    assert runner.outcome_of(False, "bug") == "xfail"
    assert runner.outcome_of(True, "bug") == "xpass"
    assert runner.xfail_reason({"xfail": {"sim": "bug"}}, "sim") == "bug"
    assert runner.xfail_reason({"xfail": {"sim": "bug"}}, "realistic") is None


class _FakeEngine:
    """Motor mínimo: contrapregunta y luego dato al pulsar un botón."""

    def __init__(self):
        self.selected = []
        self.last_reasoning = None

    def process(self, text):
        return clarification_result()

    def select_clarification_option(self, option_id, label=None):
        self.selected.append((option_id, label))
        return powerbi_result([ENERO_2026], metric="CIRUGÍAS REALIZADAS", model="Gestion Quirurgica")

    def reset(self):
        pass


def _fake_harness():
    from src.chatbot.response_formatter import clarification_prompt

    def ask(engine, cm, formatter, text):
        result = engine.process(text)
        result.setdefault("_sim", {"exception": None})
        ui = clarification_prompt(result) if result["status"] == "needs_clarification" else \
            f"**{result['metric']}**: 10"
        return result, ui

    return SimpleNamespace(
        build_engine=lambda ollama_up=True: (_FakeEngine(), SimpleNamespace(reset=lambda: None), None,
                                             {"status": "ready"}, {"status": "success"}, []),
        new_conversation=lambda engine, cm: None,
        ask=ask,
    )


def test_build_system_passes_only_supported_arguments():
    calls = []

    def realistic_build_engine(llm="fake", quiet=True):  # firma del arnés realista
        calls.append(("realistic", llm, quiet))
        return ("engine", "cm", "formatter", {"status": "ready"}, {}, [])

    def sim_build_engine(sim_root=None, ollama_up=True, powerbi_up=True, quiet=True):
        calls.append(("sim", ollama_up, quiet))
        return ("engine", "cm", "formatter", {"status": "ready"}, {}, [])

    runner.build_system(SimpleNamespace(build_engine=realistic_build_engine), "realistic", "real")
    runner.build_system(SimpleNamespace(build_engine=sim_build_engine), "sim", "down")
    assert calls == [("realistic", "real", True), ("sim", False, True)], calls


def test_run_case_presses_buttons_and_scores():
    harness = _fake_harness()
    system = runner.build_system(harness, "fake", "fake")
    case = {
        "id": "demo", "category": "i_multiturno", "arneses": ["sim"],
        "fuente": {"docx": "x.docx"},
        "turns": [
            {"user": "¿Cuántas cirugías realizadas hubo en 2024?",
             "expect": {"route": ["clarification"], "options_any": ["realizad"], "has_none_option": True}},
            {"button": 1, "expect": {"route": ["powerbi"], "models_any": ["quirurg"],
                                     "filters": [{"year": 2026}]}},
        ],
    }
    out = runner.run_case(case, system, harness, harness_name="sim")
    assert out["passed"] and out["outcome"] == "pass", json.dumps(out, ensure_ascii=False, default=str)[:2000]
    assert system[0].selected == [("a", "Cirugías realizadas — Tablero Quirurgico")]
    assert out["turns"][1]["input_type"] == "button" and out["turns"][1]["latency_s"] >= 0

    # Un botón inexistente no tumba el caso: se marca y se omiten los turnos siguientes.
    case["turns"][1]["button"] = 9
    case["turns"].append({"user": "otra", "expect": {}})
    out = runner.run_case(case, system, harness, harness_name="sim")
    assert not out["passed"] and out["turns"][1]["skipped"] and out["turns"][2]["skipped"], out["turns"]


def test_summary_and_reports_are_written():
    results = [
        {"id": "a", "category": "a_kpi_simple", "applicable": True, "passed": True, "outcome": "pass",
         "turns": [{"index": 1, "passed": True, "latency_s": 0.1, "kind": "powerbi", "checks": [
             {"check": "route", "ok": True, "detail": ""}],
             "quality": quality.quality_metrics("x", {}), "input": "q", "ui": "x"}]},
        {"id": "b", "category": "a_kpi_simple", "applicable": True, "passed": False, "outcome": "xfail",
         "xfail": "bug", "turns": [{"index": 1, "passed": False, "latency_s": 0.3, "kind": "rag", "checks": [
             {"check": "route", "ok": False, "detail": "obtenido=rag"}],
             "quality": quality.quality_metrics("y", {"route": "rag"}), "input": "q", "ui": "y",
             "reasoning": "=== RAZONAMIENTO ==="}]},
        {"id": "c", "category": "g_fuera_alcance", "applicable": False, "passed": False, "outcome": "fail",
         "turns": []},
    ]
    summary = build_summary(results, runner.CATEGORIES)
    assert summary["total"]["cases"] == 3 and summary["total"]["passed"] == 1
    assert summary["applicable"]["xfail"] == 1 and summary["applicable"]["fail"] == 0
    assert summary["by_category"]["a_kpi_simple"]["all"]["checks_ok"] == 1
    tmp = Path(tempfile.mkdtemp(prefix="eval_test_"))
    try:
        meta = {"fecha": "hoy", "harness": "sim", "llm": "fake", "llm_status": "ready", "questions": "q.json",
                "categories": "todas", "build_s": 0, "elapsed_s": 0}
        write_reports(tmp, meta, results, runner.CATEGORIES)
        markdown = (tmp / "report.md").read_text(encoding="utf-8")
        assert "| **Total** | **3** | **1** |" in markdown, markdown[:1500]
        assert "Fallos conocidos del chatbot (xfail) en casos aplicables (1)" in markdown
        assert "=== RAZONAMIENTO ===" in markdown
        assert json.loads((tmp / "report.json").read_text(encoding="utf-8"))["summary"]["total"]["cases"] == 3
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_end_to_end_on_sim_subset():
    tmp = Path(tempfile.mkdtemp(prefix="eval_sim_"))
    try:
        ids = "i_opcion_por_boton,c_sim_lav_antifluidos_ene2026,g_capital_francia,i_ninguna_boton_y_elige"
        code = runner.main(["--harness", "sim", "--case", ids, "--out", str(tmp), "--quiet", "--strict"])
        report = json.loads((tmp / "report.json").read_text(encoding="utf-8"))
        outcomes = {c["id"]: c["outcome"] for c in report["cases"]}
        assert code == 0, outcomes
        assert set(outcomes.values()) == {"pass"}, outcomes
        boton = next(c for c in report["cases"] if c["id"] == "i_opcion_por_boton")
        assert boton["turns"][1]["input_type"] == "button"
        assert boton["turns"][1]["result"]["semantic_model"] == "Atenciones Institucionales"
        assert "RAZONAMIENTO DEL ASISTENTE" in boton["turns"][0]["reasoning"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Runner mínimo
# ---------------------------------------------------------------------------

def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed_count = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failed_count += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed_count}/{len(tests)} OK")
    return 1 if failed_count else 0


if __name__ == "__main__":
    sys.exit(main())

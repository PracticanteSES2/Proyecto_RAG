"""
Evaluador del chatbot sobre un banco de preguntas (tests/eval/questions.json).

Ejecuta cada caso en una conversación NUEVA usando el arnés elegido:

    python -m tests.eval.run --harness sim                       # tests/sim (fixtures pequeños)
    python -m tests.eval.run --harness realistic --llm fake      # tests/realistic (datos reales)
    python -m tests.eval.run --harness realistic --llm real      # ... con MedGemma real
    python -m tests.eval.run --harness sim --category e_ambiguo --case lav_peso_servicio_mes
    python -m tests.eval.run --harness sim --solo-aplicables --strict
    python -m tests.eval.run --list

Cada turno es un texto del usuario o la pulsación de un botón de la
contrapregunta (engine.select_clarification_option, como hace app.py). Se mide
la latencia de cada turno, se evalúan las expectativas (expectations.py) y las
métricas de calidad (quality.py) y se escriben report.md y report.json en
--out (por defecto tests/eval/out/<arnés>-<fecha>/, carpeta ignorada por git).

El arnés se importa de forma perezosa: `--harness realistic` solo necesita que
exista tests/realistic/harness.py con la misma API que tests/sim/harness.py.
"""
import argparse
import importlib
import inspect
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.eval import expectations as ex  # noqa: E402
from tests.eval import quality  # noqa: E402
from tests.eval.report import write_reports  # noqa: E402

DEFAULT_QUESTIONS = EVAL_DIR / "questions.json"
DEFAULT_OUT_ROOT = EVAL_DIR / "out"
HARNESSES = {"sim": "tests.sim.harness", "realistic": "tests.realistic.harness"}
CATEGORIES = {
    "a_kpi_simple": "KPI numérico simple",
    "b_kpi_periodo": "KPI con periodo (año/mes)",
    "c_kpi_filtro": "KPI con filtro categórico",
    "d_agrupado": "KPI agrupado («por ...»)",
    "e_ambiguo": "Indicador ambiguo en varios tableros (debe contrapreguntar)",
    "f_documental": "Documental (qué muestra, cómo se calcula, qué filtros)",
    "g_fuera_alcance": "Fuera de alcance",
    "h_compuesta": "Compuestas (dos medidas / participación)",
    "i_multiturno": "Conversaciones multi-turno",
}
NONE_ID = "__none__"


# ----------------------------------------------------------------------------
# Banco de preguntas
# ----------------------------------------------------------------------------


def load_questions(path=DEFAULT_QUESTIONS):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = validate_questions(data)
    if problems:
        raise ValueError("Banco de preguntas inválido:\n  - " + "\n  - ".join(problems))
    return data


def validate_questions(data):
    problems = []
    seen = set()
    for index, case in enumerate(data.get("cases") or []):
        cid = case.get("id")
        where = cid or f"#{index}"
        if not cid:
            problems.append(f"{where}: falta id")
        elif cid in seen:
            problems.append(f"{where}: id repetido")
        seen.add(cid)
        if case.get("category") not in CATEGORIES:
            problems.append(f"{where}: categoría desconocida {case.get('category')!r}")
        turns = case.get("turns") or []
        if not turns:
            problems.append(f"{where}: sin turnos")
        for number, turn in enumerate(turns, 1):
            if ("user" in turn) == ("button" in turn):
                problems.append(f"{where} turno {number}: debe tener 'user' o 'button' (uno solo)")
            unknown = set(turn.get("expect") or {}) - KNOWN_EXPECT_KEYS
            if unknown:
                problems.append(f"{where} turno {number}: claves de expect desconocidas {sorted(unknown)}")
        if not (case.get("fuente") or {}).get("docx") and case.get("category") != "g_fuera_alcance":
            problems.append(f"{where}: falta fuente.docx")
        unknown_harness = set(case.get("arneses") or []) - set(HARNESSES)
        if unknown_harness:
            problems.append(f"{where}: arneses desconocidos {sorted(unknown_harness)}")
        if case.get("xfail") is not None and not isinstance(case["xfail"], (str, dict)):
            problems.append(f"{where}: xfail debe ser texto o {{arnés: motivo}}")
    return problems


KNOWN_EXPECT_KEYS = {
    "route", "status", "metrics_any", "models_any", "filters", "allow_declared_filters",
    "group_by_any", "result_type", "numbers", "answer_any", "answer_all", "answer_none",
    "keywords", "min_keyword_coverage", "options_any", "min_options", "has_none_option",
    "prompt_any", "forbid", "allow",
}


def select_cases(data, categories=(), case_ids=(), harness_name=None, only_applicable=False):
    cases = data.get("cases") or []
    if categories:
        cases = [c for c in cases if c["category"] in categories]
    if case_ids:
        missing = set(case_ids) - {c["id"] for c in cases}
        if missing:
            raise SystemExit(f"Casos inexistentes (o fuera de la categoría pedida): {sorted(missing)}")
        cases = [c for c in cases if c["id"] in case_ids]
    if only_applicable and harness_name:
        cases = [c for c in cases if is_applicable(c, harness_name)]
    return cases


def is_applicable(case, harness_name):
    """¿Se espera que el caso pase con este arnés? (campo `arneses`)."""
    return harness_name in (case.get("arneses") or ["realistic"])


# ----------------------------------------------------------------------------
# Arnés
# ----------------------------------------------------------------------------


def import_harness(name):
    module_name = HARNESSES.get(name, name)
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if name == "realistic":
            raise SystemExit(
                "No existe tests/realistic/harness.py en este árbol. "
                "Usa --harness sim o integra la rama del arnés realista."
            ) from error
        raise


def build_system(harness, name, llm):
    """Llama a harness.build_engine con los argumentos que acepte."""
    params = inspect.signature(harness.build_engine).parameters
    kwargs = {}
    if "llm" in params:
        kwargs["llm"] = llm
    elif llm == "real":
        print(f"[aviso] el arnés {name} no tiene LLM real: se usa el falso.", file=sys.stderr)
    if "ollama_up" in params:
        kwargs["ollama_up"] = llm != "down"
    if "quiet" in params:
        kwargs["quiet"] = True
    return harness.build_engine(**kwargs)


class _OptionEngine:
    """Envuelve el motor para que harness.ask() ejecute la pulsación de un
    botón (select_clarification_option) en lugar de process(texto)."""

    def __init__(self, engine, option_id, label):
        self._engine = engine
        self._option_id = option_id
        self._label = label

    def process(self, _text):
        return self._engine.select_clarification_option(self._option_id, self._label)

    def __getattr__(self, name):
        return getattr(self._engine, name)


def ask(harness, engine, cm, formatter, text=None, option=None):
    if option is None:
        return harness.ask(engine, cm, formatter, text)
    custom = getattr(harness, "ask_option", None)
    if callable(custom):
        return custom(engine, cm, formatter, option["id"], option["label"])
    return harness.ask(_OptionEngine(engine, option["id"], option["label"]), cm, formatter, option["label"])


def resolve_button(spec, buttons):
    """Botón a pulsar: número (1 = primero), "none", {"label_any": [...]} o {"id": ...}."""
    buttons = buttons or []
    if isinstance(spec, bool):
        spec = int(spec)
    if isinstance(spec, int):
        return buttons[spec - 1] if 1 <= spec <= len(buttons) else None
    if isinstance(spec, str):
        if spec.lower() in ("none", "ninguna", NONE_ID):
            return next((b for b in buttons if str(b.get("id")) == NONE_ID), None)
        return next((b for b in buttons if quality.contains(b.get("label"), spec)), None)
    if isinstance(spec, dict):
        if spec.get("id") is not None:
            found = next((b for b in buttons if str(b.get("id")) == str(spec["id"])), None)
            return found or {"id": spec["id"], "label": spec.get("label") or str(spec["id"])}
        for needle in ex.as_list(spec.get("label_any")):
            found = next((b for b in buttons if quality.contains(b.get("label"), needle)), None)
            if found:
                return found
    return None


# ----------------------------------------------------------------------------
# Ejecución de un caso
# ----------------------------------------------------------------------------


def _summary_of_result(result):
    """Campos útiles del resultado (sin filas de datos)."""
    keep = ("status", "route", "stage", "metric", "metric_id", "semantic_model", "report",
            "dashboard", "result_type", "value", "synthesis_mode", "clarification_type", "error")
    out = {k: result.get(k) for k in keep if result.get(k) is not None}
    filters = ex.applied_filters(result)
    if filters:
        out["filters"] = [
            {k: f.get(k) for k in ("type", "table", "column", "value", "year", "month") if f.get(k) is not None}
            for f in filters
        ]
    if ex.unapplied_terms(result):
        out["unapplied_terms"] = ex.unapplied_terms(result)
    dax = ex.dax_text(result)
    if dax:
        out["dax"] = dax[:4000]
    if result.get("sources"):
        out["sources"] = [
            {"dashboard": s.get("dashboard"), "chunk_type": s.get("chunk_type"),
             "score": s.get("score")} for s in result["sources"] if isinstance(s, dict)
        ]
    sim = result.get("_sim") or {}
    if sim.get("exception"):
        out["exception"] = sim.get("exception")
        out["traceback"] = sim.get("traceback")
    return out


def run_case(case, system, harness, judge=None, harness_name="sim"):
    from src.chatbot.reasoning_trace import format_reasoning_text
    from src.chatbot.response_formatter import clarification_buttons

    engine, cm, formatter = system[0], system[1], system[2]
    harness.new_conversation(engine, cm)
    turns_out = []
    buttons = []
    aborted = None
    for index, turn in enumerate(case["turns"], 1):
        expect = turn.get("expect") or {}
        if aborted:
            turns_out.append({"index": index, "skipped": True, "reason": aborted, "passed": False,
                              "input": turn.get("user") or f"[botón] {turn.get('button')}"})
            continue
        option = None
        if "button" in turn:
            option = resolve_button(turn["button"], buttons)
            if option is None:
                aborted = f"el turno {index} pide el botón {turn['button']!r} y no estaba disponible"
                turns_out.append({
                    "index": index, "input": f"[botón] {turn['button']}", "input_type": "button",
                    "skipped": True, "reason": aborted, "passed": False,
                    "available_buttons": [b.get("label") for b in buttons],
                })
                continue
            question = option["label"]
        else:
            question = turn["user"]
        started = time.perf_counter()
        try:
            result, ui = ask(harness, engine, cm, formatter, question, option)
        except Exception as error:  # el arnés ya captura las del motor; esto es un fallo del arnés
            result = {"status": "error", "route": None, "error": f"{type(error).__name__}: {error}",
                      "_sim": {"exception": f"{type(error).__name__}: {error}",
                               "traceback": traceback.format_exc()}}
            ui = ""
        latency = time.perf_counter() - started
        buttons = clarification_buttons(result) if result.get("status") == "needs_clarification" else []
        # Evidencia de la pregunta: el primer mensaje del caso y el de este turno.
        original = case["turns"][0].get("user") or ""
        asked = original if original == question else f"{original}\n{question}"
        kind, checks = ex.evaluate_turn(
            expect, result, ui, buttons, question=asked,
            forbid=case.get("forbid"), allow=case.get("allow"),
        )
        reasoning = result.get("reasoning") or getattr(engine, "last_reasoning", None)
        judged = None
        if judge is not None:
            try:
                judged = judge(case, turn, result, ui)
            except Exception as error:
                judged = {"score": None, "comment": f"juez falló: {type(error).__name__}: {error}"}
        turns_out.append({
            "index": index,
            "input": question,
            "input_type": "button" if option else "text",
            "button_id": option.get("id") if option else None,
            "ui": ui,
            "buttons": buttons,
            "kind": kind,
            "latency_s": round(latency, 3),
            "checks": checks,
            "passed": ex.turn_passed(checks),
            "quality": quality.quality_metrics(
                ui, result, question=asked, keywords=expect.get("keywords"),
            ),
            "result": _summary_of_result(result),
            "reasoning": format_reasoning_text(reasoning, ui) if reasoning else "",
            "judge": judged,
        })
    harness.new_conversation(engine, cm)
    passed = all(t.get("passed") for t in turns_out)
    xfail = xfail_reason(case, harness_name)
    return {
        "id": case["id"],
        "category": case["category"],
        "tablero": case.get("tablero"),
        "fuente": case.get("fuente"),
        "descripcion": case.get("descripcion"),
        "arneses": case.get("arneses") or ["realistic"],
        "applicable": is_applicable(case, harness_name),
        "passed": passed,
        "outcome": outcome_of(passed, xfail),
        "xfail": xfail,
        "turns": turns_out,
    }


def xfail_reason(case, harness_name):
    """Motivo de fallo conocido (bug del chatbot) para este arnés, o None."""
    xfail = case.get("xfail")
    if isinstance(xfail, dict):
        return xfail.get(harness_name) or xfail.get("*")
    return xfail or None


def outcome_of(passed, xfail):
    if passed:
        return "xpass" if xfail else "pass"
    return "xfail" if xfail else "fail"


def run_cases(cases, system, harness, judge=None, harness_name="sim", progress=True):
    results = []
    for number, case in enumerate(cases, 1):
        try:
            outcome = run_case(case, system, harness, judge=judge, harness_name=harness_name)
        except Exception as error:  # nunca tumbar la corrida completa por un caso
            outcome = {
                "id": case["id"], "category": case["category"], "tablero": case.get("tablero"),
                "fuente": case.get("fuente"), "arneses": case.get("arneses") or ["realistic"],
                "applicable": is_applicable(case, harness_name), "passed": False,
                "outcome": "fail", "xfail": None,
                "runner_error": f"{type(error).__name__}: {error}\n{traceback.format_exc()}",
                "turns": [],
            }
            try:
                harness.new_conversation(system[0], system[1])
            except Exception:
                pass
        results.append(outcome)
        if progress:
            mark = {"pass": "OK   ", "xpass": "XPASS", "xfail": "XFAIL"}.get(
                outcome["outcome"], "FAIL " if outcome["applicable"] else "fail ")
            print(f"[{number:3d}/{len(cases)}] {mark} {case['category']:16s} {case['id']}", flush=True)
    return results


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def _split(values):
    out = []
    for value in values or []:
        out += [v.strip() for v in str(value).split(",") if v.strip()]
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Evaluador del chatbot sobre el banco de preguntas.")
    parser.add_argument("--harness", choices=sorted(HARNESSES), default="sim")
    parser.add_argument("--llm", choices=("fake", "real", "down"), default="fake",
                        help="LLM del arnés: falso, real (solo realistic) o caído")
    parser.add_argument("--category", action="append", help="categoría(s), repetible o separadas por coma")
    parser.add_argument("--case", action="append", help="id(s) de caso, repetible o separados por coma")
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    parser.add_argument("--out", help="carpeta de salida (por defecto tests/eval/out/<arnés>-<fecha>)")
    parser.add_argument("--solo-aplicables", action="store_true",
                        help="solo los casos marcados para este arnés (campo 'arneses')")
    parser.add_argument("--strict", action="store_true",
                        help="código de salida 1 si falla algún caso aplicable a este arnés")
    parser.add_argument("--judge", help="juez LLM opcional 'modulo:funcion' (desactivado por defecto)")
    parser.add_argument("--list", action="store_true", help="lista los casos y termina")
    parser.add_argument("--quiet", action="store_true", help="sin progreso por caso")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    data = load_questions(args.questions)
    categories = _split(args.category)
    unknown = set(categories) - set(CATEGORIES)
    if unknown:
        raise SystemExit(f"Categorías desconocidas: {sorted(unknown)}. Válidas: {sorted(CATEGORIES)}")
    cases = select_cases(data, categories, _split(args.case), args.harness, args.solo_aplicables)

    if args.list:
        for case in cases:
            first = case["turns"][0].get("user") or case["turns"][0].get("button")
            tags = ",".join(case.get("arneses") or ["realistic"])
            known = " (xfail)" if xfail_reason(case, args.harness) else ""
            print(f"{case['category']:16s} {case['id']:42s} [{tags}]{known} {first}")
        print(f"\n{len(cases)} casos")
        return 0

    harness = import_harness(args.harness)
    judge = quality.load_judge(args.judge)
    started = time.perf_counter()
    system = build_system(harness, args.harness, args.llm)
    llm_status = system[3] if len(system) > 3 else None
    build_s = time.perf_counter() - started
    results = run_cases(cases, system, harness, judge=judge, harness_name=args.harness,
                        progress=not args.quiet)
    elapsed = time.perf_counter() - started

    out_dir = Path(args.out) if args.out else (
        DEFAULT_OUT_ROOT / f"{args.harness}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    meta = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "harness": args.harness,
        "llm": args.llm,
        "llm_status": (llm_status or {}).get("status") if isinstance(llm_status, dict) else llm_status,
        "questions": str(Path(args.questions)),
        "categories": categories or "todas",
        "build_s": round(build_s, 2),
        "elapsed_s": round(elapsed, 2),
        "judge": args.judge,
        "solo_aplicables": args.solo_aplicables,
    }
    summary = write_reports(out_dir, meta, results, CATEGORIES)
    applicable = summary["applicable"]
    print("-" * 80)
    print(f"Casos: {summary['total']['cases']} · pasan {summary['total']['passed']} "
          f"({summary['total']['pct']:.0f} %) · aplicables a '{args.harness}': "
          f"{applicable['passed']}/{applicable['cases']} "
          f"(fallos nuevos {applicable['fail']}, conocidos XFAIL {applicable['xfail']}, XPASS {applicable['xpass']})")
    if applicable["xpass"]:
        print("XPASS (bug corregido: quita la marca 'xfail' del caso): "
              + ", ".join(r["id"] for r in results if r.get("applicable") and r.get("outcome") == "xpass"))
    print(f"Informe: {out_dir / 'report.md'}")
    if args.strict and applicable["fail"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

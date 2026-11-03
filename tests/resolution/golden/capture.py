"""
Golden master del motor de resolución (refactor de query_plan_builder sin cambiar comportamiento).

Corre en el arnés realista (Power BI simulado, `--llm fake`) todas las preguntas de:
  - tests/eval/questions.json      (banco del simulador; turnos de texto y botones)
  - tests/real/banco_real.json     (pregunta + clics como run_banco: «elegir», modelo, página o defecto)
  - tests/real/banco_holdout.json  (igual)

y guarda por turno: status, ruta, indicador, modelo, filtros, agrupación, DAX normalizado,
opciones de contrapregunta y la respuesta mostrada. Además el resultado de cada caso del banco
del simulador (pasa / falla) y la latencia por turno (solo informativa).

    python -X utf8 -m tests.resolution.golden.capture --out tests/resolution/golden/foto
    python -X utf8 -m tests.resolution.golden.capture --out <tmp> --compare tests/resolution/golden/foto
    python -X utf8 -m tests.resolution.golden.capture --banco eval --solo i_opcion_por_boton --out <tmp>

SIM_CACHE_DIR: si no está definida se usa %TEMP%/proyecto_rag_golden (caché propia: Qdrant local no
admite dos procesos sobre la misma carpeta).
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("SIM_CACHE_DIR", str(Path(tempfile.gettempdir()) / "proyecto_rag_golden"))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

BANCOS = {
    "eval": REPO_ROOT / "tests" / "eval" / "questions.json",
    "real": REPO_ROOT / "tests" / "real" / "banco_real.json",
    "holdout": REPO_ROOT / "tests" / "real" / "banco_holdout.json",
}
DEFAULT_FOTO = HERE / "foto"
NONE_ID = "__none__"
# Campos comparados (la latencia y el resultado del evaluador se guardan aparte).
TURN_FIELDS = ("input", "status", "route", "stage", "clarification_type", "metric", "metric_id",
               "semantic_model", "report", "dashboard", "result_type", "filters", "unapplied_terms",
               "group_by", "dax", "dax_log", "options", "prompt", "answer", "exception")


# ----------------------------------------------------------------------------
# Normalización
# ----------------------------------------------------------------------------

def norm_dax(text):
    return " ".join(str(text or "").split())


def _jsonable(value):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str, sort_keys=True))
    except Exception:
        return str(value)


_LATENCY_RE = re.compile(r"\b\d+[.,]\d+\s*s\b")


def norm_answer(text):
    text = str(text or "")
    return _LATENCY_RE.sub("<s>", text).strip()


def snapshot_turn(result, ui, buttons, question, latency):
    from tests.eval import expectations as ex
    result = result or {}
    sim = result.get("_sim") or {}
    filters = [
        {k: f.get(k) for k in ("type", "table", "column", "value", "values", "operator", "year", "month",
                               "start", "end", "date_range", "label") if f.get(k) is not None}
        for f in ex.applied_filters(result)
    ]
    dax_parts = [result.get("dax"), *ex.as_list(result.get("dax_queries"))]
    clar = result.get("clarification") or {}
    prompt = result.get("clarification_question") or (clar.get("question") if isinstance(clar, dict) else None)
    return {
        "input": question,
        "status": result.get("status"),
        "route": result.get("route"),
        "stage": result.get("stage"),
        "clarification_type": result.get("clarification_type"),
        "metric": result.get("metric"),
        "metric_id": result.get("metric_id"),
        "semantic_model": result.get("semantic_model"),
        "report": result.get("report"),
        "dashboard": result.get("dashboard"),
        "result_type": result.get("result_type"),
        "filters": _jsonable(filters),
        "unapplied_terms": ex.unapplied_terms(result),
        "group_by": ex.group_by_texts(result),
        "dax": [norm_dax(p) for p in dax_parts if p],
        "dax_log": [norm_dax(e.get("dax")) for e in ex.as_list(sim.get("dax_log")) if isinstance(e, dict)],
        "options": [{"id": str(b.get("id")), "label": b.get("label"), "caption": b.get("caption")}
                    for b in (buttons or [])],
        "prompt": prompt,
        "answer": norm_answer(ui),
        "exception": sim.get("exception"),
        "latency_s": round(latency, 3),
    }


# ----------------------------------------------------------------------------
# Corridas
# ----------------------------------------------------------------------------

class _Recorder:
    """Arnés que delega en tests.realistic.harness y guarda el último result crudo."""

    def __init__(self, harness):
        self._h = harness
        self.last = None

    def ask(self, engine, cm, formatter, text, quiet=True):
        result, ui = self._h.ask(engine, cm, formatter, text, quiet)
        self.last = (result, ui)
        return result, ui

    def ask_option(self, engine, cm, formatter, option_id, label=None, quiet=True):
        result, ui = self._h.choose(engine, cm, formatter, option_id, label, quiet)
        self.last = (result, ui)
        return result, ui

    def new_conversation(self, engine, cm):
        return self._h.new_conversation(engine, cm)


def _buttons(result):
    from src.chatbot.response_formatter import clarification_buttons
    return clarification_buttons(result) if (result or {}).get("status") == "needs_clarification" else []


def run_eval_case(case, system, recorder):
    """Igual que tests.eval.run.run_case (misma lógica de botones), guardando cada turno."""
    from tests.eval import run as evalrun
    from tests.eval import expectations as ex
    engine, cm, formatter = system[0], system[1], system[2]
    recorder.new_conversation(engine, cm)
    turns, buttons, aborted, passed_all = [], [], None, True
    for index, turn in enumerate(case["turns"], 1):
        if aborted:
            turns.append({"input": turn.get("user") or f"[botón] {turn.get('button')}", "skipped": aborted})
            passed_all = False
            continue
        option = None
        if "button" in turn:
            option = evalrun.resolve_button(turn["button"], buttons)
            if option is None and turn.get("opcional") and not buttons:
                turns.append({"input": f"[botón] {turn['button']}", "skipped": "opcional"})
                continue
            if option is None:
                aborted = f"botón {turn['button']!r} no disponible"
                turns.append({"input": f"[botón] {turn['button']}", "skipped": aborted})
                passed_all = False
                continue
            question = option["label"]
        else:
            question = turn["user"]
        started = time.perf_counter()
        try:
            result, ui = evalrun.ask(recorder, engine, cm, formatter, question, option)
        except Exception as error:
            result = {"status": "error", "error": str(error),
                      "_sim": {"exception": f"{type(error).__name__}: {error}"}}
            ui = ""
        latency = time.perf_counter() - started
        buttons = _buttons(result)
        original = case["turns"][0].get("user") or ""
        asked = original if original == question else f"{original}\n{question}"
        _kind, checks = ex.evaluate_turn(turn.get("expect") or {}, result, ui, buttons, question=asked,
                                         forbid=case.get("forbid"), allow=case.get("allow"))
        snap = snapshot_turn(result, ui, buttons, question, latency)
        snap["passed"] = ex.turn_passed(checks)
        passed_all = passed_all and snap["passed"]
        turns.append(snap)
    recorder.new_conversation(engine, cm)
    xfail = evalrun.xfail_reason(case, "realistic")
    return {"id": case["id"], "applicable": evalrun.is_applicable(case, "realistic"),
            "outcome": evalrun.outcome_of(passed_all, xfail), "turns": turns}


def _fold(text):
    import unicodedata
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(text.casefold().split())


def pick_button(buttons, spec):
    """Copia de tests.real.run_real.pick_button (sin importar run_real)."""
    if not buttons:
        return None
    text = str(spec).strip()
    if text.isdigit() and 1 <= int(text) <= len(buttons):
        return buttons[int(text) - 1]
    if text.casefold() in ("__none__", "ninguna"):
        return next((b for b in buttons if str(b["id"]) == NONE_ID), None)
    folded = _fold(text)
    if not folded:
        return None
    real = [b for b in buttons if str(b["id"]) != NONE_ID]
    for test in (lambda b: _fold(b["label"]) == folded,
                 lambda b: folded in _fold(b["label"]),
                 lambda b: folded in _fold(b.get("caption"))):
        for b in real:
            if test(b):
                return b
    return None


def choose_button(case, buttons):
    """Copia de tests.real.run_banco.choose_button."""
    verdad = case.get("verdad") or {}
    for target in (case.get("elegir"), verdad.get("modelo"), verdad.get("pagina")):
        if target:
            button = pick_button(buttons, target)
            if button is not None:
                return button
    return next((b for b in buttons if str(b["id"]) != NONE_ID), None)


def run_real_case(case, system, recorder):
    """Como tests.real.run_banco.run_case: pregunta, hasta 2 clics y turnos extra."""
    engine, cm, formatter = system[0], system[1], system[2]
    recorder.new_conversation(engine, cm)
    turns = []

    def turn(runner, question):
        started = time.perf_counter()
        try:
            result, ui = runner()
        except Exception as error:
            result = {"status": "error", "error": str(error),
                      "_sim": {"exception": f"{type(error).__name__}: {error}"}}
            ui = ""
        latency = time.perf_counter() - started
        buttons = _buttons(result)
        turns.append(snapshot_turn(result, ui, buttons, question, latency))
        return result, buttons

    result, buttons = turn(lambda: recorder.ask(engine, cm, formatter, case["pregunta"]), case["pregunta"])
    clicks = 0
    while result.get("status") == "needs_clarification" and buttons and clicks < 2:
        button = choose_button(case, buttons)
        if button is None:
            break
        result, buttons = turn(lambda b=button: recorder.ask_option(engine, cm, formatter, b["id"], b["label"]),
                               f"[botón] {button['label']}")
        clicks += 1
    for extra in case.get("turnos_extra") or []:
        text = extra[len("texto:"):].strip() if extra.startswith("texto:") else extra
        result, buttons = turn(lambda t=text: recorder.ask(engine, cm, formatter, t), text)
    recorder.new_conversation(engine, cm)
    return {"id": case["id"], "turns": turns}


def capture(bancos=("eval", "real", "holdout"), solo=(), progress=True):
    from tests.eval import run as evalrun
    from tests.realistic import harness
    recorder = _Recorder(harness)
    out = {}
    systems = {}

    def system_for(options):
        if options not in systems:
            # Un solo motor vivo (Qdrant local): se construye al cambiar de opciones.
            systems.clear()
            systems[options] = evalrun.build_system(harness, "realistic", "fake", synthetic_exclude=options)
        return systems[options]

    def wanted(case_id):
        return not solo or case_id in solo

    if "eval" in bancos:
        data = evalrun.load_questions(BANCOS["eval"])
        groups = {}
        for case in data.get("cases") or []:
            if wanted(case["id"]):
                groups.setdefault(evalrun.harness_options(case), []).append(case)
        results = {}
        # Primero el grupo sin exclusiones (lo reutilizan los bancos reales).
        for options in sorted(groups, key=lambda o: (len(o) > 0, o)):
            system = system_for(options)
            for case in groups[options]:
                try:
                    results[case["id"]] = run_eval_case(case, system, recorder)
                except Exception:
                    results[case["id"]] = {"id": case["id"], "error": traceback.format_exc()[-2000:], "turns": []}
                if progress:
                    print(f"[eval] {results[case['id']].get('outcome', 'error'):5s} {case['id']}", flush=True)
        out["eval"] = [results[c["id"]] for c in data.get("cases") or [] if c["id"] in results]
    for name in ("real", "holdout"):
        if name not in bancos:
            continue
        data = json.loads(BANCOS[name].read_text(encoding="utf-8"))
        system = system_for(())
        items = []
        for case in data["casos"]:
            if not wanted(case["id"]):
                continue
            try:
                items.append(run_real_case(case, system, recorder))
            except Exception:
                items.append({"id": case["id"], "error": traceback.format_exc()[-2000:], "turns": []})
            if progress:
                print(f"[{name}] {case['id']}", flush=True)
        out[name] = items
    return out


# ----------------------------------------------------------------------------
# Comparación
# ----------------------------------------------------------------------------

def load_foto(folder):
    folder = Path(folder)
    return {name: json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
            for name in BANCOS if (folder / f"{name}.json").exists()}


def save_foto(data, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, items in data.items():
        (folder / f"{name}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def compare(expected, actual, bancos=None):
    """Lista de diferencias legibles (vacía = idéntico)."""
    diffs = []
    for name in bancos or expected:
        if name not in actual:
            continue
        exp = {c["id"]: c for c in expected.get(name, [])}
        act = {c["id"]: c for c in actual.get(name, [])}
        for case_id in act:
            if case_id not in exp:
                diffs.append(f"{name}/{case_id}: caso nuevo (no está en la foto)")
                continue
            e, a = exp[case_id], act[case_id]
            if e.get("outcome") != a.get("outcome"):
                diffs.append(f"{name}/{case_id}: resultado {e.get('outcome')} -> {a.get('outcome')}")
            if bool(e.get("error")) != bool(a.get("error")):
                diffs.append(f"{name}/{case_id}: error del runner {e.get('error')!r} -> {a.get('error')!r}")
            et, at = e.get("turns") or [], a.get("turns") or []
            if len(et) != len(at):
                diffs.append(f"{name}/{case_id}: {len(et)} turnos -> {len(at)}")
            for i, (te, ta) in enumerate(zip(et, at), 1):
                for field in (*TURN_FIELDS, "skipped", "passed"):
                    if te.get(field) != ta.get(field):
                        diffs.append(f"{name}/{case_id} t{i} {field}: {_short(te.get(field))} -> "
                                     f"{_short(ta.get(field))}")
    return diffs


def _short(value, limit=300):
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


def latency_summary(data):
    values = [t["latency_s"] for items in data.values() for c in items for t in c.get("turns") or []
              if isinstance(t.get("latency_s"), (int, float))]
    if not values:
        return {}
    values.sort()
    return {"turnos": len(values), "total_s": round(sum(values), 1), "media_s": round(sum(values) / len(values), 3),
            "p95_s": values[int(0.95 * (len(values) - 1))]}


def eval_score(data):
    items = data.get("eval") or []
    applicable = [c for c in items if c.get("applicable")]
    return sum(1 for c in applicable if c.get("outcome") in ("pass", "xpass")), len(applicable)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--out", required=True, help="carpeta donde guardar la foto")
    parser.add_argument("--banco", default="eval,real,holdout")
    parser.add_argument("--solo", default="", help="ids separados por coma")
    parser.add_argument("--compare", help="foto de referencia para comparar")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    bancos = tuple(b.strip() for b in args.banco.split(",") if b.strip())
    solo = {s.strip() for s in args.solo.split(",") if s.strip()}
    started = time.perf_counter()
    data = capture(bancos, solo, progress=not args.quiet)
    save_foto(data, args.out)
    passed, total = eval_score(data)
    print(f"Capturado en {time.perf_counter() - started:.0f} s · simulador {passed}/{total} · "
          f"latencia {latency_summary(data)}")
    if args.compare:
        expected = load_foto(args.compare)
        diffs = compare(expected, data, bancos)
        print(f"Latencia de la foto: {latency_summary(expected)}")
        for d in diffs:
            print("DIF", d)
        print(f"{len(diffs)} diferencia(s)")
        return 1 if diffs else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

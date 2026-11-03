"""
Corre el banco MULTITURNO (tests/real/banco_multiturno.json) contra el sistema
real (Power BI de producción en solo lectura + MedGemma), con el mismo
build_system de app.py que run_banco y run_real: cada conversación empieza de
cero y los turnos siguientes conservan el contexto como en la interfaz
(reset_if_finished de app.py). Si un turno recibe una contrapregunta se pulsa
la opción de «elegir» (o la del modelo/página de la verdad), como run_banco.

La verdad de CADA turno se calcula justo antes de preguntarlo (los tableros
del día cambian) y se compara con run_banco.evaluate. El informe mide el
acierto por turno (total, por posición y por categoría), los seguimientos
cuyo turno anterior acertó (el contexto, aislado del primer turno) y el
acierto por conversación (todos sus turnos correctos).

    PowerShell (raíz del checkout principal):
      $env:POWERBI_AUTH="device_code"; .venv\\Scripts\\python.exe -X utf8 -m tests.real.run_multiturno
    python -X utf8 -m tests.real.run_multiturno --solo MT01,MT13
    python -X utf8 -m tests.real.run_multiturno --categoria periodo
    python -X utf8 -m tests.real.run_multiturno --sim              # Power BI simulado: valida el flujo
    python -X utf8 -m tests.real.run_multiturno --reevaluar tests/real/out_multiturno/<corrida>/resultados.json

Salida: tests/real/out_multiturno/multiturno_<fecha>/resultados.json y
resumen.md (no versionados). Sin filas de pacientes: la verdad solo usa
agregados y las respuestas pasan por run_real.redact().
"""
import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.real import env as real_env  # noqa: E402
from tests.real import run_banco  # noqa: E402

HERE = Path(__file__).resolve().parent
BANCO = HERE / "banco_multiturno.json"
OUT = HERE / "out_multiturno"


def load(path=None):
    return json.loads(Path(path or BANCO).read_text(encoding="utf-8"))["conversaciones"]


def turn_case(conv, turn):
    """El turno como un caso de run_banco (evaluate/classify/choose_button)."""
    return {"id": f"{conv['id']}.{turn['n']}", "tablero": turn["tablero"], "tipo": turn["tipo"],
            "pregunta": turn["entrada"], "verdad": turn.get("verdad"), "elegir": turn.get("elegir"),
            "contrapregunta_aceptable": bool(turn.get("contrapregunta_aceptable")),
            "esperado": turn.get("esperado"), "criterio": turn.get("criterio")}


def _error_turn(text, exc):
    return {"via": "texto", "text": text, "answer": None, "status": "error", "route": None,
            "error": f"{type(exc).__name__}: {exc}", "dax": [], "buttons": [], "seconds": 0}


def run_turn(case, run_real):
    """Mensaje del usuario + clics automáticos en las contrapreguntas (≤ 2)."""
    sub = []
    try:
        first, _ = run_real.ask(case["pregunta"])
        sub.append(first)
        clicks = 0
        while sub[-1]["status"] == "needs_clarification" and sub[-1]["buttons"] and clicks < 2:
            button, eleccion = run_banco.choose_button(case, sub[-1]["buttons"], run_real.pick_button)
            if button is None:
                break
            t, _ = run_real.choose(button["id"], button["label"])
            t["eleccion"] = eleccion
            sub.append(t)
            clicks += 1
    except Exception as exc:  # la conversación sigue con el turno siguiente
        sub.append(_error_turn(case["pregunta"], exc))
    return sub


def run_conversation(conv, run_real, with_truth=True):
    run_real.new_conversation()
    out = []
    for turn in conv["turnos"]:
        case = turn_case(conv, turn)
        truth = run_banco.compute_truths(case["verdad"]) if (with_truth and case.get("verdad")) else None
        sub = run_turn(case, run_real)
        out.append({"id": case["id"], "n": turn["n"], "entrada": turn["entrada"], "tipo": turn["tipo"],
                    "verdad": truth, "turnos": sub, "eval": run_banco.evaluate(case, sub, truth),
                    "segundos": round(sum(t.get("seconds") or 0 for t in sub), 1)})
    return out


# ---------------------------------------------------------------- evaluación
def turn_ok(t):
    """True/False/None: acierto = cifra correcta sin contrapregunta innecesaria."""
    ev = t["eval"]
    if ev["correcto"] is None:
        return None
    return bool(ev["correcto"]) and "contrapregunta" not in ev["fallas"]


def conv_ok(turns):
    """La conversación acierta si TODOS sus turnos evaluados aciertan; falla
    si alguno falla; inconclusa si ninguno falla pero alguno no se evaluó."""
    marks = [turn_ok(t) for t in turns]
    if any(m is False for m in marks):
        return False
    if not marks or any(m is None for m in marks):
        return None
    return True


def evaluate_all(results, convs):
    """Re-evalúa cada turno con el banco actual (sin volver a preguntar)."""
    by_turn = {f"{c['id']}.{t['n']}": (c, t) for c in convs for t in c["turnos"]}
    for r in results:
        for t in r["turnos"]:
            if t["id"] in by_turn:
                conv, turn = by_turn[t["id"]]
                t["eval"] = run_banco.evaluate(turn_case(conv, turn), t["turnos"], t.get("verdad"))
        r["correcto"] = conv_ok(r["turnos"])
    return results


def _rate(a, b):
    return {"aciertos": a, "evaluados": b, "pct": round(100 * a / b, 1) if b else None}


def summarize(results):
    tot = [0, 0]
    pos = defaultdict(lambda: [0, 0])
    cat_t = defaultdict(lambda: [0, 0])
    cat_c = defaultdict(lambda: [0, 0])
    seg = [0, 0]           # seguimientos (n ≥ 2)
    seg_ctx = [0, 0]       # seguimientos cuyo turno anterior acertó
    convs = [0, 0]
    fallas = Counter()
    inconclusas = []
    for r in results:
        prev = None
        for t in r["turnos"]:
            ok = turn_ok(t)
            if ok is not None:
                for bucket in (tot, pos[t["n"]], cat_t[r["categoria"]]):
                    bucket[0] += int(ok)
                    bucket[1] += 1
                if t["n"] >= 2:
                    seg[0] += int(ok)
                    seg[1] += 1
                    if prev is True:
                        seg_ctx[0] += int(ok)
                        seg_ctx[1] += 1
                for f in t["eval"]["fallas"]:
                    fallas[f] += 1
            prev = ok
        c = conv_ok(r["turnos"])
        if c is None:
            inconclusas.append(r["id"])
        else:
            convs[0] += int(c)
            convs[1] += 1
            cat_c[r["categoria"]][0] += int(c)
            cat_c[r["categoria"]][1] += 1
    return {
        "turnos": _rate(*tot),
        "por_posicion": {str(k): _rate(*v) for k, v in sorted(pos.items())},
        "seguimientos": _rate(*seg),
        "seguimientos_con_turno_previo_correcto": _rate(*seg_ctx),
        "conversaciones": _rate(*convs),
        "por_categoria": {k: {"turnos": _rate(*cat_t[k]), "conversaciones": _rate(*cat_c[k])}
                          for k in sorted(set(cat_t) | set(cat_c))},
        "fallas": {run_banco.FALLAS[k]: n for k, n in fallas.most_common()},
        "inconclusas": inconclusas,
    }


def _cell(rate):
    return f"{rate['aciertos']}/{rate['evaluados']}" + (f" ({rate['pct']:.0f} %)" if rate["pct"] is not None else "")


def write_summary(out_dir, results, meta):
    s = summarize(results)
    lines = ["# Banco multiturno: resultados", ""]
    lines += [f"- **{k}:** {v}" for k, v in meta.items()]
    lines += ["", "Acierto de un turno = cifra/agrupación correcta (verdad DAX de ESE turno) sin contrapregunta "
              "innecesaria. Conversación correcta = todos sus turnos correctos.", "",
              "| Medida | Aciertos |", "|---|---|",
              f"| Turnos | {_cell(s['turnos'])} |",
              f"| Seguimientos (turno ≥ 2) | {_cell(s['seguimientos'])} |",
              f"| Seguimientos con el turno anterior correcto | {_cell(s['seguimientos_con_turno_previo_correcto'])} |",
              f"| **Conversaciones** | **{_cell(s['conversaciones'])}** |", "",
              "| Turno n.º | Aciertos |", "|---|---|"]
    lines += [f"| {k} | {_cell(v)} |" for k, v in s["por_posicion"].items()]
    lines += ["", "| Categoría | Turnos | Conversaciones |", "|---|---|---|"]
    lines += [f"| {k} | {_cell(v['turnos'])} | {_cell(v['conversaciones'])} |" for k, v in s["por_categoria"].items()]
    lines += ["", "| Tipo de falla | Turnos |", "|---|---|"]
    lines += [f"| {k} | {n} |" for k, n in s["fallas"].items()]
    lines += ["", "## Conversaciones", "", "| Conv. | Categoría | Turno | Entrada | OK | Fallas | s | Respuesta (recorte) |",
              "|---|---|---|---|---|---|---|---|"]
    mark = {True: "sí", False: "no", None: "—"}
    for r in results:
        for t in r["turnos"]:
            last = t["turnos"][-1] if t["turnos"] else {}
            ans = (last.get("answer") or "").replace("\n", " ").replace("|", "/")[:120]
            lines.append(f"| {r['id']} ({mark[r['correcto']]}) | {r['categoria']} | {t['n']} | {t['entrada'][:60]} "
                         f"| {mark[turn_ok(t)]} | {', '.join(run_banco.FALLAS[f] for f in t['eval']['fallas'])} "
                         f"| {t['segundos']} | {ans} |")
    Path(out_dir, "resumen.md").write_text("\n".join(lines), encoding="utf-8")
    return s


def select(convs, args):
    if args.solo:
        wanted = {c.strip() for c in args.solo.split(",")}
        convs = [c for c in convs if c["id"] in wanted]
    if args.categoria:
        convs = [c for c in convs if c["categoria"] == args.categoria]
    return convs


def main(argv=None):
    parser = argparse.ArgumentParser(description="Banco multiturno (Power BI de producción, solo lectura).")
    parser.add_argument("--solo", help="ids de conversación separados por coma")
    parser.add_argument("--categoria", help="solo una categoría (periodo, agrupacion, filtro, ...)")
    parser.add_argument("--out", help="carpeta de salida")
    parser.add_argument("--reevaluar", help="resultados.json previo: recalcula la evaluación sin volver a preguntar")
    parser.add_argument("--sim", action="store_true", help="Power BI simulado + LLM falso (sin verdad ni producción)")
    parser.add_argument("--banco", help="banco JSON (por defecto tests/real/banco_multiturno.json)")
    args = parser.parse_args(argv)
    real_env.setup_env()
    convs = load(args.banco)

    if args.reevaluar:
        path = Path(args.reevaluar)
        data = json.loads(path.read_text(encoding="utf-8"))
        evaluate_all(data["resultados"], convs)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(json.dumps(write_summary(path.parent, data["resultados"], data["meta"]), ensure_ascii=False, indent=1))
        return 0

    from tests.real import run_real

    run_real.SIM["on"] = args.sim
    out_dir = Path(args.out) if args.out else OUT / ("multiturno_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    print("Construyendo el sistema (Power BI real + MedGemma)...", flush=True)
    run_real.build_system()
    meta = run_real.meta_info()
    meta["commit"] = run_banco._commit()
    meta["modo"] = "SIMULADO" if args.sim else "Power BI real"
    meta["banco"] = Path(args.banco or BANCO).name
    print(" · ".join(f"{k}: {v}" for k, v in meta.items()), flush=True)
    selected = select(convs, args)
    results = []
    for i, conv in enumerate(selected, 1):
        started = time.perf_counter()
        turns = run_conversation(conv, run_real, with_truth=not args.sim)
        results.append({"id": conv["id"], "categoria": conv["categoria"], "tablero": conv["tablero"],
                        "descripcion": conv["descripcion"], "turnos": turns, "correcto": conv_ok(turns),
                        "reloj_s": round(time.perf_counter() - started, 1)})
        marks = "".join({True: "✓", False: "✗", None: "·"}[turn_ok(t)] for t in turns)
        print(f"[{i}/{len(selected)}] {conv['id']} {conv['categoria']:10} {marks} "
              f"{[f for t in turns for f in t['eval']['fallas']]}", flush=True)
        (out_dir / "resultados.json").write_text(
            json.dumps({"meta": meta, "resultados": results}, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
    (out_dir / "resultados.json").write_text(
        json.dumps({"meta": meta, "resultados": results}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    s = write_summary(out_dir, results, meta)
    print(json.dumps({k: s[k] for k in ("turnos", "seguimientos", "conversaciones")}, ensure_ascii=False))
    print("Resultados en", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

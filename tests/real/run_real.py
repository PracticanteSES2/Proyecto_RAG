"""
Runner REAL sin navegador: el mismo sistema que app.py (build_system) con
Power BI de PRODUCCIÓN (solo lectura, token en caché sin ventana), MedGemma
real (del .env, lo lee la aplicación) y el RAG/catálogos de data/.

    python -X utf8 -m tests.real.run_real "cual es el nivel de ocupacion?"
    python -X utf8 -m tests.real.run_real "egresos" --then 1            # pulsa el botón 1
    python -X utf8 -m tests.real.run_real "egresos" --then "UCI"         # botón cuya etiqueta contiene «UCI»
    python -X utf8 -m tests.real.run_real "egresos" --then "texto: y en 2025?"   # mensaje nuevo
    python -X utf8 -m tests.real.run_real "..." --out tests/real/out/manual

Cada turno guarda: pregunta, respuesta (tal como la vería la UI), estado,
ruta, botones de contrapregunta, métrica/modelo, DAX enviados a Power BI
(modelo, estado, filas, error y tiempos; NUNCA las filas, salvo una fila de
valores numéricos agregados) y el razonamiento (format_reasoning_text).
Salida: <out>/conversacion.json y <out>/conversacion.md.

Privacidad: la respuesta guardada pasa por `redact()` (números de 6 o más
dígitos -> «[num]») por si el bot llegara a listar documentos o teléfonos.
"""
import argparse
import contextlib
import io
import json
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.real import env as real_env  # noqa: E402

SYSTEM = {}
SIM = {"on": False}   # --sim: Power BI simulado (tests/realistic) para validar el runner


def redact(text):
    if text is None:
        return None
    return re.sub(r"(?<![\d.,])\d{6,}(?![\d])", "[num]", str(text))


def _safe_first_row(result):
    rows = result.get("rows") or []
    if len(rows) != 1:
        return None
    row = rows[0]
    if all(isinstance(v, (int, float)) or v is None for v in row.values()):
        return row
    return None


def qdrant_copy(source):
    import shutil

    target = Path(__file__).resolve().parent / "out" / "_qdrant_copia"
    stamp = target / ".origen"

    def signature():
        files = sorted(p for p in source.rglob("*") if p.is_file() and p.name != ".lock")
        return json.dumps([[str(p.relative_to(source)), p.stat().st_size, int(p.stat().st_mtime)] for p in files])

    sig = signature()
    if not (stamp.exists() and stamp.read_text(encoding="utf-8") == sig):
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(".lock"))
        stamp.write_text(sig, encoding="utf-8")
    return target


def build_system(quiet=True):
    """Construye el sistema de app.py (una sola vez por proceso)."""
    if SYSTEM:
        return SYSTEM
    real_env.setup_env()
    from tests.realistic import harness

    started = time.perf_counter()
    if SIM["on"]:
        # Validación sin producción: mismo app.py con Power BI SIMULADO y LLM falso.
        import os
        os.environ.pop("POWERBI_AUTH", None)   # el simulador usa su propio ADOMD falso
        engine, cm, formatter, medgemma_status, connection, _ = harness.build_engine(llm="fake")
        ns = harness.STATE["ns"]
    else:
        harness._install_streamlit_stub()
        ns = harness.load_app_namespace(real_env.PROJECT_ROOT, env_root=None)
        # Qdrant local no admite dos clientes: si la app está abierta, la carpeta
        # está bloqueada. Se usa una COPIA de solo lectura (se renueva si cambia).
        ns["QDRANT_PATH"] = qdrant_copy(Path(ns["QDRANT_PATH"]))
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink if quiet else sys.stdout):
            engine, cm, formatter, medgemma_status, connection = ns["build_system"]()
    provider = engine.powerbi_provider
    log = []
    original = provider.execute_dax

    def logged_execute_dax(dax, semantic_model=None, timeout_s=None):
        t0 = time.perf_counter()
        result = original(dax, semantic_model, timeout_s=timeout_s)
        log.append({
            "semantic_model": result.get("semantic_model") or semantic_model,
            "dax": dax,
            "status": result.get("status"),
            "row_count": result.get("row_count"),
            "columns": result.get("columns"),
            "single_numeric_row": _safe_first_row(result),
            "error": (result.get("error") or "")[:600] or None,
            "seconds": round(time.perf_counter() - t0, 2),
        })
        return result

    provider.execute_dax = logged_execute_dax
    SYSTEM.update(
        ns=ns, engine=engine, cm=cm, formatter=formatter, log=log,
        medgemma=dict(medgemma_status or {}), powerbi=dict(connection or {}),
        build_s=round(time.perf_counter() - started, 1),
    )
    return SYSTEM


def new_conversation():
    s = build_system()
    s["cm"].reset()
    try:
        s["engine"].reset(full=True)
    except TypeError:
        s["engine"].reset()


def _turn(runner, text, via):
    from src.chatbot.reasoning_trace import format_reasoning_text
    from src.chatbot.response_formatter import clarification_buttons

    s = build_system()
    ns, engine = s["ns"], s["engine"]
    before = len(s["log"])
    sink = io.StringIO()
    error = None
    started = time.perf_counter()
    try:
        with contextlib.redirect_stdout(sink):
            result = runner()
            ui = ns["get_display_answer"](result, s["formatter"])
    except Exception as exc:  # igual que app.py
        error = f"{type(exc).__name__}: {exc}"
        result = {"status": "error", "route": None, "error": error,
                  "reasoning": getattr(engine, "last_reasoning", None),
                  "traceback": traceback.format_exc()[-3000:]}
        ui = "Ocurrió un error al procesar la consulta. Intenta nuevamente."
    seconds = round(time.perf_counter() - started, 1)
    buttons = clarification_buttons(result)
    try:
        reasoning = format_reasoning_text(result.get("reasoning"), ui)
    except Exception:
        reasoning = None
    turn = {
        "via": via,
        "text": text,
        "answer": redact(ui),
        "status": result.get("status"),
        "route": result.get("route"),
        "stage": result.get("stage"),
        "metric": result.get("metric"),
        "semantic_model": result.get("semantic_model"),
        "report": result.get("report"),
        "dashboard": result.get("dashboard"),
        "value": result.get("value") if isinstance(result.get("value"), (int, float, str, type(None))) else None,
        "buttons": [{"id": str(b["id"]), "label": b["label"], "caption": b.get("caption")} for b in buttons],
        "dax": [e for e in s["log"][before:]],
        "bot_dax": result.get("dax"),
        "error": error or result.get("error"),
        "seconds": seconds,
        "reasoning": redact(reasoning),
    }
    ns["reset_if_finished"](result, engine, s["cm"])
    return turn, buttons


def ask(text):
    engine = build_system()["engine"]
    return _turn(lambda: engine.process(text), text, "texto")


def choose(option_id, label):
    engine = build_system()["engine"]
    return _turn(lambda: engine.select_clarification_option(option_id, label), label, "botón")


def pick_button(buttons, spec):
    """spec: número (1 = primero), «__none__», o texto contenido en la etiqueta."""
    if not buttons:
        return None
    text = str(spec).strip()
    if text.isdigit() and 1 <= int(text) <= len(buttons):
        return buttons[int(text) - 1]
    if text.casefold() in ("__none__", "ninguna"):
        return next((b for b in buttons if str(b["id"]) == "__none__"), None)
    folded = _fold(text)
    for b in buttons:
        if folded and folded in _fold(b["label"]):
            return b
    return None


def _fold(text):
    import unicodedata
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(text.casefold().split())


def run_conversation(turns, new=True):
    """turns: [pregunta, respuesta2, ...]. Si hay botones pendientes, una
    respuesta que no empiece por «texto:» se interpreta como clic."""
    if new:
        new_conversation()
    out = []
    buttons = []
    for spec in turns:
        spec = str(spec)
        if buttons and not spec.startswith("texto:"):
            button = pick_button(buttons, spec)
            if button is not None:
                turn, buttons = choose(button["id"], button["label"])
                out.append(turn)
                continue
        text = spec[len("texto:"):].strip() if spec.startswith("texto:") else spec
        turn, buttons = ask(text)
        out.append(turn)
    return out


def to_markdown(turns, meta=None):
    lines = ["# Conversación (Power BI real)", ""]
    for key, value in (meta or {}).items():
        lines.append(f"- **{key}:** {value}")
    lines.append("")
    for i, t in enumerate(turns, 1):
        lines += [f"## Turno {i} ({t['via']}) · {t['seconds']} s", "", f"> {t['text']}", "", t["answer"] or "", ""]
        lines.append(f"Estado: `{t['status']}` · ruta: `{t['route']}` · métrica: `{t['metric']}` · modelo: `{t['semantic_model']}`")
        if t["buttons"]:
            lines += ["", "Opciones: " + " · ".join(b["label"] for b in t["buttons"])]
        for d in t["dax"]:
            lines += ["", f"DAX → {d['semantic_model']} ({d['status']}, filas={d['row_count']}, {d['seconds']} s)"
                      + (f" ERROR: {d['error']}" if d.get("error") else ""), "```dax", d["dax"].strip(), "```"]
        if t.get("reasoning"):
            lines += ["", "<details><summary>Razonamiento</summary>", "", "```text", t["reasoning"], "```", "</details>"]
        lines.append("")
    return "\n".join(lines)


def save(turns, out_dir, meta=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "conversacion.json").write_text(
        json.dumps({"meta": meta or {}, "turns": turns}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "conversacion.md").write_text(to_markdown(turns, meta), encoding="utf-8")
    return out_dir


def meta_info():
    s = build_system()
    return {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "MedGemma": f"{s['medgemma'].get('status')} ({s['medgemma'].get('model')})",
        "Power BI": s["powerbi"].get("status"),
        "construcción (s)": s["build_s"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Conversación contra el Power BI real (solo lectura).")
    parser.add_argument("question")
    parser.add_argument("--then", action="append", default=[],
                        help="siguiente turno: número/etiqueta de botón, __none__, o «texto: ...»")
    parser.add_argument("--out", default=None, help="carpeta de salida (por defecto tests/real/out/<fecha>)")
    parser.add_argument("--sim", action="store_true", help="Power BI simulado + LLM falso (validación sin producción)")
    args = parser.parse_args(argv)
    SIM["on"] = args.sim
    real_env.setup_env()
    print("Construyendo el sistema (Power BI real + MedGemma)...", flush=True)
    build_system()
    meta = meta_info()
    print(" · ".join(f"{k}: {v}" for k, v in meta.items()))
    turns = run_conversation([args.question] + args.then)
    for t in turns:
        print("\n" + "─" * 78)
        print(f">>> {t['text']}  ({t['via']}, {t['seconds']} s, {t['status']}/{t['route']})")
        print(t["answer"])
        for i, b in enumerate(t["buttons"], 1):
            print(f"  [{i}] {b['label']}")
        for d in t["dax"]:
            print(f"  [DAX {d['semantic_model']} {d['status']} filas={d['row_count']}]")
    out = args.out or (Path(__file__).resolve().parent / "out" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    print("\nGuardado en", save(turns, out, meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())

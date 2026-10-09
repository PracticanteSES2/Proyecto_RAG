"""
Chat por consola contra el sistema real con Power BI simulado (tests/realistic/harness.py).

    python -m tests.realistic.chat "¿Cuántos egresos hubo en 2025?"
    python -m tests.realistic.chat "total atenciones" --then 2              # pulsa el botón 2
    python -m tests.realistic.chat "cirugías realizadas" --then __none__    # «Ninguna de las anteriores»
    python -m tests.realistic.chat "egresos" --then 1 --then "y en 2024?"  # botón y luego texto
    python -m tests.realistic.chat --llm real                              # MedGemma real (.env)
    python -m tests.realistic.chat                                         # modo interactivo

Imprime la respuesta tal como la mostraría la UI, los botones de contrapregunta (con su
descripción), el razonamiento (format_reasoning_text) y, con --dax, las consultas DAX enviadas al
simulador (con aproximaciones y TYPE MISMATCH). Si hay contrapregunta y la entrada es una consola,
pregunta qué botón elegir.

--then: número (1 = primer botón), "__none__" / "ninguna", o cualquier otro texto (mensaje nuevo).
Nunca imprime valores del .env (solo el estado de MedGemma).
"""
import argparse
import os
import sys

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True


def _configure_console():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _print_status(llm_status, connection, simulator):
    note = llm_status.get("sim_note")
    state = llm_status.get("status")
    print(f"LLM ({llm_status.get('mode')}): {state}" + (f" — {note}" if note else "")
          + (f" — {llm_status.get('error')[:120]}" if state != "ready" and llm_status.get("error") else ""))
    print(f"Power BI (simulado): {connection.get('status')} — modelo por defecto "
          f"{connection.get('semantic_model')!r}; {len(simulator.list_models())} modelos en el workspace")


def _print_turn(result, ui, show_dax=False, show_reasoning=True):
    from src.chatbot.reasoning_trace import format_reasoning_text
    from src.chatbot.response_formatter import clarification_buttons

    print("\n" + "─" * 78)
    print(ui)
    buttons = clarification_buttons(result)
    if buttons:
        print("\nOpciones:")
        for index, button in enumerate(buttons, 1):
            print(f"  [{index}] {button['label']}" + (f"  [id={button['id']}]" if button["id"] == "__none__" else ""))
            if button.get("caption"):
                print(f"      {button['caption']}")
    sim = result.get("_sim") or {}
    if sim.get("exception"):
        print("\n[excepción del motor]", sim["exception"])
    if show_reasoning:
        text = format_reasoning_text(result.get("reasoning"), ui)
        if text:
            print("\n" + text)
    if show_dax:
        for entry in sim.get("dax_log", []):
            print(f"\n[DAX → {entry['semantic_model']}] filas={entry.get('rows')} "
                  f"{('ERROR: ' + entry['error']) if entry.get('error') else ''}")
            print(entry["dax"].strip())
            if entry.get("result"):
                print("  resultado:", entry["result"][:5])
            for approx in entry.get("approximate", []):
                print(f"  ~ aproximado: [{approx['measure']}] ({approx['reason'][:100]})")
            for message in entry.get("type_mismatch", []):
                print("  ! " + message)
    return buttons


def _resolve(answer, buttons):
    """(option_id, label) para un botón, o None si la respuesta es texto libre."""
    text = str(answer).strip()
    if text.isdigit() and buttons and 1 <= int(text) <= len(buttons):
        button = buttons[int(text) - 1]
        return button["id"], button["label"]
    if text.casefold() in ("__none__", "ninguna", "none", "ninguna de las anteriores"):
        button = next((b for b in buttons if b["id"] == "__none__"), None)
        return ("__none__", button["label"] if button else "Ninguna de las anteriores")
    return None


def main(argv=None):
    _configure_console()
    parser = argparse.ArgumentParser(description="Chat con el sistema real y Power BI simulado.")
    parser.add_argument("question", nargs="?", help="pregunta inicial (sin ella: modo interactivo)")
    parser.add_argument("--llm", choices=("fake", "real"), default="fake")
    parser.add_argument("--then", action="append", default=[], help="respuesta siguiente (número, __none__ o texto)")
    parser.add_argument("--data-root", default=None, help="carpeta data/ (por defecto la del repo principal)")
    parser.add_argument("--no-synthetic", action="store_true", help="sin los modelos sintéticos del overlay")
    parser.add_argument("--powerbi-down", action="store_true", help="simula el endpoint XMLA caído")
    parser.add_argument("--dax", action="store_true", help="muestra las consultas DAX y su resultado")
    parser.add_argument("--no-reasoning", action="store_true", help="no imprime el razonamiento")
    parser.add_argument("--culture", default="es-CO", choices=("es-CO", "en-US", "invariant"))
    args = parser.parse_args(argv)

    from tests.realistic import harness
    print("Construyendo el sistema (la primera vez se arma la caché del overlay)...", flush=True)
    engine, cm, formatter, llm_status, connection, _ = harness.build_engine(
        data_root=args.data_root, llm=args.llm, synthetic=not args.no_synthetic,
        powerbi_up=not args.powerbi_down, culture=args.culture)
    _print_status(llm_status, connection, harness.STATE["simulator"])

    interactive = sys.stdin.isatty()
    pending = [args.question] if args.question else []
    pending += args.then
    buttons = []
    show = {"show_dax": args.dax, "show_reasoning": not args.no_reasoning}

    def step(answer):
        nonlocal buttons
        option = _resolve(answer, buttons) if buttons else None
        print(f"\n>>> {answer}" + (f"  (botón: {option[1]})" if option else ""))
        if option:
            result, ui = harness.choose(engine, cm, formatter, option[0], option[1])
        else:
            result, ui = harness.ask(engine, cm, formatter, answer)
        buttons = _print_turn(result, ui, **show)

    for answer in pending:
        step(answer)
    if not interactive:
        return 0
    if pending and not buttons:
        return 0
    while True:
        prompt = "\nElige opción (número / __none__) o escribe (Enter para salir): " if buttons else "\nTú: "
        try:
            answer = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if not answer:
            return 0
        step(answer)
        if args.question and not buttons:
            return 0


if __name__ == "__main__":
    sys.exit(main())

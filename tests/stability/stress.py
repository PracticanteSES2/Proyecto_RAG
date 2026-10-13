"""
Prueba de resistencia: muchas conversaciones seguidas (con «Nueva
conversación» entre una y otra, como la app) contra el Power BI simulado de
tests/sim y un MedGemma FALSO por HTTP (tests/stability/fake_ollama_server.py)
lento y variable, con capacidad limitada (como OLLAMA_NUM_PARALLEL) y que a
veces supera los tiempos límite.

Se usa el MedGemmaProvider y el cliente `ollama` REALES (httpx), así que se
mide lo que pasa con las conexiones: si al vencer un tiempo límite la
petición queda abierta, el servidor falso sigue «generando» y ocupa un hueco
(como Ollama); si se cierra, la cancela.

Por conversación se mide: latencia de los turnos, hilos vivos de más,
generaciones vivas en el servidor al terminar (abandonadas) y llamadas
cortadas o canceladas. Funciona también con el código de `desarrollo`
(antes de los cambios de estabilidad) para comparar.

    python -m tests.stability.stress                 # 12 conversaciones
    python -m tests.stability.stress --conversations 15 --json salida.json
"""
import argparse
import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# El cliente Ollama REAL se importa antes de que tests/sim lo sustituya.
import ollama as real_ollama  # noqa: E402

from tests.stability.fake_ollama_server import FakeOllamaServer, variable_delay  # noqa: E402

# Una conversación: documental (síntesis RAG), numérica ambigua (descriptor de
# opciones), elección, seguimiento que necesita la reescritura con el LLM y
# otra documental.
CONVERSATION = [
    "¿Qué muestra el tablero de atenciones?",
    "cuantas cirugias hubo en 2024",
    "1",
    "cirugias programadas en 2024",
    "pero lo que operaron los colegas de urologia",
    "¿Cómo se calcula el porcentaje de participación del peso en la lavandería?",
]


def _runtime_stats():
    try:
        from src.chatbot.runtime_stats import STATS
        return STATS
    except ImportError:  # código anterior a los cambios de estabilidad
        return None


def _wire_llm(engine, provider, synth_timeout, rewrite_timeout, describe_timeout):
    synthesizer = engine.rag_answer_engine.answer_synthesizer
    synthesizer.llm_provider = provider
    synthesizer.timeout_seconds = synth_timeout
    describer = getattr(engine, "option_describer", None)
    if describer is not None:
        describer.llm_provider = provider
        describer.timeout = describe_timeout  # sin efecto en el código anterior
    engine.context_llm = provider
    from src.chatbot import contextual_rewriter
    init = contextual_rewriter.LLMContextRewriter.__init__
    defaults = list(init.__defaults__)
    defaults[0] = rewrite_timeout  # timeout=8.0 -> escala de la prueba
    init.__defaults__ = tuple(defaults)


def _extra_threads(baseline):
    # Los hilos del servidor falso (uno por conexión HTTP) no cuentan: son
    # del «servidor Ollama», no de la app.
    alive = [t for t in threading.enumerate()
             if t.ident not in baseline and t.is_alive() and "process_request" not in t.name]
    names = {}
    for thread in alive:
        base = "".join("N" if c.isdigit() else c for c in thread.name)
        names[base] = names.get(base, 0) + 1
    return len(alive), names


def _drive(engine, cm, formatter, server, harness, conversations, log):
    stats = _runtime_stats()
    baseline = {t.ident for t in threading.enumerate()}
    rows = []
    for number in range(1, conversations + 1):
        harness.new_conversation(engine, cm)
        before = server.snapshot()
        latencies = []
        for text in CONVERSATION:
            started = time.perf_counter()
            harness.ask(engine, cm, formatter, text)
            latencies.append(time.perf_counter() - started)
        # Margen para que el servidor note un cierre recién hecho (sondea cada
        # 20 ms): lo que siga vivo después es trabajo abandonado de verdad.
        time.sleep(0.3)
        after = server.snapshot()
        extra, names = _extra_threads(baseline)
        row = {
            "conversation": number,
            "total_s": round(sum(latencies), 2),
            "max_turn_s": round(max(latencies), 2),
            "mean_turn_s": round(statistics.mean(latencies), 2),
            "extra_threads": extra,
            "thread_names": names,
            "server_live": after["active"] + after["queued"],
            "server_completed": after["completed"] - before["completed"],
            "server_cancelled": (after["cancelled_queued"] + after["cancelled_generating"])
            - (before["cancelled_queued"] + before["cancelled_generating"]),
            "server_requests": after["received"] - before["received"],
        }
        if stats is not None:
            snap = stats.snapshot()
            row["llm_in_flight"] = snap["llm"]["in_flight"]
            row["llm_timeouts_total"] = snap["llm"]["timeouts"]
            row["llm_saturated_total"] = snap["llm"]["saturated"]
        rows.append(row)
        if log:
            log(
                f"conv {number:2d} · total {row['total_s']:6.2f} s · turno máx {row['max_turn_s']:5.2f} s"
                f" · hilos de más {extra:2d} · vivas en el servidor {row['server_live']:2d}"
                f" · peticiones {row['server_requests']:2d} · canceladas {row['server_cancelled']:2d}"
                + (f" · agotadas (acum.) {row.get('llm_timeouts_total')}"
                   f" · saturadas (acum.) {row.get('llm_saturated_total')}" if stats is not None else "")
            )
    residual = _extra_threads(baseline), server.snapshot()
    return rows, residual


def run(conversations=12, parallel=2, scale=1.0, seed=7, synth_timeout=2.0,
        rewrite_timeout=0.8, describe_timeout=1.5, log=print):
    from tests.sim import harness

    delay = variable_delay(seed=seed, per_token_s=0.004 * scale, base_s=0.3 * scale)
    with FakeOllamaServer(delay_fn=delay, parallel=parallel) as server:
        engine, cm, formatter, _status, _pbi, _dax = harness.build_engine()
        from src.chatbot import contextual_rewriter
        from src.llm import medgemma_provider

        # Parches de proceso: se restauran al terminar (otras pruebas del
        # mismo proceso usan el Ollama falso de tests/sim).
        originals = (medgemma_provider.Client, medgemma_provider.ResponseError,
                     contextual_rewriter.LLMContextRewriter.__init__.__defaults__)
        try:
            medgemma_provider.Client = real_ollama.Client
            medgemma_provider.ResponseError = real_ollama.ResponseError
            provider = medgemma_provider.MedGemmaProvider(
                host=server.url, model="medgemma:latest", timeout=180,
            )
            _wire_llm(engine, provider, synth_timeout, rewrite_timeout, describe_timeout)
            rows, ((residual_threads, residual_names), residual_server) = _drive(
                engine, cm, formatter, server, harness, conversations, log,
            )
        finally:
            medgemma_provider.Client, medgemma_provider.ResponseError = originals[:2]
            contextual_rewriter.LLMContextRewriter.__init__.__defaults__ = originals[2]
        # Se espera a que el servidor quede libre (limpieza), sin medirlo.
        deadline = time.time() + 60
        while time.time() < deadline:
            snap = server.snapshot()
            if snap["active"] + snap["queued"] == 0:
                break
            time.sleep(0.1)

    first = rows[: max(1, len(rows) // 4)]
    last = rows[-max(1, len(rows) // 4):]
    summary = {
        "conversations": len(rows),
        "first_quarter_mean_total_s": round(statistics.mean(r["total_s"] for r in first), 2),
        "last_quarter_mean_total_s": round(statistics.mean(r["total_s"] for r in last), 2),
        "max_extra_threads": max(r["extra_threads"] for r in rows),
        "max_server_live": max(r["server_live"] for r in rows),
        "residual_extra_threads": residual_threads,
        "residual_thread_names": residual_names,
        "residual_server_live": residual_server["active"] + residual_server["queued"],
        "server_totals": residual_server,
    }
    return {"rows": rows, "summary": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--conversations", type=int, default=12)
    parser.add_argument("--parallel", type=int, default=2, help="generaciones simultáneas del servidor falso")
    parser.add_argument("--scale", type=float, default=1.0, help="multiplica la duración de las generaciones")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--json", help="guarda filas y resumen en este archivo")
    args = parser.parse_args()
    os.environ.setdefault("MEDGEMMA_TIMEOUT", "180")
    report = run(conversations=args.conversations, parallel=args.parallel, scale=args.scale, seed=args.seed)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

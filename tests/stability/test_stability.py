"""
Pruebas de estabilidad: llamadas al LLM con tiempo límite real (la conexión se
cierra y el servidor deja de generar), semáforo y saturación, un turno a la
vez, diagnóstico del servidor, reconexión de Power BI visible y una prueba de
resistencia corta (tests/stability/stress.py).

Ejecutar:
  PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 python -m tests.stability.test_stability
"""
import os
import sys
import threading
import time
import traceback
import types
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# El .env nunca se lee: dotenv falso antes de importar src.* (MedGemmaProvider
# llama a load_dotenv(), que buscaría el .env subiendo por las carpetas).
if "dotenv" not in sys.modules:
    _dotenv = types.ModuleType("dotenv")
    _dotenv.load_dotenv = lambda *a, **k: False
    _dotenv.find_dotenv = lambda *a, **k: ""
    _dotenv.__sim_fake__ = True
    sys.modules["dotenv"] = _dotenv
assert getattr(sys.modules["dotenv"], "__sim_fake__", False), "dotenv debe estar stubbeado"

import ollama as real_ollama  # noqa: E402  (cliente real, antes de tests/sim)

from tests.stability.fake_ollama_server import FakeOllamaServer  # noqa: E402

MESSAGES = [{"role": "user", "content": "hola"}]


def _wait(predicate, seconds=3.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _provider(url, **kwargs):
    from src.llm import medgemma_provider
    # tests/sim puede haber cambiado el módulo `ollama`: se usa el real.
    medgemma_provider.Client = real_ollama.Client
    medgemma_provider.ResponseError = real_ollama.ResponseError
    return medgemma_provider.MedGemmaProvider(host=url, model="medgemma:latest", timeout=180, **kwargs)


# ----------------------------------------------------------------------------
# 1. Tiempo límite real a nivel HTTP
# ----------------------------------------------------------------------------

def test_medgemma_timeout_closes_connection_and_server_stops():
    with FakeOllamaServer(delay_fn=lambda request: 5.0, parallel=1) as server:
        provider = _provider(server.url)
        started = time.perf_counter()
        result = provider.chat(MESSAGES, max_tokens=50, timeout=0.6)
        elapsed = time.perf_counter() - started
        assert result["status"] == "llm_timeout", result
        assert elapsed < 2.0, elapsed
        # El servidor nota que el cliente cerró la conexión y deja de generar.
        assert _wait(lambda: server.snapshot()["cancelled_generating"] == 1), server.snapshot()
        assert server.snapshot()["active"] == 0 and server.snapshot()["completed"] == 0


def test_medgemma_success_reuses_client_per_timeout():
    with FakeOllamaServer(delay_fn=lambda request: 0.05) as server:
        provider = _provider(server.url)
        first = provider.chat(MESSAGES, timeout=5)
        second = provider.chat(MESSAGES, timeout=5)
        assert first["status"] == second["status"] == "success" and first["answer"] == "OK"
        assert len(provider._clients) == 1
        assert provider.healthcheck()["status"] == "ready"


def test_option_describer_has_own_timeout_and_cancels():
    from src.chatbot.option_describer import OptionDescriber
    with FakeOllamaServer(delay_fn=lambda request: 4.0, parallel=3) as server:
        describer = OptionDescriber(_provider(server.url), timeout=0.6)
        options = [{"id": f"o{i}", "label": f"INDICADOR {i}"} for i in range(3)]
        started = time.perf_counter()
        outcome = describer.describe("pregunta", options)
        assert time.perf_counter() - started < 2.5
        assert outcome["descriptions"] == {} and outcome["status"] == "llm_timeout", outcome
        assert _wait(lambda: server.snapshot()["cancelled_generating"] == 3), server.snapshot()


def test_rewriter_timeout_closes_connection():
    from src.chatbot.contextual_rewriter import LLMContextRewriter
    with FakeOllamaServer(delay_fn=lambda request: 4.0) as server:
        rewriter = LLMContextRewriter(_provider(server.url), timeout=0.5)
        outcome = rewriter.rewrite("y en urologia?", "Usuario: cirugias 2024", "cirugias 2024")
        assert outcome["status"] == "timeout", outcome
        assert _wait(lambda: server.snapshot()["cancelled_generating"] == 1), server.snapshot()


# ----------------------------------------------------------------------------
# 2. Semáforo, saturación y degradación rápida de la síntesis RAG
# ----------------------------------------------------------------------------

class _BlockingProvider:
    enforces_timeout = True

    def __init__(self):
        self.release = threading.Event()

    def chat(self, messages, timeout=None, **kwargs):
        self.release.wait(timeout or 10)
        return {"status": "success", "answer": "ok", "model": "fake"}


def _occupy(provider, count):
    from src.llm.llm_gate import call_llm
    threads = [threading.Thread(target=call_llm, args=(provider, MESSAGES),
                                kwargs={"timeout": 10, "purpose": "prueba"}) for _ in range(count)]
    for thread in threads:
        thread.start()
    return threads


def test_gate_reports_saturation_quickly():
    from src.chatbot.runtime_stats import STATS
    from src.llm.llm_gate import call_llm
    os.environ["MEDGEMMA_MAX_CONCURRENT"] = "2"
    provider = _BlockingProvider()
    threads = _occupy(provider, 2)
    try:
        assert _wait(lambda: STATS.snapshot()["llm"]["in_flight"] >= 2)
        saturated_before = STATS.snapshot()["llm"]["saturated"]
        started = time.perf_counter()
        result = call_llm(provider, MESSAGES, purpose="prueba", timeout=10, queue_wait=0.3)
        assert result["status"] == "llm_saturated", result
        assert time.perf_counter() - started < 1.0
        assert STATS.snapshot()["llm"]["saturated"] == saturated_before + 1
    finally:
        provider.release.set()
        for thread in threads:
            thread.join(5)
        os.environ.pop("MEDGEMMA_MAX_CONCURRENT", None)
    assert _wait(lambda: STATS.snapshot()["llm"]["in_flight"] == 0)


def test_rag_synthesis_degrades_fast_when_llm_is_saturated():
    from src.chatbot.answer_synthesizer import AnswerSynthesizer
    from src.chatbot.rag_answer_engine import RAGAnswerEngine
    os.environ["MEDGEMMA_MAX_CONCURRENT"] = "1"
    os.environ["MEDGEMMA_QUEUE_WAIT"] = "0.3"
    provider = _BlockingProvider()
    threads = _occupy(provider, 1)
    try:
        time.sleep(0.1)
        synthesizer = AnswerSynthesizer(provider, timeout_seconds=40)
        sources = [{"text": "El tablero muestra las cirugías programadas.", "chunk_type": "dashboard_overview",
                    "dashboard": "QUIRURGICO", "score": 0.9}]
        engine = RAGAnswerEngine(retriever=None, answer_synthesizer=synthesizer)
        started = time.perf_counter()
        answer, mode, _ = engine._synthesize_answer("¿qué muestra el tablero?", sources)
        assert time.perf_counter() - started < 1.5
        assert mode == "extractive" and answer, (mode, answer)
        assert "saturado" in (engine.last_synthesis_issue or ""), engine.last_synthesis_issue
    finally:
        provider.release.set()
        for thread in threads:
            thread.join(5)
        os.environ.pop("MEDGEMMA_MAX_CONCURRENT", None)
        os.environ.pop("MEDGEMMA_QUEUE_WAIT", None)


def test_provider_without_own_timeout_is_counted_as_abandoned():
    from src.chatbot.runtime_stats import STATS
    from src.llm.llm_gate import call_llm

    class Slow:
        def chat(self, messages, **kwargs):
            time.sleep(0.5)
            return {"status": "success", "answer": "tarde"}

    before = STATS.snapshot()["llm"]
    result = call_llm(Slow(), MESSAGES, purpose="prueba", timeout=0.1)
    assert result["status"] == "llm_timeout"
    after = STATS.snapshot()["llm"]
    assert after["abandoned"] == before["abandoned"] + 1 and after["in_flight"] >= 1
    # Al terminar la llamada abandonada se libera su hueco.
    assert _wait(lambda: STATS.snapshot()["llm"]["in_flight"] == before["in_flight"], 2)


# ----------------------------------------------------------------------------
# 3. Un turno a la vez
# ----------------------------------------------------------------------------

def test_turn_slot_waits_reports_and_gives_up():
    from src.chatbot.runtime_stats import TurnBusy, turn_slot
    holding = threading.Event()
    release = threading.Event()

    def holder():
        with turn_slot("primera"):
            holding.set()
            release.wait(5)

    thread = threading.Thread(target=holder)
    thread.start()
    holding.wait(2)
    waits = []
    try:
        with turn_slot("segunda", on_wait=lambda waited, since: waits.append((waited, since)),
                       max_wait=0.6, poll_s=0.1):
            raise AssertionError("no debía entrar")
    except TurnBusy as busy:
        assert busy.holder and busy.holder["text"] == "primera"
    assert waits and waits[-1][1] is not None
    release.set()
    thread.join(5)
    # Libre otra vez: entra sin esperar.
    with turn_slot("tercera", max_wait=0.1):
        pass


def test_turn_slot_is_released_when_streamlit_aborts_the_run():
    from src.chatbot.runtime_stats import TURN_LOCK, turn_slot

    class StopException(BaseException):  # como las de control de Streamlit
        pass

    try:
        with turn_slot("abortada"):
            raise StopException()
    except StopException:
        pass
    assert not TURN_LOCK.locked()


# ----------------------------------------------------------------------------
# 4-5. Diagnóstico en el razonamiento, Power BI visible y exportación
# ----------------------------------------------------------------------------

def _sim():
    from tests.sim import harness
    engine, cm, formatter, _status, _pbi, _dax = harness.build_engine()
    return harness, engine, cm, formatter


def test_reasoning_has_server_state_and_degradation_step():
    from src.chatbot.reasoning_trace import format_reasoning_text
    harness, engine, cm, formatter = _sim()
    synthesizer = engine.rag_answer_engine.answer_synthesizer
    original = synthesizer.llm_provider, synthesizer.timeout_seconds

    class Timeout:
        enforces_timeout = True

        def chat(self, messages, timeout=None, **kwargs):
            return {"status": "llm_timeout", "answer": None, "timeout_seconds": timeout}

    try:
        synthesizer.llm_provider, synthesizer.timeout_seconds = Timeout(), 3
        harness.new_conversation(engine, cm)
        result, ui = harness.ask(engine, cm, formatter, "¿Qué muestra el tablero de atenciones?")
    finally:
        synthesizer.llm_provider, synthesizer.timeout_seconds = original
    text = format_reasoning_text(result["reasoning"], ui)
    assert "Estado al empezar: encendido hace" in text and "MedGemma" in text, text[:600]
    steps = [step["title"] for step in result["reasoning"]["steps"]]
    assert "Estado al terminar (degradado)" in steps, steps
    assert "agotaron su tiempo límite" in text and "resumen extractivo" in text, text


def test_powerbi_reconnection_is_visible_and_counted():
    from src.chatbot.runtime_stats import STATS
    harness, engine, cm, formatter = _sim()
    provider = engine.powerbi_provider
    events = []
    engine.set_progress_listener(events.append)
    try:
        harness.new_conversation(engine, cm)
        harness.ask(engine, cm, formatter, "cuanto peso hubo en lavanderia en enero de 2026")
        for connection in list(provider._connections.values()):
            connection.Close()  # p. ej. perdida tras cancelar por CommandTimeout
        before = STATS.snapshot()["powerbi"]["reopened"]
        harness.new_conversation(engine, cm)
        result, _ = harness.ask(engine, cm, formatter, "cuanto peso hubo en lavanderia en enero de 2026")
    finally:
        engine.set_progress_listener(None)
    titles = [event["title"] for event in events if event.get("kind") == "activity"]
    assert any(t.startswith("Reabriendo conexión con Power BI") and "inicio de sesión" in t
               for t in titles), titles
    assert STATS.snapshot()["powerbi"]["reopened"] > before
    assert provider.connection_events[-1]["kind"] == "reconexión"
    steps = [step["title"] for step in result["reasoning"]["steps"]]
    assert "Estado al terminar (degradado)" in steps, steps


def test_diagnostics_and_export_header():
    from src.chatbot.conversation_export import export_conversation_markdown
    from src.chatbot.runtime_stats import STATS, diagnostics_lines, status_line
    snapshot = STATS.snapshot()
    lines = "\n".join(diagnostics_lines(snapshot))
    for needle in ("Encendido", "Turnos atendidos", "MedGemma", "Power BI, conexiones abiertas",
                   "Caché de dominios", "Hilos vivos"):
        assert needle in lines, needle
    exported = export_conversation_markdown(
        [{"role": "user", "content": "hola"}],
        meta={"Estado del servidor": status_line(snapshot)},
    )
    assert "- Estado del servidor: encendido hace" in exported, exported


def test_app_shows_diagnostics_and_busy_message():
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        print("  (Streamlit no instalado: se omite)")
        return
    from src.chatbot.runtime_stats import TURN_LOCK
    app = AppTest.from_file(str(ROOT / "tests" / "realistic" / "run_app.py"), default_timeout=300)
    app.run()
    assert any(e.label == "Diagnóstico del servidor" for e in app.expander), [e.label for e in app.expander]
    os.environ["TURN_WAIT_SECONDS"] = "1"
    TURN_LOCK.acquire()
    try:
        app.chat_input[0].set_value("cuanto peso hubo en lavanderia en enero de 2026").run()
    finally:
        TURN_LOCK.release()
        os.environ.pop("TURN_WAIT_SECONDS", None)
    assert not app.exception, app.exception
    texts = " ".join(m.value for m in app.markdown)
    assert "Hay otra consulta en curso" in texts, texts[-500:]
    assert "Esperando a que termine otra consulta en curso" in texts, texts[-800:]
    # Libre otra vez: responde normal.
    app.chat_input[0].set_value("cuanto peso hubo en lavanderia en enero de 2026").run()
    labels = [element.proto.label for element in app.get("status")]
    assert any(label.startswith("Listo en") for label in labels), labels


# ----------------------------------------------------------------------------
# 6. Resistencia (corta)
# ----------------------------------------------------------------------------

def test_stress_latency_does_not_grow_and_nothing_accumulates():
    from tests.stability import stress
    report = stress.run(conversations=8, scale=0.6, log=None)
    summary = report["summary"]
    assert summary["residual_server_live"] == 0, summary
    assert summary["max_server_live"] <= 1, summary
    llm_threads = {name: count for name, count in summary["residual_thread_names"].items()
                   if "rag" in name or "llm" in name or "(run)" in name}
    assert not llm_threads, summary["residual_thread_names"]
    assert summary["last_quarter_mean_total_s"] <= summary["first_quarter_mean_total_s"] * 1.5 + 1, summary


def _run_app_test_in_subprocess():
    """La prueba con AppTest corre en otro proceso: tests/realistic (app) y
    tests/sim instalan módulos falsos distintos en sys.modules."""
    import subprocess
    completed = subprocess.run(
        [sys.executable, "-m", "tests.stability.test_stability", "--solo-app"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8"),
    )
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-40:])
        raise AssertionError(f"la prueba con AppTest falló:\n{tail}")


def main():
    only_app = "--solo-app" in sys.argv
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    if only_app:
        tests = [(n, f) for n, f in tests if n.startswith("test_app_")]
    else:
        tests = [(n, f) for n, f in tests if not n.startswith("test_app_")]
        tests.insert(0, ("test_app_shows_diagnostics_and_busy_message", _run_app_test_in_subprocess))
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failed += 1
            traceback.print_exc()
            print(f"FAIL  {name}")
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""
Fila justa (FIFO) de la puerta del LLM y del turno, con posición consultable
(src/llm/llm_gate.py, src/chatbot/runtime_stats.py).

    .venv\\Scripts\\python.exe -X utf8 -m unittest tests.perf.test_cola_justa

No usa red, .env, Ollama ni Power BI.
"""
import os
import sys
import threading
import time
import types
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# El .env nunca se lee (MedGemmaProvider llama a load_dotenv()).
if "dotenv" not in sys.modules:
    _dotenv = types.ModuleType("dotenv")
    _dotenv.load_dotenv = lambda *a, **k: False
    _dotenv.find_dotenv = lambda *a, **k: ""
    _dotenv.__sim_fake__ = True
    sys.modules["dotenv"] = _dotenv

from src.chatbot import runtime_stats  # noqa: E402
from src.chatbot.runtime_stats import STATS, TURN_LOCK, TurnBusy, queue_snapshot, turn_slot  # noqa: E402
from src.llm import llm_gate  # noqa: E402
from src.llm.llm_gate import call_llm, queue_state, ui_progress  # noqa: E402

MESSAGES = [{"role": "user", "content": "hola"}]


def _wait(predicate, seconds=3.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class _Env:
    def __init__(self, **values):
        self.values = values
        self.saved = {}

    def __enter__(self):
        for key, value in self.values.items():
            self.saved[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)

    def __exit__(self, *exc):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class GateProvider:
    """Doble que retiene cada llamada hasta que se le abra la compuerta y
    registra el orden de entrada (la etiqueta va en el mensaje)."""

    enforces_timeout = True

    def __init__(self):
        self.release = threading.Event()
        self.order = []
        self.lock = threading.Lock()
        self.received_timeouts = []

    def chat(self, messages, timeout=None, **kwargs):
        with self.lock:
            self.order.append(messages[0]["content"])
            self.received_timeouts.append(timeout)
        self.release.wait(10)
        return {"status": "success", "answer": "ok", "model": "falso"}


class OneByOne:
    """Cada llamada termina cuando se le da paso (una a una)."""

    enforces_timeout = True

    def __init__(self):
        self.step = threading.Semaphore(0)
        self.order = []
        self.lock = threading.Lock()

    def chat(self, messages, timeout=None, **kwargs):
        with self.lock:
            self.order.append(messages[0]["content"])
        self.step.acquire(timeout=10)
        return {"status": "success", "answer": "ok"}


def _call_in_thread(provider, label, results, **kwargs):
    def run():
        results[label] = call_llm(provider, [{"role": "user", "content": label}], purpose="prueba", **kwargs)
    thread = threading.Thread(target=run, name=f"prueba-{label}")
    thread.start()
    return thread


class FairGateTests(unittest.TestCase):
    def setUp(self):
        self.env = _Env(MEDGEMMA_MAX_CONCURRENT="2", MEDGEMMA_QUEUE_WAIT="5")
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__()
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 0 and queue_state()["waiting"] == 0, 5),
                        queue_state())

    def test_waiting_calls_enter_in_arrival_order(self):
        provider = OneByOne()
        results, threads = {}, []
        # Dos ocupan la capacidad; cinco más esperan, llegando en orden.
        for label in ("a", "b"):
            threads.append(_call_in_thread(provider, label, results, timeout=20))
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 2))
        waiting = ["c", "d", "e", "f", "g"]
        for index, label in enumerate(waiting, start=1):
            threads.append(_call_in_thread(provider, label, results, timeout=20))
            self.assertTrue(_wait(lambda: queue_state()["waiting"] == index), queue_state())
        for _ in range(7):
            provider.step.release()
            time.sleep(0.05)
        for thread in threads:
            thread.join(5)
        self.assertEqual(provider.order[2:], waiting)
        self.assertTrue(all(r["status"] == "success" for r in results.values()), results)

    def test_position_and_ahead_for_the_waiting_thread(self):
        provider = GateProvider()
        results, threads = {}, []
        for label in ("a", "b"):
            threads.append(_call_in_thread(provider, label, results, timeout=20))
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 2))
        threads.append(_call_in_thread(provider, "c", results, timeout=20))
        threads.append(_call_in_thread(provider, "d", results, timeout=20))
        self.assertTrue(_wait(lambda: queue_state()["waiting"] == 2))
        by_name = {t.name: t for t in threading.enumerate()}
        state_c = queue_state(by_name["prueba-c"].ident)
        state_d = queue_state(by_name["prueba-d"].ident)
        self.assertEqual((state_c["position"], state_c["ahead"]), (1, 2))
        self.assertEqual((state_d["position"], state_d["ahead"]), (2, 3))
        self.assertEqual(state_c["capacity"], 2)
        # El hilo actual no está en la fila.
        self.assertIsNone(queue_state()["position"])
        self.assertIsNone(queue_state()["ahead"])
        # La instantánea de proceso también lo muestra (campo nuevo).
        snap = STATS.snapshot()
        self.assertEqual(snap["llm_queue"]["waiting"], 2)
        self.assertEqual(snap["llm_queue"]["in_flight"], 2)
        self.assertEqual(queue_snapshot(by_name["prueba-d"].ident)["llm"]["position"], 2)
        provider.release.set()
        for thread in threads:
            thread.join(5)

    def test_giving_up_leaves_the_line_and_others_advance(self):
        provider = GateProvider()
        results, threads = {}, []
        for label in ("a", "b"):
            threads.append(_call_in_thread(provider, label, results, timeout=20))
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 2))
        threads.append(_call_in_thread(provider, "c", results, timeout=20, queue_wait=0.3))
        self.assertTrue(_wait(lambda: queue_state()["waiting"] == 1))
        threads.append(_call_in_thread(provider, "d", results, timeout=20))
        self.assertTrue(_wait(lambda: "c" in results, 3))
        self.assertEqual(results["c"]["status"], "llm_saturated")
        self.assertIn("waited_s", results["c"])
        self.assertTrue(_wait(lambda: queue_state()["waiting"] == 1))
        by_name = {t.name: t for t in threading.enumerate()}
        self.assertEqual(queue_state(by_name["prueba-d"].ident)["position"], 1)
        provider.release.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(results["d"]["status"], "success")

    def test_contract_never_raises_and_keeps_statuses(self):
        class Raises:
            enforces_timeout = True

            def chat(self, messages, **kwargs):
                raise RuntimeError("explota")

        class NotDict:
            def chat(self, messages, **kwargs):
                return "texto"

        class TimesOut:
            enforces_timeout = True

            def chat(self, messages, timeout=None, **kwargs):
                return {"status": "llm_timeout", "answer": None, "timeout_seconds": timeout}

        self.assertEqual(call_llm(Raises(), MESSAGES, timeout=2)["status"], "llm_error")
        self.assertEqual(call_llm(NotDict(), MESSAGES)["status"], "llm_error")
        self.assertEqual(call_llm(TimesOut(), MESSAGES, timeout=2)["status"], "llm_timeout")

    def test_capacity_follows_env_on_each_call(self):
        with _Env(MEDGEMMA_MAX_CONCURRENT="1"):
            provider = GateProvider()
            results = {}
            first = _call_in_thread(provider, "a", results, timeout=20)
            self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 1))
            self.assertEqual(queue_state()["capacity"], 1)
            second = call_llm(provider, MESSAGES, purpose="prueba", timeout=5, queue_wait=0.2)
            self.assertEqual(second["status"], "llm_saturated")
            provider.release.set()
            first.join(5)


class UiProgressTests(unittest.TestCase):
    def setUp(self):
        self.env = _Env(MEDGEMMA_MAX_CONCURRENT="1", MEDGEMMA_QUEUE_WAIT="0.2", MEDGEMMA_QUEUE_WAIT_UI="3")
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__()
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 0, 5))

    def test_progress_mode_waits_longer_reports_position_and_keeps_full_budget(self):
        provider = GateProvider()
        results = {}
        blocker = _call_in_thread(provider, "a", results, timeout=20)
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 1))
        seen = []
        threading.Timer(0.8, provider.release.set).start()
        with ui_progress(on_queue=seen.append):
            started = time.perf_counter()
            result = call_llm(provider, MESSAGES, purpose="síntesis RAG", timeout=10)
            waited = time.perf_counter() - started
        blocker.join(5)
        self.assertEqual(result["status"], "success", result)
        self.assertGreater(waited, 0.6)  # esperó más que MEDGEMMA_QUEUE_WAIT (0.2 s)
        waiting_events = [e for e in seen if not e.get("done")]
        self.assertTrue(waiting_events, seen)
        self.assertEqual(waiting_events[0]["position"], 1)
        self.assertEqual(waiting_events[0]["ahead"], 1)
        self.assertEqual(waiting_events[0]["purpose"], "síntesis RAG")
        self.assertTrue(seen[-1].get("done") and seen[-1].get("acquired"), seen[-1])
        # La espera en fila no le resta presupuesto a la generación.
        self.assertEqual(provider.received_timeouts[-1], 10.0)

    def test_without_progress_the_short_wait_and_total_budget_stay(self):
        provider = GateProvider()
        results = {}
        blocker = _call_in_thread(provider, "a", results, timeout=20)
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 1))
        started = time.perf_counter()
        result = call_llm(provider, MESSAGES, purpose="síntesis RAG", timeout=10)
        self.assertEqual(result["status"], "llm_saturated")
        self.assertLess(time.perf_counter() - started, 1.0)
        provider.release.set()
        blocker.join(5)

    def test_explicit_queue_wait_wins_over_progress_mode(self):
        provider = GateProvider()
        results = {}
        blocker = _call_in_thread(provider, "a", results, timeout=20)
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 1))
        with ui_progress():
            started = time.perf_counter()
            result = call_llm(provider, MESSAGES, purpose="reescritura contextual", timeout=8, queue_wait=0.2)
        self.assertEqual(result["status"], "llm_saturated")
        self.assertLess(time.perf_counter() - started, 1.0)
        provider.release.set()
        blocker.join(5)

    def test_callback_errors_are_ignored(self):
        def broken(_event):
            raise ValueError("la UI falló")

        provider = GateProvider()
        results = {}
        blocker = _call_in_thread(provider, "a", results, timeout=20)
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 1))
        threading.Timer(0.4, provider.release.set).start()
        with ui_progress(on_queue=broken):
            result = call_llm(provider, MESSAGES, timeout=5)
        blocker.join(5)
        self.assertEqual(result["status"], "success")

    def test_pressure_and_queue_observer(self):
        provider = GateProvider()
        results = {}
        blocker = _call_in_thread(provider, "a", results, timeout=20)
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 1))
        titles = []
        remove = llm_gate.add_queue_observer(lambda e: titles.append(e["titulo"]))
        try:
            before = STATS.llm_pressure()["saturated_recent"]
            result = call_llm(provider, MESSAGES, purpose="prueba", timeout=5, queue_wait=0.3)
        finally:
            remove()
        self.assertEqual(result["status"], "llm_saturated")
        pressure = STATS.llm_pressure()
        self.assertEqual(pressure["saturated_recent"], before + 1)
        self.assertEqual((pressure["in_flight"], pressure["capacity"]), (1, 1))
        self.assertIn("waiting", pressure)
        self.assertTrue(titles and all(t.startswith("LLM en cola") for t in titles), titles)
        self.assertIn("sin hueco", titles[-1])
        self.assertIn("llm_pressure", STATS.snapshot())
        provider.release.set()
        blocker.join(5)

    def test_context_does_not_leak_after_exit(self):
        with ui_progress(queue_wait=7):
            self.assertIsNotNone(llm_gate.current_progress())
        self.assertIsNone(llm_gate.current_progress())


class FairTurnTests(unittest.TestCase):
    def test_turns_enter_in_arrival_order_and_report_position(self):
        order, positions = [], {}
        holding, release = threading.Event(), threading.Event()

        def holder():
            with turn_slot("primera"):
                holding.set()
                release.wait(10)

        def waiter(label):
            def on_wait(waited, since):
                positions.setdefault(label, queue_snapshot()["turn"]["position"])
            with turn_slot(label, on_wait=on_wait, max_wait=10, poll_s=0.05):
                order.append(label)

        first = threading.Thread(target=holder)
        first.start()
        holding.wait(2)
        threads = []
        for index, label in enumerate(["t1", "t2", "t3", "t4"], start=1):
            thread = threading.Thread(target=waiter, args=(label,))
            thread.start()
            threads.append(thread)
            self.assertTrue(_wait(lambda: STATS.snapshot()["turn_queue"]["waiting"] == index), STATS.snapshot()["turn_queue"])
        snap = STATS.snapshot()["turn_queue"]
        self.assertEqual((snap["in_flight"], snap["capacity"]), (1, 1))
        release.set()
        first.join(5)
        for thread in threads:
            thread.join(5)
        self.assertEqual(order, ["t1", "t2", "t3", "t4"])
        self.assertEqual(positions, {"t1": 1, "t2": 2, "t3": 3, "t4": 4})
        self.assertEqual(STATS.snapshot()["turn_queue"]["waiting"], 0)
        self.assertFalse(TURN_LOCK.locked())

    def test_busy_turn_leaves_the_line(self):
        TURN_LOCK.acquire()  # como la prueba de la app: alguien toma el candado directo
        try:
            with self.assertRaises(TurnBusy):
                with turn_slot("espera", max_wait=0.3, poll_s=0.05):
                    pass
            self.assertEqual(STATS.snapshot()["turn_queue"]["waiting"], 0)
        finally:
            TURN_LOCK.release()
        with turn_slot("libre", max_wait=0.2):
            self.assertEqual(queue_snapshot()["turn"]["position"], None)

    def test_free_turn_enters_without_waiting(self):
        calls = []
        with turn_slot("directo", on_wait=lambda *a: calls.append(a), max_wait=1):
            pass
        self.assertEqual(calls, [])


class SnapshotFieldsTests(unittest.TestCase):
    def test_old_fields_kept_and_new_ones_added(self):
        snap = STATS.snapshot()
        for key in ("uptime_s", "turns", "llm", "llm_by_purpose", "powerbi", "threads"):
            self.assertIn(key, snap)
        for key in ("in_flight", "waiting", "completed", "timeouts", "saturated", "errors", "abandoned"):
            self.assertIn(key, snap["llm"])
        for group in ("llm_queue", "turn_queue"):
            for key in ("capacity", "in_flight", "waiting"):
                self.assertIn(key, snap[group])
        both = queue_snapshot()
        for group in ("llm", "turn"):
            for key in ("capacity", "in_flight", "waiting", "position", "ahead"):
                self.assertIn(key, both[group])
        self.assertTrue(callable(runtime_stats.status_line))
        runtime_stats.status_line(snap)  # sigue funcionando con los campos nuevos


class DoneReasonTests(unittest.TestCase):
    def test_provider_reports_done_reason(self):
        from src.llm import medgemma_provider

        class _Message:
            content = "respuesta cortada"

        class _Response:
            message = _Message()
            done_reason = "length"
            eval_count = 600

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def chat(self, **request):
                return _Response()

        original = medgemma_provider.Client
        medgemma_provider.Client = FakeClient
        try:
            provider = medgemma_provider.MedGemmaProvider(host="http://127.0.0.1:9", model="m")
            result = provider.chat(MESSAGES, max_tokens=600, timeout=5)
        finally:
            medgemma_provider.Client = original
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["done_reason"], "length")
        self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()

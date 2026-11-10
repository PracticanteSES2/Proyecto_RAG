"""
Backend Redis de la puerta del LLM (backend/app/services/puerta_llm_redis.py,
inyectado en src/llm/llm_gate.py) con fakeredis:
semáforo justo entre «procesos» (dos clientes contra el mismo servidor falso),
préstamos con TTL, purga de los que esperaban y murieron, posición en fila,
caída a memoria si Redis no responde y contrato de call_llm.

    .venv\\Scripts\\python.exe -X utf8 -m unittest tests.perf.test_gate_redis

Requiere `fakeredis` (requirements-dev.txt); si falta, se omite.
"""
import logging
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

if "dotenv" not in sys.modules:
    _dotenv = types.ModuleType("dotenv")
    _dotenv.load_dotenv = lambda *a, **k: False
    _dotenv.find_dotenv = lambda *a, **k: ""
    _dotenv.__sim_fake__ = True
    sys.modules["dotenv"] = _dotenv

try:
    import fakeredis
except ImportError:  # pragma: no cover
    fakeredis = None

from src.llm import llm_gate  # noqa: E402
from backend.app.services import puerta_llm_redis  # noqa: E402
from backend.app.services.puerta_llm_redis import RedisBackend  # noqa: E402
from src.llm.llm_gate import call_llm, evento_cola, queue_state, set_backend, ui_progress  # noqa: E402

MESSAGES = [{"role": "user", "content": "hola"}]


def _wait(predicate, seconds=5.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class Hold:
    enforces_timeout = True

    def __init__(self):
        self.release = threading.Event()
        self.order = []
        self.lock = threading.Lock()

    def chat(self, messages, timeout=None, **kwargs):
        with self.lock:
            self.order.append(messages[0]["content"])
        self.release.wait(10)
        return {"status": "success", "answer": "ok"}


@unittest.skipIf(fakeredis is None, "fakeredis no instalado")
class RedisBackendTests(unittest.TestCase):
    def setUp(self):
        self.server = fakeredis.FakeServer()
        self.capacity = 2

    def backend(self, name, **kwargs):
        client = fakeredis.FakeRedis(server=self.server)
        return RedisBackend(client, capacity_fn=lambda: self.capacity, process_id=name, poll_s=0.02, **kwargs)

    def test_capacity_is_global_across_processes(self):
        a, b = self.backend("proc-a"), self.backend("proc-b")
        p1 = a.acquire(1)
        p2 = b.acquire(1)
        self.assertIsNotNone(p1)
        self.assertIsNotNone(p2)
        self.assertIsNone(a.acquire(0.1))  # global: ya hay 2
        self.assertIsNone(b.acquire(0.1))
        self.assertEqual(a.state(-1)["in_flight"], 2)
        p1.release()
        self.assertIsNotNone(b.acquire(1))

    def test_fifo_across_processes_and_position(self):
        a, b = self.backend("proc-a"), self.backend("proc-b")
        holders = [a.acquire(1), b.acquire(1)]
        order, threads = [], []
        idents = {}

        def wait(backend, label):
            idents[label] = threading.get_ident()
            permit = backend.acquire(5)
            order.append(label)
            time.sleep(0.05)
            permit.release()

        for index, (backend, label) in enumerate([(a, "w1"), (b, "w2"), (a, "w3"), (b, "w4")], start=1):
            thread = threading.Thread(target=wait, args=(backend, label))
            thread.start()
            threads.append(thread)
            self.assertTrue(_wait(lambda: a.state(-1)["waiting"] == index), a.state(-1))
        self.assertEqual(b.state(idents["w4"])["position"], 4)
        self.assertEqual(b.state(idents["w4"])["ahead"], 5)  # 2 en curso + 3 delante
        self.assertEqual(a.state(idents["w1"])["position"], 1)
        self.assertIsNone(a.state(idents["w4"])["position"])  # w4 es de otro proceso
        for permit in holders:
            permit.release()
        for thread in threads:
            thread.join(10)
        self.assertEqual(order, ["w1", "w2", "w3", "w4"])

    def test_expired_lease_frees_the_slot_of_a_dead_process(self):
        dead, alive = self.backend("muerto"), self.backend("vivo")
        self.capacity = 1
        self.assertIsNotNone(dead.acquire(1, lease_s=0.3))  # nunca libera (proceso caído)
        self.assertIsNone(alive.acquire(0.1))
        permit = alive.acquire(2)
        self.assertIsNotNone(permit, "el préstamo vencido debía liberarse")
        permit.release()

    def test_dead_waiter_does_not_block_the_line(self):
        backend = self.backend("p", waiter_ttl_s=0.2)
        self.capacity = 1
        holder = backend.acquire(1)
        # Un ticket «huérfano» delante (proceso que murió esperando).
        client = backend.r
        now = backend._now()
        client.zadd(backend.k_fila, {"huerfano": 0})
        client.zadd(backend.k_vivos, {"huerfano": now + 0.2})
        holder.release()
        time.sleep(0.3)
        self.assertIsNotNone(backend.acquire(1))

    def test_give_up_removes_ticket(self):
        backend = self.backend("p")
        self.capacity = 1
        holder = backend.acquire(1)
        self.assertIsNone(backend.acquire(0.1))
        self.assertEqual(backend.state(-1)["waiting"], 0)
        holder.release()


@unittest.skipIf(fakeredis is None, "fakeredis no instalado")
class GateWithRedisTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ("MEDGEMMA_MAX_CONCURRENT", "LLM_GATE_BACKEND", "REDIS_URL")}
        os.environ["MEDGEMMA_MAX_CONCURRENT"] = "1"
        self.server = fakeredis.FakeServer()
        set_backend(RedisBackend(fakeredis.FakeRedis(server=self.server), capacity_fn=llm_gate.max_concurrent,
                                 process_id="api-1", poll_s=0.02))

    def tearDown(self):
        set_backend(None)
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_call_llm_contract_with_redis(self):
        self.assertEqual(llm_gate.backend_name(), "redis")
        provider = Hold()
        provider.release.set()
        result = call_llm(provider, MESSAGES, purpose="prueba", timeout=5)
        self.assertEqual(result["status"], "success")
        blocker = Hold()
        thread = threading.Thread(target=call_llm, args=(blocker, MESSAGES), kwargs={"timeout": 10})
        thread.start()
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 1))
        saturated = call_llm(provider, MESSAGES, timeout=5, queue_wait=0.2)
        self.assertEqual(saturated["status"], "llm_saturated")
        blocker.release.set()
        thread.join(5)
        self.assertEqual(queue_state()["in_flight"], 0)

    def test_progress_events_for_sse(self):
        blocker = Hold()
        thread = threading.Thread(target=call_llm, args=(blocker, MESSAGES), kwargs={"timeout": 10})
        thread.start()
        self.assertTrue(_wait(lambda: queue_state()["in_flight"] == 1))
        events = []
        threading.Timer(0.6, blocker.release.set).start()
        provider = Hold()
        provider.release.set()
        with ui_progress(on_queue=events.append, queue_wait=5):
            result = call_llm(provider, MESSAGES, purpose="síntesis RAG", timeout=10)
        thread.join(5)
        self.assertEqual(result["status"], "success")
        first = [e for e in events if not e.get("done")][0]
        self.assertEqual(first["backend"], "redis")
        sse = evento_cola(first)
        self.assertEqual((sse["posicion"], sse["en_curso"], sse["antes"]), (1, 1, 1))

    def test_redis_failing_mid_call_falls_back_to_memory(self):
        class Broken:
            name = "redis"

            def acquire(self, *a, **k):
                raise ConnectionError("redis caído")

            def state(self, ident=None):
                raise ConnectionError("redis caído")

        set_backend(Broken())
        provider = Hold()
        provider.release.set()
        with self.assertLogs("llm_gate", level=logging.WARNING):
            result = call_llm(provider, MESSAGES, timeout=5)
        self.assertEqual(result["status"], "success")
        self.assertEqual(queue_state()["backend"], "memoria")  # state() también cae a memoria


class EnvSelectionTests(unittest.TestCase):
    def test_unreachable_redis_falls_back_to_memory_with_warning(self):
        saved = {k: os.environ.get(k) for k in ("LLM_GATE_BACKEND", "REDIS_URL")}
        os.environ["LLM_GATE_BACKEND"] = "redis"
        puerta_llm_redis.instalar("redis://127.0.0.1:1/0")  # nadie escucha
        set_backend(None)
        try:
            with self.assertLogs("llm_gate", level=logging.WARNING) as logs:
                name = llm_gate.backend_name()
            self.assertEqual(name, "memoria")
            self.assertIn("Redis no disponible", "\n".join(logs.output))
            provider = Hold()
            provider.release.set()
            self.assertEqual(call_llm(provider, MESSAGES, timeout=5)["status"], "success")
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            set_backend(None)
            llm_gate._FABRICAS.pop("redis", None)

    def _with_redis_env(self):
        saved = os.environ.get("LLM_GATE_BACKEND")
        os.environ["LLM_GATE_BACKEND"] = "redis"

        def restore():
            if saved is None:
                os.environ.pop("LLM_GATE_BACKEND", None)
            else:
                os.environ["LLM_GATE_BACKEND"] = saved
            llm_gate._FABRICAS.pop("redis", None)
            set_backend(None)
        self.addCleanup(restore)

    def test_redis_without_adapter_falls_back_to_memory_with_warning(self):
        self._with_redis_env()
        llm_gate._FABRICAS.pop("redis", None)
        set_backend(None)
        with self.assertLogs("llm_gate", level=logging.WARNING) as logs:
            self.assertEqual(llm_gate.backend_name(), "memoria")
        self.assertIn("no hay adaptador", "\n".join(logs.output))

    @unittest.skipIf(fakeredis is None, "fakeredis no instalado")
    def test_installed_adapter_is_used_when_redis_answers(self):
        self._with_redis_env()
        server = fakeredis.FakeServer()
        llm_gate.registrar_backend("redis", lambda capacity_fn: RedisBackend(
            fakeredis.FakeRedis(server=server), capacity_fn=capacity_fn, poll_s=0.02))
        self.assertEqual(llm_gate.backend_name(), "redis")

    def test_default_is_memory(self):
        saved = os.environ.pop("LLM_GATE_BACKEND", None)
        set_backend(None)
        try:
            self.assertEqual(llm_gate.backend_name(), "memoria")
        finally:
            if saved is not None:
                os.environ["LLM_GATE_BACKEND"] = saved


if __name__ == "__main__":
    unittest.main()

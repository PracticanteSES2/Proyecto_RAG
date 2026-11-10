"""
Costo de MedGemma por propósito (runtime_stats + llm_gate): llamadas, tamaño
del prompt, `num_predict` pedido, tokens que informa el proveedor y llamadas
evitadas (caché, catálogo). Solo se AÑADEN campos a STATS.snapshot().

    .venv\\Scripts\\python.exe -X utf8 -m unittest tests.perf.test_costo_llm

No usa red, .env, Ollama ni Power BI.
"""
import sys
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

from src.chatbot.runtime_stats import STATS, RuntimeStats  # noqa: E402
from src.llm.llm_gate import call_llm  # noqa: E402


class _Informa:
    enforces_timeout = True

    def chat(self, messages, max_tokens=None, timeout=None, **kwargs):
        return {"status": "success", "answer": "ok", "prompt_eval_count": 120, "eval_count": 30,
                "done_reason": "stop", "truncated": False}


class CostoPorPropositoTests(unittest.TestCase):
    def setUp(self):
        self.stats = RuntimeStats()

    def test_payload_suma_caracteres_tokens_estimados_y_num_predict(self):
        messages = [{"role": "system", "content": "x" * 400}, {"role": "user", "content": "y" * 400}]
        self.stats.llm_payload("síntesis RAG", messages, 600)
        self.stats.llm_payload("síntesis RAG", messages, 600)
        cost = self.stats.snapshot()["llm_cost_by_purpose"]["síntesis RAG"]
        self.assertEqual(cost["calls"], 2)
        self.assertEqual(cost["prompt_chars"], 1600)
        self.assertEqual(cost["prompt_tokens_est"], 400)
        self.assertEqual(cost["num_predict"], 1200)
        self.assertEqual(cost["prompt_chars_avg"], 800)
        self.assertEqual(cost["num_predict_avg"], 600)

    def test_usage_suma_tokens_reales_y_truncadas(self):
        self.stats.llm_payload("opciones", [{"content": "abc"}], 60)
        self.stats.llm_usage("opciones", {"status": "success", "prompt_eval_count": 50, "eval_count": 60,
                                          "truncated": True})
        self.stats.llm_usage("opciones", {"status": "llm_timeout"})
        cost = self.stats.snapshot()["llm_cost_by_purpose"]["opciones"]
        self.assertEqual((cost["prompt_eval_tokens"], cost["eval_tokens"], cost["truncated"]), (50, 60, 1))

    def test_llamadas_evitadas_y_eventos_de_cache(self):
        self.stats.llm_call_avoided("caché: síntesis RAG")
        self.stats.llm_call_avoided("catálogo: descripción de opciones", 2)
        self.stats.llm_cache_event("hits")
        self.stats.llm_cache_event("misses")
        self.stats.llm_cache_event("misses")
        snap = self.stats.snapshot()
        self.assertEqual(snap["llm_avoided"], {"caché: síntesis RAG": 1, "catálogo: descripción de opciones": 2})
        self.assertEqual(snap["llm_cache"]["hits"], 1)
        self.assertEqual(snap["llm_cache"]["misses"], 2)

    def test_campos_existentes_no_cambian(self):
        snap = self.stats.snapshot()
        for key in ("turns", "llm", "llm_by_purpose", "llm_queue", "llm_pressure", "powerbi"):
            self.assertIn(key, snap)


class PuertaRegistraCostoTests(unittest.TestCase):
    def test_call_llm_registra_prompt_y_tokens(self):
        before = STATS.snapshot()["llm_cost_by_purpose"].get("prueba costo", {}).get("calls", 0)
        result = call_llm(_Informa(), [{"role": "user", "content": "z" * 80}], purpose="prueba costo",
                          timeout=5, max_tokens=77)
        self.assertEqual(result["status"], "success")
        cost = STATS.snapshot()["llm_cost_by_purpose"]["prueba costo"]
        self.assertEqual(cost["calls"], before + 1)
        self.assertGreaterEqual(cost["num_predict"], 77)
        self.assertGreaterEqual(cost["prompt_eval_tokens"], 120)
        self.assertGreaterEqual(cost["eval_tokens"], 30)


if __name__ == "__main__":
    unittest.main()

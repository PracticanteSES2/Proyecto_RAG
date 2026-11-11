"""
Síntesis RAG con la caché del motor (src/chatbot/cache_llm.py): la misma
pregunta (con otra forma) sobre las mismas fuentes no vuelve a llamar al LLM; el
post-proceso se aplica igual; truncadas y «sin evidencia» nunca se guardan.

    .venv\\Scripts\\python.exe -X utf8 -m unittest tests.rag.test_sintesis_cache
"""
import os
import sys
import threading
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

from src.chatbot import cache_llm  # noqa: E402
from src.chatbot.answer_synthesizer import NO_EVIDENCE_ANSWER, AnswerSynthesizer  # noqa: E402

SOURCES = [
    {"text": "Tablero: LAVADERIA Indicador documentado: TURNO_OK Descripción: Nombre del turno laboral "
             "(MAÑANA, TARDE, NOCHE) según la hora de registro de la ropa.",
     "chunk_type": "indicator", "dashboard": "LAVADERIA", "semantic_model": "TABLERO LAVANDERIA",
     "intent": "definition"},
]
GOOD = "TURNO_OK es el nombre del turno laboral (MAÑANA, TARDE, NOCHE) según la hora de registro."


class _Proveedor:
    model = "medgemma-prueba"
    enforces_timeout = True

    def __init__(self, answer=GOOD, truncated=False):
        self.calls = 0
        self.answer = answer
        self.truncated = truncated
        self.lock = threading.Lock()

    def chat(self, messages, **kwargs):
        with self.lock:
            self.calls += 1
        return {"status": "success", "answer": self.answer, "model": self.model,
                "done_reason": "length" if self.truncated else "stop", "truncated": self.truncated}


class SintesisConCacheTests(unittest.TestCase):
    def setUp(self):
        self.saved = os.environ.pop("LLM_CACHE", None)
        cache_llm.configurar_almacen(cache_llm.AlmacenMemoria())

    def tearDown(self):
        cache_llm.configurar_almacen(None)
        if self.saved is not None:
            os.environ["LLM_CACHE"] = self.saved

    def test_misma_pregunta_con_otra_forma_no_llama_otra_vez(self):
        provider = _Proveedor()
        synth = AnswerSynthesizer(provider, timeout_seconds=0)
        first = synth.synthesize_rag("¿Qué es TURNO_OK?", SOURCES)
        second = synth.synthesize_rag("que es turno_ok", SOURCES)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(first["answer"], second["answer"])
        self.assertIsNone(first.get("cache"))
        self.assertEqual(second["cache"], "hit")
        self.assertTrue(second.get("cacheable", True))

    def test_otras_fuentes_llaman_otra_vez(self):
        provider = _Proveedor()
        synth = AnswerSynthesizer(provider, timeout_seconds=0)
        synth.synthesize_rag("¿Qué es TURNO_OK?", SOURCES)
        other = [dict(SOURCES[0], text=SOURCES[0]["text"] + " Se usa en el informe mensual.")]
        synth.synthesize_rag("¿Qué es TURNO_OK?", other)
        self.assertEqual(provider.calls, 2)

    def test_sin_evidencia_no_se_guarda(self):
        provider = _Proveedor(answer=NO_EVIDENCE_ANSWER)
        synth = AnswerSynthesizer(provider, timeout_seconds=0)
        synth.synthesize_rag("¿Qué es TURNO_OK?", SOURCES)
        synth.synthesize_rag("¿Qué es TURNO_OK?", SOURCES)
        self.assertEqual(provider.calls, 2)

    def test_truncada_no_se_guarda(self):
        provider = _Proveedor(answer=GOOD + " Además se usa para", truncated=True)
        synth = AnswerSynthesizer(provider, timeout_seconds=0)
        synth.synthesize_rag("¿Qué es TURNO_OK?", SOURCES)
        calls_first = provider.calls  # puede incluir la continuación del truncado
        synth.synthesize_rag("¿Qué es TURNO_OK?", SOURCES)
        self.assertEqual(provider.calls, 2 * calls_first)


if __name__ == "__main__":
    unittest.main()

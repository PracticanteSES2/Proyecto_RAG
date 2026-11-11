"""
Palanca opcional RAG_EXTRACTO_DIRECTO (specs/010-rendimiento-llm): «¿qué es X?»
se responde con la entrada documentada de X, sin llamar a MedGemma, solo si la
pregunta nombra la medida, no hay conversación previa y la descripción es una
frase completa. Apagada por defecto.

    .venv\\Scripts\\python.exe -X utf8 -m unittest tests.rag.test_extracto_directo
"""
import os
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

from src.chatbot.rag_answer_engine import RAGAnswerEngine  # noqa: E402

TURNO = {
    "text": ("Tablero: DICCIONARIO TABLERO LAVANDERIA Medida Power BI: TURNO_OK Tabla: LAVANDERIA "
             "Descripción: Nombre del turno laboral (MAÑANA, TARDE, NOCHE) según la hora de registro."),
    "chunk_type": "measure", "dashboard": "DICCIONARIO TABLERO LAVANDERIA", "measure": "TURNO_OK",
    "is_dictionary": True, "score": 0.9, "intent": "definition",
}


class _Sintetizador:
    def __init__(self):
        self.calls = 0

    def synthesize_rag(self, question, sources, history=None):
        self.calls += 1
        return {"status": "success", "answer": "Respuesta redactada por el LLM.", "no_evidence": False}


class _Retriever:
    def __init__(self, results):
        self.results = results

    def search_general(self, question, limit=5, dashboard=None):
        return list(self.results)


class ExtractoDirectoTests(unittest.TestCase):
    def setUp(self):
        self.saved = os.environ.get("RAG_EXTRACTO_DIRECTO")

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("RAG_EXTRACTO_DIRECTO", None)
        else:
            os.environ["RAG_EXTRACTO_DIRECTO"] = self.saved

    def _answer(self, question, results=(TURNO,), history=None):
        synth = _Sintetizador()
        engine = RAGAnswerEngine(_Retriever(results), answer_synthesizer=synth, min_score=0.1)
        return engine.answer({"original_question": question}, history), synth

    def test_apagada_por_defecto_llama_al_llm(self):
        os.environ.pop("RAG_EXTRACTO_DIRECTO", None)
        result, synth = self._answer("¿qué es turno_ok?")
        self.assertEqual(synth.calls, 1)
        self.assertEqual(result["synthesis_mode"], "llm")

    def test_definicion_nombrada_no_llama_al_llm(self):
        os.environ["RAG_EXTRACTO_DIRECTO"] = "on"
        result, synth = self._answer("¿qué es turno_ok?")
        self.assertEqual(synth.calls, 0)
        self.assertEqual(result["synthesis_mode"], "extracto")
        self.assertIn("TURNO_OK", result["answer"])
        self.assertIn("turno laboral", result["answer"])

    def test_otros_casos_siguen_con_el_llm(self):
        os.environ["RAG_EXTRACTO_DIRECTO"] = "on"
        casos = [
            ("¿qué es el turno de la mañana?", (TURNO,), None),                           # no nombra la medida
            ("¿cómo se calcula turno_ok?", (dict(TURNO, intent="calculation"),), None),  # no es definición
            ("¿qué es turno_ok?", (TURNO,), [{"role": "user", "text": "hola"}]),          # hay conversación
            ("¿qué es turno_ok?", (dict(TURNO, text="Tablero: X Medida Power BI: TURNO_OK Descripción: Turno."),),
             None),                                                                       # descripción corta
        ]
        for question, results, history in casos:
            result, synth = self._answer(question, results, history)
            self.assertEqual(synth.calls, 1, question)


if __name__ == "__main__":
    unittest.main()

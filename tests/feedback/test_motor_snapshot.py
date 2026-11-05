"""
El snapshot recibe lo que de verdad devuelve el QueryEngine en la ruta RAG
(no un dict fabricado): retrieval_mode, not_found_reason y las fuentes consultadas.

Ejecutar:
  python -m unittest tests.feedback.test_motor_snapshot
"""
import json
import unittest

from src.feedback import registro
from tests.routing import test_routing as tr

FUENTES = [{"id": "s1", "collection": "col", "dashboard": "Lavanderia", "chunk_type": "visual",
            "score": 0.31, "text": "TEXTO_DE_CHUNK_SECRETO"}]


class MotorRagSnapshot(unittest.TestCase):
    def test_ruta_rag_exitosa_expone_retrieval_mode_y_motivo(self):
        rag = {"status": "success", "answer": "Respuesta documental", "sources": FUENTES,
               "synthesis_mode": "llm", "retrieval_mode": "dashboard", "not_found_reason": "ninguno"}
        engine, *_ = tr.make_system(rag)
        pregunta = "¿Qué muestra el tablero de lavandería?"
        result = engine.process(pregunta)
        self.assertEqual(result["route"], "rag")
        snap = registro.snapshot_turno(result, result["answer"], pregunta, "texto", [])
        self.assertEqual(snap["retrieval_mode"], "dashboard")
        self.assertEqual(snap["not_found_reason"], "ninguno")
        self.assertEqual(snap["fuentes"][0]["tablero"], "Lavanderia")
        self.assertNotIn("TEXTO_DE_CHUNK_SECRETO", json.dumps(snap))

    def test_fuera_de_alcance_conserva_fuentes_y_decision_del_recuperador(self):
        rag = {**tr._NOT_FOUND, "not_found_reason": "llm_no_evidence", "retrieval_mode": "open",
               "sources": FUENTES, "synthesis_mode": "none"}
        engine, *_ = tr.make_system(rag)
        pregunta = "que hago con los registros de un paciente con fiebre y dolor de cabeza"
        result = engine.process(pregunta)
        self.assertEqual(result["route"], "out_of_scope")
        self.assertEqual(result["sources"], [])  # la salida visible no cambia
        snap = registro.snapshot_turno(result, result["answer"], pregunta, "texto", [])
        self.assertEqual(snap["retrieval_mode"], "open")
        self.assertEqual(snap["not_found_reason"], "llm_no_evidence")
        self.assertEqual(len(snap["fuentes"]), 1)
        self.assertEqual(snap["fuentes"][0]["tipo_chunk"], "visual")
        self.assertNotIn("TEXTO_DE_CHUNK_SECRETO", json.dumps(snap))

    def test_ruta_powerbi_registra_el_periodo_del_plan_real(self):
        engine, *_ = tr.make_system()
        result = engine.process(tr.Q3)
        self.assertEqual(result["route"], "powerbi")
        snap = registro.snapshot_turno(result, result.get("answer"), tr.Q3, "texto", [])
        self.assertEqual(snap["periodo"]["tipo"], "month")
        self.assertEqual(snap["periodo"]["inicio"], "2026-01-01")
        self.assertEqual(snap["candidatos_indicador"], [])  # este plan no pasó por el resolvedor con candidatos


if __name__ == "__main__":
    unittest.main()

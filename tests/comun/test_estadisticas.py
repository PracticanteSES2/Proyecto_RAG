"""Estado de ejecución en la capa base (src/comun/estadisticas.py) y su reexporte de compatibilidad.

    python -X utf8 -m unittest tests.comun.test_estadisticas
"""
import ast
import os
import unittest
from pathlib import Path
from unittest import mock

from src.chatbot import runtime_stats
from src.comun import entorno, estadisticas

RAIZ = Path(__file__).resolve().parents[2]


class TestReexporte(unittest.TestCase):
    def test_mismos_objetos(self):
        # Los contadores y candados son compartidos: el reexporte no puede crear copias.
        self.assertIs(runtime_stats.STATS, estadisticas.STATS)
        self.assertIs(runtime_stats.TURN_LOCK, estadisticas.TURN_LOCK)
        self.assertIs(runtime_stats.TURN_LINE, estadisticas.TURN_LINE)
        self.assertIs(runtime_stats.turn_slot, estadisticas.turn_slot)
        self.assertIs(runtime_stats.env_float, entorno.env_float)
        self.assertIs(runtime_stats.env_int, entorno.env_int)

    def test_reexporta_la_api_de_siempre(self):
        # Lo que src/chatbot/runtime_stats.py definía antes del traslado (2026-11-10).
        api = {
            "RECENT_LATENCIES", "STATS", "TURN_LINE", "TURN_LOCK", "FifoLine", "RuntimeStats", "TurnBusy",
            "_Ticket", "_duration", "_empty_queue_state", "_turn_queue_state", "degradation_lines",
            "diagnostics_lines", "env_float", "env_int", "open_connections", "queue_snapshot", "status_line",
            "turn_lock_busy", "turn_slot", "turn_wait_limit",
            # specs/010-rendimiento-llm (costo por propósito, llamadas evitadas, caché del LLM)
            "CHARS_PER_TOKEN", "_COST_FIELDS", "_CACHE_EVENTS",
        }
        for nombre in sorted(api):
            self.assertTrue(hasattr(runtime_stats, nombre), nombre)
            self.assertTrue(hasattr(estadisticas, nombre) or hasattr(entorno, nombre), nombre)

    def test_comun_no_importa_capas_superiores(self):
        for archivo in ("estadisticas.py", "entorno.py"):
            arbol = ast.parse((RAIZ / "src/comun" / archivo).read_text(encoding="utf-8"))
            for n in ast.walk(arbol):
                if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("src."):
                    self.assertTrue(n.module.startswith("src.comun"), f"{archivo} importa {n.module}")

    def test_providers_no_importa_chatbot(self):
        texto = (RAIZ / "src/providers/powerbi_provider.py").read_text(encoding="utf-8")
        self.assertNotIn("src.chatbot", texto)


class TestEntorno(unittest.TestCase):
    def test_valores_tolerantes(self):
        with mock.patch.dict(os.environ, {"X_F": "2.5", "X_I": "3.9", "X_MAL": "abc", "X_CERO": "0"}):
            self.assertEqual(entorno.env_float("X_F", 1), 2.5)
            self.assertEqual(entorno.env_int("X_I", 1), 3)
            self.assertEqual(entorno.env_float("X_MAL", 1.5), 1.5)
            self.assertEqual(entorno.env_int("X_MAL", 4), 4)
            self.assertEqual(entorno.env_int("X_CERO", 4), 4)
            self.assertEqual(entorno.env_float("X_NO_EXISTE", 7), 7.0)


if __name__ == "__main__":
    unittest.main()

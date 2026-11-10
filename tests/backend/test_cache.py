"""Reglas, clave y huella de la caché de respuestas."""
import os
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

from backend.app.services import cache
from tests.backend import apoyo  # noqa: F401


class ClaveTest(unittest.TestCase):
    def test_misma_pregunta_escrita_distinto_da_la_misma_clave(self):
        variantes = ["¿Cuántas CIRUGÍAS hubo en 2024?", "cuantas cirugias hubo en 2024",
                     "  Cuántas cirugías  hubo en 2024 "]
        claves = {cache.clave_cache("h", cache.normalizar_pregunta(v), date(2026, 11, 10)) for v in variantes}
        self.assertEqual(len(claves), 1)

    def test_abreviaturas_de_chat(self):
        self.assertEqual(cache.normalizar_pregunta("camas x estado"), cache.normalizar_pregunta("camas por estado"))

    def test_cambia_con_fecha_huella_y_pregunta(self):
        base = cache.clave_cache("h1", "pregunta", date(2026, 11, 10))
        self.assertNotEqual(base, cache.clave_cache("h1", "pregunta", date(2026, 11, 11)))
        self.assertNotEqual(base, cache.clave_cache("h2", "pregunta", date(2026, 11, 10)))
        self.assertNotEqual(base, cache.clave_cache("h1", "otra", date(2026, 11, 10)))


class ReglasTest(unittest.TestCase):
    exito = {"status": "success", "route": "powerbi"}
    respuesta = {"degradada": False, "contrapregunta": None}

    def test_solo_sin_contexto_y_sin_opcion(self):
        self.assertTrue(cache.puede_leer({}, None))
        self.assertFalse(cache.puede_leer({}, None, habilitada=False))
        self.assertFalse(cache.puede_leer({"opcion_id": "a"}, None))
        self.assertFalse(cache.puede_leer({}, {"seguimiento": {"metric": "x"}}))
        self.assertFalse(cache.puede_leer({}, {"pendiente": {"plan": {"q": 1}}}))

    def test_que_se_guarda(self):
        self.assertTrue(cache.puede_guardar(self.exito, self.respuesta, None, {}))
        self.assertTrue(cache.puede_guardar({"status": "success", "route": "rag", "synthesis_mode": "generative"},
                                            self.respuesta, None, {}))
        casos = [
            ({"status": "success", "route": "rag", "synthesis_mode": "extractive"}, self.respuesta),
            ({"status": "success", "route": "conversacion"}, self.respuesta),
            ({"status": "needs_clarification", "route": "clarification"}, self.respuesta),
            ({"status": "error", "route": None}, self.respuesta),
            ({"status": "empty_result", "route": "powerbi"}, self.respuesta),
            (self.exito, {"degradada": True}),
        ]
        for result, respuesta in casos:
            with self.subTest(result=result, respuesta=respuesta):
                self.assertFalse(cache.puede_guardar(result, respuesta, None, {}))
        self.assertFalse(cache.puede_guardar(self.exito, self.respuesta, {"seguimiento": {"m": 1}}, {}))
        self.assertFalse(cache.puede_guardar(self.exito, self.respuesta, None, {"opcion_id": "x"}))


class HuellaTest(unittest.TestCase):
    def test_cambia_si_cambia_el_catalogo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            raiz = Path(carpeta)
            catalogo = raiz / "data" / "catalog"
            catalogo.mkdir(parents=True)
            archivo = catalogo / "source_registry.json"
            archivo.write_text("{}", encoding="utf-8")
            (raiz / "data" / "vector_db").mkdir(parents=True)
            (raiz / "data" / "vector_db" / ".lock").write_text("x", encoding="utf-8")
            huella = cache.Huella(raiz, raiz, intervalo_s=0)
            primera = huella.valor()
            self.assertEqual(primera, huella.valor())
            (raiz / "data" / "vector_db" / ".lock").write_text("otro candado", encoding="utf-8")
            self.assertEqual(primera, huella.valor())  # el candado de Qdrant no cuenta
            archivo.write_text('{"nuevo": true}', encoding="utf-8")
            futuro = time.time() + 5
            os.utime(archivo, (futuro, futuro))
            self.assertNotEqual(primera, huella.valor())

    def test_se_recalcula_por_intervalo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ahora = [0.0]
            huella = cache.Huella(Path(carpeta), Path(carpeta), intervalo_s=60, reloj=lambda: ahora[0])
            primera = huella.valor()
            (Path(carpeta) / "data" / "rag").mkdir(parents=True)
            (Path(carpeta) / "data" / "rag" / "m.json").write_text("{}", encoding="utf-8")
            self.assertEqual(primera, huella.valor())  # aún dentro del intervalo
            ahora[0] = 61.0
            self.assertNotEqual(primera, huella.valor())


if __name__ == "__main__":
    unittest.main()

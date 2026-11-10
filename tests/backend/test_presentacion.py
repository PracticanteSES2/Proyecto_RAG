"""Del result del motor al payload `respuesta`."""
import json
import unittest
from unittest import mock

from backend.app.services import presentacion
from tests.backend import apoyo  # noqa: F401


class PresentacionTest(unittest.TestCase):
    def test_contrapregunta_con_ids_originales(self):
        result = {"status": "needs_clarification", "route": "clarification", "prompt": "¿Cuál?",
                  "clarification_options": [{"id": "a", "label": "Opción A", "description": "Desc A"},
                                            {"id": 7, "label": "Opción B", "description": "Opción B"}],
                  "none_option": {"id": "ninguna", "label": "Ninguna de las anteriores"}}
        respuesta, pendientes, texto = presentacion.construir_respuesta(result, None, "t1")
        self.assertEqual(respuesta["ruta"], "contrapregunta")
        self.assertEqual(texto, "¿Cuál?")
        self.assertEqual(respuesta["contrapregunta"]["pregunta"], "¿Cuál?")
        opciones = respuesta["contrapregunta"]["opciones"]
        self.assertEqual([o["id"] for o in opciones], ["a", "7", "ninguna"])
        self.assertEqual(opciones[0]["descripcion"], "Desc A")
        self.assertIsNone(opciones[1]["descripcion"])  # repetía la etiqueta
        self.assertEqual(pendientes[1], {"id": "7", "id_original": 7, "texto": "Opción B"})
        json.dumps(respuesta)

    def test_dato_de_power_bi_con_detalles_y_fuente(self):
        result = {"status": "success", "route": "powerbi", "metric": "Cirugías", "value": 12,
                  "report": "Tablero Quirúrgico", "dashboard": "Cirugías", "semantic_model": "Gestión",
                  "query_plan": None}
        respuesta, _, texto = presentacion.construir_respuesta(result, None, "t1")
        self.assertEqual((respuesta["ruta"], texto), ("datos", "Cirugías: 12"))
        self.assertEqual(respuesta["fuentes"], [{"titulo": "Tablero Quirúrgico › Cirugías",
                                                 "tablero": "Tablero Quirúrgico", "pagina": "Cirugías"}])
        self.assertEqual(respuesta["detalles"]["metrica"], "Cirugías")
        self.assertFalse(respuesta["degradada"])

    def test_enlace_de_power_bi(self):
        enlace = {"url": "https://app.powerbi.com/x", "etiqueta": "Abrir Tablero › Página", "filtrado": True}
        with mock.patch("src.providers.powerbi_links.enlace_para_resultado", return_value=enlace):
            respuesta, _, _ = presentacion.construir_respuesta(
                {"status": "success", "route": "powerbi", "metric": "m", "value": 1}, None, "t1")
        self.assertEqual(respuesta["enlaces_powerbi"], [
            {"titulo": "Tablero › Página · con los filtros de la consulta", "url": "https://app.powerbi.com/x"}])

    def test_documentacion_extractiva_es_degradada(self):
        result = {"status": "success", "route": "rag", "answer": "Texto", "synthesis_mode": "extractive",
                  "synthesis_issue": "MedGemma saturado",
                  "sources": [{"dashboard": "Camas", "page": "Ocupación"},
                              {"dashboard": "Camas", "page": "Ocupación"},
                              {"source_file": "C:\\ruta\\secreta\\manual_camas.docx"}]}
        respuesta, _, _ = presentacion.construir_respuesta(result, None, "t1")
        self.assertEqual(respuesta["ruta"], "documentacion")
        self.assertTrue(respuesta["degradada"])
        self.assertIn("documentación", respuesta["aviso"])
        self.assertEqual([f["titulo"] for f in respuesta["fuentes"]], ["Camas › Ocupación", "manual_camas"])

    def test_rutas_y_textos(self):
        casos = [
            ({"status": "success", "route": "conversacion", "answer": "Hola"}, "conversacion", "Hola"),
            ({"status": "not_found", "route": "out_of_scope", "answer": "Fuera"}, "fuera_de_alcance", "Fuera"),
            ({"status": "powerbi_error", "route": "powerbi"}, "datos", None),
            ({"status": "raro", "route": None}, "otra", None),
        ]
        for result, ruta, texto in casos:
            with self.subTest(result=result):
                respuesta, _, obtenido = presentacion.construir_respuesta(result, None, "t1")
                self.assertEqual(respuesta["ruta"], ruta)
                if texto:
                    self.assertEqual(obtenido, texto)
                self.assertNotIn("diagnóstico", obtenido.lower())

    def test_diagnostico_es_json(self):
        result = {"status": "success", "route": "powerbi", "dax": "EVALUATE 1", "query_plan": {"a": {1, 2}},
                  "reasoning": {"steps": [{"title": "Paso", "lines": ["x"], "t": 0.1}], "server_state": "ok"}}
        datos = presentacion.diagnostico(result, "texto", {"total_s": 1.0}, cacheada=False)
        self.assertEqual(datos["dax"], "EVALUATE 1")
        self.assertEqual(datos["pasos"], [{"titulo": "Paso", "lineas": ["x"], "t": 0.1}])
        self.assertEqual(datos["estado_servidor"], "ok")
        json.dumps(datos)


class ReiniciarTest(unittest.TestCase):
    def test_conserva_contexto_solo_con_contrapregunta(self):
        from backend.app.services.motor import reiniciar_si_termino
        from tests.backend.motor_doble import instancia_doble

        instancia = instancia_doble()
        instancia.engine.process("cirugias 2024")
        reiniciar_si_termino({"status": "needs_clarification"}, instancia)
        self.assertIsNotNone(instancia.engine._pending_query_plan)
        reiniciar_si_termino({"status": "success"}, instancia)
        self.assertIsNone(instancia.engine._pending_query_plan)


if __name__ == "__main__":
    unittest.main()

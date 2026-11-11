"""API v1 de la documentación viva de punta a punta (TestClient): explorar,
proponer (202 + sondeo), corregir, aclarar, aprobar y reindexar, con el motor
doble embebido, el actualizador y la indexación dobles y una copia temporal
del fixture."""
import shutil
import time
import unittest

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.documentacion import ServicioDocumentacion, raiz_documentos
from backend.app.services.documentacion_indice import CoordinadorIndice
from tests.backend.apoyo import ajustes_prueba
from tests.backend.documentacion_doble import (
    GRUPO,
    ActualizadorDoble,
    IndexacionDoble,
    ProveedorDoble,
    raiz_temporal,
)
from tests.backend.motor_doble import piscina_doble

V1 = "/api/v1/documentacion"


class DocumentacionAPI(unittest.TestCase):
    def setUp(self):
        self.raiz = raiz_temporal()
        self.addCleanup(shutil.rmtree, self.raiz, True)
        self.actualizador = ActualizadorDoble()
        self.piscina = piscina_doble(instancias=1)
        self.indexacion = IndexacionDoble(self.piscina)

        def fabrica(servicios):
            raiz_docs = raiz_documentos(servicios.ajustes)
            coordinador = CoordinadorIndice(servicios.embebido, lambda: servicios.trabajador,
                                            servicios.ajustes.rag_raiz_datos, raiz_docs,
                                            reindexar=self.indexacion.reindexar_grupo)
            return ServicioDocumentacion(raiz_docs, coordinador, proponer=self.actualizador.proponer_cambio,
                                         fabrica_llm=ProveedorDoble)

        app = create_app(ajustes_prueba(rag_raiz_datos=self.raiz), fabrica_piscina=lambda: self.piscina,
                         fabrica_documentacion=fabrica)
        self.cliente = TestClient(app)
        self.cliente.__enter__()
        self.addCleanup(self.cliente.__exit__, None, None, None)
        self.esperar(lambda: self.cliente.get("/api/v1/salud").json()["listo"])

    def esperar(self, condicion, maximo_s=20.0):
        limite = time.time() + maximo_s
        while time.time() < limite:
            valor = condicion()
            if valor:
                return valor
            time.sleep(0.02)
        raise AssertionError("la condición no se cumplió a tiempo")

    def sondear(self, pid, hasta):
        def listo():
            datos = self.cliente.get(f"{V1}/propuestas/{pid}").json()
            return hasta(datos) and datos
        return self.esperar(listo)

    def proponer(self, nota="subí el semáforo de triage II a 20", **extra):
        respuesta = self.cliente.post(f"{V1}/propuestas", json={"nota": nota, "grupo": GRUPO, **extra})
        self.assertEqual(respuesta.status_code, 202, respuesta.text)
        return respuesta.json()

    def assertError(self, respuesta, estado, codigo):
        self.assertEqual(respuesta.status_code, estado, respuesta.text)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["codigo"], codigo)
        self.assertTrue(cuerpo["mensaje"])
        self.assertNotIn("Traceback", cuerpo["mensaje"])

    # ------------------------------------------------------------------
    def test_explorar_grupos_paginas_y_documento(self):
        grupos = self.cliente.get(f"{V1}/grupos").json()["grupos"]
        self.assertEqual(grupos, [{"grupo": GRUPO, "tablero": "TABLERO TIEMPOS URGENCIAS", "paginas": 32}])
        paginas = self.cliente.get(f"{V1}/grupos/{GRUPO}/paginas").json()
        self.assertEqual(len(paginas["paginas"]), 32)
        doc = self.cliente.get(f"{V1}/grupos/{GRUPO}/paginas/consultas_dia.md").json()
        self.assertEqual(doc["pagina"], "CONSULTAS DIA")
        self.assertEqual(doc["ficha"][1], {"dato": "Página", "valor": "CONSULTAS DIA"})
        self.assertEqual(doc["historial"][0]["nombre"], "2026-10-20 · v1")

    def test_errores_de_lectura(self):
        self.assertError(self.cliente.get(f"{V1}/grupos/nada/paginas"), 404, "grupo_no_encontrado")
        self.assertError(self.cliente.get(f"{V1}/grupos/{GRUPO}/paginas/no.md"), 404, "pagina_no_encontrada")
        self.assertError(self.cliente.get(f"{V1}/propuestas/{'a' * 32}"), 404, "propuesta_no_encontrada")

    def test_validaciones_amables(self):
        respuesta = self.cliente.post(f"{V1}/propuestas", json={"nota": "   ", "grupo": GRUPO})
        self.assertError(respuesta, 422, "peticion_invalida")
        self.assertEqual(respuesta.json()["mensaje"], "Escribe qué cambió en el tablero.")
        pid = self.proponer()["propuesta_id"]
        self.sondear(pid, lambda d: d["estado"] == "lista")
        respuesta = self.cliente.post(f"{V1}/propuestas/{pid}/aprobar", json={"autor": "  "})
        self.assertError(respuesta, 422, "peticion_invalida")
        self.assertEqual(respuesta.json()["mensaje"], "Escribe quién aprueba el cambio.")

    def test_flujo_completo_proponer_corregir_aprobar_y_reindexar(self):
        self.actualizador.despues.clear()
        creada = self.proponer(cambios_pbip=["Página CONSULTAS DIA: semáforo"], autor="Ana")
        self.assertEqual(creada["estado"], "preparando")
        self.assertTrue(creada["progreso"]["frase"])
        pid = creada["propuesta_id"]
        self.actualizador.despues.set()
        lista = self.sondear(pid, lambda d: d["estado"] != "preparando")
        self.assertEqual(lista["estado"], "lista")
        self.assertTrue(lista["puede_aprobar"])
        self.assertEqual(lista["diff"]["bloques"][0]["lineas"][0]["tipo"], "igual")

        corregida = self.cliente.post(f"{V1}/propuestas/{pid}/operaciones",
                                      json={"textos": [{"indice": 0, "texto": "Verde de 0 a 25 minutos."}]})
        self.assertEqual(corregida.status_code, 200, corregida.text)
        self.assertEqual(corregida.json()["operaciones"][0]["texto"], "Verde de 0 a 25 minutos.")

        aprobada = self.cliente.post(f"{V1}/propuestas/{pid}/aprobar", json={"autor": "Ana"})
        self.assertEqual(aprobada.status_code, 200, aprobada.text)
        self.assertEqual(aprobada.json()["estado"], "aprobada")
        self.assertEqual(aprobada.json()["aprobacion"]["version"], 2)
        final = self.sondear(pid, lambda d: d["aprobacion"]["reindexacion"]["estado"] not in ("en_curso", "sin_iniciar"))
        self.assertEqual(final["aprobacion"]["reindexacion"]["estado"], "lista")
        self.assertEqual(self.indexacion.llamadas[0]["libres"], 0)
        self.assertEqual(self.cliente.get(f"{V1}/grupos/{GRUPO}/reindexacion").json()["estado"], "lista")
        texto = (self.raiz / "docs_tableros" / GRUPO / "md" / "consultas_dia.md").read_text(encoding="utf-8")
        self.assertIn("Verde de 0 a 25 minutos.", texto)
        self.assertError(self.cliente.post(f"{V1}/propuestas/{pid}/aprobar", json={"autor": "Ana"}),
                         409, "propuesta_no_aprobable")

    def test_aclaracion_y_descarte(self):
        pid = self.proponer("nota ambigua")["propuesta_id"]
        vista = self.sondear(pid, lambda d: d["estado"] != "preparando")
        self.assertEqual(vista["estado"], "requiere_aclaracion")
        self.assertEqual([c["pagina"] for c in vista["candidatas"]], ["CONSULTAS DIA", "RESUMEN"])
        otra = self.cliente.post(f"{V1}/propuestas/{pid}/aclaracion",
                                 json={"nota": "nota ambigua precisada", "pagina": "RESUMEN"})
        self.assertEqual(otra.status_code, 202, otra.text)
        lista = self.sondear(pid, lambda d: d["estado"] != "preparando")
        self.assertEqual((lista["estado"], lista["pagina"]), ("lista", "RESUMEN"))
        descartada = self.cliente.post(f"{V1}/propuestas/{pid}/descartar")
        self.assertEqual(descartada.json()["estado"], "descartada")

    def test_reindexar_a_mano(self):
        respuesta = self.cliente.post(f"{V1}/grupos/{GRUPO}/reindexar")
        self.assertEqual(respuesta.status_code, 202, respuesta.text)
        self.assertIn(respuesta.json()["estado"], ("en_curso", "lista"))
        self.esperar(lambda: self.cliente.get(f"{V1}/grupos/{GRUPO}/reindexacion").json()["estado"] == "lista")
        self.assertError(self.cliente.post(f"{V1}/grupos/nada/reindexar"), 404, "grupo_no_encontrado")

    def test_contrato_en_openapi(self):
        rutas = self.cliente.get("/api/v1/openapi.json").json()["paths"]
        for ruta in ("/grupos", "/grupos/{grupo}/paginas", "/grupos/{grupo}/paginas/{archivo}", "/propuestas",
                     "/propuestas/{propuesta_id}", "/propuestas/{propuesta_id}/operaciones",
                     "/propuestas/{propuesta_id}/aclaracion", "/propuestas/{propuesta_id}/descartar",
                     "/propuestas/{propuesta_id}/aprobar", "/grupos/{grupo}/reindexar",
                     "/grupos/{grupo}/reindexacion"):
            self.assertIn(V1 + ruta, rutas)


if __name__ == "__main__":
    unittest.main()

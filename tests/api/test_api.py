"""API v1 de punta a punta (TestClient + SSE) con el motor doble, en memoria y
con Redis falso (fakeredis, motor embebido)."""
import json
import os
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from tests.backend.apoyo import ajustes_prueba
from tests.backend.motor_doble import piscina_doble

V1 = "/api/v1"


def leer_sse(cliente, url, cabeceras=None, maximo_s=60.0, al_evento=None):
    """Lista de {"event", "data", "id"?} hasta `fin` (o fin del flujo)."""
    eventos, actual = [], {}
    limite = time.time() + maximo_s
    with cliente.stream("GET", url, headers=cabeceras or {}) as respuesta:
        assert respuesta.status_code == 200, respuesta.read()
        assert respuesta.headers["content-type"].startswith("text/event-stream")
        for linea in respuesta.iter_lines():
            if time.time() > limite:
                raise AssertionError("el SSE no terminó a tiempo")
            if linea == "":
                if "event" in actual:
                    actual["data"] = json.loads(actual.get("data") or "{}")
                    eventos.append(actual)
                    if al_evento:
                        al_evento(actual)
                    if actual["event"] == "fin":
                        break
                actual = {}
                continue
            if linea.startswith(":"):
                continue
            campo, _, valor = linea.partition(": ")
            actual[campo] = valor
    return eventos


class BaseAPI:
    modo = None
    demora_s = 0.0
    cambios = {}

    def setUp(self):
        self.piscina = piscina_doble(instancias=1, demora_s=self.demora_s)
        if self.modo == "redis":
            import fakeredis

            servidor = fakeredis.FakeServer()
            ajustes = ajustes_prueba(redis_url="redis://falso:6379/0", motor_modo="embebido", **self.cambios)
            app = create_app(ajustes, redis_api=fakeredis.FakeAsyncRedis(server=servidor),
                             redis_trabajador=fakeredis.FakeRedis(server=servidor),
                             fabrica_piscina=lambda: self.piscina)
            self.servidor = servidor
        else:
            app = create_app(ajustes_prueba(**self.cambios), fabrica_piscina=lambda: self.piscina)
        self.app = app
        self.cliente = TestClient(app)
        self.cliente.__enter__()
        self.addCleanup(self.cliente.__exit__, None, None, None)
        self.esperar_motor()

    def esperar_motor(self, maximo_s=60):
        limite = time.time() + maximo_s
        while time.time() < limite:
            if self.cliente.get(f"{V1}/salud").json()["listo"]:
                return
            time.sleep(0.05)
        raise AssertionError("el motor embebido no arrancó")

    def conversacion(self):
        respuesta = self.cliente.post(f"{V1}/conversaciones")
        self.assertEqual(respuesta.status_code, 201)
        return respuesta.json()["conversacion_id"]

    def enviar(self, cid, mensaje="", esperado=202, **extra):
        cuerpo = {"mensaje": mensaje, **extra}
        respuesta = self.cliente.post(f"{V1}/conversaciones/{cid}/turnos", json=cuerpo,
                                      headers={"X-Cliente-Id": "navegador-prueba-1"})
        self.assertEqual(respuesta.status_code, esperado, respuesta.text)
        return respuesta.json()

    def preguntar(self, cid, mensaje="", **extra):
        creado = self.enviar(cid, mensaje, **extra)
        return creado["turno_id"], leer_sse(self.cliente, creado["eventos_url"])

    @staticmethod
    def de(eventos, nombre):
        return [e["data"] for e in eventos if e["event"] == nombre]


class FlujosAPI(BaseAPI):
    def test_charla_de_punta_a_punta(self):
        cid = self.conversacion()
        self.assertEqual(self.cliente.get(f"{V1}/conversaciones/{cid}").json()["mensajes"], [])
        tid, eventos = self.preguntar(cid, "hola")
        nombres = [e["event"] for e in eventos]
        self.assertEqual(nombres[0], "progreso")
        self.assertEqual(nombres[-2:], ["respuesta", "fin"])
        self.assertTrue(all("id" in e for e in eventos))
        respuesta = self.de(eventos, "respuesta")[0]
        self.assertEqual((respuesta["turno_id"], respuesta["ruta"]), (tid, "conversacion"))
        historial = self.cliente.get(f"{V1}/conversaciones/{cid}").json()
        self.assertEqual([m["rol"] for m in historial["mensajes"]], ["usuario", "asistente"])
        self.assertEqual(historial["mensajes"][1]["respuesta"]["texto_markdown"], "¡Hola! Soy el asistente.")
        self.assertNotIn("razonamiento", historial["mensajes"][1])
        self.assertIsNone(historial["turno_activo"])

    def test_contrapregunta_y_opcion(self):
        cid = self.conversacion()
        _, eventos = self.preguntar(cid, "cirugias 2024")
        opciones = self.de(eventos, "respuesta")[0]["contrapregunta"]["opciones"]
        historial = self.cliente.get(f"{V1}/conversaciones/{cid}").json()
        self.assertTrue(historial["mensajes"][-1]["contrapregunta_vigente"])
        self.enviar(cid, "", esperado=409, opcion_id="inventada")
        _, eventos = self.preguntar(cid, "", opcion_id=opciones[0]["id"])
        respuesta = self.de(eventos, "respuesta")[0]
        self.assertEqual((respuesta["ruta"], respuesta["estado"]), ("datos", "success"))
        historial = self.cliente.get(f"{V1}/conversaciones/{cid}").json()
        self.assertEqual(historial["mensajes"][2]["via"], "opcion")
        self.assertEqual(historial["mensajes"][2]["texto"], opciones[0]["texto"])
        self.assertFalse(any(m["contrapregunta_vigente"] for m in historial["mensajes"]))

    def test_errores_amables(self):
        self.assertEqual(self.cliente.get(f"{V1}/conversaciones/{'0' * 32}").json()["codigo"],
                         "conversacion_no_encontrada")
        self.assertEqual(self.cliente.get(f"{V1}/conversaciones/no-es-un-id").status_code, 404)
        self.assertEqual(self.cliente.get(f"{V1}/turnos/{'0' * 32}/eventos").json()["codigo"], "turno_no_encontrado")
        cid = self.conversacion()
        invalido = self.enviar(cid, "   ", esperado=422)
        self.assertEqual(invalido, {"mensaje": "Escribe una pregunta o elige una opción.",
                                    "codigo": "peticion_invalida"})
        self.assertEqual(self.enviar(cid, "x" * 2001, esperado=422)["codigo"], "peticion_invalida")
        _, eventos = self.preguntar(cid, "explota")
        error = self.de(eventos, "error")[0]
        self.assertEqual(error["codigo"], "error_motor")
        self.assertNotIn("secreto", json.dumps(eventos))
        self.assertEqual(self.cliente.get(f"{V1}/conversaciones/{cid}/exportar?formato=pdf").json()["codigo"],
                         "formato_no_soportado")

    def test_reconexion_con_last_event_id_y_reconstruccion(self):
        cid = self.conversacion()
        tid, eventos = self.preguntar(cid, "total de atenciones")
        primero = eventos[0]["id"]
        resto = leer_sse(self.cliente, f"{V1}/turnos/{tid}/eventos", {"Last-Event-ID": primero})
        self.assertEqual([e["id"] for e in resto], [e["id"] for e in eventos[1:]])
        self.borrar_eventos(tid)
        reconstruidos = leer_sse(self.cliente, f"{V1}/turnos/{tid}/eventos")
        self.assertEqual([e["event"] for e in reconstruidos], ["respuesta", "fin"])
        self.assertEqual(reconstruidos[0]["data"]["texto_markdown"], self.de(eventos, "respuesta")[0]["texto_markdown"])

    def borrar_eventos(self, tid):
        if self.modo == "redis":
            import fakeredis

            fakeredis.FakeRedis(server=self.servidor).delete(f"rag:turno:{tid}:eventos")
        else:
            self.app.state.servicios.almacen._eventos.pop(tid)

    def test_diagnostico_cache_y_exportacion(self):
        cid = self.conversacion()
        _, eventos = self.preguntar(cid, "total de atenciones", diagnostico=True)
        diagnostico = self.de(eventos, "respuesta")[0]["diagnostico"]
        self.assertIn("dax", diagnostico)
        _, eventos = self.preguntar(self.conversacion(), "Total de Atenciones", diagnostico=True)
        self.assertTrue(self.de(eventos, "respuesta")[0]["cacheada"])
        exportada = self.cliente.get(f"{V1}/conversaciones/{cid}/exportar?formato=md")
        self.assertEqual(exportada.status_code, 200)
        self.assertIn("attachment", exportada.headers["content-disposition"])
        self.assertIn("## Turno 1", exportada.text)
        self.assertIn("total de atenciones", exportada.text)
        self.assertIn("Razonamiento del asistente", exportada.text)
        sin_razonamiento = self.cliente.get(f"{V1}/conversaciones/{cid}/exportar?razonamiento=false").text
        self.assertNotIn("Razonamiento del asistente", sin_razonamiento)

    def test_calificacion(self):
        cid = self.conversacion()
        tid, _ = self.preguntar(cid, "total de atenciones")
        url = f"{V1}/turnos/{tid}/calificacion"
        self.assertEqual(self.cliente.post(url, json={"valor": "mala"}).status_code, 422)
        self.assertEqual(self.cliente.post(url, json={"valor": "regular"}).status_code, 422)
        self.assertEqual(self.cliente.post(url, json={"valor": "buena"}).json(), {"guardada": True})
        self.assertEqual(self.cliente.post(url, json={"valor": "buena"}).json(), {"guardada": True})
        self.assertEqual(self.cliente.post(url, json={"valor": "mala", "comentario": "Esperaba 43"}).status_code, 200)
        archivo = Path(os.environ["FEEDBACK_DIR"]) / "calificaciones.jsonl"
        registros = [json.loads(texto) for texto in archivo.read_text(encoding="utf-8").splitlines()]
        propias = [r for r in registros if r["id_sesion"] == cid[:12]]
        self.assertEqual([r["calificacion"] for r in propias], ["buena", "mala"])
        self.assertEqual(propias[-1]["esperado"], "Esperaba 43")

    def test_capacidades_salud_diagnostico_y_openapi(self):
        capacidades = self.cliente.get(f"{V1}/capacidades").json()
        self.assertTrue(capacidades["listo"])
        self.assertIn("¿Qué tableros puedo consultar?", capacidades["ejemplos"])
        salud = self.cliente.get(f"{V1}/salud").json()
        self.assertEqual(salud["modo"], self.modo)
        self.assertEqual(salud["componentes"]["motor"]["estado"], "ok")
        self.assertEqual(salud["componentes"]["medgemma"]["estado"], "ok")
        self.assertNotIn("redis://", json.dumps(salud))
        self.assertEqual(self.cliente.get(f"{V1}/salud/listo").status_code, 200)
        diagnostico = self.cliente.get(f"{V1}/diagnostico/servidor").json()
        self.assertTrue(diagnostico["disponible"])
        self.assertTrue(any("MedGemma" in texto for texto in diagnostico["lineas_markdown"]))
        rutas = self.cliente.get(f"{V1}/openapi.json").json()["paths"]
        for ruta in ("/api/v1/conversaciones", "/api/v1/conversaciones/{conversacion_id}/turnos",
                     "/api/v1/turnos/{turno_id}/eventos", "/api/v1/turnos/{turno_id}/calificacion",
                     "/api/v1/capacidades", "/api/v1/salud", "/api/v1/diagnostico/servidor"):
            self.assertIn(ruta, rutas)

    def test_cors_para_el_frontend(self):
        respuesta = self.cliente.options(f"{V1}/conversaciones", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
        self.assertEqual(respuesta.headers.get("access-control-allow-origin"), "http://localhost:3000")


class APIMemoriaTest(FlujosAPI, unittest.TestCase):
    modo = "memoria"


class APIRedisTest(FlujosAPI, unittest.TestCase):
    modo = "redis"


class ConcurrenciaAPI(BaseAPI):
    # Sin caché: ningún turno puede saltarse la fila (ni por coincidencia de pregunta).
    cambios = {"limite_turnos": 3, "cache_habilitada": False}

    def test_turno_en_curso_cola_y_limite(self):
        """Determinista: el turno A («bloquea») retiene la única instancia del motor
        hasta que el SSE de B (diagnóstico) recibe su primer `cola`; recién entonces
        se abre la compuerta. Sin dependencia de tiempos."""
        compuerta = self.piscina.principal.engine.compuerta
        self.addCleanup(compuerta.set)
        cid_a, cid_b = self.conversacion(), self.conversacion()
        bloqueado = self.enviar(cid_a, "bloquea")
        self.enviar(cid_a, "hola", esperado=409)
        segundo = self.enviar(cid_b, "hola", diagnostico=True)
        normal = self.cliente.post(f"{V1}/conversaciones/{self.conversacion()}/turnos", json={"mensaje": "hola"},
                                   headers={"X-Cliente-Id": "navegador-prueba-3"}).json()

        def abrir_al_ver_cola(evento):
            if evento["event"] == "cola":
                compuerta.set()

        eventos_b = leer_sse(self.cliente, segundo["eventos_url"], al_evento=abrir_al_ver_cola)
        eventos_normal = leer_sse(self.cliente, normal["eventos_url"])
        # Modo diagnóstico: recibió su posición mientras A retenía el motor.
        cola = self.de(eventos_b, "cola")
        self.assertTrue(cola, eventos_b)
        # {2,0} si el trabajador aún no había tomado A; {1,1} si ya lo tenía.
        self.assertIn(cola[0], ({"posicion": 1, "en_curso": 1}, {"posicion": 2, "en_curso": 0}))
        self.assertNotIn("en_cola", [d["etapa"] for d in self.de(eventos_b, "progreso")])
        # Modo normal: también esperó en la fila, pero nunca ve `cola` y lo primero es `progreso`.
        self.assertNotIn("cola", [e["event"] for e in eventos_normal])
        self.assertEqual(eventos_normal[0]["event"], "progreso")
        self.assertTrue(all("id" in e for e in eventos_normal))
        self.assertEqual(self.de(leer_sse(self.cliente, bloqueado["eventos_url"]), "respuesta")[0]["estado"],
                         "success")
        # El límite cuenta cada intento del navegador (también el rechazado con 409): el cuarto es 429.
        demasiadas = self.cliente.post(f"{V1}/conversaciones/{self.conversacion()}/turnos", json={"mensaje": "hola"},
                                       headers={"X-Cliente-Id": "navegador-prueba-1"})
        self.assertEqual(demasiadas.status_code, 429)
        self.assertEqual(demasiadas.json()["codigo"], "demasiadas_peticiones")
        self.assertGreaterEqual(int(demasiadas.headers["Retry-After"]), 1)
        otro = self.cliente.post(f"{V1}/conversaciones/{self.conversacion()}/turnos", json={"mensaje": "hola"},
                                 headers={"X-Cliente-Id": "navegador-prueba-2"})
        self.assertEqual(otro.status_code, 202)


class ConcurrenciaMemoriaTest(ConcurrenciaAPI, unittest.TestCase):
    modo = "memoria"


class ConcurrenciaRedisTest(ConcurrenciaAPI, unittest.TestCase):
    modo = "redis"


if __name__ == "__main__":
    unittest.main()

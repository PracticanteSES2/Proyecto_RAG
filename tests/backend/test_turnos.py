"""ProcesadorTurnos y Trabajador con el motor doble, en memoria y en Redis (fakeredis)."""
import asyncio
import time
import unittest
import uuid

from backend.app.services.cache import Huella
from backend.app.services.motor import SerializadorEstado
from backend.app.services.trabajador import Trabajador
from backend.app.services.turnos import ProcesadorTurnos
from tests.backend.apoyo import ajustes_prueba, almacenes
from tests.backend.motor_doble import piscina_doble


class BaseTurnos:
    modo = None

    def setUp(self):
        self.api, self.almacen, _ = almacenes(self.modo)
        self.ajustes = ajustes_prueba()
        self.piscina = piscina_doble()
        self.huella = Huella(self.ajustes.rag_raiz_datos, self.ajustes.rag_raiz_datos, intervalo_s=3600)
        self.procesador = ProcesadorTurnos(self.almacen, self.piscina, SerializadorEstado("s"), self.ajustes,
                                           huella=self.huella, intervalo_tic_s=0.05)
        self.cid = self.conversacion()

    def conversacion(self):
        cid = uuid.uuid4().hex
        asyncio.run(self.api.crear_conversacion(cid, 60))
        return cid

    def encolar(self, cid, mensaje="", opcion_id=None, diagnostico=False):
        turno = {"turno_id": uuid.uuid4().hex, "conversacion_id": cid, "mensaje": mensaje, "opcion_id": opcion_id,
                 "opcion_texto": None, "via": "opcion" if opcion_id else "texto", "diagnostico": diagnostico,
                 "cliente": "c", "estado": "en_cola", "creado": "2026-11-10T10:00:00-05:00",
                 "creado_ms": int(time.time() * 1000), "respuesta": None, "error": None, "snapshot": None,
                 "calificacion": None}
        asyncio.run(self.api.reservar_turno(cid, turno["turno_id"], 60))
        asyncio.run(self.api.encolar_turno(turno, 10, 60))
        return turno["turno_id"]

    def turno(self, cid, mensaje="", **extra):
        tid = self.encolar(cid, mensaje, **extra)
        tomado = self.almacen.tomar_turno("w", 200)
        self.assertEqual(tomado["turno_id"], tid)
        self.procesador.procesar(tomado)
        self.almacen.confirmar(tomado)
        eventos = asyncio.run(self.api.leer_eventos(tid, "0", 0))
        return tid, eventos

    @staticmethod
    def de(eventos, nombre):
        return [d for _, n, d in eventos if n == nombre]

    # ------------------------------------------------------------------
    def test_charla_orden_de_eventos_y_estado_final(self):
        tid, eventos = self.turno(self.cid, "hola")
        nombres = [n for _, n, _ in eventos]
        self.assertEqual(nombres[0], "progreso")
        self.assertEqual(nombres[-2:], ["respuesta", "fin"])
        respuesta = self.de(eventos, "respuesta")[0]
        self.assertEqual((respuesta["ruta"], respuesta["texto_markdown"]), ("conversacion", "¡Hola! Soy el asistente."))
        self.assertIsNone(respuesta["diagnostico"])
        turno = asyncio.run(self.api.turno(tid))
        self.assertEqual(turno["estado"], "terminado")
        self.assertEqual(turno["snapshot"]["pregunta"], "hola")
        conv = asyncio.run(self.api.conversacion(self.cid))
        self.assertIsNone(conv["turno_activo"])
        self.assertEqual([m["rol"] for m in conv["mensajes"]], ["usuario", "asistente"])
        self.assertTrue(conv["frases"])  # memoria de frases de progreso por sesión

    def test_contrapregunta_y_opcion_entre_conversaciones(self):
        _, eventos = self.turno(self.cid, "cirugias 2024")
        respuesta = self.de(eventos, "respuesta")[0]
        self.assertEqual(respuesta["ruta"], "contrapregunta")
        opciones = respuesta["contrapregunta"]["opciones"]
        self.assertEqual([o["id"] for o in opciones], ["b_cx", "7"])
        # Otra conversación se cuela en medio en la MISMA instancia del motor.
        otra = self.conversacion()
        _, eventos_otra = self.turno(otra, "y en 2025?")
        self.assertEqual(self.de(eventos_otra, "respuesta")[0]["estado"], "metric_not_resolved")
        # La primera elige la opción de id numérico: el motor recibe el id original.
        _, eventos = self.turno(self.cid, "", opcion_id="7")
        respuesta = self.de(eventos, "respuesta")[0]
        self.assertEqual((respuesta["estado"], respuesta["ruta"]), ("success", "datos"))
        self.assertIn(("opcion", 7), self.piscina.principal.engine.llamadas)
        conv = asyncio.run(self.api.conversacion(self.cid))
        self.assertEqual(conv["mensajes"][2]["texto"], "Cirugías realizadas (Atenciones)")
        self.assertEqual(conv["opciones"], [])
        # Seguimiento: usa el dato de su propia conversación.
        _, eventos = self.turno(self.cid, "y en 2025?")
        self.assertEqual(self.de(eventos, "respuesta")[0]["estado"], "success")

    def test_opcion_no_vigente(self):
        _, eventos = self.turno(self.cid, "", opcion_id="inventada")
        self.assertEqual(self.de(eventos, "error")[0]["codigo"], "opcion_no_vigente")
        self.assertEqual([n for _, n, _ in eventos][-1], "fin")

    def test_error_del_motor_sin_detalles(self):
        tid, eventos = self.turno(self.cid, "explota")
        error = self.de(eventos, "error")[0]
        self.assertEqual(error["codigo"], "error_motor")
        self.assertNotIn("secreto", str(eventos))
        self.assertEqual(asyncio.run(self.api.turno(tid))["estado"], "error")
        self.assertIsNone(asyncio.run(self.api.conversacion(self.cid))["turno_activo"])

    def test_diagnostico_y_progreso_de_actividades(self):
        _, eventos = self.turno(self.cid, "total de atenciones", diagnostico=True)
        respuesta = self.de(eventos, "respuesta")[0]
        self.assertEqual(respuesta["diagnostico"]["dax"], 'EVALUATE ROW("v", [Cirugias])')
        self.assertFalse(respuesta["diagnostico"]["cacheada"])
        self.assertIn("motor_s", respuesta["diagnostico"]["tiempos"])
        etapas = [d["etapa"] for d in self.de(eventos, "progreso")]
        self.assertEqual(etapas[0], "entendiendo")
        self.assertIn("buscando_indicador", etapas)
        self.assertEqual(etapas[-1], "finalizando")

    def test_tokens_de_la_redaccion(self):
        _, eventos = self.turno(self.cid, "documentacion")
        self.assertEqual([d["texto"] for d in self.de(eventos, "token")], ["El tablero ", "muestra la ocupación."])
        nombres = [n for _, n, _ in eventos]
        self.assertLess(nombres.index("token"), nombres.index("respuesta"))

    def test_respuesta_degradada_con_aviso(self):
        _, eventos = self.turno(self.cid, "documentacion saturada")
        self.assertEqual(self.de(eventos, "aviso")[0]["motivo"], "saturado")
        self.assertTrue(self.de(eventos, "respuesta")[0]["degradada"])

    def test_cache_entre_conversaciones_nuevas(self):
        _, primero = self.turno(self.cid, "Total de atenciones")
        self.assertFalse(self.de(primero, "respuesta")[0]["cacheada"])
        llamadas = len(self.piscina.principal.engine.llamadas)
        otra = self.conversacion()
        _, segundo = self.turno(otra, "¿total de ATENCIONES?", diagnostico=True)
        respuesta = self.de(segundo, "respuesta")[0]
        self.assertTrue(respuesta["cacheada"])
        self.assertTrue(respuesta["diagnostico"]["cacheada"])
        self.assertEqual(len(self.piscina.principal.engine.llamadas), llamadas)  # el motor no se usó
        # El contexto que deja la respuesta cacheada permite el seguimiento.
        _, tercero = self.turno(otra, "y en 2025?")
        self.assertEqual(self.de(tercero, "respuesta")[0]["estado"], "success")

    def test_sin_cache_con_contexto_ni_degradadas(self):
        self.turno(self.cid, "hola")  # ya hay memoria en la conversación
        self.turno(self.cid, "total de atenciones")
        otra = self.conversacion()
        _, eventos = self.turno(otra, "total de atenciones")
        self.assertFalse(self.de(eventos, "respuesta")[0]["cacheada"])  # la primera no se guardó (tenía contexto)
        self.turno(self.conversacion(), "documentacion saturada")
        _, eventos = self.turno(self.conversacion(), "documentacion saturada")
        self.assertFalse(self.de(eventos, "respuesta")[0]["cacheada"])

    def test_huerfano(self):
        tid = self.encolar(self.cid, "hola")
        tomado = self.almacen.tomar_turno("w", 200)
        self.procesador.cerrar_huerfano(tomado)
        eventos = asyncio.run(self.api.leer_eventos(tid, "0", 0))
        self.assertEqual([n for _, n, _ in eventos], ["error", "fin"])
        self.assertEqual(eventos[0][2]["codigo"], "interrumpido")


class TurnosMemoriaTest(BaseTurnos, unittest.TestCase):
    modo = "memoria"


class TurnosRedisTest(BaseTurnos, unittest.TestCase):
    modo = "redis"


class TrabajadorTest(unittest.TestCase):
    def test_atiende_la_cola_con_dos_instancias_y_publica_estado(self):
        api, almacen, _ = almacenes("memoria")
        ajustes = ajustes_prueba()
        piscina = piscina_doble(instancias=2, demora_s=0.3)
        procesador = ProcesadorTurnos(almacen, piscina, SerializadorEstado("s"), ajustes, intervalo_tic_s=0.05)
        trabajador = Trabajador(almacen, procesador, piscina, ajustes, version="abc")
        ids = []
        for _ in range(4):
            cid = uuid.uuid4().hex
            asyncio.run(api.crear_conversacion(cid, 60))
            tid = uuid.uuid4().hex
            turno = {"turno_id": tid, "conversacion_id": cid, "mensaje": "lento", "diagnostico": False,
                     "estado": "en_cola", "creado_ms": int(time.time() * 1000)}
            asyncio.run(api.encolar_turno(turno, 10, 60))
            ids.append(tid)
        trabajador.iniciar()
        try:
            limite = time.time() + 10
            while time.time() < limite:
                estados = [asyncio.run(api.turno(t))["estado"] for t in ids]
                if all(e == "terminado" for e in estados):
                    break
                time.sleep(0.05)
            self.assertEqual(estados, ["terminado"] * 4)
            for instancia in piscina.instancias:
                self.assertEqual(instancia.engine.max_concurrentes, 1)
            latido = asyncio.run(api.leer_motor("latido"))
            self.assertEqual((latido["instancias"], latido["version"]), (2, "abc"))
            self.assertEqual(latido["medgemma"]["estado"], "ok")
            self.assertIn("lineas_markdown", asyncio.run(api.leer_motor("diagnostico")))
            self.assertTrue(asyncio.run(api.leer_motor("capacidades"))["listo"])
            esperas = [d for t in ids for _, n, d in asyncio.run(api.leer_eventos(t, "0", 0)) if n == "progreso"]
            self.assertIn("consultando_powerbi", [d["etapa"] for d in esperas])
        finally:
            trabajador.detener()


if __name__ == "__main__":
    unittest.main()

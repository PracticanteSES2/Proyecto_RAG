"""Estado del motor por conversación: aislamiento con sesión explícita, firma y piscina."""
import json
import threading
import time
import unittest

from backend.app.services.motor import (
    PiscinaMotores,
    RecuperadorConCandado,
    SerializadorEstado,
    SesionExplicita,
    sin_contexto,
)
from tests.backend import apoyo  # noqa: F401  (rutas y FEEDBACK_DIR)
from tests.backend.motor_doble import instancia_doble, piscina_doble

OPCION_B = {"id_original": "b_cx", "texto": "Cirugías realizadas (Quirúrgico)"}


class AislamientoTest(unittest.TestCase):
    def test_una_conversacion_no_ve_el_contexto_de_otra(self):
        instancia, sesiones = instancia_doble(), SesionExplicita()
        motor = instancia.engine
        # A: deja una contrapregunta pendiente.
        _, estado_a = sesiones.ejecutar(instancia, None, "cirugias 2024")
        self.assertEqual(estado_a["pendiente"]["plan"], {"pregunta": "cirugias 2024"})
        # B: conversación nueva en la misma instancia; el motor no guardó nada de A.
        self.assertIsNone(motor._pending_query_plan)
        self.assertEqual(len(motor.conversation_memory), 0)
        _, estado_b = sesiones.ejecutar(instancia, None, "hola")
        self.assertIsNone(estado_b["pendiente"]["plan"])
        # B no puede responder la contrapregunta de A.
        ajeno, _ = sesiones.ejecutar(instancia, estado_b, "", OPCION_B)
        self.assertEqual(ajeno["status"], "metric_not_resolved")
        # A continúa: su pendiente responde la opción.
        resultado, estado_a = sesiones.ejecutar(instancia, estado_a, "", OPCION_B)
        self.assertEqual(resultado["status"], "success")
        # B pregunta un seguimiento: no hereda el dato de A.
        resultado, estado_b = sesiones.ejecutar(instancia, estado_b, "y en 2025?")
        self.assertEqual(resultado["status"], "metric_not_resolved")
        # A sí puede seguir su tema.
        resultado, estado_a = sesiones.ejecutar(instancia, estado_a, "y en 2025?")
        self.assertEqual(resultado["status"], "success")
        self.assertEqual([t["user"] for t in estado_a["memoria"]["turnos"]],
                         ["cirugias 2024", "Cirugías realizadas (Quirúrgico)", "y en 2025?"])

    def test_cierra_el_turno_y_conserva_contexto_solo_con_contrapregunta(self):
        instancia, sesiones = instancia_doble(), SesionExplicita()
        _, estado = sesiones.ejecutar(instancia, None, "cirugias 2024")
        self.assertIsNotNone(estado["pendiente"]["plan"])
        _, estado = sesiones.ejecutar(instancia, estado, "otra cosa")
        self.assertIsNone(estado["pendiente"]["plan"])
        self.assertIsNotNone(estado["seguimiento"])

    def test_si_el_motor_lanza_el_estado_previo_queda_intacto(self):
        instancia, sesiones = instancia_doble(), SesionExplicita()
        _, estado = sesiones.ejecutar(instancia, None, "cirugias 2024")
        copia = json.loads(json.dumps(estado))
        with self.assertRaises(RuntimeError):
            sesiones.ejecutar(instancia, estado, "explota")
        self.assertEqual(estado, copia)

    def test_estado_incompatible_empieza_sin_contexto(self):
        instancia, sesiones = instancia_doble(), SesionExplicita()
        with self.assertLogs("backend.app.services.motor", "WARNING"):
            resultado, estado = sesiones.ejecutar(instancia, {"version": 0}, "y en 2025?")
        self.assertEqual(resultado["status"], "metric_not_resolved")
        self.assertEqual(len(estado["memoria"]["turnos"]), 1)

    def test_sin_contexto(self):
        instancia, sesiones = instancia_doble(), SesionExplicita()
        self.assertTrue(sin_contexto(None))
        from src.chatbot.estado_conversacion import EstadoConversacion

        self.assertTrue(sin_contexto(EstadoConversacion().to_dict()))
        _, estado = sesiones.ejecutar(instancia, None, "hola")
        self.assertFalse(sin_contexto(estado))  # ya hay memoria


class SerializadorTest(unittest.TestCase):
    def test_ida_y_vuelta_json_y_firma(self):
        instancia = instancia_doble()
        _, estado_motor = SesionExplicita().ejecutar(instancia, None, "cirugias 2024")
        serializador = SerializadorEstado("secreto")
        datos = serializador.a_bytes(estado_motor)
        self.assertEqual(json.loads(datos[32:].decode("utf-8")), estado_motor)  # JSON, no pickle
        estado = serializador.de_bytes(datos)
        self.assertEqual(estado["pendiente"]["plan"], {"pregunta": "cirugias 2024"})
        manipulado = datos[:-1] + bytes([datos[-1] ^ 1])
        with self.assertLogs("backend.app.services.motor", "WARNING"):
            self.assertIsNone(serializador.de_bytes(manipulado))
        with self.assertLogs("backend.app.services.motor", "WARNING"):
            self.assertIsNone(SerializadorEstado("otro").de_bytes(datos))
        self.assertIsNone(serializador.de_bytes(None))
        self.assertIsNone(serializador.a_bytes(None))


class PiscinaTest(unittest.TestCase):
    def test_cada_instancia_atiende_un_turno_a_la_vez(self):
        piscina = piscina_doble(instancias=2)
        self.assertEqual((piscina.total, piscina.libres), (2, 2))
        ocupadas = []

        def usar():
            with piscina.tomar() as instancia:
                ocupadas.append(piscina.ocupadas)
                instancia.engine.process("hola")
                time.sleep(0.05)

        hilos = [threading.Thread(target=usar) for _ in range(5)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        self.assertLessEqual(max(ocupadas), 2)
        self.assertEqual(piscina.libres, 2)
        for instancia in piscina.instancias:
            self.assertEqual(instancia.engine.max_concurrentes, 1)

    def test_piscina_vacia(self):
        with self.assertRaises(ValueError):
            PiscinaMotores([])


class RecuperadorConCandadoTest(unittest.TestCase):
    def test_serializa_las_llamadas_y_el_modelo(self):
        class Modelo:
            def __init__(self):
                self.activos = self.maximo = 0

            def encode(self, texto):
                self.activos += 1
                self.maximo = max(self.maximo, self.activos)
                time.sleep(0.01)
                self.activos -= 1
                return [0.0]

        class Recuperador:
            collection_name = "prueba"

            def __init__(self):
                self.model = Modelo()

            def search(self, pregunta):
                return self.model.encode(pregunta)

        real = Recuperador()
        compartido = RecuperadorConCandado(real, threading.RLock())
        self.assertEqual(compartido.collection_name, "prueba")
        hilos = [threading.Thread(target=compartido.search, args=("x",)) for _ in range(4)]
        hilos += [threading.Thread(target=compartido.model.encode, args=("y",)) for _ in range(4)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        self.assertEqual(real.model.maximo, 1)


if __name__ == "__main__":
    unittest.main()

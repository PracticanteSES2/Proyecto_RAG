"""Estado del motor por conversación: aislamiento, firma y piscina."""
import threading
import time
import unittest

from backend.app.services.motor import (
    PiscinaMotores,
    RecuperadorConCandado,
    SerializadorEstado,
    capturar_estado,
    restaurar_estado,
    sin_contexto,
)
from tests.backend import apoyo  # noqa: F401  (rutas y FEEDBACK_DIR)
from tests.backend.motor_doble import instancia_doble, piscina_doble


class AislamientoTest(unittest.TestCase):
    def test_una_conversacion_no_ve_el_contexto_de_otra(self):
        instancia = instancia_doble()
        motor = instancia.engine
        # A: deja una contrapregunta pendiente.
        restaurar_estado(instancia, None)
        motor.process("cirugias 2024")
        estado_a = capturar_estado(instancia)
        # B: conversación nueva en la misma instancia.
        restaurar_estado(instancia, None)
        self.assertIsNone(motor._pending_query_plan)
        self.assertEqual(len(motor.conversation_memory), 0)
        motor.process("hola")
        estado_b = capturar_estado(instancia)
        # A continúa: su pendiente vuelve y responde la opción.
        restaurar_estado(instancia, estado_a)
        self.assertEqual(motor._pending_query_plan, {"pregunta": "cirugias 2024"})
        resultado = motor.select_clarification_option("b_cx", "Cirugías realizadas (Quirúrgico)")
        self.assertEqual(resultado["status"], "success")
        estado_a = capturar_estado(instancia)
        # B pregunta un seguimiento: no hereda el dato de A.
        restaurar_estado(instancia, estado_b)
        self.assertEqual(motor.process("y en 2025?")["status"], "metric_not_resolved")
        # A sí puede seguir su tema.
        restaurar_estado(instancia, estado_a)
        self.assertEqual(motor.process("y en 2025?")["status"], "success")

    def test_restaurar_limpia_el_estado_del_turno(self):
        instancia = instancia_doble()
        instancia.engine._trace = object()
        instancia.engine.last_reasoning = {"x": 1}
        restaurar_estado(instancia, None)
        self.assertIsNone(instancia.engine._trace)
        self.assertIsNone(instancia.engine.last_reasoning)

    def test_sin_contexto(self):
        instancia = instancia_doble()
        restaurar_estado(instancia, None)
        self.assertTrue(sin_contexto(None))
        self.assertTrue(sin_contexto(capturar_estado(instancia)))
        instancia.engine.process("hola")
        self.assertFalse(sin_contexto(capturar_estado(instancia)))  # ya hay memoria


class SerializadorTest(unittest.TestCase):
    def test_ida_y_vuelta_y_firma(self):
        instancia = instancia_doble()
        instancia.engine.process("cirugias 2024")
        serializador = SerializadorEstado("secreto")
        datos = serializador.a_bytes(capturar_estado(instancia))
        estado = serializador.de_bytes(datos)
        self.assertEqual(estado["_pending_query_plan"], {"pregunta": "cirugias 2024"})
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

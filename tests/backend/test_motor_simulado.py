"""El motor REAL (src/chatbot/fabrica.py) detrás del backend, con Power BI,
Ollama y Qdrant simulados (tests/sim: nunca abre .env ni toca servicios).

Verifica lo que más importa del backend frente al motor real: dos
conversaciones intercaladas en la MISMA instancia no se mezclan (cada una
responde su propia contrapregunta) y el estado del motor se puede serializar.
"""
import asyncio
import contextlib
import io
import unittest
import uuid

# pydantic-settings importa python-dotenv: se carga ANTES de que tests/sim reemplace
# dotenv por su doble (que garantiza que el .env nunca se lea).
import backend.app.core.config  # noqa: E402,F401
from tests.backend.apoyo import ajustes_prueba, almacenes

_INSTANCIA = None


def instancia_simulada():
    global _INSTANCIA
    if _INSTANCIA is None:
        from tests.sim import fakes, harness

        fakes.CONFIG["ollama_up"] = True
        fakes.CONFIG["powerbi_up"] = True
        fakes.install_stubs(harness.DEFAULT_SIM_ROOT)
        from backend.app.services.motor import construir_instancia_real

        with contextlib.redirect_stdout(io.StringIO()):
            _INSTANCIA = construir_instancia_real(harness.DEFAULT_SIM_ROOT)
    return _INSTANCIA


class MotorSimuladoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.app.services.motor import PiscinaMotores, SerializadorEstado
        from backend.app.services.turnos import ProcesadorTurnos

        cls.instancia = instancia_simulada()
        cls.api, cls.almacen, _ = almacenes("memoria")
        cls.procesador = ProcesadorTurnos(cls.almacen, PiscinaMotores([cls.instancia]), SerializadorEstado("s"),
                                          ajustes_prueba(cache_habilitada=False), intervalo_tic_s=0.2)

    def conversacion(self):
        cid = uuid.uuid4().hex
        asyncio.run(self.api.crear_conversacion(cid, 600))
        return cid

    def turno(self, cid, mensaje="", opcion_id=None):
        tid = uuid.uuid4().hex
        turno = {"turno_id": tid, "conversacion_id": cid, "mensaje": mensaje, "opcion_id": opcion_id,
                 "diagnostico": True, "estado": "en_cola", "creado_ms": 0}
        asyncio.run(self.api.encolar_turno(turno, 10, 600))
        with contextlib.redirect_stdout(io.StringIO()):
            self.procesador.procesar(self.almacen.tomar_turno("w", 200))
        eventos = asyncio.run(self.api.leer_eventos(tid, "0", 0))
        respuestas = [d for _, n, d in eventos if n == "respuesta"]
        self.assertTrue(respuestas, eventos)
        return respuestas[0]

    def test_portero(self):
        respuesta = self.turno(self.conversacion(), "hola")
        self.assertEqual(respuesta["ruta"], "conversacion")

    def test_conversaciones_intercaladas_no_se_mezclan(self):
        a, b = self.conversacion(), self.conversacion()
        respuesta_a = self.turno(a, "¿Cuántas cirugías realizadas hubo en 2024?")
        self.assertEqual(respuesta_a["ruta"], "contrapregunta")
        ids_a = [o["id"] for o in respuesta_a["contrapregunta"]["opciones"]]
        respuesta_b = self.turno(b, "¿Qué muestra el tablero?")
        self.assertEqual(respuesta_b["ruta"], "contrapregunta")
        opciones_b = respuesta_b["contrapregunta"]["opciones"]
        self.assertNotEqual(ids_a, [o["id"] for o in opciones_b])
        # A responde su contrapregunta aunque B dejó otra pendiente en la misma instancia.
        final_a = self.turno(a, "", opcion_id="b_cx_realizadas")
        self.assertEqual((final_a["estado"], final_a["ruta"]), ("success", "datos"), final_a)
        lavanderia = next(o for o in opciones_b if "Lavanderia" in o["texto"])
        final_b = self.turno(b, "", opcion_id=lavanderia["id"])
        self.assertEqual(final_b["ruta"], "documentacion", final_b)
        self.assertIsNotNone(final_b["diagnostico"])


if __name__ == "__main__":
    unittest.main()

"""Proceso trabajador (backend/worker.py) y chequeos externos en segundo plano."""
import threading
import time
import unittest
from unittest import mock

from backend import worker
from backend.app.services.capacidades import ChequeoEnSegundoPlano
from tests.backend.apoyo import ajustes_prueba


class WorkerTest(unittest.TestCase):
    def test_sin_redis_no_arranca(self):
        with mock.patch.object(worker, "obtener_ajustes", return_value=ajustes_prueba()), \
                self.assertLogs("backend.worker", "ERROR"):
            self.assertEqual(worker.main(), 2)

    def test_con_redis_caido_no_arranca(self):
        ajustes = ajustes_prueba(redis_url="redis://nadie:6379/0")
        with mock.patch.object(worker, "obtener_ajustes", return_value=ajustes), \
                mock.patch.object(worker, "crear_almacenes", return_value=(None, None, "memoria")), \
                self.assertLogs("backend.worker", "ERROR"):
            self.assertEqual(worker.main(), 3)


class PuntoDeEntradaTest(unittest.TestCase):
    def test_ordenes(self):
        from backend import __main__ as entrada

        with mock.patch.object(entrada.worker, "main", return_value=0) as trabajador:
            self.assertEqual(entrada.main(["trabajador"]), 0)
        trabajador.assert_called_once()
        with mock.patch.object(entrada.uvicorn, "run") as correr, \
                mock.patch.object(entrada, "create_app", return_value="app") as crear:
            self.assertEqual(entrada.main(["api", "--port", "8123"]), 0)
            correr.assert_called_once_with("app", host="127.0.0.1", port=8123)
            crear.assert_called_once()
            correr.reset_mock()
            entrada.main(["api", "--workers", "4"])
            self.assertEqual(correr.call_args.args[0], "backend.app.main:app")
            self.assertEqual(correr.call_args.kwargs["workers"], 4)


class ChequeoEnSegundoPlanoTest(unittest.TestCase):
    def test_nunca_bloquea_y_marca_timeout(self):
        soltar = threading.Event()

        def lento():
            soltar.wait(5)
            return {"status": "ready"}

        chequeo = ChequeoEnSegundoPlano(lento, intervalo_s=60, limite_s=0.05)
        inicio = time.monotonic()
        chequeo.refrescar()
        self.assertLess(time.monotonic() - inicio, 0.5)  # no espera al ping
        time.sleep(0.1)
        self.assertEqual(chequeo.ultimo(), {"status": "timeout"})
        soltar.set()
        limite = time.monotonic() + 5
        while chequeo.ultimo() != {"status": "ready"} and time.monotonic() < limite:
            time.sleep(0.01)
        self.assertEqual(chequeo.ultimo(), {"status": "ready"})

    def test_respeta_el_intervalo_y_los_errores(self):
        llamadas = []
        ahora = [0.0]

        def falla():
            llamadas.append(1)
            raise RuntimeError("caído")

        chequeo = ChequeoEnSegundoPlano(falla, intervalo_s=60, limite_s=1, reloj=lambda: ahora[0])
        with self.assertLogs("backend.app.services.capacidades", "WARNING"):
            chequeo.refrescar()
            limite = time.monotonic() + 5
            while chequeo.ultimo() is None and time.monotonic() < limite:
                time.sleep(0.01)
        self.assertEqual(chequeo.ultimo(), {"status": "error"})
        chequeo.refrescar()  # dentro del intervalo: no se repite
        ahora[0] = 61
        chequeo.refrescar()
        limite = time.monotonic() + 5
        while len(llamadas) < 2 and time.monotonic() < limite:
            time.sleep(0.01)
        self.assertEqual(len(llamadas), 2)


if __name__ == "__main__":
    unittest.main()

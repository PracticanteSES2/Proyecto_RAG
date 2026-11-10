"""
Pruebas del panel de calificación (src/feedback/panel.py) y su conexión con app.py.

Ejecutar:
  python -m unittest tests.feedback.test_panel
"""
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.feedback import lector

# Aviso inofensivo de Streamlit en modo de prueba.
logging.getLogger("streamlit").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[2]


_MAIN_ORIGINAL = sys.modules["__main__"]


def tearDownModule():
    # AppTest sustituye sys.modules["__main__"] por el guion temporal; eso rompe a
    # las pruebas que lanzan procesos con multiprocessing (spawn) en la misma ejecución.
    sys.modules["__main__"] = _MAIN_ORIGINAL


def _script_panel():
    from src.feedback.panel import mostrar_calificacion
    mensajes = [
        {"role": "assistant", "content": "Hola."},
        {"role": "user", "content": "¿Cuántas cirugías hubo?"},
        {"role": "assistant", "content": "Hubo 55 cirugías.",
         "snapshot": {"pregunta": "¿Cuántas cirugías hubo?", "via": "texto", "estado": "success",
                      "ruta": "powerbi", "respuesta": "Hubo 55 cirugías.", "opciones_contrapregunta": []}},
    ]
    mostrar_calificacion(2, mensajes)
    mostrar_calificacion(0, mensajes)


class PruebasPanel(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        anterior = os.environ.get("FEEDBACK_DIR")
        os.environ["FEEDBACK_DIR"] = self._dir.name
        self.addCleanup(lambda: os.environ.pop("FEEDBACK_DIR", None) if anterior is None
                        else os.environ.__setitem__("FEEDBACK_DIR", anterior))
        self.at = AppTest.from_function(_script_panel, default_timeout=60).run()
        self.assertFalse(self.at.exception, self.at.exception)

    def _registros(self):
        return lector.cargar_calificaciones()

    def _lineas(self):
        ruta = Path(self._dir.name) / "calificaciones.jsonl"
        return ruta.read_text(encoding="utf-8").splitlines() if ruta.exists() else []

    def _boton_guardar(self):
        return next(b for b in self.at.button if str(b.key).startswith("guardar_"))

    def test_mensaje_sin_snapshot_no_muestra_panel(self):
        # Solo el índice 2 tiene snapshot: un único widget de calificación.
        self.assertEqual(len(self.at.get("feedback")), 1)

    def test_buena_guarda_una_linea(self):
        self.at.get("feedback")[0].set_value(1).run()
        self.assertFalse(self.at.exception, self.at.exception)
        lineas = self._lineas()
        self.assertEqual(len(lineas), 1)
        registro = self._registros()[0]
        self.assertEqual(registro["calificacion"], "buena")
        self.assertEqual(registro["historial"], [
            {"rol": "assistant", "texto": "Hola."},
            {"rol": "user", "texto": "¿Cuántas cirugías hubo?"},
        ])
        self.assertTrue(any("Guardado" in str(e.value) for e in self.at.caption))

    def test_dos_reruns_con_buena_dejan_una_sola_linea(self):
        self.at.get("feedback")[0].set_value(1).run()
        self.at.run()
        self.at.run()
        self.assertEqual(len(self._lineas()), 1)

    def test_limpiar_el_pulgar_no_guarda(self):
        self.at.get("feedback")[0].set_value(None).run()
        self.assertEqual(self._lineas(), [])

    def test_mala_sin_comentario_no_guarda_y_avisa(self):
        self.at.get("feedback")[0].set_value(0).run()
        self.assertEqual(len(self.at.text_area), 1)
        self.assertEqual(self._lineas(), [])
        self._boton_guardar().click().run()
        self.assertFalse(self.at.exception, self.at.exception)
        self.assertEqual(self._lineas(), [])
        self.assertTrue(len(self.at.warning) >= 1)

    def test_mala_con_comentario_guarda_esperado(self):
        self.at.get("feedback")[0].set_value(0).run()
        self.at.text_area[0].set_value("Esperaba la cifra por especialidad").run()
        self.assertEqual(self._lineas(), [])
        self._boton_guardar().click().run()
        self.assertFalse(self.at.exception, self.at.exception)
        registro = self._registros()[0]
        self.assertEqual(registro["calificacion"], "mala")
        self.assertEqual(registro["esperado"], "Esperaba la cifra por especialidad")
        # Un rerun posterior no duplica la línea.
        self.at.run()
        self.assertEqual(len(self._lineas()), 1)

    def test_error_al_guardar_se_avisa_y_no_rompe(self):
        os.environ["FEEDBACK_DIR"] = str(Path(self._dir.name) / "archivo.txt" / "x")
        (Path(self._dir.name) / "archivo.txt").write_text("no es carpeta")
        self.at.get("feedback")[0].set_value(1).run()
        self.assertFalse(self.at.exception, self.at.exception)
        self.assertTrue(len(self.at.warning) >= 1)


class PruebasAppReal(unittest.TestCase):
    def test_app_panel_solo_con_modo_diagnostico(self):
        with tempfile.TemporaryDirectory() as carpeta:
            anterior = os.environ.get("FEEDBACK_DIR")
            os.environ["FEEDBACK_DIR"] = carpeta
            try:
                app = AppTest.from_file(str(ROOT / "tests" / "realistic" / "run_app.py"), default_timeout=300)
                app.run()
                self.assertFalse(app.exception, app.exception)
                app.chat_input[0].set_value("¿Qué muestra el tablero de lavandería?").run()
                self.assertFalse(app.exception, app.exception)
                self.assertEqual(len(app.get("feedback")), 0, "sin modo diagnóstico no hay panel")

                app.checkbox[0].check().run()
                self.assertFalse(app.exception, app.exception)
                # El mensaje ya respondido (con snapshot) ya muestra el panel al reejecutar.
                self.assertEqual(len(app.get("feedback")), 1)
                app.chat_input[0].set_value("¿Qué muestra el tablero de lavandería?").run()
                self.assertFalse(app.exception, app.exception)
                self.assertEqual(len(app.get("feedback")), 2)
                app.get("feedback")[1].set_value(1).run()
                self.assertFalse(app.exception, app.exception)
                self.assertEqual(len(lector.cargar_calificaciones()), 1)
            finally:
                if anterior is None:
                    os.environ.pop("FEEDBACK_DIR", None)
                else:
                    os.environ["FEEDBACK_DIR"] = anterior


if __name__ == "__main__":
    unittest.main()

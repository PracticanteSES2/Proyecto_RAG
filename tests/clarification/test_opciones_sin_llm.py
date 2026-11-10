"""
Descripción de opciones con menos llamadas a MedGemma (specs/010-rendimiento-llm):

  * una opción ya descrita (mismo indicador, misma expresión) sale de la caché
    del motor: la pregunta del usuario no entra en el prompt, así que la
    descripción no depende de ella;
  * una opción cuyo catálogo ya trae una descripción suficiente y distinta de
    las demás no se manda al LLM (la UI usa la del catálogo).

    .venv\\Scripts\\python.exe -X utf8 -m unittest tests.clarification.test_opciones_sin_llm
"""
import os
import sys
import threading
import types
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "dotenv" not in sys.modules:
    _dotenv = types.ModuleType("dotenv")
    _dotenv.load_dotenv = lambda *a, **k: False
    _dotenv.find_dotenv = lambda *a, **k: ""
    _dotenv.__sim_fake__ = True
    sys.modules["dotenv"] = _dotenv

from src.chatbot import cache_llm  # noqa: E402
from src.chatbot.option_describer import OptionDescriber  # noqa: E402


class _Proveedor:
    model = "medgemma-prueba"
    enforces_timeout = True

    def __init__(self, answers=None):
        self.calls = 0
        self.answers = answers or {}
        self.lock = threading.Lock()

    def chat(self, messages, **kwargs):
        with self.lock:
            self.calls += 1
        prompt = messages[-1]["content"]
        for key, answer in self.answers.items():
            if key in prompt:
                return {"status": "success", "answer": answer, "model": self.model, "done_reason": "stop"}
        return {"status": "success", "answer": "Cuenta los registros de la tabla.", "model": self.model}


CAMAS = {"id": "m1", "label": "CAMAS", "measure": "CAMAS", "table": "CAMAS DISPONIBLES",
         "dax_expression": "DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO])"}
CIRUGIAS = {"id": "m2", "label": "CIRUGÍAS PROGRAMADAS", "measure": "CIRUGÍAS PROGRAMADAS",
            "table": "PROGRAMACION", "dax_expression": "COUNTROWS(PROGRAMACION)"}
ANSWERS = {"CAMAS DISPONIBLES": "Cuenta las camas distintas registradas.",
           "PROGRAMACION": "Cuenta las cirugías agendadas en la programación quirúrgica."}


class _Base(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ("LLM_CACHE", "OPTION_DESCRIBER_CATALOGO")}
        os.environ.pop("LLM_CACHE", None)
        os.environ.pop("OPTION_DESCRIBER_CATALOGO", None)
        cache_llm.configurar_almacen(cache_llm.AlmacenMemoria())

    def tearDown(self):
        cache_llm.configurar_almacen(None)
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class OpcionesEnCacheTests(_Base):
    def test_segunda_contrapregunta_con_las_mismas_opciones_no_llama(self):
        provider = _Proveedor(ANSWERS)
        describer = OptionDescriber(provider)
        first = describer.describe("cuantas camas", [CAMAS, CIRUGIAS])
        second = describer.describe("y cirugias?", [CIRUGIAS, CAMAS])
        self.assertEqual(provider.calls, 2)
        self.assertEqual(first["descriptions"], second["descriptions"])
        self.assertEqual(second["status"], "success")
        self.assertEqual(second["descriptions"]["m1"], "Cuenta las camas distintas registradas.")

    def test_descripcion_rechazada_no_se_guarda(self):
        # «personal» no está en el indicador de camas: se descarta y no se cachea.
        provider = _Proveedor({"CAMAS DISPONIBLES": "Mide la ocupación del personal asistencial."})
        describer = OptionDescriber(provider)
        describer.describe("camas", [CAMAS])
        result = describer.describe("camas", [CAMAS])
        self.assertEqual(provider.calls, 2)
        self.assertIn("m1", result["rejected"])

    def test_sin_cache_llama_siempre(self):
        os.environ["LLM_CACHE"] = "off"
        provider = _Proveedor(ANSWERS)
        describer = OptionDescriber(provider)
        describer.describe("camas", [CAMAS])
        describer.describe("camas", [CAMAS])
        self.assertEqual(provider.calls, 2)


class CatalogoSuficienteTests(_Base):
    def test_opcion_con_descripcion_de_catalogo_suficiente_no_va_al_llm(self):
        documented = dict(CAMAS, description="Número de camas habilitadas en el hospital según el censo diario.")
        provider = _Proveedor(ANSWERS)
        result = OptionDescriber(provider).describe("camas", [documented, CIRUGIAS])
        self.assertEqual(provider.calls, 1)
        self.assertNotIn("m1", result["descriptions"])  # la UI usa la del catálogo
        self.assertEqual(result["catalog"], ["m1"])
        self.assertIn("m2", result["descriptions"])

    def test_todas_suficientes_no_hay_llamadas(self):
        a = dict(CAMAS, description="Número de camas habilitadas en el hospital según el censo diario.")
        b = dict(CIRUGIAS, description="Cirugías agendadas en la programación quirúrgica del mes en curso.")
        provider = _Proveedor(ANSWERS)
        result = OptionDescriber(provider).describe("x", [a, b])
        self.assertEqual(provider.calls, 0)
        self.assertEqual(result["status"], "catalog")
        self.assertEqual(result["descriptions"], {})

    def test_descripciones_cortas_o_repetidas_si_van_al_llm(self):
        corta = dict(CAMAS, description="Camas")
        igual_1 = dict(CIRUGIAS, description="Total de registros del indicador para el periodo seleccionado.")
        igual_2 = dict(CAMAS, id="m3", description="Total de registros del indicador para el periodo seleccionado.")
        provider = _Proveedor(ANSWERS)
        result = OptionDescriber(provider).describe("x", [corta, igual_1])
        self.assertEqual(provider.calls, 1)  # solo la corta
        self.assertEqual(result["catalog"], ["m2"])
        provider = _Proveedor(ANSWERS)
        OptionDescriber(provider).describe("x", [igual_1, igual_2])
        self.assertEqual(provider.calls, 2)

    def test_se_puede_apagar(self):
        os.environ["OPTION_DESCRIBER_CATALOGO"] = "off"
        documented = dict(CAMAS, description="Número de camas habilitadas en el hospital según el censo diario.")
        provider = _Proveedor(ANSWERS)
        OptionDescriber(provider).describe("camas", [documented])
        self.assertEqual(provider.calls, 1)


if __name__ == "__main__":
    unittest.main()

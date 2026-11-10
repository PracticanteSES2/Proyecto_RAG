"""Reglas FastAPI del perfil backend sobre mini-repos sintéticos.

  .venv\\Scripts\\python.exe -X utf8 -m unittest tests.doctor.test_fastapi -v
"""
import sys
import unittest

sys.dont_write_bytecode = True

from tests.doctor._mini_repo import diagnosticar, reglas

ROUTER_BIEN = '''
from fastapi import APIRouter
from backend.app.schemas.chat import Pregunta, Respuesta
from backend.app.services.chat import responder

router = APIRouter()


@router.post("/chat", response_model=Respuesta)
async def chat(pregunta: Pregunta) -> Respuesta:
    return await responder(pregunta)
'''

SETTINGS = '''
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
'''


def _fastapi(archivos):
    return diagnosticar(archivos)


class FastApiTests(unittest.TestCase):
    def test_router_bien_hecho_no_tiene_hallazgos(self):
        inf = _fastapi({
            "backend/app/api/v1/chat.py": ROUTER_BIEN,
            "backend/app/core/config.py": SETTINGS,
        })
        self.assertEqual([h for h in inf.hallazgos if h.categoria == "fastapi"], [])

    def test_router_fuera_de_api_v1(self):
        inf = _fastapi({"backend/app/rutas.py": ROUTER_BIEN})
        self.assertIn(("router_fuera_de_api", "backend/app/rutas.py"), reglas(inf))

    def test_sin_response_model_y_dict_suelto(self):
        codigo = '''
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/x")
        def crear(datos: dict):
            return {"ok": True}
        '''
        inf = _fastapi({"backend/app/api/v1/x.py": codigo})
        r = reglas(inf)
        self.assertIn(("sin_response_model", "backend/app/api/v1/x.py"), r)
        self.assertIn(("dict_suelto", "backend/app/api/v1/x.py"), r)

    def test_logica_en_router(self):
        ramas = "\n".join(f"    if n == {i}:\n        total += {i}" for i in range(8))
        codigo = (
            "from fastapi import APIRouter\nfrom backend.app.schemas.x import R\nrouter = APIRouter()\n\n"
            "@router.get('/x', response_model=R)\ndef x(n: int):\n    total = 0\n" + ramas + "\n    return R(total=total)\n"
        )
        inf = _fastapi({"backend/app/api/v1/x.py": codigo})
        self.assertIn(("logica_en_router", "backend/app/api/v1/x.py"), reglas(inf))

    def test_router_importa_el_motor(self):
        codigo = ROUTER_BIEN.replace("from backend.app.services.chat import responder",
                                     "from src.chatbot.query_engine import QueryEngine")
        inf = _fastapi({"backend/app/api/v1/chat.py": codigo, "src/a/x.py": ""})
        self.assertIn(("router_importa_motor", "backend/app/api/v1/chat.py"), reglas(inf))

    def test_bloqueante_en_async(self):
        codigo = '''
        import time
        import requests

        async def servicio():
            time.sleep(1)
            return requests.get("http://x")

        def sincrono():
            time.sleep(1)
        '''
        inf = _fastapi({"backend/app/services/s.py": codigo})
        h = [x for x in inf.hallazgos if x.regla == "bloqueante_en_async"]
        self.assertEqual(sorted(x.linea for x in h), [6, 7])
        self.assertTrue(all(x.severidad == "alta" for x in h))

    def test_getenv_disperso_y_settings(self):
        inf = _fastapi({
            "backend/app/services/s.py": "import os\nURL = os.getenv('REDIS_URL')\n",
            "backend/app/core/config.py": "import os\nURL = os.getenv('X')\n",
        })
        r = reglas(inf)
        self.assertIn(("getenv_disperso", "backend/app/services/s.py"), r)
        self.assertNotIn(("getenv_disperso", "backend/app/core/config.py"), r)
        self.assertIn(("settings_sin_pydantic", "backend/app/core/config.py"), r)

    def test_src_no_importa_backend(self):
        inf = _fastapi({"src/a/x.py": "from backend.app.core.config import Settings\n",
                        "backend/app/core/config.py": SETTINGS})
        self.assertIn(("importacion_prohibida", "src/a/x.py"), reglas(inf))


class MuertoReexportacionTests(unittest.TestCase):
    def test_reexportacion_no_es_import_sin_uso(self):
        inf = diagnosticar({
            "app.py": "from src.a.fachada import util\nutil()\nimport src.a.otra\n",
            "src/a/base.py": "def util():\n    return 1\n",
            "src/a/fachada.py": "from src.a.base import util\n",
            "src/a/otra.py": "from os import path  # noqa: F401\n",
        })
        self.assertFalse([h for h in inf.hallazgos if h.regla == "import_sin_uso"])


if __name__ == "__main__":
    unittest.main()

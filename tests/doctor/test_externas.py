"""Herramientas externas opcionales del perfil backend (ruff, vulture): sin instalarlas.

  .venv\\Scripts\\python.exe -X utf8 -m unittest tests.doctor.test_externas -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True

from tools.doctor import externas
from tools.doctor.config import config_de


class ExternasTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        (self.raiz / "src").mkdir()
        self.config = config_de()

    def tearDown(self):
        self._tmp.cleanup()

    def test_si_faltan_se_omiten_sin_error(self):
        with mock.patch.object(externas, "_comando", return_value=None):
            datos, omitidas = externas.correr(self.raiz, self.config)
        self.assertEqual(datos, [])
        self.assertEqual(len(omitidas), 2)
        self.assertIn("requirements-dev.txt", omitidas[0])

    def test_lee_json_de_ruff_y_texto_de_vulture(self):
        ruff = json.dumps([{"filename": str(self.raiz / "src" / "a.py"), "location": {"row": 3},
                            "code": "F401", "message": "`os` imported but unused"}]).encode()
        vulture = f"{self.raiz / 'src' / 'a.py'}:7: unused function 'f' (60% confidence)\n".encode()

        def falso(cmd, **_):
            salida = ruff if "check" in cmd else vulture
            return subprocess.CompletedProcess(cmd, 0, salida, b"")

        with mock.patch.object(externas, "_comando", return_value=["herramienta"]), \
                mock.patch.object(externas.subprocess, "run", side_effect=falso):
            datos, omitidas = externas.correr(self.raiz, self.config)
        self.assertEqual(omitidas, [])
        self.assertEqual([(d.herramienta, d.archivo, d.linea, d.codigo) for d in datos],
                         [("ruff", "src/a.py", 3, "F401"), ("vulture", "src/a.py", 7, "muerto")])


if __name__ == "__main__":
    unittest.main()

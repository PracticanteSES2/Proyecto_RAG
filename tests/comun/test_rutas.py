"""Rutas canónicas (src/comun/rutas.py): raíz del proyecto y carpetas efímeras de var/.

    python -X utf8 -m unittest tests.comun.test_rutas
"""
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from src.comun import rutas

RAIZ = Path(__file__).resolve().parents[2]


class TestRutas(unittest.TestCase):
    def test_raiz_del_proyecto(self):
        self.assertEqual(rutas.RAIZ_PROYECTO, RAIZ)
        self.assertTrue((rutas.RAIZ_PROYECTO / "app.py").exists())
        self.assertEqual(rutas.DATOS, RAIZ / "data")

    def test_var_por_defecto_en_la_raiz(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROYECTO_VAR_DIR", None)
            self.assertEqual(rutas.raiz_var(), RAIZ / "var")
            self.assertEqual(rutas.ruta_salida("eval", "x"), RAIZ / "var" / "out" / "eval" / "x")
            self.assertEqual(rutas.ruta_log("regresion.log"), RAIZ / "var" / "logs" / "regresion.log")
            self.assertEqual(rutas.ruta_tmp("qdrant"), RAIZ / "var" / "tmp" / "qdrant")

    def test_var_sobreescribible_por_entorno(self):
        with mock.patch.dict(os.environ, {"PROYECTO_VAR_DIR": str(RAIZ / "otra")}):
            self.assertEqual(rutas.ruta_salida("real"), RAIZ / "otra" / "out" / "real")

    def test_no_crea_carpetas(self):
        with mock.patch.dict(os.environ, {"PROYECTO_VAR_DIR": str(RAIZ / "var" / "no_existe_nunca")}):
            ruta = rutas.ruta_salida("algo")
        self.assertFalse(ruta.exists())

    def test_partes_absolutas_o_con_puntos_no_escapan_de_var(self):
        for mala in ("/etc", "..", "a/../../b", "C:\\x"):
            with self.assertRaises(ValueError, msg=mala):
                rutas.ruta_salida(mala)

    def test_var_esta_ignorada_por_git(self):
        for ruta in ("var/out/eval/informe.md", "var/logs/app.log", "var/tmp/x"):
            salida = subprocess.run(["git", "-C", str(RAIZ), "check-ignore", "-q", ruta])
            self.assertEqual(salida.returncode, 0, ruta)


if __name__ == "__main__":
    unittest.main()

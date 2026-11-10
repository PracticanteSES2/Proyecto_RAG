"""CLI y trinquete del doctor sobre un mini-repo sintético.

  .venv\\Scripts\\python.exe -X utf8 -m unittest tests.doctor.test_cli -v
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

from tests.doctor._mini_repo import BASE, MiniRepo, escribir
from tools.doctor import cli

LIMPIO = {
    "app.py": "from src.a.x import f\nf()\n",
    "src/a/x.py": "def f():\n    return 1\n",
    "tests/test_x.py": "from src.a.x import f\n\n\ndef test_f():\n    assert f() == 1\n",
}


def _toml(config: dict) -> str:
    """Serializa la configuración BASE de las pruebas (solo lo que usa)."""
    est = config["estructura"]
    lineas = [
        "[estructura]",
        "raiz_permitida = " + json.dumps(est["raiz_permitida"]),
        "[estructura.subcarpetas]",
        *(f"{k} = {json.dumps(v)}" for k, v in est["subcarpetas"].items()),
    ]
    for capa in config["capas"]["orden"]:
        lineas += ["[[capas.orden]]", f'nombre = "{capa["nombre"]}"', "modulos = " + json.dumps(capa["modulos"])]
    lineas += ["[legado]", 'rutas = ["app.py"]']
    return "\n".join(lineas) + "\n"


class CliTests(unittest.TestCase):
    def setUp(self):
        self._repo = MiniRepo(LIMPIO)
        self.raiz = self._repo.__enter__()
        self._tmp = tempfile.TemporaryDirectory(prefix="doctor_cfg_")
        aux = Path(self._tmp.name)
        self.config = aux / "reglas.toml"
        self.config.write_text(_toml(BASE), encoding="utf-8")
        self.base = aux / "linea_base.json"

    def tearDown(self):
        self._repo.__exit__(None, None, None)
        self._tmp.cleanup()

    def correr(self, *args):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
            codigo = cli.main([
                "--raiz", str(self.raiz), "--config", str(self.config),
                "--linea-base", str(self.base), "--sin-externas", *args,
            ])
        return codigo, salida.getvalue()

    def test_informe_de_consola(self):
        escribir(self.raiz, {"src/a/y.py": "def g():\n    print(1)\n"})
        codigo, texto = self.correr()
        self.assertEqual(codigo, 0)
        self.assertIn("Puntaje global", texto)
        self.assertIn("Higiene", texto)
        self.assertIn("src/a/y.py:2", texto)

    def test_json(self):
        codigo, texto = self.correr("--json")
        self.assertEqual(codigo, 0)
        datos = json.loads(texto)
        self.assertEqual(datos["puntaje_global"], 100.0)
        backend = datos["perfiles"]["backend"]
        self.assertIn("estructura", backend["categorias"])
        self.assertEqual(backend["hallazgos"], [])
        self.assertTrue(datos["perfiles"]["frontend"]["omitido"])

    def test_markdown(self):
        destino = Path(self._tmp.name) / "informe.md"
        codigo, _ = self.correr("--md", str(destino))
        self.assertEqual(codigo, 0)
        self.assertIn("# Doctor", destino.read_text(encoding="utf-8"))

    def test_verificar_sin_linea_base_es_error_de_uso(self):
        codigo, texto = self.correr("--verificar")
        self.assertEqual(codigo, 2)
        self.assertIn("--actualizar-linea-base", texto)

    def test_trinquete_completo(self):
        self.assertEqual(self.correr("--actualizar-linea-base")[0], 0)
        self.assertTrue(self.base.exists())
        self.assertEqual(self.correr("--verificar")[0], 0)

        # Hallazgo alto nuevo → falla y lo nombra.
        escribir(self.raiz, {"src/a/x.py": "def f():\n    try:\n        return 1\n    except:\n        pass\n"})
        codigo, texto = self.correr("--verificar")
        self.assertEqual(codigo, 1)
        self.assertIn("except_desnudo", texto)

        # Se arregla → vuelve a pasar.
        escribir(self.raiz, {"src/a/x.py": "def f():\n    return 1\n"})
        self.assertEqual(self.correr("--verificar")[0], 0)

    def test_baja_de_categoria_sin_alta_nueva_tambien_falla(self):
        self.correr("--actualizar-linea-base")
        escribir(self.raiz, {"src/a/x.py": "def f():\n    print('x')\n    return 1\n"})
        codigo, texto = self.correr("--verificar")
        self.assertEqual(codigo, 1)
        self.assertIn("higiene", texto.lower())

    def test_hallazgos_viejos_se_toleran_y_mejora_sube_el_liston(self):
        escribir(self.raiz, {"src/a/run.log": "x", "src/a/y.py": "def g():\n    print(1)\n"})
        self.correr("--actualizar-linea-base")
        self.assertEqual(self.correr("--verificar")[0], 0)  # lo viejo se tolera
        antes = json.loads(self.base.read_text(encoding="utf-8"))["puntaje_global"]

        (self.raiz / "src/a/run.log").unlink()
        codigo, texto = self.correr("--verificar")
        self.assertEqual(codigo, 0)
        self.assertIn("--actualizar-linea-base", texto)  # sugiere subir el listón
        self.correr("--actualizar-linea-base")
        despues = json.loads(self.base.read_text(encoding="utf-8"))["puntaje_global"]
        self.assertGreater(despues, antes)

    def test_legado_que_crece_falla(self):
        self.correr("--actualizar-linea-base")
        escribir(self.raiz, {"app.py": LIMPIO["app.py"] + "def nueva_pantalla():\n    return 1\n\nnueva_pantalla()\n"})
        codigo, texto = self.correr("--verificar")
        self.assertEqual(codigo, 1)
        self.assertIn("legado_crece", texto)

    def test_actualizar_no_baja_el_liston_sin_forzar(self):
        self.correr("--actualizar-linea-base")
        escribir(self.raiz, {"src/a/run.log": "x"})
        codigo, texto = self.correr("--actualizar-linea-base")
        self.assertEqual(codigo, 1)
        self.assertIn("--forzar", texto)
        self.assertEqual(self.correr("--actualizar-linea-base", "--forzar")[0], 0)
        self.assertEqual(self.correr("--verificar")[0], 0)

    def test_perfiles_separados_en_la_linea_base(self):
        escribir(self.raiz, {"frontend/app/page.tsx": "export default function P() {\n  return null;\n}\n"})
        self.assertEqual(self.correr("--actualizar-linea-base")[0], 0)
        base = json.loads(self.base.read_text(encoding="utf-8"))
        self.assertIn("backend", base["perfiles"])
        self.assertIn("frontend", base["perfiles"])
        self.assertNotIn("react", base["perfiles"]["frontend"]["categorias"])  # omitida (--sin-externas)

        # Un `any` nuevo en el frontend rompe solo el perfil frontend.
        escribir(self.raiz, {"frontend/lib/x.ts": "export const a: any = 1;\n"})
        codigo, texto = self.correr("frontend", "--verificar")
        self.assertEqual(codigo, 1)
        self.assertIn("frontend/tipos", texto)
        self.assertEqual(self.correr("backend", "--verificar")[0], 0)

    def test_estricto_falla_si_algo_no_se_pudo_verificar(self):
        escribir(self.raiz, {"frontend/app/page.tsx": "export default function P() {\n  return null;\n}\n"})
        self.correr("--actualizar-linea-base")
        (self.raiz / "frontend/app/page.tsx").unlink()
        (self.raiz / "frontend/app").rmdir()
        (self.raiz / "frontend").rmdir()
        codigo, texto = self.correr("--verificar")
        self.assertEqual(codigo, 0)
        self.assertIn("sin verificar", texto)
        self.assertEqual(self.correr("--verificar", "--estricto")[0], 3)


if __name__ == "__main__":
    unittest.main()

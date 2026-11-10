"""Reglas del doctor sobre mini-repos sintéticos (sin git, en temporales).

  .venv\\Scripts\\python.exe -X utf8 -m unittest discover -s tests/doctor -t .
"""
import sys
import unittest

sys.dont_write_bytecode = True

import shutil
import subprocess

from tests.doctor._mini_repo import BASE, MiniRepo, diagnosticar, fusionar, reglas
from tools.doctor.config import config_de
from tools.doctor.motor import analizar

# Cadenas armadas por partes para que el propio doctor no las marque en este archivo.
MOJIBAKE = "Informaci\u00c3\u00b3n"
RUTA_USUARIO = "C:" + "\\\\Users\\\\pepe\\\\proyecto"
CLAVE = "sk_live_" + "a1b2c3d4e5f6g7h8i9"

FUNCION_8 = '''
def {nombre}(valores):
    total = 0
    for valor in valores:
        if valor > 0:
            total += valor
        else:
            total -= 1
    return total
'''


class EstructuraTests(unittest.TestCase):
    def test_raiz_no_permitida(self):
        inf = diagnosticar({"app.py": "", "notas_sueltas.txt": "x", "src/a/m.py": ""})
        r = reglas(inf)
        self.assertIn(("raiz_no_permitida", "notas_sueltas.txt"), r)
        self.assertNotIn(("raiz_no_permitida", "app.py"), r)
        self.assertNotIn(("raiz_no_permitida", "src"), r)

    def test_archivo_temporal_y_severidad_alta(self):
        inf = diagnosticar({"src/a/salida.log": "x", "tools/copia.zip": b"PK\x03\x04", "src/a/m.py": ""})
        r = reglas(inf)
        self.assertIn(("archivo_temporal", "src/a/salida.log"), r)
        self.assertIn(("archivo_temporal", "tools/copia.zip"), r)
        alta = [h for h in inf.hallazgos if h.regla == "archivo_temporal"]
        self.assertTrue(all(h.severidad == "alta" for h in alta))

    def test_exclusiones_no_se_analizan(self):
        inf = diagnosticar({
            "data/x.log": "x",
            "tests/sim/fixtures/y.log": "x",
            ".venv/lib/z.py": "print(1)",
        })
        archivos = {h.archivo for h in inf.hallazgos}
        self.assertFalse(any(a.startswith(("data/", "tests/sim/fixtures", ".venv")) for a in archivos), archivos)

    def test_carpeta_sin_dueno(self):
        inf = diagnosticar({
            "tools/manual/a.py": "", "tools/raro/b.py": "",
            "src/a/x.py": "", "src/huerfana/y.py": "",
        })
        r = reglas(inf)
        self.assertIn(("carpeta_sin_dueno", "tools/raro"), r)
        self.assertIn(("carpeta_sin_dueno", "src/huerfana"), r)
        self.assertNotIn(("carpeta_sin_dueno", "tools/manual"), r)
        self.assertNotIn(("carpeta_sin_dueno", "src/a"), r)

    def test_modulo_suelto_en_src(self):
        self.assertIn(("modulo_suelto_src", "src/suelto.py"), reglas(diagnosticar({"src/suelto.py": "X = 1\n"})))


class TamanoTests(unittest.TestCase):
    def test_archivo_grande_media_y_alta(self):
        cuerpo = "".join(f"X{i} = {i}\n" for i in range(20))
        inf = diagnosticar({"src/a/m.py": cuerpo}, tamano={"archivo_media": 10, "archivo_alta": 100})
        h = [h for h in inf.hallazgos if h.regla == "archivo_grande"]
        self.assertEqual([x.severidad for x in h], ["media"])
        inf = diagnosticar({"src/a/m.py": cuerpo}, tamano={"archivo_media": 10, "archivo_alta": 15})
        self.assertEqual([x.severidad for x in inf.hallazgos if x.regla == "archivo_grande"], ["alta"])

    def test_funcion_larga_con_linea(self):
        codigo = "X = 1\n\n" + FUNCION_8.format(nombre="larga")
        inf = diagnosticar({"src/a/m.py": codigo}, tamano={"funcion_media": 5})
        h = [h for h in inf.hallazgos if h.regla == "funcion_larga"]
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0].linea, 4)
        self.assertIn("larga", h[0].mensaje)

    def test_complejidad(self):
        codigo = '''
        def enredada(x, y):
            if x and y:
                return 1
            for i in range(x):
                if i % 2 or y:
                    continue
            while y:
                y -= 1
            return 0

        def simple(x):
            return x
        '''
        inf = diagnosticar({"src/a/m.py": codigo}, tamano={"complejidad_media": 4})
        h = [h for h in inf.hallazgos if h.regla == "complejidad"]
        self.assertEqual([x.mensaje.split("`")[1] for x in h], ["enredada"])

    def test_tamano_no_aplica_a_pruebas(self):
        cuerpo = "".join(f"X{i} = {i}\n" for i in range(20))
        inf = diagnosticar({"tests/test_m.py": cuerpo}, tamano={"archivo_media": 10})
        self.assertNotIn(("archivo_grande", "tests/test_m.py"), reglas(inf))


class DuplicacionTests(unittest.TestCase):
    def test_funcion_identica_entre_modulos(self):
        inf = diagnosticar({
            "src/a/x.py": FUNCION_8.format(nombre="sumar"),
            "src/b/y.py": FUNCION_8.format(nombre="acumular"),
        })
        h = [h for h in inf.hallazgos if h.regla == "funcion_identica"]
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0].archivo, "src/b/y.py")
        self.assertIn("src/a/x.py", h[0].mensaje)

    def test_funcion_casi_identica(self):
        otra = FUNCION_8.format(nombre="acumular").replace("valores", "items").replace("valor", "it").replace("total", "acc")
        inf = diagnosticar({
            "src/a/x.py": FUNCION_8.format(nombre="sumar"),
            "src/b/y.py": otra,
        }, duplicacion={"min_lineas_casi": 6})
        self.assertIn(("funcion_casi_identica", "src/b/y.py"), reglas(inf))
        self.assertNotIn(("funcion_identica", "src/b/y.py"), reglas(inf))

    def test_funciones_cortas_no_cuentan(self):
        corta = "def f(x):\n    return x + 1\n"
        inf = diagnosticar({"src/a/x.py": corta, "src/b/y.py": corta})
        self.assertFalse([h for h in inf.hallazgos if h.categoria == "duplicacion"])

    def test_utilidad_repetida_quitar_tildes(self):
        a = '''
        import unicodedata
        def limpiar(t):
            return unicodedata.normalize("NFKD", t)
        '''
        b = a.replace("limpiar", "sin_tildes")
        inf = diagnosticar({"src/a/x.py": a, "src/b/y.py": b, "app.py": "from src.a.x import limpiar\nfrom src.b.y import sin_tildes\n"})
        r = reglas(inf)
        self.assertIn(("utilidad_repetida", "src/a/x.py"), r)
        self.assertIn(("utilidad_repetida", "src/b/y.py"), r)

    def test_utilidad_repetida_raiz_del_proyecto(self):
        mod = "from pathlib import Path\nRAIZ = Path(__file__).resolve().parents[2]\n"
        inf = diagnosticar({"src/a/x.py": mod, "src/b/y.py": mod})
        h = [h for h in inf.hallazgos if h.regla == "utilidad_repetida"]
        self.assertEqual({x.archivo for x in h}, {"src/a/x.py", "src/b/y.py"})
        self.assertIn("raíz del proyecto", h[0].mensaje)

    def test_una_sola_utilidad_no_es_repetida(self):
        mod = "from pathlib import Path\nRAIZ = Path(__file__).resolve().parents[2]\n"
        inf = diagnosticar({"src/a/x.py": mod})
        self.assertNotIn(("utilidad_repetida", "src/a/x.py"), reglas(inf))


class MuertoTests(unittest.TestCase):
    def test_modulo_sin_uso_y_solo_pruebas(self):
        inf = diagnosticar({
            "app.py": "from src.a import usado\nusado.f()\n",
            "src/a/usado.py": "def f():\n    return 1\n",
            "src/a/huerfano.py": "def g():\n    return 2\n",
            "src/a/probado.py": "def h():\n    return 3\n",
            "tests/test_probado.py": "from src.a.probado import h\n\ndef test_h():\n    assert h() == 3\n",
        })
        r = reglas(inf)
        self.assertIn(("modulo_sin_uso", "src/a/huerfano.py"), r)
        self.assertNotIn(("modulo_sin_uso", "src/a/usado.py"), r)
        self.assertIn(("modulo_solo_pruebas", "src/a/probado.py"), r)

    def test_simbolo_sin_uso(self):
        inf = diagnosticar({
            "app.py": "from src.a.m import usada\nusada()\n",
            "src/a/m.py": "def usada():\n    return 1\n\ndef nunca_llamada():\n    return 2\n",
        })
        h = [h for h in inf.hallazgos if h.regla == "simbolo_sin_uso"]
        self.assertEqual([x.mensaje.split("`")[1] for x in h], ["nunca_llamada"])
        self.assertEqual(h[0].linea, 4)

    def test_import_sin_uso(self):
        inf = diagnosticar({
            "app.py": "import src.a.m\nimport src.a.paquete\n",
            "src/a/m.py": "import os\nimport sys\nprint_ = sys.argv\n",
            "src/a/paquete/__init__.py": "from os import path\n",
        })
        h = [(h.archivo, h.mensaje.split("`")[1]) for h in inf.hallazgos if h.regla == "import_sin_uso"]
        self.assertEqual(h, [("src/a/m.py", "os")])


class CapasTests(unittest.TestCase):
    def test_src_no_importa_tools_ni_tests(self):
        inf = diagnosticar({"src/a/x.py": "from tools.manual import algo\n", "tools/manual/algo.py": ""})
        h = [h for h in inf.hallazgos if h.regla == "importacion_prohibida"]
        self.assertEqual([(x.archivo, x.linea, x.severidad) for x in h], [("src/a/x.py", 1, "alta")])

    def test_capa_invertida(self):
        inf = diagnosticar({
            "src/base/x.py": "\nfrom src.app.y import f\n",
            "src/app/y.py": "from src.base.x import g\ndef f():\n    pass\n",
        })
        h = [h for h in inf.hallazgos if h.regla == "capa_invertida"]
        self.assertEqual([(x.archivo, x.linea) for x in h], [("src/base/x.py", 2)])

    def test_ciclo_solo_con_imports_de_modulo(self):
        inf = diagnosticar({
            "src/a/x.py": "import src.a.y\n",
            "src/a/y.py": "import src.a.x\n",
            "src/b/p.py": "import src.b.q\n",
            "src/b/q.py": "def f():\n    import src.b.p\n",
        })
        h = [h for h in inf.hallazgos if h.regla == "ciclo"]
        self.assertEqual(len(h), 1)
        self.assertIn("src.a.x", h[0].mensaje)

    def test_importacion_rota(self):
        inf = diagnosticar({
            "app.py": "from src.a.x import existe, inexistente\nimport src.a.nada\n",
            "src/a/x.py": "def existe():\n    pass\n",
        })
        h = [h for h in inf.hallazgos if h.regla == "importacion_rota"]
        self.assertEqual(len(h), 2)
        self.assertTrue(all(x.severidad == "alta" for x in h))

    def test_import_protegido_por_try_no_es_roto(self):
        inf = diagnosticar({"app.py": "try:\n    import src.a.nada\nexcept ImportError:\n    pass\n", "src/a/x.py": ""})
        self.assertFalse([h for h in inf.hallazgos if h.regla == "importacion_rota"])


class PruebasTests(unittest.TestCase):
    def test_modulo_sin_pruebas(self):
        inf = diagnosticar({
            "src/a/x.py": "def f():\n    pass\n",
            "src/a/y.py": "def g():\n    pass\n",
            "tests/test_x.py": "from src.a.x import f\n\ndef test_f():\n    f()\n",
        })
        r = reglas(inf)
        self.assertIn(("modulo_sin_pruebas", "src/a/y.py"), r)
        self.assertNotIn(("modulo_sin_pruebas", "src/a/x.py"), r)

    def test_prueba_huerfana_y_patch_roto(self):
        inf = diagnosticar({
            "src/a/x.py": "def f():\n    pass\n",
            "tests/test_y.py": (
                "from unittest import mock\n"
                "from src.a.borrado import f\n\n"
                "def test_y():\n"
                "    with mock.patch(\"src.a.x.no_existe\"):\n"
                "        pass\n"
            ),
        })
        r = reglas(inf)
        self.assertIn(("prueba_huerfana", "tests/test_y.py"), r)
        self.assertIn(("patch_roto", "tests/test_y.py"), r)

    def test_archivo_de_prueba_sin_pruebas(self):
        inf = diagnosticar({"tests/test_vacio.py": "X = 1\n"})
        self.assertIn(("archivo_prueba_vacio", "tests/test_vacio.py"), reglas(inf))


class HigieneTests(unittest.TestCase):
    def test_print_solo_en_src_y_fuera_de_main(self):
        inf = diagnosticar({
            "src/a/x.py": "def f():\n    print('depurando')\n\nif __name__ == '__main__':\n    print('ok')\n",
            "tools/manual/s.py": "print('herramienta')\n",
        })
        h = [h for h in inf.hallazgos if h.regla == "print_depuracion"]
        self.assertEqual([(x.archivo, x.linea) for x in h], [("src/a/x.py", 2)])

    def test_excepts(self):
        codigo = '''
        def f():
            try:
                pass
            except:
                pass
            try:
                pass
            except Exception:
                pass
            try:
                pass
            except ValueError:
                return None
        '''
        inf = diagnosticar({"src/a/x.py": codigo})
        sev = sorted((h.regla, h.severidad) for h in inf.hallazgos if h.regla.startswith("except"))
        self.assertEqual(sev, [("except_desnudo", "alta"), ("except_silencioso", "media")])

    def test_breakpoint(self):
        inf = diagnosticar({"src/a/x.py": "def f():\n    breakpoint()\n"})
        self.assertIn(("punto_de_ruptura", "src/a/x.py"), reglas(inf))

    def test_todo_marcador_y_no_palabra(self):
        inf = diagnosticar({"src/a/x.py": "X = 1  # TO" + "DO: arreglar\nY = 2  # si TODO el periodo cae\n"})
        h = [h for h in inf.hallazgos if h.regla == "todo"]
        self.assertEqual([x.linea for x in h], [1])

    def test_secretos(self):
        inf = diagnosticar({
            "src/a/x.py": f'API_KEY = "{CLAVE}"\n',
            "src/a/y.py": 'import os\napi_key = os.getenv("X")\ntoken = "fake-token-1234567890"\n',
        })
        r = reglas(inf)
        self.assertIn(("secreto", "src/a/x.py"), r)
        self.assertNotIn(("secreto", "src/a/y.py"), r)

    def test_ruta_de_usuario(self):
        inf = diagnosticar({"src/a/x.py": f'RUTA = r"{RUTA_USUARIO}"\n'})
        self.assertIn(("ruta_usuario", "src/a/x.py"), reglas(inf))

    def test_bom_salvo_ps1(self):
        inf = diagnosticar({"src/a/x.py": "\ufeffX = 1\n", "tools/s.ps1": "\ufeffWrite-Host 1\n"})
        r = reglas(inf)
        self.assertIn(("bom", "src/a/x.py"), r)
        self.assertNotIn(("bom", "tools/s.ps1"), r)

    def test_mojibake(self):
        inf = diagnosticar({"docs/guia.md": f"# Guía\n\n{MOJIBAKE} del tablero\n", "docs/bien.md": "Información\n"})
        h = [h for h in inf.hallazgos if h.regla == "mojibake"]
        self.assertEqual([(x.archivo, x.linea) for x in h], [("docs/guia.md", 3)])

    def test_sintaxis_invalida_no_detiene(self):
        inf = diagnosticar({"src/a/x.py": "def (:\n", "src/a/y.py": "def f():\n    print(1)\n"})
        r = reglas(inf)
        self.assertIn(("sintaxis_invalida", "src/a/x.py"), r)
        self.assertIn(("print_depuracion", "src/a/y.py"), r)

    def test_sys_path_en_src(self):
        inf = diagnosticar({"src/a/x.py": "import sys\nsys.path.insert(0, '.')\n"})
        self.assertIn(("sys_path", "src/a/x.py"), reglas(inf))


class ExtensionesArquitecturaTests(unittest.TestCase):
    """Extensiones pedidas en docs/ARQUITECTURA.md §12."""

    PROHIBIDAS = {"prohibidas": [
        {"desde": "tools", "hacia": ["tests"], "excepto": ["tools.manual"]},
        {"desde": "src", "hacia": ["redis", "fastapi"]},
    ]}

    def test_excepto_en_importaciones_prohibidas(self):
        inf = diagnosticar({
            "tools/manual/sondeo.py": "from tests.real import banco\n",
            "tools/script.py": "from tests.real import banco\n",
            "tests/real/banco.py": "X = 1\n",
        }, capas=self.PROHIBIDAS)
        r = reglas(inf)
        self.assertIn(("importacion_prohibida", "tools/script.py"), r)
        self.assertNotIn(("importacion_prohibida", "tools/manual/sondeo.py"), r)

    def test_prohibido_importar_paquete_externo(self):
        inf = diagnosticar({"src/a/x.py": "import redis\n"}, capas=self.PROHIBIDAS)
        self.assertIn(("importacion_prohibida", "src/a/x.py"), reglas(inf))

    def test_nombres_prohibidos(self):
        inf = diagnosticar({"src/a/utils.py": "X = 1\n", "src/a/periodo.py": "X = 1\n", "tools/manual/test_final.py": ""},
                           higiene={"nombres_prohibidos": ["utils.py", "test_final.py"]})
        r = reglas(inf)
        self.assertIn(("nombre_prohibido", "src/a/utils.py"), r)
        self.assertIn(("nombre_prohibido", "tools/manual/test_final.py"), r)
        self.assertNotIn(("nombre_prohibido", "src/a/periodo.py"), r)

    def test_salidas_fuera_de_var_segun_gitignore(self):
        inf = diagnosticar({
            ".gitignore": "/var/\n/data\n/tools/carga/salidas/\n*.log\n",
            "tests/real/.gitignore": "out*/\n",
        })
        h = {(x.archivo, x.mensaje.split("`")[1]) for x in inf.hallazgos if x.regla == "salida_fuera_de_var"}
        self.assertEqual(h, {(".gitignore", "tools/carga/salidas"), ("tests/real/.gitignore", "tests/real/out*")})

    @unittest.skipUnless(shutil.which("git"), "requiere git")
    def test_carpetas_que_deben_estar_ignoradas(self):
        cfg = config_de(fusionar(BASE, {"estructura": {
            "carpetas_ignoradas": ["var", "data", "__pycache__"],
            "raiz_permitida": [*BASE["estructura"]["raiz_permitida"], "var", "data"],
        }}))
        archivos = {"src/a/x.py": "", "var/out/informe.txt": "x", "src/a/__pycache__/x.pyc": "x",
                    "tests/sim/data/catalogo.json": "{}"}  # «data» solo cuenta en la raíz
        with MiniRepo(archivos) as raiz:
            subprocess.run(["git", "init", "-q"], cwd=raiz, check=True)
            inf = analizar(raiz, cfg, externas=False)
            r = reglas(inf)
            self.assertIn(("no_ignorada", "var"), r)
            self.assertIn(("no_ignorada", "src/a/__pycache__"), r)
            self.assertNotIn(("no_ignorada", "tests/sim/data"), r)
            (raiz / ".gitignore").write_text("/var/\n__pycache__/\n", encoding="utf-8")
            r = reglas(analizar(raiz, cfg, externas=False))
            self.assertFalse([x for x in r if x[0] == "no_ignorada"])


class PuntajeTests(unittest.TestCase):
    def test_repo_limpio_saca_100(self):
        inf = diagnosticar({
            "app.py": "from src.a.x import f\nf()\n",
            "src/a/x.py": "def f():\n    return 1\n",
            "tests/test_x.py": "from src.a.x import f\n\n\ndef test_f():\n    assert f() == 1\n",
        })
        self.assertEqual(inf.hallazgos, [])
        self.assertEqual(inf.puntaje_global, 100.0)
        self.assertTrue(all(v == 100.0 for v in inf.puntajes.values()))

    def test_alta_pesa_mas_que_baja(self):
        base = {"app.py": "", "src/a/x.py": ""}
        alta = diagnosticar({**base, "src/a/run.log": "x"})
        baja = diagnosticar({**base, "src/a/y.py": "\ufeffX = 1\n"})
        self.assertLess(alta.puntajes["estructura"], 100)
        self.assertLess(baja.puntajes["higiene"], 100)
        self.assertLess(100 - baja.puntajes["higiene"], 100 - alta.puntajes["estructura"])

    def test_huella_no_depende_de_la_linea(self):
        a = diagnosticar({"src/a/x.py": "def f():\n    print(1)\n"})
        b = diagnosticar({"src/a/x.py": "\n\n\ndef f():\n    print(1)\n"})
        ha = [h.huella for h in a.hallazgos if h.regla == "print_depuracion"]
        hb = [h.huella for h in b.hallazgos if h.regla == "print_depuracion"]
        self.assertEqual(ha, hb)


if __name__ == "__main__":
    unittest.main()

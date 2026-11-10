"""Perfil frontend (Next.js + TypeScript): reglas propias y lectores de tsc/ESLint/react-doctor.

No necesita Node: las herramientas externas se prueban con salidas de ejemplo.

  .venv\\Scripts\\python.exe -X utf8 -m unittest tests.doctor.test_frontend -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True

from tests.doctor._mini_repo import BASE, MiniRepo
from tools.doctor import frontend
from tools.doctor.config import config_de

COMPONENTE = """\
import { obtenerResumen } from "@/lib/api/resumen";

export default async function Pagina() {
  const datos = await obtenerResumen();
  return <main style={{ color: "var(--texto)" }}>{datos.titulo}</main>;
}
"""


def analizar(archivos, externas=False, **cambios):
    config = config_de({**BASE, **cambios})
    with MiniRepo(archivos) as raiz:
        return frontend.analizar(raiz, config, externas=externas)


def reglas(inf):
    return {(h.regla, h.archivo) for h in inf.hallazgos}


class ReglasPropiasTests(unittest.TestCase):
    def test_sin_frontend_se_omite_con_aviso(self):
        inf = analizar({"src/a/x.py": ""})
        self.assertTrue(inf.omitido)
        self.assertIn("frontend/", inf.avisos[0])
        self.assertIsNone(inf.puntaje)

    def test_componente_limpio(self):
        inf = analizar({
            "frontend/app/page.tsx": COMPONENTE,
            "frontend/lib/api/resumen.ts": "export async function obtenerResumen() {\n  const r = await fetch('/api/v1/resumen');\n  return r.json();\n}\n",
            "frontend/package.json": "{}",
        })
        self.assertEqual(inf.hallazgos, [])
        self.assertEqual(inf.puntaje, 100.0)
        # Sin externas: sus categorías se omiten y no cuentan.
        self.assertEqual(set(inf.omitidas), {"compilacion", "lint", "react"})
        self.assertNotIn("react", inf.puntajes)

    def test_any_ts_ignore_y_expect_error(self):
        codigo = "const a: any = 1;\nconst b = x as any;\n// @ts-ignore\nconst c = 1;\n// @ts-expect-error\nconst d = 2;\n// texto: any comentario\n"
        inf = analizar({"frontend/lib/util.ts": codigo})
        lineas = sorted((h.regla, h.linea) for h in inf.hallazgos if h.categoria == "tipos")
        self.assertEqual(lineas, [("any", 1), ("any", 2), ("ts_expect_error", 5), ("ts_ignore", 3)])

    def test_fetch_fuera_de_lib_api(self):
        inf = analizar({
            "frontend/components/Tabla.tsx": "export function T() {\n  fetch('/api/x');\n  return null;\n}\n",
            "frontend/lib/api/cliente.ts": "export const get = () => fetch('/api/x');\n",
        })
        r = reglas(inf)
        self.assertIn(("fetch_fuera_de_api", "frontend/components/Tabla.tsx"), r)
        self.assertNotIn(("fetch_fuera_de_api", "frontend/lib/api/cliente.ts"), r)

    def test_hex_fuera_de_tokens(self):
        inf = analizar({
            "frontend/components/Boton.tsx": "export const B = () => <button style={{ color: '#ff0000' }} />;\n",
            "frontend/styles/tokens.css": ":root { --primario: #0a6ebd; }\n",
            "frontend/app/globals.css": "body { background: #fff; }\n",
        })
        h = [(x.archivo, x.linea) for x in inf.hallazgos if x.regla == "hex_fuera_de_tokens"]
        self.assertEqual(h, [("frontend/components/Boton.tsx", 1)])

    def test_componente_grande(self):
        cuerpo = "export function G() {\n" + "  const x = 1;\n" * 30 + "  return null;\n}\n"
        inf = analizar({"frontend/components/G.tsx": cuerpo},
                       frontend={"componente_media": 20, "componente_alta": 100})
        self.assertIn(("componente_grande", "frontend/components/G.tsx"), reglas(inf))

    def test_higiene_frontend(self):
        codigo = "console.log('x');\nconsole.error('ok');\ndebugger;\n// TO" + "DO: algo\n// eslint-disable-next-line\n"
        inf = analizar({"frontend/lib/a.ts": codigo})
        self.assertEqual(sorted((h.regla, h.linea) for h in inf.hallazgos),
                         [("console_log", 1), ("debugger", 3), ("eslint_disable", 5), ("todo", 4)])

    def test_fuera_de_lugar_y_exclusiones(self):
        inf = analizar({
            "frontend/app/page.tsx": COMPONENTE,
            "frontend/utilidades_sueltas/x.ts": "export const a = 1;\n",
            "frontend/node_modules/lib/index.js": "console.log('x')\n",
            "frontend/.next/server/page.js": "debugger;\n",
        })
        r = reglas(inf)
        self.assertIn(("fuera_de_lugar", "frontend/utilidades_sueltas"), r)
        self.assertFalse(any("node_modules" in a or ".next" in a for _, a in r))

    def test_sin_node_omite_externas_con_motivo(self):
        with mock.patch("tools.doctor.frontend.shutil.which", return_value=None):
            inf = analizar({"frontend/app/page.tsx": COMPONENTE}, externas=True)
        self.assertEqual(set(inf.omitidas), {"compilacion", "lint", "react"})
        self.assertIn("Node.js", inf.omitidas["react"])
        self.assertTrue(any("Node.js" in a for a in inf.avisos))


class LectoresExternosTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        self.base = self.raiz / "frontend"
        self.base.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_tsc(self):
        salida = (
            "app/page.tsx(4,7): error TS2322: Type 'string' is not assignable to type 'number'.\n"
            "lib/api/x.ts(1,1): error TS2307: Cannot find module 'y'.\n"
            "Found 2 errors.\n"
        )
        h = frontend.parsear_tsc(salida, self.raiz, self.base)
        self.assertEqual([(x.archivo, x.linea, x.severidad) for x in h],
                         [("frontend/app/page.tsx", 4, "alta"), ("frontend/lib/api/x.ts", 1, "alta")])
        self.assertTrue(h[0].mensaje.startswith("TS2322"))

    def test_eslint(self):
        datos = [{"filePath": str(self.base / "app" / "page.tsx"), "messages": [
            {"ruleId": "react-hooks/exhaustive-deps", "severity": 1, "message": "Falta dep", "line": 9},
            {"ruleId": "@next/next/no-img-element", "severity": 2, "message": "Usa next/image", "line": 3},
        ]}]
        h = frontend.parsear_eslint(json.dumps(datos), self.raiz, self.base)
        self.assertEqual(sorted((x.regla, x.severidad, x.linea) for x in h),
                         [("@next/next/no-img-element", "media", 3), ("react-hooks/exhaustive-deps", "baja", 9)])
        self.assertEqual(h[0].archivo, "frontend/app/page.tsx")

    def test_react_doctor_tolerante(self):
        # El --json de react-doctor no tiene esquema documentado: se prueban dos formas.
        plano = {"ok": True, "summary": {"errors": 1}, "diagnostics": [
            {"filePath": "app/page.tsx", "line": 12, "rule": "no-array-index-key", "plugin": "react-doctor",
             "severity": "error", "message": "No uses el índice como key", "help": "Usa un id estable"},
            {"filePath": "components/T.tsx", "location": {"line": 3}, "rule": "no-effect-fetch",
             "severity": "warning", "message": "fetch en useEffect"},
        ]}
        h = frontend.parsear_react_doctor("Escaneando…\n" + json.dumps(plano), self.raiz, self.base)
        self.assertEqual([(x.archivo, x.linea, x.severidad, x.regla) for x in h], [
            ("frontend/app/page.tsx", 12, "alta", "react-doctor/no-array-index-key"),
            ("frontend/components/T.tsx", 3, "media", "no-effect-fetch"),
        ])
        agrupado = {"projects": [{"rules": [{"rule": "rerender", "severity": "warning", "message": "Re-render",
                                             "files": [{"path": "app/a.tsx", "line": 2}, {"path": "app/b.tsx", "line": 5}]}]}]}
        h = frontend.parsear_react_doctor(json.dumps(agrupado), self.raiz, self.base)
        self.assertEqual([(x.archivo, x.linea, x.regla) for x in h],
                         [("frontend/app/a.tsx", 2, "rerender"), ("frontend/app/b.tsx", 5, "rerender")])

    def test_react_doctor_error(self):
        with self.assertRaises(ValueError):
            frontend.parsear_react_doctor(json.dumps({"ok": False, "error": "no es un proyecto React"}), self.raiz, self.base)


if __name__ == "__main__":
    unittest.main()

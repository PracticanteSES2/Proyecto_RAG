"""
Los scripts de mantenimiento de tools/ arrancan como se ejecutan de verdad.

`tools/update_rag.py` lanza a los demás con `python tools/<script>.py`: en ese modo Python solo pone
`tools/` en sys.path, así que cada script debe añadir la raíz del proyecto ANTES de importar `src`.
Un refactor que reordene los imports (p. ej. los de `src.comun` del 2026-11-10) rompe la
actualización completa del RAG sin que ninguna otra prueba lo note.

La prueba carga cada script en un proceso aparte (sin ejecutar su `main`: no toca Power BI, red ni
data/) y comprueba que importa y que su raíz es la del proyecto.

Ejecutar:  python -X utf8 -m unittest tests.pipeline.test_scripts_de_mantenimiento
"""
import subprocess
import sys
import unittest
from pathlib import Path

from src.comun.rutas import RAIZ_PROYECTO as RAIZ

SCRIPTS = (
    "update_rag.py",
    "sync_powerbi_links.py",
    "sync_powerbi_metadata.py",
    "ingest_rag.py",
    "import_documentation_batch.py",
    "build_powerbi_catalogs.py",
)

# runpy carga el archivo como lo haría `python tools/x.py` (sys.path[0] = tools/), pero con otro
# __name__ para que no corra su main. Imprime la raíz que calculó el script.
CARGA = (
    "import runpy, sys\n"
    "sys.path[0] = sys.argv[2]\n"
    "g = runpy.run_path(sys.argv[1], run_name='carga_de_prueba')\n"
    "print(g.get('PROJECT_ROOT') or g.get('ROOT'))\n"
)


class ScriptsDeMantenimientoTest(unittest.TestCase):
    def test_cada_script_importa_desde_tools_con_la_raiz_del_proyecto(self):
        for nombre in SCRIPTS:
            with self.subTest(script=nombre):
                ruta = RAIZ / "tools" / nombre
                self.assertTrue(ruta.exists(), f"falta {ruta}")
                proceso = subprocess.run(
                    [sys.executable, "-X", "utf8", "-c", CARGA, str(ruta), str(ruta.parent)],
                    cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", timeout=600,
                )
                self.assertEqual(proceso.returncode, 0, proceso.stderr[-1500:])
                raiz = (proceso.stdout.strip().splitlines() or [""])[-1]
                self.assertEqual(Path(raiz).resolve(), RAIZ, f"{nombre} calcula la raíz {raiz!r}")


if __name__ == "__main__":
    unittest.main()

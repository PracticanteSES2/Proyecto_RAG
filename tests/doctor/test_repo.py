"""El repo real no baja del listón: `python -m tools.doctor --verificar`.

  .venv\\Scripts\\python.exe -X utf8 -m unittest tests.doctor.test_repo -v

Si falla, el cambio empeoró la salud del proyecto (ver docs/calidad/doctor.md).
"""
import subprocess
import sys
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


class RepoTests(unittest.TestCase):
    def test_verificar_repo(self):
        inicio = time.perf_counter()
        r = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "tools.doctor", "--verificar", "--sin-externas"],
            cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
        duracion = time.perf_counter() - inicio
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # Meta: < 30 s; margen para máquinas cargadas.
        self.assertLess(duracion, 60, f"el doctor tardó {duracion:.1f} s")


if __name__ == "__main__":
    unittest.main()

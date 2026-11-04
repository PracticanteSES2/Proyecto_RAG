import tomllib
import unittest
from pathlib import Path

from src.ui import estilo

RAIZ = Path(__file__).resolve().parents[2]


class TestEstilo(unittest.TestCase):
    def test_config_toml_valido_y_con_color_primario(self):
        datos = tomllib.loads((RAIZ / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(datos["theme"]["primaryColor"].upper(), estilo.AZUL_PRIMARIO)

    def test_css_incluye_los_tres_colores_del_filete(self):
        c = estilo.css()
        for color in (estilo.AZUL, estilo.VERDE, estilo.CORAL):
            self.assertIn(color, c)

    def test_logo_existe(self):
        self.assertTrue(estilo.LOGO_PATH.exists())


if __name__ == "__main__":
    unittest.main()

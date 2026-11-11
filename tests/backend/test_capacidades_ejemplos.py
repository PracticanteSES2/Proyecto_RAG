"""Ejemplos de preguntas de la bienvenida: legibles y con el tablero nombrado."""
import json
import tempfile
import unittest
from pathlib import Path

from backend.app.services.capacidades import ejemplos_preguntas


def _raiz_con_metricas(metricas: list[dict]) -> Path:
    raiz = Path(tempfile.mkdtemp())
    (raiz / "data" / "rag").mkdir(parents=True)
    (raiz / "data" / "rag" / "master_metrics.json").write_text(
        json.dumps({"metrics": metricas}), encoding="utf-8")
    return raiz


class EjemplosPreguntasTest(unittest.TestCase):
    def test_descarta_etiquetas_tecnicas_y_metricas_sin_tablero(self):
        raiz = _raiz_con_metricas([
            {"label": "%OCUPACIONHOS", "report": None},
            {"label": "%RARO", "report": "TABLERO X"},
            {"label": "CAMAS OCUPADAS", "report": "BRIEFING HOSPITALARIO"},
        ])
        ejemplos = ejemplos_preguntas(raiz, [], ["Briefing Hospitalario"])
        self.assertFalse(any("%" in e for e in ejemplos))
        self.assertIn("Camas ocupadas del mes pasado en Briefing Hospitalario", ejemplos)

    def test_usa_el_nombre_del_catalogo_y_si_no_lo_hay_el_del_informe(self):
        raiz = _raiz_con_metricas([{"label": "PESO TOTAL por Mes", "report": "TABLERO LAVANDERIA"}])
        self.assertIn("Peso total por mes del mes pasado en Tablero Lavanderia", ejemplos_preguntas(raiz, []))

    def test_sin_metricas_quedan_los_fijos(self):
        ejemplos = ejemplos_preguntas(Path(tempfile.mkdtemp()), [])
        self.assertEqual(ejemplos, ["¿Qué tableros puedo consultar?"])


if __name__ == "__main__":
    unittest.main()

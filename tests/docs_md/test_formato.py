"""
Pruebas del formato y del repositorio de la documentación .md.

    python -m unittest tests.docs_md.test_formato
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.docs_md import formato as F
from src.docs_md import repositorio as R

FIXTURES = Path(__file__).parent / "fixtures"
EJEMPLO = FIXTURES / "tablero_tiempos_urgencias" / "md" / "consultas_dia.md"


class FormatoTest(unittest.TestCase):
    def setUp(self):
        self.texto = EJEMPLO.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.doc = F.parsear(self.texto)

    def test_ejemplo_valido_y_canonico(self):
        self.assertEqual(F.validar(self.doc), [])
        self.assertEqual(F.serializar(self.doc), self.texto)

    def test_metadatos(self):
        self.assertEqual(self.doc.pagina, "CONSULTAS DIA")
        self.assertEqual(self.doc.meta["tablas"], ["CONSULTAS_DIA", "EN_ESPERA_CONSULTA"])
        self.assertEqual(self.doc.meta["version"], 1)

    def test_busqueda_sin_tildes_ni_mayusculas(self):
        self.assertIsNotNone(self.doc.buscar("Reglas de negocio", "semaforo TRIAGE ii"))

    def test_modificar_agrega_historial_y_version(self):
        op = F.Operacion("modificar", "Reglas de negocio", "Semáforo triage II", "Verde de 0 a 20 minutos, amarillo de 21 a 30 y rojo de 31 o más")
        nuevo = F.aplicar_operaciones(self.doc, [op], "Se amplió el verde del semáforo de triage II a 20 minutos", autor="Ana", fecha="2026-10-21")
        self.assertEqual(nuevo.buscar("Reglas de negocio", "Semáforo triage II").texto,
                         "Verde de 0 a 20 minutos, amarillo de 21 a 30 y rojo de 31 o más.")
        self.assertEqual(nuevo.meta["version"], 2)
        self.assertEqual(nuevo.meta["actualizado"], "2026-10-21")
        ultima = nuevo.entradas("Historial de cambios")[-1]
        self.assertEqual(ultima.nombre, "2026-10-21 · v2")
        self.assertIn("Autor: Ana.", ultima.texto)
        self.assertEqual(F.validar(nuevo), [])
        # el original no cambia
        self.assertEqual(self.doc.meta["version"], 1)

    def test_agregar_y_eliminar(self):
        ops = [
            F.Operacion("agregar", "Visuales", "Tarjeta total en espera", "Cantidad de pacientes en espera de consulta"),
            F.Operacion("eliminar", "Visuales", "Leyendas de oportunidad"),
        ]
        nuevo = F.aplicar_operaciones(self.doc, ops, "Nueva tarjeta y sin leyendas")
        nombres = [e.nombre for e in nuevo.entradas("Visuales")]
        self.assertIn("Tarjeta total en espera", nombres)
        self.assertNotIn("Leyendas de oportunidad", nombres)

    def test_errores_de_operacion(self):
        casos = [
            F.Operacion("modificar", "Visuales", "No existe", "x"),
            F.Operacion("agregar", "Reglas de negocio", "semáforo triage ii", "duplicado"),
            F.Operacion("agregar", "Sección inventada", "X", "y"),
            F.Operacion("borrar", "Visuales", "X", "y"),
            F.Operacion("modificar", "Historial de cambios", "x", "y"),
            F.Operacion("agregar", "Propósito", "x", "y"),
        ]
        for op in casos:
            with self.subTest(op=op):
                with self.assertRaises(F.ErrorOperacion):
                    F.aplicar_operaciones(self.doc, [op], "r")

    def test_proposito_se_reemplaza(self):
        nuevo = F.aplicar_operaciones(self.doc, [F.Operacion("modificar", "Propósito", "", "Texto nuevo.")], "r")
        self.assertEqual(nuevo.proposito, "Texto nuevo.")

    def test_validar_detecta_problemas(self):
        malo = self.texto.replace("## Visuales", "## Gráficos").replace("Verde de 0 a 15 minutos, amarillo de 16 a 30 y rojo de 31 o más.", "sin punto")
        errores = F.validar(malo)
        self.assertTrue(any("Gráficos" in e for e in errores))
        self.assertTrue(any("terminar en punto" in e for e in errores))

    def test_entrada_en_varias_lineas_se_une(self):
        texto = self.texto.replace(
            "- **Semáforo triage II**: Verde de 0 a 15 minutos, amarillo de 16 a 30 y rojo de 31 o más.",
            "- **Semáforo triage II**: Verde de 0 a 15 minutos,\n  amarillo de 16 a 30 y rojo de 31 o más.",
        )
        doc = F.parsear(texto)
        self.assertEqual(doc.buscar("Reglas de negocio", "Semáforo triage II").texto,
                         "Verde de 0 a 15 minutos, amarillo de 16 a 30 y rojo de 31 o más.")

    def test_diff(self):
        nuevo = F.aplicar_operaciones(self.doc, [F.Operacion("eliminar", "Observaciones", "Huecos en el semáforo")], "r")
        diff = F.diferencias(self.texto, F.serializar(nuevo), "consultas_dia.md")
        self.assertIn("-- **Huecos en el semáforo**", diff)


class RepositorioTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shutil.copytree(FIXTURES / "tablero_tiempos_urgencias", Path(self.tmp) / "tablero_tiempos_urgencias")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_listar_y_leer(self):
        tableros = R.listar_tableros(self.tmp)
        self.assertEqual(tableros[0]["source_group"], "tablero_tiempos_urgencias")
        self.assertEqual(tableros[0]["tablero"], "TABLERO TIEMPOS URGENCIAS")
        paginas = R.listar_paginas("tablero_tiempos_urgencias", self.tmp)
        self.assertIn("CONSULTAS DIA", [p["pagina"] for p in paginas])
        doc = R.leer_pagina("tablero_tiempos_urgencias", "consultas día", self.tmp)
        self.assertEqual(doc.pagina, "CONSULTAS DIA")

    def test_guardar_valida(self):
        doc = R.leer_pagina("tablero_tiempos_urgencias", "CONSULTAS DIA", self.tmp)
        doc.proposito = ""
        with self.assertRaises(R.ErrorRepositorio):
            R.guardar_pagina("tablero_tiempos_urgencias", doc, self.tmp)

    def test_raiz_por_variable_de_entorno(self):
        os.environ["DOCS_MD_ROOT"] = self.tmp
        try:
            self.assertEqual(len(R.listar_tableros()), 1)
        finally:
            del os.environ["DOCS_MD_ROOT"]


if __name__ == "__main__":
    unittest.main()

"""
Pruebas del contenido de la documentación .md del TABLERO TIEMPOS URGENCIAS
(fixture que sirve de documentación inicial del tablero).

    python -m unittest tests.docs_md.test_contenido
"""
import re
import unittest
from pathlib import Path

from src.docs_md import formato as F
from src.docs_md import repositorio as R

CARPETA = Path(__file__).parent / "fixtures" / "tablero_tiempos_urgencias" / "md"
TABLERO = "TABLERO TIEMPOS URGENCIAS"
PAGINA_GENERAL = "GENERAL"
HISTORIAL_INICIAL = ("2026-10-20 · v1",
                     "Documentación inicial generada a partir del PBIP y de la documentación versión 2.")

# Páginas del PBIP (definition/pages). Las dos páginas llamadas «INTERCONSULTAS»
# se documentan como INTERCONSULTAS DIA e INTERCONSULTAS HISTORICO.
PAGINAS_DIA = [
    "RESUMEN_D", "RESUMEN DIA", "TIEMPOS TRIAGE DIA", "ADMISIONES DIA", "CONSULTAS DIA",
    "CONSULTAS PRIORITARIAS", "INGRESOS DIA", "PACIENTES EN OBSERVACION", "HOSPITALIZACION DIA",
    "EGRESOS DIA", "INTERCONSULTAS DIA", "LABORATORIOS", "IMAGENES DIA",
]
PAGINAS_HISTORICO = [
    "RESUMEN", "TIEMPO TRIAGE", "MAPA DE CALOR TRIAGE", "LLEGADAS", "TIEMPO TRIAGE-ADMISION",
    "MAPA DE CALOR ADMISIONES", "TIEMPO PARA CONSULTA", "MAPA DE CALOR CONSULTAS",
    "INICIO TRATAMIENTO HISTORICOS", "MAPA DE CALOR TRATAMIENTOS", "OBSERVACIÓN HISTORICO",
    "EXAMENES", "IMAGENES", "INTERCONSULTAS HISTORICO", "TIEMPO EGRESO", "TIEMPO HOSPI",
    "TIEMPO ESTANCIA", "TIEMPO ASIGNACIÓN CAMAS",
]

# Tamaño máximo (líneas) para mantener la documentación compacta.
MAX_LINEAS_PAGINA = 50
MAX_LINEAS_GENERAL = 110

# Patrones de datos personales obvios: números de documento o teléfono (7 o más
# dígitos seguidos, con o sin separadores de miles), correos y siglas de documento
# seguidas de un número.
PATRONES_PII = [
    re.compile(r"(?<![\w.])\d{7,}(?![\w])"),
    re.compile(r"\b\d{1,3}(?:\.\d{3}){2,}\b"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    re.compile(r"\b(?:C\.?C\.?|T\.?I\.?|R\.?C\.?|C\.?E\.?)\s*(?:No\.?|N°|#)?\s*\d{5,}", re.IGNORECASE),
]


def _leer(archivo: Path) -> str:
    return archivo.read_text(encoding="utf-8").replace("\r\n", "\n")


class ContenidoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archivos = sorted(CARPETA.glob("*.md"))
        cls.textos = {a.name: _leer(a) for a in cls.archivos}
        cls.docs = {nombre: F.parsear(texto) for nombre, texto in cls.textos.items()}

    def test_cantidad_de_archivos(self):
        self.assertEqual(len(self.archivos), 1 + len(PAGINAS_DIA) + len(PAGINAS_HISTORICO))
        self.assertIn(R.ARCHIVO_GENERAL, self.textos)

    def test_formato_valido_y_canonico(self):
        for nombre, texto in self.textos.items():
            with self.subTest(archivo=nombre):
                doc = self.docs[nombre]
                self.assertEqual(F.validar(doc), [])
                self.assertEqual(F.serializar(doc), texto)

    def test_nombre_de_archivo(self):
        for nombre, doc in self.docs.items():
            with self.subTest(archivo=nombre):
                self.assertEqual(R.archivo_para(doc), nombre)

    def test_metadatos(self):
        for nombre, doc in self.docs.items():
            with self.subTest(archivo=nombre):
                self.assertEqual(doc.meta.get("tablero"), TABLERO)
                self.assertEqual(doc.meta.get("version"), 1)
                self.assertEqual(doc.meta.get("actualizado"), "2026-10-20")
                self.assertTrue(str(doc.meta.get("nombre_funcional") or "").strip())
                if doc.meta.get("bloque") != "General":
                    self.assertTrue(doc.meta.get("tablas"), "La página debe declarar sus tablas.")

    def test_historial_inicial(self):
        for nombre, doc in self.docs.items():
            with self.subTest(archivo=nombre):
                historial = doc.entradas(F.SECCION_HISTORIAL)
                self.assertEqual([(e.nombre, e.texto) for e in historial], [HISTORIAL_INICIAL])

    def test_paginas_unicas(self):
        paginas = [doc.pagina for doc in self.docs.values()]
        claves = [F.normalizar_nombre(p) for p in paginas]
        self.assertEqual(len(claves), len(set(claves)), paginas)

    def test_todas_las_paginas_del_pbip_cubiertas(self):
        por_bloque = {"General": set(), "Día": set(), "Histórico": set()}
        for doc in self.docs.values():
            por_bloque[doc.meta["bloque"]].add(doc.pagina)
        self.assertEqual(por_bloque["General"], {PAGINA_GENERAL})
        self.assertEqual(por_bloque["Día"], set(PAGINAS_DIA))
        self.assertEqual(por_bloque["Histórico"], set(PAGINAS_HISTORICO))

    def test_interconsultas_explica_nombre_en_power_bi(self):
        for pagina in ("INTERCONSULTAS DIA", "INTERCONSULTAS HISTORICO"):
            with self.subTest(pagina=pagina):
                doc = next(d for d in self.docs.values() if d.pagina == pagina)
                self.assertIn("se llama INTERCONSULTAS", doc.proposito)

    def test_compacto(self):
        for nombre, texto in self.textos.items():
            with self.subTest(archivo=nombre):
                limite = MAX_LINEAS_GENERAL if nombre == R.ARCHIVO_GENERAL else MAX_LINEAS_PAGINA
                self.assertLessEqual(len(texto.splitlines()), limite)

    def test_sin_sql(self):
        sql = re.compile(r"\bSELECT\b.+\bFROM\b|\bLEFT JOIN\b|\bINNER JOIN\b", re.IGNORECASE)
        for nombre, texto in self.textos.items():
            with self.subTest(archivo=nombre):
                self.assertIsNone(sql.search(texto))

    def test_sin_datos_personales(self):
        for nombre, texto in self.textos.items():
            for numero, linea in enumerate(texto.splitlines(), 1):
                for patron in PATRONES_PII:
                    with self.subTest(archivo=nombre, linea=numero, patron=patron.pattern):
                        self.assertIsNone(patron.search(linea), linea)


if __name__ == "__main__":
    unittest.main()

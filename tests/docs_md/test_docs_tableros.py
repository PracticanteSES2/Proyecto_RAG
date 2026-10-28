"""
Valida toda la documentación .md de docs_tableros/ (un subtest por archivo).

    python -m unittest tests.docs_md.test_docs_tableros
"""
import json
import re
import unittest
from pathlib import Path

from src.docs_md import formato as F
from src.docs_md import repositorio as R

RAIZ = Path(__file__).resolve().parents[2] / "docs_tableros"

# Patrones de datos personales obvios (documentos, teléfonos, correos).
PII = [
    # 7+ dígitos sueltos; no cuentan los decimales (5,4693…) ni los códigos
    # citados entre comillas simples ('3720102').
    re.compile(r"(?<![\d.,'])\d{7,}(?![\d'])"),
    # Números con separador de miles que parecen documentos; los montos
    # redondos (1.000.000, 500.000.000) son umbrales o rangos, no personas.
    re.compile(r"\b\d{1,3}(?:\.\d{3})+\.(?!000\b)\d{3}\b"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    re.compile(r"\b(?:CC|TI|RC|CE)\s*[:#]?\s*\d{5,}\b"),
]

# Identificadores técnicos de Power BI que no son datos personales y se quitan
# antes de buscar PII: ids de página («ReportSection0b34ce4c…», «6c03bc7bd793eda6c68a»),
# GUID y el valor de `id_pagina` en los metadatos. Solo se quitan tokens con
# letras hexadecimales (o el prefijo ReportSection): un número de documento o un
# teléfono, que son solo dígitos, nunca se quita.
_IDS_TECNICOS = [
    re.compile(r"^id_pagina:.*$", re.M),
    re.compile(r"\bReportSection[0-9A-Za-z]*\b"),
    re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    re.compile(r"\b(?=[0-9a-fA-F]*[a-fA-F])(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{16,}\b"),
]


def sin_ids_tecnicos(texto: str) -> str:
    for patron in _IDS_TECNICOS:
        texto = patron.sub(" ", texto)
    return texto


def posible_pii(texto: str) -> str | None:
    """Patrón de PII que aparece en el texto (sin contar ids técnicos) o None."""
    limpio = sin_ids_tecnicos(texto)
    for patron in PII:
        if patron.search(limpio):
            return patron.pattern
    return None


def _grupos():
    return sorted(p for p in RAIZ.iterdir() if p.is_dir()) if RAIZ.exists() else []


class DocsTablerosTest(unittest.TestCase):
    def test_hay_documentacion(self):
        self.assertTrue(_grupos(), "docs_tableros/ está vacío")

    def test_cada_grupo_tiene_manifest_general_y_paginas(self):
        for grupo in _grupos():
            with self.subTest(grupo=grupo.name):
                manifest = json.loads((grupo / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest.get("source_group"), grupo.name)
                archivos = sorted((grupo / "md").glob("*.md"))
                self.assertIn("_general.md", [a.name for a in archivos])
                self.assertGreater(len(archivos), 1)

    def test_archivos_validos_canonicos_y_sin_pii(self):
        for grupo in _grupos():
            paginas = set()
            for archivo in sorted((grupo / "md").glob("*.md")):
                with self.subTest(archivo=f"{grupo.name}/{archivo.name}"):
                    texto = archivo.read_text(encoding="utf-8").replace("\r\n", "\n")
                    doc = F.parsear(texto)
                    self.assertEqual(F.validar(doc), [])
                    self.assertEqual(F.serializar(doc), texto, "no está en forma canónica")
                    self.assertEqual(R.archivo_para(doc), archivo.name)
                    self.assertNotIn(F.normalizar_nombre(doc.pagina), paginas, "página repetida")
                    paginas.add(F.normalizar_nombre(doc.pagina))
                    if archivo.name == "_general.md":
                        self.assertEqual(doc.meta.get("pagina"), "GENERAL")
                    self.assertIsNone(posible_pii(texto), "posible dato personal")


class DiccionariosTest(unittest.TestCase):
    """`_diccionario*.md` (bloque Diccionario), cuando existen."""

    def _archivos(self):
        return [(g, a) for g in _grupos() for a in sorted((g / "md").glob("*.md")) if R.es_archivo_diccionario(a.name)]

    def test_diccionarios_cumplen_el_formato(self):
        from src.docs_md import ingesta as I

        for grupo, archivo in self._archivos():
            with self.subTest(archivo=f"{grupo.name}/{archivo.name}"):
                texto = archivo.read_text(encoding="utf-8").replace("\r\n", "\n")
                doc = F.parsear(texto)
                self.assertEqual(F.validar(doc), [])
                self.assertEqual(F.serializar(doc), texto, "no está en forma canónica")
                self.assertEqual(doc.meta.get("bloque"), "Diccionario")
                self.assertEqual(R.archivo_para(doc), archivo.name)
                self.assertTrue(set(doc.secciones) <= set(F.SECCIONES_DICCIONARIO))
                self.assertIsNone(posible_pii(texto), "posible dato personal")
                for e in doc.entradas("Medidas"):
                    campos = I.campos_entrada_diccionario(e.texto)
                    self.assertTrue(campos["tabla"], f"{e.nombre}: falta «Tabla:»")
                    self.assertIn("Cálculo:", e.texto, e.nombre)
                    self.assertIn("Se usa en:", e.texto, e.nombre)
                for seccion in ("Columnas calculadas", "Columnas clave"):
                    for e in doc.entradas(seccion):
                        self.assertIn("Se usa en:", e.texto, e.nombre)
                for e in doc.entradas("Columnas calculadas"):
                    self.assertIn("Cálculo:", e.texto, e.nombre)

    def test_nombres_unicos_entre_los_archivos_del_diccionario_de_un_grupo(self):
        vistos = {}
        for grupo, archivo in self._archivos():
            doc = F.parsear(archivo.read_text(encoding="utf-8"))
            for seccion in ("Medidas", "Columnas calculadas", "Columnas clave", "Tablas", "Relaciones"):
                for e in doc.entradas(seccion):
                    clave = (grupo.name, seccion, F.normalizar_nombre(e.nombre))
                    self.assertNotIn(clave, vistos, f"{e.nombre} repetido en {archivo.name} y {vistos.get(clave)}")
                    vistos[clave] = archivo.name

    def test_el_diccionario_no_es_una_pagina(self):
        for grupo, archivo in self._archivos():
            nombres = [p["archivo"] for p in R.listar_paginas(grupo.name, RAIZ)]
            self.assertNotIn(archivo.name, nombres)
            self.assertIn(archivo.name, [d["archivo"] for d in R.listar_diccionarios(grupo.name, RAIZ)])


if __name__ == "__main__":
    unittest.main()

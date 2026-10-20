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
    re.compile(r"\b\d{7,}\b"),
    re.compile(r"\b\d{1,3}(?:\.\d{3}){2,}\b"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    re.compile(r"\b(?:CC|TI|RC|CE)\s*[:#]?\s*\d{5,}\b"),
]


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
                    for patron in PII:
                        self.assertIsNone(patron.search(texto), f"posible dato personal: {patron.pattern}")


if __name__ == "__main__":
    unittest.main()

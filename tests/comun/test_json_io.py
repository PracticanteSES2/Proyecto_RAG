"""src/comun/json_io.py, colecciones.py y registro.py frente a las implementaciones que reemplazan.

Los ORÁCULOS son copias literales de los lectores/escritores que había en src/ (fase 3): la salida en disco
debe ser idéntica byte a byte y la lectura, el mismo objeto.

    python -X utf8 -m unittest tests.comun.test_json_io
"""
import contextlib
import io
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path

from src.comun import colecciones, json_io, registro

DATOS = {"tablero": "Ocupación", "ñ": ["á", 1, 2.5, None, True], "anidado": {"x": [{"y": "z"}]}, "vacío": {}}


def o_save_json_catalog_utils(data, output_file):
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, default=str)


def o_save_json_write_text(data, path):
    # powerbi_catalog_manager · tools/import_documentation_batch · tools/local_data/metadata_format ·
    # tools/sync_powerbi_metadata
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def o_save_json_chunk_builder(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def o_escribir_json_atomico(datos, ruta):
    # catalogo/indexacion._escribir_json (antes en docs_md)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


class TestEscribir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _bytes(self, escritor, nombre, datos=DATOS):
        ruta = self.tmp / nombre / "sub" / "x.json"
        escritor(datos, ruta)
        return ruta.read_bytes()

    def test_mismos_bytes_que_los_escritores_viejos(self):
        nuevo = self._bytes(lambda d, r: json_io.escribir_json(d, r), "nuevo")
        self.assertEqual(nuevo, self._bytes(o_save_json_write_text, "write_text"))
        self.assertEqual(nuevo, self._bytes(o_save_json_chunk_builder, "chunk"))
        atomico = self._bytes(lambda d, r: json_io.escribir_json(d, r, atomico=True), "atomico")
        self.assertEqual(atomico, self._bytes(o_escribir_json_atomico, "atomico_viejo"))
        self.assertEqual(nuevo, atomico)
        self.assertEqual([p.name for p in (self.tmp / "atomico" / "sub").iterdir()], ["x.json"])

    def test_default_str_como_catalog_utils(self):
        datos = {"ruta": Path("a/b"), "n": 1}
        nuevo = self._bytes(lambda d, r: json_io.escribir_json(d, r, default=str), "nuevo", datos)
        self.assertEqual(nuevo, self._bytes(o_save_json_catalog_utils, "viejo", datos))


class TestLeer(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ruta = self.tmp / "x.json"
        json_io.escribir_json(DATOS, self.ruta)

    def test_lee_igual(self):
        with open(self.ruta, "r", encoding="utf-8") as archivo:
            self.assertEqual(json_io.leer_json(self.ruta), json.load(archivo))

    def test_faltante(self):
        faltante = self.tmp / "no.json"
        with self.assertRaises(FileNotFoundError):
            json_io.leer_json(faltante)
        self.assertIsNone(json_io.leer_json(faltante, None))
        self.assertEqual(json_io.leer_json(faltante, {}), {})

    def test_bom(self):
        con_bom = self.tmp / "bom.json"
        con_bom.write_bytes(b"\xef\xbb\xbf" + json.dumps({"a": 1}).encode("utf-8"))
        self.assertEqual(json_io.leer_json(con_bom, bom=True), {"a": 1})
        with self.assertRaises(json.JSONDecodeError):
            json_io.leer_json(con_bom)


class TestComoLista(unittest.TestCase):
    def test_casos(self):
        lista = [1]
        self.assertIs(colecciones.como_lista(lista), lista)
        self.assertEqual(colecciones.como_lista(None), [])
        self.assertEqual(colecciones.como_lista("a"), ["a"])
        self.assertEqual(colecciones.como_lista((1, 2)), [(1, 2)])
        self.assertEqual(colecciones.como_lista(0), [0])


class TestRegistro(unittest.TestCase):
    def tearDown(self):
        raiz = logging.getLogger()
        for h in list(raiz.handlers):
            if getattr(h, "_proyecto_rag", False):
                raiz.removeHandler(h)

    def test_cli_ve_info_por_stdout_como_print(self):
        registro.configurar_registro()
        registro.configurar_registro()  # idempotente
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            logging.getLogger("src.prueba").info("Documentos procesados: %s", 3)
        self.assertEqual(salida.getvalue(), "Documentos procesados: 3\n")
        self.assertEqual(sum(getattr(h, "_proyecto_rag", False) for h in logging.getLogger().handlers), 1)

    def test_mensajes_de_visibles_y_silenciados(self):
        log = logging.getLogger("src.prueba_ctx.modulo")
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), registro.mensajes_de(["src.prueba_ctx"], visibles=True):
            log.info("Procesando: %s", "a.md")
        self.assertEqual(salida.getvalue(), "Procesando: a.md\n")
        errores = io.StringIO()
        with contextlib.redirect_stderr(errores), contextlib.redirect_stdout(salida), \
                registro.mensajes_de(["src.prueba_ctx"], visibles=False):
            log.warning("[AVISO] silenciado")
        self.assertEqual(errores.getvalue(), "")
        self.assertEqual(salida.getvalue(), "Procesando: a.md\n")
        self.assertEqual(logging.getLogger("src.prueba_ctx").handlers, [])
        self.assertTrue(logging.getLogger("src.prueba_ctx").propagate)

    def test_nivel_por_entorno(self):
        os.environ["PROYECTO_LOG_NIVEL"] = "warning"
        try:
            registro.configurar_registro()
            self.assertEqual(logging.getLogger().level, logging.WARNING)
        finally:
            os.environ.pop("PROYECTO_LOG_NIVEL", None)


if __name__ == "__main__":
    unittest.main()

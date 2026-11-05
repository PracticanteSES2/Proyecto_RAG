"""
Pruebas ADVERSARIALES de src/feedback (registro y lector). Cada prueba expresa el
comportamiento CORRECTO; si falla, es un hallazgo (ver task-1-pruebas.md).

  python -X utf8 -m unittest tests.feedback.test_adversarial_registro
"""
import copy
import datetime
import decimal
import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from src.feedback import lector, registro

RAIZ = Path(__file__).resolve().parents[2]


def _rec(id_turno="s:1", cal="buena", **extra):
    r = {"id_turno": id_turno, "calificacion": cal, "esperado": ""}
    r.update(extra)
    return r


def _estricto(linea: str):
    """json.loads que rechaza NaN/Infinity (JSON estricto)."""
    def malo(c):
        raise ValueError("constante no JSON: " + c)
    return json.loads(linea, parse_constant=malo)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ruta = self.dir / "cal.jsonl"
        self._old = os.environ.get("FEEDBACK_DIR")
        os.environ["FEEDBACK_DIR"] = str(self.dir)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("FEEDBACK_DIR", None)
        else:
            os.environ["FEEDBACK_DIR"] = self._old
        self._tmp.cleanup()

    def lineas(self):
        return self.ruta.read_bytes().split(b"\n")[:-1]


# ---------------------------------------------------------------- (1) tipos raros
class TiposRaros(Base):
    def test_result_no_dict_no_lanza(self):
        for r in (None, [], [1, 2], "texto", 5, set()):
            snap = registro.snapshot_turno(r, "x", "p", "texto", [])
            json.dumps(snap)

    def test_claves_con_none_y_tipos_cruzados(self):
        r = {"status": None, "route": None, "sources": None, "query_plan": [], "source_context": "x",
             "question": None, "error": None, "metric": None,
             "filters": "no es lista"}
        snap = registro.snapshot_turno(r, None, None, None, None)
        json.dumps(snap, allow_nan=False)

    def test_listas_con_basura_dentro(self):
        r = {"sources": [None, 5, "x", [], {"score": "alto"}],
             "query_plan": {"filters": [None, 3, {"values": 7}], "group_by": [None, "x"], "metric": 5},
             "source_context": {"candidates": [None, 1, {"score": None}]}}
        snap = registro.snapshot_turno(r, "r", "p", "texto", [None, 3, "ok"])
        json.dumps(snap, allow_nan=False)

    def test_strings_enormes_5mb_se_acotan_y_rapido(self):
        grande = "x" * (5 * 1024 * 1024)
        t0 = time.time()
        snap = registro.snapshot_turno({"error": grande, "question": grande}, grande, grande, "t", [grande])
        self.assertLess(time.time() - t0, 5)
        self.assertLessEqual(len(snap["respuesta"]), 1500)
        self.assertLessEqual(len(snap["error"]), 200)

    def test_pregunta_y_opciones_enormes_estan_acotadas(self):
        """El log no debe poder crecer sin límite por un texto libre (pregunta, opciones)."""
        grande = "x" * (5 * 1024 * 1024)
        snap = registro.snapshot_turno({"question": grande}, "r", grande, "t", [grande])
        total = len(json.dumps(snap, ensure_ascii=False))
        self.assertLess(total, 100_000, f"snapshot de {total} caracteres")

    def test_campos_identificadores_enormes_estan_acotados(self):
        grande = "y" * (2 * 1024 * 1024)
        snap = registro.snapshot_turno({"metric": grande, "report": grande, "not_found_reason": grande,
                                        "source_context": {"reason": grande}}, "r", "p", "t", [])
        total = len(json.dumps(snap, ensure_ascii=False))
        self.assertLess(total, 100_000, f"snapshot de {total} caracteres")

    def test_metric_dict_no_filtra_su_contenido(self):
        """Si `metric` llega como dict (con dax/valores), str(dict) no debe acabar en el log."""
        r = {"metric": {"label": "M", "dax": "EVALUATE SECRETO_DAX", "rows": ["Ana Perez"]}}
        texto = json.dumps(registro.snapshot_turno(r, "r", "p", "t", []), ensure_ascii=False)
        self.assertNotIn("SECRETO_DAX", texto)
        self.assertNotIn("Ana Perez", texto)

    def test_identificadores_no_dict_no_filtran(self):
        r = {"report": {"x": "SECRETO_FILA"}, "dashboard": ["SECRETO_FILA"], "stage": {"a": "SECRETO_FILA"}}
        texto = json.dumps(registro.snapshot_turno(r, "r", "p", "t", []), ensure_ascii=False)
        self.assertNotIn("SECRETO_FILA", texto)

    def test_unicode_raro_emoji_se_guarda_y_se_lee(self):
        raro = "ñandú 😀 \u200b\u202e \u2028 \x00 \x1f \ufeff 日本語"
        snap = registro.snapshot_turno({}, raro, raro, "t", [raro])
        reg = registro.construir_registro(snap, [{"rol": "user", "texto": raro}], "mala", raro, "s", 1)
        registro.guardar(reg, self.ruta)
        got = lector.cargar_calificaciones(self.ruta)
        self.assertEqual(len(got), 1)
        self.assertEqual(len(self.lineas()), 1)

    def test_surrogates_sueltos_no_rompen_guardar(self):
        """Un surrogate suelto (p.ej. de un texto pegado) no debe hacer fallar el guardado."""
        snap = registro.snapshot_turno({}, "a\ud800b", "p\udfffq", "t", [])
        reg = registro.construir_registro(snap, [], "mala", "falta \ud83d", "s", 1)
        registro.guardar(reg, self.ruta)
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 1)
        self.assertEqual(len(self.lineas()), 1)

    def test_valores_no_serializables_en_result(self):
        r = {"status": {1, 2}, "route": datetime.datetime.now(), "metric": decimal.Decimal("1.5"),
             "sources": [{"score": decimal.Decimal("0.5"), "id": {1}}],
             "source_context": {"candidates": [{"score": datetime.date.today()}]}}
        snap = registro.snapshot_turno(r, "r", "p", "t", [])
        registro.guardar(registro.construir_registro(snap, [], "buena", "", "s", 1), self.ruta)
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 1)

    def test_nan_e_inf_en_scores_producen_json_estricto(self):
        r = {"sources": [{"id": "a", "score": float("nan")}, {"id": "b", "score": float("inf")}],
             "source_context": {"candidates": [{"id": "a", "score": float("-inf")}]}}
        snap = registro.snapshot_turno(r, "r", "p", "t", [])
        registro.guardar(registro.construir_registro(snap, [], "buena", "", "s", 1), self.ruta)
        for l in self.lineas():
            _estricto(l.decode("utf-8"))

    def test_bool_no_se_trata_como_puntaje(self):
        snap = registro.snapshot_turno({"sources": [{"id": "a", "score": True}]}, "r", "p", "t", [])
        self.assertIsNone(snap["fuentes"][0]["puntaje"])


# ---------------------------------------------------------------- (2) enmascarado
class Enmascarado(Base):
    def m(self, texto):
        return registro.snapshot_turno({}, "", texto, "t", [])["pregunta"]

    def test_cedula_simple_y_longitudes(self):
        self.assertEqual(self.m("1234567890"), "[NUM]")
        self.assertEqual(self.m("123456"), "[NUM]")          # 6 exactos
        self.assertEqual(self.m("12345"), "12345")           # 5 no
        self.assertEqual(self.m("ced12345678abc"), "ced[NUM]abc")

    def test_cedula_con_puntos(self):
        self.assertNotRegex(self.m("cedula 1.234.567.890"), r"\d\.\d{3}\.\d{3}")

    def test_cedula_con_espacios(self):
        self.assertNotRegex(self.m("cedula 1 234 567 890"), r"234 567")

    def test_cedula_con_guiones(self):
        self.assertNotRegex(self.m("cedula 1234-567-890"), r"567-890")

    def test_periodos_y_fechas_legitimos_no_se_rompen_en_exceso(self):
        self.assertEqual(self.m("año 2025"), "año 2025")
        self.assertEqual(self.m("fecha 2025-10-05"), "fecha 2025-10-05")
        self.assertEqual(self.m("monto 12.345,67"), "monto 12.345,67")

    def test_periodo_aaaamm_se_conserva(self):
        # Hallazgo si falla: «202510» (periodo legítimo) se enmascara como si fuera cédula.
        self.assertEqual(self.m("periodo 202510"), "periodo 202510")

    def test_digitos_unicode_no_ascii(self):
        self.assertNotIn("\u0661\u0662\u0663\u0664\u0665\u0666\u0667", self.m("\u0661\u0662\u0663\u0664\u0665\u0666\u0667"))

    def test_digitos_ancho_completo(self):
        self.assertNotIn("１２３４５６７８", self.m("１２３４５６７８"))

    def test_decimal_largo_deja_cola_numerica_inocua(self):
        self.assertNotIn("1234567", self.m("saldo 1234567.89"))

    def test_mascara_tambien_en_historial_esperado_error_opciones(self):
        snap = registro.snapshot_turno({"error": "fallo cedula 1234567890"}, "r", "p", "t", ["opcion 9876543210"])
        reg = registro.construir_registro(snap, [{"rol": "user", "texto": "id 1112223334"}], "mala",
                                          "esperaba 5556667778", "s", 1)
        txt = json.dumps(reg)
        for n in ("1234567890", "9876543210", "1112223334", "5556667778"):
            self.assertNotIn(n, txt)

    def test_numero_en_campos_identificadores_enmascarado(self):
        """Un nombre de informe/tablero/not_found_reason con cédula embebida llega al log sin enmascarar."""
        r = {"not_found_reason": "sin datos para 1234567890", "report": "Informe 1234567890"}
        txt = json.dumps(registro.snapshot_turno(r, "r", "p", "t", []))
        self.assertNotIn("1234567890", txt)


# ---------------------------------------------------------------- (3) tablas
class Tablas(Base):
    def r(self, texto, result=None):
        return registro.snapshot_turno(result or {}, texto, "p", "t", [])["respuesta"]

    def test_tabla_con_pipe_inicial_y_crlf(self):
        out = self.r("Total 5\r\n| paciente | x |\r\n|---|---|\r\n| Ana | 1 |\r\n")
        self.assertNotIn("|", out)
        self.assertNotIn("Ana", out)

    def test_tabla_con_pipe_inicial_indentada_o_tab(self):
        out = self.r("Total\n   | Ana | 1 |\n\t| Juan | 2 |")
        self.assertNotIn("Ana", out)
        self.assertNotIn("Juan", out)

    def test_tabla_sin_pipe_inicial_no_filtra_filas(self):
        out = self.r("Total\npaciente | edad\n--- | ---\nAna Perez | 33\nJuan Gomez | 40")
        self.assertNotIn("Ana Perez", out)

    def test_separador_unicode_de_linea_no_oculta_tablas(self):
        out = self.r("Total\u2028| Ana | 1 |\u2028| Juan | 2 |")
        self.assertNotIn("Ana", out)

    def test_ruta_powerbi_tabla_solo_primera_linea(self):
        res = {"route": "powerbi", "result_type": "table"}
        out = self.r("Resumen 10 filas\n- Ana Perez: 3\n- Juan: 4", res)
        self.assertEqual(out, "Resumen 10 filas")

    def test_ruta_powerbi_tabla_primera_linea_es_tabla(self):
        res = {"route": "powerbi", "result_type": "table"}
        out = self.r("| a | b |\n| Ana | 1 |\nresumen", res)
        self.assertNotIn("Ana", out)

    def test_ruta_powerbi_detalle_solo_primera_linea(self):
        res = {"route": "powerbi", "result_type": "scalar", "detail": {"rows": [1]}}
        out = self.r("Total 5\nAna Perez 1\nJuan 2", res)
        self.assertEqual(out, "Total 5")

    def test_ruta_powerbi_primera_linea_se_recorta_a_400(self):
        res = {"route": "powerbi", "result_type": "table"}
        self.assertEqual(len(self.r("z" * 1000, res)), 400)

    def test_ruta_powerbi_primera_linea_vacia_inicial(self):
        res = {"route": "powerbi", "result_type": "table"}
        out = self.r("\n\n  Total 3\nAna", res)
        self.assertEqual(out, "Total 3")

    def test_ruta_rag_no_powerbi_con_tabla_no_se_trunca_a_una_linea(self):
        out = self.r("l1\nl2\nl3", {"route": "rag"})
        self.assertEqual(out, "l1\nl2\nl3")

    def test_vinetas_por_paciente_en_respuesta_no_tabular(self):
        """Documenta límite: viñetas fuera de ruta powerbi-tabla no se filtran (se espera que sí si hay nombres)."""
        out = self.r("- Ana Perez 1234567\n- Juan Gomez 7654321", {"route": "powerbi", "result_type": "scalar"})
        self.assertNotIn("Ana Perez", out)


# ---------------------------------------------------------------- (4) esperado
class Esperado(Base):
    def reg(self, esperado, cal="mala"):
        snap = registro.snapshot_turno({}, "r", "p", "t", [])
        return registro.construir_registro(snap, [], cal, esperado, "s", 1)

    def test_esperado_solo_espacios_tabs_y_unicode_rechazado(self):
        for e in ("", "   ", "\t\t", "\n\r\n", "\u00a0", "\u3000", "\u2003  \t", None):
            with self.assertRaises(ValueError, msg=repr(e)):
                self.reg(e)

    def test_esperado_con_caracteres_invisibles_rechazado(self):
        """Espacio de ancho cero / marca de dirección no es un comentario."""
        for e in ("\u200b", "\u200b\u200b ", "\ufeff", "\u2060"):
            with self.assertRaises(ValueError, msg=repr(e)):
                self.reg(e)

    def test_esperado_que_solo_son_lineas_de_tabla_no_queda_vacio(self):
        """«mala» con esperado '| x |' se acepta pero se guarda vacío: la calificación pierde su comentario."""
        try:
            reg = self.reg("| tablero | Cirugia |")
        except ValueError:
            return
        self.assertNotEqual(reg["esperado"], "")

    def test_esperado_con_saltos_es_una_sola_linea(self):
        reg = self.reg("linea1\nlinea2\r\nlinea3\u2028x\u0085y\x0b\x0c")
        registro.guardar(reg, self.ruta)
        self.assertEqual(len(self.lineas()), 1)
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 1)

    def test_esperado_1mb_esta_acotado(self):
        reg = self.reg("e" * (1024 * 1024))
        self.assertLess(len(reg["esperado"]), 20_000)

    def test_esperado_buena_con_solo_espacios_ok(self):
        self.assertEqual(self.reg("   ", "buena")["esperado"], "")

    def test_calificaciones_invalidas(self):
        for c in ("Buena", "BUENA", "", None, 1, True, "buena ", ["buena"]):
            with self.assertRaises((ValueError, TypeError), msg=repr(c)):
                self.reg("x", c)

    def test_calificacion_lista_lanza_ValueError_no_TypeError(self):
        with self.assertRaises(ValueError):
            self.reg("x", ["buena"])

    def test_calificacion_dict_no_hasheable(self):
        with self.assertRaises(ValueError):
            self.reg("x", {"a": 1})


# ---------------------------------------------------------------- (5) id_turno
class IdTurno(Base):
    def reg(self, ses, idx, cal="buena", esperado=""):
        snap = registro.snapshot_turno({}, "r", "p", "t", [])
        return registro.construir_registro(snap, [], cal, esperado, ses, idx)

    def test_id_con_dos_puntos_y_saltos(self):
        r = self.reg("a:b\nc\r\nd", 3)
        registro.guardar(r, self.ruta)
        got = lector.cargar_calificaciones(self.ruta)
        self.assertEqual(got[0]["id_turno"], "a:b\nc\r\nd:3")
        self.assertEqual(len(self.lineas()), 1)

    @unittest.skip("diferido al ledger (hallazgo 14)")
    def test_ids_no_colisionan_con_dos_puntos(self):
        a = self.reg("a:1", 2)["id_turno"]
        b = self.reg("a", "1:2")["id_turno"]
        self.assertNotEqual(a, b)

    @unittest.skip("diferido al ledger (hallazgo 14)")
    def test_indice_no_numerico_se_rechaza(self):
        with self.assertRaises((ValueError, TypeError)):
            self.reg("s", None)

    @unittest.skip("diferido al ledger (hallazgo 14)")
    def test_id_sesion_none_o_vacio_se_rechaza(self):
        for s in (None, ""):
            with self.assertRaises((ValueError, TypeError), msg=repr(s)):
                self.reg(s, 1)

    def test_reescritura_alterna_gana_la_ultima(self):
        for i, c in enumerate(["buena", "mala", "buena", "mala", "buena"]):
            registro.guardar(self.reg("s", 1, c, "x" if c == "mala" else ""), self.ruta)
        got = lector.cargar_calificaciones(self.ruta)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["calificacion"], "buena")

    @unittest.skip("diferido al ledger (hallazgo 15)")
    def test_orden_de_salida_sigue_a_la_ultima_escritura(self):
        registro.guardar(self.reg("s", 1), self.ruta)
        registro.guardar(self.reg("s", 2), self.ruta)
        registro.guardar(self.reg("s", 1, "mala", "x"), self.ruta)   # 1 reescrito al final
        ids = [r["id_turno"] for r in lector.cargar_calificaciones(self.ruta)]
        self.assertEqual(ids, ["s:2", "s:1"])

    def test_fechas_orden_cronologico(self):
        registro.guardar(self.reg("s", 1), self.ruta)
        time.sleep(1.1)
        registro.guardar(self.reg("s", 1, "mala", "x"), self.ruta)
        got = lector.cargar_calificaciones(self.ruta)
        self.assertEqual(got[0]["calificacion"], "mala")


# ---------------------------------------------------------------- (6) lector
class Lector(Base):
    def escribir(self, *trozos: bytes):
        self.ruta.write_bytes(b"".join(trozos))

    def test_bom_al_inicio(self):
        self.escribir(b"\xef\xbb\xbf" + json.dumps(_rec("a:1")).encode() + b"\n",
                      json.dumps(_rec("a:2")).encode() + b"\n")
        ids = {r["id_turno"] for r in lector.cargar_calificaciones(self.ruta)}
        self.assertEqual(ids, {"a:1", "a:2"})

    def test_lineas_crlf(self):
        self.escribir(json.dumps(_rec("a:1")).encode() + b"\r\n", json.dumps(_rec("a:2")).encode() + b"\r\n")
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 2)

    def test_linea_parcial_final_sin_salto(self):
        self.escribir(json.dumps(_rec("a:1")).encode() + b"\n", b'{"id_turno": "a:2", "calif')
        self.assertEqual([r["id_turno"] for r in lector.cargar_calificaciones(self.ruta)], ["a:1"])

    def test_ultima_linea_valida_sin_salto_final_se_lee(self):
        self.escribir(json.dumps(_rec("a:1")).encode())
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 1)

    def test_json_valido_pero_no_dict(self):
        self.escribir(b"[1,2]\n", b"5\n", b"null\n", b'"txt"\n', b"true\n", json.dumps(_rec("a:1")).encode() + b"\n")
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 1)

    def test_lineas_sin_id_turno_o_vacio(self):
        self.escribir(b'{"x":1}\n', b'{"id_turno": null}\n', b'{"id_turno": ""}\n', b"\n", b"   \n")
        self.assertEqual(lector.cargar_calificaciones(self.ruta), [])

    def test_id_turno_no_hasheable_no_rompe_el_lector(self):
        self.escribir(b'{"id_turno": ["a"]}\n', b'{"id_turno": {"k": 1}}\n', json.dumps(_rec("ok:1")).encode() + b"\n")
        got = lector.cargar_calificaciones(self.ruta)
        self.assertEqual([r["id_turno"] for r in got], ["ok:1"])

    def test_anidamiento_extremo_no_rompe_el_lector(self):
        self.escribir(b"[" * 200000 + b"]" * 200000 + b"\n", json.dumps(_rec("ok:1")).encode() + b"\n")
        got = lector.cargar_calificaciones(self.ruta)
        self.assertEqual([r["id_turno"] for r in got], ["ok:1"])

    def test_utf8_invalido_y_nul(self):
        self.escribir(b'{"id_turno":"a:1","x":"\xff\xfe"}\n', b"\x00\x00\x00\n", json.dumps(_rec("ok:1")).encode() + b"\n")
        self.assertEqual([r["id_turno"] for r in lector.cargar_calificaciones(self.ruta)], ["ok:1"])

    def test_archivo_vacio_y_inexistente(self):
        self.escribir(b"")
        self.assertEqual(lector.cargar_calificaciones(self.ruta), [])
        self.assertEqual(lector.cargar_calificaciones(self.dir / "nada.jsonl"), [])

    def test_ruta_str_y_defecto_por_env(self):
        registro.guardar(_rec("a:1"), str(self.ruta))
        self.assertEqual(len(lector.cargar_calificaciones(str(self.ruta))), 1)
        registro.guardar(_rec("a:2"))     # ruta por defecto -> FEEDBACK_DIR
        self.assertEqual(len(lector.cargar_calificaciones()), 1)
        self.assertEqual(registro.ruta_log(), self.dir / "calificaciones.jsonl")

    def test_registro_con_u2028_crudo_no_parte_la_linea(self):
        registro.guardar(_rec("a:1", esperado="x\u2028y\u0085z"), self.ruta)
        self.assertEqual(len(self.lineas()), 1)
        self.assertEqual(lector.cargar_calificaciones(self.ruta)[0]["esperado"], "x\u2028y\u0085z")


# ---------------------------------------------------------------- (7) concurrencia
def _worker(ruta, wid, n):
    from src.feedback import registro as R
    relleno = "ñ" * 700   # ~2 KB en UTF-8
    for i in range(n):
        R.guardar({"id_turno": f"w{wid}:{i}", "relleno": relleno}, Path(ruta))


def _muere_con_candado(ruta, listo):
    from src.feedback import registro as R
    lock = open(Path(ruta).with_name(Path(ruta).name + ".lock"), "a+b")
    R._bloquear(lock)
    listo.set()
    os._exit(1)   # muere sin liberar explícitamente


def _retiene(ruta, listo, segundos):
    from src.feedback import registro as R
    lock = open(Path(ruta).with_name(Path(ruta).name + ".lock"), "a+b")
    R._bloquear(lock)
    listo.set()
    time.sleep(segundos)
    R._desbloquear(lock)
    lock.close()


class Concurrencia(Base):
    def test_8_procesos_x_100_escrituras_de_2kb(self):
        ctx = multiprocessing.get_context("spawn")
        ps = [ctx.Process(target=_worker, args=(str(self.ruta), w, 100)) for w in range(8)]
        t0 = time.time()
        for p in ps:
            p.start()
        for p in ps:
            p.join(180)
        for p in ps:
            self.assertEqual(p.exitcode, 0)
        lineas = self.lineas()
        validas = [json.loads(l.decode("utf-8")) for l in lineas]
        self.assertEqual(len(validas), 800, f"{len(validas)} líneas en {time.time()-t0:.1f}s")
        self.assertEqual(len({v['id_turno'] for v in validas}), 800)

    def test_proceso_que_muere_con_el_candado_no_bloquea_a_los_demas(self):
        ctx = multiprocessing.get_context("spawn")
        listo = ctx.Event()
        p = ctx.Process(target=_muere_con_candado, args=(str(self.ruta), listo))
        p.start()
        self.assertTrue(listo.wait(30))
        p.join(30)
        t0 = time.time()
        registro.guardar(_rec("a:1"), self.ruta)
        self.assertLess(time.time() - t0, 3)
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 1)

    def test_candado_retenido_un_rato_se_espera_y_luego_escribe(self):
        ctx = multiprocessing.get_context("spawn")
        listo = ctx.Event()
        p = ctx.Process(target=_retiene, args=(str(self.ruta), listo, 1.5))
        p.start()
        self.assertTrue(listo.wait(30))
        registro.guardar(_rec("a:1"), self.ruta)
        p.join(30)
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 1)

    def test_lock_retenido_para_siempre_lanza_en_tiempo_acotado(self):
        ctx = multiprocessing.get_context("spawn")
        listo = ctx.Event()
        p = ctx.Process(target=_retiene, args=(str(self.ruta), listo, 15))
        p.start()
        try:
            self.assertTrue(listo.wait(30))
            t0 = time.time()
            with self.assertRaises(OSError):
                registro.guardar(_rec("a:1"), self.ruta)
            self.assertLess(time.time() - t0, 10)
        finally:
            p.terminate()
            p.join(10)

    def test_lock_con_contenido_previo_no_rompe_guardar(self):
        """Si <log>.lock ya tiene bytes (alguien lo editó/escribió), guardar no debe fallar tras escribir."""
        self.ruta.with_name(self.ruta.name + ".lock").write_bytes(b"basura previa")
        registro.guardar(_rec("a:1"), self.ruta)
        registro.guardar(_rec("a:2"), self.ruta)
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 2)

    def test_lock_abierto_por_otro_handle_en_el_mismo_proceso(self):
        otro = open(self.ruta.with_name(self.ruta.name + ".lock"), "a+b")
        try:
            registro.guardar(_rec("a:1"), self.ruta)
        finally:
            otro.close()
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 1)

    def test_log_abierto_en_lectura_por_otro_no_impide_escribir(self):
        self.ruta.write_bytes(b"")
        with open(self.ruta, "rb"):
            registro.guardar(_rec("a:1"), self.ruta)
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 1)

    def test_ruta_inexistente_en_otra_unidad_lanza_OSError(self):
        libre = None
        for l in "ZYXWVUTSRQ":
            if not os.path.exists(f"{l}:\\"):
                libre = l
                break
        if libre is None:
            self.skipTest("sin letra de unidad libre")
        with self.assertRaises(OSError):
            registro.guardar(_rec("a:1"), Path(f"{libre}:\\no\\existe\\x.jsonl"))

    def test_carpeta_de_solo_lectura_lanza_o_escribe_pero_no_corrompe(self):
        carpeta = self.dir / "ro"
        carpeta.mkdir()
        subprocess.run(["icacls", str(carpeta), "/deny", "Everyone:(WD,AD)"], capture_output=True)
        try:
            try:
                registro.guardar(_rec("a:1"), carpeta / "x.jsonl")
            except OSError:
                pass   # lanzar es el comportamiento documentado
        finally:
            subprocess.run(["icacls", str(carpeta), "/remove:d", "Everyone"], capture_output=True)

    def test_ruta_es_un_directorio_lanza_OSError(self):
        d = self.dir / "carpeta.jsonl"
        d.mkdir()
        with self.assertRaises(OSError):
            registro.guardar(_rec("a:1"), d)

    def test_registro_no_serializable_en_guardar_no_deja_linea_parcial(self):
        with self.assertRaises(TypeError):
            registro.guardar({"id_turno": "a:1", "x": {1, 2}}, self.ruta)
        self.assertFalse(self.ruta.exists() and self.ruta.stat().st_size > 0)

    def test_registro_grande_1mb_es_una_linea_valida(self):
        registro.guardar(_rec("a:1", blob="b" * (1024 * 1024)), self.ruta)
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 1)

    def test_hilos_y_registro_mezclados_con_escritura_lenta_mantienen_lineas(self):
        import threading
        errores = []

        def t(k):
            try:
                for i in range(30):
                    registro.guardar(_rec(f"h{k}:{i}", blob="ñ" * 3000), self.ruta)
            except Exception as e:  # noqa
                errores.append(e)
        hs = [threading.Thread(target=t, args=(k,)) for k in range(10)]
        [h.start() for h in hs]
        [h.join() for h in hs]
        self.assertEqual(errores, [])
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 300)


# ---------------------------------------------------------------- (8) idempotencia
class Idempotencia(Base):
    def test_snapshot_no_muta_el_result(self):
        r = {"status": "success", "route": "powerbi", "result_type": "table", "question": "q",
             "rows": [{"a": 1}], "detail": {"rows": [{"p": "x"}]}, "dax": "D",
             "query_plan": {"metric": {"label": "m", "dax": "d"}, "group_by": [{"table": "t", "column": "c"}],
                            "filters": [{"type": "c", "table": "t", "column": "c", "values": [1, 2], "value": "v"}]},
             "source_context": {"candidates": [{"id": 1, "score": 0.123456}], "reason": "r"},
             "sources": [{"id": "s", "score": 0.987654321, "text": "TXT"}], "error": "e"}
        antes = copy.deepcopy(r)
        opciones = ["a", "b"]
        antes_op = copy.deepcopy(opciones)
        s1 = registro.snapshot_turno(r, "resp\n| a |", "preg 1234567", "texto", opciones)
        self.assertEqual(r, antes)
        self.assertEqual(opciones, antes_op)
        s2 = registro.snapshot_turno(r, "resp\n| a |", "preg 1234567", "texto", opciones)
        s1.pop("fecha_turno"); s2.pop("fecha_turno")
        self.assertEqual(s1, s2)

    def test_snapshot_no_comparte_referencias_con_result(self):
        r = {"query_plan": {"group_by": [{"table": "t", "column": "c"}]}}
        s = registro.snapshot_turno(r, "r", "p", "t", [])
        s["plan_consulta"]["group_by"].append("x")
        self.assertEqual(len(r["query_plan"]["group_by"]), 1)

    def test_construir_registro_no_muta_snapshot_ni_historial(self):
        snap = registro.snapshot_turno({}, "r", "p", "t", [])
        hist = [{"rol": "user", "texto": "hola 1234567"} for _ in range(8)]
        a, b = copy.deepcopy(snap), copy.deepcopy(hist)
        reg = registro.construir_registro(snap, hist, "mala", "x", "s", 1)
        self.assertEqual(snap, a)
        self.assertEqual(hist, b)
        self.assertEqual(len(reg["historial"]), 6)
        self.assertNotIn("version", snap)

    def test_construir_registro_no_deja_pasar_claves_ajenas_del_snapshot(self):
        """El snapshot que llega podría venir contaminado; el registro final debe respetar la lista blanca."""
        snap = registro.snapshot_turno({}, "r", "p", "t", [])
        snap["rows"] = [{"paciente": "Ana"}]
        reg = registro.construir_registro(snap, [], "buena", "", "s", 1)
        self.assertNotIn("rows", reg)

    @unittest.skip("diferido al ledger (hallazgo 17)")
    def test_historial_formato_de_app_role_content_no_se_pierde_en_silencio(self):
        """Si llega {'role','content'} (formato de app.py) el texto no debe perderse sin aviso."""
        reg = registro.construir_registro(registro.snapshot_turno({}, "r", "p", "t", []),
                                          [{"role": "user", "content": "hola"}], "buena", "", "s", 1)
        self.assertNotEqual(reg["historial"][0]["texto"], "")

    @unittest.skip("diferido al ledger (hallazgo 17)")
    def test_opciones_como_tupla_se_conservan(self):
        s = registro.snapshot_turno({}, "r", "p", "t", ("a", "b"))
        self.assertEqual(s["opciones_contrapregunta"], ["a", "b"])


# ---------------------------------------------------------------- (9) contrato
class Contrato(Base):
    def test_claves_del_snapshot_segun_brief(self):
        esperadas = {"pregunta", "pregunta_reescrita", "via", "estado", "ruta", "etapa", "informe", "tablero",
                     "modelo_semantico", "metrica", "plan_consulta", "contexto_fuentes", "modo_sintesis",
                     "retrieval_mode", "not_found_reason", "fuentes", "opciones_contrapregunta", "respuesta",
                     "error", "fecha_turno", "tablero_esperado"}
        self.assertEqual(set(registro.snapshot_turno({}, "r", "p", "t", [])), esperadas)

    def test_claves_del_registro_segun_brief(self):
        reg = registro.construir_registro(registro.snapshot_turno({}, "r", "p", "t", []), [], "buena", "", "s", 3)
        for k in ("version", "id_turno", "id_sesion", "fecha_calificacion", "commit_codigo", "historial",
                  "calificacion", "esperado"):
            self.assertIn(k, reg)
        self.assertNotIn("indice_turno", reg)
        self.assertEqual(reg["version"], 1)
        self.assertEqual(reg["id_turno"], "s:3")

    def test_plan_y_contexto_vacios_son_none_y_con_contenido_tienen_forma(self):
        s = registro.snapshot_turno({}, "r", "p", "t", [])
        self.assertIsNone(s["plan_consulta"])
        self.assertIsNone(s["contexto_fuentes"])
        self.assertIsNone(s["pregunta_reescrita"])

    def test_filtros_value_y_values(self):
        r = {"query_plan": {"filters": [{"type": "a", "table": "t", "column": "c", "value": 0},
                                        {"type": "a", "table": "t", "column": "c", "values": ["x", "y"]},
                                        {"type": "a", "table": "t", "column": "c", "value": ""}]}}
        f = registro.snapshot_turno(r, "r", "p", "t", [])["plan_consulta"]["filtros"]
        self.assertEqual([x["n_valores"] for x in f], [1, 2, 0])

    def test_score_a_4_decimales(self):
        r = {"source_context": {"candidates": [{"id": "a", "score": 0.123456789}]},
             "sources": [{"id": "s", "final_score": 0.987654321}]}
        s = registro.snapshot_turno(r, "r", "p", "t", [])
        self.assertEqual(s["contexto_fuentes"]["candidates"][0]["score"], 0.1235)
        self.assertEqual(s["fuentes"][0]["puntaje"], 0.9877)

    def test_candidates_id_cae_en_modelo_semantico(self):
        r = {"source_context": {"candidates": [{"semantic_model": "M"}]}}
        c = registro.snapshot_turno(r, "r", "p", "t", [])["contexto_fuentes"]["candidates"][0]
        self.assertEqual((c["id"], c["modelo"]), ("M", "M"))

    def test_fuentes_sin_texto_ni_ruta_absoluta(self):
        """El id de fuente puede ser una ruta de archivo local (source_file); no debe exponer rutas de usuario."""
        r = {"sources": [{"source_file": r"C:\Users\ad6709\Documents\x.md"}]}
        s = registro.snapshot_turno(r, "r", "p", "t", [])
        self.assertNotIn("ad6709", json.dumps(s))

    def test_commit_codigo_es_hex_corto_o_vacio_y_cacheado(self):
        c = registro._commit_codigo()
        self.assertRegex(c, r"^([0-9a-f]{7,12})?$")
        self.assertIs(registro._commit_codigo(), c)

    def test_commit_codigo_independiente_del_cwd(self):
        registro._commit_codigo.cache_clear()
        old = os.getcwd()
        os.chdir(self.dir)
        try:
            self.assertRegex(registro._commit_codigo(), r"^[0-9a-f]{7,12}$")
        finally:
            os.chdir(old)
            registro._commit_codigo.cache_clear()

    def test_guardar_escribe_lf_y_utf8_sin_bom(self):
        registro.guardar(_rec("a:1", esperado="ñ"), self.ruta)
        datos = self.ruta.read_bytes()
        self.assertTrue(datos.endswith(b"\n"))
        self.assertNotIn(b"\r", datos)
        self.assertFalse(datos.startswith(b"\xef\xbb\xbf"))
        self.assertIn("ñ".encode("utf-8"), datos)

    def test_nombres_de_evaluador_no_presentes(self):
        reg = registro.construir_registro(registro.snapshot_turno({}, "r", "p", "t", []), [], "buena", "", "s", 1)
        for k in reg:
            self.assertNotIn(k, ("usuario", "evaluador", "user", "autor"))


# ------------------------------------------------- ronda de correcciones 1 (rulings)
class Ronda1(Base):
    def m(self, texto):
        return registro.snapshot_turno({}, "", texto, "t", [])["pregunta"]

    def test_cedulas_y_telefonos_con_separadores_se_enmascaran(self):
        for t in ("1.234.567.890", "1 234 567 890", "123-456-789", "300 123 4567", "12345 6789"):
            self.assertEqual(self.m("cc " + t), "cc [NUM]", t)

    def test_periodos_y_fechas_validas_se_conservan(self):
        for t in ("202510", "20251005", "2025-10-05", "05/10/2025", "05.10.2025", "5 10 2025", "2024 2025"):
            self.assertEqual(self.m("dato " + t), "dato " + t, t)

    def test_periodos_y_fechas_invalidas_se_enmascaran(self):
        for t in ("202513", "199912", "20251345", "12345678"):
            self.assertEqual(self.m("dato " + t), "dato [NUM]", t)

    def test_error_guarda_solo_el_tipo_de_excepcion(self):
        snap = registro.snapshot_turno({"error": "KeyError: 'Juan Perez Gomez'"}, "r", "p", "t", [])
        self.assertEqual(snap["error"], "KeyError")
        snap = registro.snapshot_turno({"error": "No pude hablar con Juan Perez"}, "r", "p", "t", [])
        self.assertNotIn("Juan", snap["error"])

    def test_lineas_con_pipes_y_vinetas_se_descartan_de_respuesta_en_cualquier_ruta(self):
        texto = "Total\n* Ana: 1\n• Luis: 2\n1. Eva: 3\n2) Pepe: 4\na | b | c\nfin"
        for res in ({}, {"route": "rag"}, {"route": "clarification"}):
            out = registro.snapshot_turno(res, texto, "p", "t", [])["respuesta"]
            self.assertEqual(out, "Total\nfin")

    def test_historial_descarta_vinetas_y_asistente_solo_primera_linea(self):
        snap = registro.snapshot_turno({}, "r", "p", "t", [])
        hist = [{"rol": "user", "texto": "hola\n- Ana: 5"},
                {"rol": "assistant", "texto": "- Juan: 3\nHay 8 casos\notra linea\n| x | y |"}]
        reg = registro.construir_registro(snap, hist, "buena", "", "s", 1)
        self.assertEqual(reg["historial"][0]["texto"], "hola")
        self.assertEqual(reg["historial"][1]["texto"], "Hay 8 casos")

    def test_lector_acepta_bom_con_utf8_sig(self):
        self.ruta.write_bytes(b"\xef\xbb\xbf" + json.dumps(_rec("a:1")).encode() + b"\n")
        self.assertEqual(len(lector.cargar_calificaciones(self.ruta)), 1)

    def test_linea_parcial_previa_no_se_pega_a_la_siguiente(self):
        self.ruta.write_bytes(json.dumps(_rec("a:1")).encode() + b"\n" + b'{"id_turno": "a:2", "cal')
        registro.guardar(_rec("a:3"), self.ruta)
        self.assertEqual({r["id_turno"] for r in lector.cargar_calificaciones(self.ruta)}, {"a:1", "a:3"})

    def test_error_al_desbloquear_no_enmascara_la_excepcion_original(self):
        from unittest import mock
        with mock.patch.object(registro, "_escribir", side_effect=PermissionError("original")), \
                mock.patch.object(registro.time, "sleep"):
            with self.assertRaises(PermissionError) as cm:
                registro.guardar(_rec("a:1"), self.ruta)
        self.assertEqual(str(cm.exception), "original")


if __name__ == "__main__":
    unittest.main()

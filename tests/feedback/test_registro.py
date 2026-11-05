"""
Pruebas del registro y el lector de calificaciones (src/feedback).

Ejecutar:
  python -m unittest tests.feedback.test_registro
"""
import json
import multiprocessing
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from src.feedback import lector, registro


def _result_powerbi():
    return {
        "status": "success", "route": "powerbi", "result_type": "scalar", "stage": "query_plan_result",
        "question": "cuantas cirugias plasticas hubo", "report": "Cirugia", "dashboard": "Cirugias",
        "semantic_model": "Modelo_Cirugia", "metric": "Cirugias realizadas", "value": 55,
        "rows": [{"paciente": "Ana Perez", "cedula": "1234567890"}],
        "dax": "EVALUATE ROW(\"x\", 1)", "powerbi": {"raw": 1}, "reasoning": "porque si",
        "detail": {"rows": [{"paciente": "Juan"}]},
        "filters": [{"type": "categorical", "table": "T", "column": "ESPECIALIDAD",
                     "values": ["CIRUGIA PLASTICA SECRETA"], "value": "CIRUGIA PLASTICA SECRETA"}],
        "group_by": [{"table": "T", "column": "MES"}],
        "query_plan": {
            "metric": {"label": "Cirugias realizadas", "metric_id": "m1", "dax": "SECRETO_DAX"},
            "report": "Cirugia", "semantic_model": "Modelo_Cirugia", "mode": "scalar",
            "group_by": [{"table": "T", "column": "MES"}],
            "filters": [{"type": "categorical", "table": "T", "column": "ESPECIALIDAD",
                         "values": ["CIRUGIA PLASTICA SECRETA", "OTRA"]}],
            "contexts": ["ctx secreto"],
        },
        "source_context": {
            "semantic_model": "Modelo_Cirugia", "routing_strength": "strong", "reason": "metric_match",
            "status": "resolved", "domain": "dominio secreto",
            "candidates": [{"id": "c1", "semantic_model": "Modelo_Cirugia", "dashboard": "Cirugias",
                            "score": 0.123456789, "contexts": ["x"]}],
        },
    }


class SnapshotTests(unittest.TestCase):
    def test_snapshot_sin_filas_de_tabla(self):
        snap = registro.snapshot_turno({}, "Total 5\n| paciente | x |\n| Ana | 1 |", "p", "texto", [])
        self.assertNotIn("|", snap["respuesta"])

    def test_snapshot_recorta_a_1500(self):
        snap = registro.snapshot_turno({}, "a" * 5000, "p", "texto", [])
        self.assertEqual(len(snap["respuesta"]), 1500)

    def test_snapshot_descarta_claves_de_filas_y_texto_de_chunks(self):
        result = {"route": "rag", "status": "success", "rows": [{"k": "SECRETO_FILA"}],
                  "sources": [{"id": "s1", "collection": "col", "dashboard": "D", "chunk_type": "ct",
                               "score": 0.9, "text": "TEXTO_DE_CHUNK_SECRETO"}]}
        snap = registro.snapshot_turno(result, "r", "p", "texto", [])
        dump = json.dumps(snap, ensure_ascii=False)
        self.assertNotIn("SECRETO_FILA", dump)
        self.assertNotIn("TEXTO_DE_CHUNK_SECRETO", dump)
        self.assertEqual(snap["fuentes"][0]["tipo_chunk"], "ct")
        self.assertEqual(snap["fuentes"][0]["tablero"], "D")

    def test_lista_blanca_no_copia_dax_value_detail_ni_valores_de_filtros(self):
        snap = registro.snapshot_turno(_result_powerbi(), "Hay 55", "p", "texto", [])
        dump = json.dumps(snap, ensure_ascii=False)
        for secreto in ("EVALUATE", "SECRETO_DAX", "Juan", "Ana Perez", "porque si",
                        "CIRUGIA PLASTICA SECRETA", "ctx secreto", "dominio secreto", "OTRA"):
            self.assertNotIn(secreto, dump)
        flt = snap["plan_consulta"]["filtros"][0]
        self.assertEqual(flt, {"tipo": "categorical", "tabla": "T", "columna": "ESPECIALIDAD", "n_valores": 2})

    def test_candidates_y_pregunta_reescrita_presentes(self):
        snap = registro.snapshot_turno(_result_powerbi(), "Hay 55", "cuantas cirugias", "texto", ["a"])
        self.assertEqual(snap["pregunta_reescrita"], "cuantas cirugias plasticas hubo")
        cand = snap["contexto_fuentes"]["candidates"][0]
        self.assertEqual(cand, {"id": "c1", "modelo": "Modelo_Cirugia", "tablero": "Cirugias", "score": 0.1235})
        self.assertEqual(snap["opciones_contrapregunta"], ["a"])
        self.assertIsNone(snap["tablero_esperado"])
        self.assertEqual(snap["metrica"], "Cirugias realizadas")

    def test_result_vacio_o_con_none_no_falla(self):
        for result in ({}, None, {"source_context": None, "sources": None, "query_plan": None,
                                  "filters": None, "error": None}):
            snap = registro.snapshot_turno(result, "r", "p", "texto", [])
            self.assertEqual(snap["fuentes"], [])
            self.assertIsNone(snap["ruta"])

    def test_numeros_largos_se_enmascaran(self):
        snap = registro.snapshot_turno({}, "r", "cedula 1234567890 aqui", "texto", [])
        self.assertIn("[NUM]", snap["pregunta"])
        self.assertNotIn("1234567890", snap["pregunta"])
        reg = registro.construir_registro(snap, [], "mala", "esperaba 1234567890", "s", 1)
        self.assertIn("[NUM]", reg["esperado"])
        self.assertNotIn("1234567890", reg["esperado"])

    def test_respuesta_tabla_powerbi_solo_primera_linea(self):
        result = {"route": "powerbi", "result_type": "table"}
        snap = registro.snapshot_turno(result, ("x" * 600) + "\nsegunda linea", "p", "texto", [])
        self.assertEqual(len(snap["respuesta"]), 400)
        self.assertNotIn("segunda", snap["respuesta"])

    def test_error_recortado_a_200(self):
        snap = registro.snapshot_turno({"error": "e" * 500}, "r", "p", "texto", [])
        self.assertEqual(len(snap["error"]), 200)


class RegistroTests(unittest.TestCase):
    def _snap(self):
        return registro.snapshot_turno({"route": "rag"}, "r", "p", "texto", [])

    def test_mala_sin_esperado_rechazada(self):
        for esperado in ("", "   \n"):
            with mock.patch.object(registro, "guardar") as guardar:
                with self.assertRaises(ValueError):
                    registro.construir_registro(self._snap(), [], "mala", esperado, "s", 1)
                guardar.assert_not_called()

    def test_calificacion_invalida_rechazada(self):
        with self.assertRaises(ValueError):
            registro.construir_registro(self._snap(), [], "regular", "", "s", 1)

    def test_historial_ultimos_6(self):
        historial = [{"rol": "user", "texto": f"m{i}", "extra": "x"} for i in range(10)]
        reg = registro.construir_registro(self._snap(), historial, "buena", "", "s", 3)
        self.assertEqual([h["texto"] for h in reg["historial"]], [f"m{i}" for i in range(4, 10)])
        self.assertEqual(set(reg["historial"][0]), {"rol", "texto"})
        self.assertEqual(reg["version"], 1)
        self.assertEqual(reg["id_turno"], "s:3")
        self.assertNotIn("indice_turno", reg)


class EscrituraTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"FEEDBACK_DIR": os.path.join(self.tmp.name, "sub", "fb")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _reg(self, id_turno, calificacion="buena", esperado=""):
        return {"id_turno": id_turno, "calificacion": calificacion, "esperado": esperado}

    def test_ruta_por_defecto_y_feedback_dir(self):
        self.assertEqual(registro.ruta_log(), Path(self.tmp.name) / "sub" / "fb" / "calificaciones.jsonl")
        with mock.patch.dict(os.environ):
            os.environ.pop("FEEDBACK_DIR")
            self.assertEqual(registro.ruta_log().parts[-3:], ("data", "feedback", "calificaciones.jsonl"))

    def test_guardar_crea_carpeta_y_lector_devuelve_ultima(self):
        registro.guardar(self._reg("s:1", "buena"))
        registro.guardar(self._reg("s:1", "mala", "algo"))
        registro.guardar(self._reg("s:2", "buena"))
        datos = lector.cargar_calificaciones()
        self.assertEqual(len(datos), 2)
        self.assertEqual({d["id_turno"]: d["calificacion"] for d in datos}, {"s:1": "mala", "s:2": "buena"})
        self.assertNotIn(b"\r\n", registro.ruta_log().read_bytes())

    def test_lector_sin_archivo(self):
        self.assertEqual(lector.cargar_calificaciones(), [])

    def test_lector_omite_linea_corrupta(self):
        registro.guardar(self._reg("s:1"))
        with open(registro.ruta_log(), "ab") as f:
            f.write(b'{"id_turno": "roto\n\n[1,2]\n')
        registro.guardar(self._reg("s:2"))
        self.assertEqual(len(lector.cargar_calificaciones()), 2)

    def test_escritura_concurrente_20_hilos_20_lineas_validas(self):
        hilos = [threading.Thread(target=registro.guardar, args=(self._reg(f"h:{i}", esperado="ñ" * 500),))
                 for i in range(20)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        lineas = registro.ruta_log().read_bytes().decode("utf-8").splitlines()
        self.assertEqual(len(lineas), 20)
        self.assertEqual(len({json.loads(l)["id_turno"] for l in lineas}), 20)

    def test_escritura_concurrente_4_procesos_x_50_todas_validas(self):
        ctx = multiprocessing.get_context("spawn")
        procs = [ctx.Process(target=_escribir_en_proceso, args=(os.environ["FEEDBACK_DIR"], p, 50))
                 for p in range(4)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(120)
            self.assertEqual(p.exitcode, 0)
        lineas = registro.ruta_log().read_bytes().decode("utf-8").splitlines()
        self.assertEqual(len(lineas), 200)
        self.assertEqual(len({json.loads(l)["id_turno"] for l in lineas}), 200)


def _escribir_en_proceso(carpeta, proceso, cantidad):
    os.environ["FEEDBACK_DIR"] = carpeta
    from src.feedback import registro as reg
    for i in range(cantidad):
        reg.guardar({"id_turno": f"p{proceso}:{i}", "calificacion": "buena", "esperado": "x" * 300})


if __name__ == "__main__":
    unittest.main()

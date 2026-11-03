"""
Pruebas OFFLINE de los bancos nuevos y de la regresión real (sin Power BI ni
MedGemma): banco holdout 2 (estructura, mezcla y similitud), banco
multiturno (estructura, corrida con un runner falso y resumen) y
regresion_real (resumen versionable, clasificación y código de salida).

    python -X utf8 -m tests.real.test_bancos
"""
import importlib
import json
import re
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.real import run_banco, run_multiturno, similitud  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA_TIPOS = run_banco.DATA_TIPOS
QUINCE = {"BRIEFING HOSPITALARIO", "TABLERO TIEMPOS URGENCIAS", "TABLERO DE ATENCIONES INSTITUCIONALES",
          "ASIGNACION DE CITAS", "TABLERO EPS", "TABLERO_FARMACIA", "Tablero Control Facturacion",
          "Demanda Insatisfecha", "TABLERO_ANTIBIOTICOS", "Tablero_lavanderia", "TABLERO NAOS",
          "TABLERO RECEPCION TECNICA", "TABLERO_REFERENCIA", "TABLERO_CVC", "TABLERO PERFIL DE MORBILIDAD"}


def _bank(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def regresion():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return importlib.import_module("regresion_real")


class Placeholders(unittest.TestCase):
    def test_todo_marcador_de_periodo_se_conoce(self):
        known = set(run_banco.period_values())
        for name in ("banco_real.json", "banco_holdout.json", "banco_holdout2.json", "banco_multiturno.json"):
            data = _bank(name)
            daxes = [c["verdad"]["dax"] for c in data.get("casos", []) if c.get("verdad")]
            daxes += [t["verdad"]["dax"] for c in data.get("conversaciones", []) for t in c["turnos"] if t.get("verdad")]
            for dax in daxes:
                for key in re.findall(r"\{([A-Z_]+)\}", dax):
                    self.assertIn(key, known, f"{name}: {{{key}}}")
                self.assertFalse(re.search(r"\{[A-Z_]+\}", run_banco.fill(dax)), name)

    def test_mes_antepasado_y_semana_pasada(self):
        from datetime import date
        p = run_banco.period_values(date(2026, 1, 15))   # jueves
        self.assertEqual((p["INI_MES_ANTEPASADO"], p["FIN_MES_ANTEPASADO"]), (date(2025, 11, 1), date(2025, 11, 30)))
        self.assertEqual((p["INI_SEMANA_PASADA"], p["FIN_SEMANA_PASADA"]), (date(2026, 1, 5), date(2026, 1, 11)))
        self.assertIn("DATE(2025, 11, 1)", run_banco.fill("{INI_MES_ANTEPASADO}", date(2026, 1, 15)))
        # «{INI_SEMANA}» no se come el prefijo de «{INI_SEMANA_PASADA}»
        self.assertEqual(run_banco.fill("{INI_SEMANA_PASADA}", date(2026, 1, 15)), "DATE(2026, 1, 5)")


class Holdout2(unittest.TestCase):
    def setUp(self):
        self.h2 = _bank("banco_holdout2.json")["casos"]
        self.h1 = _bank("banco_holdout.json")["casos"]

    def test_estructura(self):
        self.assertEqual(len(self.h2), 50)
        ids = [c["id"] for c in self.h2]
        self.assertEqual(len(ids), len(set(ids)))
        for c in self.h2:
            self.assertTrue(c.get("criterio"), c["id"])
            if c["tipo"] in DATA_TIPOS:
                self.assertTrue(c["verdad"]["dax"].startswith("EVALUATE"), c["id"])
                self.assertEqual(c["verdad"]["modelo"], c["tablero"], c["id"])
            elif c["tipo"] in ("definicion", "fuera_alcance"):
                self.assertTrue(c.get("esperado"), c["id"])

    def test_misma_mezcla_que_el_holdout(self):
        self.assertEqual({c["tablero"] for c in self.h2}, QUINCE)
        self.assertEqual({c["tipo"] for c in self.h2}, {c["tipo"] for c in self.h1})
        a, b = Counter(c["tablero"] for c in self.h1), Counter(c["tablero"] for c in self.h2)
        for board in QUINCE:
            self.assertLessEqual(abs(a[board] - b[board]), 2, board)
        ta, tb = Counter(c["tipo"] for c in self.h1), Counter(c["tipo"] for c in self.h2)
        for tipo in ta:
            self.assertLessEqual(abs(ta[tipo] - tb[tipo]), 3, tipo)

    def test_pbip_incompletos_marcados_en_criterio(self):
        incompletos = {"TABLERO_REFERENCIA", "TABLERO_CVC", "TABLERO PERFIL DE MORBILIDAD",
                       "TABLERO DE ATENCIONES INSTITUCIONALES"}
        for c in self.h2:
            if c["tablero"] in incompletos and c["tipo"] in DATA_TIPOS:
                self.assertIn("PBIP local incompleto", c["criterio"], c["id"])


class Similitud(unittest.TestCase):
    def test_holdout2_no_repite_ni_parafrasea(self):
        hits = similitud.check(HERE / "banco_holdout2.json")
        self.assertEqual(hits, [], "\n".join(f"{h['id']} ~ {h['otro']}: {h['pregunta']} ~ {h['otra']}" for h in hits))

    def test_calibracion(self):
        par = [("cuantos egresos hubo ayer", "cuántos egresos hubo el día de ayer?"),
               ("cuantas camas disponibles hay ahorita", "cuantas camas hay disponibles ahora"),
               ("cuantos kilos de ropa se lavaron el mes pasado", "kilos d ropa lavados el mes pasado"),
               ("citas en espera por especialidad", "citas en espera x especialidad")]
        for a, b in par:
            self.assertTrue(similitud.parecida(a, b)[0], (a, b, similitud.scores(a, b)))
        distintas = [("cuantas camas hay en transicion ahorita?", "hay camas bloqueadas? cuantas son"),
                     ("cuantos egresos hubo ayer", "cuanto se facturo el mes pasado"),
                     ("q antibioticos se estan usando ahorita", "dosis de antibiotico aplicadas en las ucis")]
        for a, b in distintas:
            self.assertFalse(similitud.parecida(a, b)[0], (a, b, similitud.scores(a, b)))

    def test_detecta_una_parafrasis_inyectada(self):
        data = _bank("banco_holdout2.json")
        data["casos"].append({"id": "GX", "tablero": "TABLERO EPS", "tipo": "numero",
                              "pregunta": "cuantos triages atendidos hay en el tablero de eps?"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "banco_x.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            hits = similitud.check(path, others=[HERE / "banco_real.json", HERE / "banco_holdout.json"])
        self.assertEqual([h["id"] for h in hits], ["GX"])
        self.assertTrue(hits[0]["otro"].endswith(":EP02"))


class Multiturno(unittest.TestCase):
    def setUp(self):
        self.convs = _bank("banco_multiturno.json")["conversaciones"]

    def test_estructura(self):
        self.assertTrue(20 <= len(self.convs) <= 30)
        self.assertEqual({c["categoria"] for c in self.convs},
                         {"periodo", "agrupacion", "filtro", "indicador", "pronombre", "correccion", "clic"})
        for c in self.convs:
            self.assertTrue(2 <= len(c["turnos"]) <= 4, c["id"])
            self.assertEqual([t["n"] for t in c["turnos"]], list(range(1, len(c["turnos"]) + 1)), c["id"])
            for t in c["turnos"]:
                self.assertIn(t["tipo"], DATA_TIPOS, c["id"])
                self.assertTrue(t["verdad"]["dax"].startswith("EVALUATE"), (c["id"], t["n"]))
                self.assertTrue(t["entrada"].strip(), (c["id"], t["n"]))
        clic = [c for c in self.convs if c["categoria"] == "clic"]
        self.assertTrue(all(c["turnos"][0]["contrapregunta_aceptable"] and c["turnos"][0]["elegir"] for c in clic))

    def test_seguimientos_son_cortos(self):
        """Los seguimientos dependen del contexto: no repiten la pregunta completa."""
        for c in self.convs:
            for t in c["turnos"][1:]:
                self.assertLess(len(t["entrada"]), len(c["turnos"][0]["entrada"]) + 25, (c["id"], t["n"]))


def _turn(answer, status="success", model="BRIEFING HOSPITALARIO", dax=(), buttons=(), value=None, error=None):
    return {"via": "texto", "text": "¿?", "answer": answer, "status": status, "route": "powerbi",
            "semantic_model": model, "value": value, "error": error,
            "dax": [{"semantic_model": model, "status": "success", "row_count": 1, "dax": d} for d in dax],
            "buttons": [{"id": str(i), "label": b, "caption": None} for i, b in enumerate(buttons, 1)], "seconds": 1.0}


class FakeRunReal:
    """Sustituto de run_real: guion de respuestas por texto; registra clics."""

    def __init__(self, script):
        self.script = script
        self.log = []

    def new_conversation(self):
        self.log.append("nueva")

    def ask(self, text):
        self.log.append(("texto", text))
        t = self.script[text]
        return t, t["buttons"]

    def choose(self, option_id, label):
        self.log.append(("clic", label))
        t = self.script["clic:" + label]
        return t, t["buttons"]

    @staticmethod
    def pick_button(buttons, spec):
        from tests.real.run_real import pick_button
        return pick_button(buttons, spec)


CONV = {"id": "MTX", "categoria": "clic", "tablero": "BRIEFING HOSPITALARIO", "descripcion": "x", "turnos": [
    {"n": 1, "entrada": "cuantos egresos hubo ayer", "tablero": "BRIEFING HOSPITALARIO", "tipo": "numero",
     "elegir": "BRIEFING", "contrapregunta_aceptable": True,
     "verdad": {"modelo": "BRIEFING HOSPITALARIO", "dax": 'EVALUATE ROW("v", DISTINCTCOUNT(EGRESOS[INGRESO]))',
                "tolerancia": 0.0, "unidad": "", "porcentaje": False, "pagina": "INGRESOS Y EGRESOS"}},
    {"n": 2, "entrada": "¿y antier?", "tablero": "BRIEFING HOSPITALARIO", "tipo": "numero", "elegir": None,
     "contrapregunta_aceptable": False,
     "verdad": {"modelo": "BRIEFING HOSPITALARIO", "dax": 'EVALUATE ROW("v", DISTINCTCOUNT(EGRESOS[INGRESO]))',
                "tolerancia": 0.0, "unidad": "", "porcentaje": False, "pagina": "INGRESOS Y EGRESOS"}}]}


class CorridaMultiturno(unittest.TestCase):
    def test_clic_y_evaluacion_por_turno(self):
        fake = FakeRunReal({
            "cuantos egresos hubo ayer": _turn("¿Cuál?", status="needs_clarification",
                                               buttons=("TABLERO DE ATENCIONES", "BRIEFING HOSPITALARIO")),
            "clic:BRIEFING HOSPITALARIO": _turn("Egresos ayer: **48**", dax=["DISTINCTCOUNT(EGRESOS[INGRESO])"]),
            "¿y antier?": _turn("Egresos antier: **50**", dax=["DISTINCTCOUNT(EGRESOS[INGRESO])"]),
        })
        truths = iter([{"valor": 48}, {"valor": 51}])
        original = run_banco.compute_truths
        run_banco.compute_truths = lambda verdad, today=None: next(truths)
        try:
            turns = run_multiturno.run_conversation(CONV, fake)
        finally:
            run_banco.compute_truths = original
        self.assertEqual(fake.log, ["nueva", ("texto", "cuantos egresos hubo ayer"), ("clic", "BRIEFING HOSPITALARIO"),
                                    ("texto", "¿y antier?")])
        self.assertEqual(turns[0]["turnos"][-1]["eleccion"]["modo"], "elegir")
        self.assertEqual([run_multiturno.turn_ok(t) for t in turns], [True, False])
        self.assertIs(run_multiturno.conv_ok(turns), False)
        s = run_multiturno.summarize([{"id": "MTX", "categoria": "clic", "turnos": turns}])
        self.assertEqual((s["turnos"]["aciertos"], s["turnos"]["evaluados"]), (1, 2))
        self.assertEqual(s["por_posicion"]["1"]["aciertos"], 1)
        self.assertEqual(s["seguimientos_con_turno_previo_correcto"]["evaluados"], 1)
        self.assertEqual(s["conversaciones"]["aciertos"], 0)
        self.assertEqual(s["por_categoria"]["clic"]["conversaciones"]["evaluados"], 1)

    def test_conversacion_inconclusa_y_resumen_md(self):
        t_ok = {"n": 1, "id": "A.1", "entrada": "x", "eval": {"correcto": True, "fallas": [], "detalle": {}},
                "turnos": [_turn("1")], "segundos": 1}
        t_na = {"n": 2, "id": "A.2", "entrada": "y", "eval": {"correcto": None, "fallas": [], "detalle": {}},
                "turnos": [_turn("2")], "segundos": 1}
        self.assertIsNone(run_multiturno.conv_ok([t_ok, t_na]))
        results = [{"id": "A", "categoria": "periodo", "correcto": None, "turnos": [t_ok, t_na]}]
        with tempfile.TemporaryDirectory() as tmp:
            s = run_multiturno.write_summary(tmp, results, {"modo": "prueba"})
            text = (Path(tmp) / "resumen.md").read_text(encoding="utf-8")
        self.assertEqual(s["inconclusas"], ["A"])
        self.assertIn("Seguimientos con el turno anterior correcto", text)


class Regresion(unittest.TestCase):
    """regresion_real con resultados.json sintéticos y una línea base temporal."""

    TRUTH_DAX = ('EVALUATE ROW("v", CALCULATE(DISTINCTCOUNT(PENDIENTES_FARMACIA[HCNFOLIO]),\n'
                 '    KEEPFILTERS(FILTER(ALL(PENDIENTES_FARMACIA[FECHA_CIERRE]), ISBLANK(PENDIENTES_FARMACIA[FECHA_CIERRE])))))')

    def setUp(self):
        self.rr = regresion()
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.saved = (self.rr.BANCOS, self.rr.LINEA_BASE, self.rr.OUT)
        banco = {"casos": [
            {"id": "A1", "tablero": "TABLERO_FARMACIA", "tipo": "numero", "pregunta": "suministros pendientes",
             "contrapregunta_aceptable": False,
             "verdad": {"modelo": "TABLERO_FARMACIA", "dax": self.TRUTH_DAX, "tolerancia": 0.0}},
            {"id": "A2", "tablero": "TABLERO_FARMACIA", "tipo": "numero", "pregunta": "productos bajo minimo",
             "contrapregunta_aceptable": False,
             "verdad": {"modelo": "TABLERO_FARMACIA", "dax": 'EVALUATE ROW("v", DISTINCTCOUNT(CANTIDAD_MINIMA[CODIGO]))',
                        "tolerancia": 0.0}},
            {"id": "A3", "tablero": "TABLERO_FARMACIA", "tipo": "numero", "pregunta": "vencidos",
             "contrapregunta_aceptable": False,
             "verdad": {"modelo": "TABLERO_FARMACIA", "dax": 'EVALUATE ROW("v", SUM(PRODUCTOS_VENCIDOS[iddcantid]))',
                        "tolerancia": 0.0}},
            {"id": "A4", "tablero": "TABLERO_FARMACIA", "tipo": "numero", "pregunta": "otro",
             "contrapregunta_aceptable": False,
             "verdad": {"modelo": "TABLERO_FARMACIA", "dax": 'EVALUATE ROW("v", COUNT(X[Y]))', "tolerancia": 0.0}},
        ]}
        (tmp / "banco_x.json").write_text(json.dumps(banco), encoding="utf-8")
        self.rr.BANCOS = {"desarrollo": tmp / "banco_x.json"}
        self.rr.LINEA_BASE = tmp / "linea_base"
        self.rr.OUT = tmp / "out"
        self.run_dir = tmp / "corrida"
        (self.run_dir / "desarrollo").mkdir(parents=True)
        self.bot_same = ('EVALUATE ROW("v", CALCULATE(DISTINCTCOUNT(\'PENDIENTES_FARMACIA\'[HCNFOLIO]), '
                         'FILTER(ALL(PENDIENTES_FARMACIA[FECHA_CIERRE]), ISBLANK(PENDIENTES_FARMACIA[FECHA_CIERRE]))))')

    def tearDown(self):
        self.rr.BANCOS, self.rr.LINEA_BASE, self.rr.OUT = self.saved
        self.tmp.cleanup()

    def _write(self, rows):
        res = [{"id": cid, "tablero": "TABLERO_FARMACIA", "tipo": "numero", "pregunta": cid, "verdad": truth,
                "turnos": turns, "eval": {"correcto": None, "fallas": [], "detalle": {}}, "segundos": 1}
               for cid, truth, turns in rows]
        (self.run_dir / "desarrollo" / "resultados.json").write_text(
            json.dumps({"meta": {"fecha": "x", "commit": "abc"}, "resultados": res}), encoding="utf-8")

    def _all_ok(self):
        m = "TABLERO_FARMACIA"
        self._write([
            ("A1", {"valor": 278}, [_turn("**278** pendientes", model=m, dax=[self.bot_same], value=278)]),
            ("A2", {"valor": 10}, [_turn("**10** productos", model=m, dax=["DISTINCTCOUNT(CANTIDAD_MINIMA[CODIGO])"])]),
            ("A3", {"valor": 5}, [_turn("**5** unidades", model=m, dax=["SUM(PRODUCTOS_VENCIDOS[iddcantid])"])]),
            ("A4", {"valor": 7}, [_turn("**3**", model=m, dax=["COUNT(X[Y])"])]),
        ])

    def test_aceptar_guarda_solo_el_resumen(self):
        self._all_ok()
        code = self.rr.main(["--bancos", "desarrollo", "--reusar", str(self.run_dir), "--aceptar"])
        self.assertEqual(code, 0)
        base = json.loads((self.rr.LINEA_BASE / "desarrollo.json").read_text(encoding="utf-8"))
        self.assertEqual(base["resumen"], {"aciertos": 3, "evaluados": 4})
        for c in base["casos"]:
            self.assertLessEqual(set(c), {"id", "correcto", "fallas", "cifra", "nivel"})
        text = json.dumps(base, ensure_ascii=False)
        self.assertNotIn("pendientes", text)       # nada de respuestas
        self.assertNotIn("DISTINCTCOUNT", text)    # ni DAX
        self.assertEqual(base["casos"][0]["cifra"], {"verdad": 278.0, "bot": 278.0})

    def test_regresion_dato_en_vivo_red_y_mejora(self):
        self._all_ok()
        self.rr.main(["--bancos", "desarrollo", "--reusar", str(self.run_dir), "--aceptar"])
        m = "TABLERO_FARMACIA"
        self._write([
            # misma consulta que la verdad, la cifra se movió entre las dos consultas (FM01)
            ("A1", {"valor": 281}, [_turn("**278** pendientes", model=m, dax=[self.bot_same], value=278)]),
            # otra consulta: regresión
            ("A2", {"valor": 10}, [_turn("**12** productos", model=m,
                                         dax=["CALCULATE(DISTINCTCOUNT(CANTIDAD_MINIMA[CODIGO]), ALMACENES[X] = \"Y\")"])]),
            # error de red en la verdad
            ("A3", {"error": "HTTPSConnectionPool: Read timed out"}, [_turn("**5** unidades", model=m)]),
            # fallaba y ahora acierta
            ("A4", {"valor": 3}, [_turn("**3**", model=m, dax=["COUNT(X[Y])"])]),
        ])
        code = self.rr.main(["--bancos", "desarrollo", "--reusar", str(self.run_dir)])
        self.assertEqual(code, 1)
        text = (self.run_dir / "REGRESION.md").read_text(encoding="utf-8")
        self.assertIn("## Regresiones", text)
        actual, detalle = self.rr.resumen_banco("desarrollo", self.run_dir / "desarrollo" / "resultados.json")
        estados = {x["id"]: x["estado"] for x in self.rr.comparar(self.rr.load_base("desarrollo"), actual, detalle)}
        self.assertEqual(estados, {"A1": "dato_en_vivo", "A2": "regresion", "A3": "red", "A4": "mejora"})
        self.assertTrue((self.rr.OUT / "REGRESION.md").exists())

    def test_sin_regresiones_sale_cero_y_todo_red_sale_dos(self):
        self._all_ok()
        self.rr.main(["--bancos", "desarrollo", "--reusar", str(self.run_dir), "--aceptar"])
        self.assertEqual(self.rr.main(["--bancos", "desarrollo", "--reusar", str(self.run_dir)]), 0)
        err = {"error": "ConnectionError: Max retries exceeded"}
        self._write([(cid, err, [_turn(None, status="error", error="ConnectionError: Max retries exceeded")])
                     for cid in ("A1", "A2", "A3", "A4")])
        self.assertEqual(self.rr.main(["--bancos", "desarrollo", "--reusar", str(self.run_dir)]), 2)

    def test_firma_dax(self):
        refs, lits = self.rr.dax_firma("EVALUATE ROW(\"v\", CALCULATE([%OCUPACION], 'SERVICIOS'[HSUNOMBRE] = \"UCI\", "
                                       "Calendario[FECHA] >= DATE(2026, 10, 1)))")
        self.assertEqual(refs, {"[%ocupacion]", "servicios[hsunombre]", "calendario[fecha]"})
        self.assertEqual(lits, {"uci", "2026-10-1"})


class RegresionMultiturno(unittest.TestCase):
    def test_resumen_por_turno_y_conversacion(self):
        rr = regresion()
        conv = json.loads(json.dumps(CONV))
        turns = [{"id": "MTX.1", "n": 1, "entrada": "a", "tipo": "numero", "verdad": {"valor": 48},
                  "turnos": [_turn("**48**", dax=["DISTINCTCOUNT(EGRESOS[INGRESO])"])], "segundos": 1,
                  "eval": {"correcto": None, "fallas": []}},
                 {"id": "MTX.2", "n": 2, "entrada": "b", "tipo": "numero", "verdad": {"valor": 51},
                  "turnos": [_turn("**50**", dax=["DISTINCTCOUNT(EGRESOS[INGRESO])"])], "segundos": 1,
                  "eval": {"correcto": None, "fallas": []}}]
        with tempfile.TemporaryDirectory() as tmp:
            bank = Path(tmp) / "banco_mt.json"
            bank.write_text(json.dumps({"conversaciones": [conv]}), encoding="utf-8")
            res = Path(tmp) / "resultados.json"
            res.write_text(json.dumps({"meta": {}, "resultados": [{"id": "MTX", "categoria": "clic", "turnos": turns}]}),
                           encoding="utf-8")
            saved = dict(rr.BANCOS)
            rr.BANCOS["multiturno"] = bank
            try:
                actual, _ = rr.resumen_banco("multiturno", res)
            finally:
                rr.BANCOS.clear()
                rr.BANCOS.update(saved)
        by = {c["id"]: c for c in actual["casos"]}
        self.assertEqual((by["MTX.1"]["correcto"], by["MTX.2"]["correcto"], by["MTX"]["correcto"]), (True, False, False))
        self.assertEqual(by["MTX"]["nivel"], "conversacion")
        self.assertEqual(actual["resumen"], {"aciertos": 1, "evaluados": 2,
                                             "conversaciones": {"aciertos": 0, "evaluadas": 1}})


if __name__ == "__main__":
    unittest.main(verbosity=1)

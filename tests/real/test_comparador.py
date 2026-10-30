"""
Pruebas OFFLINE del comparador del banco real (sin Power BI ni MedGemma):
respuestas de ejemplo → veredicto.

    python -m tests.real.test_comparador
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.real import auditoria, correr_todo, run_banco  # noqa: E402

BRIEF = "BRIEFING HOSPITALARIO"
ATEN = "TABLERO DE ATENCIONES INSTITUCIONALES"
EPS = "TABLERO EPS"


def case(cid="X01", tipo="numero", dax='EVALUATE ROW("v", DISTINCTCOUNT(T[ID]))', modelo=BRIEF, **kw):
    verdad = {"modelo": modelo, "dax": dax, "tolerancia": kw.pop("tol", 0.0), "unidad": kw.pop("unidad", ""),
              "porcentaje": kw.pop("porcentaje", False), "pagina": kw.pop("pagina", "INICIO")}
    for key in ("alternativas", "lista_alternativa", "cobertura_minima", "top_keys"):
        if key in kw:
            verdad[key] = kw.pop(key)
    item = {"id": cid, "tablero": modelo, "tipo": tipo, "pregunta": "¿?", "verdad": verdad,
            "elegir": kw.pop("elegir", None), "contrapregunta_aceptable": kw.pop("contrapregunta_ok", False)}
    item.update(kw)
    return item


def turn(answer, status="success", route="powerbi", model=BRIEF, dax=(), via="texto", buttons=(), eleccion=None,
         seconds=1.0):
    return {"via": via, "text": "¿?", "answer": answer, "status": status, "route": route, "semantic_model": model,
            "dax": [{"semantic_model": model, "status": "success", "row_count": 1, "dax": d} if isinstance(d, str)
                    else d for d in dax],
            "buttons": [{"id": str(i), "label": b, "caption": None} for i, b in enumerate(buttons, 1)],
            "eleccion": eleccion, "seconds": seconds}


def clarification(*labels):
    return turn("¿Cuál de estos indicadores?", status="needs_clarification", route="clarification", model=None,
                buttons=labels)


class Numeros(unittest.TestCase):
    def test_cifra_en_formato_espanol(self):
        ev = run_banco.evaluate(case(), [turn("Hay **1.442** consultas", dax=["ROW(DISTINCTCOUNT(T[ID]))"])],
                                {"valor": 1442})
        self.assertIs(ev["correcto"], True)
        self.assertEqual(ev["fallas"], [])

    def test_porcentaje(self):
        c = case(dax='EVALUATE ROW("v", [%OCUPACION])', unidad="%", porcentaje=True, tol=0.01)
        ev = run_banco.evaluate(c, [turn("Ocupación: **92,1 %**", dax=["ROW([%OCUPACION])"])], {"valor": 0.921})
        self.assertIs(ev["correcto"], True)

    def test_millones(self):
        c = case(dax='EVALUATE ROW("v", SUM(U[FACTURADO]))', tol=0.01)
        ev = run_banco.evaluate(c, [turn("Facturado: $ 12,5 millones", dax=["SUM(U[FACTURADO])"])],
                                {"valor": 12_500_000})
        self.assertIs(ev["correcto"], True)

    def test_sin_datos_cuando_la_verdad_es_vacia(self):
        ev = run_banco.evaluate(case(), [turn("No hay datos para esos filtros.")], {"valor": None})
        self.assertIs(ev["correcto"], True)


class Clasificacion(unittest.TestCase):
    def test_indicador_sin_calculate(self):
        """BH08: la verdad no tiene CALCULATE; el bot usó otra columna → indicador (antes salía «filtro»)."""
        c = case(dax="EVALUATE ROW(\"v\", DISTINCTCOUNT('EGRESOS PROBABLES'[AINCONSEC]))")
        t = turn("**EGRESOS EFECTIVOS HOY**: **11**",
                 dax=["EVALUATE ROW(\"__value\", SUM('EGRESOS PROBABLES'[EGRESO_EFECTIVO_HOY]))"])
        ev = run_banco.evaluate(c, [t], {"valor": 263})
        self.assertIs(ev["correcto"], False)
        self.assertEqual(ev["fallas"], ["indicador"])

    def test_filtro_con_el_indicador_correcto(self):
        """FM01: misma medida, sin el filtro del visual → filtro."""
        c = case(dax="EVALUATE ROW(\"v\", CALCULATE(DISTINCTCOUNT(P[HCNFOLIO]),\n"
                     "    KEEPFILTERS(FILTER(ALL('P'[FECHA_CIERRE]), ISBLANK('P'[FECHA_CIERRE])))))")
        t = turn("**2.439 suministros**", dax=["EVALUATE ROW(\"__value\", DISTINCTCOUNT('P'[HCNFOLIO]))"])
        ev = run_banco.evaluate(c, [t], {"valor": 278})
        self.assertEqual(ev["fallas"], ["filtro"])
        res = {"id": "FM01", "tablero": BRIEF, "turnos": [t], "eval": ev}
        self.assertEqual(auditoria.causa_raiz(c, res), ["1"])

    def test_filtro_espurio_es_causa_2(self):
        c = case(dax="EVALUATE ROW(\"v\", CALCULATE(SUM(A[TOTAL]),\n"
                     "    KEEPFILTERS(FILTER(ALL(A[FECHA]), A[FECHA] >= {INI_MES_PASADO} && A[FECHA] <= {FIN_MES_PASADO}))))")
        t = turn("**ATENCIONES** con asegurador SALUD TOTAL: **392**",
                 dax=["EVALUATE ROW(\"__value\", CALCULATE(SUM('A'[TOTAL]), TREATAS({\"SALUD TOTAL\"}, 'A'[ASEGURADOR]),"
                      " FILTER(ALL('A'[FECHA]), 'A'[FECHA] >= DATE(2026, 9, 1))))"])
        ev = run_banco.evaluate(c, [t], {"valor": 5000})
        self.assertEqual(ev["fallas"], ["filtro"])
        self.assertEqual(auditoria.causa_raiz(c, {"turnos": [t], "eval": ev}), ["2"])

    def test_sin_datos_con_medida_en_linea_es_filtro(self):
        """AI04: verdad = [TOTAL_TRIAGES]; el bot escribió la expresión y filtró por otra fecha → filtro, causa 3."""
        c = case(dax='EVALUATE ROW("v", CALCULATE([TOTAL_TRIAGES], '
                     "KEEPFILTERS(FILTER(ALL('Calendario'[Date]), 'Calendario'[Date] >= {INI_ANO_PASADO}))))",
                 modelo=ATEN)
        t = turn("No hay datos para esos filtros.", status="empty_result", model=ATEN,
                 dax=["EVALUATE ROW(\"__value\", CALCULATE(DISTINCTCOUNT('TRIAGES'[OID_TRIAGE]), "
                      "FILTER(ALL('CONSULTAS PRIORITARIAS'[FECHA]), 'CONSULTAS PRIORITARIAS'[FECHA] >= DATE(2025,1,1))))"])
        ev = run_banco.evaluate(c, [t], {"valor": 60000})
        self.assertEqual(ev["fallas"], ["filtro"])
        self.assertEqual(auditoria.causa_raiz(c, {"turnos": [t], "eval": ev}), ["3"])

    def test_rag_en_pregunta_de_datos_es_indicador(self):
        """FM03: respuesta de RAG con cifras de la documentación → indicador/enrutamiento, no «inventada»."""
        t = turn("Los medicamentos que vencen en 0 o 1 mes… 30-120 días.", route="rag", model=None)
        ev = run_banco.evaluate(case(), [t], {"valor": 69})
        self.assertEqual(ev["fallas"], ["indicador"])
        self.assertEqual(ev["detalle"]["enrutamiento"], "rag")
        self.assertEqual(auditoria.causa_raiz(case(), {"turnos": [t], "eval": ev}), ["6"])

    def test_cifra_sin_fuente_es_inventada(self):
        t = turn("Hay 120 pacientes.", route="llm", model=None)
        ev = run_banco.evaluate(case(), [t], {"valor": 69})
        self.assertEqual(ev["fallas"], ["inventada"])

    def test_modelo_distinto_es_indicador(self):
        t = turn("**CAMAS**: 300", model=ATEN, dax=["ROW(DISTINCTCOUNT(T[ID]))"])
        ev = run_banco.evaluate(case(), [t], {"valor": 410})
        self.assertEqual(ev["fallas"], ["indicador"])

    def test_agrupacion_ignorada(self):
        c = case(tipo="agrupado", dax='EVALUATE SUMMARIZECOLUMNS(I[ESPECIALIDAD], "v", SUM(I[SOLICITUDES]))',
                 top_keys=2)
        t = turn("Interconsultas de ayer: **41**", dax=["ROW(SUM(I[SOLICITUDES]))"])
        truth = {"grupos": [{"clave": "MEDICINA INTERNA", "valor": 20}, {"clave": "CIRUGIA", "valor": 21}]}
        ev = run_banco.evaluate(c, [t], truth)
        self.assertEqual(ev["fallas"], ["agrupacion"])


class Expresion(unittest.TestCase):
    def test_nucleo_de_la_verdad(self):
        f = run_banco.truth_core_expr
        self.assertEqual(f("EVALUATE ROW(\"v\", DISTINCTCOUNT('E P'[AINCONSEC]))"), "DISTINCTCOUNT('E P'[AINCONSEC])")
        self.assertEqual(f('EVALUATE ROW("v", CALCULATE([%OCUPACION],\n KEEPFILTERS(FILTER(ALL(X[a]), X[a] IN {1, 2}))))'),
                         "[%OCUPACION]")
        self.assertEqual(f('EVALUATE TOPN(5, SUMMARIZECOLUMNS(U[T], KEEPFILTERS(FILTER(ALL(U[a]), U[a] = "x,y")), '
                           '"v", SUM(U[F])), [v], DESC)'), "SUM(U[F])")
        self.assertEqual(f('EVALUATE CALCULATETABLE(VALUES(S[NOM]), KEEPFILTERS(FILTER(ALL(S[H]), S[H] IN {"a,b"})))'),
                         "VALUES(S[NOM])")
        self.assertEqual(f('EVALUATE ROW("agosto", CALCULATE(AVERAGE(O[MIN]), F), "mes_pasado", CALCULATE(AVERAGE(O[MIN]), G))'),
                         "AVERAGE(O[MIN])")


class Alternativas(unittest.TestCase):
    def test_alternativa_con_su_propio_modelo(self):
        """AI05: la tarjeta del TABLERO EPS responde la pregunta tal como está → acierto."""
        c = case(dax='EVALUATE ROW("v", [Total_consultas_urgencias])', modelo=ATEN, tol=0.01,
                 alternativas=[{"modelo": EPS, "dax": 'EVALUATE ROW("v", COUNT(CONSULTA_URGENCIAS[OID_TRIAGE]))'}])
        t = turn("**Consultas urgencias** (mes pasado): **1.442**", model=EPS,
                 dax=["ROW(DISTINCTCOUNT('CONSULTA_URGENCIAS'[OID_TRIAGE]))"])
        truth = {"valor": 1729, "alternativas": [{"valor": 1442, "modelo": EPS}]}
        ev = run_banco.evaluate(c, [t], truth)
        self.assertIs(ev["correcto"], True)
        # si la cifra no coincide, el modelo del bot es el de una alternativa → no es «indicador»
        ev = run_banco.evaluate(c, [t], {"valor": 1729, "alternativas": [{"valor": 1500, "modelo": EPS}]})
        self.assertEqual(ev["fallas"], ["filtro"])

    def test_compute_truths_usa_el_modelo_de_cada_alternativa(self):
        calls = []
        original = run_banco.real_env.dax

        def fake(query, model, max_rows=60):
            calls.append(model)
            return [{"[v]": 10 if model == ATEN else 7}]

        run_banco.real_env.dax = fake
        try:
            truth = run_banco.compute_truths({"modelo": ATEN, "dax": "EVALUATE ROW(\"v\", 1)",
                                              "alternativas": [{"modelo": EPS, "dax": "EVALUATE ROW(\"v\", 2)"},
                                                               "EVALUATE ROW(\"v\", 3)"]})
        finally:
            run_banco.real_env.dax = original
        self.assertEqual(calls, [ATEN, EPS, ATEN])
        self.assertEqual(truth["valor"], 10)
        self.assertEqual([a["valor"] for a in truth["alternativas"]], [7, 10])
        self.assertEqual(truth["alternativas"][0]["modelo"], EPS)

    def test_lista_de_otra_dimension_real(self):
        """BH05: lista de ULT_GESTION[AREA_SERVICIO] (≥ 5 valores, DAX exitoso) → acierto."""
        c = case(tipo="lista", dax="EVALUATE VALUES(SERVICIOS[NOM_SERV])", cobertura_minima=0.5,
                 lista_alternativa={"columnas": ["serv", "area"], "minimo": 5})
        answer = "Power BI registra 6 áreas:\n\n- CARDIOLOGIA\n- CIRUGIA\n- ECOGRAFIA\n- PATOLOGIA\n- RAYOS X\n- URGENCIAS"
        t = turn(answer, model="Tablero Control Facturacion",
                 dax=[{"status": "success", "row_count": 34, "semantic_model": "Tablero Control Facturacion",
                       "dax": "EVALUATE VALUES('ULT_GESTION'[AREA_SERVICIO])"}])
        truth = {"lista": ["CUARTO PISO NORTE", "QUINTO PISO SUR", "SEXTO PISO", "URGENCIAS"]}
        ev = run_banco.evaluate(c, [t], truth)
        self.assertIs(ev["correcto"], True)
        self.assertTrue(ev["detalle"]["lista_alternativa"])
        # una dimensión que no es de servicios/áreas no vale
        t["dax"][0]["dax"] = "EVALUATE VALUES('ULT_GESTION'[TERNOMCOM])"
        self.assertIs(run_banco.evaluate(c, [t], truth)["correcto"], False)


class Contrapreguntas(unittest.TestCase):
    def test_innecesaria_falla_aunque_la_cifra_sea_correcta(self):
        turns = [clarification("A", "B"), turn("**12**", via="botón", dax=["ROW(DISTINCTCOUNT(T[ID]))"],
                                                eleccion={"modo": "elegir"})]
        ev = run_banco.evaluate(case(), turns, {"valor": 12})
        self.assertIs(ev["correcto"], True)
        self.assertIn("contrapregunta", ev["fallas"])
        self.assertEqual(auditoria.auto_verdict({"eval": ev}), "falla")

    def test_legitima_no_penaliza(self):
        turns = [clarification("A", "B"), turn("**12**", via="botón", dax=["ROW(DISTINCTCOUNT(T[ID]))"],
                                                eleccion={"modo": "elegir"})]
        ev = run_banco.evaluate(case(contrapregunta_ok=True), turns, {"valor": 12})
        self.assertEqual(ev["fallas"], [])
        self.assertEqual(auditoria.auto_verdict({"eval": ev}), "acierto")

    def test_eleccion_por_defecto_con_contrapregunta_legitima_es_inconclusa(self):
        turns = [clarification("A", "B"), turn("**99**", via="botón", dax=["ROW(DISTINCTCOUNT(T[ID]))"],
                                                eleccion={"modo": "defecto"})]
        ev = run_banco.evaluate(case(contrapregunta_ok=True), turns, {"valor": 12})
        self.assertIsNone(ev["correcto"])
        self.assertIn("inconcluso", ev["detalle"])
        self.assertEqual(auditoria.auto_verdict({"eval": ev}), "inconcluso")

    def test_eleccion_por_defecto_con_contrapregunta_innecesaria_falla_solo_por_ella(self):
        turns = [clarification("A", "B"), turn("**99**", via="botón", dax=["ROW(SUM(T[OTRA]))"],
                                                eleccion={"modo": "defecto"})]
        ev = run_banco.evaluate(case(), turns, {"valor": 12})
        self.assertIs(ev["correcto"], False)
        self.assertEqual(ev["fallas"], ["contrapregunta"])

    def test_choose_button_registra_el_modo(self):
        from tests.real.run_real import pick_button
        buttons = [{"id": "1", "label": "EGRESOS", "caption": "Cuenta ingresos · BRIEFING HOSPITALARIO"},
                   {"id": "2", "label": "Total Egresos", "caption": "· TABLERO DE ATENCIONES INSTITUCIONALES"},
                   {"id": "__none__", "label": "Ninguna de las anteriores", "caption": None}]
        b, how = run_banco.choose_button(case(elegir="Total Egresos"), buttons, pick_button)
        self.assertEqual((b["id"], how["modo"]), ("2", "elegir"))
        b, how = run_banco.choose_button(case(elegir="BRIEFING"), buttons, pick_button)   # por la descripción
        self.assertEqual((b["id"], how["modo"]), ("1", "elegir"))
        b, how = run_banco.choose_button(case(modelo=ATEN), buttons, pick_button)
        self.assertEqual((b["id"], how["modo"]), ("2", "modelo"))
        b, how = run_banco.choose_button(case(modelo="OTRO", pagina="X"), buttons, pick_button)
        self.assertEqual((b["id"], how["modo"]), ("1", "defecto"))


class Auditoria(unittest.TestCase):
    def _result(self, cid, answer, correct, fallas=(), tablero=BRIEF):
        return {"id": cid, "tablero": tablero, "turnos": [turn(answer)],
                "eval": {"correcto": correct, "fallas": list(fallas), "detalle": {}}}

    def test_veredicto_auditado_solo_si_la_respuesta_es_la_misma(self):
        audit = {"casos": {"X01": {"veredicto": "acierto", "fallas": [], "causas": [],
                                   "huella": auditoria.huella("Respuesta auditada: 68")}}}
        same = self._result("X01", "Respuesta auditada: 68", False, ["filtro"])
        other = self._result("X01", "Otra respuesta: 70", False, ["filtro"])
        self.assertEqual(auditoria.verdict(same, audit)["veredicto"], "acierto")
        self.assertEqual(auditoria.verdict(same, audit)["fuente"], "auditado")
        v = auditoria.verdict(other, audit, case())
        self.assertEqual((v["veredicto"], v["fuente"]), ("falla", "automático"))

    def test_contrapregunta_auditada_no_se_hereda_si_ya_no_se_pregunta(self):
        # TU08: se auditó «cifra correcta tras una contrapregunta innecesaria»;
        # si la corrida nueva responde directo con el mismo texto, vale el automático.
        answer = "**IMAGENES TOMADAS** en septiembre: **851**"
        audit = {"casos": {"T08": {"veredicto": "falla", "fallas": ["contrapregunta"], "causas": ["4"],
                                   "huella": auditoria.huella(answer)}}}
        direct = self._result("T08", answer, True)
        v = auditoria.verdict(direct, audit, case())
        self.assertEqual((v["veredicto"], v["fuente"]), ("acierto", "automático"))
        asked = {**direct, "turnos": [turn("¿Cuál?", status="needs_clarification", buttons=["A", "B"]),
                                      turn(answer, via="botón")]}
        v = auditoria.verdict(asked, audit, case())
        self.assertEqual((v["veredicto"], v["fuente"]), ("falla", "auditado"))

    def test_resumen_por_tablero_y_causa(self):
        audit = {"casos": {"A": {"veredicto": "falla", "fallas": ["filtro"], "causas": ["1"], "huella": auditoria.huella("a")},
                           "C": {"veredicto": "inconcluso", "huella": auditoria.huella("c")}}}
        results = [self._result("A", "a", True), self._result("B", "b", True, tablero=ATEN),
                   self._result("C", "c", False)]
        s = auditoria.summarize(results, audit)
        self.assertEqual((s["aciertos"], s["evaluados"]), (1, 2))
        self.assertEqual(s["por_tablero"][BRIEF], {"aciertos": 0, "evaluados": 1})
        self.assertEqual(s["por_causa"], {"1": ["A"]})
        self.assertEqual(s["inconclusos"], ["C"])

    def test_auditoria_json_es_coherente(self):
        data = auditoria.load()
        casos = data["casos"]
        self.assertEqual(len(casos), 71)
        self.assertTrue(all(c["veredicto"] in auditoria.VEREDICTOS for c in casos.values()))
        ok = sum(c["veredicto"] == "acierto" for c in casos.values())
        ev = sum(c["veredicto"] in ("acierto", "falla") for c in casos.values())
        self.assertEqual((ok, ev), (26, 67))  # AC02 reauditado en r3: contrapregunta legítima
        for cid, c in casos.items():
            if c["veredicto"] == "falla":
                self.assertTrue(c["causas"], cid)
                self.assertTrue(set(c["causas"]) <= set(auditoria.CAUSAS), cid)
        banco = {c["id"] for c in json.loads(run_banco.BANCO.read_text(encoding="utf-8"))["casos"]}
        self.assertEqual(set(casos), banco)


class Informe(unittest.TestCase):
    def test_informe_con_comparacion(self):
        c = case("X01")
        cases = {"X01": c, "X02": case("X02")}
        good = turn("**12**", dax=["ROW(DISTINCTCOUNT(T[ID]))"])
        bad = turn("**99**", dax=["ROW(DISTINCTCOUNT(T[ID]))"])

        def res(cid, t, truth):
            return {"id": cid, "tablero": BRIEF, "tipo": "numero", "pregunta": "¿?", "verdad": truth, "turnos": [t],
                    "segundos": 1.0, "eval": run_banco.evaluate(cases[cid], [t], truth)}

        with tempfile.TemporaryDirectory() as tmp:
            prev = [res("X01", bad, {"valor": 12}), res("X02", good, {"valor": 12})]
            correr_todo.build_report({"commit": "antes"}, prev, cases, Path(tmp) / "antes",
                                     audit_path=Path(tmp) / "no_existe.json")
            cur = [res("X01", good, {"valor": 12}), res("X02", bad, {"valor": 12})]
            auto, audited = correr_todo.build_report({"commit": "ahora"}, cur, cases, Path(tmp) / "ahora",
                                                     audit_path=Path(tmp) / "no_existe.json",
                                                     comparar=Path(tmp) / "antes" / "resultado.json")
            text = (Path(tmp) / "ahora" / "INFORME.md").read_text(encoding="utf-8")
        self.assertEqual((audited["aciertos"], audited["evaluados"]), (1, 2))
        for needle in ("## Tasas", "**Auditada**", "## Por tablero", "## Por causa raíz",
                       "## Comparación con la corrida anterior", "| X01 | no (1) | sí | MEJORA |",
                       "| X02 | sí | no (1) | EMPEORA |"):
            self.assertIn(needle, text)

    def test_reevaluar_la_corrida_base(self):
        """Si están las salidas de db2f1af, la tasa auditada reproduce 26/67 (25 + AC02 reauditado en r3)."""
        base = Path(r"C:\Users\ad6708\Documents\banco_real_out_base_db2f1af\resultado.json")
        if not base.exists():
            self.skipTest("no están las salidas de la corrida base")
        cases = {c["id"]: c for c in json.loads(run_banco.BANCO.read_text(encoding="utf-8"))["casos"]}
        _, _, results = auditoria.load_previous(base, cases)
        s = auditoria.summarize(results, auditoria.load(), cases)
        self.assertEqual((s["aciertos"], s["evaluados"], s["auditados"]), (26, 67, 71))


if __name__ == "__main__":
    unittest.main(verbosity=1)

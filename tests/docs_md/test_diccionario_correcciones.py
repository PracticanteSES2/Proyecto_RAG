"""
Correcciones del diccionario y de la cobertura reportadas por los agentes de contenido.

    python -m unittest tests.docs_md.test_diccionario_correcciones

Sintéticas y offline, salvo `PbipRealesTest`, que se salta si no hay `tableros/`
(en un worktree: DOCS_MD_DATA_ROOT=<checkout principal>).
"""
import contextlib
import copy
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.docs_md import diccionario as D
from src.docs_md import formato as F
from src.docs_md import repositorio as R
from src.docs_md.uso import uso_de_campos
from tests.docs_md import diccionario_fixture as X
from tests.docs_md.test_docs_tableros import posible_pii

FECHA = "2026-10-28"


def _pagina_md(pagina: str, cuerpo: dict, meta_extra: dict | None = None, proposito: str = "Página de prueba.",
               tablas=None) -> str:
    meta = {"tablero": X.TABLERO, "pagina": pagina, "nombre_funcional": pagina.title(), "bloque": "Día",
            "tablas": tablas or ["PACIENTES"], "actualizado": "2026-10-20", "version": 1}
    meta.update(meta_extra or {})
    doc = F.Documento(meta=meta, titulo=pagina, proposito=proposito)
    for seccion, entradas in cuerpo.items():
        doc.secciones[seccion] = [F.Entrada(n, t) for n, t in entradas]
    doc.secciones[F.SECCION_HISTORIAL] = [F.Entrada("2026-10-20 · v1", "Inicial.")]
    return F.serializar(doc)


def _visual(id_, tipo, campos, titulo=None):
    """campos: [(expresión, nombre visible)]."""
    return {"id": id_, "tipo": tipo, "titulo": titulo, "campos": [c for c, _ in campos],
            "campos_detalle": [{"rol": "Values", "expresion": c, "nombre": n} for c, n in campos],
            "filtros": [], "semaforo": [], "formato_condicional": [], "texto": None, "destino": None,
            "destino_id": None, "accion": None, "tablas": [], "oculto": False}


def _pagina(id_, nombre, visuales):
    return {"id": id_, "nombre": nombre, "visible": True, "orden": 1, "filtros": [], "obtener_detalles": [],
            "visuales": visuales}


def _modelo(columnas=None, medidas=None, tablas=None, relaciones=None, hechos=None) -> dict:
    return {"tablero": X.TABLERO, "modelo_nombre": X.TABLERO, "fuentes": [], "hechos": hechos,
            "tablas": {t: {"descripcion": "", "oculta": False, "modo": "Import", "dax": None} for t in (tablas or [])},
            "medidas": medidas or {}, "columnas": columnas or {}, "relaciones": relaciones or []}


def _col(tipo="texto", calculada=False, dax=None, resumen="", formato=""):
    return {"tipo_dato": tipo, "descripcion": "", "oculta": False, "calculada": calculada, "dax": dax,
            "resumen_por": resumen, "formato": formato}


def _medida(tabla="PACIENTES", dax="1", tipo="entero", formato=""):
    return {"tabla": tabla, "descripcion": "", "dax": dax, "formato": formato, "tipo_dato": tipo,
            "oculta": False, "carpeta": ""}


class _ConProyecto(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dic_fix_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.grupo, self.hechos = X.crear_proyecto(self.tmp)
        self.raiz = self.tmp / "docs_tableros"
        self.md = self.raiz / self.grupo / "md"

    def escribir_md(self, archivo, texto):
        (self.md / archivo).write_text(texto, encoding="utf-8")

    def cobertura(self, hechos=None):
        return D.cobertura(self.grupo, self.tmp, raiz_docs=self.raiz, hechos=hechos or self.hechos)

    def esqueleto(self, hechos=None):
        return D.generar_esqueleto(self.grupo, self.tmp, raiz_docs=self.raiz, hechos=hechos or self.hechos, fecha=FECHA)


# 1 ---------------------------------------------------------------------------
class RelacionBidireccionalTest(unittest.TestCase):
    def test_uno_a_uno_bidireccional_se_lista_una_vez(self):
        rel = lambda a, b: {"desde": a, "hacia": b, "activa": True, "ambos": True, "card_desde": "One", "card_hacia": "One"}
        modelo = _modelo(tablas=["PRODUCTOS_DESECHADOS", "ALMACENES"],
                         relaciones=[rel(("PRODUCTOS_DESECHADOS", "OID"), ("ALMACENES", "OID")),
                                     rel(("ALMACENES", "OID"), ("PRODUCTOS_DESECHADOS", "OID"))])
        plan = D.construir_plan(modelo)
        self.assertEqual([e.nombre for e in plan.secciones["Relaciones"]], ["PRODUCTOS_DESECHADOS[OID] → ALMACENES[OID]"])
        self.assertFalse(any(e.nombre.startswith("Nombre repetido") for e in plan.observaciones))
        # Una entrada escrita en el otro sentido cuenta como la misma relación (no queda obsoleta ni se duplica).
        self.assertEqual(D._clave_entrada("Relaciones", "ALMACENES[OID] → PRODUCTOS_DESECHADOS[OID]"),
                         D._clave_relacion(("PRODUCTOS_DESECHADOS", "OID"), ("ALMACENES", "OID")))


# 2 y 6 -------------------------------------------------------------------------
class CoberturaVisualesTest(_ConProyecto):
    def setUp(self):
        super().setUp()
        self.hechos["paginas"] = [_pagina("p1", "RESUMEN ", [  # nombre con espacio final
            _visual("v1", "slicer", [("Calendario[Date] (Año)", "Date Año")]),
            _visual("v2", "slicer", [("Calendario[Date] (Mes)", "Fecha Mes1")]),
            _visual("v3", "pivotTable", [("PACIENTES[FECHA_INGRESO] (Año)", "IDFECDOC Año"),
                                          ("PACIENTES[Total pacientes]", "Total pacientes")]),
            _visual("v4", "card", [("PACIENTES[Porcentaje activos]", "Porcentaje activos")], "PORCENTAJE ACTIVOS"),
        ])]

    def faltantes(self, cuerpo):
        self.escribir_md("resumen.md", _pagina_md("RESUMEN", cuerpo))
        c = self.cobertura()
        self.assertEqual(c["paginas"]["faltantes"], [], "«RESUMEN » empareja con «RESUMEN»")
        return c["visuales"]["faltantes"]

    def test_por_expresion_con_y_sin_nivel_de_jerarquia_y_por_titulo(self):
        # «Calendario[Date] (Año)» documenta también el segmentador de Mes (misma columna
        # sin el nivel); la matriz se reconoce por PACIENTES[FECHA_INGRESO] sin «(Año)».
        faltan = self.faltantes({"Visuales": [
            ("Filtros", "Segmentación de Calendario[Date] (Año)."),
            ("Matriz", "Filas PACIENTES[FECHA_INGRESO] por año.")]})
        self.assertEqual(faltan, ["RESUMEN › Tarjeta «PORCENTAJE ACTIVOS»"])
        faltan = self.faltantes({"Visuales": [("Tarjeta", "Titulada PORCENTAJE ACTIVOS.")]})
        self.assertNotIn("RESUMEN › Tarjeta «PORCENTAJE ACTIVOS»", faltan)
        self.assertIn("RESUMEN › Segmentación de Calendario[Date] (Mes)", faltan)

    def test_segmentador_de_fecha_si_la_pagina_documenta_la_columna(self):
        faltan = self.faltantes({
            "Fuentes de datos": [("Calendario", "Fechas; la columna Date alimenta los filtros de año y mes.")],
            "Visuales": [("Tarjeta", "PORCENTAJE ACTIVOS."), ("Matriz", "PACIENTES[FECHA_INGRESO] (Año).")]})
        self.assertEqual(faltan, [])

    def test_el_nombre_interno_ya_no_es_necesario_pero_sigue_valiendo(self):
        faltan = self.faltantes({"Visuales": [("Matriz", "IDFECDOC Año.")]})
        self.assertNotIn("RESUMEN › Matriz «IDFECDOC Año»", faltan)

    def test_uso_recorta_el_nombre_de_la_pagina(self):
        uso = uso_de_campos(self.hechos)
        self.assertEqual({u["pagina"] for u in uso["Calendario[Date]"]}, {"RESUMEN"})


# 3 ---------------------------------------------------------------------------
class TipoColumnaCalculadaTest(unittest.TestCase):
    def test_numerica_aunque_el_csv_diga_texto(self):
        self.assertEqual(D._tipo_columna_calculada(_col("texto", True, "IF(x,1,0)", resumen="Sum")), "número")
        self.assertEqual(D._tipo_columna_calculada(_col("texto", True, "A-B", formato="0")), "número")
        self.assertEqual(D._tipo_columna_calculada(_col("texto", True, 'IF(x,"SI","NO")', resumen="None")), "texto")
        self.assertEqual(D._tipo_columna_calculada(_col("entero", True, "1")), "entero")

    def test_en_el_esqueleto_y_con_dataType_del_tmdl(self):
        tmp = Path(tempfile.mkdtemp(prefix="dic_tipo_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        grupo, hechos = X.crear_proyecto(tmp)
        X._escribir(tmp / "data" / "model_metadata" / X.MODELO / "columns.csv", X._COLUMNAS, [
            X._columna("PACIENTES", "SERVICIO"),
            X._columna("PACIENTES", "FALTA", "String", True, "IF(PACIENTES[SERVICIO]<>\"\",1,0)", resumen="Sum"),
            X._columna("PACIENTES", "DIAS", "String", True, "PACIENTES[SERVICIO]"),
        ])
        hechos = copy.deepcopy(hechos)
        hechos["tablas"]["PACIENTES"]["columnas_detalle"] = [
            {"nombre": "DIAS", "tipo": "int64", "calculada": True, "resumen_por": "sum"}]
        doc = D.generar_esqueleto(grupo, tmp, raiz_docs=tmp / "docs_tableros", hechos=hechos, fecha=FECHA)
        self.assertIn("Tipo: número.", doc.buscar("Columnas calculadas", "PACIENTES[FALTA]").texto)
        self.assertIn("Tipo: entero.", doc.buscar("Columnas calculadas", "PACIENTES[DIAS]").texto)


# 4 y 14 ----------------------------------------------------------------------
class SinModeloTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dic_sinmod_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        X.crear_proyecto(self.tmp)
        X._manifest(self.tmp, "tablero_sin_modelo", "tablero_sin_modelo", "TABLERO SIN MODELO")
        self.raiz = self.tmp / "docs_tableros"
        md = self.raiz / "tablero_sin_modelo" / "md"
        dic = F.Documento(meta={"tablero": "TABLERO SIN MODELO", "pagina": "DICCIONARIO", "nombre_funcional": "Dic",
                                "bloque": "Diccionario", "tablas": [], "actualizado": FECHA, "version": 1},
                          titulo="DICCIONARIO", proposito="Prueba.")
        dic.secciones["Medidas"] = [
            F.Entrada("[A]", "Algo. Unidad: Por confirmar. Tabla: T. Cálculo: `1`. Se usa en: nada."),
            F.Entrada("[B]", "Por confirmar. Unidad: n. Tabla: T. Cálculo: `2`. Se usa en: nada."),
            F.Entrada("[C]", "Listo. Unidad: n. Tabla: T. Cálculo: `3`. Se usa en: nada.")]
        dic.secciones[F.SECCION_HISTORIAL] = [F.Entrada(f"{FECHA} · v1", "Inicial.")]
        (md / "_diccionario.md").write_text(F.serializar(dic), encoding="utf-8")
        (md / "roto.md").write_text("sin formato", encoding="utf-8")
        (self.raiz / X.GRUPO / "md" / "resumen.md").write_text(_pagina_md("RESUMEN", {}), encoding="utf-8")

    def test_informa_sin_modelo_y_valida_los_md(self):
        c = D.cobertura("tablero_sin_modelo", self.tmp, raiz_docs=self.raiz)
        self.assertTrue(c["sin_modelo"])
        self.assertIn("sin modelo disponible", c["mensaje"])
        self.assertIsNone(c["porcentaje"])
        self.assertEqual(c["validacion"]["archivos"], 2)
        self.assertIn("roto.md", c["validacion"]["errores"])
        self.assertEqual(c["paginas"]["total"], 0)
        # 14: las dos cifras de «Por confirmar».
        self.assertEqual((c["diccionario"]["por_confirmar"], c["diccionario"]["con_por_confirmar"]), (1, 2))

    def test_cli_todos_sigue_funcionando(self):
        anterior = os.environ.get("DOCS_MD_ROOT")
        os.environ["DOCS_MD_ROOT"] = str(self.raiz)
        try:
            salida, error = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
                codigo = D.main(["--raiz", str(self.tmp), "cobertura", "--todos"])
            with contextlib.redirect_stdout(io.StringIO()) as js:
                D.main(["--raiz", str(self.tmp), "cobertura", "--todos", "--json"])
        finally:
            if anterior is None:
                os.environ.pop("DOCS_MD_ROOT")
            else:
                os.environ["DOCS_MD_ROOT"] = anterior
        self.assertEqual(codigo, 0)
        self.assertIn("tablero_sin_modelo (TABLERO SIN MODELO): sin modelo disponible", salida.getvalue())
        self.assertIn(X.GRUPO, salida.getvalue())
        self.assertIn("lo mencionan", salida.getvalue())
        self.assertEqual(len(json.loads(js.getvalue())), 2)


# 5 y 12 ----------------------------------------------------------------------
class EmparejamientoPaginasTest(_ConProyecto):
    def _docs(self, *pares):
        return [(a, F.parsear(t), F.normalizar_nombre(t)) for a, t in pares]

    def test_paginas_con_nombre_repetido(self):
        self.hechos["paginas"] = [
            _pagina("ReportSection0b34ce4c", "INTERCONSULTAS", [
                _visual("a", "tableEx", [("INTERCONSULTA_DIA[DOCUMENTO]", "DOCUMENTO")], "EN ESPERA INTERCONSULTA")]),
            _pagina("40b538b7decab0134a35", "INTERCONSULTAS", [
                _visual("b", "lineChart", [("INTERCONSULTAS[TIEMPO]", "TIEMPO")], "TIEMPO DE RESPUESTA HISTORICO"),
                _visual("c", "slicer", [("Calendario[Date] (Año)", "Año")])]),
        ]
        self.escribir_md("interconsultas_dia.md", _pagina_md(
            "INTERCONSULTAS DIA", {"Visuales": [("Tabla", "EN ESPERA INTERCONSULTA, documentos.")]},
            {"id_pagina": "ReportSection0b34ce4c"},
            proposito="En Power BI esta página se llama INTERCONSULTAS."))
        self.escribir_md("interconsultas_historico.md", _pagina_md(
            "INTERCONSULTAS HISTORICO", {"Visuales": [("Líneas", "TIEMPO DE RESPUESTA HISTORICO por mes.")]},
            proposito="En Power BI esta página también se llama INTERCONSULTAS."))
        c = self.cobertura()
        self.assertEqual(c["paginas"]["faltantes"], [])
        mecanismos = {(e["id"], e["archivo"], e["mecanismo"]) for e in c["emparejamiento"]}
        self.assertEqual(mecanismos, {("ReportSection0b34ce4c", "interconsultas_dia.md", "id"),
                                      ("40b538b7decab0134a35", "interconsultas_historico.md", "visuales")})

    def test_sufijo_numerico_y_alias(self):
        paginas = [_pagina("a", "X", []), _pagina("b", "X", []), _pagina("c", "Página 1", [])]
        docs = self._docs(
            ("x.md", _pagina_md("X", {})), ("x_2.md", _pagina_md("X (2)", {})),
            ("lav.md", _pagina_md("LAVANDERIA", {}, {"pagina_pbip": ["Página 1"]})))
        pares = D.emparejar_paginas(paginas, docs)
        self.assertEqual({i: (docs[j][0], m) for i, (j, m) in pares.items()},
                         {0: ("x.md", "nombre"), 1: ("x_2.md", "nombre"), 2: ("lav.md", "alias")})

    def test_duplicado_de_sin_falsos_positivos(self):
        docs = self._docs(("detalle.md", _pagina_md("DETALLE", {})))
        pares = D.emparejar_paginas([_pagina("a", "Duplicado de DETALLE", [])], docs)
        self.assertEqual(pares, {0: (0, "duplicado")})
        # Si la página original también existe, el duplicado no se empareja con su .md.
        pares = D.emparejar_paginas([_pagina("a", "DETALLE", []), _pagina("b", "Duplicado de DETALLE", [])], docs)
        self.assertEqual(pares, {0: (0, "nombre")})

    def test_visuales_genericos_no_emparejan(self):
        # Un .md que menciona la página pero solo comparte segmentadores o visuales que
        # documentan muchos .md no se empareja.
        comun = _visual("t", "card", [("PACIENTES[Total pacientes]", "Total")], "TOTAL")
        paginas = [_pagina("a", "OTRA", [comun, _visual("s", "slicer", [("Calendario[Date] (Año)", "Año")])])]
        docs = self._docs(*[(f"d{i}.md", _pagina_md(f"D{i}", {"Visuales": [("T", "TOTAL de OTRA.")]})) for i in range(3)])
        self.assertEqual(D.emparejar_paginas(paginas, docs), {})


# 7 ---------------------------------------------------------------------------
class DetectorPiiTest(unittest.TestCase):
    def test_no_cuenta_identificadores_tecnicos(self):
        for texto in ("---\nid_pagina: ReportSection0b34ce4c1234567890\n---",
                      "La página ReportSection1234567 está oculta.",
                      "Id de página 6c03bc7bd793eda6c68a1234567.",
                      "Visual 25A4F1234567890B1C2D3E4F5.",
                      "Tabla LocalDateTable_9ac60001-c9f5-4042-97cd-bb95fe5d5871."):
            self.assertIsNone(posible_pii(texto), texto)

    def test_sigue_detectando_documentos_y_telefonos(self):
        for texto in ("Paciente con documento 1234567890.", "Teléfono 3001234567.", "CC 12345678",
                      "id_pagina 1234567", "ReportSection abc 98765432", "correo ana@hospital.org",
                      "Documento 1.234.567.891"):
            self.assertIsNotNone(posible_pii(texto), texto)


# 8 y 10 ----------------------------------------------------------------------
class DescripcionesHeredadasTest(_ConProyecto):
    LARGO = ("Pacientes hospitalizados hoy, una fila por paciente, con su servicio, estado y fecha de ingreso; "
             "se actualiza cada hora desde la historia clínica y excluye a los pacientes de urgencias que aún no "
             "tienen cama asignada, a los de cirugía ambulatoria y a los trasladados a otra institución durante el día, "
             "porque el tablero se centra en la ocupación de camas de hospitalización")

    def test_no_trunca_lo_heredado(self):
        self.assertGreater(len(self.LARGO), 300)
        self.escribir_md("resumen.md", _pagina_md("RESUMEN", {"Fuentes de datos": [("PACIENTES", self.LARGO + ".")]}))
        texto = self.esqueleto().buscar("Tablas", "PACIENTES").texto
        self.assertTrue(texto.startswith(self.LARGO + "."), texto)
        self.assertNotIn("…", texto)

    def test_no_propaga_notas_de_nombre_de_pagina_si_el_pbip_trae_los_nombres(self):
        self.escribir_md("resumen.md", _pagina_md("RESUMEN", {"Fuentes de datos": [
            ("PACIENTES", "Pacientes de hoy. Nombre de página en Power BI por confirmar. Una fila por paciente.")]}))
        con_pbip = self.esqueleto().buscar("Tablas", "PACIENTES").texto
        self.assertTrue(con_pbip.startswith("Pacientes de hoy. Una fila por paciente."), con_pbip)
        self.assertNotIn("Nombre de página", con_pbip)
        sin_pbip = D.generar_esqueleto(self.grupo, self.tmp, raiz_docs=self.raiz, fecha=FECHA)
        self.assertIn("Nombre de página en Power BI por confirmar", sin_pbip.buscar("Tablas", "PACIENTES").texto)


# 9 ---------------------------------------------------------------------------
class PbipSinVisualesTest(_ConProyecto):
    def setUp(self):
        super().setUp()
        for p in self.hechos["paginas"]:
            p["visuales"] = []
            p["filtros"] = []

    def test_se_usa_en_sin_dato(self):
        doc = self.esqueleto()
        texto = doc.buscar("Medidas", "[Sin uso]").texto
        self.assertIn(f"Se usa en: {D.SIN_VISUALES}.", texto)
        self.assertNotIn("no aparece en visuales", F.serializar(doc))

    def test_escribir_respeta_el_texto_redactado(self):
        D.escribir_esqueleto(self.grupo, self.tmp, raiz_docs=self.raiz, hechos=self.hechos, fecha=FECHA)
        ruta = self.md / "_diccionario.md"
        doc = F.parsear(ruta.read_text(encoding="utf-8"))
        entrada = doc.buscar("Medidas", "[Sin uso]")
        entrada.texto = "Medida de prueba. Unidad: n. Tabla: PACIENTES. Cálculo: `x`. Se usa en: tarjeta oculta de RESUMEN (según el propietario)."
        ruta.write_text(F.serializar(doc), encoding="utf-8")
        antes = ruta.read_text(encoding="utf-8")
        for _ in range(2):
            r = D.escribir_esqueleto(self.grupo, self.tmp, raiz_docs=self.raiz, hechos=self.hechos, fecha=FECHA)
            self.assertEqual(r["escritos"], [])
        self.assertEqual(ruta.read_text(encoding="utf-8"), antes)
        simulado = D.escribir_esqueleto(self.grupo, self.tmp, raiz_docs=self.raiz, hechos=self.hechos, fecha=FECHA,
                                        guardar=False)
        self.assertEqual((simulado["nuevas"], simulado["obsoletas"], simulado["detalle"]), (0, 0, []))


# 11 --------------------------------------------------------------------------
class DescripcionColumnaPorTablaTest(unittest.TestCase):
    def setUp(self):
        self.modelo = _modelo(tablas=["CIRUGIAS", "CONSULTAS_AMBULATORIAS", "SERV"], columnas={
            ("CIRUGIAS", "ESPECIALIDAD"): _col(), ("CONSULTAS_AMBULATORIAS", "ESPECIALIDAD"): _col(),
            ("SERV", "CODIGO"): _col()})

    def conocido(self, entradas, tablas):
        doc = F.parsear(_pagina_md("CIRUGIAS", {"Definiciones": entradas}, tablas=tablas))
        return D.conocimiento_md([("cirugias.md", doc)], self.modelo)["columnas"]

    def test_no_copia_a_otra_tabla_con_la_misma_columna(self):
        col = self.conocido([("ESPECIALIDAD", "Especialidad del cirujano.")], ["CIRUGIAS"])
        self.assertEqual(set(col), {("CIRUGIAS", "ESPECIALIDAD")})

    def test_ambigua_sin_tabla_no_se_hereda(self):
        self.assertEqual(self.conocido([("ESPECIALIDAD", "Especialidad.")], ["OTRA"]), {})

    def test_por_tabla_columna_o_nombre_unico(self):
        col = self.conocido([("Regla", "CONSULTAS_AMBULATORIAS[ESPECIALIDAD] viene de la agenda."),
                             ("CODIGO", "Código del servicio sin espacios.")], ["OTRA"])
        self.assertEqual(set(col), {("CONSULTAS_AMBULATORIAS", "ESPECIALIDAD"), ("SERV", "CODIGO")})

    def test_cita_con_prefijo_no_confunde_tablas(self):
        self.modelo["columnas"][("ESPECIALIDADES_CIRUGIAS", "ESPECIALIDAD")] = _col()
        col = self.conocido([("Regla", "ESPECIALIDADES_CIRUGIAS[ESPECIALIDAD] es el catálogo.")], ["OTRA"])
        self.assertEqual(set(col), {("ESPECIALIDADES_CIRUGIAS", "ESPECIALIDAD")})


# 13 --------------------------------------------------------------------------
class UnidadTest(unittest.TestCase):
    def test_sin_evidencia_queda_por_confirmar(self):
        self.assertEqual(D._unidad(_medida(tipo="fecha"), None), D.POR_CONFIRMAR)
        self.assertEqual(D._unidad(_medida(formato="0.0%"), None), "porcentaje")

    def test_no_se_hereda_de_una_entrada_de_varias_medidas(self):
        modelo = _modelo(tablas=["T"], medidas={"Espera": _medida("T"), "Total": _medida("T"), "Solo": _medida("T")})
        doc = F.parsear(_pagina_md("P", {"Indicadores": [
            ("Tiempos", "Espera y conteo. Unidad: minutos. Medidas [Espera] y [Total]."),
            ("Solo", "Una sola. Unidad: pacientes. Medida [Solo].")]}))
        unidades = D.conocimiento_md([("p.md", doc)], modelo)["unidades"]
        self.assertEqual(unidades, {"Solo": "pacientes"})


# 15 --------------------------------------------------------------------------
class CarpetaPbipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dic_pbip_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def informe(self, carpeta, nombre):
        (self.tmp / "tableros" / carpeta / f"{nombre}.Report").mkdir(parents=True)
        (self.tmp / "tableros" / carpeta / f"{nombre}.SemanticModel").mkdir(parents=True)
        return self.tmp / "tableros" / carpeta

    def test_nombre_del_report_y_palabras_vacias(self):
        control = self.informe("Tablero Control de Facturacion", "Tablero Control Facturacion")
        lav = self.informe("Tablero_lavanderia", "Tablero_lavanderia")
        atenciones = self.informe("ATENCIONES INSTITUCIONALES", "ATENCIONES INSTITUCIONALES")
        m = {"report": "TABLERO CONTROL FACTURACION", "semantic_model": "Tablero Control Facturacion"}
        self.assertEqual(D.carpeta_pbip("tablero_control_facturacion", self.tmp, m), control)
        self.assertEqual(D.carpeta_pbip("tablero_lavanderia", self.tmp, {"pbir_path": None}), lav)
        self.assertEqual(D.carpeta_pbip("tablero_de_atenciones_institucionales", self.tmp, {}), atenciones)
        self.assertIsNone(D.carpeta_pbip("tablero_financiera", self.tmp, {"report": "TABLERO FINANCIERA"}))

    def test_pbir_path_del_manifest(self):
        carpeta = self.informe("Nombre Raro", "Otro Nombre")
        m = {"pbir_path": str(carpeta / "Otro Nombre.Report")}
        self.assertEqual(D.carpeta_pbip("tablero_x", self.tmp, m), carpeta)
        # Ruta de otra máquina: se usa el nombre de su carpeta dentro de tableros/.
        m = {"pbir_path": str(Path("Z:/otra/tableros/Nombre Raro/Otro Nombre.Report"))}
        self.assertEqual(D.carpeta_pbip("tablero_x", self.tmp, m), carpeta)

    def test_ambiguo_no_elige(self):
        self.informe("TABLERO DE CITAS", "TABLERO DE CITAS")
        self.informe("CITAS", "CITAS")
        # «tablero_citas» coincide exacto (en slug) con una sola: sin ambigüedad.
        self.assertEqual(D.carpeta_pbip("tablero_citas", self.tmp, {}).name, "CITAS")
        # Sin palabras vacías, «tablero_de_citas» y «citas» se vuelven iguales: en el paso exacto gana la suya.
        self.assertEqual(D.carpeta_pbip("tablero_de_citas", self.tmp, {}).name, "TABLERO DE CITAS")
        self.informe("Citas del", "Citas del")
        self.assertIsNone(D.carpeta_pbip("tablero_la_citas", self.tmp, {}))


class PbipRealesTest(unittest.TestCase):
    """Los PBIP reales de `tableros/` se resuelven cada uno a un único grupo."""

    def test_cada_pbip_real_tiene_su_grupo(self):
        raiz = D.raiz_datos()
        base = raiz / "tableros"
        if not base.is_dir():
            self.skipTest("no hay tableros/ (DOCS_MD_DATA_ROOT=<checkout principal>)")
        docs = Path(__file__).resolve().parents[2] / "docs_tableros"
        resueltas: dict[Path, list[str]] = {}
        for manifest_ruta in sorted(docs.glob("*/manifest.json")):
            grupo = manifest_ruta.parent.name
            manifest = json.loads(manifest_ruta.read_text(encoding="utf-8-sig"))
            carpeta = D.carpeta_pbip(grupo, raiz, manifest)
            if carpeta is not None:
                resueltas.setdefault(carpeta, []).append(grupo)
        carpetas = sorted(p for p in base.iterdir() if p.is_dir() and any(p.glob("*.Report")))
        for carpeta in carpetas:
            with self.subTest(carpeta=carpeta.name):
                self.assertEqual(len(resueltas.get(carpeta, [])), 1, resueltas.get(carpeta))
        self.assertEqual(set(resueltas), set(carpetas))


if __name__ == "__main__":
    unittest.main()

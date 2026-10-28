"""
Diccionario de variables: formato, repositorio, ingesta al RAG, esqueleto,
cobertura, comparación con el modelo y escritura sin pisar texto.

    python -m unittest tests.docs_md.test_diccionario

Todo es sintético y offline (tests/docs_md/diccionario_fixture.py): no necesita
Power BI, MedGemma, Qdrant ni los datos reales del propietario.
"""
import contextlib
import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from src.docs_md import diccionario as D
from src.docs_md import formato as F
from src.docs_md import ingesta as I
from src.docs_md import repositorio as R
from src.docs_md.uso import texto_uso, uso_de_campos
from src.rag import chunk_builder as CB
from tests.docs_md import diccionario_fixture as X
from tests.docs_md.test_docs_tableros import PII

FECHA = "2026-10-28"

DICCIONARIO = """---
tablero: TABLERO MINI
pagina: DICCIONARIO
nombre_funcional: Diccionario de variables del tablero
bloque: Diccionario
tablas: [PACIENTES]
actualizado: 2026-10-20
version: 1
---

# DICCIONARIO

## Propósito
Diccionario de prueba.

## Tablas
- **PACIENTES**: Pacientes hospitalizados. Origen: consulta SQL. Granularidad: una fila por paciente. Columnas principales: SERVICIO, ESTADO.

## Medidas
- **[Pacientes activos]**: Pacientes con estado ACTIVO. Unidad: pacientes. Tabla: PACIENTES. Cálculo: `CALCULATE([Total pacientes], PACIENTES[ESTADO] = "ACTIVO")`. Se usa en: RESUMEN › Tarjeta «X».
- **[Medida vieja]**: Ya no existe. Unidad: pacientes. Tabla: PACIENTES. Cálculo: `COUNTROWS(PACIENTES)`. Se usa en: RESUMEN › Tarjeta «Y».

## Columnas calculadas
- **PACIENTES[DIAS]**: Días desde el ingreso. Tipo: entero. Cálculo: `DATEDIFF(PACIENTES[FECHA_INGRESO], TODAY(), DAY)`. Se usa en: DETALLE › Tabla «LISTADO».

## Columnas clave
- **PACIENTES[SERVICIO]**: Servicio donde está el paciente. Tipo: texto. Valores: Por confirmar. Se usa en: RESUMEN › Segmentación de PACIENTES[SERVICIO].

## Relaciones
- **PACIENTES[FECHA_INGRESO] → Calendario[Date]**: Muchos a uno, Calendario filtra a PACIENTES, activa.

## Observaciones
- **Unidad**: La unidad de las medidas por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial.
"""

PAGINA_RESUMEN = """---
tablero: TABLERO MINI
pagina: RESUMEN
nombre_funcional: Resumen de pacientes
bloque: Día
tablas: [PACIENTES]
actualizado: 2026-10-20
version: 1
---

# RESUMEN

## Propósito
Muestra el total de pacientes y el porcentaje de activos.

## Fuentes de datos
- **PACIENTES**: Pacientes hospitalizados hoy, una fila por paciente.

## Indicadores
- **Total de pacientes**: Cantidad de pacientes en el contexto. Medida Total pacientes = COUNTROWS(PACIENTES).
- **Días promedio**: Promedio de días de estancia. Unidad: días. Medida [Dias promedio].

## Visuales
- **Tarjeta TOTAL PACIENTES**: Muestra el total de pacientes.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial.
"""


def _proyecto(testcase) -> tuple[Path, str, dict]:
    tmp = Path(tempfile.mkdtemp(prefix="dic_"))
    testcase.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
    grupo, hechos = X.crear_proyecto(tmp)
    return tmp, grupo, hechos


def _carpeta_md(tmp: Path, grupo: str = X.GRUPO) -> Path:
    return tmp / "docs_tableros" / grupo / "md"


class FormatoDiccionarioTest(unittest.TestCase):
    def test_parsear_serializar_ida_y_vuelta(self):
        doc = F.parsear(DICCIONARIO)
        self.assertEqual(F.validar(doc), [])
        self.assertEqual(F.serializar(doc), DICCIONARIO)
        self.assertEqual([s for s in doc.secciones], F.SECCIONES_DICCIONARIO[1:])
        self.assertEqual(doc.buscar("Medidas", "[pacientes ACTIVOS]").nombre, "[Pacientes activos]")

    def test_secciones_en_orden(self):
        desordenado = DICCIONARIO.replace("## Tablas", "## ZZ").replace("## Medidas", "## Tablas").replace("## ZZ", "## Medidas")
        doc = F.parsear(desordenado)
        salida = F.serializar(doc)
        self.assertLess(salida.index("## Tablas"), salida.index("## Medidas"))
        self.assertLess(salida.index("## Columnas calculadas"), salida.index("## Columnas clave"))
        self.assertLess(salida.index("## Relaciones"), salida.index("## Historial"))

    def test_validar_rechaza_secciones_y_nombres_de_otro_bloque(self):
        doc = F.parsear(DICCIONARIO)
        doc.secciones["Indicadores"] = [F.Entrada("X", "Algo.")]
        self.assertTrue(any("Indicadores" in e for e in F.validar(doc)))
        doc = F.parsear(DICCIONARIO)
        doc.secciones["Medidas"][0].nombre = "Pacientes activos"
        self.assertTrue(any("[Medida]" in e for e in F.validar(doc)))
        doc = F.parsear(DICCIONARIO)
        doc.meta["pagina"] = doc.titulo = "PACIENTES"
        self.assertTrue(any("DICCIONARIO" in e for e in F.validar(doc)))

    def test_una_pagina_no_admite_secciones_del_diccionario(self):
        pagina = F.parsear(PAGINA_RESUMEN)
        pagina.secciones["Medidas"] = [F.Entrada("[X]", "Algo.")]
        self.assertTrue(any("Medidas" in e for e in F.validar(pagina)))
        self.assertEqual(F.validar(F.parsear(PAGINA_RESUMEN)), [])

    def test_aplicar_operaciones(self):
        doc = F.parsear(DICCIONARIO)
        ops = [
            F.Operacion("modificar", "Medidas", "[Pacientes activos]",
                        "Pacientes con tratamiento activo. Unidad: pacientes. Tabla: PACIENTES. Cálculo: `COUNTROWS(PACIENTES)`. Se usa en: RESUMEN › Tarjeta «X»."),
            F.Operacion("agregar", "Columnas clave", "PACIENTES[ESTADO]", "Estado del paciente. Tipo: texto. Se usa en: filtros."),
            F.Operacion("eliminar", "Medidas", "[Medida vieja]"),
        ]
        nuevo = F.aplicar_operaciones(doc, ops, "Se ajusta el diccionario", autor="Ana", fecha=FECHA)
        self.assertEqual(F.validar(nuevo), [])
        self.assertEqual(nuevo.meta["version"], 2)
        self.assertIsNone(nuevo.buscar("Medidas", "[Medida vieja]"))
        self.assertIn("tratamiento activo", nuevo.buscar("Medidas", "[Pacientes activos]").texto)
        self.assertIsNotNone(nuevo.buscar("Columnas clave", "PACIENTES[estado]"))
        self.assertEqual(doc.buscar("Medidas", "[Medida vieja]").nombre, "[Medida vieja]", "el original no cambia")
        with self.assertRaises(F.ErrorOperacion):
            F.aplicar_operaciones(doc, [F.Operacion("agregar", "Indicadores", "X", "y")], "r")

    def test_nombres_largos_de_columnas_se_aceptan_en_el_diccionario(self):
        doc = F.parsear(DICCIONARIO)
        largo = "TABLA_" + "X" * 80 + "[" + "COLUMNA_" + "Y" * 60 + "]"
        self.assertGreater(len(largo), F.MAX_NOMBRE)
        nuevo = F.aplicar_operaciones(doc, [F.Operacion("agregar", "Columnas clave", largo, "Algo. Se usa en: filtros.")], "r")
        self.assertEqual(F.validar(nuevo), [])


class RepositorioDiccionarioTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.grupo, _ = _proyecto(self)
        md = _carpeta_md(self.tmp)
        (md / "_diccionario.md").write_text(DICCIONARIO, encoding="utf-8")
        (md / "resumen.md").write_text(PAGINA_RESUMEN, encoding="utf-8")
        self.raiz = self.tmp / "docs_tableros"

    def test_listar_paginas_no_devuelve_el_diccionario(self):
        paginas = R.listar_paginas(self.grupo, self.raiz)
        self.assertEqual([p["archivo"] for p in paginas], ["resumen.md"])
        dic = R.listar_diccionarios(self.grupo, self.raiz)
        self.assertEqual([(d["archivo"], d["pagina"], d["valido"]) for d in dic], [("_diccionario.md", "DICCIONARIO", True)])
        self.assertEqual(R.listar_tableros(self.raiz)[0]["paginas"], 1)

    def test_leer_aplicar_y_guardar(self):
        doc = R.leer_pagina(self.grupo, "DICCIONARIO", self.raiz)
        self.assertEqual(doc.meta["bloque"], "Diccionario")
        self.assertEqual(R.leer_diccionario(self.grupo, raiz=self.raiz).pagina, "DICCIONARIO")
        nuevo = F.aplicar_operaciones(doc, [F.Operacion("eliminar", "Medidas", "[Medida vieja]")], "Se quita", fecha=FECHA)
        ruta = R.guardar_pagina(self.grupo, nuevo, self.raiz)
        self.assertEqual(ruta.name, "_diccionario.md")
        self.assertIsNone(R.leer_diccionario(self.grupo, raiz=self.raiz).buscar("Medidas", "[Medida vieja]"))
        self.assertEqual([p["archivo"] for p in R.listar_paginas(self.grupo, self.raiz)], ["resumen.md"])

    def test_archivo_para_con_tema(self):
        doc = F.parsear(DICCIONARIO)
        doc.meta["pagina"] = doc.titulo = "DICCIONARIO COLUMNAS"
        self.assertEqual(R.archivo_para(doc), "_diccionario_columnas.md")
        self.assertTrue(R.es_archivo_diccionario("_diccionario_columnas.md"))
        self.assertFalse(R.es_archivo_diccionario("diccionario_de_datos.md"))


class IngestaDiccionarioTest(unittest.TestCase):
    def setUp(self):
        self.doc = F.parsear(DICCIONARIO)
        self.tablero = I.documento_a_tablero(self.doc, nombre=I.nombre_diccionario(self.doc))

    def test_campos_de_una_entrada(self):
        c = I.campos_entrada_diccionario(
            'Total de algo. Unidad: pacientes. Tabla: T. Cálculo: `IF(x, "Tabla: y. Cálculo: z")`. Se usa en: P › V; Q › W.')
        self.assertEqual(c["descripcion"], "Total de algo.")
        self.assertEqual(c["unidad"], "pacientes")
        self.assertEqual(c["tabla"], "T")
        self.assertEqual(c["calculo"], 'IF(x, "Tabla: y. Cálculo: z")')
        self.assertEqual(c["se_usa_en"], "P › V; Q › W")
        sin = I.campos_entrada_diccionario("Por confirmar. Unidad: Por confirmar. Tabla: T. Cálculo: Por confirmar. Se usa en: Por confirmar.")
        self.assertIsNone(sin["calculo"])

    def test_esquema_normalizado(self):
        t = self.tablero
        self.assertEqual(t["name"], "DICCIONARIO TABLERO MINI")
        self.assertTrue(t["is_dictionary"])
        medida = next(m for m in t["documented_measures"] if m["name"] == "Pacientes activos")
        self.assertEqual(medida["table"], "PACIENTES")
        self.assertEqual(medida["expression"], 'CALCULATE([Total pacientes], PACIENTES[ESTADO] = "ACTIVO")')
        self.assertIn("Pacientes con estado ACTIVO.", medida["description"])
        self.assertIn("Unidad: pacientes", medida["description"])
        self.assertIn("RESUMEN › Tarjeta «X»", medida["description"])
        self.assertNotIn("Cálculo", medida["description"])
        columna = t["calculated_columns"][0]
        self.assertEqual((columna["table"], columna["name"]), ("PACIENTES", "DIAS"))
        self.assertIn("DATEDIFF", columna["expression"])
        self.assertTrue(t["data_sources"][0].startswith("PACIENTES: Pacientes hospitalizados."))
        encabezados = {s["heading"] for s in t["other_sections"]}
        self.assertEqual(encabezados, {"Columnas clave", "Relaciones", "Historial de cambios"})
        self.assertEqual(len(t["notes"]), 1)
        self.assertEqual(t["indicators"], [])

    def test_las_paginas_no_cambian(self):
        pagina = I.documento_a_tablero(F.parsear(PAGINA_RESUMEN))
        self.assertNotIn("is_dictionary", pagina)
        nombres = [m["name"] for m in pagina["documented_measures"]]
        self.assertIn("Dias promedio", nombres)

    def test_chunks_buscables(self):
        t = dict(self.tablero, source_group=X.GRUPO, semantic_model_key=X.MODELO,
                 matched_measures=[], unmatched_documented_measures=self.tablero["documented_measures"])
        chunks = CB.build_chunks({"dashboards": [t]})
        tipos = {c["chunk_type"] for c in chunks}
        self.assertTrue({"documented_measure", "calculated_column", "data_source", "document_section", "dashboard_overview"} <= tipos)
        medida = next(c for c in chunks if c["chunk_type"] == "documented_measure" and c["metadata"]["measure"] == "Pacientes activos")
        # «¿qué mide X?» / «¿cómo se calcula X?»: nombre, descripción y DAX en el mismo chunk.
        for fragmento in ("Pacientes activos", "Pacientes con estado ACTIVO", "CALCULATE([Total pacientes]", "PACIENTES"):
            self.assertIn(fragmento, medida["text"])
        columnas = [c for c in chunks if c["metadata"].get("section_category") == "other" and c["metadata"]["section"] == "Columnas clave"]
        self.assertEqual(len(columnas), 1)
        self.assertIn("PACIENTES[SERVICIO]", columnas[0]["text"])
        self.assertEqual(len({c["id"] for c in chunks}), len(chunks))

    def test_medidas_con_nombres_casi_iguales_no_se_pisan(self):
        doc = F.parsear(DICCIONARIO)
        doc.secciones["Medidas"] = [
            F.Entrada("[Consultas Año Anterior]", "Uno. Unidad: n. Tabla: T. Cálculo: `1`. Se usa en: nada."),
            F.Entrada("[Consultas_Año_Anterior]", "Dos. Unidad: n. Tabla: T. Cálculo: `2`. Se usa en: nada."),
        ]
        t = I.documento_a_tablero(doc)
        t.update(matched_measures=[], unmatched_documented_measures=t["documented_measures"])
        medidas = [c for c in CB.build_chunks({"dashboards": [t]}) if c["chunk_type"] == "documented_measure"]
        self.assertEqual(len(medidas), 2)

    def test_markdown_dashboard_del_normalizador(self):
        from src.semantic.document_normalizer import normalize_markdown_dashboard
        t = normalize_markdown_dashboard({"markdown": DICCIONARIO, "name": "DICCIONARIO TABLERO MINI", "aliases": []})
        self.assertTrue(t["is_dictionary"])
        self.assertEqual(len(t["documented_measures"]), 2)

    def test_el_diccionario_no_cuenta_como_pagina(self):
        from src.semantic.semantic_merge import merge_dashboard
        fusion = merge_dashboard(dict(self.tablero), {}, {})
        self.assertTrue(fusion["is_dictionary"])
        self.assertNotIn("is_dictionary", merge_dashboard(I.documento_a_tablero(F.parsear(PAGINA_RESUMEN)), {}, {}))
        from src.semantic.source_model_router import SourceModelRouter
        router = SourceModelRouter.__new__(SourceModelRouter)
        n = SourceModelRouter.register_documentation_dashboards(router, [("DICCIONARIO TABLERO MINI", X.GRUPO), ("RESUMEN", X.GRUPO)])
        self.assertEqual(n, 1)

    def test_proceso_de_archivo_md(self):
        from src.ingestion.document_parser import process_markdown_document
        tmp, grupo, _ = _proyecto(self)
        (_carpeta_md(tmp) / "_diccionario.md").write_text(DICCIONARIO, encoding="utf-8")
        resultado = process_markdown_document(_carpeta_md(tmp) / "_diccionario.md", tmp / "data" / "raw", tmp / "docs_tableros")
        self.assertEqual(resultado["format_warnings"], [])
        tablero = resultado["dashboards"][0]
        self.assertEqual(tablero["name"], "DICCIONARIO TABLERO MINI")
        self.assertEqual(resultado["source_group"], X.GRUPO)


class UsoTest(unittest.TestCase):
    def test_uso_de_campos(self):
        _, hechos = X.crear_proyecto(Path(tempfile.mkdtemp(prefix="dic_uso_")))
        uso = uso_de_campos(hechos)
        self.assertEqual([u["pagina"] for u in uso["[Total pacientes]"]], ["RESUMEN"])
        self.assertEqual(uso["[Total pacientes]"][0]["tipo"], "card")
        self.assertEqual(uso["[Total pacientes]"][0]["titulo"], "TOTAL PACIENTES")
        self.assertEqual(sorted({u["pagina"] for u in uso["PACIENTES[SERVICIO]"]}), ["DETALLE", "RESUMEN"])
        self.assertIn("Calendario[Date]", uso)  # «Calendario[Date] (Año)»
        filtro = [u for u in uso["PACIENTES[DIAS]"] if u["visual"] == "Filtro de la página"]
        self.assertEqual(filtro[0]["pagina"], "DETALLE")
        self.assertNotIn("[Sin uso]", uso)
        self.assertIn("RESUMEN › Tarjeta «TOTAL PACIENTES»", texto_uso(uso["[Total pacientes]"]))
        self.assertIn("no aparece", texto_uso([]))

    def test_tablas_con_espacios(self):
        hechos = {"tablas": {"EN ESPERA": {}}, "medidas": {"EN ESPERA[Total]": "x"},
                  "paginas": [{"nombre": "P", "visuales": [
                      {"id": "v", "tipo": "card", "campos": ["AVERAGE(EN ESPERA[COL])", "EN ESPERA[Total]"], "campos_detalle": [], "filtros": []}]}]}
        uso = uso_de_campos(hechos)
        self.assertEqual(set(uso), {"EN ESPERA[COL]", "[Total]"})


class EsqueletoTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.grupo, self.hechos = _proyecto(self)
        self.raiz = self.tmp / "docs_tableros"

    def esqueleto(self, **kw):
        return D.generar_esqueleto(self.grupo, self.tmp, raiz_docs=self.raiz, hechos=self.hechos, fecha=FECHA, **kw)

    def test_estructura_y_valida(self):
        doc = self.esqueleto()
        self.assertEqual(F.validar(doc), [])
        self.assertEqual(doc.meta["bloque"], "Diccionario")
        self.assertEqual(doc.meta["tablero"], X.TABLERO)
        orden = [s for s in F.SECCIONES_DICCIONARIO if s in doc.secciones]
        self.assertEqual(sorted(doc.secciones), sorted(orden))
        for seccion in ("Tablas", "Medidas", "Columnas calculadas", "Columnas clave", "Relaciones", "Historial de cambios"):
            self.assertIn(seccion, doc.secciones)
        texto = F.serializar(doc)
        self.assertEqual(F.serializar(F.parsear(texto)), texto)
        # Sin las tablas automáticas de fechas ni las columnas RowNumber.
        self.assertNotIn("LocalDateTable", texto)
        self.assertNotIn("DateTableTemplate", texto)
        self.assertNotIn("RowNumber", texto)

    def test_es_determinista(self):
        self.assertEqual(F.serializar(self.esqueleto()), F.serializar(self.esqueleto()))

    def test_medidas_dax_literal_uso_y_clases(self):
        doc = self.esqueleto()
        activos = doc.buscar("Medidas", "[Pacientes activos]").texto
        self.assertIn('Cálculo: `CALCULATE([Total pacientes], PACIENTES[ESTADO] = "ACTIVO")`', activos)  # sin el comentario --
        self.assertIn("Tabla: PACIENTES.", activos)
        self.assertIn("Unidad: Por confirmar.", activos)
        self.assertTrue(activos.startswith("Por confirmar."))
        self.assertIn("las medidas [Porcentaje activos]", activos)  # la usa otra medida
        total = doc.buscar("Medidas", "[Total pacientes]").texto
        self.assertIn("Cálculo: `COUNTROWS(PACIENTES)`", total)  # sin el comentario //
        self.assertIn("RESUMEN › Tarjeta «TOTAL PACIENTES»", total)
        self.assertIn("Unidad: porcentaje.", doc.buscar("Medidas", "[Porcentaje activos]").texto)
        self.assertIn("Clase: oculta.", doc.buscar("Medidas", "[Base interna]").texto)
        self.assertIn("Promedio de días de estancia.", doc.buscar("Medidas", "[Dias promedio]").texto)  # descripción del modelo
        sin_uso = doc.buscar("Medidas", "[Sin uso]").texto
        self.assertIn("no aparece en visuales", sin_uso)
        self.assertIn('Cálculo: `VAR x = "Tabla: texto" RETURN x`', sin_uso)
        for e in doc.entradas("Medidas"):
            self.assertNotIn("\n", e.texto)

    def test_columnas_tablas_y_relaciones(self):
        doc = self.esqueleto()
        dias = doc.buscar("Columnas calculadas", "PACIENTES[DIAS]").texto
        self.assertIn("Tipo: entero.", dias)
        self.assertIn("Cálculo: `DATEDIFF(PACIENTES[FECHA_INGRESO], TODAY(), DAY)`", dias)
        self.assertIn("DETALLE › Tabla «LISTADO»", dias)
        self.assertIn("Filtro de la página", dias)
        servicio = doc.buscar("Columnas clave", "PACIENTES[SERVICIO]").texto
        self.assertIn("Tipo: texto.", servicio)
        self.assertIn("Valores: Por confirmar.", servicio)
        self.assertIsNone(doc.buscar("Columnas clave", "PACIENTES[NOTA]"), "no se usa en visuales")
        self.assertIsNotNone(doc.buscar("Columnas clave", "Calendario[Date]"))
        tabla = doc.buscar("Tablas", "PACIENTES").texto
        self.assertIn("consulta SQL sobre DBO.HOSPITAL, DBO.CAMAS en la base DWPRUEBA", tabla)
        self.assertIn("Granularidad: Por confirmar.", tabla)
        self.assertIn("tabla calculada con DAX `CALENDAR", doc.buscar("Tablas", "Calendario").texto)
        activa = doc.buscar("Relaciones", "PACIENTES[FECHA_INGRESO] → Calendario[Date]").texto
        self.assertEqual(activa, "Muchos a uno, Calendario filtra a PACIENTES, activa.")
        self.assertIn("inactiva", doc.buscar("Relaciones", "PACIENTES[NOTA] → Calendario[Date]").texto)
        self.assertEqual(len(doc.entradas("Relaciones")), 2)  # la relación con LocalDateTable no cuenta

    def test_toma_descripciones_de_la_documentacion_md(self):
        carpeta = _carpeta_md(self.tmp)
        (carpeta / "resumen.md").write_text(PAGINA_RESUMEN, encoding="utf-8")
        doc = self.esqueleto()
        total = doc.buscar("Medidas", "[Total pacientes]").texto
        self.assertTrue(total.startswith("Total de pacientes. Cantidad de pacientes en el contexto."), total)
        dias = doc.buscar("Medidas", "[Dias promedio]").texto
        self.assertIn("Promedio de días de estancia.", dias)
        self.assertIn("Unidad: días.", dias)  # la unidad se toma de la página; la descripción del modelo manda
        self.assertTrue(doc.buscar("Tablas", "PACIENTES").texto.startswith("Pacientes hospitalizados hoy, una fila por paciente."))

    def test_sin_pbip_marca_uso_por_confirmar(self):
        doc = D.generar_esqueleto(self.grupo, self.tmp, raiz_docs=self.raiz, fecha=FECHA)
        self.assertIn("Se usa en: Por confirmar.", doc.buscar("Medidas", "[Sin uso]").texto)
        self.assertIsNotNone(doc.buscar("Observaciones", "Sin informe PBIP"))
        self.assertEqual(len(doc.entradas("Columnas clave")), 0)

    def test_sin_datos_falla_claro(self):
        with self.assertRaises(FileNotFoundError):
            D.generar_esqueleto("tablero_que_no_existe", self.tmp, raiz_docs=self.raiz)

    def test_sin_pii(self):
        texto = F.serializar(self.esqueleto())
        for patron in PII:
            self.assertIsNone(patron.search(texto), patron.pattern)


class EsqueletoGrandeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dic_grande_"))
        cls.grupo, cls.hechos = X.crear_proyecto_grande(cls.tmp)
        cls.archivos = D.generar_esqueleto_archivos(cls.grupo, cls.tmp, raiz_docs=cls.tmp / "docs_tableros",
                                                    hechos=cls.hechos, fecha=FECHA)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_prioriza_lo_usado_y_resume_el_resto(self):
        principal = self.archivos["_diccionario.md"]
        self.assertEqual(F.validar(principal), [])
        medidas = principal.entradas("Medidas")
        self.assertLess(len(medidas), 60)
        self.assertLessEqual(len(medidas), D.MAX_MEDIDAS_COMPLETAS)
        nombres = {F.normalizar_nombre(e.nombre) for e in medidas}
        for k in range(1, 31):  # las 30 usadas en tarjetas
            self.assertIn(F.normalizar_nombre(f"[Medida {k}]"), nombres)
        self.assertIn(F.normalizar_nombre("[Medida 0]"), nombres, "la que tiene descripción en el modelo")
        self.assertNotIn(F.normalizar_nombre("[Medida 500]"), nombres)
        resumenes = [e for e in principal.entradas("Observaciones") if e.nombre.startswith("Medidas no detalladas en")]
        self.assertTrue(resumenes)
        self.assertEqual(sum(int(re.match(r"(\d+) ", e.texto).group(1)) for e in resumenes) + len(medidas), 1800)
        self.assertLessEqual(len(principal.entradas("Observaciones")), D.MAX_RESUMENES * 2 + 5)

    def test_total_razonable_y_columnas_priorizadas(self):
        # Con 600 columnas calculadas solo se detallan las usadas en visuales.
        self.assertEqual(sorted(self.archivos), ["_diccionario.md"])
        principal = self.archivos["_diccionario.md"]
        self.assertEqual([e.nombre for e in principal.entradas("Columnas calculadas")], ["T005[CALC_5]"])
        self.assertTrue(any(e.nombre.startswith("Columnas calculadas no detalladas en") for e in principal.entradas("Observaciones")))
        peso = sum(len(F.serializar(d)) for d in self.archivos.values())
        self.assertLess(peso, 120_000, "el archivo debe ser útil, no ruido")

    def test_muchas_columnas_van_a_otro_archivo(self):
        tmp = Path(tempfile.mkdtemp(prefix="dic_cols_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        grupo, hechos = X.crear_proyecto_grande(tmp, n_calculadas=140)
        archivos = D.generar_esqueleto_archivos(grupo, tmp, raiz_docs=tmp / "docs_tableros", hechos=hechos, fecha=FECHA)
        self.assertEqual(sorted(archivos), ["_diccionario.md", "_diccionario_columnas.md"])
        columnas = archivos["_diccionario_columnas.md"]
        self.assertEqual(F.validar(columnas), [])
        self.assertEqual(columnas.pagina, "DICCIONARIO COLUMNAS")
        self.assertEqual(R.archivo_para(columnas), "_diccionario_columnas.md")
        self.assertEqual(len(columnas.entradas("Columnas calculadas")), 140)
        self.assertNotIn("Columnas calculadas", archivos["_diccionario.md"].secciones)
        self.assertEqual(F.validar(archivos["_diccionario.md"]), [])

    def test_tablas_resumidas_si_son_muchas(self):
        principal = self.archivos["_diccionario.md"]
        self.assertEqual(len(principal.entradas("Tablas")), 160)  # todas tienen medidas
        self.assertTrue(any("ID, NOMBRE" in e.texto for e in principal.entradas("Tablas")))


class CoberturaYComparacionTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.grupo, self.hechos = _proyecto(self)
        self.raiz = self.tmp / "docs_tableros"
        self.carpeta = _carpeta_md(self.tmp)

    def cobertura(self):
        return D.cobertura(self.grupo, self.tmp, raiz_docs=self.raiz, hechos=self.hechos)

    def test_cobertura_sin_documentacion(self):
        c = self.cobertura()
        self.assertEqual(c["medidas"]["documentados"], 0)
        self.assertEqual(c["medidas"]["total"], 6)
        self.assertEqual(c["medidas"]["porcentaje"], 0.0)
        self.assertEqual(c["paginas"]["faltantes"], ["RESUMEN", "DETALLE"])
        self.assertFalse(c["diccionario"]["existe"])
        self.assertEqual(c["tablas"]["total"], 2)
        self.assertEqual(c["relaciones"]["total"], 2)
        self.assertEqual(c["porcentaje"], 0.0)

    def test_cobertura_con_paginas_md(self):
        (self.carpeta / "resumen.md").write_text(PAGINA_RESUMEN, encoding="utf-8")
        c = self.cobertura()
        self.assertEqual(c["paginas"]["documentados"], 1)
        self.assertEqual(c["paginas"]["faltantes"], ["DETALLE"])
        self.assertEqual(sorted(c["medidas"]["faltantes"]),
                         sorted(["[Pacientes activos]", "[Porcentaje activos]", "[Base interna]", "[Sin uso]"]))
        self.assertNotIn("PACIENTES", c["tablas"]["faltantes"])
        self.assertIn("Calendario", c["tablas"]["faltantes"])
        # Visual «TOTAL PACIENTES» documentado por su título; los de DETALLE no (página sin documentar).
        self.assertFalse(any("TOTAL PACIENTES" in v for v in c["visuales"]["faltantes"]))
        self.assertTrue(any("DETALLE" in v for v in c["visuales"]["faltantes"]))
        self.assertGreater(c["porcentaje"], 0)

    def test_cobertura_con_diccionario(self):
        (self.carpeta / "_diccionario.md").write_text(DICCIONARIO, encoding="utf-8")
        c = self.cobertura()
        self.assertNotIn("[Pacientes activos]", c["medidas"]["faltantes"])
        self.assertNotIn("PACIENTES[SERVICIO]", c["columnas_clave"]["faltantes"])
        self.assertEqual(c["relaciones"]["faltantes"], ["PACIENTES[NOTA] → Calendario[Date]"])
        self.assertTrue(c["diccionario"]["existe"])
        self.assertEqual(c["diccionario"]["entradas"], 6)

    def test_comparar_obsoletas_nuevas_y_cambios(self):
        doc = DICCIONARIO.replace("[Medida vieja]", "[Total viejo]").replace(
            "Cálculo: `COUNTROWS(PACIENTES)`. Se usa en: RESUMEN › Tarjeta «Y»",
            "Cálculo: `COUNTROWS( PACIENTES )`. Se usa en: RESUMEN › Tarjeta «Y»")
        (self.carpeta / "_diccionario.md").write_text(doc, encoding="utf-8")
        r = D.comparar_con_modelo(self.grupo, self.tmp, raiz_docs=self.raiz, hechos=self.hechos)
        self.assertTrue(r["hay_diccionario"])
        self.assertEqual(r["obsoletas"]["medidas"], ["[Total viejo]"])
        self.assertEqual(r["obsoletas"]["columnas"], [])
        self.assertIn("[Total pacientes]", r["nuevas"]["medidas"])
        self.assertNotIn("[Pacientes activos]", r["nuevas"]["medidas"])
        self.assertEqual(r["renombradas_probables"], [{"antes": "[Total viejo]", "despues": "[Total pacientes]", "motivo": "mismo cálculo DAX"}])
        self.assertEqual(r["cambios_calculo"], [])  # solo cambian espacios: no es un cambio de cálculo
        self.assertIn("PACIENTES[NOTA] → Calendario[Date]", r["nuevas"]["relaciones"])

    def test_comparar_sin_diccionario(self):
        r = D.comparar_con_modelo(self.grupo, self.tmp, raiz_docs=self.raiz, hechos=self.hechos)
        self.assertFalse(r["hay_diccionario"])
        self.assertEqual(r["obsoletas"], {"medidas": [], "columnas": [], "tablas": [], "relaciones": []})
        self.assertEqual(len(r["nuevas"]["medidas"]), 6)


class EscribirTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.grupo, self.hechos = _proyecto(self)
        self.raiz = self.tmp / "docs_tableros"
        self.carpeta = _carpeta_md(self.tmp)

    def escribir(self):
        return D.escribir_esqueleto(self.grupo, self.tmp, raiz_docs=self.raiz, hechos=self.hechos, fecha=FECHA)

    def test_crea_el_archivo_y_es_idempotente(self):
        r = self.escribir()
        self.assertEqual([Path(p).name for p in r["escritos"]], ["_diccionario.md"])
        texto = (self.carpeta / "_diccionario.md").read_text(encoding="utf-8")
        self.assertEqual(F.validar(texto), [])
        self.assertEqual(F.serializar(F.parsear(texto)), texto)
        r2 = self.escribir()
        self.assertEqual(r2["escritos"], [])
        self.assertEqual((self.carpeta / "_diccionario.md").read_text(encoding="utf-8"), texto)

    def test_no_pisa_texto_redactado_agrega_nuevas_y_marca_obsoletas(self):
        (self.carpeta / "_diccionario.md").write_text(DICCIONARIO, encoding="utf-8")
        r = self.escribir()
        self.assertEqual(len(r["escritos"]), 1)
        doc = R.leer_diccionario(self.grupo, raiz=self.raiz)
        self.assertEqual(F.validar(doc), [])
        original = F.parsear(DICCIONARIO)
        # Lo redactado queda igual.
        self.assertEqual(doc.buscar("Medidas", "[Pacientes activos]").texto, original.buscar("Medidas", "[Pacientes activos]").texto)
        self.assertEqual(doc.buscar("Columnas calculadas", "PACIENTES[DIAS]").texto, original.buscar("Columnas calculadas", "PACIENTES[DIAS]").texto)
        self.assertEqual(doc.buscar("Tablas", "PACIENTES").texto, original.buscar("Tablas", "PACIENTES").texto)
        self.assertEqual(doc.proposito, "Diccionario de prueba.")
        self.assertEqual(doc.buscar("Observaciones", "Unidad").texto, "La unidad de las medidas por confirmar.")
        # Lo que ya no existe se marca; lo nuevo se agrega.
        self.assertTrue(doc.buscar("Medidas", "[Medida vieja]").texto.endswith(D.MARCA_OBSOLETA))
        self.assertIsNotNone(doc.buscar("Medidas", "[Total pacientes]"))
        self.assertIsNotNone(doc.buscar("Tablas", "Calendario"))
        self.assertIsNotNone(doc.buscar("Relaciones", "PACIENTES[NOTA] → Calendario[Date]"))
        self.assertEqual(doc.meta["version"], 2)
        self.assertEqual(doc.entradas("Historial de cambios")[-1].nombre, f"{FECHA} · v2")
        # Segunda corrida: nada cambia (no duplica, no marca dos veces).
        antes = (self.carpeta / "_diccionario.md").read_text(encoding="utf-8")
        self.assertEqual(self.escribir()["escritos"], [])
        self.assertEqual((self.carpeta / "_diccionario.md").read_text(encoding="utf-8"), antes)
        self.assertEqual(antes.count(D.MARCA_OBSOLETA), 1)

    def test_no_duplica_lo_que_otro_archivo_del_diccionario_ya_documenta(self):
        otro = F.parsear(DICCIONARIO)
        otro.meta["pagina"] = otro.titulo = "DICCIONARIO EXTRA"
        R.guardar_pagina(self.grupo, otro, self.raiz)
        self.assertTrue((self.carpeta / "_diccionario_extra.md").exists())
        self.escribir()
        principal = R.leer_diccionario(self.grupo, "_diccionario.md", self.raiz)
        self.assertIsNone(principal.buscar("Medidas", "[Pacientes activos]"))
        self.assertIsNotNone(principal.buscar("Medidas", "[Total pacientes]"))
        extra = R.leer_pagina(self.grupo, "DICCIONARIO EXTRA", self.raiz)
        self.assertTrue(extra.buscar("Medidas", "[Medida vieja]").texto.endswith(D.MARCA_OBSOLETA))


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.grupo, _ = _proyecto(self)
        self.raiz = self.tmp / "docs_tableros"

    def ejecutar(self, *args):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = D.main(["--raiz", str(self.tmp), *args])
        return codigo, salida.getvalue()

    def test_cobertura_y_json(self):
        codigo, texto = self.ejecutar("cobertura", self.grupo)
        self.assertEqual(codigo, 0)
        self.assertIn(self.grupo, texto)
        self.assertIn("Medidas", texto)
        _, texto_json = self.ejecutar("cobertura", self.grupo, "--json")
        self.assertEqual(json.loads(texto_json)[0]["medidas"]["total"], 6)

    def test_esqueleto_imprime_y_escribe(self):
        codigo, texto = self.ejecutar("esqueleto", self.grupo)
        self.assertEqual(codigo, 0)
        self.assertIn("bloque: Diccionario", texto)
        self.assertFalse((_carpeta_md(self.tmp) / "_diccionario.md").exists())
        # DOCS_MD_ROOT sirve de raíz de los .md.
        import os
        anterior = os.environ.get("DOCS_MD_ROOT")
        os.environ["DOCS_MD_ROOT"] = str(self.raiz)
        try:
            _, texto = self.ejecutar("esqueleto", self.grupo, "--escribir")
        finally:
            if anterior is None:
                os.environ.pop("DOCS_MD_ROOT")
            else:
                os.environ["DOCS_MD_ROOT"] = anterior
        self.assertIn("1 archivo(s)", texto)
        self.assertTrue((_carpeta_md(self.tmp) / "_diccionario.md").exists())


if __name__ == "__main__":
    unittest.main()

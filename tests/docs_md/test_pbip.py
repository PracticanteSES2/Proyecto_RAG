"""
Pruebas de los hechos del PBIP, su comparación y los borradores .md.

    python -m unittest tests.docs_md.test_pbip

Las pruebas con el tablero real usan data/raw/tablero_tiempos_urgencias del repo
principal (o DOCS_PBIP_PRUEBA); si no existe se saltan. Nunca se copia ni se lee
.pbi/cache.abf.
"""
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from src.docs_md import formato as F
from src.docs_md import pbip

RAIZ_REPO = Path(__file__).resolve().parents[2]
CANDIDATOS = [
    os.getenv("DOCS_PBIP_PRUEBA", ""),
    str(RAIZ_REPO / "data" / "raw" / "tablero_tiempos_urgencias"),
    r"C:\Users\ad6708\Documents\Proyecto_RAG\data\raw\tablero_tiempos_urgencias",
]
PBIP_REAL = next((Path(c) for c in CANDIDATOS if c and (Path(c) / "TABLERO TIEMPOS URGENCIAS.Report").is_dir()), None)
NOMBRE = "TABLERO TIEMPOS URGENCIAS"
PBIX_REAL = next((Path(c) for c in [
    os.getenv("DOCS_PBIX_PRUEBA", ""),
    str(RAIZ_REPO / "data" / "raw" / "tablero_financiera" / "TABLERO_FINANCIERA.pbix"),
    r"C:\Users\ad6708\Documents\Proyecto_RAG\data\raw\tablero_financiera\TABLERO_FINANCIERA.pbix",
] if c and Path(c).is_file()), None)


def _pagina(hechos, nombre):
    return next(p for p in hechos["paginas"] if p["nombre"] == nombre)


def _copiar_pbip(origen: Path, destino: Path) -> Path:
    """Copia solo el informe y el modelo (sin cache.abf ni documentos)."""
    ignorar = shutil.ignore_patterns("cache.abf", "*.abf")
    for carpeta in (f"{NOMBRE}.Report", f"{NOMBRE}.SemanticModel"):
        shutil.copytree(origen / carpeta, destino / carpeta, ignore=ignorar)
    pbip_archivo = origen / f"{NOMBRE}.pbip"
    if pbip_archivo.exists():
        shutil.copy2(pbip_archivo, destino / pbip_archivo.name)
    return destino


class PiezasTest(unittest.TestCase):
    """Partes del analizador que no necesitan el tablero real."""

    def test_sql_de_m_con_escapes(self):
        m = ('let\n Origen = Sql.Database("srv,1433\\inst", "DWX", [Query="SELECT A,#(lf)  B#(tab)FROM T#(lf)'
             'WHERE X = ""1"" AND CAST(F AS DATE) BETWEEN \'2023-01-01\' AND GETDATE()"])\nin Origen')
        info = pbip._analizar_m(m)
        self.assertEqual(info["servidor"], "srv,1433\\inst")
        self.assertEqual(info["base_datos"], "DWX")
        self.assertIn("\n  B\tFROM T\n", info["sql"])
        self.assertIn('X = "1"', info["sql"])
        self.assertEqual(pbip._condiciones_where(info["sql"]),
                         ['X = "1"', "CAST(F AS DATE) BETWEEN '2023-01-01' AND GETDATE()"])

    def test_sql_con_native_query(self):
        m = 'Value.NativeQuery(Sql.Database("s", "d"), "SELECT 1#(lf)FROM T WHERE A = 2", null, [EnableFolding=true])'
        info = pbip._analizar_m(m)
        self.assertEqual(info["sql"], "SELECT 1\nFROM T WHERE A = 2")
        self.assertEqual((info["servidor"], info["base_datos"]), ("s", "d"))

    def test_tabla_tmdl(self):
        texto = (
            "table 'EN ESPERA'\n"
            "\tmeasure 'Total X' =\n"
            "\t\t\tVAR a = 1\n"
            "\t\t\tRETURN a\n"
            "\t\tformatString: 0\n\n"
            "\tcolumn A\n\t\tdataType: int64\n\t\tsourceColumn: A\n\n"
            "\tcolumn B = IF('EN ESPERA'[A] > 1, 1, 0)\n\t\tsummarizeBy: sum\n\n"
            "\tpartition 'EN ESPERA' = m\n\t\tmode: directQuery\n\t\tsource =\n"
            "\t\t\t\tlet\n\t\t\t\t    Origen = Sql.Database(\"s\", \"d\", [Query=\"SELECT A FROM T\"])\n"
            "\t\t\t\tin\n\t\t\t\t    Origen\n\n"
            "\tannotation PBI_ResultType = Table\n"
        )
        t = pbip._parsear_tabla_tmdl(texto)
        self.assertEqual(t["nombre"], "EN ESPERA")
        self.assertEqual(t["columnas"], ["A", "B"])
        self.assertEqual(t["calculadas"], {"B": "IF('EN ESPERA'[A] > 1, 1, 0)"})
        self.assertEqual(t["medidas"], {"Total X": "VAR a = 1\nRETURN a"})
        self.assertEqual(t["particiones"][0]["modo"], "directQuery")
        self.assertEqual(pbip._analizar_m(t["particiones"][0]["fuente"])["sql"], "SELECT A FROM T")

    def test_colores_y_rangos(self):
        self.assertEqual(pbip._nombre_color("'#48F579'"), "verde")
        self.assertEqual(pbip._nombre_color("#E8D166"), "amarillo")
        self.assertEqual(pbip._nombre_color("#F65B40"), "rojo")
        r = pbip._rango([(2, 31, None), (3, 1000, None)])
        self.assertEqual(pbip._texto_rango(r), "≥31")
        self.assertEqual(pbip._huecos([{"min": 0, "max": 15, "min_incluido": True, "max_incluido": True},
                                        {"min": 16, "max": 30, "min_incluido": False, "max_incluido": True}]), ["16"])

    def test_columna_de_relacion(self):
        self.assertEqual(pbip._columna_rel("'EN ESPERA'.'FECHA X'"), ("EN ESPERA", "FECHA X"))
        self.assertEqual(pbip._columna_rel("T.FECHA"), ("T", "FECHA"))


@unittest.skipIf(PBIP_REAL is None, "No está el PBIP de tablero_tiempos_urgencias")
class HechosRealesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hechos = pbip.extraer_hechos(PBIP_REAL)

    def test_paginas_y_visibilidad(self):
        paginas = self.hechos["paginas"]
        self.assertEqual(len(paginas), 31)
        self.assertEqual([p["nombre"] for p in paginas if p["visible"]], ["RESUMEN_D"])
        self.assertEqual(paginas[0]["nombre"], "RESUMEN_D")
        self.assertEqual([p["orden"] for p in paginas], list(range(1, 32)))
        # Dos páginas «INTERCONSULTAS» distintas por id.
        ids = [p["id"] for p in paginas if p["nombre"] == "INTERCONSULTAS"]
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)
        json.dumps(self.hechos)  # serializable

    def test_agregacion_real_de_tarjetas(self):
        resumen = _pagina(self.hechos, "RESUMEN_D")
        campos = [c for v in resumen["visuales"] if v["tipo"] == "card" for c in v["campos"]]
        self.assertIn("AVERAGE(TRIAGES_DIA[TIEMPO_PARA_TRIAGE_DIA])", campos)
        # El queryRef dice Min pero la función es 4 (MAX).
        self.assertIn("MAX(TRIAGES_DIA[FECHA])", campos)

    def test_botones_y_destinos(self):
        resumen = _pagina(self.hechos, "RESUMEN_D")
        destinos = {v["destino"] for v in resumen["visuales"] if v["tipo"] == "actionButton"}
        self.assertIn("CONSULTAS DIA", destinos)
        self.assertIn("TIEMPOS TRIAGE DIA", destinos)

    def test_semaforo_triage(self):
        pagina = _pagina(self.hechos, "TIEMPOS TRIAGE DIA")
        tabla = next(v for v in pagina["visuales"] if v["titulo"] == "EN ESPERA TRIAGE")
        self.assertEqual(tabla["semaforo"], ["TIEMPO EN ESPERA: verde 0–15", "TIEMPO EN ESPERA: amarillo 16–30",
                                             "TIEMPO EN ESPERA: rojo ≥31"])
        # La regla heredada sobre TRIAGES_DIA[MIN] (columna ausente del visual) se ignora.
        self.assertTrue(all(r["evalua"] != "SUM(TRIAGES_DIA[MIN])" for r in tabla["formato_condicional"]))

    def test_filtros_legibles(self):
        pagina = _pagina(self.hechos, "CONSULTAS DIA")
        filtros = [f for v in pagina["visuales"] for f in v["filtros"]]
        self.assertIn("EN_ESPERA_CONSULTA[TRIAGE_II] = 1", filtros)
        self.assertIn("CONSULTAS_DIA[HORA_CONSULTA] no está vacío", filtros)
        self.assertEqual(pagina["obtener_detalles"], ["CONSULTAS_DIA[HORA_CONSULTA]"])

    def test_textos(self):
        pagina = _pagina(self.hechos, "CONSULTAS DIA")
        textos = [v["texto"] for v in pagina["visuales"] if v["tipo"] == "textbox"]
        self.assertTrue(any("0-60 MINUTOS" in t for t in textos))

    def test_tablas_medidas_y_relaciones(self):
        tablas = self.hechos["tablas"]
        self.assertEqual(sum(1 for t in tablas.values() if t["modo"] == "DirectQuery"), 17)
        self.assertFalse(any(pbip._es_automatica(t) for t in tablas))
        consultas = tablas["CONSULTAS_DIA"]
        self.assertEqual(consultas["base_datos"], "DWSES")
        self.assertIn("FROM DIM_TRIAGE", consultas["sql"])
        self.assertNotIn("#(lf)", consultas["sql"])
        self.assertEqual(consultas["calculadas"]["TRIAGE_II"], 'IF(CONSULTAS_DIA[HCCODIGO]="II",1,0)')
        self.assertEqual(tablas["Calendario"]["origen"], "DAX")
        self.assertEqual(self.hechos["medidas"]["INTERCONSULTA[%ATENDIDO]"],
                         "SUM(INTERCONSULTA[RESPUESTAS])/SUM(INTERCONSULTA[SOLICITUDES])")
        self.assertIn("OBSERV_HIST[INGRESO] -> IMAGENES[INGRESO] (inactiva)", self.hechos["relaciones"])

    def test_comparar_igual_es_vacio(self):
        self.assertEqual(pbip.comparar(self.hechos, self.hechos), [])
        copia = json.loads(json.dumps(self.hechos))  # como si viniera de la instantánea
        self.assertEqual(pbip.comparar(copia, self.hechos), [])


@unittest.skipIf(PBIP_REAL is None, "No está el PBIP de tablero_tiempos_urgencias")
class CompararTest(unittest.TestCase):
    """Copia el PBIP, cambia varios visual.json y el modelo, y verifica las frases."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="pbip_prueba_")
        cls.ruta = _copiar_pbip(PBIP_REAL, Path(cls.tmp))
        cls.antes = pbip.extraer_hechos(cls.ruta)
        paginas = cls.ruta / f"{NOMBRE}.Report" / "definition" / "pages"
        modelo = cls.ruta / f"{NOMBRE}.SemanticModel" / "definition" / "tables"

        def ids(nombre):
            return _pagina(cls.antes, nombre)["id"]

        def editar(archivo: Path, funcion):
            datos = json.loads(archivo.read_text(encoding="utf-8"))
            funcion(datos)
            archivo.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")

        def visual(pagina, condicion):
            p = _pagina(cls.antes, pagina)
            v = next(v for v in p["visuales"] if condicion(v))
            return paginas / p["id"] / "visuals" / v["id"] / "visual.json"

        # 1. Umbral del semáforo: verde 0–15 -> 0–20 y amarillo 16–30 -> 21–30.
        archivo = visual("TIEMPOS TRIAGE DIA", lambda v: v["titulo"] == "EN ESPERA TRIAGE")
        texto = archivo.read_text(encoding="utf-8")
        texto = texto.replace('"Value": "15D"', '"Value": "20D"').replace('"Value": "16D"', '"Value": "21D"')
        archivo.write_text(texto, encoding="utf-8")

        # 2. Quitar el filtro «HORA_CONSULTA no está vacío» de la primera tabla CONSULTAS REALIZADAS.
        archivo = visual("CONSULTAS DIA", lambda v: v["titulo"] == "CONSULTAS REALIZADAS")
        editar(archivo, lambda d: d["filterConfig"].__setitem__("filters", [
            f for f in d["filterConfig"]["filters"] if f["field"]["Column"]["Property"] != "HORA_CONSULTA"]))

        # 3. Agregación de la tarjeta de triage: AVERAGE (1) -> MAX (4).
        archivo = visual("RESUMEN_D", lambda v: v["campos"] == ["AVERAGE(TRIAGES_DIA[TIEMPO_PARA_TRIAGE_DIA])"])
        editar(archivo, lambda d: d["visual"]["query"]["queryState"]["Values"]["projections"][0]["field"]
               ["Aggregation"].__setitem__("Function", 4))

        # 4. Visual nuevo: copia de la tarjeta de fecha con otro id y otra columna.
        origen = visual("RESUMEN_D", lambda v: v["campos"] == ["MAX(TRIAGES_DIA[FECHA])"])
        nuevo = paginas / ids("RESUMEN_D") / "visuals" / "nuevo0000000000000001"
        nuevo.mkdir()
        datos = json.loads(origen.read_text(encoding="utf-8"))
        datos["name"] = "nuevo0000000000000001"
        proy = datos["visual"]["query"]["queryState"]["Values"]["projections"][0]
        proy["field"]["Aggregation"]["Expression"]["Column"]["Property"] = "TIEMPO_PARA_TRIAGE_DIA"
        proy["field"]["Aggregation"]["Function"] = 3
        proy["nativeQueryRef"] = "TIEMPO MÍNIMO PARA TRIAGE"
        (nuevo / "visual.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")

        # 5. Renombrar una página.
        editar(paginas / ids("TIEMPOS TRIAGE DIA") / "page.json",
               lambda d: d.__setitem__("displayName", "TIEMPOS DE TRIAGE DIA"))

        # 6. SQL: una condición WHERE nueva en CONSULTAS_DIA.
        tmdl = modelo / "CONSULTAS_DIA.tmdl"
        texto = tmdl.read_text(encoding="utf-8")
        texto = texto.replace("HCCODIGO NOT IN ('UA') and", "HCCODIGO NOT IN ('UA','M') and", 1)
        tmdl.write_text(texto, encoding="utf-8")

        # 7. Medida cambiada y medida nueva.
        tmdl = modelo / "INTERCONSULTA.tmdl"
        texto = tmdl.read_text(encoding="utf-8")
        texto = texto.replace("measure %ATENDIDO = SUM(INTERCONSULTA[RESPUESTAS])/SUM(INTERCONSULTA[SOLICITUDES])",
                              "measure %ATENDIDO = DIVIDE(SUM(INTERCONSULTA[RESPUESTAS]),SUM(INTERCONSULTA[SOLICITUDES]))\n"
                              "\t\tformatString: 0\n\n"
                              "\tmeasure 'TOTAL SOLICITUDES' = SUM(INTERCONSULTA[SOLICITUDES])", 1)
        tmdl.write_text(texto, encoding="utf-8")

        cls.despues = pbip.extraer_hechos(cls.ruta)
        cls.cambios = pbip.comparar(cls.antes, cls.despues)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _hay(self, *fragmentos):
        for frase in self.cambios:
            if all(f in frase for f in fragmentos):
                return frase
        self.fail(f"No aparece {fragmentos} en:\n" + "\n".join(self.cambios))

    def test_umbral_del_semaforo(self):
        frase = self._hay("cambió el semáforo de TIEMPO EN ESPERA", "verde 0–15", "verde 0–20", "amarillo 21–30")
        self.assertIn("Tabla «EN ESPERA TRIAGE»", frase)

    def test_filtro_quitado(self):
        self._hay("Página CONSULTAS DIA", "CONSULTAS REALIZADAS", "se quitó el filtro «CONSULTAS_DIA[HORA_CONSULTA] no está vacío»")

    def test_agregacion(self):
        self._hay("Página RESUMEN_D", "la agregación de TRIAGES_DIA[TIEMPO_PARA_TRIAGE_DIA] cambió de AVERAGE a MAX")

    def test_visual_agregado(self):
        self._hay("Página RESUMEN_D: se agregó el visual Tarjeta «TIEMPO MÍNIMO PARA TRIAGE»",
                  "MIN(TRIAGES_DIA[TIEMPO_PARA_TRIAGE_DIA])")

    def test_pagina_renombrada(self):
        self._hay("Se renombró la página TIEMPOS TRIAGE DIA a «TIEMPOS DE TRIAGE DIA»")
        # Los cambios de sus visuales se nombran con el nombre nuevo.
        self._hay("Página TIEMPOS DE TRIAGE DIA, Tabla «EN ESPERA TRIAGE»")

    def test_sql_y_medidas(self):
        self._hay("Cambió la sentencia SQL de la tabla CONSULTAS_DIA", "nuevas", "('UA','M')", "quitadas", "('UA')")
        self._hay("Cambió la medida INTERCONSULTA[%ATENDIDO]", "DIVIDE(")
        self._hay("Nueva medida INTERCONSULTA[TOTAL SOLICITUDES] = SUM(INTERCONSULTA[SOLICITUDES])")

    def test_sin_ruido(self):
        # Solo los cambios hechos: 1 semáforo + 1 filtro + 1 agregación + 1 visual + 1 renombre + SQL + 2 medidas.
        self.assertEqual(len(self.cambios), 8, "\n".join(self.cambios))

    def test_instantanea(self):
        raiz = Path(self.tmp) / "docs"
        ruta = pbip.guardar_instantanea(self.antes, "grupo_prueba", raiz)
        self.assertTrue(ruta.exists())
        self.assertEqual(pbip.cambios_desde_instantanea(self.ruta, "grupo_prueba", raiz), self.cambios)
        self.assertEqual(pbip.cambios_desde_instantanea(self.ruta, "otro_grupo", raiz), [])


@unittest.skipIf(PBIP_REAL is None, "No está el PBIP de tablero_tiempos_urgencias")
class EsqueletoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archivos = pbip.esqueleto(PBIP_REAL, NOMBRE, "tablero_tiempos_urgencias")

    def test_todos_validan(self):
        self.assertEqual(len(self.archivos), 32)  # 31 páginas + _general.md
        for nombre, texto in self.archivos.items():
            with self.subTest(archivo=nombre):
                self.assertEqual(F.validar(texto), [])
                doc = F.parsear(texto)
                self.assertEqual(F.serializar(doc), texto)  # forma canónica

    def test_nombres_de_archivo_y_repetidas(self):
        self.assertIn("_general.md", self.archivos)
        self.assertIn("consultas_dia.md", self.archivos)
        self.assertIn("interconsultas.md", self.archivos)
        self.assertIn("interconsultas_2.md", self.archivos)
        doc = F.parsear(self.archivos["interconsultas_2.md"])
        self.assertEqual(doc.pagina, "INTERCONSULTAS (2)")
        self.assertTrue(doc.meta["id_pagina"])

    def test_contenido_deducido(self):
        doc = F.parsear(self.archivos["consultas_dia.md"])
        self.assertTrue(doc.proposito.startswith("Por confirmar."))
        self.assertEqual(doc.meta["bloque"], "Día")
        self.assertIn("DirectQuery", doc.buscar("Fuentes de datos", "CONSULTAS_DIA").texto)
        semaforo = doc.buscar("Reglas de negocio", "Semáforo TIEMPO EN ESPERA")
        self.assertIn("Verde de 0 a 15, amarillo de 16 a 30 y rojo de 31 o más", semaforo.texto)
        self.assertIn("16 y 31", doc.buscar("Observaciones", "Huecos en el semáforo TIEMPO DE ESPERA").texto)
        general = F.parsear(self.archivos["_general.md"])
        self.assertEqual(general.meta["bloque"], "General")
        self.assertIsNotNone(general.buscar("Definiciones", "INTERCONSULTA[%ATENDIDO]"))


@unittest.skipIf(PBIX_REAL is None, "No está TABLERO_FINANCIERA.pbix")
class PbixTest(unittest.TestCase):
    """El .pbix se lee sin extraer y sin abrir nunca la entrada DataModel."""

    @classmethod
    def setUpClass(cls):
        cls.pedidas = []
        original = zipfile.ZipFile.open
        pedidas = cls.pedidas

        def abrir_vigilado(self, name, *args, **kwargs):
            nombre = name.filename if isinstance(name, zipfile.ZipInfo) else name
            pedidas.append(nombre)
            if nombre == "DataModel" or not nombre.startswith("Report/"):
                raise AssertionError(f"Se intentó abrir la entrada prohibida «{nombre}» del .pbix")
            return original(self, name, *args, **kwargs)

        prohibido = mock.Mock(side_effect=AssertionError("No se extrae el .pbix a disco"))
        with mock.patch.object(zipfile.ZipFile, "open", abrir_vigilado), \
                mock.patch.object(zipfile.ZipFile, "extract", prohibido), \
                mock.patch.object(zipfile.ZipFile, "extractall", prohibido):
            cls.hechos = pbip.extraer_hechos(PBIX_REAL)
            cls.archivos = pbip.esqueleto(PBIX_REAL, "TABLERO FINANCIERA", "tablero_financiera")

    def test_no_toca_datamodel(self):
        self.assertTrue(self.pedidas)
        self.assertNotIn("DataModel", self.pedidas)
        self.assertTrue(all(n.startswith("Report/") for n in self.pedidas))

    def test_paginas_y_visuales(self):
        h = self.hechos
        self.assertFalse(h["modelo_disponible"])
        self.assertEqual(h["tablero"], "TABLERO_FINANCIERA")
        self.assertGreater(len(h["paginas"]), 5)
        self.assertGreater(sum(len(p["visuales"]) for p in h["paginas"]), 50)
        inicio = h["paginas"][0]
        self.assertEqual(inicio["nombre"], "INICIO")
        self.assertTrue(inicio["visible"])
        self.assertTrue(any(v["tipo"] == "card" and v["campos"] for v in inicio["visuales"]))
        self.assertTrue(any(v["destino"] for v in inicio["visuales"]))
        json.dumps(h)

    def test_tablas_solo_con_nombres(self):
        self.assertTrue(self.hechos["tablas"])
        for datos in self.hechos["tablas"].values():
            self.assertIsNone(datos["modo"])
            self.assertIsNone(datos["sql"])
        self.assertTrue(all(dax is None for dax in self.hechos["medidas"].values()))
        self.assertEqual(self.hechos["relaciones"], [])
        self.assertEqual(pbip.comparar(self.hechos, self.hechos), [])

    def test_esqueleto_valido(self):
        self.assertEqual(len(self.archivos), len(self.hechos["paginas"]) + 1)
        for nombre, texto in self.archivos.items():
            with self.subTest(archivo=nombre):
                self.assertEqual(F.validar(texto), [])
        general = F.parsear(self.archivos["_general.md"])
        self.assertIsNotNone(general.buscar("Observaciones", "Modelo no disponible"))


if __name__ == "__main__":
    unittest.main()

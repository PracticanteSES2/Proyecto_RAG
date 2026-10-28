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
import time
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


# ---------------------------------------------------------------------------
# Fixtures sintéticos (sin datos reales) para TMDL y PBIR
# ---------------------------------------------------------------------------

def _escribir(ruta: Path, texto: str):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8", newline="")


def _lit(valor: str) -> dict:
    return {"expr": {"Literal": {"Value": valor}}}


def _col(tabla: str, col: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": tabla}}, "Property": col}}


def _med(tabla: str, med: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": tabla}}, "Property": med}}


def _visual_json(nombre, tipo, x=0, y=0, proyecciones=None, **extra) -> str:
    datos = {"name": nombre, "position": {"x": x, "y": y, "width": 100, "height": 50},
             "visual": {"visualType": tipo}}
    if proyecciones:
        datos["visual"]["query"] = {"queryState": {"Values": {"projections": [
            {"field": f, "queryRef": f"q{i}", "nativeQueryRef": f"campo{i}"} for i, f in enumerate(proyecciones)]}}}
    for clave in ("visualContainerObjects", "objects"):
        if clave in extra:
            datos["visual"][clave] = extra.pop(clave)
    datos.update(extra)
    return json.dumps(datos)


TMDL_VENTAS = (
    "/// Hechos de ventas del día.\n"
    "table 'Mi ''Tabla'''\n"
    "\tlineageTag: aaaa\n\n"
    "\t/// Total vendido sin impuestos.\n"
    "\tmeasure 'Total Ventas' = ```\n"
    "\t\t\t\n"
    "\t\t\tVAR a = SUM('Mi ''Tabla'''[Monto])  // comentario con `backticks`\n"
    "\t\t\tRETURN a\n"
    "\t\t\t```\n"
    "\t\tformatString: #,0.00\n"
    "\t\tdisplayFolder: Finanzas\\Ventas\n"
    "\t\tisHidden\n"
    "\t\tlineageTag: bbbb\n\n"
    "\tmeasure Corta = SUM('Mi ''Tabla'''[Monto])\n"
    "\t\tformatString: 0\n\n"
    "\tmeasure Continua = DIVIDE(\n"
    "\t\t\t[Total Ventas],\n"
    "\t\t\t2)\n"
    "\t\tdescription: Mitad del total\n\n"
    "\tmeasure A_mano =\n"
    "\t\tCALCULATE([Corta], ALL('Mi ''Tabla'''))\n"
    "\t\tformatString: 0.0\n\n"
    "\t/// Monto en pesos.\n"
    "\tcolumn Monto\n"
    "\t\tdataType: double\n"
    "\t\tisHidden\n"
    "\t\tsummarizeBy: sum\n"
    "\t\tsourceColumn: MONTO_SQL\n"
    "\t\tformatString: #,0\n\n"
    "\tcolumn Doble = [Monto] * 2\n"
    "\t\tdataType: double\n"
    "\t\tdisplayFolder: Calculadas\n"
    "\t\tsummarizeBy: none\n\n"
    "\thierarchy Jerarquía\n"
    "\t\tlineageTag: cccc\n\n"
    "\t\tlevel Año\n"
    "\t\t\tcolumn: Año\n\n"
    "\t\tlevel Mes\n"
    "\t\t\tcolumn: Mes\n\n"
    "\tpartition 'Mi ''Tabla''' = m\n"
    "\t\tmode: directQuery\n"
    "\t\tsource =\n"
    "\t\t\t\tlet\n"
    "\t\t\t\t    Origen = Sql.Database(\"srv\\inst\", \"DWX\", [Query=\"SELECT MONTO_SQL FROM T WHERE X = 1\", "
    "CommandTimeout=#duration(0,0,5,0)]),\n"
    "\t\t\t\t    Filtrado = Table.SelectRows(Origen, each [Monto] > 0)\n"
    "\t\t\t\tin\n"
    "\t\t\t\t    Filtrado\n\n"
    "\tannotation PBI_ResultType = Table\n"
)

TMDL_CALCULADA = (
    "table Calendario\n"
    "\tcolumn Fecha\n"
    "\t\tdataType: dateTime\n"
    "\t\ttype: calculatedTableColumn\n"
    "\t\tsourceColumn: [Date]\n\n"
    "\tcolumn Año = YEAR(Calendario[Fecha])\n"
    "\t\tdataType: int64\n\n"
    "\tpartition Calendario = calculated\n"
    "\t\tmode: import\n"
    "\t\tsource = CALENDAR(DATE(2020,1,1), TODAY())\n"
)

TMDL_ORIGENES = (
    "table Excel\n"
    "\tcolumn A\n\t\tdataType: string\n\n"
    "\tpartition Excel = m\n"
    "\t\tmode: import\n"
    "\t\tsource =\n"
    "\t\t\t\tlet\n"
    "\t\t\t\t    Origen = Excel.Workbook(Web.Contents(\"https://ejemplo.sharepoint.com/sitio/libro.xlsx\"), null, true)\n"
    "\t\t\t\tin\n"
    "\t\t\t\t    Origen\n\n"
    "table Secreta\n"
    "\tcolumn A\n\t\tdataType: string\n\n"
    "\tpartition Secreta = m\n"
    "\t\tmode: import\n"
    "\t\tsource =\n"
    "\t\t\t\tlet\n"
    "\t\t\t\t    Origen = Odbc.DataSource(\"Driver=X;Server=s;User ID=pepe;Password=Clave123;\", [HierarchicalNavigation=true]),\n"
    "\t\t\t\t    Web = Web.Contents(\"https://u:clave@host/api?token=abc123&x=1\", [Headers=[Authorization=\"Bearer zzz\"]])\n"
    "\t\t\t\tin\n"
    "\t\t\t\t    Origen\n\n"
    "table Derivada\n"
    "\tcolumn A\n\t\tdataType: string\n\n"
    "\tpartition Derivada = m\n"
    "\t\tmode: import\n"
    "\t\tsource =\n"
    "\t\t\t\tlet\n"
    "\t\t\t\t    Origen = Excel,\n"
    "\t\t\t\t    Quitar = Table.RemoveColumns(Origen, {\"B\"})\n"
    "\t\t\t\tin\n"
    "\t\t\t\t    Quitar\n\n"
    "table Lago\n"
    "\tcolumn A\n\t\tdataType: string\n\n"
    "\tpartition Lago = entity\n"
    "\t\tmode: directLake\n"
    "\t\tsource\n"
    "\t\t\tentityName: dim_lago\n"
    "\t\t\tschemaName: dbo\n"
    "\t\t\texpressionSource: DatabaseQuery\n"
)

TMDL_REL = (
    "relationship r1\n"
    "\tfromColumn: 'Mi ''Tabla'''.Monto\n"
    "\ttoColumn: Calendario.Fecha\n\n"
    "relationship r2\n"
    "\tisActive: false\n"
    "\tcrossFilteringBehavior: bothDirections\n"
    "\tfromCardinality: one\n"
    "\ttoCardinality: one\n"
    "\tfromColumn: Excel.A\n"
    "\ttoColumn: Derivada.A\n\n"
    "relationship r3\n"
    "\tfromColumn: LocalDateTable_1234.Date\n"
    "\ttoColumn: Excel.A\n"
)


def _modelo_sintetico(base: Path, nombre="DEMO") -> Path:
    modelo = base / f"{nombre}.SemanticModel" / "definition"
    _escribir(modelo / "tables" / "Mi Tabla.tmdl", TMDL_VENTAS)
    _escribir(modelo / "tables" / "Calendario.tmdl", TMDL_CALCULADA)
    _escribir(modelo / "tables" / "Origenes.tmdl", TMDL_ORIGENES)
    _escribir(modelo / "tables" / "LocalDateTable_1234.tmdl",
              "table LocalDateTable_1234\n\tcolumn Date\n\t\tisHidden\n\t\tdataType: dateTime\n")
    _escribir(modelo / "relationships.tmdl", TMDL_REL)
    _escribir(modelo / "model.tmdl",
              "/// Modelo de prueba del hospital.\nmodel Model\n\tculture: es-CO\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\n"
              "annotation PBI_QueryOrder = [\"A\"]\n")
    _escribir(modelo / "expressions.tmdl",
              "/// Parámetro del servidor.\nexpression Servidor = \"srv\" meta [IsParameterQuery=true, Type=\"Text\"]\n"
              "\tlineageTag: x\n\nexpression Consulta =\n\t\t\tlet\n\t\t\t    Origen = Sql.Database(\"s\", \"d\")\n\t\t\tin\n\t\t\t    Origen\n"
              "\tlineageTag: y\n")
    _escribir(modelo / "roles" / "Lector.tmdl",
              "role Lector\n\tmodelPermission: read\n\n\ttablePermission Excel = [A] = \"x\"\n")
    return base / f"{nombre}.SemanticModel"


def _informe_sintetico(base: Path, nombre="DEMO") -> Path:
    informe = base / f"{nombre}.Report"
    d = informe / "definition"
    _escribir(informe / "definition.pbir", json.dumps({"version": "4.0", "datasetReference": {
        "byPath": {"path": f"../{nombre}.SemanticModel"}}}))
    _escribir(d / "report.json", json.dumps({"filterConfig": {"filters": [{
        "name": "f", "field": _col("Excel", "A"), "type": "Categorical",
        "filter": {"Version": 2, "From": [{"Name": "e", "Entity": "Excel", "Type": 0}], "Where": [{"Condition": {"In": {
            "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "e"}}, "Property": "A"}}],
            "Values": [[{"Literal": {"Value": "'ok'"}}]]}}}]}}]}}))
    _escribir(d / "pages" / "pages.json", json.dumps({"pageOrder": ["inicio", "detalle", "tip", "vacia"]}))
    _escribir(d / "pages" / "inicio" / "page.json", json.dumps({
        "name": "inicio", "displayName": "INICIO",
        "filterConfig": {"filters": [{
            "name": "fp", "field": _col("Mi 'Tabla'", "Monto"), "type": "Advanced",
            "filter": {"Version": 2, "From": [{"Name": "m", "Entity": "Mi 'Tabla'", "Type": 0}], "Where": [{"Condition": {
                "Comparison": {"ComparisonKind": 1, "Left": {"Column": {"Expression": {"SourceRef": {"Source": "m"}},
                                                                        "Property": "Monto"}},
                               "Right": {"Literal": {"Value": "0L"}}}}}]}}]}}))
    v = d / "pages" / "inicio" / "visuals"
    # Tarjeta de varios campos (medida y columna agregada) con título y filtro de visual.
    agregada = {"Aggregation": {"Expression": _col("Mi 'Tabla'", "Monto"), "Function": 1}}
    _escribir(v / "tarjeta" / "visual.json", _visual_json(
        "tarjeta", "multiRowCard", x=0, y=0, proyecciones=[_med("Mi 'Tabla'", "Total Ventas"), agregada],
        visualContainerObjects={"title": [{"properties": {"text": _lit("'Ventas del día'")}}],
                                "general": [{"properties": {"altText": _lit("'Resumen'")}}]},
        filterConfig={"filters": [{"name": "fv", "field": _col("Excel", "A"), "type": "Categorical", "filter": {
            "Version": 2, "From": [{"Name": "e", "Entity": "Excel", "Type": 0}], "Where": [{"Condition": {"Not": {
                "Expression": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "e"}},
                                                                   "Property": "A"}}],
                                      "Values": [[{"Literal": {"Value": "null"}}]]}}}}}]}}]}))
    # Segmentador de lista desplegable.
    _escribir(v / "seg" / "visual.json", _visual_json(
        "seg", "slicer", x=200, y=0, proyecciones=[_col("Excel", "A")],
        objects={"data": [{"properties": {"mode": _lit("'Dropdown'")}}],
                 "selection": [{"properties": {"singleSelect": _lit("true")}}]}))
    # Grupo oculto que contiene un botón hacia un marcador.
    _escribir(v / "grupo" / "visual.json", json.dumps({
        "name": "grupo", "position": {"x": 0, "y": 100, "width": 50, "height": 50},
        "visualGroup": {"displayName": "Navegación", "groupMode": "ScaleMode"}, "isHidden": True}))
    _escribir(v / "boton" / "visual.json", _visual_json(
        "boton", "actionButton", x=0, y=100, parentGroupName="grupo",
        visualContainerObjects={"visualLink": [{"properties": {
            "show": _lit("true"), "type": _lit("'Bookmark'"), "bookmark": _lit("'marca1'")}}]}))
    _escribir(v / "boton2" / "visual.json", _visual_json(
        "boton2", "actionButton", x=100, y=100,
        visualContainerObjects={"visualLink": [{"properties": {
            "show": _lit("true"), "type": _lit("'PageNavigation'"), "navigationSection": _lit("'detalle'")}}]}))
    # Tabla con formato condicional por valor de un campo (color que devuelve una medida).
    _escribir(v / "tabla" / "visual.json", _visual_json(
        "tabla", "tableEx", x=0, y=200, proyecciones=[_col("Excel", "A"), _med("Mi 'Tabla'", "Corta")],
        objects={"values": [{"selector": {"metadata": "q1"}, "properties": {
            "backColor": {"solid": {"color": {"expr": _med("Mi 'Tabla'", "Corta")}}}}}]}))
    # Visual personalizado con identificador hexadecimal.
    _escribir(v / "cust" / "visual.json", _visual_json("cust", "textFilter" + "A" * 32, x=300, y=200,
                                                       proyecciones=[_col("Excel", "A")]))
    # JSON dañado: se anota y el resto del informe se lee.
    _escribir(v / "roto" / "visual.json", "{ esto no es json")
    _escribir(d / "pages" / "detalle" / "page.json", json.dumps({
        "name": "detalle", "displayName": "DETALLE", "visibility": "HiddenInViewMode",
        "pageBinding": {"name": "pb", "type": "Drillthrough", "parameters": []},
        "filterConfig": {"filters": [{"name": "dt", "field": _col("Excel", "A"), "type": "Categorical",
                                      "howCreated": "Drillthrough"}]}}))
    _escribir(d / "pages" / "tip" / "page.json", json.dumps({"name": "tip", "displayName": "TIP", "type": "Tooltip",
                                                          "visibility": "HiddenInViewMode"}))
    _escribir(d / "pages" / "vacia" / "page.json", json.dumps({"name": "vacia", "displayName": "VACÍA"}))
    _escribir(d / "bookmarks" / "bookmarks.json", json.dumps({"items": [{"name": "marca1"}]}))
    _escribir(d / "bookmarks" / "marca1.bookmark.json", json.dumps({
        "name": "marca1", "displayName": "Vista detalle", "options": {"targetVisualNames": ["tarjeta"]},
        "explorationState": {"version": "1.3", "activeSection": "detalle"}}))
    return informe


class TmdlSinteticoTest(unittest.TestCase):
    """TMDL con comillas, backticks, /// y propiedades; sin datos reales."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="pbip_sint_")
        cls.base = Path(cls.tmp)
        _modelo_sintetico(cls.base)
        _informe_sintetico(cls.base)
        cls.hechos = pbip.extraer_hechos(cls.base)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_medidas_con_todos_sus_atributos(self):
        m = self.hechos["medidas_detalle"]["Mi 'Tabla'[Total Ventas]"]
        self.assertEqual(m["tabla"], "Mi 'Tabla'")
        self.assertEqual(m["formato"], "#,0.00")
        self.assertEqual(m["carpeta"], "Finanzas\\Ventas")
        self.assertTrue(m["oculta"])
        self.assertEqual(m["descripcion"], "Total vendido sin impuestos.")
        self.assertIn("RETURN a", m["dax"])
        self.assertIn("`backticks`", m["dax"])
        self.assertTrue(m["dax"].startswith("VAR a"))
        # `medidas` conserva el contrato: «T[m]» -> DAX.
        self.assertEqual(self.hechos["medidas"]["Mi 'Tabla'[Total Ventas]"], m["dax"])

    def test_medidas_de_una_linea_continuas_y_a_mano(self):
        med = self.hechos["medidas_detalle"]
        self.assertEqual(med["Mi 'Tabla'[Corta]"]["dax"], "SUM('Mi ''Tabla'''[Monto])")
        self.assertEqual(med["Mi 'Tabla'[Corta]"]["formato"], "0")
        self.assertFalse(med["Mi 'Tabla'[Corta]"]["oculta"])
        # Expresión que sigue en líneas más indentadas.
        self.assertEqual(med["Mi 'Tabla'[Continua]"]["dax"], "DIVIDE(\n[Total Ventas],\n2)")
        self.assertEqual(med["Mi 'Tabla'[Continua]"]["descripcion"], "Mitad del total")
        # Cuerpo escrito a mano un nivel por debajo de las propiedades.
        self.assertEqual(med["Mi 'Tabla'[A_mano]"]["dax"], "CALCULATE([Corta], ALL('Mi ''Tabla'''))")
        self.assertEqual(med["Mi 'Tabla'[A_mano]"]["formato"], "0.0")

    def test_columnas(self):
        t = self.hechos["tablas"]["Mi 'Tabla'"]
        cols = {c["nombre"]: c for c in t["columnas_detalle"]}
        self.assertEqual(t["columnas"], ["Monto", "Doble"])
        self.assertTrue(cols["Monto"]["oculta"])
        self.assertFalse(cols["Monto"]["calculada"])
        self.assertEqual(cols["Monto"]["tipo"], "double")
        self.assertEqual(cols["Monto"]["resumen_por"], "sum")
        self.assertEqual(cols["Monto"]["columna_origen"], "MONTO_SQL")
        self.assertEqual(cols["Monto"]["descripcion"], "Monto en pesos.")
        self.assertEqual(cols["Monto"]["formato"], "#,0")
        self.assertTrue(cols["Doble"]["calculada"])
        self.assertEqual(cols["Doble"]["dax"], "[Monto] * 2")
        self.assertEqual(cols["Doble"]["carpeta"], "Calculadas")
        self.assertEqual(t["calculadas"], {"Doble": "[Monto] * 2"})

    def test_tabla_modo_origen_particion_y_jerarquia(self):
        t = self.hechos["tablas"]["Mi 'Tabla'"]
        self.assertEqual(t["modo"], "DirectQuery")
        self.assertEqual(t["descripcion"], "Hechos de ventas del día.")
        self.assertEqual((t["origen"], t["servidor"], t["base_datos"]), ("Sql.Database", "srv\\inst", "DWX"))
        self.assertEqual(t["sql"], "SELECT MONTO_SQL FROM T WHERE X = 1")
        self.assertFalse(t["calculada"])
        self.assertEqual(t["particiones"], [{"nombre": "Mi 'Tabla'", "tipo": "m", "modo": "DirectQuery"}])
        self.assertEqual(t["jerarquias"], [{"nombre": "Jerarquía", "oculta": False, "niveles": ["Año", "Mes"]}])
        self.assertEqual(t["medidas"], ["Total Ventas", "Corta", "Continua", "A_mano"])
        self.assertIn("SQL Server", t["origen_resumen"])
        self.assertIn("DWX", t["origen_resumen"])

    def test_tabla_calculada_y_columnas_de_tabla_calculada(self):
        t = self.hechos["tablas"]["Calendario"]
        self.assertTrue(t["calculada"])
        self.assertEqual(t["origen"], "DAX")
        self.assertEqual(t["dax"], "CALENDAR(DATE(2020,1,1), TODAY())")
        cols = {c["nombre"]: c for c in t["columnas_detalle"]}
        # Las columnas de una tabla calculada no son «columnas calculadas»; la que tiene = sí.
        self.assertFalse(cols["Fecha"]["calculada"])
        self.assertEqual(cols["Fecha"]["columna_origen"], "[Date]")
        self.assertTrue(cols["Año"]["calculada"])
        self.assertEqual(cols["Año"]["dax"], "YEAR(Calendario[Fecha])")

    def test_origenes_distintos(self):
        t = self.hechos["tablas"]
        self.assertEqual(t["Excel"]["origen"], "Excel.Workbook")
        self.assertIn("sitio ejemplo.sharepoint.com", t["Excel"]["origen_resumen"])
        # Una consulta que parte de otra no toma «Table.RemoveColumns» como origen.
        self.assertEqual(t["Derivada"]["origen"], "referencia")
        self.assertEqual(t["Derivada"]["referencia"], "Excel")
        self.assertEqual(t["Derivada"]["origen_resumen"], "Referencia a la consulta Excel")
        self.assertEqual(t["Lago"]["modo"], "DirectLake")
        self.assertEqual(t["Lago"]["origen_resumen"], "Entidad dbo.dim_lago")

    def test_no_quedan_credenciales(self):
        s = self.hechos["tablas"]["Secreta"]
        texto = json.dumps(self.hechos, ensure_ascii=False)
        for secreto in ("Clave123", "pepe", "clave@", "abc123", "zzz"):
            self.assertNotIn(secreto, texto)
        self.assertIn("Password=***", s["m"])
        self.assertIn("***@host", s["m"])
        self.assertIn("token=***", s["m"])

    def test_sanear_no_toca_sql_normal(self):
        self.assertEqual(pbip._sanear("SELECT user, pass FROM T WHERE username = 'a'", sql=True),
                         "SELECT user, pass FROM T WHERE username = 'a'")
        self.assertEqual(pbip._sanear("Server=s;Pwd=x;"), "Server=s;Pwd=***;")

    def test_relaciones(self):
        self.assertEqual(self.hechos["relaciones"], [
            "Excel[A] -> Derivada[A] (inactiva) (filtro en ambos sentidos)",
            "Mi 'Tabla'[Monto] -> Calendario[Fecha]",
        ])
        det = {r["desde"]: r for r in self.hechos["relaciones_detalle"]}
        r2 = det["Excel[A]"]
        self.assertFalse(r2["activa"])
        self.assertTrue(r2["ambos_sentidos"])
        self.assertEqual((r2["cardinalidad_desde"], r2["cardinalidad_hacia"]), ("one", "one"))
        self.assertEqual(det["Mi 'Tabla'[Monto]"]["cardinalidad_desde"], "many")

    def test_modelo_expresiones_y_roles(self):
        self.assertEqual(self.hechos["modelo"]["descripcion"], "Modelo de prueba del hospital.")
        self.assertEqual(self.hechos["modelo"]["cultura"], "es-CO")
        self.assertTrue(self.hechos["expresiones"]["Servidor"]["parametro"])
        self.assertEqual(self.hechos["expresiones"]["Servidor"]["descripcion"], "Parámetro del servidor.")
        self.assertEqual(self.hechos["expresiones"]["Consulta"]["base_datos"], "d")
        self.assertEqual(self.hechos["roles"]["Lector"]["permiso"], "read")
        self.assertEqual(self.hechos["roles"]["Lector"]["filtros"], {"Excel": '[A] = "x"'})

    def test_tablas_automaticas_fuera(self):
        self.assertFalse(any(t.startswith("LocalDateTable") for t in self.hechos["tablas"]))
        self.assertFalse(any("LocalDateTable" in r for r in self.hechos["relaciones"]))

    def test_indentacion_con_espacios_y_crlf(self):
        texto = ("table T\r\n    measure M =\r\n            1 + 1\r\n        formatString: 0\r\n\r\n"
                 "    column C\r\n        dataType: string\r\n")
        t = pbip._parsear_tabla_tmdl(texto)
        self.assertEqual(t["medidas"], {"M": "1 + 1"})
        self.assertEqual(t["columnas"], ["C"])
        self.assertEqual(t["detalle"]["medidas_detalle"][0]["formato"], "0")

    def test_backticks_en_una_sola_linea_y_cierre_pegado(self):
        texto = ("table T\n\tmeasure A = ``` 1 + 1 ```\n\t\tformatString: 0\n\n"
                 "\tmeasure B = ```\n\t\t\tSUM(T[x])```\n\t\tdisplayFolder: Z\n")
        t = pbip._parsear_tabla_tmdl(texto)["detalle"]["medidas_detalle"]
        self.assertEqual((t[0]["dax"], t[0]["formato"]), ("1 + 1", "0"))
        self.assertEqual((t[1]["dax"], t[1]["carpeta"]), ("SUM(T[x])", "Z"))

    def test_rendimiento_modelo_grande(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            definicion = base / "G.SemanticModel" / "definition" / "tables"
            for i in range(160):
                medidas = "".join(
                    f"\tmeasure M{j} = ```\n\t\t\tCALCULATE(SUM(T{i}[c{j % 5}]), T{i}[c0] > {j})\n\t\t\t```\n"
                    f"\t\tformatString: 0\n\t\tlineageTag: x\n\n" for j in range(12))
                columnas = "".join(f"\tcolumn c{j}\n\t\tdataType: int64\n\t\tsummarizeBy: sum\n\t\tsourceColumn: c{j}\n\n"
                                   for j in range(30))
                _escribir(definicion / f"T{i}.tmdl", f"table T{i}\n{medidas}{columnas}"
                          f"\tpartition T{i} = m\n\t\tmode: import\n\t\tsource =\n\t\t\t\tlet\n"
                          f"\t\t\t\t    Origen = Sql.Database(\"s\", \"d\", [Query=\"SELECT * FROM T{i}\"])\n"
                          f"\t\t\t\tin\n\t\t\t\t    Origen\n")
            informe = base / "G.Report" / "definition"
            _escribir(informe / "pages" / "pages.json", json.dumps({"pageOrder": ["p"]}))
            _escribir(informe / "pages" / "p" / "page.json", json.dumps({"name": "p", "displayName": "P"}))
            inicio = time.perf_counter()
            h = pbip.extraer_hechos(base)
            self.assertLess(time.perf_counter() - inicio, 5)
            self.assertEqual((len(h["tablas"]), len(h["medidas"])), (160, 1920))


class InformeSinteticoTest(unittest.TestCase):
    """Páginas, visuales, grupos, marcadores, filtros y formato condicional del PBIR."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="pbip_sint_")
        base = Path(cls.tmp)
        _modelo_sintetico(base)
        _informe_sintetico(base)
        cls.hechos = pbip.extraer_hechos(base)
        cls.paginas = {p["nombre"]: p for p in cls.hechos["paginas"]}
        cls.visuales = {v["id"]: v for p in cls.hechos["paginas"] for v in p["visuales"]}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_paginas_tipos_y_vacias(self):
        self.assertEqual([p["nombre"] for p in self.hechos["paginas"]], ["INICIO", "DETALLE", "TIP", "VACÍA"])
        self.assertEqual(self.paginas["TIP"]["tipo_pagina"], "Tooltip")
        self.assertEqual(self.paginas["DETALLE"]["tipo_pagina"], "Drillthrough")
        self.assertEqual(self.paginas["INICIO"]["tipo_pagina"], "Normal")
        self.assertFalse(self.paginas["DETALLE"]["visible"])
        self.assertEqual(self.paginas["VACÍA"]["visuales"], [])
        self.assertEqual(self.paginas["DETALLE"]["obtener_detalles"], ["Excel[A]"])
        json.dumps(self.hechos)

    def test_filtros_de_informe_pagina_y_visual(self):
        self.assertEqual(self.hechos["filtros_reporte"], ["Excel[A] = 'ok'"])
        self.assertEqual(self.paginas["INICIO"]["filtros"], ["Mi 'Tabla'[Monto] > 0"])
        self.assertEqual(self.visuales["tarjeta"]["filtros"], ["Excel[A] no está vacío"])

    def test_tarjeta_de_varios_campos(self):
        v = self.visuales["tarjeta"]
        self.assertEqual(v["campos"], ["Mi 'Tabla'[Total Ventas]", "AVERAGE(Mi 'Tabla'[Monto])"])
        self.assertEqual(v["titulo"], "Ventas del día")
        self.assertEqual(v["texto_alternativo"], "Resumen")
        self.assertEqual(v["tablas"], ["Excel", "Mi 'Tabla'"])

    def test_segmentador(self):
        v = self.visuales["seg"]
        self.assertEqual(v["campos"], ["Excel[A]"])
        self.assertEqual(v["segmentador"], {"modo": "Dropdown", "seleccion_unica": True})

    def test_grupos_ocultos_y_botones_con_destino(self):
        boton = self.visuales["boton"]
        self.assertEqual(boton["grupo"], "Navegación")
        self.assertTrue(boton["oculto"])  # hereda lo oculto de su grupo
        self.assertEqual(boton["accion"], "Bookmark")
        self.assertEqual(boton["destino"], "el marcador «Vista detalle» (DETALLE)")
        self.assertEqual(self.visuales["grupo"]["tipo"], "grupo")
        self.assertEqual(self.visuales["boton2"]["destino"], "DETALLE")
        self.assertFalse(self.visuales["boton2"]["oculto"])

    def test_marcadores(self):
        self.assertEqual(self.hechos["marcadores"], [
            {"id": "marca1", "nombre": "Vista detalle", "pagina_id": "detalle", "pagina": "DETALLE",
             "visuales": ["tarjeta"]}])

    def test_formato_condicional_por_campo(self):
        v = self.visuales["tabla"]
        regla = v["formato_condicional"][0]
        self.assertEqual(regla["tipo"], "campo")
        self.assertEqual(regla["evalua"], "Mi 'Tabla'[Corta]")
        self.assertEqual(v["semaforo"], ["campo1: color según Mi 'Tabla'[Corta]"])

    def test_visual_personalizado_y_json_roto(self):
        v = self.visuales["cust"]
        self.assertTrue(v["tipo"].startswith("textFilter"))
        self.assertEqual(pbip._nombre_tipo(v["tipo"]), "Filtro de texto (visual personalizado)")
        self.assertEqual(pbip._nombre_tipo("PBI_CV_16948668_E17D"), "Visual personalizado (PBI_CV_16948668_E17D)")
        self.assertNotIn("roto", self.visuales)
        self.assertTrue(any("roto" in a for a in self.hechos["advertencias"]))

    def test_comparar_y_esqueleto_funcionan_con_lo_nuevo(self):
        self.assertEqual(pbip.comparar(self.hechos, json.loads(json.dumps(self.hechos))), [])
        archivos = pbip.esqueleto(self.tmp, "DEMO", "demo")
        for nombre, texto in archivos.items():
            with self.subTest(archivo=nombre):
                self.assertEqual(F.validar(texto), [])

    def test_hechos_viejos_sin_campos_nuevos_se_comparan(self):
        viejo = {k: v for k, v in self.hechos.items() if k in (
            "tablero", "modelo_disponible", "paginas", "tablas", "medidas", "relaciones", "filtros_reporte")}
        self.assertEqual(pbip.comparar(viejo, self.hechos), [])

    def test_informe_solo_con_paginas_sin_visuales_y_sin_modelo(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            d = base / "X.Report" / "definition"
            _escribir(d / "pages" / "pages.json", json.dumps({"pageOrder": ["a"]}))
            _escribir(d / "pages" / "a" / "page.json", json.dumps({"name": "a", "displayName": "CVC"}))
            h = pbip.extraer_hechos(base)
            self.assertFalse(h["modelo_disponible"])
            self.assertEqual([(p["nombre"], len(p["visuales"])) for p in h["paginas"]], [("CVC", 0)])


TABLEROS = next((Path(c) for c in (
    os.getenv("DOCS_TABLEROS", ""), str(RAIZ_REPO / "tableros"),
    r"C:\Users\ad6708\Documents\Proyecto_RAG\tableros") if c and Path(c).is_dir()), None)


@unittest.skipIf(TABLEROS is None, "No existe la carpeta tableros/")
class TablerosRealesTest(unittest.TestCase):
    """Recorre todos los PBIP de tableros/: ninguno debe lanzar excepción y los que traen TMDL
    devuelven el modelo. Solo lee .json y .tmdl; nunca cache.abf."""

    def test_todos_los_pbip(self):
        carpetas = [c for c in sorted(TABLEROS.iterdir()) if c.is_dir() and any(c.glob("*.Report"))]
        if not carpetas:
            self.skipTest("tableros/ no tiene proyectos PBIP")
        for carpeta in carpetas:
            with self.subTest(tablero=carpeta.name):
                hechos = pbip.extraer_hechos(carpeta)
                con_tmdl = any(carpeta.glob("*.SemanticModel/definition/tables/*.tmdl"))
                if con_tmdl:
                    self.assertTrue(hechos["modelo_disponible"])
                    self.assertTrue(hechos["tablas"])
                json.dumps(hechos)
                texto = json.dumps(hechos, ensure_ascii=False).lower()
                self.assertNotRegex(texto, r"password=(?!\*\*\*)[^;\"\\ ]+")
                self.assertEqual(pbip.comparar(hechos, json.loads(json.dumps(hechos))), [])


if __name__ == "__main__":
    unittest.main()

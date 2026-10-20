"""
Pruebas de la página «Documentación» (pages/1_Documentación.py) con AppTest.

    PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m unittest tests.docs_md.test_interfaz

Usan servicios simulados (tests/docs_md/fakes_interfaz.py, vía la variable
DOCS_MD_SERVICIOS) y DOCS_MD_ROOT apuntando a una copia temporal de
tests/docs_md/fixtures: nunca tocan data/ ni llaman a MedGemma o Qdrant.

La última prueba carga el chat (app.py) hasta el primer render con el arnés
tests/realistic/run_app.py (Power BI y LLM simulados); se omite si no hay
data/ con catálogos o si DOCS_MD_SIN_APP=1.
"""
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

from src.docs_md import interfaz as I
from src.docs_md import repositorio as R
from src.docs_md.actualizador import Propuesta
from src.docs_md.formato import Operacion, parsear
from tests.docs_md import fakes_interfaz as fakes

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # pragma: no cover
    AppTest = None

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
PAGINA = ROOT / "pages" / "1_Documentación.py"
GRUPO = "tablero_tiempos_urgencias"

GENERAL = """---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TABLERO TIEMPOS URGENCIAS
nombre_funcional: Tiempos de atención del servicio de urgencias
bloque: General
actualizado: 2026-10-20
version: 1
---

# TABLERO TIEMPOS URGENCIAS

## Propósito
Tablero de tiempos de atención del servicio de urgencias.

## Definiciones
- **Tiempo de espera**: Minutos entre la admisión y el inicio de la consulta.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial.
"""

VARIABLES = ("DOCS_MD_ROOT", "DOCS_MD_SERVICIOS", "DOCS_MD_FAKE_REINDEX_FALLA", "DOCS_MD_FAKE_DEMORA")


def _textos(elementos):
    return "\n".join(str(e.value) for e in elementos)


def _boton(at, etiqueta):
    for boton in at.button:
        if boton.label == etiqueta:
            return boton
    raise AssertionError(f"No hay botón «{etiqueta}»: {[b.label for b in at.button]}")


@unittest.skipIf(AppTest is None, "Streamlit no está instalado")
class InterfazTest(unittest.TestCase):
    def setUp(self):
        self._entorno = {v: os.environ.get(v) for v in VARIABLES}
        self.tmp = Path(tempfile.mkdtemp(prefix="docs_md_ui_"))
        # Tablero mínimo propio (manifest + CONSULTAS DIA + general): las
        # pruebas no dependen de cuántas páginas tenga el fixture completo.
        self.carpeta = self.tmp / GRUPO / "md"
        self.carpeta.mkdir(parents=True)
        shutil.copy(FIXTURES / GRUPO / "manifest.json", self.tmp / GRUPO / "manifest.json")
        shutil.copy(FIXTURES / GRUPO / "md" / "consultas_dia.md", self.carpeta / "consultas_dia.md")
        (self.carpeta / "_general.md").write_text(GENERAL, encoding="utf-8")
        os.environ["DOCS_MD_ROOT"] = str(self.tmp)
        os.environ["DOCS_MD_SERVICIOS"] = "tests.docs_md.fakes_interfaz"
        os.environ.pop("DOCS_MD_FAKE_REINDEX_FALLA", None)
        os.environ.pop("DOCS_MD_FAKE_DEMORA", None)
        fakes.reiniciar()
        # Sin chat abierto: si otra prueba dejó un retriever real en el proceso, no se usa aquí.
        self._retriever_mod = sys.modules.get("src.rag.retriever")
        sin_chat = types.ModuleType("src.rag.retriever")
        sin_chat.retriever_abierto = lambda qdrant_path=None: None
        sys.modules["src.rag.retriever"] = sin_chat
        self.at = AppTest.from_file(str(PAGINA), default_timeout=60)
        self.at.run()
        self.assertFalse(self.at.exception, self.at.exception)

    def tearDown(self):
        if self._retriever_mod is None:
            sys.modules.pop("src.rag.retriever", None)
        else:
            sys.modules["src.rag.retriever"] = self._retriever_mod
        for clave, valor in self._entorno.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- utilidades ---------------------------------------------------------
    def _ok(self):
        self.assertFalse(self.at.exception, self.at.exception)

    def _proponer(self, nota, autor="Ana", pagina=None, pbip=None):
        self.at.radio(key="docs_modo").set_value(I.MODO_PROPONER).run()
        self._ok()
        self.at.text_area(key="docs_nota").input(nota)
        self.at.text_input(key="docs_autor").input(autor)
        if pagina is not None:
            self.at.selectbox(key="docs_pagina_prop").set_value(pagina)
        if pbip is not None:
            self.at.text_area(key="docs_pbip").input(pbip)
        _boton(self.at, "Generar propuesta").click().run()
        self._ok()

    def _leer(self, archivo="consultas_dia.md"):
        return (self.carpeta / archivo).read_text(encoding="utf-8")

    # -- ver ----------------------------------------------------------------
    def test_lista_tableros_y_paginas_general_primero(self):
        tablero = self.at.selectbox(key="docs_tablero")
        self.assertEqual(tablero.options, ["TABLERO TIEMPOS URGENCIAS (2 páginas)"])
        paginas = self.at.selectbox(key="docs_pagina_ver")
        self.assertTrue(paginas.options[0].startswith("General del tablero — Tiempos de atención"))
        self.assertIn("CONSULTAS DIA — Oportunidad", paginas.options[1])
        self.assertIn("· Día", paginas.options[1])
        self.assertIn("Formato válido", _textos(self.at.success))

    def test_renderiza_pagina_con_ficha_e_historial(self):
        self.at.selectbox(key="docs_pagina_ver").set_value("consultas_dia.md").run()
        self._ok()
        texto = _textos(self.at.markdown)
        self.assertIn("### CONSULTAS DIA", texto)
        self.assertIn("**Semáforo triage II**: Verde de 0 a 15 minutos", texto)
        self.assertIn("| Bloque | Día |", texto)            # ficha en lugar del YAML
        self.assertIn("| Tablas | CONSULTAS_DIA, EN_ESPERA_CONSULTA |", texto)
        self.assertNotIn("nombre_funcional:", texto)
        self.assertIn("Historial de cambios", texto)
        self.assertIn("**2026-10-20 · v1**", texto)
        self.assertIn("Formato válido", _textos(self.at.success))

    def test_indicador_de_formato_invalido(self):
        texto = self._leer().replace("rojo de 31 o más.", "rojo de 31 o más")
        (self.carpeta / "consultas_dia.md").write_text(texto, encoding="utf-8")
        self.at.run()
        paginas = self.at.selectbox(key="docs_pagina_ver")
        self.assertTrue(paginas.options[1].startswith("⚠️"))
        paginas.set_value("consultas_dia.md").run()
        self._ok()
        self.assertIn("Formato con problemas", _textos(self.at.error))
        self.assertIn("debe terminar en punto", _textos(self.at.error))

    # -- proponer, revisar y aprobar -----------------------------------------
    def test_propone_muestra_diff_y_aprueba(self):
        self._proponer("le subí el verde del semáforo de triage II a 20 minutos")
        llamada = fakes.LLAMADAS["proponer"][-1]
        self.assertIsNone(llamada["pagina"])            # «detectar automáticamente»
        texto = _textos(self.at.markdown)
        self.assertIn("**Página:** CONSULTAS DIA", texto)
        self.assertIn("Cambiar la entrada **«Semáforo triage II»** de **Reglas de negocio**", texto)
        self.assertIn(I.COLOR_AGREGADA, texto)
        self.assertIn("+ - **Semáforo triage II**: Verde de 0 a 20 minutos", texto)
        self.assertIn("− - **Semáforo triage II**: Verde de 0 a 15 minutos", texto)
        self.assertIn("@@", _textos(self.at.code))      # diff unificado en el expander
        self.assertIn("El resultado cumple el formato", _textos(self.at.success))

        _boton(self.at, "✅ Aprobar y guardar").click().run()
        self._ok()
        guardado = parsear(self._leer())
        self.assertEqual(guardado.meta["version"], 2)
        self.assertIn("Verde de 0 a 20 minutos", guardado.buscar("Reglas de negocio", "Semáforo triage II").texto)
        self.assertIn("Autor: Ana.", guardado.entradas("Historial de cambios")[-1].texto)
        self.assertIn("versión 2", _textos(self.at.success))
        self.assertEqual(fakes.LLAMADAS["reindexar"][-1]["source_group"], GRUPO)
        self.assertIsNone(fakes.LLAMADAS["reindexar"][-1]["qdrant_client"])
        self.assertIn("se reindexó **TABLERO TIEMPOS URGENCIAS**", _textos(self.at.info))
        self.assertIsNone(self.at.session_state["docs_propuesta"])

    def test_muestra_avisos_metodo_y_tiempos(self):
        self._proponer("le subí el verde del semáforo de triage II a 20 minutos")
        avisos = _textos(self.at.warning)
        self.assertIn("Revisa esto antes de aprobar (1)", avisos)
        self.assertIn("«Leyenda de oportunidad» también tiene la cifra 15", avisos)
        leyendas = _textos(self.at.caption)
        self.assertIn("Cómo se eligió la página: la nota la nombra", leyendas)
        self.assertIn("1 llamada a MedGemma (1.5 s)", leyendas)
        # Los avisos van junto al diff: antes del bloque «Antes y después».
        bloques = [str(m.value) for m in self.at.main if hasattr(m, "value")]
        posicion_aviso = next(i for i, v in enumerate(bloques) if "Revisa esto antes de aprobar" in v)
        posicion_diff = next(i for i, v in enumerate(bloques) if "Antes y después" in v)
        self.assertLess(posicion_aviso, posicion_diff)

    def test_pagina_indicada_se_explica(self):
        self._proponer("agregué una tarjeta", pagina="CONSULTAS DIA")
        self.assertIn("la elegiste tú en el formulario", _textos(self.at.caption))
        self.assertNotIn("Revisa esto antes de aprobar", _textos(self.at.warning))

    def test_pagina_elegida_y_cambios_pbip(self):
        self._proponer("agregué una tarjeta", pagina="CONSULTAS DIA",
                       pbip="Página CONSULTAS DIA: nueva tarjeta.\n\nOtro cambio.")
        llamada = fakes.LLAMADAS["proponer"][-1]
        self.assertEqual(llamada["pagina"], "CONSULTAS DIA")
        self.assertEqual(llamada["cambios_pbip"], ["Página CONSULTAS DIA: nueva tarjeta.", "Otro cambio."])
        self.assertIn("Agregar la entrada **«Nota del equipo»** en **Observaciones**", _textos(self.at.markdown))

    def test_formulario_pide_nota_y_autor(self):
        self._proponer("", autor="")
        self.assertIn("escribe qué cambió y escribe tu nombre", _textos(self.at.warning))
        self.assertEqual(fakes.LLAMADAS["proponer"], [])

    def test_rechazar_no_cambia_nada(self):
        antes = self._leer()
        self._proponer("le subí el semáforo de triage II")
        _boton(self.at, "❌ Rechazar").click().run()
        self._ok()
        self.assertEqual(self._leer(), antes)
        self.assertIn("Propuesta descartada", _textos(self.at.info))
        self.assertEqual(fakes.LLAMADAS["aplicar"], [])

    def test_edicion_manual_antes_de_aprobar(self):
        self._proponer("le subí el semáforo de triage II")
        n = self.at.session_state["docs_propuesta_n"]
        self.at.text_area(key=f"docs_op_{n}_0").input("Verde de 0 a 25 minutos, amarillo de 26 a 30 y rojo de 31 o más").run()
        self._ok()
        self.assertIn("Actualizar vista previa", _textos(self.at.info))
        self.assertTrue(_boton(self.at, "✅ Aprobar y guardar").disabled)
        _boton(self.at, "🔄 Actualizar vista previa").click().run()
        self._ok()
        self.assertIn("Verde de 0 a 25 minutos", _textos(self.at.markdown))
        self.assertIn("Vista previa actualizada", _textos(self.at.success))
        aprobar = _boton(self.at, "✅ Aprobar y guardar")
        self.assertFalse(aprobar.disabled)
        aprobar.click().run()
        self._ok()
        guardado = parsear(self._leer())
        self.assertEqual(guardado.buscar("Reglas de negocio", "Semáforo triage II").texto,
                         "Verde de 0 a 25 minutos, amarillo de 26 a 30 y rojo de 31 o más.")

    def test_aclaracion_elegir_pagina_y_reintentar(self):
        self._proponer("nota ambigua sobre el tablero")
        self.assertIn("Hace falta una aclaración", _textos(self.at.warning))
        n = self.at.session_state["docs_propuesta_n"]
        radio = self.at.radio(key=f"docs_aclara_pagina_{n}")
        self.assertIn("CONSULTAS DIA", radio.options[2] if len(radio.options) > 2 else radio.options[1])
        radio.set_value("CONSULTAS DIA")
        _boton(self.at, "Reintentar").click().run()
        self._ok()
        self.assertEqual(fakes.LLAMADAS["proponer"][-1]["pagina"], "CONSULTAS DIA")
        self.assertEqual(self.at.session_state["docs_propuesta"].estado, "lista")
        self.assertIn("**Página:** CONSULTAS DIA", _textos(self.at.markdown))

    def test_error_con_detalle_tecnico(self):
        self._proponer("esto falla")
        errores = _textos(self.at.error)
        self.assertIn("No se pudo preparar la propuesta", errores)
        self.assertIn("respuesta incompleta", errores)
        self.assertIn('"operaciones": [', _textos(self.at.code))
        self.assertEqual([b.label for b in self.at.button if "Aprobar" in b.label], [])

    def test_excepcion_del_servicio_se_muestra_como_error(self):
        def revienta(*args, **kwargs):
            raise NotImplementedError("Pendiente: agente actualizador")
        original = fakes.proponer_cambio
        fakes.proponer_cambio = revienta
        try:
            self._proponer("cualquier cosa")
        finally:
            fakes.proponer_cambio = original
        self.assertIn("todavía no está disponible", _textos(self.at.error))

    def test_reindexacion_falla_y_se_reintenta(self):
        os.environ["DOCS_MD_FAKE_REINDEX_FALLA"] = "1"
        self._proponer("le subí el semáforo de triage II")
        _boton(self.at, "✅ Aprobar y guardar").click().run()
        self._ok()
        self.assertEqual(parsear(self._leer()).meta["version"], 2)   # el .md sí quedó guardado
        self.assertIn("sí quedó guardado", _textos(self.at.warning))
        os.environ.pop("DOCS_MD_FAKE_REINDEX_FALLA")
        _boton(self.at, "🔁 Reintentar la reindexación").click().run()
        self._ok()
        self.assertEqual(len(fakes.LLAMADAS["reindexar"]), 2)
        self.assertIn("se reindexó", _textos(self.at.info))
        self.assertNotIn("Reintentar la reindexación", [b.label for b in self.at.button])

    def test_aprobar_falla_si_el_archivo_cambio(self):
        self._proponer("le subí el semáforo de triage II")
        (self.carpeta / "consultas_dia.md").write_text(self._leer().replace("15 minutos", "16 minutos"),
                                                      encoding="utf-8")
        _boton(self.at, "✅ Aprobar y guardar").click().run()
        self._ok()
        self.assertIn("No se guardó el cambio", _textos(self.at.error))
        self.assertIsNotNone(self.at.session_state["docs_propuesta"])
        self.assertEqual(fakes.LLAMADAS["reindexar"], [])

    def test_reutiliza_el_cliente_qdrant_del_chat(self):
        refrescos = []
        cliente = object()
        retriever = types.SimpleNamespace(client=cliente, refresh_metadata=lambda: refrescos.append(1))
        modulo = types.ModuleType("src.rag.retriever")
        modulo.retriever_abierto = lambda qdrant_path=None: retriever
        anterior = sys.modules.get("src.rag.retriever")
        sys.modules["src.rag.retriever"] = modulo
        try:
            self._proponer("le subí el semáforo de triage II")
            _boton(self.at, "✅ Aprobar y guardar").click().run()
            self._ok()
        finally:
            if anterior is None:
                sys.modules.pop("src.rag.retriever", None)
            else:
                sys.modules["src.rag.retriever"] = anterior
        self.assertIs(fakes.LLAMADAS["reindexar"][-1]["qdrant_client"], cliente)
        self.assertEqual(refrescos, [1])
        self.assertIn("con la conexión del chat", _textos(self.at.info))

    def test_la_pagina_se_abre_desde_app(self):
        # Streamlit descubre pages/ junto a app.py; abrir la página no ejecuta el chat.
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        at.switch_page("pages/1_Documentación.py")
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(at.title[0].value, "📚 Documentación de tableros")

    def test_boton_proponer_desde_ver(self):
        self.at.selectbox(key="docs_pagina_ver").set_value("consultas_dia.md").run()
        _boton(self.at, "✏️ Proponer un cambio en esta página").click().run()
        self._ok()
        self.assertEqual(self.at.radio(key="docs_modo").value, I.MODO_PROPONER)
        self.assertEqual(self.at.selectbox(key="docs_pagina_prop").value, "CONSULTAS DIA")


class LogicaTest(unittest.TestCase):
    def setUp(self):
        self.antes = (FIXTURES / GRUPO / "md" / "consultas_dia.md").read_text(encoding="utf-8")

    def test_describir_operacion(self):
        self.assertEqual(I.describir_operacion(Operacion("eliminar", "Visuales", "Leyendas")),
                         "Quitar la entrada **«Leyendas»** de **Visuales**")
        self.assertIn("Propósito", I.describir_operacion(Operacion("modificar", "Propósito", "", "x")))

    def test_reaplicar_y_diff(self):
        propuesta = Propuesta(nota="n", source_group=GRUPO, pagina="CONSULTAS DIA", estado="lista",
                              resumen="Cambio", antes=self.antes)
        op = Operacion("modificar", "Reglas de negocio", "Semáforo triage III", "Verde de 0 a 45 minutos")
        nueva = I.reaplicar(propuesta, [op])
        self.assertIn("Verde de 0 a 45 minutos.", nueva.despues)
        self.assertIn("+- **Semáforo triage III**: Verde de 0 a 45 minutos.", nueva.diff)
        html = I.diff_html(nueva.antes, nueva.despues)
        self.assertIn(I.COLOR_ELIMINADA, html)
        agregadas, eliminadas = I.lineas_cambiadas(nueva.antes, nueva.despues)
        # regla + versión (+ fecha si cambia) salen y entran; el historial solo entra
        self.assertEqual(agregadas, eliminadas + 1)
        self.assertGreaterEqual(eliminadas, 2)
        with self.assertRaises(ValueError):
            I.reaplicar(propuesta, [Operacion("modificar", "Reglas de negocio", "No existe", "x")])

    def test_textos_de_metodo_y_tiempos(self):
        p = Propuesta(nota="n", source_group=GRUPO, pagina="EGRESOS DIA", metodo_pagina="medgemma",
                      candidatas=["EGRESOS DIA", "TIEMPO EGRESO"])
        self.assertIn("MedGemma la eligió", I.metodo_pagina_texto(p))
        self.assertIn("TIEMPO EGRESO", I.metodo_pagina_texto(p))
        self.assertEqual(I.metodo_pagina_texto(Propuesta(nota="n", source_group=GRUPO)), "")
        self.assertEqual(I.tiempos_texto(9.84, [4.1, 5.2]),
                         "preparada en 9.8 s · 2 llamadas a MedGemma (4.1 s + 5.2 s)")
        self.assertEqual(I.tiempos_texto(None, []), "")

    def test_diff_html_escapa(self):
        self.assertIn("&lt;b&gt;", I.diff_html("a", "<b>"))
        self.assertIn("No hay diferencias", I.diff_html("a", "a"))


class RetrieverAbiertoTest(unittest.TestCase):
    def test_registro_del_retriever_abierto(self):
        try:
            from src.rag import retriever as modulo
        except Exception as exc:  # dependencias pesadas ausentes
            self.skipTest(f"No se pudo importar src.rag.retriever: {exc}")
        r = modulo.HybridRetriever.__new__(modulo.HybridRetriever)
        r.client = types.SimpleNamespace(close=lambda: None)
        ruta = Path(tempfile.gettempdir()) / "qdrant_prueba_docs"
        r.qdrant_path = ruta
        modulo._ACTIVE_RETRIEVERS[modulo._path_key(ruta)] = r
        self.assertIs(modulo.retriever_abierto(), r)
        self.assertIs(modulo.retriever_abierto(ruta), r)
        r.close()
        self.assertIsNone(modulo.retriever_abierto(ruta))


@unittest.skipIf(AppTest is None, "Streamlit no está instalado")
class AppPrincipalTest(unittest.TestCase):
    def test_el_chat_sigue_cargando(self):
        if os.getenv("DOCS_MD_SIN_APP") == "1":
            self.skipTest("DOCS_MD_SIN_APP=1")
        try:
            from tests.realistic import harness
            harness.resolve_data_root()
        except Exception as exc:
            self.skipTest(f"Sin data/ para el arnés del chat: {exc}")
        at = AppTest.from_file(str(ROOT / "tests" / "realistic" / "run_app.py"), default_timeout=300)
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(at.title[0].value, "📊 Asistente de Gestión Clínica")
        self.assertTrue(at.chat_input)
        # El retriever de build_system queda disponible para reutilizar su cliente de Qdrant.
        from src.rag.retriever import retriever_abierto
        self.assertIsNotNone(retriever_abierto())
        self.assertIsNotNone(I.retriever_del_chat())


if __name__ == "__main__":
    unittest.main()

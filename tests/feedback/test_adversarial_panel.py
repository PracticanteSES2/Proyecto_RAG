"""
Pruebas adversariales del panel de calificación (src/feedback/panel.py) y su conexión con app.py.

Ejecutar:
  python -X utf8 -m unittest tests.feedback.test_adversarial_panel
"""
import json
import logging
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from src.chatbot.conversation_export import export_conversation_markdown
from src.feedback import lector

logging.getLogger("streamlit").setLevel(logging.ERROR)
ROOT = Path(__file__).resolve().parents[2]
_MAIN_ORIGINAL = sys.modules["__main__"]
PREGUNTA = "¿Qué muestra el tablero de lavandería?"


def tearDownModule():
    sys.modules["__main__"] = _MAIN_ORIGINAL


# ----------------------------------------------------------------- scripts

def _script_basico():
    import streamlit as st
    from src.feedback.panel import mostrar_calificacion
    msgs = [
        {"role": "assistant", "content": "Hola."},
        {"role": "user", "content": "¿Cuántas?"},
        {"role": "assistant", "content": "55", "snapshot": {
            "pregunta": "¿Cuántas?", "via": "texto", "estado": "success", "ruta": "powerbi",
            "respuesta": "55", "opciones_contrapregunta": []}},
    ]
    mostrar_calificacion(2, msgs)


def _script_dos_turnos():
    import streamlit as st
    from src.feedback.panel import mostrar_calificacion
    snap = {"pregunta": "p", "via": "texto", "respuesta": "r", "opciones_contrapregunta": []}
    msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "A", "snapshot": snap},
            {"role": "user", "content": "b"}, {"role": "assistant", "content": "B", "snapshot": snap}]
    mostrar_calificacion(1, msgs)
    mostrar_calificacion(3, msgs)
    if st.button("nueva", key="nueva"):
        st.session_state.pop("id_sesion", None)
        st.rerun()


def _script_casos_raros():
    import streamlit as st
    from src.feedback.panel import mostrar_calificacion
    ok = {"role": "assistant", "content": "x", "snapshot": {"respuesta": "x"}}
    casos = {
        "idx_neg": (-1, [ok]),
        "idx_fuera": (5, [ok]),
        "vacia": (0, []),
        "snap_none": (0, [{"role": "assistant", "content": "x", "snapshot": None}]),
        "snap_ausente": (0, [{"role": "assistant", "content": "x"}]),
        "snap_vacio": (0, [{"role": "assistant", "content": "x", "snapshot": {}}]),
        "snap_str": (0, [{"role": "assistant", "content": "x", "snapshot": "hola"}]),
        "msg_none": (0, [None]),
        "msg_str": (0, ["texto"]),
        "indice_str": ("1", [ok, ok]),
    }
    for nombre, (i, m) in casos.items():
        try:
            mostrar_calificacion(i, m)
            st.session_state["r_" + nombre] = "ok"
        except Exception as e:  # noqa: BLE001
            st.session_state["r_" + nombre] = f"EXC {type(e).__name__}: {e}"


def _script_historial_raro():
    from src.feedback.panel import mostrar_calificacion
    snap = {"pregunta": "p", "via": "texto", "respuesta": "r", "opciones_contrapregunta": []}
    msgs = [{"role": "user", "content": 12345678},
            {"role": "assistant", "content": None},
            {"role": "user", "content": {"a": 1}},
            {"role": "user", "content": ["x", "y"]},
            {"role": "user"},
            {"content": "sin rol"},
            {"role": "user", "content": "😀 café ñ 日本語 \u202e"},
            {"role": "assistant", "content": "ok", "snapshot": snap}]
    mostrar_calificacion(7, msgs)


def _script_largo():
    from src.feedback.panel import mostrar_calificacion
    snap = {"pregunta": "p", "via": "texto", "respuesta": "r", "opciones_contrapregunta": []}
    msgs = []
    for i in range(50):
        msgs.append({"role": "user", "content": f"pregunta {i}"})
        msgs.append({"role": "assistant", "content": f"resp {i}", "snapshot": snap})
    mostrar_calificacion(99, msgs)
    mostrar_calificacion(98, msgs)  # usuario sin snapshot: sin panel


def _script_usuario_con_snapshot():
    from src.feedback.panel import mostrar_calificacion
    msgs = [{"role": "user", "content": "hola", "snapshot": {"respuesta": "x", "pregunta": "hola"}}]
    mostrar_calificacion(0, msgs)


def _script_mutacion():
    import copy
    import streamlit as st
    from src.feedback.panel import mostrar_calificacion
    snap = {"pregunta": "¿Cédula 12345678?", "via": "texto", "respuesta": "r 12345678 | x |",
            "opciones_contrapregunta": ["a", "b"], "fuentes": [{"id": "1"}]}
    msgs = [{"role": "user", "content": "cédula 12345678"},
            {"role": "assistant", "content": "r", "snapshot": snap}]
    antes = copy.deepcopy(msgs)
    mostrar_calificacion(1, msgs)
    st.session_state["mutado"] = (msgs != antes)


# ----------------------------------------------------------------- base

class Base(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        anterior = os.environ.get("FEEDBACK_DIR")
        os.environ["FEEDBACK_DIR"] = self._dir.name
        self.addCleanup(lambda: os.environ.pop("FEEDBACK_DIR", None) if anterior is None
                        else os.environ.__setitem__("FEEDBACK_DIR", anterior))

    def app(self, fn):
        at = AppTest.from_function(fn, default_timeout=60).run()
        self.assertFalse(at.exception, at.exception)
        return at

    def lineas(self):
        ruta = Path(self._dir.name) / "calificaciones.jsonl"
        return ruta.read_text(encoding="utf-8").splitlines() if ruta.exists() else []

    def registros(self):
        return lector.cargar_calificaciones()

    @staticmethod
    def boton(at, prefijo="guardar_"):
        return [b for b in at.button if str(b.key).startswith(prefijo)]

    @staticmethod
    def hay_guardado(at):
        return any("Guardado" in str(c.value) for c in at.caption)


# ----------------------------------------------------------------- (1) secuencias

class Secuencias(Base):
    def test_buena_mala_buena_lectora_devuelve_buena(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(1).run()
        at.get("feedback")[0].set_value(0).run()
        at.get("feedback")[0].set_value(1).run()
        self.assertFalse(at.exception, at.exception)
        regs = self.registros()
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0]["calificacion"], "buena")

    def test_mala_guardar_editar_guardar_dos_lineas_y_lectora_ultima(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(0).run()
        at.text_area[0].set_value("Primera version").run()
        self.boton(at)[0].click().run()
        self.assertEqual(len(self.lineas()), 1)
        at.text_area[0].set_value("Segunda version").run()
        self.assertEqual(len(self.lineas()), 1, "editar sin pulsar Guardar no escribe")
        self.boton(at)[0].click().run()
        self.assertEqual(len(self.lineas()), 2)
        regs = self.registros()
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0]["esperado"], "Segunda version")

    def test_guardar_dos_veces_mismo_comentario_una_linea(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(0).run()
        at.text_area[0].set_value("Algo").run()
        self.boton(at)[0].click().run()
        self.boton(at)[0].click().run()
        self.assertEqual(len(self.lineas()), 1)

    def test_buena_luego_limpiar_pulgar_no_duplica(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(1).run()
        at.get("feedback")[0].set_value(None).run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(len(self.lineas()), 1)
        self.assertEqual(len(at.get("feedback")), 1)

    def test_limpiar_pulgar_oculta_caption_guardado(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(1).run()
        at.get("feedback")[0].set_value(None).run()
        self.assertFalse(self.hay_guardado(at))

    def test_mala_solo_espacios_avisa_y_no_escribe(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(0).run()
        at.text_area[0].set_value("   \n\t  ").run()
        self.boton(at)[0].click().run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(self.lineas(), [])
        self.assertGreaterEqual(len(at.warning), 1)
        self.assertFalse(self.hay_guardado(at))

    def test_mala_sin_pulsar_guardar_no_escribe_aunque_haya_comentario(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(0).run()
        at.text_area[0].set_value("comentario").run()
        at.run()
        self.assertEqual(self.lineas(), [])

    def test_muchos_reruns_sin_cambios_una_sola_linea(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(1).run()
        for _ in range(8):
            at.run()
        self.assertEqual(len(self.lineas()), 1)

    def test_mala_buena_mala_misma_nota_la_lectora_termina_en_mala(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(0).run()
        at.text_area[0].set_value("Nota").run()
        self.boton(at)[0].click().run()
        at.get("feedback")[0].set_value(1).run()
        self.assertEqual(self.registros()[0]["calificacion"], "buena")
        at.get("feedback")[0].set_value(0).run()
        self.boton(at)[0].click().run()
        self.assertEqual(self.registros()[0]["calificacion"], "mala")

    def test_mala_guardada_buena_y_de_nuevo_mala_sin_pulsar_guardar_no_queda_buena_obsoleta(self):
        # El usuario deja el pulgar en 👎 pero el registro vigente dice «buena».
        # Comportamiento correcto: no mostrar «Guardado ✔» para el estado 👎 no guardado.
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(1).run()
        at.get("feedback")[0].set_value(0).run()
        self.assertFalse(self.hay_guardado(at),
                         "con 👎 sin guardar no debe verse «Guardado ✔» de la calificación anterior")

    def test_editar_comentario_tras_guardar_quita_caption_guardado(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(0).run()
        at.text_area[0].set_value("uno").run()
        self.boton(at)[0].click().run()
        self.assertTrue(self.hay_guardado(at))
        at.text_area[0].set_value("dos").run()
        self.assertFalse(self.hay_guardado(at))


# ----------------------------------------------------------------- (2) entradas raras

class EntradasRaras(Base):
    def _malos(self):
        at = AppTest.from_function(_script_casos_raros, default_timeout=60).run()
        self.assertFalse(at.exception, at.exception)
        return {k: v for k, v in at.session_state.to_dict().items()
                if str(k).startswith("r_") and v != "ok"}

    def test_indices_y_snapshots_raros_no_lanzan(self):
        malos = {k: v for k, v in self._malos().items() if not k.startswith(("r_msg_", "r_indice_"))}
        self.assertEqual(malos, {})

    def test_mensajes_no_dict_no_lanzan(self):
        malos = {k: v for k, v in self._malos().items() if k.startswith("r_msg_")}
        self.assertEqual(malos, {})

    def test_indice_no_entero_no_lanza(self):
        malos = {k: v for k, v in self._malos().items() if k.startswith("r_indice_")}
        self.assertEqual(malos, {})

    def test_usuario_con_snapshot_no_rompe_ni_escribe(self):
        self.app(_script_usuario_con_snapshot)
        self.assertEqual(self.lineas(), [])

    def test_historial_con_contenido_no_str_y_unicode_guarda(self):
        at = self.app(_script_historial_raro)
        at.get("feedback")[0].set_value(1).run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(len(at.warning), 0, [w.value for w in at.warning])
        regs = self.registros()
        self.assertEqual(len(regs), 1)
        self.assertIn("日本語", json.dumps(regs[0], ensure_ascii=False))

    def test_historial_largo_100_mensajes_solo_6_en_registro(self):
        at = self.app(_script_largo)
        self.assertEqual(len(at.get("feedback")), 1)
        at.get("feedback")[0].set_value(1).run()
        reg = self.registros()[0]
        self.assertEqual(len(reg["historial"]), 6)
        self.assertTrue(reg["id_turno"].endswith(":99"))
        self.assertEqual(reg["historial"][-1]["texto"], "pregunta 49")

    def test_no_muta_mensajes_ni_snapshot(self):
        at = self.app(_script_mutacion)
        self.assertFalse(at.session_state["mutado"])
        at.get("feedback")[0].set_value(1).run()
        self.assertFalse(at.session_state["mutado"])


# ----------------------------------------------------------------- (3) turnos y sesiones

class TurnosYSesiones(Base):
    def test_dos_turnos_ids_distintos_y_widgets_sin_colision(self):
        at = self.app(_script_dos_turnos)
        self.assertEqual(len(at.get("feedback")), 2)
        at.get("feedback")[0].set_value(1).run()
        at.get("feedback")[1].set_value(0).run()
        at.text_area[0].set_value("esperaba otra cosa").run()
        self.boton(at)[0].click().run()
        self.assertFalse(at.exception, at.exception)
        regs = self.registros()
        self.assertEqual(len(regs), 2)
        por_idx = {r["id_turno"].split(":")[1]: r["calificacion"] for r in regs}
        self.assertEqual(por_idx, {"1": "buena", "3": "mala"})

    def test_nueva_conversacion_renueva_id_sesion(self):
        at = self.app(_script_dos_turnos)
        at.get("feedback")[0].set_value(1).run()
        antes = at.session_state["id_sesion"]
        at.button(key="nueva").click().run()
        self.assertFalse(at.exception, at.exception)
        at.get("feedback")[0].set_value(1).run()
        self.assertNotEqual(antes, at.session_state["id_sesion"])
        self.assertEqual(len(self.registros()), 2, "mismo índice en otra conversación = otro id_turno")

    def test_nueva_conversacion_pulgar_no_hereda_valor(self):
        at = self.app(_script_dos_turnos)
        at.get("feedback")[0].set_value(1).run()
        at.button(key="nueva").click().run()
        self.assertFalse(self.hay_guardado(at), "tras renovar la sesión el widget empieza limpio")

    def test_id_sesion_vacio_se_regenera(self):
        at = AppTest.from_function(_script_dos_turnos, default_timeout=60)
        at.session_state["id_sesion"] = ""
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(at.session_state["id_sesion"])


# ----------------------------------------------------------------- (4) fallos de guardado

class FalloAlGuardar(Base):
    def test_feedback_dir_es_archivo_avisa_no_marca_y_reintento_guarda(self):
        archivo = Path(self._dir.name) / "archivo.txt"
        archivo.write_text("x")
        os.environ["FEEDBACK_DIR"] = str(archivo)
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(1).run()
        self.assertFalse(at.exception, at.exception)
        self.assertGreaterEqual(len(at.warning), 1)
        self.assertFalse(self.hay_guardado(at))
        self.assertFalse([k for k in at.session_state.keys() if str(k).startswith("guardado_")])
        os.environ["FEEDBACK_DIR"] = self._dir.name
        at.run()
        self.assertEqual(len(self.lineas()), 1)
        self.assertTrue(self.hay_guardado(at))

    def test_guardar_lanza_en_mala_no_marca_guardado_y_reintento_guarda(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(0).run()
        at.text_area[0].set_value("nota").run()
        with mock.patch("src.feedback.panel.guardar", side_effect=OSError("disco lleno")):
            self.boton(at)[0].click().run()
        self.assertFalse(at.exception, at.exception)
        self.assertGreaterEqual(len(at.warning), 1)
        self.assertFalse(self.hay_guardado(at))
        self.assertEqual(self.lineas(), [])
        self.boton(at)[0].click().run()
        self.assertEqual(len(self.lineas()), 1)

    def test_aviso_de_error_no_filtra_ruta_ni_mensaje(self):
        at = self.app(_script_basico)
        with mock.patch("src.feedback.panel.guardar", side_effect=OSError(r"C:\secreto\ruta 12345678")):
            at.get("feedback")[0].set_value(1).run()
        textos = " ".join(str(w.value) for w in at.warning)
        self.assertNotIn("secreto", textos)
        self.assertNotIn("12345678", textos)

    def test_construir_registro_lanza_no_rompe(self):
        at = self.app(_script_basico)
        with mock.patch("src.feedback.panel.construir_registro", side_effect=RuntimeError("x")):
            at.get("feedback")[0].set_value(1).run()
        self.assertFalse(at.exception, at.exception)
        self.assertGreaterEqual(len(at.warning), 1)

    def test_reruns_fallidos_no_escriben_nada(self):
        at = self.app(_script_basico)
        with mock.patch("src.feedback.panel.guardar", side_effect=OSError("x")):
            at.get("feedback")[0].set_value(1).run()
            at.run()
            at.run()
        self.assertEqual(self.lineas(), [])


# ----------------------------------------------------------------- (5) saneamiento

class Saneamiento(Base):
    def _guardar_mala(self, texto):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(0).run()
        at.text_area[0].set_value(texto).run()
        self.boton(at)[0].click().run()
        self.assertFalse(at.exception, at.exception)
        return self.registros()

    def test_cedula_se_enmascara_en_esperado(self):
        regs = self._guardar_mala("El paciente 1.234.567.890 debia aparecer")
        self.assertEqual(len(regs), 1)
        crudo = json.dumps(regs[0])
        self.assertNotIn("1234567890", crudo)
        self.assertNotIn("1.234.567.890", crudo)
        self.assertIn("[NUM]", regs[0]["esperado"])

    def test_filas_de_tabla_no_llegan_al_log(self):
        regs = self._guardar_mala("Esperaba:\n| Juan | 12345678 |\n|---|---|\ntexto normal")
        crudo = "\n".join(self.lineas())
        self.assertNotIn("Juan", crudo)
        self.assertNotIn("12345678", crudo)
        self.assertIn("texto normal", regs[0]["esperado"])

    def test_vinetas_con_cedula_enmascaradas(self):
        self._guardar_mala("- 98765432 es el documento\n* 11223344 otro")
        crudo = "\n".join(self.lineas())
        self.assertNotIn("98765432", crudo)
        self.assertNotIn("11223344", crudo)

    def test_un_registro_una_linea_fisica_con_saltos_en_comentario(self):
        self._guardar_mala("linea1\nlinea2\r\nlinea3\u2028linea4")
        self.assertEqual(len(self.lineas()), 1)

    def test_pipes_en_medio_de_linea_no_rompen(self):
        regs = self._guardar_mala("A | B | C esperaba esto")
        self.assertEqual(len(regs), 1)


# ----------------------------------------------------------------- (6) app real

def _app_real():
    return AppTest.from_file(str(ROOT / "tests" / "realistic" / "run_app.py"), default_timeout=300)


class AppReal(Base):
    def test_apagado_cero_widgets_encendido_uno_por_respuesta_no_saludo(self):
        app = _app_real().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.get("feedback")), 0)
        app.chat_input[0].set_value(PREGUNTA).run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.get("feedback")), 0)
        app.checkbox[0].check().run()
        self.assertEqual(len(app.get("feedback")), 1)
        msgs = app.session_state["messages"]
        self.assertEqual([m["role"] for m in msgs], ["assistant", "user", "assistant"])
        self.assertNotIn("snapshot", msgs[0])
        self.assertNotIn("snapshot", msgs[1])
        self.assertIn("snapshot", msgs[2])
        app.chat_input[0].set_value(PREGUNTA).run()
        self.assertEqual(len(app.get("feedback")), 2)
        app.checkbox[0].uncheck().run()
        self.assertEqual(len(app.get("feedback")), 0)
        self.assertEqual(len(self.lineas()), 0)

    def test_calificar_turno_vivo_y_rerun_una_linea_indice_de_la_respuesta(self):
        app = _app_real().run()
        app.checkbox[0].check().run()
        app.chat_input[0].set_value(PREGUNTA).run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.get("feedback")), 1)
        app.get("feedback")[0].set_value(1).run()
        self.assertFalse(app.exception, app.exception)
        app.run()
        self.assertEqual(len(self.lineas()), 1)
        reg = self.registros()[0]
        self.assertTrue(reg["id_turno"].endswith(":2"), reg["id_turno"])
        for prohibida in ("rows", "dax", "contexts", "reasoning", "detail", "details", "powerbi"):
            self.assertNotIn(prohibida, reg)

    def test_nueva_conversacion_en_app_real_renueva_sesion(self):
        app = _app_real().run()
        app.checkbox[0].check().run()
        app.chat_input[0].set_value(PREGUNTA).run()
        app.get("feedback")[0].set_value(1).run()
        sesion1 = app.session_state["id_sesion"]
        nuevo = [b for b in app.sidebar.button if "Nueva conversación" in str(b.label)]
        self.assertTrue(nuevo, [b.label for b in app.sidebar.button])
        nuevo[0].click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.get("feedback")), 0)
        app.chat_input[0].set_value(PREGUNTA).run()
        self.assertEqual(len(app.get("feedback")), 1)
        app.get("feedback")[0].set_value(1).run()
        self.assertNotEqual(sesion1, app.session_state["id_sesion"])
        self.assertEqual(len(self.registros()), 2)
        self.assertEqual(len(self.lineas()), 2)

    def test_error_de_guardado_en_app_real_no_rompe_chat(self):
        app = _app_real().run()
        app.checkbox[0].check().run()
        app.chat_input[0].set_value(PREGUNTA).run()
        with mock.patch("src.feedback.panel.guardar", side_effect=OSError("x")):
            app.get("feedback")[0].set_value(1).run()
            self.assertFalse(app.exception, app.exception)
            app.chat_input[0].set_value(PREGUNTA).run()
            self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.get("feedback")), 2)


# ----------------------------------------------------------------- (7) export

class Export(Base):
    def test_export_no_filtra_el_snapshot(self):
        marca = "MARCA_SNAPSHOT_UNICA_XYZ"
        msgs = [
            {"role": "user", "content": "hola", "via": "texto"},
            {"role": "assistant", "content": "respuesta visible", "status": "success", "route": "powerbi",
             "snapshot": {"pregunta": marca, "respuesta": marca, "ruta": marca, "informe": marca,
                          "fuentes": [{"id": marca}], "opciones_contrapregunta": [marca]}},
        ]
        md = export_conversation_markdown(msgs)
        self.assertNotIn(marca, md)
        self.assertNotIn("snapshot", md.lower())
        self.assertIn("respuesta visible", md)

    def test_export_igual_con_y_sin_snapshot(self):
        base = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a", "status": "ok"}]
        con = [dict(m) for m in base]
        con[1]["snapshot"] = {"respuesta": "a", "pregunta": "q"}
        t = datetime(2026, 1, 1)
        self.assertEqual(export_conversation_markdown(base, now=t), export_conversation_markdown(con, now=t))

    def test_export_en_app_real_no_incluye_snapshot(self):
        app = _app_real().run()
        app.checkbox[0].check().run()
        app.chat_input[0].set_value(PREGUNTA).run()
        msgs = app.session_state["messages"]
        self.assertIn("snapshot", msgs[-1])
        md = export_conversation_markdown(msgs)
        for clave in ("fecha_turno", "opciones_contrapregunta", "modelo_semantico", "tablero_esperado"):
            self.assertNotIn(clave, md)


# ----------------------------------------------------------------- (9) consistencia

class Consistencia(Base):
    def test_firma_segun_brief(self):
        import inspect
        from src.feedback import panel
        self.assertEqual(list(inspect.signature(panel.mostrar_calificacion).parameters), ["indice", "mensajes"])

    def test_etiquetas_segun_brief(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(0).run()
        self.assertEqual(at.text_area[0].label, "¿Qué esperabas que respondiera? (no incluyas datos de pacientes)")
        self.assertEqual(self.boton(at)[0].label, "Guardar")

    def test_id_sesion_12_hex_e_id_turno_coherente(self):
        at = self.app(_script_basico)
        at.get("feedback")[0].set_value(1).run()
        sesion = at.session_state["id_sesion"]
        self.assertRegex(sesion, r"^[0-9a-f]{12}$")
        reg = self.registros()[0]
        self.assertEqual(reg["id_turno"], f"{sesion}:2")
        self.assertEqual(reg["id_sesion"], sesion)


if __name__ == "__main__":
    unittest.main()

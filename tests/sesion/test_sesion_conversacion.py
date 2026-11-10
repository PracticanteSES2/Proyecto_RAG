"""
Memoria por sesión (spec 008): el motor es compartido y el estado de cada
conversación viaja en una EstadoConversacion.

Antes, app.py creaba un único QueryEngine (@st.cache_resource) que guardaba en
sus atributos la memoria, la consulta anterior y las contrapreguntas: el
seguimiento de una persona se completaba con la pregunta de otra y «Nueva
conversación» borraba el contexto de todos.

Cubre: seguimientos intercalados de dos conversaciones, contrapregunta de A que
B no responde, reiniciar A sin tocar B, serializar y restaurar (también con una
contrapregunta abierta), que el motor no guarde estado de conversación, turnos
concurrentes en hilos (motor de verdad con turnos en serie, y el andamiaje del
turno en paralelo real) y el cableado de app.py (reset_if_finished).

    python -X utf8 -m unittest tests.sesion.test_sesion_conversacion
"""
import copy
import json
import sys
import threading
import time
import unittest
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.estado_conversacion import VERSION_ESTADO, EstadoConversacion
from src.chatbot.response_formatter import clarification_buttons, format_filters_line

A_PREGUNTA = "cirugías programadas de abril de 2025"
B_PREGUNTA = "atenciones de marzo de 2024"
SEGUIMIENTO = "¿y en urología?"
AMBIGUA = "cirugías realizadas de marzo de 2025"
_FALLAS = (AssertionError, KeyError, RuntimeError, TypeError, ValueError, threading.BrokenBarrierError)


def _sim():
    from tests.context import test_context
    return test_context.sim()


def _resumen(resultado):
    filtros = [(f.get("column"), f.get("value")) for f in resultado.get("filters") or []
               if f.get("type") == "categorical" and f.get("column") not in ("AÑO", "MES")]
    periodo = format_filters_line(resultado.get("filters") or [])
    return resultado.get("status"), resultado.get("metric"), filtros, periodo


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness, (cls.engine, cls.cm, cls.formatter, *_) = _sim()

    def setUp(self):
        # El modo legado (sin sesion=) no debe arrastrar nada de otra prueba.
        self.harness.new_conversation(self.engine, self.cm)

    def preguntar(self, texto, sesion):
        return self.engine.process(texto, sesion=sesion)

    def elegir(self, resultado, indice, sesion):
        boton = clarification_buttons(resultado)[indice]
        return self.engine.select_clarification_option(boton["id"], boton["label"], sesion=sesion)


class EstadoSerializableTest(unittest.TestCase):
    def test_estado_nuevo_es_json_puro_y_versionado(self):
        estado = EstadoConversacion()
        datos = estado.to_dict()
        self.assertEqual(datos["version"], VERSION_ESTADO)
        self.assertEqual(json.loads(json.dumps(datos)), datos)
        self.assertEqual(len(estado.id), 32)
        self.assertNotEqual(estado.id, EstadoConversacion().id)

    def test_conserva_tuplas_conjuntos_fechas_y_claves_no_texto(self):
        estado = EstadoConversacion(id="x")
        estado.plan_pendiente = {"choices": [{"id": "m1", "par": (1, "a")}], "vistos": {"b", "a"},
                                 "desde": date(2025, 3, 1), 3: "tres", "__tupla__": "literal"}
        estado.seguimiento = {"filters": [{"value": (2025, 3)}]}
        restaurado = EstadoConversacion.from_json(estado.to_json())
        self.assertEqual(restaurado.plan_pendiente, estado.plan_pendiente)
        self.assertIsInstance(restaurado.plan_pendiente["choices"][0]["par"], tuple)
        self.assertEqual(restaurado.seguimiento, estado.seguimiento)
        self.assertEqual(restaurado.to_dict(), estado.to_dict())

    def test_valor_no_serializable_falla_con_su_ruta(self):
        estado = EstadoConversacion()
        estado.seguimiento = {"objeto": object()}
        with self.assertRaisesRegex(TypeError, r"\$\.objeto"):
            estado.to_dict()

    def test_version_incompatible_o_corrupto_lanza_valueerror(self):
        datos = EstadoConversacion().to_dict()
        with self.assertRaises(ValueError):
            EstadoConversacion.from_dict({**datos, "version": VERSION_ESTADO + 1})
        with self.assertRaises(ValueError):
            EstadoConversacion.from_json("{no es json")
        with self.assertRaises(ValueError):
            EstadoConversacion.from_dict({**datos, "memoria": "texto"})

    def test_cerrar_turno_y_reiniciar(self):
        estado = EstadoConversacion()
        estado.plan_pendiente, estado.seguimiento = {"question": "q"}, {"metric_id": "m"}
        estado.memoria.record("hola", {"status": "success", "route": "rag", "answer": "x"})
        estado.intencion.awaiting_clarification = True
        estado.cerrar_turno({"status": "needs_clarification"})
        self.assertIsNotNone(estado.plan_pendiente)
        estado.cerrar_turno({"status": "success"})
        self.assertIsNone(estado.plan_pendiente)
        self.assertFalse(estado.intencion.awaiting_clarification)
        self.assertEqual((estado.seguimiento, len(estado.memoria)), ({"metric_id": "m"}, 1))
        estado.reiniciar()
        self.assertEqual((estado.seguimiento, len(estado.memoria)), (None, 0))


class AislamientoTest(_Base):
    def test_seguimientos_intercalados_no_se_contaminan(self):
        a, b = EstadoConversacion(), EstadoConversacion()
        self.assertEqual(self.preguntar(A_PREGUNTA, a)["status"], "success")
        self.assertEqual(self.preguntar(B_PREGUNTA, b)["status"], "success")
        seg_a = _resumen(self.preguntar(SEGUIMIENTO, a))
        seg_b = _resumen(self.preguntar(SEGUIMIENTO, b))
        self.assertEqual(seg_a[:3], ("success", "CIRUGÍAS PROGRAMADAS", [("ESPECIALIDAD", "UROLOGIA")]), seg_a)
        self.assertIn("abril 2025", seg_a[3])
        self.assertEqual(seg_b[:3], ("success", "TOTAL ATENCIONES", [("ESPECIALIDAD", "UROLOGIA")]), seg_b)
        self.assertIn("marzo 2024", seg_b[3])
        # Cada memoria tiene solo lo suyo.
        self.assertEqual([t["user"] for t in a.memoria.turns()], [A_PREGUNTA, SEGUIMIENTO])
        self.assertEqual([t["user"] for t in b.memoria.turns()], [B_PREGUNTA, SEGUIMIENTO])
        self.assertEqual(self.engine.conversation_history(10, sesion=b)[0]["text"], B_PREGUNTA)

    def test_contrapregunta_pendiente_de_a_no_la_responde_b(self):
        a, b = EstadoConversacion(), EstadoConversacion()
        abierta = self.preguntar(AMBIGUA, a)
        self.assertEqual(abierta["status"], "needs_clarification")
        self.assertIsNotNone(a.plan_pendiente)
        # B no tiene nada pendiente: el botón de A no aplica y «1» no elige la opción de A.
        boton = clarification_buttons(abierta)[0]
        ajeno = self.engine.select_clarification_option(boton["id"], boton["label"], sesion=b)
        self.assertEqual(ajeno.get("error"), "No hay una aclaración pendiente.")
        respuesta_b = self.preguntar("1", b)
        self.assertNotEqual(respuesta_b.get("metric"), "Cirugías realizadas")
        self.assertNotIn("Cirugías realizadas", str(respuesta_b.get("metric")))
        # A sigue con su contrapregunta y la resuelve.
        self.assertIsNotNone(a.plan_pendiente)
        elegida = self.elegir(abierta, 0, a)
        self.assertEqual(elegida["status"], "success", elegida.get("error"))
        self.assertIn("marzo 2025", _resumen(elegida)[3])
        self.assertIsNone(a.plan_pendiente)

    def test_reiniciar_a_no_afecta_b(self):
        a, b = EstadoConversacion(), EstadoConversacion()
        self.preguntar(A_PREGUNTA, a)
        self.preguntar(B_PREGUNTA, b)
        a.reiniciar()
        self.assertEqual((len(a.memoria), a.seguimiento), (0, None))
        seg_b = _resumen(self.preguntar(SEGUIMIENTO, b))
        self.assertEqual(seg_b[1:3], ("TOTAL ATENCIONES", [("ESPECIALIDAD", "UROLOGIA")]), seg_b)
        # El reset de compatibilidad con sesion= tampoco toca a la otra.
        self.engine.reset(full=True, sesion=b)
        self.assertEqual(len(b.memoria), 0)

    def test_estado_sobrevive_serializar_y_restaurar(self):
        a = EstadoConversacion()
        self.preguntar(A_PREGUNTA, a)
        restaurada = EstadoConversacion.from_json(a.to_json())
        self.assertEqual(restaurada.to_dict(), a.to_dict())
        directo = _resumen(self.preguntar(SEGUIMIENTO, a))
        tras_json = _resumen(self.preguntar(SEGUIMIENTO, restaurada))
        self.assertEqual(directo, tras_json)
        self.assertEqual(tras_json[1:3], ("CIRUGÍAS PROGRAMADAS", [("ESPECIALIDAD", "UROLOGIA")]))
        # Con una contrapregunta abierta: se guarda, se restaura y se elige la opción.
        c = EstadoConversacion()
        abierta = self.preguntar(AMBIGUA, c)
        c2 = EstadoConversacion.from_json(json.dumps(json.loads(c.to_json())))
        elegida = self.elegir(abierta, 0, c2)
        self.assertEqual(elegida["status"], "success", elegida.get("error"))
        self.assertIn("marzo 2025", _resumen(elegida)[3])

    def test_cada_turno_serializa_y_restaura_igual(self):
        """Ida y vuelta por JSON en CADA turno: misma respuesta que sin serializar."""
        guion = [A_PREGUNTA, SEGUIMIENTO, "y en 2024?", AMBIGUA, "#0", "y en urología?", "cuantas cirugias hubo",
                 "y en el mes pasado?", "#1"]
        directa, viajera = EstadoConversacion(), EstadoConversacion()
        ultimo = {}
        for paso in guion:
            salidas = []
            for nombre in ("directa", "viajera"):
                estado = directa if nombre == "directa" else viajera
                if paso.startswith("#"):
                    resultado = self.elegir(ultimo[nombre], int(paso[1:]), estado)
                else:
                    resultado = self.preguntar(paso, estado)
                ultimo[nombre] = resultado
                salidas.append(_resumen(resultado) + (resultado.get("route"),))
                if nombre == "viajera":
                    viajera = EstadoConversacion.from_json(viajera.to_json())
            self.assertEqual(salidas[0], salidas[1], paso)
        self.assertEqual(directa.to_dict()["memoria"]["turnos"], viajera.to_dict()["memoria"]["turnos"])

    def test_el_motor_no_guarda_estado_de_conversacion(self):
        legado = self.engine._sesion_legado().to_dict()
        legado_gestor = copy.deepcopy(self.cm.state.to_dict())
        a = EstadoConversacion()
        self.preguntar(AMBIGUA, a)
        self.preguntar(A_PREGUNTA, a)
        self.preguntar(SEGUIMIENTO, a)
        self.assertEqual(self.engine._sesion_legado().to_dict(), legado)
        self.assertEqual(self.cm.state.to_dict(), legado_gestor)
        prohibidos = {"_pending_query_plan", "_pending_master_metric", "_pending_dashboard_clarification",
                      "_last_success", "_deferred_context_message", "conversation_memory", "last_reasoning",
                      "_trace", "_turn_interpretation", "_turn_message", "_range_choice", "_applying_deferred"}
        self.assertFalse(prohibidos & set(vars(self.engine)), prohibidos & set(vars(self.engine)))
        self.assertFalse({"state", "candidate_dashboards"} & set(vars(self.cm)))
        self.assertIsNotNone(a.ultimo_razonamiento)
        self.assertNotIn("ultimo_razonamiento", json.dumps(a.to_dict()))

    def test_app_reset_if_finished_con_sesion_solo_toca_esa_sesion(self):
        reset_if_finished = self.harness._APP_NS["reset_if_finished"]
        a = EstadoConversacion()
        a.plan_pendiente = {"question": "q", "choices": []}
        self.engine._pending_query_plan = {"question": "legado"}
        reset_if_finished({"status": "success"}, self.engine, self.cm, sesion=a)
        self.assertIsNone(a.plan_pendiente)
        self.assertEqual(self.engine._pending_query_plan, {"question": "legado"})


class ConcurrenciaTest(_Base):
    def test_turnos_en_hilos_intercalados_con_turno_a_la_vez(self):
        """Como Streamlit: un hilo por navegador y turn_slot (un turno a la vez)."""
        candado = threading.Lock()
        guiones = {
            "A": [A_PREGUNTA, SEGUIMIENTO, "y en 2024?"],
            "B": [B_PREGUNTA, SEGUIMIENTO, "y en 2023?"],
        }
        estados = {nombre: EstadoConversacion() for nombre in guiones}
        salidas, errores = {nombre: [] for nombre in guiones}, []

        def conversar(nombre):
            try:
                for texto in guiones[nombre]:
                    with candado:
                        resultado = self.preguntar(texto, estados[nombre])
                    salidas[nombre].append(_resumen(resultado))
                    time.sleep(0.01)  # deja entrar a la otra conversación
            except _FALLAS as error:  # se reporta abajo, en el hilo principal
                errores.append(f"{nombre}: {type(error).__name__}: {error}")

        hilos = [threading.Thread(target=conversar, args=(n,)) for n in guiones]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(300)
        self.assertEqual(errores, [])
        self.assertEqual({s[1] for s in salidas["A"]}, {"CIRUGÍAS PROGRAMADAS"}, salidas["A"])
        self.assertEqual({s[1] for s in salidas["B"]}, {"TOTAL ATENCIONES"}, salidas["B"])
        self.assertIn("2024", salidas["A"][2][3])
        self.assertIn("2023", salidas["B"][2][3])
        self.assertEqual(salidas["A"][2][2], [("ESPECIALIDAD", "UROLOGIA")])
        self.assertEqual(salidas["B"][2][2], [("ESPECIALIDAD", "UROLOGIA")])

    def test_estado_del_turno_por_hilo_en_paralelo_real(self):
        """Dos turnos a la vez DENTRO del motor (sin candado): razonamiento,
        interpretación, mensaje del turno, seguimiento, memoria y escucha de
        progreso son de cada turno. El cuerpo del turno es falso (los
        colaboradores compartidos aún no admiten turnos en paralelo)."""
        motor = copy.copy(self.engine)
        for clave in ("_sesion_propia", "_turno_propio"):
            motor.__dict__.pop(clave, None)
        barrera = threading.Barrier(2, timeout=30)

        def turno_falso(mensaje):
            motor._think("inicio", mensaje)
            motor._turn_interpretation = f"interpretado {mensaje}"
            motor._range_choice = mensaje
            motor._activity("trabajando", mensaje)
            barrera.wait()  # los dos turnos están dentro del motor a la vez
            time.sleep(0.02)
            motor._last_success = {"question": mensaje}
            assert motor._turn_interpretation == f"interpretado {mensaje}"
            assert motor._range_choice == mensaje and motor._trace.text == mensaje
            barrera.wait()
            return {"status": "success", "route": "powerbi", "answer": mensaje, "metric": mensaje}

        motor._process_turn = turno_falso
        motor._portero_turn = lambda *args: None
        estados = {n: EstadoConversacion() for n in ("A", "B")}
        eventos = {n: [] for n in estados}
        resultados, errores = {}, []

        def conversar(nombre):
            try:
                for i in range(3):
                    texto = f"pregunta {nombre}{i}"
                    resultados[(nombre, i)] = motor.process(texto, sesion=estados[nombre],
                                                            progreso=eventos[nombre].append)
            except _FALLAS as error:  # se reporta abajo, en el hilo principal
                errores.append(f"{nombre}: {type(error).__name__}: {error}")
                barrera.abort()

        hilos = [threading.Thread(target=conversar, args=(n,)) for n in estados]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(60)
        self.assertEqual(errores, [])
        for nombre, estado in estados.items():
            propias = [f"pregunta {nombre}{i}" for i in range(3)]
            self.assertEqual([t["user"] for t in estado.memoria.turns()], propias)
            self.assertEqual([t["interpreted"] for t in estado.memoria.turns()],
                             [f"interpretado {p}" for p in propias])
            self.assertEqual(estado.seguimiento, {"question": propias[-1]})
            for i, texto in enumerate(propias):
                self.assertEqual(resultados[(nombre, i)]["reasoning"]["text"], texto)
            ajenas = [e for e in eventos[nombre] if "pregunta" in " ".join(e.get("lines") or [])
                      and not any(nombre in line for line in e.get("lines") or [])]
            self.assertEqual(ajenas, [])
            self.assertTrue(eventos[nombre])
        self.assertIsNone(motor.progress_listener)


if __name__ == "__main__":
    unittest.main()

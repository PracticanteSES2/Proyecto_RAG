"""
Portero conectado al motor (QueryEngine.process) con el arnés offline de
tests/sim: sin Power BI, Ollama, Qdrant ni .env.

Ejecutar:
  python -X utf8 -m unittest tests.portero.test_motor_portero
"""
import sys
import types
import unittest
from contextlib import ExitStack
from unittest import mock

sys.dont_write_bytecode = True

from tests.sim import harness

_SISTEMA = {}


def _sistema():
    if "s" not in _SISTEMA:
        _SISTEMA["s"] = harness.build_engine()
    return _SISTEMA["s"]


def _razonamiento(result):
    return "\n".join(
        " ".join([step.get("title") or "", *[str(line) for line in step.get("lines") or []]])
        for step in (result.get("reasoning") or {}).get("steps") or []
    )


class MotorPorteroTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.cm, self.formatter, *_ = _sistema()
        harness.new_conversation(self.engine, self.cm)

    def tearDown(self):
        harness.new_conversation(self.engine, self.cm)

    def ask(self, texto):
        return harness.ask(self.engine, self.cm, self.formatter, texto)

    def _espiar_busquedas(self, stack):
        """Cuenta las llamadas search* del retriever (falso) del motor."""
        llamadas = []
        retriever = self.engine.rag_answer_engine.retriever
        for nombre in dir(retriever):
            if nombre.startswith("search") and callable(getattr(retriever, nombre)):
                original = getattr(retriever, nombre)

                def espia(*a, _n=nombre, _o=original, **k):
                    llamadas.append(_n)
                    return _o(*a, **k)

                stack.enter_context(mock.patch.object(retriever, nombre, espia))
        return llamadas

    def test_hola_responde_sin_buscar(self):
        with ExitStack() as stack:
            llamadas = self._espiar_busquedas(stack)
            result, ui = self.ask("hola")
        self.assertEqual(result["route"], "conversacion", ui)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["conversation_kind"], "charla/saludo")
        self.assertEqual(result["question"], "hola")
        self.assertEqual(llamadas, [])
        self.assertEqual(result["_sim"]["dax_log"], [])
        self.assertIn("Mensaje conversacional", _razonamiento(result))
        self.assertEqual(ui, result["answer"])

    def test_que_puedes_hacer_lista_tableros_del_catalogo(self):
        result, ui = self.ask("¿Qué puedes hacer?")
        self.assertEqual(result["route"], "conversacion", ui)
        self.assertEqual(result["conversation_kind"], "capacidades/capacidades")
        linea = next(l for l in ui.split("\n\n") if l.startswith("**Datos**"))
        for nombre in ("Atenciones Institucionales", "Gestion Quirurgica", "Lavanderia"):
            self.assertIn(nombre, linea)

    def test_no_actua_con_contrapregunta_pendiente(self):
        for respuesta in ("ninguna", "gracias"):
            harness.new_conversation(self.engine, self.cm)
            primero, ui1 = self.ask("cuantas cirugias hubo en 2024")
            self.assertEqual(primero["status"], "needs_clarification", ui1)
            segundo, ui2 = self.ask(respuesta)
            self.assertNotEqual(segundo["route"], "conversacion", (respuesta, ui2))

    def test_gracias_no_rompe_seguimiento(self):
        primero, ui1 = self.ask("cirugias programadas de urologia en 2024")
        self.assertEqual(primero["status"], "success", ui1)
        segundo, _ = self.ask("gracias")
        self.assertEqual(segundo["route"], "conversacion")
        tercero, ui3 = self.ask("¿y en octubre?")
        self.assertEqual(tercero["status"], "success", ui3)
        self.assertEqual(tercero["query_plan"]["metric"]["metric_id"],
                         primero["query_plan"]["metric"]["metric_id"])
        self.assertIn("como seguimiento", _razonamiento(tercero))
        periodo = tercero["query_plan"]["period"]
        self.assertEqual((periodo["kind"], periodo["start"], periodo["end"]),
                         ("month", "2024-10-01", "2024-11-01"))

    def test_que_mas_tras_respuesta_no_es_saludo(self):
        self.ask("cirugias programadas de urologia en 2024")
        result, ui = self.ask("¿qué más?")
        self.assertNotEqual(result["route"], "conversacion", ui)

    def test_portero_precalentado_al_construir_el_sistema(self):
        engine, *_ = harness.build_engine()
        vocabulario, similitud, datos, _ = engine._portero_recursos
        self.assertTrue(vocabulario)
        self.assertIsNotNone(similitud)
        self.assertIn("Lavanderia", datos)

    def test_saludo_mas_pregunta_va_a_datos(self):
        result, ui = self.ask("hola, cirugias programadas de urologia en 2024")
        self.assertEqual(result["route"], "powerbi", ui)
        self.assertEqual(result["status"], "success", ui)

    def test_portero_que_lanza_no_tumba_el_turno(self):
        with mock.patch("src.chatbot.portero.clasificar", side_effect=RuntimeError("boom")) as falso:
            result, ui = self.ask("hola")
        falso.assert_called()
        self.assertIsNone(result["_sim"]["exception"])
        self.assertNotEqual(result["route"], "conversacion")

    def test_fallo_del_portero_se_registra_sin_el_texto_del_usuario(self):
        secreto = "hola texto-privado-xyz"
        with mock.patch("src.chatbot.portero.clasificar", side_effect=RuntimeError("boom")):
            with self.assertLogs("src.chatbot.query_engine", level="WARNING") as cap:
                self.ask(secreto)
        salida = "|".join(cap.output)
        self.assertIn("RuntimeError", salida)
        self.assertNotIn("texto-privado-xyz", salida)

    def test_fallo_del_precalentado_se_registra(self):
        with mock.patch.object(type(self.engine), "_portero_resources", side_effect=ValueError("mal")):
            with self.assertLogs("src.chatbot.query_engine", level="WARNING") as cap:
                self.assertFalse(self.engine.warm_up_portero())
        self.assertIn("ValueError", "|".join(cap.output))

    def test_recursos_armados_una_vez_con_similitud(self):
        self.ask("hola")
        recursos = self.engine._portero_recursos
        vocabulario, similitud, datos, _ = recursos
        self.assertTrue(vocabulario)
        self.assertIsNotNone(similitud)
        self.assertIn("Lavanderia", datos)
        self.ask("gracias")
        self.assertIs(self.engine._portero_recursos, recursos)

    def test_sin_rag_answer_engine_usa_solo_reglas(self):
        guardado = self.engine.rag_answer_engine
        self.engine._portero_recursos = None
        try:
            self.engine.rag_answer_engine = types.SimpleNamespace()
            result, ui = self.ask("hola")
            self.assertEqual(result["route"], "conversacion", ui)
            self.assertIn("(regla)", _razonamiento(result))
            vocabulario, similitud, _, _ = self.engine._portero_recursos
            self.assertIsNone(similitud)
        finally:
            self.engine.rag_answer_engine = guardado
            self.engine._portero_recursos = None


if __name__ == "__main__":
    unittest.main()

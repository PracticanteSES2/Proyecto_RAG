"""Streaming de la síntesis documental: `FiltroBorrador`, `escuchar_tokens`,
`AnswerSynthesizer.synthesize_rag(on_token=...)` y `RAGAnswerEngine.answer`.

Decisión (specs/009-experiencia-espera/plan.md): los tokens son un BORRADOR;
el post-proceso (limpieza, salvaguarda de cifras, truncado) se aplica igual al
texto completo y la respuesta final lo reemplaza. Sin `on_token` todo queda
idéntico.

Ejecutar: python -X utf8 -m unittest tests.streaming.test_sintesis_stream
"""
import unittest

from src.chatbot.answer_synthesizer import NO_EVIDENCE_ANSWER, AnswerSynthesizer
from src.chatbot.rag_answer_engine import RAGAnswerEngine
from src.chatbot.respuesta_en_vivo import FiltroBorrador, escuchar_tokens, oyente_tokens

SOURCES = [{
    "text": "Tablero: BRIEFING Indicador: CANTIDAD DE PACIENTES Descripción: Cuenta los pacientes "
            "únicos inscritos en la aseguradora.",
    "chunk_type": "indicator", "dashboard": "DETALLE OCUPACIÓN", "semantic_model": "BRIEFING HOSPITALARIO",
    "intent": "definition", "score": 0.9,
}]
RESPUESTA = "El indicador cuenta los pacientes únicos inscritos en la aseguradora."


def _trozos(texto, tamano=6):
    return [texto[i:i + tamano] for i in range(0, len(texto), tamano)]


class _ProveedorStream:
    """LLM falso con la firma de MedGemmaProvider (stream + on_token)."""

    enforces_timeout = True

    def __init__(self, answer=RESPUESTA):
        self.answer = answer
        self.pedidos = []

    def chat(self, messages, temperature=0.1, max_tokens=450, think=False, timeout=None, format=None,
             stream=False, on_token=None):
        self.pedidos.append({"stream": stream, "on_token": on_token})
        if stream and on_token:
            for trozo in _trozos(self.answer):
                on_token(trozo)
        return {"status": "success", "answer": self.answer, "model": "falso"}


class _Recuperador:
    def search_general(self, question, limit=5, dashboard=None):
        return [dict(SOURCES[0])]


def _filtrar(texto, tamano=4):
    salida = []
    filtro = FiltroBorrador(salida.append, retenidas=(NO_EVIDENCE_ANSWER,),
                            relleno_inicial=AnswerSynthesizer._LEADING_FILLER_RE)
    for trozo in _trozos(texto, tamano):
        filtro(trozo)
    return "".join(salida)


class TestFiltroBorrador(unittest.TestCase):
    def test_texto_normal_pasa_completo(self):
        self.assertEqual(_filtrar(RESPUESTA), RESPUESTA)

    def test_quita_la_muletilla_inicial_y_pone_mayuscula(self):
        self.assertEqual(_filtrar("Claro, el indicador cuenta los pacientes únicos."),
                         "El indicador cuenta los pacientes únicos.")

    def test_nunca_transmite_la_frase_de_sin_evidencia(self):
        self.assertEqual(_filtrar(NO_EVIDENCE_ANSWER), "")
        self.assertEqual(_filtrar(NO_EVIDENCE_ANSWER, tamano=1), "")

    def test_si_se_aparta_de_la_frase_retenida_la_suelta(self):
        texto = "No encontré la fórmula exacta, pero el indicador cuenta los pacientes."
        self.assertEqual(_filtrar(texto), texto)

    def test_respuesta_corta_queda_para_la_final(self):
        self.assertEqual(_filtrar("Sí."), "")

    def test_callback_que_lanza_no_rompe(self):
        def roto(_texto):
            raise RuntimeError("boom")

        filtro = FiltroBorrador(roto)
        for trozo in _trozos(RESPUESTA):
            filtro(trozo)  # no lanza


class TestEscucharTokens(unittest.TestCase):
    def test_contexto_por_bloque(self):
        self.assertIsNone(oyente_tokens())
        def cb(_texto):
            return None
        with escuchar_tokens(cb):
            self.assertIs(oyente_tokens(), cb)
            with escuchar_tokens(None):
                self.assertIsNone(oyente_tokens())
            self.assertIs(oyente_tokens(), cb)
        self.assertIsNone(oyente_tokens())


class TestSintesisConTokens(unittest.TestCase):
    def test_tokens_y_resultado_identico(self):
        tokens = []
        proveedor = _ProveedorStream()
        con = AnswerSynthesizer(proveedor, timeout_seconds=5).synthesize_rag("qué mide", SOURCES,
                                                                             on_token=tokens.append)
        sin = AnswerSynthesizer(_ProveedorStream(), timeout_seconds=5).synthesize_rag("qué mide", SOURCES)
        self.assertEqual(con, sin)
        self.assertEqual("".join(tokens), RESPUESTA)
        self.assertTrue(proveedor.pedidos[0]["stream"])

    def test_sin_on_token_no_hay_streaming(self):
        proveedor = _ProveedorStream()
        AnswerSynthesizer(proveedor, timeout_seconds=5).synthesize_rag("qué mide", SOURCES)
        self.assertFalse(proveedor.pedidos[0]["stream"])

    def test_sin_evidencia_no_se_transmite(self):
        tokens = []
        resultado = AnswerSynthesizer(_ProveedorStream(NO_EVIDENCE_ANSWER), timeout_seconds=5).synthesize_rag(
            "¿y el clima?", SOURCES, on_token=tokens.append)
        self.assertTrue(resultado["no_evidence"])
        self.assertEqual(tokens, [])


class TestRAGConTokens(unittest.TestCase):
    def _motor(self, answer=RESPUESTA):
        return RAGAnswerEngine(retriever=_Recuperador(),
                               answer_synthesizer=AnswerSynthesizer(_ProveedorStream(answer), timeout_seconds=5))

    def test_escuchar_tokens_llega_a_la_sintesis_sin_tocar_el_motor_de_chat(self):
        tokens = []
        with escuchar_tokens(tokens.append):
            con = self._motor().answer({"original_question": "qué mide"})
        sin = self._motor().answer({"original_question": "qué mide"})
        self.assertEqual(con, sin)
        self.assertEqual("".join(tokens), RESPUESTA)

    def test_on_token_explicito(self):
        tokens = []
        self._motor().answer({"original_question": "qué mide"}, on_token=tokens.append)
        self.assertEqual("".join(tokens), RESPUESTA)

    def test_sintetizador_antiguo_sin_on_token_sigue_funcionando(self):
        class Antiguo:
            def synthesize_rag(self, question, sources):
                return {"status": "success", "answer": "Cuenta los pacientes únicos.", "no_evidence": False}

        with escuchar_tokens(lambda t: None):
            resultado = RAGAnswerEngine(retriever=_Recuperador(), answer_synthesizer=Antiguo()).answer(
                {"original_question": "qué mide"})
        self.assertEqual(resultado["status"], "success")

    def test_la_salvaguarda_sigue_mandando_sobre_el_borrador(self):
        # El borrador muestra la cifra inventada; la respuesta final validada
        # (la que reemplaza al borrador) no la trae.
        inventada = RESPUESTA + " En 2025 subió un 37 % frente al año anterior."
        tokens = []
        with escuchar_tokens(tokens.append):
            con = self._motor(inventada).answer({"original_question": "qué mide"})
        sin = self._motor(inventada).answer({"original_question": "qué mide"})
        self.assertEqual(con, sin)
        self.assertIn("37", "".join(tokens))
        self.assertNotIn("37", con["answer"])


if __name__ == "__main__":
    unittest.main()

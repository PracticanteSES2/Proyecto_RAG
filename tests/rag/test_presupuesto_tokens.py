"""
Presupuesto de tokens del LLM (src/llm/presupuesto_tokens.py): `num_predict`
por propósito configurable por entorno, estimación de tokens de entrada y
recorte controlado del contexto para no pasar de `num_ctx`.

Ejecutar:
  python -X utf8 -m unittest tests.rag.test_presupuesto_tokens
"""
import os
import unittest
from unittest import mock

from src.llm import presupuesto_tokens as P


def _mensajes(texto):
    return [{"role": "system", "content": "Eres un asistente."}, {"role": "user", "content": texto}]


class NumPredictTests(unittest.TestCase):
    def test_valores_por_defecto_por_proposito(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for nombre in ("LLM_NUM_PREDICT_SINTESIS", "LLM_NUM_PREDICT_OPCIONES"):
                os.environ.pop(nombre, None)
            self.assertEqual(P.num_predict("sintesis"), 600)
            self.assertEqual(P.num_predict("opciones"), 60)
            self.assertEqual(P.num_predict("reescritura"), 80)
            self.assertEqual(P.num_predict("intencion"), 160)
            self.assertEqual(P.num_predict("continuacion"), 200)

    def test_se_configura_por_entorno_y_tolera_valores_invalidos(self):
        with mock.patch.dict(os.environ, {"LLM_NUM_PREDICT_SINTESIS": "800"}):
            self.assertEqual(P.num_predict("sintesis"), 800)
        with mock.patch.dict(os.environ, {"LLM_NUM_PREDICT_SINTESIS": "mucho"}):
            self.assertEqual(P.num_predict("sintesis"), 600)

    def test_proposito_desconocido_falla_ruidosamente(self):
        with self.assertRaises(KeyError):
            P.num_predict("inventado")

    def test_num_ctx_por_entorno(self):
        with mock.patch.dict(os.environ, {"MEDGEMMA_NUM_CTX": "8192"}):
            self.assertEqual(P.num_ctx(), 8192)
        with mock.patch.dict(os.environ, {"MEDGEMMA_NUM_CTX": ""}):
            self.assertEqual(P.num_ctx(), 4096)

    def test_palabras_objetivo_deja_holgura(self):
        # 600 tokens → ~250 palabras (≈ 430 tokens con Markdown).
        self.assertEqual(P.palabras_objetivo(600), 250)
        self.assertEqual(P.palabras_objetivo(200), 80)

    def test_la_extension_va_en_letras_para_que_no_se_copie_como_cifra(self):
        self.assertEqual(P.extension_pedida(600), "doscientas cincuenta")
        self.assertEqual(P.extension_pedida(300), "ciento veinte")
        self.assertEqual(P.palabras_en_letras(100), "cien")
        self.assertEqual(P.palabras_en_letras(80), "ochenta")
        self.assertEqual(P.palabras_en_letras(1500), "1500")


class EstimacionTests(unittest.TestCase):
    def test_estimacion_conservadora(self):
        with mock.patch.dict(os.environ, {"LLM_CARACTERES_POR_TOKEN": "3.3"}):
            self.assertEqual(P.estimar_tokens(""), 0)
            self.assertEqual(P.estimar_tokens("a" * 330), 100)
            # Mensajes: contenido + plantilla por mensaje.
            self.assertGreater(P.tokens_mensajes(_mensajes("a" * 330)), 100)

    def test_entrada_maxima_descuenta_salida_y_margen(self):
        self.assertEqual(P.entrada_maxima(600, ctx=4096), 4096 - 600 - P.MARGEN_PLANTILLA)


class AjusteContextoTests(unittest.TestCase):
    FUENTES = ("A" * 3000, "B" * 3000, "C" * 3000, "D" * 3000)

    def _construir(self, n, max_chars):
        contexto = "\n\n".join(self.FUENTES[:n])
        if max_chars is not None:
            contexto = contexto[:max_chars]
        return contexto, _mensajes("PREGUNTA\n" + contexto)

    def test_si_cabe_no_toca_nada(self):
        contexto, _, recorte = P.ajustar_a_contexto(self._construir, 4, 600, ctx=32768)
        self.assertIsNone(recorte)
        self.assertIn("D" * 10, contexto)

    def test_quita_primero_las_fuentes_menos_relevantes(self):
        # 4096 - 600 - margen ≈ 3430 tokens ≈ 11.300 caracteres: caben 3 de 4 fuentes.
        with mock.patch.dict(os.environ, {"LLM_CARACTERES_POR_TOKEN": "3.3"}):
            contexto, mensajes, recorte = P.ajustar_a_contexto(self._construir, 4, 600, ctx=4096)
            self.assertEqual(recorte["fuentes_quitadas"], 1)
            self.assertFalse(recorte["contexto_recortado"])
            self.assertNotIn("D", contexto)
            self.assertIn("C" * 10, contexto)
            self.assertLessEqual(P.tokens_mensajes(mensajes), P.entrada_maxima(600, ctx=4096))
            self.assertGreater(recorte["tokens_antes"], recorte["limite"])

    def test_con_una_sola_fuente_recorta_el_texto(self):
        with mock.patch.dict(os.environ, {"LLM_CARACTERES_POR_TOKEN": "3.3"}):
            contexto, mensajes, recorte = P.ajustar_a_contexto(self._construir, 4, 600, ctx=1200)
            self.assertEqual(recorte["fuentes_quitadas"], 3)
            self.assertTrue(recorte["contexto_recortado"])
            self.assertLessEqual(P.tokens_mensajes(mensajes), P.entrada_maxima(600, ctx=1200))
            self.assertTrue(contexto.startswith("AAAA"))


if __name__ == "__main__":
    unittest.main()

"""
Síntesis RAG con respuestas truncadas por `num_predict` (dobles de prueba que
devuelven `done_reason="length"`; nunca MedGemma real): corte seguro + línea
del tablero, continuación cuando hay tiempo y el servidor está libre, recorte
de la entrada contra `num_ctx`, diagnóstico en la traza y `cacheable`.
También: reescritura y descripción de opciones truncadas.

Ejecutar:
  python -X utf8 -m unittest tests.rag.test_sintesis_truncada
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from src.chatbot import respuesta_completa as R
from src.chatbot.answer_synthesizer import AnswerSynthesizer
from src.chatbot.contextual_rewriter import LLMContextRewriter
from src.chatbot.option_describer import OptionDescriber
from src.chatbot.rag_answer_engine import RAGAnswerEngine

RAIZ = Path(__file__).resolve().parents[2]
ARG_TURNO = "--turno-completo"
LIBRE = {"in_flight": 0, "waiting": 0, "capacity": 3, "saturated_recent": 0}
OCUPADO = dict(LIBRE, waiting=2)

TEXTO = ("El indicador mide la ocupación de camas del hospital. Se calcula dividiendo los días cama "
         "ocupados entre los días cama disponibles del periodo.")
FUENTE = {"text": TEXTO, "dashboard": "OCUPACION", "chunk_type": "indicator", "score": 0.9,
          "semantic_model": "MODELO OCUPACION", "intent": "definition"}

CORTADA = "El indicador mide la ocupación de camas del hospital. Se calcula dividiendo los días cama ocup"


def _resp(answer, truncated=False, eval_count=600):
    return {"status": "success", "answer": answer, "model": "doble",
            "done_reason": "length" if truncated else "stop", "truncated": truncated,
            "eval_count": eval_count if truncated else 120, "prompt_eval_count": 900}


class _Proveedor:
    """Doble de MedGemma: devuelve las respuestas en orden y guarda las llamadas."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def chat(self, messages, **kwargs):
        self.llamadas.append({"messages": messages, **kwargs})
        return self.respuestas.pop(0) if self.respuestas else _resp("Sin más.")


class _Retriever:
    def __init__(self, fuentes):
        self.fuentes = fuentes

    def search_general(self, question, limit=5, dashboard=None):
        return list(self.fuentes)


def _motor(proveedor, fuentes=(FUENTE,)):
    sintetizador = AnswerSynthesizer(proveedor, timeout_seconds=0)
    return RAGAnswerEngine(_Retriever(list(fuentes)), answer_synthesizer=sintetizador)


def _preguntar(motor, pregunta="¿qué es la ocupación?"):
    return motor.answer({"original_question": pregunta})


class SintesisTruncadaTests(unittest.TestCase):
    def test_servidor_con_fila_corta_y_agrega_la_linea_del_tablero(self):
        proveedor = _Proveedor(_resp(CORTADA, truncated=True))
        with mock.patch.object(R, "presion_llm", return_value=OCUPADO):
            resultado = _preguntar(_motor(proveedor))
        self.assertEqual(len(proveedor.llamadas), 1)
        self.assertEqual(resultado["status"], "success")
        respuesta = resultado["answer"]
        self.assertTrue(respuesta.startswith("El indicador mide la ocupación de camas del hospital."))
        self.assertNotIn("ocup\n", respuesta + "\n")
        self.assertIn("La respuesta completa está en el tablero", respuesta)
        self.assertFalse(resultado["cacheable"])
        detalle = resultado["synthesis_detail"]
        self.assertIn("truncada: sí", detalle)
        self.assertIn("600", detalle)
        self.assertIn("fila", detalle)

    def test_la_linea_lleva_el_enlace_de_power_bi_si_existe(self):
        proveedor = _Proveedor(_resp(CORTADA, truncated=True))
        enlace = {"url": "https://app.powerbi.com/groups/g/reports/r/ReportSection1", "nivel": "pagina"}
        with mock.patch.object(R, "presion_llm", return_value=OCUPADO), \
                mock.patch("src.chatbot.rag_answer_engine.enlace_para_resultado", return_value=enlace):
            resultado = _preguntar(_motor(proveedor))
        self.assertIn("(https://app.powerbi.com/groups/g/reports/r/ReportSection1)", resultado["answer"])

    def test_servidor_libre_hace_una_continuacion_y_une_sin_aviso(self):
        proveedor = _Proveedor(
            _resp(CORTADA, truncated=True),
            _resp("Se calcula dividiendo los días cama ocupados entre los días cama disponibles del periodo."),
        )
        with mock.patch.object(R, "presion_llm", return_value=LIBRE):
            resultado = _preguntar(_motor(proveedor))
        self.assertEqual(len(proveedor.llamadas), 2)
        segunda = proveedor.llamadas[1]["messages"]
        self.assertEqual(segunda[-2]["role"], "assistant")
        self.assertEqual(segunda[-2]["content"], "El indicador mide la ocupación de camas del hospital.")
        self.assertIn("sin repetir", segunda[-1]["content"])
        self.assertEqual(proveedor.llamadas[1]["max_tokens"], 200)
        self.assertEqual(resultado["answer"], TEXTO)
        self.assertTrue(resultado["cacheable"])
        self.assertIn("continuación", resultado["synthesis_detail"])

    def test_continuacion_tambien_truncada_corta_el_conjunto(self):
        proveedor = _Proveedor(
            _resp(CORTADA, truncated=True),
            _resp("Se calcula dividiendo los días cama ocupados entre los días cama disponibles del periodo. "
                  "Además se compa", truncated=True, eval_count=200),
        )
        with mock.patch.object(R, "presion_llm", return_value=LIBRE):
            resultado = _preguntar(_motor(proveedor))
        self.assertEqual(len(proveedor.llamadas), 2)
        self.assertTrue(resultado["answer"].startswith(TEXTO))
        self.assertNotIn("Además", resultado["answer"])
        self.assertIn("La respuesta completa está en el tablero", resultado["answer"])
        self.assertFalse(resultado["cacheable"])

    def test_sin_nada_completo_usa_el_resumen_extractivo(self):
        proveedor = _Proveedor(_resp("El indicador mide la ocupa", truncated=True))
        with mock.patch.object(R, "presion_llm", return_value=OCUPADO):
            resultado = _preguntar(_motor(proveedor))
        self.assertEqual(resultado["synthesis_mode"], "extractive")
        self.assertIn("se usa el resumen extractivo", resultado["synthesis_issue"])
        self.assertNotIn("token", resultado["answer"].lower())

    def test_respuesta_completa_no_cambia_y_el_diagnostico_lo_dice(self):
        proveedor = _Proveedor(_resp(TEXTO))
        resultado = _preguntar(_motor(proveedor))
        self.assertEqual(resultado["answer"], TEXTO)
        self.assertTrue(resultado["cacheable"])
        self.assertIn("truncada: no", resultado["synthesis_detail"])
        self.assertIn("entrada recortada: no", resultado["synthesis_detail"])

    def test_el_prompt_pide_una_extension_acorde_a_num_predict(self):
        proveedor = _Proveedor(_resp(TEXTO))
        _preguntar(_motor(proveedor))
        self.assertEqual(proveedor.llamadas[0]["max_tokens"], 600)
        self.assertIn("doscientas cincuenta palabras", proveedor.llamadas[0]["messages"][1]["content"])
        with mock.patch.dict(os.environ, {"LLM_NUM_PREDICT_SINTESIS": "300"}):
            proveedor = _Proveedor(_resp(TEXTO))
            _preguntar(_motor(proveedor))
        self.assertEqual(proveedor.llamadas[0]["max_tokens"], 300)
        self.assertIn("ciento veinte palabras", proveedor.llamadas[0]["messages"][1]["content"])

    def test_entrada_que_no_cabe_en_num_ctx_quita_las_fuentes_menos_relevantes(self):
        fuentes = [FUENTE] + [dict(FUENTE, text=f"Fuente extra {letra}. " + "relleno " * 250,
                                   chunk_type="visual") for letra in "XYZ"]
        proveedor = _Proveedor(_resp(TEXTO))
        with mock.patch.dict(os.environ, {"MEDGEMMA_NUM_CTX": "2000", "LLM_CARACTERES_POR_TOKEN": "3.3"}):
            resultado = _preguntar(_motor(proveedor, fuentes))
        usuario = proveedor.llamadas[0]["messages"][1]["content"]
        self.assertIn("ocupación de camas", usuario)
        self.assertNotIn("Fuente extra Z", usuario)
        self.assertIn("entrada recortada: sí", resultado["synthesis_detail"])


def _turno_truncado():
    """Turno real del motor con el arnés tests/sim (Ollama falso que trunca la
    síntesis). Corre en un proceso propio (ver TurnoCompletoTests)."""
    from tests.sim import fakes, harness

    engine, manager, formatter, *_ = harness.build_engine()
    original = fakes.FakeOllamaClient.chat

    def truncada(self, model=None, messages=None, **kwargs):
        respuesta = original(self, model=model, messages=messages, **kwargs)
        contenido = respuesta.message.content
        if contenido.startswith("[FakeLLM]") and "CONTEXTO RECUPERADO" in messages[-1]["content"]:
            return fakes._Obj(message=fakes._Obj(content=contenido[: len(contenido) * 2 // 3]),
                              done_reason="length", eval_count=600, prompt_eval_count=1800)
        return respuesta

    with mock.patch.object(fakes.FakeOllamaClient, "chat", truncada), \
            mock.patch.object(R, "presion_llm", return_value=OCUPADO):
        resultado, _ = harness.ask(engine, manager, formatter, "¿Qué significa el indicador cirugías programadas?")
    return {
        "route": resultado.get("route"), "answer": resultado.get("answer"), "cacheable": resultado.get("cacheable"),
        "lineas": [linea for paso in (resultado.get("reasoning") or {}).get("steps") or [] for linea in paso["lines"]],
    }


class TurnoCompletoTests(unittest.TestCase):
    """Turno real del motor (arnés tests/sim) con la síntesis truncada.

    Corre en OTRO proceso, como la prueba con AppTest de tests/stability: el
    arnés instala módulos falsos en sys.modules (sentence_transformers, ollama,
    qdrant_client, dotenv...) y, en el mismo proceso, chocaría con los módulos
    reales que ya importaron otras pruebas (y los dejaría para las siguientes).
    Así la prueba es hermética e independiente del orden del discover."""

    def test_el_turno_no_es_cacheable_y_la_traza_lo_dice(self):
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "tests.rag.test_sintesis_truncada", ARG_TURNO], check=False,
            cwd=str(RAIZ), capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8"), timeout=600,
        )
        cola = "\n".join((completed.stdout + completed.stderr).splitlines()[-40:])
        self.assertEqual(completed.returncode, 0, cola)
        resultado = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(resultado["route"], "rag", resultado["answer"])
        self.assertIs(resultado["cacheable"], False)
        self.assertTrue(any("truncada: sí" in linea for linea in resultado["lineas"]), resultado["lineas"])


class OtrosPropositosTests(unittest.TestCase):
    def test_reescritura_truncada_se_rechaza(self):
        proveedor = _Proveedor(_resp("¿Cuántos pacientes ingresaron a urgencias en el mes de", truncated=True,
                                     eval_count=80))
        rewriter = LLMContextRewriter(proveedor)
        resultado = rewriter.rewrite("¿y en urgencias?", "Usuario: ¿cuántos pacientes ingresaron?",
                                     "cuántos pacientes ingresaron urgencias mes")
        self.assertEqual(resultado["status"], "rejected")
        self.assertIn("cortada", resultado["reason"])

    def test_descripcion_de_opcion_truncada_sin_frase_completa_se_descarta(self):
        proveedor = _Proveedor(_resp("Cuenta los pacientes atendidos en urgencias durante el", truncated=True,
                                     eval_count=60))
        describer = OptionDescriber(proveedor, timeout=0)
        opcion = {"id": "o1", "label": "PACIENTES URGENCIAS", "measure": "PACIENTES URGENCIAS",
                  "dax_expression": "COUNTROWS('URGENCIAS')", "description": "", "report": "R",
                  "page": "P", "visuals": [], "semantic_model": "M"}
        resultado = describer.describe("pacientes", [opcion])
        # Sin frase completa no hay descripción del LLM: se usa la del catálogo.
        self.assertNotIn("o1", resultado["descriptions"])
        self.assertEqual(resultado["status"], "unparsed")
        self.assertEqual(proveedor.llamadas[0]["max_tokens"], 60)


if __name__ == "__main__":
    if ARG_TURNO in sys.argv:
        # Proceso hijo de TurnoCompletoTests: la última línea es el resultado en JSON.
        print(json.dumps(_turno_truncado(), ensure_ascii=False))
    else:
        unittest.main()

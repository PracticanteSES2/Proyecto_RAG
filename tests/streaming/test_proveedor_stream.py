"""Streaming de MedGemma: `MedGemmaProvider.chat(stream=True, on_token=cb)` y
`llm_gate.call_llm(..., on_token=cb)`. Sin .env ni MedGemma real: cliente
Ollama falso y el servidor HTTP falso de tests/stability (NDJSON real).

Ejecutar: python -X utf8 -m unittest tests.streaming.test_proveedor_stream
"""
import threading
import time
import unittest
from unittest import mock

from ollama import ChatResponse, ResponseError

from src.llm import llm_gate
from src.llm import medgemma_provider as mp
from tests.stability.fake_ollama_server import FakeOllamaServer

PIEZAS = ["El indicador", " mide la", " ocupación", " de camas."]


def _parte(texto, done=False, done_reason=None, eval_count=None):
    return ChatResponse(model="medgemma:latest", message={"role": "assistant", "content": texto},
                        done=done, done_reason=done_reason, eval_count=eval_count)


class _ClienteFalso:
    """Imita ollama.Client.chat: con stream=True devuelve un generador."""

    def __init__(self, piezas=PIEZAS, pausa=0.0, done_reason="stop", error_en=None):
        self.piezas, self.pausa, self.done_reason, self.error_en = list(piezas), pausa, done_reason, error_en
        self.pedidos = []
        self.cerrado = False

    def _generador(self):
        try:
            for indice, pieza in enumerate(self.piezas):
                if self.error_en == indice:
                    raise ResponseError("modelo caído")
                if self.pausa:
                    time.sleep(self.pausa)
                yield _parte(pieza)
            yield _parte("", done=True, done_reason=self.done_reason, eval_count=len(self.piezas))
        finally:
            self.cerrado = True

    def chat(self, **pedido):
        self.pedidos.append(pedido)
        if pedido.get("stream"):
            return self._generador()
        return _parte("".join(self.piezas), done=True, done_reason=self.done_reason,
                      eval_count=len(self.piezas))


def _proveedor(cliente=None, host="http://127.0.0.1:9"):
    with mock.patch.object(mp, "load_dotenv", lambda *a, **k: False):
        proveedor = mp.MedGemmaProvider(host=host, model="medgemma:latest", timeout=30)
    if cliente is not None:
        proveedor._client_for = lambda timeout: cliente
    return proveedor


MENSAJES = [{"role": "user", "content": "¿qué mide el indicador?"}]


class TestProveedorStream(unittest.TestCase):
    def test_tokens_en_orden_y_mismo_resultado_que_sin_stream(self):
        tokens = []
        cliente = _ClienteFalso()
        con_stream = _proveedor(cliente).chat(MENSAJES, stream=True, on_token=tokens.append)
        sin_stream = _proveedor(_ClienteFalso()).chat(MENSAJES)
        self.assertEqual(tokens, PIEZAS)
        self.assertEqual(con_stream, sin_stream)
        self.assertEqual(con_stream["answer"], "El indicador mide la ocupación de camas.")
        self.assertTrue(cliente.pedidos[0]["stream"])
        self.assertTrue(cliente.cerrado)

    def test_sin_stream_el_pedido_no_cambia(self):
        cliente = _ClienteFalso()
        _proveedor(cliente).chat(MENSAJES, on_token=lambda t: None)
        self.assertFalse(cliente.pedidos[0]["stream"])

    def test_corte_por_longitud_marca_truncado(self):
        resultado = _proveedor(_ClienteFalso(done_reason="length")).chat(MENSAJES, stream=True)
        self.assertTrue(resultado["truncated"])
        self.assertEqual(resultado["eval_count"], len(PIEZAS))

    def test_callback_que_lanza_no_cambia_el_resultado(self):
        def roto(_texto):
            raise RuntimeError("la interfaz se cayó")

        resultado = _proveedor(_ClienteFalso()).chat(MENSAJES, stream=True, on_token=roto)
        self.assertEqual(resultado["status"], "success")
        self.assertEqual(resultado["answer"], "El indicador mide la ocupación de camas.")

    def test_respuesta_vacia(self):
        tokens = []
        resultado = _proveedor(_ClienteFalso(piezas=[""])).chat(MENSAJES, stream=True, on_token=tokens.append)
        self.assertEqual(resultado["status"], "empty_response")
        self.assertEqual(tokens, [])

    def test_plazo_total_vence_a_mitad_del_stream(self):
        cliente = _ClienteFalso(piezas=["palabra "] * 40, pausa=0.03)
        tokens = []
        inicio = time.monotonic()
        resultado = _proveedor(cliente).chat(MENSAJES, stream=True, on_token=tokens.append, timeout=0.2)
        self.assertLess(time.monotonic() - inicio, 0.6)
        self.assertEqual(resultado["status"], "llm_timeout")
        self.assertIsNone(resultado["answer"])
        self.assertTrue(cliente.cerrado)  # generador cerrado = conexión cerrada
        self.assertLess(len(tokens), 40)

    def test_error_de_ollama_a_mitad(self):
        resultado = _proveedor(_ClienteFalso(error_en=2)).chat(MENSAJES, stream=True)
        self.assertEqual(resultado["status"], "ollama_error")


class TestProveedorStreamHTTP(unittest.TestCase):
    """Cliente Ollama real contra el servidor falso que transmite NDJSON."""

    def test_stream_real_por_http(self):
        contenido = "El tablero muestra los indicadores documentados."
        with FakeOllamaServer(content_fn=lambda pedido: contenido) as servidor:
            tokens = []
            resultado = _proveedor(host=servidor.url).chat(MENSAJES, stream=True, on_token=tokens.append)
        self.assertEqual(resultado["status"], "success")
        self.assertEqual(resultado["answer"], contenido)
        self.assertGreater(len(tokens), 3)
        self.assertEqual("".join(tokens), contenido)

    def test_al_vencer_se_cierra_la_conexion_y_el_servidor_deja_de_generar(self):
        contenido = " ".join(["palabra"] * 60)
        with FakeOllamaServer(content_fn=lambda pedido: contenido) as servidor:
            servidor.stream_chunk_s = 0.03
            resultado = _proveedor(host=servidor.url).chat(MENSAJES, stream=True, on_token=lambda t: None,
                                                           timeout=0.4)
            self.assertEqual(resultado["status"], "llm_timeout")
            limite = time.monotonic() + 3
            while servidor.snapshot()["cancelled_streaming"] < 1 and time.monotonic() < limite:
                time.sleep(0.05)
            self.assertEqual(servidor.snapshot()["cancelled_streaming"], 1)
            self.assertEqual(servidor.snapshot()["completed"], 0)


class _ProveedorConTokens:
    enforces_timeout = True

    def __init__(self, piezas=PIEZAS):
        self.piezas = piezas
        self.recibido = {}

    def chat(self, messages, timeout=None, stream=False, on_token=None):
        self.recibido = {"stream": stream, "on_token": on_token, "timeout": timeout}
        for pieza in self.piezas if stream and on_token else []:
            on_token(pieza)
        return {"status": "success", "answer": "".join(self.piezas).strip()}


class _ProveedorAntiguo:
    """Doble de prueba sin `stream` ni `on_token`."""

    def chat(self, messages, temperature=0.1, max_tokens=450, think=False):
        return {"status": "success", "answer": "respuesta"}


class _ProveedorLentoSinLimite:
    """Sin tiempo límite propio: la puerta lo espera en un hilo y lo abandona."""

    enforces_timeout = False

    def __init__(self):
        self.terminado = threading.Event()

    def chat(self, messages, stream=False, on_token=None):
        for indice in range(30):
            on_token(f"t{indice} ")
            time.sleep(0.02)
        self.terminado.set()
        return {"status": "success", "answer": "tarde"}


class _BackendSinHueco:
    name = "memoria"

    def acquire(self, queue_wait, **kwargs):
        return None

    def state(self, ident=None):
        return {"capacity": 1, "in_flight": 1, "waiting": 0, "position": None, "ahead": None}


class TestPuertaConTokens(unittest.TestCase):
    def test_pasa_stream_y_tokens_al_proveedor_sin_cambiar_el_resultado(self):
        tokens = []
        proveedor = _ProveedorConTokens()
        resultado = llm_gate.call_llm(proveedor, MENSAJES, purpose="prueba", timeout=5, on_token=tokens.append)
        self.assertEqual(tokens, PIEZAS)
        self.assertTrue(proveedor.recibido["stream"])
        self.assertEqual(resultado, llm_gate.call_llm(_ProveedorConTokens(), MENSAJES, purpose="prueba", timeout=5))

    def test_sin_on_token_no_pide_stream(self):
        proveedor = _ProveedorConTokens()
        llm_gate.call_llm(proveedor, MENSAJES, purpose="prueba", timeout=5)
        self.assertFalse(proveedor.recibido["stream"])
        self.assertIsNone(proveedor.recibido["on_token"])

    def test_callback_que_lanza_no_rompe_la_llamada(self):
        def roto(_texto):
            raise RuntimeError("boom")

        resultado = llm_gate.call_llm(_ProveedorConTokens(), MENSAJES, purpose="prueba", timeout=5, on_token=roto)
        self.assertEqual(resultado["status"], "success")

    def test_proveedor_sin_on_token_funciona_igual(self):
        resultado = llm_gate.call_llm(_ProveedorAntiguo(), MENSAJES, purpose="prueba", on_token=lambda t: None)
        self.assertEqual(resultado["status"], "success")

    def test_tras_abandonar_por_tiempo_no_llegan_mas_tokens(self):
        tokens = []
        proveedor = _ProveedorLentoSinLimite()
        resultado = llm_gate.call_llm(proveedor, MENSAJES, purpose="prueba", timeout=0.15, on_token=tokens.append)
        self.assertEqual(resultado["status"], "llm_timeout")
        recibidos = len(tokens)
        self.assertTrue(proveedor.terminado.wait(3))
        self.assertEqual(len(tokens), recibidos)
        self.assertLess(recibidos, 30)

    def test_saturado_sin_tokens_y_mismo_status(self):
        tokens = []
        llm_gate.set_backend(_BackendSinHueco())
        try:
            resultado = llm_gate.call_llm(_ProveedorConTokens(), MENSAJES, purpose="prueba", queue_wait=0.01,
                                          on_token=tokens.append)
        finally:
            llm_gate.set_backend(None)
        self.assertEqual(resultado["status"], "llm_saturated")
        self.assertEqual(tokens, [])


if __name__ == "__main__":
    unittest.main()

"""
Caché de llamadas al LLM dentro del motor (src/chatbot/cache_llm.py) y su
almacén Redis (backend/app/services/cache_llm_redis.py, con fakeredis).

    .venv\\Scripts\\python.exe -X utf8 -m unittest tests.perf.test_cache_llm

No usa red, .env, Ollama ni Power BI.
"""
import os
import sys
import threading
import time
import types
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "dotenv" not in sys.modules:
    _dotenv = types.ModuleType("dotenv")
    _dotenv.load_dotenv = lambda *a, **k: False
    _dotenv.find_dotenv = lambda *a, **k: ""
    _dotenv.__sim_fake__ = True
    sys.modules["dotenv"] = _dotenv

try:
    import fakeredis
except ImportError:  # pragma: no cover
    fakeredis = None

from src.chatbot import cache_llm  # noqa: E402
from src.chatbot.cache_llm import AlmacenMemoria, clave, guardable, llamar_con_cache  # noqa: E402
from src.chatbot.runtime_stats import STATS  # noqa: E402

OK = {"status": "success", "answer": "Respuesta completa.", "model": "m", "done_reason": "stop"}


class _Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class _Contador:
    def __init__(self, resultado=None, espera=0.0):
        self.n = 0
        self.resultado = resultado or OK
        self.espera = espera
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            self.n += 1
        if self.espera:
            time.sleep(self.espera)
        return dict(self.resultado)


class _Base(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ("LLM_CACHE", "LLM_CACHE_TTL_S")}
        os.environ.pop("LLM_CACHE", None)
        cache_llm.configurar_almacen(AlmacenMemoria())
        cache_llm.fijar_version("")

    def tearDown(self):
        cache_llm.configurar_almacen(None)
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class AlmacenMemoriaTests(unittest.TestCase):
    def test_lru_desaloja_la_menos_usada(self):
        almacen = AlmacenMemoria(max_entradas=2)
        almacen.guardar("a", {"v": 1}, 60)
        almacen.guardar("b", {"v": 2}, 60)
        self.assertEqual(almacen.leer("a"), {"v": 1})  # «a» pasa a ser la más reciente
        almacen.guardar("c", {"v": 3}, 60)
        self.assertIsNone(almacen.leer("b"))
        self.assertEqual(almacen.leer("a"), {"v": 1})
        self.assertEqual(len(almacen), 2)

    def test_ttl_vence(self):
        reloj = _Reloj()
        almacen = AlmacenMemoria(reloj=reloj)
        almacen.guardar("a", {"v": 1}, 10)
        reloj.t += 9
        self.assertEqual(almacen.leer("a"), {"v": 1})
        reloj.t += 2
        self.assertIsNone(almacen.leer("a"))

    def test_devuelve_copias(self):
        almacen = AlmacenMemoria()
        almacen.guardar("a", {"v": [1]}, 60)
        leido = almacen.leer("a")
        leido["v"].append(2)
        self.assertEqual(almacen.leer("a"), {"v": [1]})


class ClaveTests(_Base):
    def test_misma_pregunta_con_otra_forma_da_la_misma_clave(self):
        a = clave("síntesis RAG", "¿Qué es NEDOCS?", fuentes="F1", prompt="P", modelo="m", max_tokens=600)
        b = clave("síntesis RAG", "que es nedocs", fuentes="F1", prompt="P", modelo="m", max_tokens=600)
        self.assertEqual(a, b)

    def test_cambia_con_fuentes_prompt_modelo_tokens_proposito_y_version(self):
        base = dict(pregunta="que es nedocs", fuentes="F1", prompt="P", modelo="m", max_tokens=600)
        k0 = clave("síntesis RAG", **base)
        variantes = [
            clave("síntesis RAG", **dict(base, fuentes="F2")),
            clave("síntesis RAG", **dict(base, prompt="P2")),
            clave("síntesis RAG", **dict(base, modelo="otro")),
            clave("síntesis RAG", **dict(base, max_tokens=350)),
            clave("descripción de opciones", **base),
            clave("síntesis RAG", **dict(base, pregunta="que es triage")),
        ]
        cache_llm.fijar_version("indice-2")
        variantes.append(clave("síntesis RAG", **base))
        self.assertEqual(len(set(variantes + [k0])), len(variantes) + 1)

    def test_guardable_solo_respuestas_completas(self):
        self.assertTrue(guardable(OK))
        for malo in (
            {"status": "llm_saturated", "answer": None},
            {"status": "llm_timeout", "answer": None},
            {"status": "success", "answer": ""},
            {"status": "success", "answer": "corta a la mi", "truncated": True},
            {"status": "success", "answer": "corta a la mi", "done_reason": "length"},
            None,
        ):
            self.assertFalse(guardable(malo), malo)


class LlamarConCacheTests(_Base):
    def test_segunda_llamada_no_llega_al_llm(self):
        llamar = _Contador()
        before = STATS.snapshot()
        r1 = llamar_con_cache("k", llamar, proposito="síntesis RAG")
        r2 = llamar_con_cache("k", llamar, proposito="síntesis RAG")
        after = STATS.snapshot()
        self.assertEqual(llamar.n, 1)
        self.assertEqual(r1["answer"], r2["answer"])
        self.assertEqual(r2["cache"], "hit")
        self.assertEqual(after["llm_cache"]["hits"] - before["llm_cache"]["hits"], 1)
        self.assertEqual(after["llm_avoided"].get("caché: síntesis RAG", 0)
                         - before["llm_avoided"].get("caché: síntesis RAG", 0), 1)

    def test_no_guarda_degradadas_ni_truncadas(self):
        for resultado in ({"status": "llm_saturated", "answer": None},
                          {"status": "success", "answer": "a medias", "truncated": True}):
            llamar = _Contador(resultado)
            llamar_con_cache("k-" + resultado["status"], llamar)
            llamar_con_cache("k-" + resultado["status"], llamar)
            self.assertEqual(llamar.n, 2, resultado)

    def test_predicado_propio_de_quien_llama(self):
        llamar = _Contador()
        llamar_con_cache("k", llamar, es_guardable=lambda r: False)
        llamar_con_cache("k", llamar, es_guardable=lambda r: False)
        self.assertEqual(llamar.n, 2)

    def test_apagada_con_variable_de_entorno(self):
        os.environ["LLM_CACHE"] = "off"
        llamar = _Contador()
        llamar_con_cache("k", llamar)
        r = llamar_con_cache("k", llamar)
        self.assertEqual(llamar.n, 2)
        self.assertNotIn("cache", r)

    def test_peticiones_identicas_simultaneas_hacen_una_sola_llamada(self):
        llamar = _Contador(espera=0.3)
        resultados = []
        hilos = [threading.Thread(target=lambda: resultados.append(llamar_con_cache("k", llamar)))
                 for _ in range(4)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(5)
        self.assertEqual(llamar.n, 1)
        self.assertEqual(len(resultados), 4)
        self.assertTrue(all(r["answer"] == OK["answer"] for r in resultados))
        self.assertEqual(sum(r.get("cache") in ("compartida", "hit") for r in resultados), 3)

    def test_si_la_lider_falla_las_demas_llaman_por_su_cuenta(self):
        llamar = _Contador({"status": "llm_saturated", "answer": None}, espera=0.2)
        hilos = [threading.Thread(target=llamar_con_cache, args=("k", llamar)) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(5)
        self.assertEqual(llamar.n, 2)

    def test_almacen_caido_no_rompe_la_llamada(self):
        class Roto:
            nombre = "roto"

            def leer(self, clave):
                raise ConnectionError("caído")

            def guardar(self, clave, valor, ttl_s):
                raise ConnectionError("caído")

        cache_llm.configurar_almacen(Roto())
        llamar = _Contador()
        with self.assertLogs("cache_llm", level="WARNING"):
            r = llamar_con_cache("k", llamar)
        self.assertEqual(r["answer"], OK["answer"])

    def test_solo_guarda_campos_de_la_respuesta(self):
        llamar = _Contador(dict(OK, host="http://servidor", queue_wait_s=3.0))
        llamar_con_cache("k", llamar)
        r = llamar_con_cache("k", llamar)
        self.assertNotIn("host", r)
        self.assertNotIn("queue_wait_s", r)


@unittest.skipIf(fakeredis is None, "fakeredis no instalado")
class AlmacenRedisTests(_Base):
    def test_misma_interfaz_con_ttl_y_prefijo(self):
        from backend.app.services.cache_llm_redis import AlmacenRedis

        cliente = fakeredis.FakeRedis()
        almacen = AlmacenRedis(cliente, prefijo="rag")
        almacen.guardar("abc", {"status": "success", "answer": "hola"}, 60)
        self.assertEqual(almacen.leer("abc"), {"status": "success", "answer": "hola"})
        self.assertIsNone(almacen.leer("otra"))
        self.assertEqual(cliente.keys("*"), [b"rag:llm:abc"])
        self.assertTrue(0 < cliente.ttl("rag:llm:abc") <= 60)

    def test_compartida_entre_procesos(self):
        from backend.app.services.cache_llm_redis import AlmacenRedis

        servidor = fakeredis.FakeServer()
        cache_llm.configurar_almacen(AlmacenRedis(fakeredis.FakeRedis(server=servidor)))
        llamar = _Contador()
        llamar_con_cache("k", llamar)
        # Otro worker con su propio cliente contra el mismo Redis.
        cache_llm.configurar_almacen(AlmacenRedis(fakeredis.FakeRedis(server=servidor)))
        r = llamar_con_cache("k", llamar)
        self.assertEqual(llamar.n, 1)
        self.assertEqual(r["cache"], "hit")


if __name__ == "__main__":
    unittest.main()

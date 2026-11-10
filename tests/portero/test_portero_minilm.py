"""Calibración del portero con el MiniLM real (solo caché local, sin red)."""

import json
import os
import sys
import time
import unittest
from pathlib import Path

from src.chatbot.portero import (
    SimilitudPortero,
    bloqueado_por_guardas,
    clasificar,
    normalizar,
    vocabulario_dominio,
)
from tests.portero.test_portero import BANCO, PROJECT_ROOT, _json

VOCAB = vocabulario_dominio(PROJECT_ROOT)
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # = src.rag.retriever


def _cargar_modelo():
    # En `unittest discover` el arnés de tests/sim ya instaló un
    # sentence_transformers falso: se aparta un momento para cargar el real.
    falso = sys.modules.get("sentence_transformers")
    if falso is not None and getattr(falso, "__file__", None) is None:
        del sys.modules["sentence_transformers"]
        try:
            return _cargar_modelo_real()
        finally:
            sys.modules["sentence_transformers"] = falso
    return _cargar_modelo_real()


def _cargar_modelo_real():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer

    # Sin importar src.rag.retriever: dejaría el qdrant_client real en
    # sys.modules y rompería las pruebas del arnés (tests/sim) del mismo proceso.
    try:
        return SentenceTransformer(MODEL_NAME, local_files_only=True)
    except TypeError:
        # Versión sin local_files_only: se fuerza el modo sin red para que
        # el respaldo nunca pueda descargar nada; luego se restauran los valores.
        previo = {k: os.environ.get(k) for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            return SentenceTransformer(MODEL_NAME)
        finally:
            for k, v in previo.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def _no_disponible(mensaje):
    """Sin MiniLM local: se omite, salvo PORTERO_REQUIRE_MINILM=1 (entonces falla)."""
    if os.environ.get("PORTERO_REQUIRE_MINILM") == "1":
        raise AssertionError(mensaje)
    raise unittest.SkipTest(mensaje)


def _textos_banco_real():
    return [c["pregunta"] for c in _json("banco_real.json")["casos"]]


class TestPorteroMiniLM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.modelo = _cargar_modelo()
        except Exception as exc:  # sin caché local: se omite, nunca se descarga
            _no_disponible(f"MiniLM no disponible offline: {exc}")
        cls.sim = SimilitudPortero(cls.modelo)
        if not cls.sim.activa:
            _no_disponible("SimilitudPortero inactiva")

    def _casos(self):
        return json.loads(BANCO.read_text(encoding="utf-8"))["casos"]

    def test_cobertura_banco_portero_con_similitud(self):
        casos = [c for c in self._casos() if c["esperado"] is not None and c["id"].startswith("C")]
        aciertos = 0
        for c in casos:
            r = clasificar(c["texto"], VOCAB, similitud=self.sim)
            if r is not None and f"{r.tipo}/{r.subtipo}" == c["esperado"]:
                aciertos += 1
        self.assertGreaterEqual(aciertos / len(casos), 0.90, f"{aciertos}/{len(casos)}")

    def test_sin_falsos_positivos_banco_portero(self):
        malos = [c["id"] for c in self._casos()
                 if c["esperado"] is None
                 and clasificar(c["texto"], VOCAB, similitud=self.sim) is not None]
        self.assertEqual(malos, [])

    def test_sin_falsos_positivos_dejando_uno_fuera(self):
        """Quita de las referencias la propia pregunta para no medir una trampa."""
        malos = []
        textos = [c["texto"] for c in self._casos() if c["esperado"] is None]
        textos += _textos_banco_real()
        for t in textos:
            n = len(normalizar(t).split())
            if bloqueado_por_guardas(t, VOCAB) or not 3 <= n <= 8:
                continue
            clave, sim, dom = self.sim.mejor(t, excluir_igual=True)
            if sim >= self.sim.umbral and sim - dom >= self.sim.margen \
                    and clasificar(t, VOCAB) is None:
                malos.append(t)
        self.assertEqual(malos, [])

    def test_barrido_banco_real_sin_intercepciones(self):
        interceptados = [t for t in _textos_banco_real()
                         if clasificar(t, VOCAB, similitud=self.sim) is not None]
        self.assertEqual(interceptados, [])

    # ---- Fuera de alcance (spec 002) con MiniLM real ----

    def test_alcance_sin_falsos_positivos_en_todos_los_bancos(self):
        from tests.portero.test_portero_alcance import _casos, _como_motor, textos_todos_los_bancos

        textos = textos_todos_los_bancos() + [c["texto"] for c in _casos("N") + _casos("D")]
        malos = [t for t in textos if (r := _como_motor(t, self.sim)) is not None
                 and r.tipo == "fuera_de_alcance"]
        self.assertEqual(malos, [])

    def test_alcance_capta_parafrasis_por_similitud(self):
        """Paráfrasis nuevas (ni ejemplos ni casos del banco) sin marcador de regla."""
        casos = {
            "dime algo chistoso": "entretenimiento", "como aprendo a programar": "programacion",
            "que paso con la guerra": "fuera_de_alcance",
        }
        for texto, sub in casos.items():
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto, VOCAB))  # sin similitud no se capta
                r = clasificar(texto, VOCAB, similitud=self.sim)
                self.assertIsNotNone(r)
                self.assertEqual(r.motivo, "similitud")
                self.assertIn(sub, (r.subtipo, r.tipo))

    def test_latencia_media_menor_50_ms(self):
        textos = ["que tal como estas hoy", "eso es todo muchas gracias",
                  "que cosas puedo consultar", "quien te creo y para que"]
        self.sim.mejor(textos[0])  # calentamiento
        t0 = time.perf_counter()
        n = 40
        for i in range(n):
            # Sin la caché de vectores: se mide el coste real de un mensaje nuevo.
            self.sim.__dict__.pop("_cache_vectores", None)
            clasificar(textos[i % len(textos)], VOCAB, similitud=self.sim)
        media_ms = (time.perf_counter() - t0) / n * 1000
        self.assertLess(media_ms, 50, f"{media_ms:.1f} ms")


if __name__ == "__main__":
    unittest.main()

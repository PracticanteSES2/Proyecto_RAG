"""Calibración del portero con el MiniLM real (solo caché local, sin red)."""

import json
import os
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


def _cargar_modelo():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer

    from src.rag.retriever import MODEL_NAME

    try:
        return SentenceTransformer(MODEL_NAME, local_files_only=True)
    except TypeError:
        return SentenceTransformer(MODEL_NAME)


def _textos_banco_real():
    return [c["pregunta"] for c in _json("banco_real.json")["casos"]]


class TestPorteroMiniLM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.modelo = _cargar_modelo()
        except Exception as exc:  # sin caché local: se omite, nunca se descarga
            raise unittest.SkipTest(f"MiniLM no disponible offline: {exc}")
        cls.sim = SimilitudPortero(cls.modelo)
        if not cls.sim.activa:
            raise unittest.SkipTest("SimilitudPortero inactiva")

    def _casos(self):
        return json.loads(BANCO.read_text(encoding="utf-8"))["casos"]

    def test_cobertura_banco_portero_con_similitud(self):
        casos = [c for c in self._casos() if c["esperado"] is not None]
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

    def test_latencia_media_menor_50_ms(self):
        textos = ["que tal como estas hoy", "eso es todo muchas gracias",
                  "que cosas puedo consultar", "quien te creo y para que"]
        self.sim.mejor(textos[0])  # calentamiento
        t0 = time.perf_counter()
        n = 40
        for i in range(n):
            clasificar(textos[i % len(textos)], VOCAB, similitud=self.sim)
        media_ms = (time.perf_counter() - t0) / n * 1000
        self.assertLess(media_ms, 50, f"{media_ms:.1f} ms")


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from pathlib import Path

from src.chatbot.portero import (
    bloqueado_por_guardas,
    clasificar,
    normalizar,
    vocabulario_dominio,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BANCO = Path(__file__).with_name("banco_portero.json")
VOCAB = vocabulario_dominio(PROJECT_ROOT)


def _json(nombre):
    return json.loads((PROJECT_ROOT / "tests" / "real" / nombre).read_text(encoding="utf-8"))


def _textos_reales():
    textos = []
    for nombre in ("banco_real.json", "banco_holdout.json", "banco_holdout2.json"):
        for caso in _json(nombre)["casos"]:
            textos.append(caso["pregunta"])
            for extra in caso.get("turnos_extra") or []:
                textos.append(extra.removeprefix("texto: "))
    for conv in _json("banco_multiturno.json")["conversaciones"]:
        for turno in conv["turnos"]:
            if turno.get("entrada"):
                textos.append(turno["entrada"])
    return textos


class TestPortero(unittest.TestCase):
    def test_vocabulario_dominio_no_vacio(self):
        self.assertGreater(len(VOCAB), 100)

    def test_normalizar(self):
        self.assertEqual(normalizar("¿Cómo   estás HOY?!"), "como estas hoy")

    def test_saludos_basicos(self):
        casos = [
            ("hola", "subtipo", "saludo"),
            ("¿Cómo estás hoy?", "subtipo", "estado"),
            ("gracias", "subtipo", "agradecimiento"),
            ("¿quién eres?", "tipo", "identidad"),
            ("¿qué puedes hacer?", "tipo", "capacidades"),
            ("ayuda", "tipo", "capacidades"),
        ]
        for texto, campo, valor in casos:
            with self.subTest(texto=texto):
                c = clasificar(texto)
                self.assertIsNotNone(c)
                self.assertEqual(getattr(c, campo), valor)
                self.assertEqual(c.motivo, "regla")

    def test_saludo_mas_pregunta_no_se_intercepta(self):
        texto = "hola, ¿cuántas cirugías hubo en octubre?"
        self.assertIsNone(clasificar(texto, frozenset({"cirugias"})))
        self.assertEqual(bloqueado_por_guardas("hola 2025", frozenset()), "numero")
        self.assertEqual(bloqueado_por_guardas("buenas, en octubre", frozenset()), "periodo")
        self.assertEqual(
            bloqueado_por_guardas("hola cirugías", frozenset({"cirugias"})), "dominio")

    def test_hoy_solo_no_bloquea(self):
        self.assertIsNone(bloqueado_por_guardas("¿cómo estás hoy?", frozenset()))

    def test_mensaje_largo_no_se_intercepta(self):
        texto = "hola quiero que me ayudes con una cosa muy importante para mi"
        self.assertEqual(bloqueado_por_guardas(texto, frozenset()), "largo")
        self.assertIsNone(clasificar(texto))

    def test_lista_de_bloqueo_y_respuestas_a_contrapregunta(self):
        for texto in ("como vamos", "resumen", "novedades", "que hay de nuevo",
                      "ayuda con las camas", "listo", "ok", "si", "no", "ninguna",
                      "dale", "perfecto"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto))

    def test_tipeo_solo_en_palabras_largas(self):
        self.assertEqual(clasificar("holaa").subtipo, "saludo")
        self.assertEqual(clasificar("graciass").subtipo, "agradecimiento")
        self.assertEqual(clasificar("buenos diass").subtipo, "saludo")
        self.assertEqual(clasificar("muchisima gracias").subtipo, "agradecimiento")

    def test_palabras_reales_parecidas_no_se_interceptan(self):
        for texto in ("sola", "cola", "mola", "rola", "bola", "holas", "ayudo",
                      "ayudas", "ayudar", "ayudan", "que eras", "que seres",
                      "nos vamos", "nos vimos", "como estan", "buenos diaz",
                      "muchas gracios"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto))

    def test_banco_portero_sin_falsos_positivos(self):
        casos = json.loads(BANCO.read_text(encoding="utf-8"))["casos"]
        malos = [c["id"] for c in casos
                 if c["esperado"] is None and clasificar(c["texto"], VOCAB) is not None]
        self.assertEqual(malos, [], f"falsos positivos: {malos}")

    def test_banco_portero_cobertura_reglas(self):
        casos = [c for c in json.loads(BANCO.read_text(encoding="utf-8"))["casos"]
                 if c["esperado"] is not None]
        aciertos = 0
        for c in casos:
            r = clasificar(c["texto"], VOCAB)
            if r is not None and f"{r.tipo}/{r.subtipo}" == c["esperado"]:
                aciertos += 1
        self.assertGreaterEqual(aciertos / len(casos), 0.75, f"{aciertos}/{len(casos)}")

    def test_barrido_bancos_reales_sin_intercepciones(self):
        textos = _textos_reales()
        self.assertGreater(len(textos), 100)
        interceptados = [t for t in textos if clasificar(t, VOCAB) is not None]
        self.assertEqual(interceptados, [])


if __name__ == "__main__":
    unittest.main()

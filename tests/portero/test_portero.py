import json
import time
import unittest
from pathlib import Path

import numpy as np

from src.chatbot.portero import (
    Clasificacion,
    EJEMPLOS,
    SimilitudPortero,
    bloqueado_por_guardas,
    catalogo_tableros,
    clasificar,
    normalizar,
    responder,
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


class _ModeloFalso:
    """encode devuelve vectores fijos: ejemplos de charla en el eje 0,
    referencias de dominio en un vector cercano a la charla, consultas por mapa."""

    CHARLA = (1.0, 0.0, 0.0)
    DOMINIO = (0.6, 0.8, 0.0)

    def __init__(self, consultas):
        self.consultas = {normalizar(k): v for k, v in consultas.items()}
        self.ejemplos = {normalizar(t) for lista in EJEMPLOS.values() for t in lista}

    def encode(self, textos, **kwargs):
        filas = []
        for t in textos:
            n = normalizar(t)
            if n in self.consultas:
                v = self.consultas[n]
            elif n in self.ejemplos:
                v = self.CHARLA
            else:
                v = self.DOMINIO
            v = np.array(v, dtype=float)
            filas.append(v / np.linalg.norm(v))
        return np.array(filas)


class _ModeloQueFalla:
    def encode(self, textos, **kwargs):
        raise RuntimeError("sin modelo")


class _Router:
    def __init__(self, models, docs):
        self.models = models
        self._documentation_dashboards = docs


class TestSimilitudFalsa(unittest.TestCase):
    def setUp(self):
        self.modelo = _ModeloFalso({
            "mensaje alto con margen": (1, 0, 0),
            "mensaje alto sin margen": (0.8, 0.6, 0),
            "mensaje bajo": (0, 0, 1),
            "buenas cirugias hoy": (1, 0, 0),
            "todo tranquilo por alla": (1, 0, 0),
        })
        self.sim = SimilitudPortero(self.modelo)

    def test_similitud_intercepta_solo_sobre_umbral_y_margen(self):
        c = clasificar("mensaje alto con margen", similitud=self.sim)
        self.assertIsNotNone(c)
        self.assertEqual(c.motivo, "similitud")
        self.assertIsNone(clasificar("mensaje alto sin margen", similitud=self.sim))
        self.assertIsNone(clasificar("mensaje bajo", similitud=self.sim))

    def test_similitud_no_aplica_a_una_o_dos_palabras(self):
        modelo = _ModeloFalso({"mensaje alto": (1, 0, 0)})
        self.assertIsNone(clasificar("mensaje alto", similitud=SimilitudPortero(modelo)))

    def test_similitud_no_salta_guardas(self):
        self.assertIsNone(
            clasificar("buenas cirugias hoy", frozenset({"cirugias"}), similitud=self.sim))

    def test_modelo_que_falla_deja_solo_reglas(self):
        s = SimilitudPortero(_ModeloQueFalla())
        self.assertIsNone(s.mejor("todo tranquilo por alla"))
        self.assertEqual(clasificar("hola", similitud=s).motivo, "regla")
        self.assertIsNone(clasificar("todo tranquilo por alla", similitud=s))

    def test_catalogo_dos_grupos(self):
        router = _Router(
            [{"semantic_model": "CIRUGIAS", "semantic_model_key": "cirugias"}],
            [("CIRUGIAS", "cirugias"), ("TRIAGE", "atenciones"),
             ("DICCIONARIO X", "x"), ("TRIAGE", "atenciones")])
        self.assertEqual(catalogo_tableros(router), (["Cirugias"], ["Triage"]))

    def test_catalogo_entrada_malformada_no_descarta_el_resto(self):
        router = _Router(
            [{"semantic_model": "CIRUGIAS", "semantic_model_key": "cirugias"}],
            [("TRIAGE", "atenciones"), None, ("solo-uno",), 42, ("CAMAS", "camas")])
        self.assertEqual(catalogo_tableros(router), (["Cirugias"], ["Camas", "Triage"]))

    def test_similitud_sin_referencias_de_dominio_no_clasifica(self):
        class _ModeloVacio(_ModeloFalso):
            def encode(self, textos, **kwargs):
                if not textos:
                    return np.zeros((0, 3))
                return super().encode(textos, **kwargs)

        s = SimilitudPortero(_ModeloVacio({"mensaje alto con margen": (1, 0, 0)}),
                             referencias_dominio=[])
        self.assertTrue(s.activa)
        self.assertIsNone(s.mejor("mensaje alto con margen"))
        self.assertIsNone(clasificar("mensaje alto con margen", similitud=s))
        # Sin referencias tras excluir la idéntica (leave-one-out): tampoco hay margen.
        s = SimilitudPortero(self.modelo, referencias_dominio=["mensaje alto con margen"])
        self.assertIsNone(s.mejor("mensaje alto con margen", excluir_igual=True))

    def test_catalogo_sin_router(self):
        self.assertEqual(catalogo_tableros(None), ([], []))
        self.assertEqual(catalogo_tableros(object()), ([], []))

    def test_respuesta_capacidades(self):
        c = Clasificacion("capacidades", "capacidades", 1.0, "regla")
        texto = responder(c, ["Cirugias", "Camas"], ["Triage"])
        self.assertIn("**Datos**", texto)
        self.assertIn("Cirugias, Camas", texto)
        self.assertIn("**Documentación**", texto)
        self.assertIn("Triage", texto)
        solo_datos = responder(c, ["Camas"], [])
        self.assertNotIn("**Documentación**", solo_datos)
        vacio = responder(c, [], [])
        self.assertNotIn("**Datos**", vacio)
        self.assertIn("indicadores", vacio)

    def test_respuesta_identidad_dice_no_clinico(self):
        c = Clasificacion("identidad", "identidad", 1.0, "regla")
        texto = responder(c, [], [])
        self.assertIn("No doy recomendaciones clínicas", texto)

    def test_respuestas_charla(self):
        for sub, esperado in (("saludo", "Hola"), ("estado", "Hola"),
                              ("agradecimiento", "Con gusto"), ("despedida", "Hasta pronto")):
            c = Clasificacion("charla", sub, 1.0, "regla")
            self.assertIn(esperado, responder(c, [], []))


class _RouterConPaginas(_Router):
    def __init__(self, models, docs, paginas):
        super().__init__(models, docs)
        self._paginas = paginas

    def pages_for_model(self, modelo):
        return [{"dashboard": p} for p in self._paginas.get(modelo, [])]


class TestRevisionPortero(unittest.TestCase):
    """Correcciones de la revisión (F1, F3, F4, F5, F6)."""

    def test_que_mas_solo_no_es_saludo(self):
        for texto in ("que mas", "q mas", "k mas", "¿qué más?", "Qué más", "gracias, ¿qué más?"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto, VOCAB))
        self.assertEqual(clasificar("hola, ¿qué más?", VOCAB).subtipo, "saludo")
        self.assertEqual(clasificar("que mas como vas", VOCAB).subtipo, "estado")
        self.assertEqual(clasificar("qué más, ¿cómo vas?", VOCAB).subtipo, "estado")

    def test_texto_enorme_sale_rapido(self):
        for texto in ("a" * 1_000_000, "ﷺ" * 100_000, "h" + "o" * 500_000 + "la"):
            t0 = time.perf_counter()
            self.assertIsNone(clasificar(texto, VOCAB))
            self.assertLess(time.perf_counter() - t0, 0.2)
        self.assertIsNone(clasificar("hola " + "a" * 200, VOCAB))

    def test_dos_frases_unidas_con_prioridad(self):
        casos = {
            "hola buenas tardes": "saludo", "chao gracias": "despedida",
            "gracias chao": "despedida", "hola como estas": "estado",
            "hola quien eres": "identidad", "gracias que puedes hacer": "capacidades",
            "buenas noches gracias": "agradecimiento",
        }
        for texto, sub in casos.items():
            with self.subTest(texto=texto):
                c = clasificar(texto, VOCAB)
                self.assertIsNotNone(c)
                self.assertEqual((c.subtipo, c.motivo), (sub, "regla"))
        for texto in ("hola hola hola hola hola", "gracias ninguna", "ok", "listo",
                      "gracias por las cirugias", "hola de nuevo"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto, VOCAB))

    def test_frase_exacta_no_la_bloquean_dominio_ni_periodo(self):
        vocab = frozenset({"todos", "manana", "nombre", "opciones"})
        casos = {
            "hasta mañana": "despedida", "buenos días a todos": "saludo",
            "hola a todos": "saludo", "buenas tardes a todos": "saludo",
            "gracias parce": "agradecimiento", "quiubo parce": "saludo",
            "q hubo": "saludo", "qué hubo": "saludo", "necesito ayuda": "capacidades",
            "qué opciones hay": "capacidades", "cuál es tu nombre": "identidad",
        }
        for texto, sub in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto, vocab).subtipo, sub)
        # Con un número siempre se bloquea; con una edición, las guardas valen.
        self.assertIsNone(clasificar("hasta mañana 2", vocab))
        self.assertEqual(clasificar("buenas tarde a todos").subtipo, "saludo")
        self.assertIsNone(clasificar("buenas tarde a todos", frozenset({"todos"})))
        self.assertIsNone(clasificar("buenas tardes a todo", frozenset({"todo"})))

    def test_referencias_sin_leer_tests(self):
        from unittest import mock
        from src.chatbot import portero

        self.assertEqual(portero.REFERENCIAS_PATH.parent.name, "chatbot")
        original = Path.read_text

        def sin_tests(self_path, *a, **k):
            if "tests" in Path(self_path).parts:
                raise AssertionError(f"produccion leyo {self_path}")
            return original(self_path, *a, **k)

        with mock.patch.object(Path, "read_text", sin_tests):
            refs = portero.referencias_dominio_defecto()
        self.assertGreater(len(refs), 100)
        self.assertIn("cuantas camas hay disponibles", refs)
        holdouts = {c["pregunta"] for n in ("banco_holdout.json", "banco_holdout2.json")
                    for c in _json(n)["casos"] if c.get("pregunta")} - {
            c["pregunta"] for c in _json("banco_real.json")["casos"]}
        self.assertFalse(holdouts & set(refs))

    def test_nombres_de_tablero_legibles(self):
        router = _Router(
            [{"semantic_model": "Tablero_Cvc"}, {"semantic_model": "TABLERO COSTOS ABC"},
             {"semantic_model": "NAOS"}, {"semantic_model": "GESTIÓN DE CAMAS"},
             {"semantic_model": "Gestión Camas"}, {"semantic_model": "UCI ADULTOS"}],
            [])
        datos, _ = catalogo_tableros(router)
        self.assertEqual(datos, ["Gestión Camas", "NAOS", "Tablero Costos ABC", "Tablero Cvc",
                                 "UCI Adultos"])

    def test_documentacion_sin_duplicados_ni_paginas(self):
        router = _RouterConPaginas(
            [{"semantic_model": "Lavanderia"}, {"semantic_model": "Referencia"}],
            [("TABLERO LAVANDERIA", "lav"), ("SEGUIMIENTO REMISION", "rem"),
             ("SEGUIMIENTO REMISIONES", "rem"), ("INICIO", "ref"), ("REPS", "ref"),
             ("Tablero_Tiempos_Egreso", "egr"), ("TABLERO DE TIEMPOS EGRESO", "egr")],
            {"Referencia": ["INICIO", "REPS"]})
        datos, docs = catalogo_tableros(router)
        self.assertEqual(datos, ["Lavanderia", "Referencia"])
        self.assertEqual(docs, ["Seguimiento Remision", "Tablero Tiempos Egreso"])


if __name__ == "__main__":
    unittest.main()

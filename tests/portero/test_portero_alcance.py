"""Portero de alcance (spec 002): mensajes fuera de alcance, sin LLM ni consultas.

  .venv/Scripts/python.exe -X utf8 -m unittest tests.portero.test_portero_alcance -v

Principio: un falso positivo (bloquear una pregunta real) es mucho peor que un
falso negativo. El barrido de TODOS los bancos reales debe dar 0 intercepciones.
"""
import json
import time
import unittest
from collections import Counter
from pathlib import Path

import numpy as np

from src.chatbot import portero_alcance
from src.chatbot.portero import (
    Clasificacion, EJEMPLOS, SimilitudPortero, clasificar, normalizar, responder,
)
from tests.portero.test_portero import BANCO, PROJECT_ROOT, VOCAB, _json

TIPO = "fuera_de_alcance"


def _casos(prefijo):
    return [c for c in json.loads(BANCO.read_text(encoding="utf-8"))["casos"]
            if c["id"].startswith(prefijo)]


_RUTAS_RECHAZO = {"out_of_scope", "not_found", "metric_not_resolved"}


def _es_rechazo_real(caso):
    return caso.get("tipo") == "fuera_alcance" or bool((caso.get("esperado") or {}).get("rechazo"))


def _es_rechazo_eval(turno):
    rutas = set((turno.get("expect") or {}).get("route") or [])
    return bool(rutas) and rutas <= _RUTAS_RECHAZO


def textos_fuera_de_alcance_etiquetados():
    """Mensajes que los bancos YA etiquetan como fuera de alcance (rechazo): son
    positivos ciegos, no falsos positivos."""
    textos = [c["pregunta"] for n in ("banco_real.json", "banco_holdout.json", "banco_holdout2.json")
              for c in _json(n)["casos"] if _es_rechazo_real(c)]
    for caso in _casos_eval():
        for turno in caso.get("turns") or []:
            if isinstance(turno.get("user"), str) and (
                    caso.get("category") == "g_fuera_alcance" or _es_rechazo_eval(turno)):
                textos.append(turno["user"])
    return textos


def textos_todos_los_bancos():
    """Preguntas reales de todos los bancos (desarrollo, holdouts, multi-turno,
    evaluador y diccionario), sin las que el propio banco espera rechazar."""
    textos = []
    for nombre in ("banco_real.json", "banco_holdout.json", "banco_holdout2.json"):
        for caso in _json(nombre)["casos"]:
            if _es_rechazo_real(caso):
                continue
            textos.append(caso["pregunta"])
            for extra in caso.get("turnos_extra") or []:
                textos.append(extra.removeprefix("texto: "))
    for conv in _json("banco_multiturno.json")["conversaciones"]:
        for turno in conv["turnos"]:
            if turno.get("entrada"):
                textos.append(turno["entrada"])
    for caso in _casos_eval():
        if caso.get("category") == "g_fuera_alcance":
            continue  # fuera de alcance esperado (ver test_casos_fuera_de_alcance_del_evaluador)
        for turno in caso.get("turns") or []:
            if isinstance(turno.get("user"), str) and not _es_rechazo_eval(turno):
                textos.append(turno["user"])
    dicc = PROJECT_ROOT / "tests" / "eval" / "diccionario_preguntas.json"
    for caso in json.loads(dicc.read_text(encoding="utf-8"))["casos"]:
        textos.append(caso["pregunta"])
    return [t for t in textos if isinstance(t, str) and t.strip()]


def _casos_eval():
    ruta = PROJECT_ROOT / "tests" / "eval" / "questions.json"
    return json.loads(ruta.read_text(encoding="utf-8"))["cases"]


def _como_motor(texto, similitud=None):
    """Igual que el motor: charla sobre el texto normalizado, alcance sobre el original."""
    from src.semantic.question_normalizer import normalize_question, vocabulary_for

    try:
        norm = normalize_question(texto, vocabulary_for(PROJECT_ROOT)).text or texto
    except Exception:
        norm = texto
    return clasificar(norm, VOCAB, similitud, original=texto)


class TestEjemplosDelUsuario(unittest.TestCase):
    def test_cinco_ejemplos(self):
        casos = {
            "necesito que me respondas algo": "vago",
            "quiero saber cuánto es la raíz cuadrada de x": "calculo",
            "qué pasó ayer en Tailandia": "noticias",
            "cómo hace las cirugías el hospital Santa Sofía": "otra_institucion",
            "hazme un reporte de": "vago",
        }
        for texto, sub in casos.items():
            with self.subTest(texto=texto):
                c = _como_motor(texto)
                self.assertIsNotNone(c)
                self.assertEqual((c.tipo, c.subtipo, c.motivo), (TIPO, sub, "regla"))
                self.assertTrue(c.detalle)
        self.assertIsNone(_como_motor("hazme un reporte de la ocupación de camas"))

    def test_clasificacion_detalle_por_defecto(self):
        self.assertEqual(Clasificacion("charla", "saludo", 1.0, "regla").detalle, "")

    def test_usa_el_original_y_no_el_normalizado(self):
        # El normalizador del motor convierte «arepas» en «áreas» (palabra del catálogo).
        self.assertEqual(clasificar("receta de áreas", VOCAB, original="receta de arepas").subtipo,
                         "recetas")
        self.assertIsNone(clasificar("receta de áreas", VOCAB))


class TestCategorias(unittest.TestCase):
    def test_cobertura_por_categoria_solo_reglas(self):
        casos = _casos("F")
        self.assertGreaterEqual(len(casos), 100)
        total, aciertos, fallos = Counter(), Counter(), []
        for c in casos:
            sub = c["esperado"].split("/", 1)[1]
            total[sub] += 1
            r = clasificar(c["texto"], VOCAB)
            if r is not None and f"{r.tipo}/{r.subtipo}" == c["esperado"]:
                aciertos[sub] += 1
            else:
                fallos.append((c["id"], c["texto"], r and f"{r.tipo}/{r.subtipo}"))
        global_ = sum(aciertos.values()) / sum(total.values())
        self.assertGreaterEqual(global_, 0.90, fallos)
        for sub in total:
            with self.subTest(categoria=sub):
                self.assertGreaterEqual(aciertos[sub] / total[sub], 0.80,
                                        [f for f in fallos if sub in str(f)])

    def test_variantes_mayusculas_tildes_y_jerga(self):
        for texto, sub in {
            "CUENTAME UN CHISTE": "entretenimiento", "cuéntame un chiste": "entretenimiento",
            "q le doy a mi hijo pa la fiebre": "clinico", "k paso en tailandia": "noticias",
            "nesecito q me respondas algo": "vago", "RECETA DE AREPAS": "recetas",
            "hola, ¿me cuentas un chiste?": "entretenimiento",
            "buenas tardes, ¿cuál es la capital de Francia?": "conocimiento",
        }.items():
            with self.subTest(texto=texto):
                c = clasificar(texto, VOCAB)
                self.assertIsNotNone(c)
                self.assertEqual(c.subtipo, sub)

    def test_anula_palabra_del_catalogo_fuera_del_marcador(self):
        for texto in ("cuentame un chiste sobre las cirugias y la ocupacion de camas",
                      "receta de antibioticos", "noticias de urgencias",
                      "escribe un correo con la ocupacion de camas",
                      "redacta un correo con el indicador de cirujias",  # tipeo
                      "cual es la capital del indicador", "hay chistes en el tablero?"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto, VOCAB))

    def test_anula_periodo_numero_y_propio_hospital(self):
        self.assertIsNone(clasificar("escribe un correo de enero", VOCAB))      # periodo
        self.assertIsNone(clasificar("escribe un correo de 2024", VOCAB))       # número
        self.assertIsNone(clasificar("noticias del hospital de caldas", VOCAB))  # propio
        self.assertIsNone(clasificar("chistes del SES", VOCAB))
        # Tolerancias: noticias/clima/deportes con periodo; cálculo con número.
        self.assertEqual(clasificar("noticias de ayer", VOCAB).subtipo, "noticias")
        self.assertEqual(clasificar("raiz cuadrada de 81", VOCAB).subtipo, "calculo")

    def test_seguimiento_nunca_se_bloquea(self):
        for texto in ("y en el santa sofia?", "y un chiste?", "tambien noticias de tailandia"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto, VOCAB))

    def test_vago_solo_mensaje_entero(self):
        for texto in ("hazme un reporte", "dame un resumen", "hazme un grafico", "necesito un reporte",
                      "tengo una pregunta sobre las cirugias", "necesito informacion de camas",
                      "hazme un informe de urgencias del mes pasado", "dime"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto, VOCAB))

    def test_clinico_vs_datos_de_farmacia(self):
        for texto in ("que le doy a mi hijo para la fiebre", "me duele la cabeza que me tomo",
                      "que antibiotico le doy a un paciente con neumonia"):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto, VOCAB).subtipo, "clinico")
        for texto in ("cual es el antibiotico que mas se esta usando?",
                      "cuantas dosis de amoxicilina se suministraron",
                      "cuantos pacientes con fiebre le doy de alta",
                      "pacientes con antibiotico por servicio", "total de dosis de antibioticos suministradas"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto, VOCAB))

    def test_otra_institucion_vs_remisiones_propias(self):
        self.assertEqual(clasificar("cuantas camas tiene el santa sofia", VOCAB).subtipo,
                         "otra_institucion")
        for texto in ("cuantos pacientes remitimos al santa sofia", "remisiones a la clinica avidanti",
                      "pacientes del hospital santa sofia", "compara el hospital de caldas con el santa sofia",
                      "traslados hacia la clinica san marcel", "pacientes de otros hospitales"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto, VOCAB))

    def test_sin_sentido(self):
        for texto in ("asdfgh", "jajaja", "???", "", "   ", "😂😂", "hjkl ñlkj", "qwerty"):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto, VOCAB).subtipo, "sin_sentido")
        for texto in ("pq", "x", "q", "bn", "la 2", "sí", "cvc", "uci", "ok", "mmm"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto, VOCAB))

    def test_numeros_y_fechas_sueltos_nunca_se_bloquean(self):
        # Años, fechas, rangos y opciones son seguimientos o respuestas a botones.
        for texto in ("2024", "2024 2025", "10/2025", "05/10/2025", "2024-2025", "1", "3",
                      "12345 6789", "y 2024?", "1/2"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto, VOCAB))
        self.assertEqual(clasificar("2+2", VOCAB).subtipo, "calculo")
        self.assertEqual(clasificar("cuanto es 10/2", VOCAB).subtipo, "calculo")

    def test_aseguradoras_no_son_otra_institucion(self):
        for texto in ("MEDICINA PREPAGADA COLSANITAS", "atenciones de colsanitas",
                      "cuantas atenciones de la eps de la clinica san marcel"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar(texto, VOCAB))

    def test_positivos_etiquetados_en_los_bancos(self):
        """Rechazos que los bancos ya esperan (holdouts H47-H49, G48-G50 y casos
        del evaluador). Medición: antes de generalizar dos reglas («mejor X
        para Y» clínico y «buscarv» de ofimática) se detectaban 4 de 6 holdouts."""
        textos = textos_fuera_de_alcance_etiquetados()
        detectados = [t for t in textos if (_como_motor(t) or Clasificacion("", "", 0, "")).tipo == TIPO]
        # No se esperan: el saludo (charla) y salario/PIB (los resuelve el motor tras el catálogo).
        self.assertGreaterEqual(len(detectados), len(textos) - 3, set(textos) - set(detectados))

    def test_tipeo_de_una_letra_cuenta_como_dominio(self):
        for t in ("cirujias", "ocupasion", "cirugas", "urgenciass", "arepas"):  # arepas ~ areas
            self.assertTrue(portero_alcance.es_dominio(t, VOCAB), t)
        for t in ("chiste", "tailandia", "hacer", "receta", "correo", "las", "una"):
            self.assertFalse(portero_alcance.es_dominio(t, VOCAB), t)

    def test_casos_fuera_de_alcance_del_evaluador(self):
        """Casos g_fuera_alcance de tests/eval/questions.json (salvo saludo y los
        que el motor ya resuelve como fuera de alcance tras el catálogo)."""
        esperados = {
            "g_capital_francia": "conocimiento", "g_receta": "recetas", "g_clima": "clima",
            "g_consejo_clinico": "clinico", "g_futbol": "deportes", "g_codigo": "programacion",
        }
        casos = {c["id"]: c["turns"][0]["user"] for c in _casos_eval()}
        for cid, sub in esperados.items():
            with self.subTest(caso=cid):
                c = _como_motor(casos[cid])
                self.assertIsNotNone(c)
                self.assertEqual(c.subtipo, sub)

    def test_texto_enorme_sale_rapido(self):
        for texto in ("a" * 1_000_000, "chiste " * 50_000):
            t0 = time.perf_counter()
            self.assertIsNone(clasificar(texto, VOCAB))
            self.assertLess(time.perf_counter() - t0, 0.2)

    def test_latencia_reglas_menor_5_ms(self):
        """SC-004: lo que AÑADE el alcance (la charla de la primera entrega va aparte)."""
        textos = [c["texto"] for c in _casos("F")] + [c["texto"] for c in _casos("N")]
        portero_alcance.detectar(textos[0], VOCAB)
        t0 = time.perf_counter()
        for t in textos:
            portero_alcance.detectar(t, VOCAB)
        media_ms = (time.perf_counter() - t0) / len(textos) * 1000
        self.assertLess(media_ms, 5, f"{media_ms:.2f} ms")


class TestSinFalsosPositivos(unittest.TestCase):
    def test_casos_de_dominio_del_banco(self):
        malos = [(c["id"], c["texto"]) for c in _casos("N") + _casos("D")
                 if clasificar(c["texto"], VOCAB) is not None]
        self.assertEqual(malos, [])

    def test_barrido_todos_los_bancos_sin_intercepciones(self):
        textos = textos_todos_los_bancos()
        self.assertGreater(len(textos), 400)
        malos = [t for t in textos if clasificar(t, VOCAB) is not None]
        self.assertEqual(malos, [])
        malos = [t for t in textos if _como_motor(t) is not None]
        self.assertEqual(malos, [])


class _ModeloFalso:
    """Ejemplos de charla en el eje 0, de alcance en el eje 2, dominio cerca del
    alcance (0, 0.6, 0.8); las consultas, por mapa."""

    def __init__(self, consultas):
        self.consultas = {normalizar(k): v for k, v in consultas.items()}
        self.charla = {normalizar(t) for lista in EJEMPLOS.values() for t in lista}
        self.alcance = {normalizar(t) for lista in portero_alcance.EJEMPLOS.values() for t in lista}

    def encode(self, textos, **kwargs):
        filas = []
        for t in textos:
            n = normalizar(t)
            if n in self.consultas:
                v = self.consultas[n]
            elif n in self.alcance:
                v = (0.0, 0.0, 1.0)
            elif n in self.charla:
                v = (1.0, 0.0, 0.0)
            else:
                v = (0.0, 0.6, 0.8)
            v = np.array(v, dtype=float)
            filas.append(v / np.linalg.norm(v))
        return np.array(filas)


class _ModeloQueFalla:
    def encode(self, textos, **kwargs):
        raise RuntimeError("sin modelo")


class TestSimilitudAlcanceFalsa(unittest.TestCase):
    def setUp(self):
        self.sim = SimilitudPortero(_ModeloFalso({
            "mensaje raro con margen": (0, -0.6, 0.8),   # alcance 0.80, dominio 0.28
            "mensaje raro sin margen": (0, 0.36, 0.93),  # alcance 0.93, dominio 0.96
            "mensaje raro bajo": (0, 1, 0),
            "mensaje raro de cirugias": (0, 0, 1),
            "mensaje raro en enero": (0, 0, 1),
            "dos palabras": (0, 0, 1),
        }))

    def test_actua_solo_sobre_umbral_y_margen(self):
        c = clasificar("mensaje raro con margen", VOCAB, self.sim)
        self.assertIsNotNone(c)
        self.assertEqual((c.tipo, c.motivo), (TIPO, "similitud"))
        self.assertIn(c.subtipo, portero_alcance.SUBTIPOS)
        self.assertIn("similitud", c.detalle)
        self.assertIsNone(clasificar("mensaje raro sin margen", VOCAB, self.sim))
        self.assertIsNone(clasificar("mensaje raro bajo", VOCAB, self.sim))

    def test_no_salta_anulaciones_ni_aplica_a_dos_palabras(self):
        self.assertIsNone(clasificar("mensaje raro de cirugias", VOCAB, self.sim))
        self.assertIsNone(clasificar("mensaje raro en enero", VOCAB, self.sim))
        self.assertIsNone(clasificar("dos palabras", VOCAB, self.sim))

    def test_modelo_que_falla_deja_solo_reglas(self):
        s = SimilitudPortero(_ModeloQueFalla())
        self.assertIsNone(s.mejor_alcance("mensaje raro con margen"))
        self.assertEqual(clasificar("cuentame un chiste", VOCAB, s).subtipo, "entretenimiento")
        self.assertIsNone(clasificar("mensaje raro con margen", VOCAB, s))


class TestRespuestas(unittest.TestCase):
    def _r(self, sub, datos=(), docs=()):
        return responder(Clasificacion(TIPO, sub, 1.0, "regla", "x"), list(datos), list(docs))

    def test_todas_dicen_que_si_puede_hacer(self):
        for sub in portero_alcance.SUBTIPOS - {"vago"}:
            with self.subTest(sub=sub):
                texto = self._r(sub)
                self.assertIn("¿qué puedes hacer?", texto)
                self.assertLess(len(texto), 450)

    def test_vaga_incluye_capacidades_del_catalogo(self):
        texto = self._r("vago", ["Cirugias", "Camas"], ["Triage"])
        self.assertTrue(texto.startswith("Claro"))
        self.assertIn("**Datos**", texto)
        self.assertIn("Cirugias, Camas", texto)

    def test_textos_por_grupo(self):
        self.assertIn("No doy recomendaciones clínicas", self._r("clinico"))
        self.assertIn("otras instituciones", self._r("otra_institucion"))
        self.assertIn("No redacto", self._r("redaccion"))
        self.assertIn("No redacto", self._r("programacion"))
        self.assertIn("No entendí", self._r("sin_sentido"))
        self.assertIn("fuera de lo que puedo responder", self._r("calculo"))


if __name__ == "__main__":
    unittest.main()

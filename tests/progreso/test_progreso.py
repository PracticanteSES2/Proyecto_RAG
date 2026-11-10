"""Pruebas del progreso del turno (src/chatbot/progreso.py): lógica pura, sin interfaz."""
import json
import random
import re
import unittest

from src.chatbot import progreso
from src.chatbot.progreso import (
    ETAPAS,
    FRASES,
    UMBRALES_ESPERA,
    SelectorFrases,
    TraductorProgreso,
    aviso_degradacion,
    etapa_de_evento,
    evento_cola,
    frase_espera,
    leer_carga_llm,
    nivel_espera,
)
from src.chatbot.reasoning_trace import ReasoningTrace

# Títulos de actividad que emite hoy el motor (query_engine, powerbi_provider)
# y los ganchos reservados («LLM en cola», «Redactando»).
ACTIVIDADES = {
    "Interpretando la pregunta": "entendiendo",
    "Interpretando la pregunta con MedGemma (intención estructurada)": "entendiendo",
    "Interpretando el mensaje con el contexto de la conversación (MedGemma)": "entendiendo",
    "Buscando el indicador, los filtros y el periodo (Query Plan)": "buscando_indicador",
    "Armando la consulta con el indicador elegido": "buscando_indicador",
    "MedGemma está describiendo 4 opciones": "preparando_opciones",
    "Consultando Power BI (CIRUGIAS)": "consultando_powerbi",
    "Consultando Power BI (modelo por defecto)": "consultando_powerbi",
    "Trayendo la lista de valores de Power BI": "consultando_powerbi",
    "Trayendo la lista de detalle de Power BI": "consultando_powerbi",
    "Abriendo conexión con Power BI (modelo X). Si en el servidor aparece una ventana de inicio de sesión, complétala.": "conectando_powerbi",
    "Reabriendo conexión con Power BI (modelo X). Si en el servidor aparece una ventana de inicio de sesión, complétala.": "conectando_powerbi",
    "Buscando en la documentación y redactando la respuesta con MedGemma": "revisando_documentacion",
    "LLM en cola": "en_cola",
    "Redactando la respuesta": "redactando",
}

TECNICOS = ("medgemma", "dax", "query plan", "modelo sem", "llm", "ollama", "rag", "pasos")


def _textos_visibles():
    textos = [frase for variantes in FRASES.values() for frase in variantes]
    for etapa in ETAPAS:
        for ocupado in (False, True):
            for nivel in range(1, len(UMBRALES_ESPERA) + 1):
                textos.append(frase_espera(nivel, etapa, {"ocupado": ocupado}))
    textos += [progreso.AVISO_SATURADO, progreso.AVISO_SIN_REDACCION]
    return textos


class TestEtapas(unittest.TestCase):
    def test_todas_las_actividades_del_motor_tienen_etapa(self):
        for titulo, esperada in ACTIVIDADES.items():
            with self.subTest(titulo=titulo):
                self.assertEqual(etapa_de_evento({"kind": "activity", "title": titulo}), esperada)

    def test_pasos_y_eventos_raros_no_cambian_la_etapa(self):
        self.assertIsNone(etapa_de_evento({"kind": "step", "title": "Mensaje conversacional"}))
        self.assertIsNone(etapa_de_evento({"kind": "step", "title": "Interpretando la pregunta"}))
        self.assertIsNone(etapa_de_evento({}))
        self.assertIsNone(etapa_de_evento(None))
        self.assertIsNone(etapa_de_evento({"kind": "activity", "title": "algo que no existe"}))

    def test_catalogo_de_etapas(self):
        for etapa in ("entendiendo", "buscando_indicador", "consultando_powerbi",
                      "revisando_documentacion", "en_cola", "redactando", "finalizando"):
            self.assertIn(etapa, ETAPAS)

    def test_cada_etapa_tiene_al_menos_tres_variantes(self):
        for etapa in ETAPAS:
            with self.subTest(etapa=etapa):
                self.assertGreaterEqual(len(set(FRASES[etapa])), 3)

    def test_textos_visibles_sin_digitos_ni_tecnicismos(self):
        for texto in _textos_visibles():
            with self.subTest(texto=texto):
                self.assertIsNone(re.search(r"\d", texto))
                palabras = set(re.findall(r"\w+", texto.lower()))
                for termino in TECNICOS:
                    if " " in termino:
                        self.assertNotIn(termino, texto.lower())
                    else:
                        self.assertNotIn(termino, palabras)


class TestSelectorFrases(unittest.TestCase):
    def test_no_repite_la_ultima_frase_entre_turnos(self):
        recientes = []
        anterior = None
        for semilla in range(10):
            frase = SelectorFrases(recientes, rng=random.Random(semilla)).elegir("consultando_powerbi")
            self.assertIn(frase, FRASES["consultando_powerbi"])
            self.assertNotEqual(frase, anterior)
            anterior = frase

    def test_dentro_del_turno_una_etapa_repetida_cambia_de_frase(self):
        selector = SelectorFrases([], rng=random.Random(1))
        self.assertNotEqual(selector.elegir("consultando_powerbi"), selector.elegir("consultando_powerbi"))

    def test_si_se_agotan_las_variantes_sigue_respondiendo(self):
        selector = SelectorFrases(list(FRASES["buscando_indicador"]), rng=random.Random(2))
        for _ in range(len(FRASES["buscando_indicador"]) + 2):
            self.assertIn(selector.elegir("buscando_indicador"), FRASES["buscando_indicador"])

    def test_memoria_acotada(self):
        recientes = []
        selector = SelectorFrases(recientes, rng=random.Random(3))
        for _ in range(40):
            for etapa in ETAPAS:
                selector.elegir(etapa)
        self.assertLessEqual(len(recientes), progreso.MAX_RECIENTES)

    def test_etapa_desconocida_usa_entendiendo(self):
        self.assertIn(SelectorFrases([], rng=random.Random(4)).elegir("no-existe"), FRASES["entendiendo"])


class TestEsperas(unittest.TestCase):
    def test_umbrales_crecientes(self):
        segundos = [s for s, _ in UMBRALES_ESPERA]
        self.assertEqual(segundos, sorted(set(segundos)))

    def test_nivel_por_tiempo(self):
        primero, segundo = UMBRALES_ESPERA[0][0], UMBRALES_ESPERA[1][0]
        self.assertEqual(nivel_espera(0), 0)
        self.assertEqual(nivel_espera(primero - 0.1), 0)
        self.assertEqual(nivel_espera(primero), 1)
        self.assertEqual(nivel_espera(segundo + 1), 2)
        self.assertEqual(nivel_espera(10_000), len(UMBRALES_ESPERA))

    def test_nivel_dos_segun_etapa_y_carga(self):
        self.assertIn("Power BI", frase_espera(2, "consultando_powerbi"))
        self.assertEqual(frase_espera(2, "conectando_powerbi"), frase_espera(2, "consultando_powerbi"))
        self.assertIn("fila", frase_espera(2, "revisando_documentacion", {"ocupado": True}))
        self.assertNotIn("fila", frase_espera(2, "revisando_documentacion", {"ocupado": False}))
        self.assertNotIn("fila", frase_espera(2, "buscando_indicador", {"ocupado": True}))  # sin LLM
        self.assertIn("otra consulta", frase_espera(2, "en_cola"))

    def test_nivel_tres_pide_no_reenviar(self):
        self.assertIn("volver a enviar", frase_espera(3, "buscando_indicador"))


class _StatsFalso:
    def __init__(self, llm=None, presion=None, lanza=False):
        if llm is not None:
            self.llm = llm
        if presion is not None:
            self.llm_pressure = lambda: presion
        self._lanza = lanza

    def __getattr__(self, nombre):
        if nombre == "llm" and self.__dict__.get("_lanza"):
            raise RuntimeError("boom")
        raise AttributeError(nombre)


class TestCargaLLM(unittest.TestCase):
    def test_lee_contadores_actuales(self):
        carga = leer_carga_llm(_StatsFalso(llm={"in_flight": 1, "waiting": 0}), capacidad=3)
        self.assertEqual(carga, {"en_curso": 1, "en_cola": 0, "capacidad": 3, "ocupado": False})

    def test_cola_o_huecos_llenos_es_ocupado(self):
        self.assertTrue(leer_carga_llm(_StatsFalso(llm={"in_flight": 1, "waiting": 2}), capacidad=3)["ocupado"])
        self.assertTrue(leer_carga_llm(_StatsFalso(llm={"in_flight": 3, "waiting": 0}), capacidad=3)["ocupado"])

    def test_prefiere_llm_pressure_si_existe(self):
        stats = _StatsFalso(
            llm={"in_flight": 0, "waiting": 0},
            presion={"in_flight": 2, "waiting": 0, "capacity": 4, "saturated_recent": 1},
        )
        carga = leer_carga_llm(stats)
        self.assertEqual((carga["en_curso"], carga["capacidad"]), (2, 4))
        self.assertTrue(carga["ocupado"])  # rechazos recientes por saturación

    def test_fallo_al_leer_es_sin_carga(self):
        self.assertFalse(leer_carga_llm(_StatsFalso(lanza=True), capacidad=3)["ocupado"])

    def test_por_defecto_lee_stats_del_proceso(self):
        self.assertIn("ocupado", leer_carga_llm())


class TestAvisoDegradacion(unittest.TestCase):
    def _rag(self, *lineas):
        return {
            "status": "success", "route": "rag", "synthesis_mode": "extractive",
            "reasoning": {"steps": [{"title": "Búsqueda en la documentación (RAG)", "lines": list(lineas)}]},
        }

    def test_extractiva_por_saturacion(self):
        aviso = aviso_degradacion(self._rag("MedGemma estaba saturado (sin hueco libre): se usa el resumen extractivo"))
        self.assertEqual(aviso["motivo"], "saturado")
        self.assertIn("muchas consultas a la vez", aviso["texto"])

    def test_extractiva_por_otro_motivo(self):
        aviso = aviso_degradacion(self._rag("MedGemma no respondió en 60 s (se cortó la llamada)"))
        self.assertEqual(aviso["motivo"], "sin_redaccion")
        self.assertIn("no pude redactar", aviso["texto"])

    def test_respuesta_normal_sin_aviso(self):
        self.assertIsNone(aviso_degradacion({"status": "success", "route": "rag", "synthesis_mode": "llm"}))
        self.assertIsNone(aviso_degradacion({"status": "success", "route": "powerbi"}))
        self.assertIsNone(aviso_degradacion({"status": "success", "route": "conversacion"}))
        self.assertIsNone(aviso_degradacion(None))

    def test_no_encontrado_sin_aviso(self):
        resultado = self._rag("saturado")
        resultado["status"] = "not_found"
        self.assertIsNone(aviso_degradacion(resultado))


class _Reloj:
    def __init__(self):
        self.ahora = 1000.0

    def __call__(self):
        return self.ahora


def _traductor(carga=None):
    reloj = _Reloj()
    traductor = TraductorProgreso(
        recientes=[], reloj=reloj, rng=random.Random(0),
        carga=(lambda: carga) if carga is not None else (lambda: {"ocupado": False}),
    )
    return traductor, reloj


class TestTraductor(unittest.TestCase):
    def test_iniciar_emite_entendiendo(self):
        traductor, _ = _traductor()
        eventos = traductor.iniciar()
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["evento"], "progreso")
        datos = eventos[0]["datos"]
        self.assertEqual(set(datos), {"etapa", "frase", "t"})
        self.assertEqual(datos["etapa"], "entendiendo")
        self.assertIn(datos["frase"], FRASES["entendiendo"])
        self.assertEqual(datos["t"], 0.0)

    def test_solo_emite_al_cambiar_de_etapa(self):
        traductor, reloj = _traductor()
        traductor.iniciar()
        self.assertEqual(traductor.traducir({"kind": "activity", "title": "Interpretando la pregunta"}), [])
        self.assertEqual(traductor.traducir({"kind": "step", "title": "Pregunta normalizada"}), [])
        reloj.ahora += 4.04
        eventos = traductor.traducir({"kind": "activity", "title": "Consultando Power BI (CIRUGIAS)",
                                      "lines": ["EVALUATE ROW(...)"]})
        self.assertEqual([e["datos"]["etapa"] for e in eventos], ["consultando_powerbi"])
        self.assertEqual(eventos[0]["datos"]["t"], 4.0)
        self.assertNotIn("CIRUGIAS", json.dumps(eventos))
        self.assertNotIn("EVALUATE", json.dumps(eventos))
        # Otra consulta en la misma etapa: sin ruido.
        self.assertEqual(traductor.traducir({"kind": "activity", "title": "Consultando Power BI (OTRO)"}), [])

    def test_volver_a_una_etapa_cambia_la_frase(self):
        traductor, _ = _traductor()
        primera = traductor.traducir({"kind": "activity", "title": "Consultando Power BI (A)"})[0]["datos"]["frase"]
        traductor.traducir({"kind": "activity", "title": "Armando la consulta con el indicador elegido"})
        segunda = traductor.traducir({"kind": "activity", "title": "Consultando Power BI (B)"})[0]["datos"]["frase"]
        self.assertNotEqual(primera, segunda)

    def test_esperando_turno_y_cola(self):
        traductor, _ = _traductor()
        traductor.iniciar()
        eventos = traductor.esperando_turno(posicion=2, en_curso=1)
        self.assertEqual([e["evento"] for e in eventos], ["progreso", "cola"])
        self.assertEqual(eventos[0]["datos"]["etapa"], "en_cola")
        self.assertEqual(eventos[1]["datos"], {"posicion": 2, "en_curso": 1})
        # Siguiente aviso de espera: solo la cola (la etapa ya se dijo).
        self.assertEqual([e["evento"] for e in traductor.esperando_turno(1, 1)], ["cola"])

    def test_evento_cola_sin_negativos(self):
        self.assertEqual(evento_cola(-1, None)["datos"], {"posicion": 0, "en_curso": 0})

    def test_tic_emite_esperas_al_cruzar_umbrales(self):
        traductor, reloj = _traductor()
        traductor.iniciar()
        self.assertEqual(traductor.tic(), [])
        reloj.ahora += UMBRALES_ESPERA[0][0]
        eventos = traductor.tic()
        self.assertEqual([(e["evento"], e["datos"]["nivel"]) for e in eventos], [("espera", 1)])
        self.assertEqual(set(eventos[0]["datos"]), {"nivel", "frase", "t"})
        self.assertEqual(traductor.tic(), [])  # mismo nivel: nada nuevo

    def test_tic_atrasado_emite_solo_el_nivel_mas_alto(self):
        traductor, reloj = _traductor()
        traductor.iniciar()
        reloj.ahora += UMBRALES_ESPERA[2][0] + 1
        eventos = traductor.tic()
        self.assertEqual([e["datos"]["nivel"] for e in eventos], [3])

    def test_tic_nivel_dos_con_carga_ocupada_habla_de_fila(self):
        traductor, reloj = _traductor(carga={"ocupado": True})
        traductor.traducir({"kind": "activity", "title": "Buscando en la documentación y redactando la respuesta con MedGemma"})
        reloj.ahora += UMBRALES_ESPERA[1][0]
        self.assertIn("fila", traductor.tic()[0]["datos"]["frase"])

    def test_finalizar_y_aviso(self):
        traductor, _ = _traductor()
        traductor.iniciar()
        self.assertEqual(traductor.finalizar()[0]["datos"]["etapa"], "finalizando")
        self.assertEqual(traductor.aviso({"status": "success", "route": "powerbi"}), [])
        aviso = traductor.aviso({"status": "success", "route": "rag", "synthesis_mode": "extractive"})
        self.assertEqual(aviso[0]["evento"], "aviso")
        self.assertEqual(aviso[0]["datos"]["motivo"], "sin_redaccion")

    def test_todos_los_eventos_son_json(self):
        traductor, reloj = _traductor()
        eventos = traductor.iniciar() + traductor.esperando_turno(1, 1)
        for titulo in ACTIVIDADES:
            eventos += traductor.traducir({"kind": "activity", "title": titulo})
        reloj.ahora += 100
        eventos += traductor.tic() + traductor.finalizar()
        eventos += traductor.aviso({"status": "success", "route": "rag", "synthesis_mode": "extractive"})
        self.assertEqual(json.loads(json.dumps(eventos, ensure_ascii=False)), eventos)
        for sobre in eventos:
            self.assertIn(sobre["evento"], ("progreso", "espera", "cola", "aviso"))

    def test_evento_malformado_no_lanza(self):
        traductor, _ = _traductor()
        self.assertEqual(traductor.traducir("no es un dict"), [])
        self.assertEqual(traductor.traducir({"kind": "activity", "title": None}), [])

    def test_carga_que_lanza_no_tumba(self):
        def rota():
            raise RuntimeError("boom")

        reloj = _Reloj()
        traductor = TraductorProgreso(reloj=reloj, rng=random.Random(0), carga=rota)
        traductor.traducir({"kind": "activity", "title": "Interpretando la pregunta"})
        reloj.ahora += UMBRALES_ESPERA[1][0]
        self.assertEqual(traductor.tic()[0]["datos"]["nivel"], 2)

    def test_con_la_traza_real_del_motor(self):
        # El listener del motor (ReasoningTrace) alimenta al traductor.
        traductor, _ = _traductor()
        salida = traductor.iniciar()
        traza = ReasoningTrace("question", "hola", listener=lambda e: salida.extend(traductor.traducir(e)))
        traza.activity("Interpretando la pregunta")
        traza.add("Pregunta normalizada", "original: «x»")
        traza.activity("Buscando el indicador, los filtros y el periodo (Query Plan)")
        traza.activity("Consultando Power BI (CIRUGIAS)", "EVALUATE ...")
        self.assertEqual([e["datos"]["etapa"] for e in salida],
                         ["entendiendo", "buscando_indicador", "consultando_powerbi"])


if __name__ == "__main__":
    unittest.main()

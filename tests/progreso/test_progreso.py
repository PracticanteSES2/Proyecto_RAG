"""Pruebas del progreso del turno (src/chatbot/progreso.py): lógica pura, sin interfaz."""
import json
import random
import re
import unittest

from src.chatbot import progreso
from src.chatbot.progreso import (
    ETAPAS,
    FRASES,
    ROTACION_S,
    SEGUIMIENTO,
    UMBRALES_ESPERA,
    SelectorFrases,
    TraductorProgreso,
    aviso_degradacion,
    etapa_de_evento,
    evento_cola,
    evento_token,
    frase_espera,
    leer_carga_llm,
    nivel_espera,
)
from src.chatbot.reasoning_trace import ReasoningTrace

# Títulos de actividad que emite hoy el motor (query_engine, powerbi_provider)
# y el gancho reservado «Redactando».
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
    "Redactando la respuesta": "redactando",
}

TECNICOS = ("medgemma", "dax", "query plan", "modelo sem", "llm", "ollama", "rag", "pasos")

# Decisión del usuario: la espera nunca habla de otros, de filas ni de carga.
VOCABULARIO_DE_COLA = re.compile(
    r"\b(colas?|filas?|turnos?|posici[oó]n|ocupad\w*|saturad\w*|servidor\w*|en curso|"
    r"otras? consultas?|muchas consultas|varias consultas|usuarios?|personas?|antes que la tuya)\b",
    re.IGNORECASE,
)


def _textos_visibles():
    textos = [frase for variantes in FRASES.values() for frase in variantes]
    textos += [frase for variantes in SEGUIMIENTO.values() for frase in variantes]
    for etapa in ETAPAS:
        for nivel in range(1, len(UMBRALES_ESPERA) + 1):
            textos.append(frase_espera(nivel, etapa))
    textos += [progreso.AVISO_EXTRACTIVO]
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

    def test_esperar_hueco_del_llm_no_cambia_la_etapa(self):
        # «LLM en cola…» (llm_gate.add_queue_observer) es diagnóstico: el usuario
        # sigue viendo la etapa de trabajo sobre SU pregunta.
        for titulo in ("LLM en cola", "LLM en cola: posición 2, 3 en curso", "LLM en cola: entró tras 4.0 s"):
            self.assertIsNone(etapa_de_evento({"kind": "activity", "title": titulo}))

    def test_catalogo_de_etapas(self):
        for etapa in ("entendiendo", "buscando_indicador", "consultando_powerbi",
                      "revisando_documentacion", "redactando", "finalizando"):
            self.assertIn(etapa, ETAPAS)
        self.assertNotIn("en_cola", ETAPAS)

    def test_cada_etapa_tiene_al_menos_tres_variantes_y_seguimiento(self):
        for etapa in ETAPAS:
            with self.subTest(etapa=etapa):
                self.assertGreaterEqual(len(set(FRASES[etapa])), 3)
                self.assertGreaterEqual(len(set(SEGUIMIENTO[etapa])), 2)
                self.assertFalse(set(SEGUIMIENTO[etapa]) & set(FRASES[etapa]))

    def test_textos_visibles_nunca_hablan_de_colas_ni_de_otros(self):
        for texto in _textos_visibles():
            with self.subTest(texto=texto):
                self.assertIsNone(VOCABULARIO_DE_COLA.search(texto))

    def test_la_espera_del_llm_suena_a_trabajo_sobre_la_pregunta(self):
        seguimiento = " ".join(SEGUIMIENTO["revisando_documentacion"])
        for frase in ("Revisando los datos que encontré", "Organizando la respuesta", "Redactando la respuesta"):
            self.assertIn(frase, seguimiento)

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

    def test_nivel_dos_segun_etapa(self):
        self.assertIn("Power BI", frase_espera(2, "consultando_powerbi"))
        self.assertEqual(frase_espera(2, "conectando_powerbi"), frase_espera(2, "consultando_powerbi"))
        self.assertIn("ya casi la tengo", frase_espera(2, "revisando_documentacion"))
        self.assertNotIn("Power BI", frase_espera(2, "revisando_documentacion"))

    def test_esperas_tranquilizan_hablando_de_la_pregunta(self):
        self.assertEqual(frase_espera(1, "revisando_documentacion"), "Sigo trabajando en tu pregunta…")
        self.assertIn("volver a enviarla", frase_espera(3, "buscando_indicador"))
        self.assertIn("sigo en ello", frase_espera(4, "entendiendo"))


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

    def test_extractiva_por_saturacion_nota_neutra(self):
        aviso = aviso_degradacion(self._rag("MedGemma estaba saturado (sin hueco libre): se usa el resumen extractivo"))
        self.assertEqual(aviso["motivo"], "saturado")  # solo para el modo diagnóstico
        self.assertEqual(aviso["texto"], "Te muestro lo que dice la documentación.")

    def test_extractiva_por_otro_motivo_misma_nota(self):
        aviso = aviso_degradacion(self._rag("MedGemma no respondió en 60 s (se cortó la llamada)"))
        self.assertEqual(aviso["motivo"], "sin_redaccion")
        self.assertEqual(aviso["texto"], progreso.AVISO_EXTRACTIVO)

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


def _traductor():
    reloj = _Reloj()
    traductor = TraductorProgreso(recientes=[], reloj=reloj, rng=random.Random(0))
    return traductor, reloj


def _esperas(eventos):
    return [e for e in eventos if e["evento"] == "espera"]


def _progresos(eventos):
    return [e for e in eventos if e["evento"] == "progreso"]


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

    def test_esperando_turno_no_cambia_la_etapa_y_solo_emite_cola(self):
        traductor, _ = _traductor()
        traductor.iniciar()
        eventos = traductor.esperando_turno(posicion=2, en_curso=1)
        # La etapa visible sigue siendo de trabajo; `cola` es solo para diagnóstico.
        self.assertEqual([e["evento"] for e in eventos], ["cola"])
        self.assertEqual(eventos[0]["datos"], {"posicion": 2, "en_curso": 1})
        self.assertEqual(traductor.etapa, "entendiendo")
        self.assertEqual([e["evento"] for e in traductor.esperando_turno(1, 1)], ["cola"])

    def test_esperando_turno_antes_de_iniciar_muestra_entendiendo(self):
        traductor, _ = _traductor()
        eventos = traductor.esperando_turno(1, 1)
        self.assertEqual([e["evento"] for e in eventos], ["progreso", "cola"])
        self.assertEqual(eventos[0]["datos"]["etapa"], "entendiendo")

    def test_evento_cola_sin_negativos(self):
        self.assertEqual(evento_cola(-1, None)["datos"], {"posicion": 0, "en_curso": 0})

    def test_tic_emite_esperas_al_cruzar_umbrales(self):
        traductor, reloj = _traductor()
        traductor.iniciar()
        self.assertEqual(traductor.tic(), [])
        reloj.ahora += UMBRALES_ESPERA[0][0]
        eventos = _esperas(traductor.tic())
        self.assertEqual([(e["evento"], e["datos"]["nivel"]) for e in eventos], [("espera", 1)])
        self.assertEqual(set(eventos[0]["datos"]), {"nivel", "frase", "t"})
        self.assertEqual(_esperas(traductor.tic()), [])  # mismo nivel: nada nuevo

    def test_tic_atrasado_emite_solo_el_nivel_mas_alto(self):
        traductor, reloj = _traductor()
        traductor.iniciar()
        reloj.ahora += UMBRALES_ESPERA[2][0] + 1
        eventos = _esperas(traductor.tic())
        self.assertEqual([e["datos"]["nivel"] for e in eventos], [3])

    def test_rotacion_lenta_de_frases_en_la_misma_etapa(self):
        traductor, reloj = _traductor()
        traductor.traducir({"kind": "activity", "title": "Buscando en la documentación y redactando la respuesta con MedGemma"})
        reloj.ahora += ROTACION_S - 0.5
        self.assertEqual(_progresos(traductor.tic()), [])  # todavía no
        frases = []
        for _ in range(len(SEGUIMIENTO["revisando_documentacion"]) + 2):
            reloj.ahora += ROTACION_S
            rotacion = _progresos(traductor.tic())
            self.assertEqual(len(rotacion), 1)
            self.assertEqual(set(rotacion[0]["datos"]), {"etapa", "frase", "t"})
            self.assertEqual(rotacion[0]["datos"]["etapa"], "revisando_documentacion")
            frases.append(rotacion[0]["datos"]["frase"])
        # En orden de avance, sin repetir la frase anterior, y cíclica.
        largo = len(SEGUIMIENTO["revisando_documentacion"])
        self.assertEqual(frases[:largo], list(SEGUIMIENTO["revisando_documentacion"]))
        self.assertTrue(all(a != b for a, b in zip(frases, frases[1:], strict=False)))

    def test_cambio_de_etapa_reinicia_la_rotacion(self):
        traductor, reloj = _traductor()
        traductor.iniciar()
        reloj.ahora += ROTACION_S - 1
        traductor.traducir({"kind": "activity", "title": "Consultando Power BI (A)"})
        reloj.ahora += 2
        self.assertEqual(_progresos(traductor.tic()), [])

    def test_espera_del_llm_mantiene_la_etapa_y_rota(self):
        traductor, reloj = _traductor()
        traductor.traducir({"kind": "activity", "title": "Buscando en la documentación y redactando la respuesta con MedGemma"})
        self.assertEqual(traductor.traducir({"kind": "activity", "title": "LLM en cola: posición 3, 3 en curso"}), [])
        reloj.ahora += UMBRALES_ESPERA[1][0]
        eventos = traductor.tic()
        texto = json.dumps(eventos, ensure_ascii=False)
        self.assertIsNone(VOCABULARIO_DE_COLA.search(texto))
        self.assertEqual(_esperas(eventos)[0]["datos"]["nivel"], 2)

    def test_token_emite_evento_y_silencia_las_esperas(self):
        traductor, reloj = _traductor()
        traductor.iniciar()
        self.assertEqual(traductor.token(""), [])
        eventos = traductor.token("El indicador")
        self.assertEqual(eventos, [{"evento": "token", "datos": {"texto": "El indicador"}}])
        self.assertEqual(evento_token(" mide")["datos"], {"texto": " mide"})
        reloj.ahora += 100
        self.assertEqual(traductor.tic(), [])  # la respuesta visible ya es el avance

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
        eventos += traductor.tic() + traductor.finalizar() + traductor.token("Hola")
        eventos += traductor.aviso({"status": "success", "route": "rag", "synthesis_mode": "extractive"})
        self.assertEqual(json.loads(json.dumps(eventos, ensure_ascii=False)), eventos)
        for sobre in eventos:
            self.assertIn(sobre["evento"], ("progreso", "espera", "cola", "aviso", "token"))

    def test_evento_malformado_no_lanza(self):
        traductor, _ = _traductor()
        self.assertEqual(traductor.traducir("no es un dict"), [])
        self.assertEqual(traductor.traducir({"kind": "activity", "title": None}), [])

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

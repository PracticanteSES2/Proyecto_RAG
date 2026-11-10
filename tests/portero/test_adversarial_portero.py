"""Pruebas adversariales del portero. Cada prueba expresa el comportamiento
acordado tras la revisión (informe: .superpowers/sdd/2026-11-09-portero-conversacional/
adversarial.md); un fallo es un hallazgo.

  .venv/Scripts/python.exe -X utf8 -m unittest tests.portero.test_adversarial_portero -v

El MiniLM real se usa solo si está en la caché local (sin red); si no, esas
pruebas se omiten.
"""
import os
import sys
import time
import unittest

sys.dont_write_bytecode = True

from src.chatbot.portero import (
    SimilitudPortero, Clasificacion, catalogo_tableros, clasificar, responder,
)
from tests.sim import harness
from pathlib import Path
from src.chatbot.portero import vocabulario_dominio

VOCAB = vocabulario_dominio(Path(__file__).resolve().parents[2])


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _cargar_modelo():
    # Si otra prueba del mismo proceso ya instaló el falso del arnés, se aparta
    # un momento para cargar el MiniLM real y luego se restituye.
    falso = sys.modules.get("sentence_transformers")
    if falso is not None and getattr(falso, "__file__", None) is None:
        del sys.modules["sentence_transformers"]
        try:
            return _cargar_modelo_real()
        finally:
            sys.modules["sentence_transformers"] = falso
    return _cargar_modelo_real()


def _cargar_modelo_real():
    # sin importar src.rag.retriever (arrastraria qdrant_client real antes de los stubs)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer
    try:
        return SentenceTransformer(MODEL_NAME, local_files_only=True)
    except TypeError:
        # Sin local_files_only: modo sin red forzado para que no pueda descargar.
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

NO_CHARLA = [
    "¿cómo vamos?", "¿cómo va urgencias?", "qué tal las cirugías", "buenas tardes, necesito el censo",
    "gracias, ahora por servicio", "hola de nuevo", "ayúdame con ocupación", "¿qué hay?", "¿qué más hay?",
    "listo, y el anterior", "perfecto, ¿y en marzo?", "ok y por especialidad", "chao el filtro",
    "quítale el filtro", "otra vez", "todo", "todos", "nada", "ninguno", "el primero", "sí, ese",
    "no, el otro", "2", "UCI", "IPS", "EPS", "urgencias", "cirugía", "y por servicio", "y por médico",
    "más detalle", "dame más", "continúa", "cómo se calcula", "el último", "el mismo", "cancelar",
    "nueva consulta", "no entiendo", "por qué", "no era eso", "qué pena", "regular", "más o menos",
    "vale", "claro", "ya", "ajá", "ah ok", "ok perfecto", "gracias, y el de ayer", "gracias y en urgencias",
    "buenos días, cuántas camas hay", "hola, quiero ver ocupación", "hola tengo una pregunta",
    "una consulta", "necesito ayuda con un dato", "ayuda con el informe", "muéstrame los tableros",
    "cómo está el hospital", "cómo están los turnos", "cómo va el día", "cómo amaneció urgencias",
    "cómo nos fue ayer", "qué tal vamos", "todo bien con las camas", "qué hay en urgencias",
    "qué hay pendiente", "qué más tienes", "qué más puedes mostrar", "qué más datos hay", "qué más pasó",
    "otro", "siguiente", "el siguiente", "opción 1", "la uno", "uno", "dos", "sí por favor", "no gracias",
    "no, gracias", "sí, gracias", "ninguno gracias", "todas gracias", "el primero gracias", "nada gracias",
    "nada más", "eso es todo", "es todo", "por ahora nada", "ya no más", "basta", "con eso basta",
    "qué sabes de camas", "qué puedes decirme de urgencias", "para qué sirve la ocupación",
    "quién atiende urgencias", "quién es el responsable", "de dónde sacas los datos",
    "cuéntame más", "dime más", "qué otras hay", "y las demás", "y el resto", "ver más", "mostrar todo",
    "qué debo escribir", "cómo hago", "cómo se filtra", "cómo pregunto por camas", "qué tal por especialidad",
    "qué tal ayer", "buen trabajo", "muy bien", "está bien", "todo claro", "listo, siguiente",
    "bueno gracias entonces", "entonces", "pues sí", "oye", "dime", "cuéntame", "dime cuál",
    "me ayudas con un dato", "gracias pero no era eso", "gracias, pero quería otro dato",
    "buenas, quisiera saber algo", "bien gracias y tú", "hasta luego el filtro", "adiós al filtro",
    "qué tableros hay de camas", "qué tableros tienes de cirugía", "cómo funciona la ocupación",
    "quién lo calcula", "en qué quedamos", "qué pasa con urgencias", "a ver qué hay",
    "q mas", "k mas", "gracias, ¿qué más?",
]
NO_CHARLA_CRITICOS = ["¿qué más?", "qué más", "que mas"]

# Meta-conversación que la similitud real sí intercepta (M3 del informe): se
# aceptan tal como están (si cambian, solo pueden pasar a None o a la misma clase).
ACEPTADOS_POR_SIMILITUD = [
    ("me puedes ayudar", "capacidades/capacidades"), ("quién lo creó", "identidad/identidad"),
    ("con quién me comunico", "identidad/identidad"), ("a quién le pregunto", "capacidades/capacidades"),
    ("a quién llamo", "identidad/identidad"), ("por ahora es todo", "charla/agradecimiento"),
]

# Charla que DEBE reconocerse (frases de regla y uniones de dos frases, F4).
CHARLA = [
    ("buenos días a todos", "charla/saludo"), ("hola buenas tardes", "charla/saludo"),
    ("quiubo parce", "charla/saludo"), ("q hubo", "charla/saludo"), ("qué hubo", "charla/saludo"),
    ("hey hola", "charla/saludo"), ("buenas buenas", "charla/saludo"), ("hola a todos", "charla/saludo"),
    ("buenas tardes a todos", "charla/saludo"), ("hola, ¿qué más?", "charla/saludo"),
    ("hola cómo estás", "charla/estado"), ("hola como estas", "charla/estado"),
    ("gracias parce", "charla/agradecimiento"), ("gracias, muy amable", "charla/agradecimiento"),
    ("gracias, hasta luego", "charla/despedida"), ("chao, gracias", "charla/despedida"),
    ("gracias, chao", "charla/despedida"), ("hasta mañana", "charla/despedida"),
    ("cuál es tu nombre", "identidad/identidad"), ("necesito ayuda", "capacidades/capacidades"),
    ("qué opciones hay", "capacidades/capacidades"),
]

# Charla que hoy NO se reconoce (va al flujo normal, el lado seguro): el margen
# de la similitud se mantiene en 0.20 por decisión (A-I2). Nunca debe salir con
# otra clase distinta de la esperada.
CHARLA_NO_CUBIERTA = [
    ("buenos días a todos", "charla/saludo"), ("hola buenas tardes", "charla/saludo"),
    ("quiubo parce", "charla/saludo"), ("q hubo", "charla/saludo"), ("qué hubo", "charla/saludo"),
    ("epa", "charla/saludo"), ("hey hola", "charla/saludo"), ("buenas buenas", "charla/saludo"),
    ("buenas noches a todos", "charla/saludo"), ("muy buenas", "charla/saludo"),
    ("cordial saludo", "charla/saludo"), ("un saludo", "charla/saludo"),
    ("hola cómo estás", "charla/estado"), ("hola como estas", "charla/estado"),
    ("cómo amaneció", "charla/estado"), ("cómo está usted", "charla/estado"),
    ("cómo has estado", "charla/estado"), ("qué más cuenta", "charla/saludo"),
    ("gracias parce", "charla/agradecimiento"), ("mil gracias parce", "charla/agradecimiento"),
    ("gracias, muy amable", "charla/agradecimiento"), ("vale gracias", "charla/agradecimiento"),
    ("genial gracias", "charla/agradecimiento"), ("excelente, gracias", "charla/agradecimiento"),
    ("listo, muchas gracias", "charla/agradecimiento"), ("se agradece", "charla/agradecimiento"),
    ("gracias, hasta luego", "charla/despedida"), ("chao, gracias", "charla/despedida"),
    ("gracias, chao", "charla/despedida"), ("hasta mañana", "charla/despedida"),
    ("que le vaya bien", "charla/despedida"), ("buen fin de semana", "charla/despedida"),
    ("ya me voy", "charla/despedida"), ("bye", "charla/despedida"),
    ("cuál es tu nombre", "identidad/identidad"), ("eres una IA", "identidad/identidad"),
    ("eres persona", "identidad/identidad"), ("qué haces", "capacidades/capacidades"),
    ("ayúdame", "capacidades/capacidades"), ("necesito ayuda", "capacidades/capacidades"),
    ("qué opciones hay", "capacidades/capacidades"), ("cuáles tableros hay", "capacidades/capacidades"),
    ("con qué tableros cuentas", "capacidades/capacidades"), ("cómo funcionas", "capacidades/capacidades"),
    ("cómo te uso", "capacidades/capacidades"), ("menú", "capacidades/capacidades"),
]
CHARLA_NO_CUBIERTA = [c for c in CHARLA_NO_CUBIERTA if c not in CHARLA]


_SIM = None
_SIM_ERR = None


def _no_disponible(mensaje):
    """Sin MiniLM local: se omite, salvo PORTERO_REQUIRE_MINILM=1 (entonces falla)."""
    if os.environ.get("PORTERO_REQUIRE_MINILM") == "1":
        raise AssertionError(mensaje)
    raise unittest.SkipTest(mensaje)


def _sim():
    """MiniLM real, cargado una sola vez y de forma perezosa (en setUpClass, antes
    de que harness.build_engine sustituya sentence_transformers por un falso)."""
    global _SIM, _SIM_ERR
    if _SIM is None and _SIM_ERR is None:
        try:
            sim = SimilitudPortero(_cargar_modelo())
            if sim.activa:
                _SIM = sim
            else:
                _SIM_ERR = "similitud inactiva"
        except Exception as exc:  # sin cache local
            _SIM_ERR = f"MiniLM no disponible offline: {exc}"
    if _SIM is None:
        _no_disponible(_SIM_ERR)
    return _SIM


def _precargar():
    """Carga el MiniLM real (si existe) antes de que harness.build_engine lo
    sustituya por un falso; los fallos se reportan en las clases que lo necesitan."""
    try:
        _sim()
    except (unittest.SkipTest, AssertionError):
        pass


class FalsosPositivos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim = _sim()

    def _fallos(self, lista):
        out = []
        for s in lista:
            r = clasificar(s, VOCAB, similitud=self.sim)
            # Spec 002: una petición vaga de mensaje ENTERO («hola, tengo una
            # pregunta») se responde pidiendo el dato; nunca es una pregunta de datos.
            if r is not None and (r.tipo, r.subtipo) != ("fuera_de_alcance", "vago"):
                out.append(f"{s!r} -> {r.tipo}/{r.subtipo} conf={r.confianza:.3f} ({r.motivo})")
        return out

    def test_no_intercepta_mensajes_de_dominio_o_seguimiento(self):
        self.assertEqual(self._fallos(NO_CHARLA), [])

    def test_que_mas_y_cierres_ambiguos_no_se_interceptan(self):
        self.assertEqual(self._fallos(NO_CHARLA_CRITICOS), [])

    def test_meta_conversacion_aceptada(self):
        malos = []
        for texto, aceptado in ACEPTADOS_POR_SIMILITUD:
            r = clasificar(texto, VOCAB, similitud=self.sim)
            got = f"{r.tipo}/{r.subtipo}" if r else None
            if got not in (None, aceptado):
                malos.append(f"{texto!r}: {got}")
        self.assertEqual(malos, [])


class FalsosNegativos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim = _sim()

    def test_reconoce_charla_colombiana(self):
        malos = []
        for texto, esperado in CHARLA:
            r = clasificar(texto, VOCAB, similitud=self.sim)
            got = f"{r.tipo}/{r.subtipo}" if r else None
            if got != esperado:
                malos.append(f"{texto!r}: esperado {esperado}, obtenido {got}")
        self.assertEqual(malos, [], f"{len(malos)}/{len(CHARLA)} sin reconocer")

    def test_charla_no_cubierta_nunca_con_otra_clase(self):
        malos = []
        for texto, esperado in CHARLA_NO_CUBIERTA:
            r = clasificar(texto, VOCAB, similitud=self.sim)
            got = f"{r.tipo}/{r.subtipo}" if r else None
            if got not in (None, esperado):
                malos.append(f"{texto!r}: esperado {esperado} o None, obtenido {got}")
        self.assertEqual(malos, [])

    def test_charla_reconocida_sin_similitud(self):
        """Las frases de regla no dependen del MiniLM."""
        malos = [t for t, e in CHARLA
                 if (lambda r: f"{r.tipo}/{r.subtipo}" if r else None)(clasificar(t, VOCAB)) != e]
        self.assertEqual(malos, [])


class Motor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _precargar()
        cls.engine, cls.cm, cls.fm, *_ = harness.build_engine()

    def setUp(self):
        harness.new_conversation(self.engine, self.cm)

    def ask(self, t):
        return harness.ask(self.engine, self.cm, self.fm, t)

    def test_gracias_no_rompe_seguimiento(self):
        self.ask("cirugias programadas de urologia en 2024")
        self.ask("gracias")
        c, ui = self.ask("¿y en octubre?")
        self.assertEqual(c["route"], "powerbi", ui)
        self.assertIn("octubre", ui.lower())

    def test_dos_gracias_seguidos_y_seguimiento(self):
        self.ask("cirugias programadas de urologia en 2024")
        for _ in range(2):
            r, _ = self.ask("gracias")
            self.assertEqual(r["route"], "conversacion")
        c, ui = self.ask("¿y en octubre?")
        self.assertEqual(c["route"], "powerbi", ui)

    def test_que_mas_tras_respuesta_no_es_saludo(self):
        self.ask("cirugias programadas de urologia en 2024")
        r, ui = self.ask("¿qué más?")
        self.assertNotEqual(r["route"], "conversacion", ui)

    def test_hola_primero_y_luego_pregunta(self):
        r, _ = self.ask("hola")
        self.assertEqual(r["route"], "conversacion")
        r, ui = self.ask("cirugias programadas de urologia en 2024")
        self.assertEqual(r["route"], "powerbi", ui)
        r, ui = self.ask("y en octubre")
        self.assertEqual(r["route"], "powerbi", ui)

    def test_contrapregunta_abierta_no_se_intercepta(self):
        for x in ("hola", "gracias", "qué puedes hacer", "chao", "qué más", "cómo estás"):
            harness.new_conversation(self.engine, self.cm)
            a, _ = self.ask("cuantas cirugias hubo en 2024")
            self.assertEqual(a["status"], "needs_clarification")
            r, ui = self.ask(x)
            self.assertNotEqual(r["route"], "conversacion", (x, ui))

    def test_mensaje_aplazado_con_gracias_previo(self):
        self.ask("gracias")
        a, _ = self.ask("cuantas cirugias hubo en 2024")
        self.assertEqual(a["status"], "needs_clarification")
        self.ask("¿y en el mes pasado?")
        self.assertEqual(self.engine._deferred_context_message, "¿y en el mes pasado?")
        ops = a.get("clarification_options") or []
        self.assertTrue(ops)
        op = ops[0]
        oid = op.get("id") if isinstance(op, dict) else op
        res = self.engine.select_clarification_option(oid, "x")
        self.assertEqual(res.get("route"), "powerbi", res.get("answer"))

    def test_nueva_conversacion_reinicia_portero(self):
        self.ask("hola")
        harness.new_conversation(self.engine, self.cm)
        r, _ = self.ask("hola")
        self.assertEqual(r["route"], "conversacion")

    def test_mayusculas_signos_emojis(self):
        for t in ("HOLA!!!", "¡¡Gracias!!", "  hola  ", "GRACIAS.", "Hola?", "hola...", "hola 👋", "gracias 🙏"):
            r, ui = self.ask(t)
            self.assertEqual(r["route"], "conversacion", (t, ui))

    def test_texto_raro_no_lanza(self):
        for t in ("", "   ", "¿?", "👋", "a" * 5000, "hola\n\ngracias", "\x00hola"):
            r, ui = self.ask(t)
            self.assertIsNone(r["_sim"]["exception"], (t[:20], r["_sim"]["traceback"]))


class Capacidades(unittest.TestCase):
    def test_texto_con_fixtures_del_simulador(self):
        _precargar()
        eng, cm, fm, *_ = harness.build_engine()
        r, ui = harness.ask(eng, cm, fm, "qué puedes hacer")
        self.assertEqual(r["route"], "conversacion")
        items = []
        for linea in ui.split("\n\n"):
            if linea.startswith("**"):
                items += [x.strip() for x in linea.split(":", 1)[1].split(",")]
        self.assertEqual(len(items), len(set(i.lower() for i in items)), "tableros duplicados")
        self.assertFalse([i for i in items if "_" in i or i.upper().startswith("DICCIONARIO")])

    def test_catalogo_real_sin_guiones_bajos_duplicados_ni_siglas_deformadas(self):
        from src.chatbot.portero import _clave_tablero
        from src.semantic.source_model_router import SourceModelRouter
        R = Path(__file__).resolve().parents[2]
        if not (R / "data/catalog/source_registry.json").exists():
            raise unittest.SkipTest("sin data/catalog real")
        router = SourceModelRouter(
            source_registry_path=R / "data/catalog/source_registry.json",
            visual_catalog_path=R / "data/rag/visual_metrics_catalog.json",
            project_root=R, default_semantic_model="x")
        router.register_documentation_dashboards([])
        datos, docs = catalogo_tableros(router)
        texto = responder(Clasificacion("capacidades", "capacidades", 1.0, "t"), datos, docs)
        nombres = datos + docs
        self.assertFalse([d for d in nombres if "_" in d])
        claves = [_clave_tablero(n) for n in nombres]
        self.assertEqual(len(claves), len(set(claves)), "tableros duplicados")
        self.assertFalse([d for d in nombres if d.upper().startswith("DICCIONARIO")])
        for deformada in ("Cvc", "Abc", "Naos", "Eps"):
            self.assertNotIn(f" {deformada}", texto)


class Rendimiento(unittest.TestCase):
    def test_primer_mensaje_vs_siguientes(self):
        _precargar()
        eng, cm, fm, *_ = harness.build_engine()
        tiempos = []
        for t in ("hola", "gracias", "chao", "hola", "cuantas camas hay"):
            t0 = time.perf_counter()
            harness.ask(eng, cm, fm, t)
            tiempos.append(time.perf_counter() - t0)
        self.assertLess(tiempos[0], 1.0,
                        f"primer mensaje (construccion perezosa) >1s; turnos={[round(x, 3) for x in tiempos]}")


if __name__ == "__main__":
    unittest.main()

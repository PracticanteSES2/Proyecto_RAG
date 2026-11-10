"""Portero conversacional: detecta charla pura (saludo, gracias, despedida,
estado), preguntas de identidad y de capacidades, antes del flujo de datos.

Módulo puro, sin estado del motor. Ante cualquier duda devuelve ``None`` y el
mensaje sigue el flujo normal. Regla de oro: el mensaje normalizado, sin
muletillas, debe ser ENTERO una frase conversacional conocida (no contenerla).

Similitud MiniLM (tras reglas, lista de bloqueo y guardas; solo 3 a 8 palabras):
UMBRAL = 0.80 y MARGEN = 0.20 (research D2, confirmados por barrido umbral
0.70-0.85 x margen 0.10-0.30 sobre banco_portero + banco_real).
Cifras vigentes (banco con 113 casos C y 74 D, MiniLM real): reglas solas
101/113, con similitud 105/113; falsos positivos 0/74 (tambien en leave-one-out);
barrido ciego de 243 textos (banco_real + holdout + holdout2 + multiturno): 0.
Las preguntas de banco_real tambien son referencias de dominio, asi que la
evidencia ciega honesta son holdout, holdout2 y multi-turno, mas leave-one-out.
Las referencias de dominio viven en portero_referencias.json (produccion no lee
tests/).

Segunda entrega (specs/002-portero-alcance): si no es charla, ``clasificar``
prueba ``portero_alcance`` (mensajes fuera de alcance: vaga, cálculo, noticias,
clínico, otra institución, sin sentido…) sobre el mensaje ORIGINAL.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_PALABRAS = 8
MIN_PALABRAS_SIMILITUD = 3
UMBRAL = 0.80
MARGEN = 0.20

_TIPO_POR_SUBTIPO = {
    "saludo": "charla",
    "agradecimiento": "charla",
    "despedida": "charla",
    "estado": "charla",
    "identidad": "identidad",
    "capacidades": "capacidades",
}

# Frases conversacionales (normalizadas). Fuente: research.md D6.
_FRASES = {
    "saludo": [
        "hola", "holi", "ola", "hola hola", "buenas", "buenos dias", "buen dia",
        "buenas tardes", "buenas noches", "q mas", "que mas", "quiubo",
        "quiubole", "k mas pues", "k mas", "hey", "saludos", "hola que tal",
        "hola q tal", "q tal", "que tal", "hola buenas",
    ],
    "estado": [
        "como estas", "como esta", "como estas hoy", "como te va", "como vas",
        "todo bien", "todo bien por alla", "bien y tu", "como amaneciste",
        "que mas como vas", "como le va",
    ],
    "agradecimiento": [
        "gracias", "grax", "grcias", "graciass", "mil gracias",
        "muchas gracias", "muchisimas gracias", "gracias por la ayuda",
        "ok gracias", "perfecto gracias", "listo gracias", "super gracias",
        "te agradezco", "muy amable", "dios le pague",
    ],
    "despedida": [
        "chao", "chau", "adios", "hasta luego", "hasta pronto", "nos vemos",
        "bendiciones", "que este bien", "feliz dia", "feliz tarde",
        "buena noche", "me despido",
    ],
    "identidad": [
        "quien eres", "que eres", "con quien hablo", "eres un robot",
        "eres humano", "como te llamas",
    ],
    "capacidades": [
        "que puedes hacer", "que sabes hacer", "en que me ayudas",
        "para que sirves", "que tableros hay", "ayuda",
    ],
}

_MULETILLAS = frozenset({"oye", "bueno", "porfa", "pues"})
_MULETILLAS_FRASE = ("por favor",)

# Palabras que nunca cuentan como dominio aunque el catálogo las contenga.
# Se calcula con las frases de D6 (antes de _FRASES_EXTRA): las palabras nuevas
# («todos», «manana», «nombre», «opciones»...) siguen siendo dominio para la
# similitud; las frases completas no las necesitan (ver clasificar).
_PALABRAS_CONVERSACIONALES = frozenset(
    {w for lista in _FRASES.values() for f in lista for w in f.split()}
    | _MULETILLAS
    | {"hoy", "bien", "ayuda", "gracias", "hola", "buenas"}
)

# Frases añadidas tras la revisión adversarial (charla colombiana frecuente).
_FRASES_EXTRA = {
    "saludo": ["buenos dias a todos", "hola a todos", "buenas tardes a todos",
               "quiubo parce", "q hubo", "que hubo"],
    "agradecimiento": ["gracias parce"],
    "despedida": ["hasta manana"],
    "identidad": ["cual es tu nombre"],
    "capacidades": ["necesito ayuda", "que opciones hay"],
}
for _sub, _lista in _FRASES_EXTRA.items():
    _FRASES[_sub] = _FRASES[_sub] + _lista

# «¿qué más?» a solas, tras una respuesta, pide más datos: solo es saludo
# combinado con otra frase de saludo o estado («hola, ¿qué más?»).
_SOLO_COMBINADAS = frozenset({"que mas", "q mas", "k mas"})
_COMPANERAS_SOLO_COMBINADAS = frozenset({"saludo", "estado"})

# Prioridad del subtipo cuando el mensaje une dos frases («hola, ¿cómo estás?»).
_PRIORIDAD = ("identidad", "capacidades", "estado", "despedida", "agradecimiento", "saludo")

MAX_CARACTERES = 200

_PERIODOS = frozenset({
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "setiembre", "octubre", "noviembre", "diciembre",
    "semana", "semanas", "mes", "meses", "trimestre", "trimestres",
    "semestre", "ano", "anos", "ayer", "anterior", "anteriores", "anoche",
    "antier", "anteayer",
})

_SOLOS_FLUJO_NORMAL = frozenset({
    "listo", "ok", "si", "no", "ninguna", "dale", "perfecto", "resumen",
    "novedades", "como vamos", "como estamos", "como va", "que hay de nuevo",
}) | _SOLO_COMBINADAS


@dataclass(frozen=True)
class Clasificacion:
    tipo: str
    subtipo: str
    confianza: float
    motivo: str
    detalle: str = ""  # por qué (marcador o similitud); solo en fuera de alcance


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin signos, espacios colapsados."""
    base = unicodedata.normalize("NFKD", str(texto or "").lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = re.sub(r"[^a-z0-9]+", " ", base)
    return " ".join(base.split())


def _sin_muletillas(norm: str) -> list[str]:
    norm = f" {norm} "
    for frase in _MULETILLAS_FRASE:
        norm = norm.replace(f" {frase} ", " ")
    return [t for t in norm.split() if t not in _MULETILLAS]


def bloqueado_por_guardas(texto: str, vocabulario_dominio: frozenset[str]) -> str | None:
    """Motivo del bloqueo (numero, periodo, dominio, largo) o None."""
    norm = normalizar(texto)
    tokens = norm.split()
    if any(c.isdigit() for c in norm):
        return "numero"
    if any(t in _PERIODOS for t in tokens):
        return "periodo"
    if any(t in vocabulario_dominio for t in tokens):
        return "dominio"
    if len(tokens) > MAX_PALABRAS:
        return "largo"
    return None


_PREFIJOS_BLOQUEO = (
    "como vamos", "como estamos", "como va", "ayuda con", "ayuda para",
    "que hay de nuevo",
)


def _colapsar(palabra: str) -> str:
    """Reduce letras repetidas (holaa, graciass) a una sola."""
    return re.sub(r"(.)\1+", r"\1", palabra)


def _una_letra(a: str, b: str) -> bool:
    """True si a y b difieren por omitir o insertar exactamente una letra."""
    if abs(len(a) - len(b)) != 1:
        return False
    corta, larga = (a, b) if len(a) < len(b) else (b, a)
    return any(larga[:i] + larga[i + 1:] == corta for i in range(len(larga)))


def _ediciones(token: str, base: str) -> int | None:
    """Ediciones para que token case con base (None si no casa).

    Sin coste: letras repetidas. Coste 1: omitir o insertar una letra, solo
    si la palabra base tiene 6 o más letras. Nunca sustituciones.
    """
    if token == base or _colapsar(token) == _colapsar(base):
        return 0
    if (len(base) >= 6 and len(token) >= 5
            and _una_letra(_colapsar(token), _colapsar(base))):
        return 1
    return None


def _casa(tokens: list[str], frase: list[str]) -> bool:
    """tokens casa con frase (misma longitud) con a lo sumo una edición."""
    if len(tokens) != len(frase):
        return False
    total = 0
    for a, b in zip(tokens, frase):
        e = _ediciones(a, b)
        if e is None:
            return False
        total += e
    return total <= 1


def _en_lista_bloqueo(tokens: list[str]) -> bool:
    if any(_casa(tokens, solo.split()) for solo in _SOLOS_FLUJO_NORMAL):
        return True
    for prefijo in _PREFIJOS_BLOQUEO:
        p = prefijo.split()
        if len(tokens) > len(p) and _casa(tokens[:len(p)], p):
            return True
    # «como esta X» con más palabras: pregunta por X (no es saludo de estado).
    return len(tokens) > 2 and tokens[:2] == ["como", "esta"]


_TABLA = [(f.split(), sub) for sub, lista in _FRASES.items() for f in lista]


def _ediciones_frase(tokens: list[str], frase: list[str]) -> int | None:
    """Ediciones totales para que tokens case con frase (misma longitud)."""
    if len(tokens) != len(frase):
        return None
    total = 0
    for a, b in zip(tokens, frase):
        e = _ediciones(a, b)
        if e is None:
            return None
        total += e
    return total


def _frase_regla(tokens: list[str]) -> tuple[str, str, int] | None:
    """(frase, subtipo, ediciones) de la frase de regla que mejor casa, o None."""
    mejor = None
    for frase, sub in _TABLA:
        e = _ediciones_frase(tokens, frase)
        if e is not None and e <= 1 and (mejor is None or e < mejor[2]):
            mejor = (" ".join(frase), sub, e)
            if e == 0:
                break
    return mejor


def _por_reglas(tokens: list[str]) -> tuple[str, int] | None:
    """(subtipo, ediciones) si el mensaje es ENTERO una frase de regla o la unión
    de dos («hola buenas tardes», «gracias, chao»), con a lo sumo una edición."""
    sola = _frase_regla(tokens)
    if sola is not None and sola[0] not in _SOLO_COMBINADAS:
        return sola[1], sola[2]
    mejor = None
    for i in range(1, len(tokens)):
        a, b = _frase_regla(tokens[:i]), _frase_regla(tokens[i:])
        if a is None or b is None or a[2] + b[2] > 1:
            continue
        if (a[0] in _SOLO_COMBINADAS and b[1] not in _COMPANERAS_SOLO_COMBINADAS) or (
                b[0] in _SOLO_COMBINADAS and a[1] not in _COMPANERAS_SOLO_COMBINADAS):
            continue
        sub = min((a[1], b[1]), key=_PRIORIDAD.index)
        candidato = (sub, a[2] + b[2])
        if mejor is None or candidato[1] < mejor[1]:
            mejor = candidato
    return mejor


def clasificar(texto: str, vocabulario_dominio: frozenset[str] = frozenset(),
               similitud: "SimilitudPortero | None" = None,
               original: str | None = None) -> Clasificacion | None:
    """Charla/identidad/capacidades (primera entrega) o, si no lo es, fuera de
    alcance (segunda entrega, ``portero_alcance``); None = flujo normal.

    ``texto`` es el mensaje normalizado por el motor; ``original`` el que
    escribió el usuario (el alcance lo usa: la normalización puede inventar
    palabras del catálogo, «arepas» → «áreas»). Sin ``original``, ``texto``.
    """
    c = _clasificar_charla(texto, vocabulario_dominio, similitud)
    if c is not None:
        return c
    return _clasificar_alcance(texto, vocabulario_dominio, similitud, original)


def _clasificar_alcance(texto, vocabulario_dominio, similitud, original):
    """Fuera de alcance (spec 002) o None. Nunca con un mensaje que sea ENTERO
    de la lista de bloqueo («resumen», «ok», «ninguna»…): son seguimientos del
    dominio o respuestas a una contrapregunta. Los prefijos de bloqueo («cómo va
    X») no aplican aquí: cada categoría exige su marcador y sus anulaciones."""
    tokens = _sin_muletillas(normalizar(texto)) if len(texto or "") <= MAX_CARACTERES else []
    if tokens and any(_casa(tokens, solo.split()) for solo in _SOLOS_FLUJO_NORMAL):
        return None
    from src.chatbot import portero_alcance

    d = portero_alcance.detectar(original if original is not None else texto,
                                 vocabulario_dominio, similitud)
    if d is None:
        return None
    return Clasificacion(portero_alcance.TIPO, d.subtipo, 1.0 if d.motivo == "regla" else 0.9,
                         d.motivo, d.detalle)


def _clasificar_charla(texto: str, vocabulario_dominio: frozenset[str] = frozenset(),
                       similitud: "SimilitudPortero | None" = None) -> Clasificacion | None:
    """Clasifica charla/identidad/capacidades o devuelve None.

    Orden: tope de longitud, guarda de número, lista de bloqueo, reglas (frase
    completa o unión de dos), guardas de periodo/dominio/largo y similitud. Una
    frase de regla completa SIN ediciones no pasa por las guardas de periodo,
    dominio ni largo («hasta mañana», «buenos días a todos»); con una edición sí.
    """
    tokens = _tokens_charla(texto)
    if tokens is None:
        return None
    regla = _por_reglas(tokens)
    if regla is not None:
        return _clasificacion_regla(regla, texto, vocabulario_dominio)
    if bloqueado_por_guardas(texto, vocabulario_dominio):
        return None
    return _por_similitud(" ".join(tokens), similitud)


def _tokens_charla(texto: str) -> list[str] | None:
    """Palabras sin muletillas, o None si el mensaje no puede ser charla: muy
    largo (acota el coste), con números, vacío o de la lista de bloqueo."""
    if len(texto or "") > MAX_CARACTERES:
        return None
    norm = normalizar(texto)
    if any(c.isdigit() for c in norm):
        return None
    tokens = _sin_muletillas(norm)
    return tokens if tokens and not _en_lista_bloqueo(tokens) else None


def _clasificacion_regla(regla, texto, vocabulario_dominio) -> Clasificacion | None:
    """Frase de regla sin ediciones: sin guardas; con una edición: con guardas."""
    sub, ediciones = regla
    if ediciones and bloqueado_por_guardas(texto, vocabulario_dominio):
        return None
    return Clasificacion(_TIPO_POR_SUBTIPO[sub], sub, 1.0 if ediciones == 0 else 0.9, "regla")


def _por_similitud(frase: str, similitud) -> Clasificacion | None:
    """Última barrera: solo mensajes de 3 a 8 palabras, tras reglas y guardas."""
    if similitud is None or not (MIN_PALABRAS_SIMILITUD <= len(frase.split()) <= MAX_PALABRAS):
        return None
    try:
        mejor = similitud.mejor(frase)
    except Exception as exc:
        logging.getLogger(__name__).warning("similitud portero fallo: %s", exc)
        return None
    if mejor is None:
        return None
    clave, sim, sim_dominio = mejor
    if sim < similitud.umbral or sim - sim_dominio < similitud.margen:
        return None
    tipo, subtipo = clave.split("/", 1)
    return Clasificacion(tipo, subtipo, float(sim), "similitud")


def vocabulario_dominio(project_root, docs_root=None) -> frozenset[str]:
    """Palabras del catálogo (targets) sin palabras conversacionales.
    ``docs_root`` fija la documentación (las pruebas la usan con una raíz sin
    ``data/`` para tener el mismo vocabulario en cualquier checkout)."""
    try:
        from src.semantic.question_normalizer import vocabulary_for

        palabras = {normalizar(k) for k in vocabulary_for(Path(project_root), docs_root).targets}
        palabras = {p for p in palabras if p and " " not in p}
        return frozenset(palabras - _PALABRAS_CONVERSACIONALES)
    except Exception as exc:
        logging.getLogger(__name__).warning("vocabulario_dominio fallo: %s", exc)
        return frozenset()


# Ejemplos conversacionales (normalizados) para la similitud. Fuente: research D2/D6.
EJEMPLOS = {
    "saludo": [
        "hola", "hola buenas", "hola que tal", "hola como andas", "hola a todos",
        "buenos dias", "buenas tardes", "buenas noches", "buen dia para todos",
        "que mas", "que mas pues", "quiubo parce", "hey que tal", "saludos cordiales",
        "un saludo", "hola buen dia", "hola buenas tardes", "muy buenos dias",
        "buenas tardes a todos", "hola mucho gusto", "buenas como estan",
        "hola es un gusto saludarte", "holi que mas", "ola buenas", "que onda", "que onda parce",
    ],
    "estado": [
        "como estas", "como estas hoy", "como te va", "como vas", "como andas",
        "como amaneciste", "como te encuentras", "todo bien por alla",
        "todo bien contigo", "que mas como vas", "como le va", "bien y tu",
        "como has estado", "como te ha ido", "como va tu dia", "espero que estes bien",
        "como te sientes hoy", "todo tranquilo por alla", "como esta usted",
        "y tu como estas", "como te fue hoy", "que tal tu dia",
    ],
    "agradecimiento": [
        "gracias", "muchas gracias", "mil gracias", "muchisimas gracias",
        "gracias por la ayuda", "gracias por tu ayuda", "ok gracias", "listo gracias",
        "perfecto gracias", "super gracias", "te agradezco", "te agradezco mucho",
        "muy amable", "muy amable gracias", "dios le pague", "gracias por todo",
        "gracias por la informacion", "excelente gracias", "gracias de verdad",
        "mil gracias por todo", "gracias por responderme", "quedo muy agradecido",
        "gracias eres muy amable", "muchas gracias por tu tiempo", "eso es todo gracias", "eso es todo por ahora",
    ],
    "despedida": [
        "chao", "chao nos vemos", "adios", "adios y gracias", "hasta luego",
        "hasta pronto", "hasta manana", "nos vemos", "nos vemos luego",
        "bendiciones", "que este bien", "que te vaya bien", "feliz dia",
        "feliz tarde", "buena noche", "me despido", "que tengas buen dia",
        "que tengas buena tarde", "hasta la proxima", "cuidate mucho",
        "feliz noche", "un abrazo hasta luego", "que descanses",
    ],
    "identidad": [
        "quien eres", "quien eres tu", "que eres", "que eres exactamente",
        "con quien hablo", "con quien estoy hablando", "eres un robot",
        "eres una persona", "eres humano", "eres una inteligencia artificial",
        "como te llamas", "cual es tu nombre", "tu nombre cual es",
        "dime quien eres", "quien eres y que haces", "te llamas como",
        "eres un bot", "eres real", "quien me atiende", "quien te creo",
        "que clase de asistente eres", "de donde eres",
    ],
    "capacidades": [
        "que puedes hacer", "que sabes hacer", "en que me puedes ayudar",
        "en que me ayudas", "para que sirves", "que tableros hay",
        "que tableros tienes", "que informacion tienes", "que puedo preguntarte",
        "que me puedes decir", "ayuda", "necesito ayuda", "como funcionas",
        "como te uso", "que cosas sabes", "que temas manejas",
        "con que me puedes ayudar", "que consultas puedo hacer",
        "que tipo de preguntas respondes", "cuales son tus funciones",
        "que tableros puedo consultar", "para que sirve este asistente",
        "que informacion manejas", "dime que puedes hacer", "que cosas puedo consultar",
    ],
}

_DOMINIO_BASE = [
    "como vamos", "como estamos este mes", "como va la ocupacion", "como esta la ocupacion",
    "que hay de nuevo en camas", "resumen de cirugias", "novedades de urgencias",
    "ayuda con las camas", "ayuda para consultar cirugias", "cual es el nivel de ocupacion",
    "cuantas cirugias se realizaron", "cuantas camas hay disponibles",
    "como estan las urgencias", "como va el triage", "como esta la facturacion",
    "que tableros de camas hay", "que puedes decirme de las cirugias",
    "quien es el medico con mas cirugias", "para que sirve el indicador de rotacion",
    "que significa la ocupacion", "como se calcula la estancia", "como se calcula el indicador",
]


class SimilitudPortero:
    """Similitud coseno (producto punto de vectores normalizados) contra ejemplos
    conversacionales y referencias de dominio, precalculados una sola vez."""

    def __init__(self, modelo, umbral: float = UMBRAL, margen: float = MARGEN,
                 referencias_dominio: list[str] | None = None,
                 umbral_alcance: float | None = None, margen_alcance: float | None = None):
        from src.chatbot import portero_alcance

        self.modelo = modelo
        self.umbral = umbral
        self.margen = margen
        self.umbral_alcance = portero_alcance.UMBRAL if umbral_alcance is None else umbral_alcance
        self.margen_alcance = portero_alcance.MARGEN if margen_alcance is None else margen_alcance
        self._claves: list[str] = []
        self._matriz = self._dominio = self._matriz_alcance = None
        self._textos_dominio: list[str] = []
        self._claves_alcance: list[str] = []
        try:
            import numpy as np

            self._np = np
            self._preparar_charla(referencias_dominio)
        except Exception as exc:
            logging.getLogger(__name__).warning("SimilitudPortero inactiva: %s", exc)
            self._matriz = None
        if self._matriz is not None:
            # Fuera de alcance (spec 002), aparte: si falla, la charla sigue con
            # similitud y el alcance queda solo con reglas.
            try:
                self._preparar_alcance(portero_alcance.EJEMPLOS)
            except Exception as exc:
                logging.getLogger(__name__).warning("similitud de alcance inactiva: %s", exc)
                self._matriz_alcance = None

    @staticmethod
    def _textos_y_claves(ejemplos: dict, clave) -> tuple[list[str], list[str]]:
        pares = [(normalizar(t), clave(sub)) for sub, lista in ejemplos.items() for t in lista]
        return [t for t, _ in pares], [c for _, c in pares]

    def _preparar_charla(self, referencias_dominio):
        textos, claves = self._textos_y_claves(EJEMPLOS, lambda s: f"{_TIPO_POR_SUBTIPO[s]}/{s}")
        refs = referencias_dominio if referencias_dominio is not None else referencias_dominio_defecto()
        refs = sorted({normalizar(r) for r in refs if normalizar(r)})
        self._matriz = self._codificar(textos)
        self._dominio = self._codificar(refs)
        self._claves, self._textos_dominio = claves, refs

    def _preparar_alcance(self, ejemplos: dict):
        textos, claves = self._textos_y_claves(ejemplos, lambda s: s)
        self._matriz_alcance = self._codificar(textos)
        self._claves_alcance = claves

    def mejor_alcance(self, texto: str):
        """(subtipo, sim_alcance, sim_dominio_max, sim_charla_max) o None."""
        if (self._matriz_alcance is None or self._dominio is None or not len(self._dominio)
                or self._matriz is None):
            return None
        try:
            v = self._vector(normalizar(texto))
            sims = self._matriz_alcance @ v
            i = int(sims.argmax())
            return (self._claves_alcance[i], float(sims[i]),
                    float((self._dominio @ v).max()), float((self._matriz @ v).max()))
        except Exception as exc:
            logging.getLogger(__name__).warning("SimilitudPortero.mejor_alcance fallo: %s",
                                                type(exc).__name__)
            return None

    def _vector(self, norm: str):
        """Vector de un texto normalizado; la charla y el alcance suelen pedir el
        mismo en un turno, así que se recuerdan los últimos (un solo encode)."""
        cache = self.__dict__.setdefault("_cache_vectores", {})
        v = cache.get(norm)
        if v is None:
            v = self._codificar([norm])[0]
            if len(cache) >= 256:
                cache.clear()
            cache[norm] = v
        return v

    def _codificar(self, textos):
        vec = self._np.asarray(
            self.modelo.encode(textos, normalize_embeddings=True), dtype=float)
        if vec.ndim != 2 or vec.shape[0] != len(textos):
            raise ValueError("encode devolvio una forma inesperada")
        return vec

    @property
    def activa(self) -> bool:
        return self._matriz is not None

    def mejor(self, texto: str, excluir_igual: bool = False):
        """(clave, sim_conversacional, sim_dominio_max) o None si inactiva/falla
        o sin referencias de dominio (sin ellas el margen no protege nada).

        ``excluir_igual`` ignora la referencia de dominio idéntica al texto
        (evaluación leave-one-out en calibración)."""
        if self._matriz is None or self._dominio is None or not len(self._dominio):
            return None
        try:
            norm = normalizar(texto)
            v = self._vector(norm)
            sims = self._matriz @ v
            i = int(sims.argmax())
            dom = self._dominio @ v
            if excluir_igual:
                dom = self._np.array(
                    [d for d, t in zip(dom, self._textos_dominio) if t != norm])
            if not dom.size:
                return None
            sim_dom = float(dom.max())
            return self._claves[i], float(sims[i]), sim_dom
        except Exception as exc:
            logging.getLogger(__name__).warning("SimilitudPortero.mejor fallo: %s", exc)
            return None


REFERENCIAS_PATH = Path(__file__).with_name("portero_referencias.json")


def referencias_dominio_defecto() -> list[str]:
    """Preguntas de dominio de referencia para el margen de la similitud.

    Se leen de ``portero_referencias.json`` (junto a este módulo; producción no
    lee ``tests/``). Se generó una vez con la base fija ``_DOMINIO_BASE``, las
    preguntas de ``tests/real/banco_real.json`` y los nulos de
    ``tests/portero/banco_portero.json`` de la calibración; nunca holdouts ni
    multi-turno. Si falta el archivo, solo la base fija."""
    try:
        datos = json.loads(REFERENCIAS_PATH.read_text(encoding="utf-8"))
        refs = [r for r in datos.get("referencias", []) if isinstance(r, str) and r.strip()]
        return refs or list(_DOMINIO_BASE)
    except Exception as exc:
        logging.getLogger(__name__).warning("referencias del portero no disponibles: %s", exc)
        return list(_DOMINIO_BASE)


# Palabras que no distinguen un tablero de otro al deduplicar nombres.
_VACIAS_NOMBRE = frozenset({"de", "del", "la", "el", "los", "las", "tablero", "tableros"})
# En minúscula dentro del nombre y nunca tratadas como siglas.
_MINUSCULAS_NOMBRE = frozenset({"de", "del", "la", "el", "los", "las", "y", "e", "o", "u",
                                "en", "por", "para", "con", "sin", "al", "a"})


def _nombre_tablero(nombre) -> str:
    """Nombre legible: «_» -> espacio, formato título, siglas (palabras en
    mayúsculas de hasta 4 letras en el original: ABC, NAOS, CVC, UCI) intactas."""
    partes = []
    for i, palabra in enumerate(str(nombre or "").replace("_", " ").split()):
        baja = palabra.lower()
        if i and baja in _MINUSCULAS_NOMBRE:
            partes.append(baja)
        elif (palabra.isalpha() and palabra.isupper() and len(palabra) <= 4
              and baja not in _MINUSCULAS_NOMBRE):
            partes.append(palabra)
        else:
            partes.append(palabra[:1].upper() + palabra[1:].lower())
    return " ".join(partes)


def _clave_tablero(nombre) -> str:
    """Clave de deduplicación: normalizada, sin palabras vacías ni plural final
    («Gestión De Camas» = «Gestion Camas», «Remisiones» = «Remision»)."""
    claves = []
    for t in normalizar(str(nombre or "").replace("_", " ")).split():
        if t in _VACIAS_NOMBRE:
            continue
        if len(t) > 4 and t.endswith("es"):
            t = t[:-2]
        elif len(t) > 3 and t.endswith("s"):
            t = t[:-1]
        claves.append(t)
    return " ".join(claves)


def _agregar(grupo: dict, nombre: str) -> None:
    """Un nombre por clave: el más corto (y luego alfabético)."""
    clave = _clave_tablero(nombre)
    if not clave:
        return
    actual = grupo.get(clave)
    if actual is None or (len(nombre), nombre) < (len(actual), actual):
        grupo[clave] = nombre


def _paginas_de_modelos(router, modelos) -> set[str]:
    """Claves de las páginas (catálogo visual) de los modelos consultables."""
    claves = set()
    paginas_de = getattr(router, "pages_for_model", None)
    if not callable(paginas_de):
        return claves
    for m in modelos:
        try:
            for ctx in paginas_de(m.get("semantic_model")) or []:
                nombre = ctx.get("dashboard") if isinstance(ctx, dict) else ctx
                clave = _clave_tablero(nombre)
                if clave:
                    claves.add(clave)
        except Exception:
            continue
    return claves


def catalogo_tableros(router) -> tuple[list[str], list[str]]:
    """(datos, documentacion): tableros con datos y tableros solo documentados.

    Nombres legibles y deduplicados; en documentación no van los que ya están en
    datos, ni las páginas de un modelo consultable, ni los «DICCIONARIO»."""
    try:
        if router is None:
            return [], []
        modelos = [m for m in (getattr(router, "models", None) or []) if isinstance(m, dict)]
        datos, claves = {}, set()
        for m in modelos:
            nombre = str(m.get("semantic_model") or "").strip()
            if nombre:
                _agregar(datos, _nombre_tablero(nombre))
                claves.add(_clave_tablero(nombre))
            clave = _clave_tablero(m.get("semantic_model_key") or "")
            if clave:
                claves.add(clave)
        claves |= _paginas_de_modelos(router, modelos)
        claves.discard("")
        docs = {}
        for entrada in getattr(router, "_documentation_dashboards", None) or []:
            try:
                nombre, grupo = entrada  # una entrada malformada se salta sola
            except (TypeError, ValueError):
                continue
            nombre = str(nombre or "").strip()
            if not nombre or nombre.upper().startswith("DICCIONARIO"):
                continue
            if _clave_tablero(nombre) in claves or _clave_tablero(grupo) in claves:
                continue
            _agregar(docs, _nombre_tablero(nombre))
        return sorted(datos.values()), sorted(docs.values())
    except Exception as exc:
        logging.getLogger(__name__).warning("catalogo_tableros fallo: %s", exc)
        return [], []


_EJEMPLO_PREGUNTA = "«¿Cuál es el nivel de ocupación?»"

_TEXTOS = {
    "saludo": ("¡Hola! Puedes preguntarme por los indicadores de los tableros "
               "institucionales, por ejemplo: «¿Cuántas cirugías se realizaron el mes pasado?»."),
    "estado": ("¡Hola! Estoy bien y listo para ayudarte. Puedes preguntarme por los "
               "indicadores de los tableros institucionales, por ejemplo: "
               "«¿Cuántas cirugías se realizaron el mes pasado?»."),
    "agradecimiento": "Con gusto. Si necesitas otro dato, aquí estoy.",
    "despedida": "¡Hasta pronto!",
    "identidad": ("Soy el asistente de consulta de los tableros institucionales del "
                  "Hospital Universitario de Caldas. Respondo con datos de Power BI y "
                  "con la documentación de los tableros. No doy recomendaciones clínicas."),
}


def recursos(root, modelo, router):
    """(vocabulario, similitud, datos, documentacion) del portero. La similitud
    MiniLM solo con vocabulario de dominio (su guarda) y si el modelo responde."""
    if root is None:
        from src.semantic.question_normalizer import PROJECT_ROOT as root
    vocabulario = vocabulario_dominio(root)
    similitud = None
    if vocabulario and modelo is not None:
        similitud = SimilitudPortero(modelo)
        if not similitud.activa:
            similitud = None
    datos, documentacion = catalogo_tableros(router)
    return vocabulario, similitud, datos, documentacion


_TITULOS_ALCANCE = {"vago": "Petición sin tema", "sin_sentido": "Mensaje sin contenido reconocible"}


def turno(c: Clasificacion, answer: str, message: str) -> tuple[str, list[str], dict, bool]:
    """(título y líneas del razonamiento, resultado del turno, ¿rechazo?).

    Los rechazos fuera de alcance (spec 002) salen por la ruta ``out_of_scope``
    que motor, app, evaluador y memoria ya entienden (y cortan el seguimiento);
    la petición vaga y el sin sentido, como la charla, por ``conversacion``."""
    kind = f"{c.tipo}/{c.subtipo}"
    resultado = {"status": "success", "route": "conversacion", "answer": answer,
                 "conversation_kind": kind, "question": message, "stage": f"portero/{kind}"}
    if c.tipo != "fuera_de_alcance":
        return ("Mensaje conversacional",
                [f"{kind} ({c.motivo}): respondido sin buscar en la documentación ni en Power BI"],
                resultado, False)
    rechazo = c.subtipo not in _TITULOS_ALCANCE
    if rechazo:
        resultado.update(status="not_found", route="out_of_scope", sources=[],
                         not_found_reason="portero_fuera_de_alcance")
    lineas = [f"{kind} ({c.motivo}): {c.detalle}",
              "respondido con un texto fijo, sin buscar en la documentación ni en Power BI "
              "ni usar el modelo de lenguaje"]
    return _TITULOS_ALCANCE.get(c.subtipo, "Mensaje fuera de alcance"), lineas, resultado, rechazo


def responder(c: Clasificacion, datos: list[str], documentacion: list[str]) -> str:
    """Texto fijo de respuesta para una clasificación del portero."""
    if c.tipo == "fuera_de_alcance":
        from src.chatbot import portero_alcance

        capacidades = ""
        if c.subtipo == "vago":
            capacidades = responder(Clasificacion("capacidades", "capacidades", 1.0, "regla"),
                                    datos, documentacion)
        return portero_alcance.texto_respuesta(c.subtipo, capacidades)
    if c.tipo == "capacidades":
        if not datos and not documentacion:
            return ("Puedo responder preguntas sobre los indicadores y la documentación "
                    f"de los tableros institucionales. Ejemplo: {_EJEMPLO_PREGUNTA}")
        partes = ["Puedo ayudarte con:"]
        if datos:
            partes.append(f"**Datos** (cifras de Power BI): {', '.join(datos)}")
        if documentacion:
            partes.append("**Documentación** (qué muestra cada tablero y cómo se calcula): "
                          f"{', '.join(documentacion)}")
        partes.append(f"Ejemplo: {_EJEMPLO_PREGUNTA}")
        return "\n\n".join(partes)
    return _TEXTOS.get(c.subtipo, _TEXTOS["saludo"])

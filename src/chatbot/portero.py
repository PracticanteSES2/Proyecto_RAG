"""Portero conversacional: detecta charla pura (saludo, gracias, despedida,
estado), preguntas de identidad y de capacidades, antes del flujo de datos.

Módulo puro, sin estado del motor. Ante cualquier duda devuelve ``None`` y el
mensaje sigue el flujo normal. Regla de oro: el mensaje normalizado, sin
muletillas, debe ser ENTERO una frase conversacional conocida (no contenerla).

Similitud MiniLM (tras reglas, lista de bloqueo y guardas; solo 3 a 8 palabras):
UMBRAL = 0.80 y MARGEN = 0.20 (valores iniciales de research D2, confirmados por
barrido umbral 0.70-0.85 x margen 0.10-0.30 sobre banco_portero + banco_real).
Cifras (2026-11-09, MiniLM real, 24 a 26 ejemplos por subtipo):
  - cobertura de casos C del banco del portero: 89/97 = 91.8 % (reglas solas 85/97);
  - falsos positivos: 0 (tambien en leave-one-out, sin la propia pregunta como
    referencia de dominio);
  - barrido ciego (banco_real + holdout + holdout2 + multiturno, 243 textos): 0;
  - latencia media por clasificar: ~37 ms (vectores precalculados).
Los 8 casos C restantes son de 1 a 2 palabras o los bloquea una guarda de dominio.
El menor margen de un nulo sin guarda fue 0.199 («hola hola cuantas consultas hay»,
que la guarda de dominio ya bloquea): subir el margen no es necesario, pero bajarlo
si lo seria problematico.
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
_PALABRAS_CONVERSACIONALES = frozenset(
    {w for lista in _FRASES.values() for f in lista for w in f.split()}
    | _MULETILLAS
    | {"hoy", "bien", "ayuda", "gracias", "hola", "buenas"}
)

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
})


@dataclass(frozen=True)
class Clasificacion:
    tipo: str
    subtipo: str
    confianza: float
    motivo: str


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
_EXACTAS = {" ".join(t): sub for t, sub in _TABLA}


def _coincidencia_aproximada(tokens: list[str]) -> str | None:
    for frase, sub in _TABLA:
        if _casa(tokens, frase):
            return sub
    return None


def clasificar(texto: str, vocabulario_dominio: frozenset[str] = frozenset(),
               similitud: "SimilitudPortero | None" = None) -> Clasificacion | None:
    """Clasifica charla/identidad/capacidades o devuelve None (flujo normal)."""
    if bloqueado_por_guardas(texto, vocabulario_dominio):
        return None
    tokens = _sin_muletillas(normalizar(texto))
    if not tokens or _en_lista_bloqueo(tokens):
        return None
    frase = " ".join(tokens)
    sub = _EXACTAS.get(frase)
    confianza = 1.0
    if sub is None:
        sub = _coincidencia_aproximada(tokens)
        confianza = 0.9
    if sub is not None:
        return Clasificacion(_TIPO_POR_SUBTIPO[sub], sub, confianza, "regla")
    return _por_similitud(frase, similitud)


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


def vocabulario_dominio(project_root) -> frozenset[str]:
    """Palabras del catálogo (targets) sin palabras conversacionales."""
    try:
        from src.semantic.question_normalizer import vocabulary_for

        palabras = {normalizar(k) for k in vocabulary_for(Path(project_root)).targets}
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
                 referencias_dominio: list[str] | None = None):
        self.modelo = modelo
        self.umbral = umbral
        self.margen = margen
        self._claves: list[str] = []
        self._matriz = None
        self._dominio = None
        self._textos_dominio: list[str] = []
        try:
            import numpy as np

            self._np = np
            textos, claves = [], []
            for sub, lista in EJEMPLOS.items():
                for t in lista:
                    textos.append(normalizar(t))
                    claves.append(f"{_TIPO_POR_SUBTIPO[sub]}/{sub}")
            refs = (referencias_dominio if referencias_dominio is not None
                    else referencias_dominio_defecto())
            refs = sorted({normalizar(r) for r in refs if normalizar(r)})
            self._matriz = self._codificar(textos)
            self._dominio = self._codificar(refs)
            self._claves = claves
            self._textos_dominio = refs
        except Exception as exc:
            logging.getLogger(__name__).warning("SimilitudPortero inactiva: %s", exc)
            self._matriz = None

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
        """(clave, sim_conversacional, sim_dominio_max) o None si inactiva/falla.

        ``excluir_igual`` ignora la referencia de dominio idéntica al texto
        (evaluación leave-one-out en calibración)."""
        if self._matriz is None:
            return None
        try:
            norm = normalizar(texto)
            v = self._codificar([norm])[0]
            sims = self._matriz @ v
            i = int(sims.argmax())
            dom = self._dominio @ v
            if excluir_igual:
                dom = self._np.array(
                    [d for d, t in zip(dom, self._textos_dominio) if t != norm])
            sim_dom = float(dom.max()) if dom.size else 0.0
            return self._claves[i], float(sims[i]), sim_dom
        except Exception as exc:
            logging.getLogger(__name__).warning("SimilitudPortero.mejor fallo: %s", exc)
            return None


def referencias_dominio_defecto() -> list[str]:
    """Preguntas de dominio de referencia: base fija + banco_real + nulos del banco
    del portero (si están en el repositorio). Nunca holdouts ni multi-turno."""
    refs = list(_DOMINIO_BASE)
    raiz = Path(__file__).resolve().parents[2] / "tests"
    try:
        banco = json.loads((raiz / "real" / "banco_real.json").read_text(encoding="utf-8"))
        refs += [c["pregunta"] for c in banco.get("casos", []) if c.get("pregunta")]
    except Exception:
        pass
    try:
        banco = json.loads(
            (raiz / "portero" / "banco_portero.json").read_text(encoding="utf-8"))
        refs += [c["texto"] for c in banco.get("casos", []) if c.get("esperado") is None]
    except Exception:
        pass
    return refs


def catalogo_tableros(router) -> tuple[list[str], list[str]]:
    """(datos, documentacion): tableros con datos y tableros solo documentados."""
    try:
        if router is None:
            return [], []
        modelos = getattr(router, "models", None) or []
        datos, claves = set(), set()
        for m in modelos:
            nombre = str(m.get("semantic_model") or "").strip()
            if nombre:
                datos.add(nombre.title())
                claves.add(normalizar(nombre))
            clave = normalizar(m.get("semantic_model_key") or "")
            if clave:
                claves.add(clave)
        docs = set()
        for nombre, grupo in getattr(router, "_documentation_dashboards", None) or []:
            nombre = str(nombre or "").strip()
            if not nombre or nombre.upper().startswith("DICCIONARIO"):
                continue
            if normalizar(nombre) in claves or normalizar(grupo) in claves:
                continue
            docs.add(nombre.title())
        return sorted(datos), sorted(docs)
    except Exception as exc:
        logging.getLogger(__name__).warning("catalogo_tableros fallo: %s", exc)
        return [], []


_EJEMPLO_PREGUNTA = "«¿Cuál es el nivel de ocupación?»"

_TEXTOS = {
    "saludo": ("¡Hola! Estoy bien y listo para ayudarte. Puedes preguntarme por los "
               "indicadores de los tableros institucionales, por ejemplo: "
               "«¿Cuántas cirugías se realizaron el mes pasado?»."),
    "agradecimiento": "Con gusto. Si necesitas otro dato, aquí estoy.",
    "despedida": "¡Hasta pronto!",
    "identidad": ("Soy el asistente de consulta de los tableros institucionales del "
                  "Hospital Universitario de Caldas. Respondo con datos de Power BI y "
                  "con la documentación de los tableros. No doy recomendaciones clínicas."),
}
_TEXTOS["estado"] = _TEXTOS["saludo"]


def responder(c: Clasificacion, datos: list[str], documentacion: list[str]) -> str:
    """Texto fijo de respuesta para una clasificación del portero."""
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

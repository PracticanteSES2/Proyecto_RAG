"""Portero conversacional: detecta charla pura (saludo, gracias, despedida,
estado), preguntas de identidad y de capacidades, antes del flujo de datos.

Módulo puro, sin estado del motor. Ante cualquier duda devuelve ``None`` y el
mensaje sigue el flujo normal. Regla de oro: el mensaje normalizado, sin
muletillas, debe ser ENTERO una frase conversacional conocida (no contenerla).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_PALABRAS = 8

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
    if sub is None:
        return None
    return Clasificacion(_TIPO_POR_SUBTIPO[sub], sub, confianza, "regla")


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

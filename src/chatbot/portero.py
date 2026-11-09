"""Portero conversacional: detecta charla pura (saludo, gracias, despedida,
estado), preguntas de identidad y de capacidades, antes del flujo de datos.

Módulo puro, sin estado del motor. Ante cualquier duda devuelve ``None`` y el
mensaje sigue el flujo normal. Regla de oro: el mensaje normalizado, sin
muletillas, debe ser ENTERO una frase conversacional conocida (no contenerla).
"""

from __future__ import annotations

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


def _en_lista_bloqueo(tokens: list[str]) -> bool:
    frase = " ".join(tokens)
    if frase in _SOLOS_FLUJO_NORMAL:
        return True
    if frase.startswith(("como vamos ", "como estamos ", "como va ", "ayuda con ",
                         "ayuda para ", "que hay de nuevo ")):
        return True
    # «como esta X» con más palabras: pregunta por X (no es saludo de estado).
    if len(tokens) > 2 and tokens[:2] == ["como", "esta"]:
        return True
    return False


def _distancia_maxima_uno(a: str, b: str) -> bool:
    """True si a y b difieren en como mucho una edición (Damerau)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        difs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(difs) == 1:
            return True
        return (len(difs) == 2 and difs[1] == difs[0] + 1
                and a[difs[0]] == b[difs[1]] and a[difs[1]] == b[difs[0]])
    corta, larga = (a, b) if len(a) < len(b) else (b, a)
    return any(larga[:i] + larga[i + 1:] == corta for i in range(len(larga)))


def _tabla():
    return [(f.split(), sub) for sub, lista in _FRASES.items() for f in lista]


_TABLA = _tabla()
_EXACTAS = {" ".join(t): sub for t, sub in _TABLA}


def _coincidencia_aproximada(tokens: list[str]) -> str | None:
    """Una sola edición permitida, y solo en palabras de 4+ letras."""
    for frase, sub in _TABLA:
        if len(frase) != len(tokens):
            continue
        ediciones = 0
        for a, b in zip(tokens, frase):
            if a == b:
                continue
            if len(a) < 4 or len(b) < 4 or not _distancia_maxima_uno(a, b):
                ediciones = 99
                break
            ediciones += 1
        if ediciones == 1:
            return sub
    return None


def clasificar(texto: str, vocabulario_dominio: frozenset[str] = frozenset(),
               similitud=None) -> Clasificacion | None:
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
    except Exception:
        return frozenset()

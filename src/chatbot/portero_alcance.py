"""Portero de alcance (segunda entrega): mensajes que no tienen nada que ver con
los tableros de Power BI del hospital ni con su documentación.

Módulo puro, sin LLM ni consultas. Regla de oro: un falso positivo (bloquear una
pregunta real) es mucho peor que un falso negativo, así que en la duda devuelve
``None`` y el mensaje sigue el flujo normal.

Cómo decide (spec 002, FR-002/FR-003), en este orden (``_DETECTORES``):

1. Plantillas vagas de mensaje ENTERO («necesito que me respondas algo»,
   «hazme un reporte de» sin tema).
2. Mensajes vacíos, risa o tecleo al azar en TODAS sus palabras (sin sentido).
3. Operaciones y ecuaciones escritas con números («2+2», «3x + 5 = 20»).
4. Marcadores explícitos por categoría (``portero_alcance_patrones``). Las
   palabras dentro del marcador y el campo semántico de la categoría quedan
   toleradas; cualquier otra palabra del catálogo (con tipeo de una letra),
   periodo, número o mención del propio hospital ANULA la detección.
5. Sin marcador: similitud MiniLM (``portero.SimilitudPortero.mejor_alcance``)
   solo sobre mensajes «limpios» de 3 a 12 palabras.

Se analiza el mensaje ORIGINAL del usuario: la normalización del motor corrige
tipeos hacia el catálogo y puede inventar palabras de dominio («arepas» →
«áreas», «respondas» → «respondidas»).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache

from src.chatbot.portero import normalizar
from src.chatbot.portero_alcance_patrones import (
    CATEGORIAS, DIRECCION, FILAS_TECLADO, FLUJO, GENERICAS, JERGA, PARTES_DEL_DIA, PERIODOS,
    PROPIO, RELLENO, RISA, SEGUIMIENTO, VAGO, Categoria,
)
from src.chatbot.portero_alcance_respuestas import EJEMPLOS, texto_respuesta  # noqa: F401 (API)
from src.semantic.question_normalizer import fold

MAX_CARACTERES = 200
MIN_PALABRAS_SIMILITUD = 3
MAX_PALABRAS_SIMILITUD = 12
# Calibración (MiniLM real, 2026-11-10): tras las anulaciones estrictas solo 7
# preguntas reales de todos los bancos llegan «limpias» a la similitud y ninguna
# pasa ni con 0.70/0.05; se fijan los mismos 0.80/0.20 de la charla (colchón) y
# además la similitud de alcance debe superar a la de charla («gracias, ¿qué
# más?» 0.80 alcance vs 0.97 charla). Paráfrasis nuevas captadas: 6/15.
UMBRAL = 0.80
MARGEN = 0.20

TIPO = "fuera_de_alcance"
SUBTIPOS = frozenset(("vago", "sin_sentido") + tuple(c.subtipo for c in CATEGORIAS))

_SIN_CATEGORIA = Categoria("", ())
_ANULADO = object()  # marcador presente pero con señal de dominio: flujo normal


@dataclass(frozen=True)
class Deteccion:
    subtipo: str
    motivo: str    # "regla" o "similitud"
    detalle: str   # marcador o similitud que la justifica


def _tokens(texto: str) -> list[str]:
    """Palabras normalizadas, con la jerga expandida y sin relleno («porfa»)."""
    return [JERGA.get(t, t) for t in normalizar(texto).split() if JERGA.get(t, t) not in RELLENO]


# ---------------------------------------------------------------- dominio

@lru_cache(maxsize=4)
def _indice_dominio(vocabulario: frozenset) -> tuple[frozenset, frozenset, frozenset]:
    """(exactas, comodines de sustitución, palabras con una letra menos) del
    vocabulario de dominio sin genéricas (solo palabras de 5+ letras para tipeos)."""
    exactas = frozenset(vocabulario - GENERICAS)
    largas = [w for w in exactas if len(w) >= 5]
    comodines = frozenset(w[:i] + "*" + w[i + 1:] for w in largas for i in range(len(w)))
    menos_una = frozenset(w[:i] + w[i + 1:] for w in largas for i in range(len(w)))
    return exactas, comodines, menos_una


def es_dominio(token: str, vocabulario: frozenset) -> bool:
    """Palabra del catálogo, o a una letra (sustitución, inserción u omisión) de
    una palabra del catálogo de 5+ letras («cirujias», «ocupasion», «cirugas»)."""
    if token in GENERICAS:
        return False
    exactas, comodines, menos_una = _indice_dominio(vocabulario)
    if token in exactas:
        return True
    if len(token) < 5:
        return False
    return token in menos_una or any(
        token[:i] + "*" + token[i + 1:] in comodines
        or (len(token) >= 6 and token[:i] + token[i + 1:] in exactas)
        for i in range(len(token)))


# ------------------------------------------------------------- anulaciones

def _anulacion_global(tokens: list[str]) -> str | None:
    if tokens and tokens[0] in SEGUIMIENTO:
        return "seguimiento"
    return "propio hospital" if PROPIO.search(" ".join(tokens)) else None


def _es_saludo_del_dia(tokens: list[str], i: int) -> bool:
    """«buenos días», «buenas tardes»: saludo, no periodo."""
    return tokens[i] in PARTES_DEL_DIA and i > 0 and tokens[i - 1] in ("buenos", "buenas", "buen")


def _anulacion_token(tokens: list[str], i: int, vocabulario: frozenset, cat: Categoria) -> str | None:
    t = tokens[i]
    if any(c.isdigit() for c in t):
        return None if cat.numero else "numero"
    if t in PERIODOS:
        return None if cat.periodo or _es_saludo_del_dia(tokens, i) else "periodo"
    if t in cat.tolera or not cat.por_dominio:
        return None
    return f"dominio «{t}»" if es_dominio(t, vocabulario) else None


def _anulacion_institucion(texto: str, tokens: list[str]) -> str | None:
    return "flujo entre instituciones" if FLUJO.search(texto) or DIRECCION.search(texto) else None


def _anulacion_clinica(texto: str, tokens: list[str]) -> str | None:
    """«¿cuántos pacientes con…?»: pregunta estadística, no consejo."""
    if "pacientes" in tokens or re.search(
            r"\bcuant[oa]s (?!mg|miligramos|ml|gotas|tabletas|pastillas|capsulas|veces)\w+", texto):
        return "pregunta estadistica"
    return None


_ANULACION_POR_CATEGORIA = {
    "otra_institucion": _anulacion_institucion,
    "clinico": _anulacion_clinica,
}


def motivo_anulacion(tokens: list[str], cubiertos: set[int], vocabulario: frozenset,
                     categoria: Categoria | None = None) -> str | None:
    """Por qué el mensaje NO puede ser fuera de alcance (o None si puede)."""
    cat = categoria or _SIN_CATEGORIA
    por_token = (_anulacion_token(tokens, i, vocabulario, cat)
                 for i in range(len(tokens)) if i not in cubiertos)
    motivo = _anulacion_global(tokens) or next((m for m in por_token if m), None)
    especifica = _ANULACION_POR_CATEGORIA.get(cat.subtipo)
    return motivo or (especifica(" ".join(tokens), tokens) if especifica else None)


# -------------------------------------------------------------- detectores

def _por_vago(original, tokens, vocabulario):
    return Deteccion("vago", "regla", "petición sin tema") if VAGO.match(" ".join(tokens)) else None


def _es_tecleo(t: str, vocabulario: frozenset) -> bool:
    if t in vocabulario or not t.isalpha():  # «2024» es un año, no tecleo
        return False
    if len(t) >= 4 and not re.search(r"[aeiouy]", t):
        return True
    if any(f[i:i + 4] in t or f[i:i + 4][::-1] in t for f in FILAS_TECLADO for i in range(len(f) - 3)):
        return True
    return bool(re.fullmatch(r"([a-z]{2,4})\1{2,}[a-z]{0,3}", t))


def _por_sin_sentido(original, tokens, vocabulario):
    if not tokens:
        return Deteccion("sin_sentido", "regla", "mensaje vacío o solo signos")
    if all(RISA.match(t) or _es_tecleo(t, vocabulario) for t in tokens):
        return Deteccion("sin_sentido", "regla", "risa o tecleo sin palabras")
    return None


def normalizar_operaciones(texto: str) -> str:
    """Minúsculas sin tildes (``fold``) conservando operadores (+ - * / x ^ =)."""
    base = fold(texto).replace("×", "*").replace("÷", "/").replace(",", ".")
    base = re.sub(r"[^a-z0-9+\-*/^=.]+", " ", base)
    base = re.sub(r"\s*([+\-*/^=])\s*", r" \1 ", base)
    return " ".join(base.split()).strip(" .")


# Sin «cuánto es» solo + * x ^: «10/2025» o «2024-2025» son periodos.
_ARITMETICA = (re.compile(r"\d+(\.\d+)?( ?[+*x^] ?\d+(\.\d+)?)+( ?=)?"),
               re.compile(r"cuanto (es|son|da) \d+(\.\d+)?( ?[-+*/x^] ?\d+(\.\d+)?)+( ?=)?"))
_ECUACION = re.compile(r"\d*x ?[-+*/] ?\d+ ?= ?-?\d+")
_RELLENO_ECUACION = re.compile(
    r"\b(resuelve|resuelveme|resolver|despeja|ecuacion|esta|la|oye|porfa|por favor|ayudame|a)\b")


def _por_aritmetica(original, tokens, vocabulario):
    crudo = normalizar_operaciones(original)
    if any(p.fullmatch(crudo) for p in _ARITMETICA):
        return Deteccion("calculo", "regla", "operación aritmética")
    resto = _RELLENO_ECUACION.sub("", crudo)
    if _ECUACION.search(crudo) and not re.search(r"[a-wyz]{4,}", resto):
        return Deteccion("calculo", "regla", "ecuación")
    return None


def _tramos(patrones, texto: str) -> list[tuple[int, int]]:
    return [m.span("m") if "m" in p.groupindex else m.span() for p in patrones for m in p.finditer(texto)]


def _cubiertos(texto: str, spans) -> set[int]:
    """Índices de las palabras de ``texto`` que caen dentro de algún tramo."""
    salida, pos = set(), 0
    for i, t in enumerate(texto.split(" ")):
        if any(a <= pos and pos + len(t) <= b for a, b in spans):
            salida.add(i)
        pos += len(t) + 1
    return salida


def _por_marcadores(original, tokens, vocabulario):
    """Primera categoría con marcador; anulada si hay señal de dominio."""
    texto = " ".join(tokens)
    for cat in CATEGORIAS:
        spans = _tramos(cat.patrones, texto)
        if not spans:
            continue
        cubiertos = _cubiertos(texto, spans + _tramos(cat.extras, texto))
        if motivo_anulacion(tokens, cubiertos, vocabulario, cat):
            return _ANULADO
        a, b = spans[0]
        return Deteccion(cat.subtipo, "regla", f"marcador «{texto[a:b]}»")
    return None


_DETECTORES = (_por_vago, _por_sin_sentido, _por_aritmetica, _por_marcadores)


def detectar(original: str, vocabulario: frozenset = frozenset(),
             similitud=None) -> Deteccion | None:
    """Detección fuera de alcance, o None (flujo normal). Nunca lanza."""
    try:
        return _detectar(original, vocabulario, similitud)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "portero de alcance desactivado en este mensaje (%s)", type(exc).__name__)
        return None


def _detectar(original, vocabulario, similitud):
    if len(original or "") > MAX_CARACTERES:
        return None
    tokens = _tokens(original)
    for detector in _DETECTORES:
        r = detector(original, tokens, vocabulario)
        if r is not None:
            return None if r is _ANULADO else r
    return _por_similitud(tokens, vocabulario, similitud)


def _por_similitud(tokens, vocabulario, similitud):
    """Última barrera: mensaje «limpio» (sin catálogo, periodo, número ni
    hospital) de 3 a 12 palabras, sobre umbral y con margen."""
    mejor = getattr(similitud, "mejor_alcance", None)
    if not callable(mejor) or not (MIN_PALABRAS_SIMILITUD <= len(tokens) <= MAX_PALABRAS_SIMILITUD):
        return None
    if motivo_anulacion(tokens, set(), vocabulario, None):
        return None
    try:
        r = mejor(" ".join(tokens))
    except Exception as exc:
        logging.getLogger(__name__).warning("similitud de alcance fallo: %s", type(exc).__name__)
        return None
    if r is None:
        return None
    subtipo, sim, sim_dominio, sim_charla = r
    umbral = getattr(similitud, "umbral_alcance", UMBRAL)
    margen = getattr(similitud, "margen_alcance", MARGEN)
    if sim < umbral or sim - sim_dominio < margen or sim <= sim_charla:
        return None
    return Deteccion(subtipo, "similitud",
                     f"similitud {sim:.2f} (margen {sim - sim_dominio:.2f} frente a preguntas de dominio)")

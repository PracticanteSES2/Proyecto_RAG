"""Normalización de texto para comparar: la ÚNICA implementación de «minúsculas y sin tildes».

Antes de escribir otra variante, mira si una de estas sirve (docs/ARQUITECTURA.md §11):

    plegar("Atención Médica")             -> "atencion medica"    minúsculas, sin tildes; signos intactos
    normalizar("Ocupación (%) - Cama")    -> "ocupacion cama"     solo [a-z0-9], palabras separadas por un espacio
    normalizar("Ocupación (%)", "%")      -> "ocupacion %"        igual, conservando los caracteres indicados
    llave("Nº de Camas_UCI")              -> "ndecamasuci"       solo [a-z0-9], sin espacios (comparar nombres)
    slug("Tablero Briefing")              -> "tablero_briefing"   [a-z0-9] unidos por «_» (carpetas, claves)
    sin_tildes("Atención ½")              -> "Atencion 1⁄2"       NFKD sin combinantes; NO cambia mayúsculas

Las cuatro primeras aplican, en este orden: ``str(texto or "")`` → ``lower()`` → NFD → quitar las marcas de categoría
``Mn`` (la «ñ» queda «n»). Las variantes que quedan en el código y NO son equivalentes (NFKD con
``unicodedata.combining``, ``casefold``, mayúsculas, signos conservados, misma longitud) lo dicen en un
comentario junto a su definición. ``sin_tildes`` es la variante «de compatibilidad» (NFKD: ligaduras,
superíndices y fracciones se descomponen) que usan los rótulos y los enlaces; ``tests/comun/test_texto.py`` prueba la equivalencia de cada sustitución.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# Atajo para el español: las vocales con tilde, diéresis o grave y la «ñ» sin pasar por NFD.
# Da lo mismo que NFD + quitar «Mn» (lo prueba tests/comun/test_texto.py carácter por carácter).
_PLIEGUE_RAPIDO = str.maketrans("áéíóúüñàèìòùâêîôû", "aeiouunaeiouaeiou")
_NO_ALFANUM = re.compile(r"[^a-z0-9]+")


def plegar(texto) -> str:
    """Minúsculas y sin tildes (NFD sin marcas ``Mn``); conserva espacios y signos."""
    texto = str(texto or "").lower()
    if texto.isascii():
        return texto
    texto = texto.translate(_PLIEGUE_RAPIDO)
    if texto.isascii():
        return texto
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


@lru_cache(maxsize=16)
def _no_permitidos(conservar: str) -> re.Pattern:
    if not conservar:
        return _NO_ALFANUM
    return re.compile(r"[^a-z0-9" + re.escape(conservar) + r"]+")


def normalizar(texto, conservar: str = "") -> str:
    """``plegar`` + todo lo que no sea ``[a-z0-9]`` (ni ``conservar``) pasa a un espacio; sin espacios dobles
    ni en los extremos. ``conservar="%"`` es la variante de los indicadores («porcentaje de ocupación %»)."""
    return _no_permitidos(conservar).sub(" ", plegar(texto)).strip()


def llave(texto) -> str:
    """Clave compacta para comparar nombres: ``plegar`` y solo ``[a-z0-9]``, sin separadores."""
    return _NO_ALFANUM.sub("", plegar(texto))


def slug(texto) -> str:
    """``plegar`` y las secuencias que no son ``[a-z0-9]`` pasan a «_» (sin «_» en los extremos)."""
    return _NO_ALFANUM.sub("_", plegar(texto)).strip("_")


def sin_tildes(texto) -> str:
    """NFKD y sin caracteres combinantes (``unicodedata.combining``); mayúsculas y signos intactos.

    No es ``plegar`` sin ``lower``: NFKD descompone también ligaduras, superíndices y fracciones («ﬁ» → «fi»,
    «²» → «2») y ``combining`` no coincide con la categoría ``Mn`` en todos los caracteres.
    """
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c))

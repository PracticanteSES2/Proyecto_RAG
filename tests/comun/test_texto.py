"""Equivalencia de src/comun/texto.py con las variantes de normalización que reemplaza.

Cada ORÁCULO es la copia literal de una función que existía en src/ antes de la fase 3 (docs/ARQUITECTURA.md);
la sustitución solo es válida si la función canónica da exactamente lo mismo:

  * para TODOS los puntos de código Unicode, solos y en contexto («A» + c + tilde combinante);
  * para cadenas aleatorias (semilla fija) con letras, tildes combinantes, signos y espacios raros;
  * para el vocabulario real del catálogo (nombres de tableros, tablas, columnas, medidas y valores),
    si hay un data/ disponible (en el worktree o en el checkout principal; si no, se omite esa parte).

Por defecto el vocabulario y los contextos se muestrean (~1 min). ``TEXTO_EXHAUSTIVO=1`` lo recorre todo
(~5 min); se corrió así al hacer cada sustitución de la fase 3.

    python -X utf8 -m unittest tests.comun.test_texto
"""
import json
import os
import random
import re
import sys
import unicodedata
import unittest
from pathlib import Path

from src.comun import texto as T

RAIZ = Path(__file__).resolve().parents[2]
EXHAUSTIVO = bool(os.getenv("TEXTO_EXHAUSTIVO"))


# ---------------------------------------------------------------------------------------------
# Oráculos: copias literales de las variantes originales (agrupadas por comportamiento)
# ---------------------------------------------------------------------------------------------

def o_fold_lento(text):
    # detail_formatter._fold · domain_cache._plain · extractive._plain · detail_list._fold
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


_FAST_FOLD = str.maketrans("áéíóúüñàèìòùâêîôû", "aeiouunaeiouaeiou")


def o_fold_rapido(text):
    # semantic/question_normalizer.fold
    text = str(text or "").lower()
    if text.isascii():
        return text
    text = text.translate(_FAST_FOLD)
    if text.isascii():
        return text
    text = unicodedata.normalize("NFD", text)
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def o_normalize_text(value):
    # global_master_metric_builder · master_metric_resolver · query_semantic_planner ·
    # source_model_router · visual_catalog_builder (normalize_text)
    value = str(value or "").lower().strip()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def o_normalize_text_strip_lower(value):
    # powerbi_catalog_manager.normalize_text
    value = str(value or "").strip().lower()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def o_table_coverage(value):
    # table_coverage._normalize
    value = str(value or "").lower()
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def o_table_titles(text):
    # table_titles._plain (sin colapsar espacios: la regex ya los colapsa)
    text = unicodedata.normalize("NFD", str(text or "").lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def o_ranking(text):
    # rag/ranking.normalize_text ([^a-z0-9\s] y luego \s+)
    text = str(text or "").lower().strip()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def o_business_filter(value):
    # business_filter_resolver.BusinessFilterResolver._normalize
    if not value:
        return ""
    value = str(value).lower()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def o_metric_resolver(value):
    # metric_resolver.MetricResolver._normalize_text («_» a espacio antes de la regex)
    if not value:
        return ""
    value = str(value).lower()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn")
    value = value.replace("_", " ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def o_resolucion(value):
    # semantic/resolucion/texto._normalize_str (conserva %)
    value = str(value or "")
    value = value.lower().strip()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9%]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def o_question_kind(value):
    # question_kind.normalize_question · documented_aggregations._normalize (conserva %)
    value = str(value or "").lower().strip()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9%]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def o_intent_parser(text):
    # chatbot/intent_parser.normalize_text ([^a-z0-9%\s] y luego \s+)
    if not text:
        return ""
    text = text.lower().strip()
    text = "".join(character for character in unicodedata.normalize("NFD", text)
                   if unicodedata.category(character) != "Mn")
    text = re.sub(r"[^a-z0-9%\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def o_business_terms(text):
    # chatbot/business_terms.fold (conserva %, split/join)
    text = unicodedata.normalize("NFD", str(text or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", text).split())


def o_llave(value):
    # dax_validator._normalize · filter_resolver.normalize_name · semantic_merge.normalize_name
    if not value:
        return ""
    value = str(value).strip().lower()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]", "", value)


def o_dax_validator(value):
    # dax/dax_validator.DAXValidator._normalize (solo None es vacío)
    if value is None:
        return ""
    value = str(value).strip().lower()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]", "", value)


def o_compact(name):
    # providers/domain_cache._compact · semantic/detail_list.compact
    text = unicodedata.normalize("NFD", str(name or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", text)


def _clean_parser(text):
    if not text:
        return ""
    text = str(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def o_slugify_parser(value):
    # ingestion/document_parser.slugify
    value = _clean_parser(value).lower()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _clean_chunk(value):
    if value is None:
        return ""
    value = str(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def o_normalize_key(value):
    # rag/chunk_builder.normalize_key
    value = _clean_chunk(value).lower()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def o_slug_repositorio(texto):
    # docs_md/repositorio.slug (NFD y quitar Mn ANTES de lower)
    texto = unicodedata.normalize("NFD", str(texto or ""))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_") or "pagina"


def o_slugify_catalogo(value):
    # semantic/powerbi_catalog_manager.slugify
    return o_normalize_text_strip_lower(value).replace(" ", "_") or "sin_nombre"


def o_source_labels(text):
    # rag/source_labels._plain
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().upper()


def o_norm_label(text):
    # chatbot/response_formatter._norm_label (con su _plain = " ".join(split()))
    text = unicodedata.normalize("NFKD", " ".join(str(text or "").split()).lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def o_powerbi_links(texto):
    # providers/powerbi_links.normalizar
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[_\-.]+", " ", texto.upper())
    return " ".join(texto.split())


# Pares (oráculo, función canónica que lo reemplaza).
EQUIVALENCIAS = [
    ("fold lento", o_fold_lento, T.plegar),
    ("fold rápido", o_fold_rapido, T.plegar),
    ("normalize_text", o_normalize_text, T.normalizar),
    ("normalize_text strip/lower", o_normalize_text_strip_lower, T.normalizar),
    ("table_coverage", o_table_coverage, T.normalizar),
    ("table_titles", o_table_titles, T.normalizar),
    ("ranking", o_ranking, T.normalizar),
    ("business_filter", o_business_filter, T.normalizar),
    ("metric_resolver", o_metric_resolver, T.normalizar),
    ("resolucion %", o_resolucion, lambda v: T.normalizar(v, "%")),
    ("question_kind %", o_question_kind, lambda v: T.normalizar(v, "%")),
    ("intent_parser %", o_intent_parser, lambda v: T.normalizar(v, "%")),
    ("business_terms %", o_business_terms, lambda v: T.normalizar(v, "%")),
    ("llave", o_llave, T.llave),
    ("compact", o_compact, T.llave),
    ("dax_validator", o_dax_validator, lambda v: "" if v is None else T.llave(str(v))),
    ("slugify parser", o_slugify_parser, T.slug),
    # chunk_builder.clean_text solo trata None como vacío (0 -> "0"): se conserva delante de slug.
    ("normalize_key", o_normalize_key, lambda v: T.slug(_clean_chunk(v))),
    ("slugify catálogo", o_slugify_catalogo, lambda v: T.slug(v) or "sin_nombre"),
    # También tools/import_documentation_batch, tools/local_data/metadata_format y tools/sync_powerbi_metadata
    # (normalize_text = «strip/lower», slugify = «slugify catálogo»).
    ("slug repositorio", o_slug_repositorio, lambda v: T.slug(v) or "pagina"),
    ("source_labels", o_source_labels, lambda v: re.sub(r"\s+", " ", T.sin_tildes(v)).strip().upper()),
    ("norm_label", o_norm_label, lambda v: T.sin_tildes(" ".join(str(v or "").split()).lower())),
    ("powerbi_links", o_powerbi_links,
     lambda v: " ".join(re.sub(r"[_\-.]+", " ", T.sin_tildes(v).upper()).split())),
]


def _todos_los_puntos():
    """Los puntos de código que distinguen a una variante de otra, más un representante de cada clase.

    Todas las variantes dependen solo de: ASCII sí/no, ``lower()``, ``casefold()``, NFD, NFKD, la categoría
    (``Mn`` y demás marcas), ``combining`` e ``isspace()`` (la clase de espacios de ``re``). Un carácter que no es ASCII ni
    espacio ni marca y que ninguna de esas operaciones cambia acaba como separador en TODAS las variantes; se
    prueba una muestra de ellos en vez del millón largo.
    """
    resto = []
    for cp in range(sys.maxunicode + 1):
        if 0xD800 <= cp <= 0xDFFF:
            continue
        c = chr(cp)
        if (c.isascii() or c.isspace() or c.lower() != c or c.casefold() != c
                or unicodedata.normalize("NFD", c) != c or unicodedata.normalize("NFKD", c) != c
                or unicodedata.category(c).startswith("M") or unicodedata.combining(c)):
            yield c
        else:
            resto.append(c)
    yield from resto[:: max(1, len(resto) // 2000)]


def _aleatorias(n=8000, semilla=20261110):
    rnd = random.Random(semilla)
    alfabeto = (
        "abcxyzABCXYZ0189 áéíóúüñÁÉÍÓÚÜÑàèâêçãõøßæœİıǅẞΣσςΩ"
        "%_-./,;:()[]{}'\"¿?¡!#&*+=\t\n\r\xa0 ​̧́̃̈͏⃝"
        "ﬁ①²½ＡＢｃＣº ª№™"
    )
    for _ in range(n):
        yield "".join(rnd.choice(alfabeto) for _ in range(rnd.randint(0, 24)))


def _data_root():
    candidatos = [RAIZ / "data"]
    git = RAIZ / ".git"
    if git.is_file():
        texto = git.read_text(encoding="utf-8").strip()
        if texto.startswith("gitdir:"):
            gitdir = Path(texto.split(":", 1)[1].strip())
            if gitdir.parent.name == "worktrees":
                candidatos.append(gitdir.parents[2] / "data")
    for c in candidatos:
        if (c / "catalog").is_dir():
            return c
    return None


def _vocabulario(limite=60000):
    raiz = _data_root()
    if raiz is None:
        return []
    vistos = set()

    def recorrer(obj):
        if len(vistos) >= limite:
            return
        if isinstance(obj, str):
            if len(obj) <= 300:
                vistos.add(obj)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                vistos.add(str(k))
                recorrer(v)
        elif isinstance(obj, list):
            for v in obj:
                recorrer(v)

    for ruta in sorted((raiz / "catalog").rglob("*.json")):
        try:
            recorrer(json.loads(ruta.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(vistos)


class TestEquivalencias(unittest.TestCase):
    def _comparar(self, entradas, etiqueta):
        for nombre, oraculo, canonica in EQUIVALENCIAS:
            for e in entradas:
                try:
                    esperado = oraculo(e)
                except AttributeError:
                    # La original solo aceptaba str (intent_parser: «text.lower()»); la canónica acepta cualquiera.
                    continue
                obtenido = canonica(e)
                if esperado != obtenido:
                    self.fail(f"[{etiqueta}] {nombre}: {e!r} -> {esperado!r} (original) vs {obtenido!r} (canónica)")

    def test_todos_los_puntos_de_codigo(self):
        self._comparar(list(_todos_los_puntos()), "punto de código")

    def test_puntos_en_contexto(self):
        # Letra antes y tilde combinante después: el orden lower/NFD y la reordenación canónica importan aquí.
        puntos = [c for c in _todos_los_puntos() if not c.isascii() or c.isalnum()]
        if not EXHAUSTIVO:
            puntos = puntos[::5]
        self._comparar([f"A{c}́ x" for c in puntos], "en contexto")

    def test_cadenas_aleatorias(self):
        self._comparar(list(_aleatorias()), "aleatoria")

    def test_valores_no_texto(self):
        self._comparar([None, "", 0, 0.0, False, 12, 3.5, "  ", "\xa0"], "no texto")

    def test_vocabulario_real_del_catalogo(self):
        vocabulario = _vocabulario()
        if not EXHAUSTIVO:
            vocabulario = vocabulario[:: max(1, len(vocabulario) // 6000)]
        if not vocabulario:
            self.skipTest("sin data/catalog (ni en el worktree ni en el checkout principal)")
        self._comparar(vocabulario, "catálogo")


class TestEjemplos(unittest.TestCase):
    def test_documentados(self):
        self.assertEqual(T.plegar("Atención Médica"), "atencion medica")
        self.assertEqual(T.normalizar("Ocupación (%) - Cama"), "ocupacion cama")
        self.assertEqual(T.normalizar("Ocupación (%)", "%"), "ocupacion %")
        self.assertEqual(T.llave("Nº de Camas_UCI"), "ndecamasuci")
        self.assertEqual(T.slug("Tablero Briefing"), "tablero_briefing")
        self.assertEqual(T.plegar("Niño, ¿año?"), "nino, ¿ano?")


if __name__ == "__main__":
    unittest.main()

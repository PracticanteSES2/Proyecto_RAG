"""
Pruebas offline del diccionario de variables en el RAG
(«DICCIONARIO <TABLERO>», payload `is_dictionary`).

Cubre: fuera de alcance sin chunks del diccionario, alias de grupo que apuntan
al tablero (no al diccionario), medidas del diccionario fuera de la resolución
de métricas y etiquetas legibles de las fuentes.

Ejecutar:  python -m tests.rag.test_dictionary_retrieval      (o con pytest)
Sin modelo de embeddings ni Qdrant: reutiliza los dobles de test_rag_retrieval.
"""
import sys

sys.dont_write_bytecode = True

from src.chatbot.answer_synthesizer import AnswerSynthesizer
from src.rag.chunk_builder import _base_metadata
from src.rag.extractive import readable_fallback
from src.rag.retriever import HybridRetriever
from src.rag.source_labels import (
    dictionary_page_label,
    is_dictionary_source,
    source_label,
)
from src.semantic.metric_resolver import MetricResolver
from tests.rag.test_rag_retrieval import (
    CHUNKS,
    LAV,
    URG,
    _FakeClient,
    _FakeModel,
    _FakeProvider,
    _chunk,
)


DIC_LAV = "DICCIONARIO TABLERO LAVANDERIA"
DIC_URG = "DICCIONARIO TABLERO TIEMPOS URGENCIAS"


def _dictionary_chunk(point_id, chunk_type, dashboard, group, model, text,
                      measure=None, section=None, flag=True):
    chunk = _chunk(point_id, chunk_type, dashboard, group, model, text,
                   aliases=[model], measure=measure)
    chunk["payload"]["section"] = section or chunk_type
    if flag:
        chunk["payload"]["is_dictionary"] = True
    return chunk


DICTIONARY_CHUNKS = [
    _dictionary_chunk(
        "d1", "measure", DIC_LAV, *LAV,
        "Tablero: DICCIONARIO TABLERO LAVANDERIA Medida Power BI: TURNO_OK Tabla: LAVANDERIA "
        "Descripción: Nombre del turno laboral (MAÑANA, TARDE, NOCHE) según LAVANDERIA[Turno].",
        measure="TURNO_OK", section="measures"),
    _dictionary_chunk(
        "d2", "calculated_column", DIC_LAV, *LAV,
        "Tablero: DICCIONARIO TABLERO LAVANDERIA Columna calculada: PESO_KG Tabla: LAVANDERIA "
        "Descripción: Peso de la ropa en kilogramos.", section="calculated_columns"),
    # Índice antiguo: sin `is_dictionary`, se reconoce solo por el nombre.
    _dictionary_chunk(
        "d3", "calculated_column", DIC_URG, *URG,
        "Tablero: DICCIONARIO TABLERO TIEMPOS URGENCIAS Columna calculada: EN_ESPERA "
        "Tabla: TRIAGE Descripción: Pacientes en espera por tramo horario.",
        section="calculated_columns", flag=False),
]

ALL_CHUNKS = CHUNKS + DICTIONARY_CHUNKS


def make_retriever(scores=None, default=0.30):
    retriever = HybridRetriever.__new__(HybridRetriever)
    retriever.model = _FakeModel()
    retriever.client = _FakeClient(ALL_CHUNKS, scores=scores, default=default)
    retriever.collection_name = "test"
    retriever._load_corpus()
    return retriever


# ============================================================
# 1. FUERA DE ALCANCE: SIN CHUNKS DEL DICCIONARIO
# ============================================================

def test_out_of_scope_returns_no_dictionary_chunks():
    question = "como va a estar el clima mañana en manizales"
    # Coseno alto (0,51 con el modelo real) solo contra el diccionario: sin
    # apoyo léxico no prueba nada.
    retriever = make_retriever(
        scores={question: {"d1": 0.60, "d2": 0.60, "d3": 0.60}},
        default=0.10,
    )
    assert retriever.search_general(question, limit=5) == []


def test_dictionary_entry_kept_with_lexical_support():
    question = "que es la columna peso kg"
    retriever = make_retriever(scores={question: {"d2": 0.55}}, default=0.10)
    results = retriever.search_general(question, limit=3)
    assert results and results[0]["dashboard"] == DIC_LAV, results
    assert results[0]["is_dictionary"] is True


def test_legacy_dictionary_recognized_by_name():
    retriever = make_retriever()
    by_id = {item["id"]: item for item in retriever._corpus}
    assert by_id["d3"]["is_dictionary"] is True
    assert by_id["u1"]["is_dictionary"] is False


def test_named_entry_outranks_chunks_that_only_mention_it():
    question = "como se calcula el turno ok en lavanderia"
    indicator = _chunk(
        "i1", "indicator", "Página 1", *LAV,
        "Tablero: Página 1 Indicador documentado: Peso por turno: Peso total de cada turno "
        "(LAVANDERIA[TURNO_OK]) y su porcentaje sobre el total.", aliases=["LAVANDERIA"])
    column = _dictionary_chunk(
        "d4", "calculated_column", DIC_LAV, *LAV,
        "Tablero: DICCIONARIO TABLERO LAVANDERIA Columna calculada: TURNO_OK Tabla: LAVANDERIA "
        "Descripción: Turno laboral en texto: 1 MAÑANA, 2 TARDE, 3 NOCHE.",
        section="calculated_columns")
    retriever = HybridRetriever.__new__(HybridRetriever)
    retriever.model = _FakeModel()
    retriever.client = _FakeClient(
        [CHUNKS[5], indicator, column],
        scores={question: {"i1": 0.29, "d4": 0.22}},
        default=0.10,
    )
    retriever.collection_name = "test"
    retriever._load_corpus()
    results = retriever.search_general(question, limit=3)
    assert "TURNO_OK" in results[0]["source_label"], [r["source_label"] for r in results]


# ============================================================
# 2. ALIAS DE GRUPO -> TABLERO (NO EL DICCIONARIO)
# ============================================================

def test_group_alias_points_to_dashboard_not_dictionary():
    retriever = make_retriever()
    aliases = retriever.dashboard_aliases
    assert aliases["lavanderia"] == "LAVADERIA", aliases
    assert aliases.get("tablero lavanderia") != DIC_LAV, aliases
    # El diccionario solo se nombra a sí mismo.
    assert aliases["diccionario tablero lavanderia"] == DIC_LAV
    assert retriever.detect_dashboard("que muestra el tablero de lavanderia") == "LAVADERIA"
    # Su nombre contiene todos los tokens del informe, pero no es su página
    # principal.
    assert retriever.detect_dashboard("que es el boton azul en tiempos de urgencias") == (
        "TIEMPO TOTAL EN URGENCIAS"
    )


# ============================================================
# 3. MEDIDAS DEL DICCIONARIO: NO SON CANDIDATAS DE MÉTRICA
# ============================================================

def test_dictionary_measures_excluded_from_measure_search():
    retriever = make_retriever(default=0.50)
    candidates = retriever.search_measure_candidates("turno ok", limit=20)
    assert candidates and not any(c.get("is_dictionary") for c in candidates), candidates
    assert retriever.get_measures_by_dashboard(DIC_LAV) == []


class _DictionaryOnlyRetriever:
    """Retriever antiguo / doble que sí devuelve medidas del diccionario."""

    def search_measure_candidates(self, question, limit=20, dashboard=None):
        return [{"measure": "TURNO_OK", "dashboard": DIC_LAV, "score": 0.9,
                 "chunk_type": "measure", "text": DICTIONARY_CHUNKS[0]["payload"]["text"]}]

    def get_measures_by_dashboard(self, dashboard):
        return self.search_measure_candidates("")


def test_metric_resolver_ignores_dictionary_measures():
    resolver = MetricResolver(_DictionaryOnlyRetriever(), debug=False)
    result = resolver.resolve({"metric_type": "turno ok", "original_question": "turno ok"})
    assert result["status"] == "not_found", result
    result = resolver.resolve({"metric_type": "turno ok", "dashboard": DIC_LAV})
    assert result["status"] == "not_found", result


# ============================================================
# 4. ETIQUETA LEGIBLE
# ============================================================

def test_source_label_for_dictionary_and_pages():
    measure = dict(DICTIONARY_CHUNKS[0]["payload"])
    assert source_label(measure) == (
        "Diccionario de variables · TABLERO LAVANDERIA › Medidas › [TURNO_OK]"
    )
    column = dict(DICTIONARY_CHUNKS[2]["payload"])
    assert source_label(column) == (
        "Diccionario de variables · TABLERO TIEMPOS URGENCIAS › Columnas calculadas › TRIAGE[EN_ESPERA]"
    )
    assert source_label(dict(CHUNKS[0]["payload"])) == "TIEMPO TOTAL EN URGENCIAS"
    assert dictionary_page_label("LAVADERIA") == "LAVADERIA"
    assert dictionary_page_label("diccionario tablero cvc") == "Diccionario de variables · tablero cvc"


def test_retriever_results_carry_readable_label():
    question = "que es la columna peso kg"
    retriever = make_retriever(scores={question: {"d2": 0.55}}, default=0.10)
    result = retriever.search_general(question, limit=1)[0]
    assert result["source_label"].startswith("Diccionario de variables · TABLERO LAVANDERIA")


def test_synthesis_and_fallback_name_the_dictionary():
    source = dict(DICTIONARY_CHUNKS[0]["payload"], intent="definition")
    provider = _FakeProvider()
    AnswerSynthesizer(provider, timeout_seconds=0).synthesize_rag("que es turno ok", [source])
    user = provider.messages[1]["content"]
    assert "Diccionario de variables del tablero: TABLERO LAVANDERIA" in user, user
    assert "Página del tablero: DICCIONARIO" not in user
    fallback = readable_fallback([source]) or ""
    assert "Diccionario de variables · TABLERO LAVANDERIA" in fallback, fallback


def test_chunk_builder_marks_dictionary_payload():
    assert _base_metadata({"name": DIC_LAV, "is_dictionary": True})["is_dictionary"] is True
    assert "is_dictionary" not in _base_metadata({"name": "LAVADERIA"})
    assert is_dictionary_source({"metadata": {"is_dictionary": True}})


def _run_all():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, func in tests:
        try:
            func()
            print("PASS ", name)
        except Exception as error:  # noqa: BLE001
            failed += 1
            print("FAIL ", name, "->", type(error).__name__, error)
    print(f"{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())

"""
Pruebas offline del RAG documental: tokenización, intención, alcance
(informe/página), puntaje híbrido, umbral adaptativo, diversidad, síntesis y
resumen extractivo.

Ejecutar:  python -m tests.rag.test_rag_retrieval      (o con pytest)
No usa el modelo de embeddings, Qdrant ni Ollama: el cliente vectorial es un
doble en memoria con cosenos fijados por prueba.
"""
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True

from src.chatbot.answer_synthesizer import NO_EVIDENCE_ANSWER, AnswerSynthesizer
from src.chatbot.rag_answer_engine import RAGAnswerEngine
from src.rag.extractive import readable_fallback, readable_source
from src.rag.ranking import (
    LexicalIndex,
    ScopeIndex,
    detect_question_intent,
    query_terms,
    select_diverse,
    tokenize,
)
from src.rag.retriever import HybridRetriever


# ============================================================
# CORPUS DE PRUEBA (formato real de los chunks)
# ============================================================

def _chunk(point_id, chunk_type, page, group, model, text, aliases=None, measure=None):
    return {
        "id": point_id,
        "payload": {
            "text": text,
            "chunk_type": chunk_type,
            "dashboard": page,
            "dashboard_aliases": aliases or [],
            "source_group": group,
            "semantic_model": model,
            "measure": measure,
            "section": chunk_type,
        },
    }


URG = ("tablero_tiempos_urgencias", "TABLERO TIEMPOS URGENCIAS")
BRI = ("tablero_briefing_hospitalario", "BRIEFING HOSPITALARIO")
LAV = ("tablero_lavanderia", "TABLERO LAVANDERIA")
FAC = ("tablero_control_facturacion", "Tablero Control Facturacion")

CHUNKS = [
    _chunk("u1", "document_section", "TIEMPO TOTAL EN URGENCIAS", *URG,
           "Tablero: TIEMPO TOTAL EN URGENCIAS Sección: DOCUMENTACIÓN ÁREA BOTÓN AZUL Contenido: "
           "El área Botón Azul fue creada como un marcador funcional para analizar los pacientes "
           "identificados como medicina prepagada priorizada."),
    _chunk("u2", "visual", "TIEMPO TOTAL EN URGENCIAS", *URG,
           "Tablero: TIEMPO TOTAL EN URGENCIAS Visualización documentada: Gráfico de líneas – "
           "Tiempo total: Muestra el tiempo total de permanencia en urgencias por mes."),
    _chunk("b1", "dashboard_overview", "URGENCIAS", *BRI,
           "Tablero: URGENCIAS Alias: BRIEFING HOSPITALARIO Descripción: Este tablero muestra los "
           "pacientes que se encuentran en urgencias.", aliases=["BRIEFING HOSPITALARIO"]),
    _chunk("b2", "dashboard_overview", "REPS", *BRI,
           "Tablero: REPS Alias: BRIEFING HOSPITALARIO Descripción: Presenta la capacidad instalada "
           "del hospital: camas, consultorios, salas y sillas.", aliases=["BRIEFING HOSPITALARIO"]),
    _chunk("b3", "calculated_column", "NEDOCS", *BRI,
           "Tablero: NEDOCS Columna calculada: total Tabla: Descripción: Calcula el valor del "
           "indicador NEDOCS a partir de las variables A1, A2, B1, B2, C, D y E. Expresión DAX: "
           "(-20 + 85.8 * ((NEDOCS[A1]) / (NEDOCS[A2]))", aliases=["BRIEFING HOSPITALARIO"]),
    _chunk("l1", "dashboard_overview", "LAVADERIA", *LAV,
           "Tablero: LAVADERIA Alias: LAVANDERIA Descripción: Este tablero monitorea la "
           "distribución del peso de ropa hospitalaria por turno laboral y por mes.",
           aliases=["LAVANDERIA"]),
    _chunk("l2", "documented_measure", "LAVADERIA", *LAV,
           "Tablero: LAVADERIA Medida documentada: TURNO_OK Tabla documentada: LAVANDERIA "
           "Descripción: Expresión documentada: IF(LAVANDERIA[Turno]=1, \"MAÑANA\", "
           "IF(LAVANDERIA[Turno]=2,\"TARDE\", IF(LAVANDERIA[Turno]=3,\"NOCHE\"))) Estado: documentada.",
           aliases=["LAVANDERIA"], measure="TURNO_OK"),
    _chunk("l3", "visual", "LAVADERIA", *LAV,
           "Tablero: LAVADERIA Visualización documentada: Filtros por Años y Mes: Permiten "
           "segmentar la información por Aseguradora, Año y Mes.", aliases=["LAVANDERIA"]),
    _chunk("l4", "sql_query", "LAVADERIA", *LAV,
           "Tablero: LAVADERIA Consulta técnica documentada (parte 1 de 2): SELECT turno, peso, "
           "CASE WHEN turno = 1 THEN 'MAÑANA' END AS turno_ok FROM LAVANDERIA_DIARIA",
           aliases=["LAVANDERIA"]),
    _chunk("f1", "dashboard_overview", "AUDITORÍA MEDICAMENTOS", *FAC,
           "Tablero: AUDITORÍA MEDICAMENTOS Alias: Descripción: Este tablero analiza los tiempos de "
           "gestión de la auditoría de medicamentos.", aliases=["CONTROL FACTURACION"]),
    _chunk("f2", "visual", "AUDITORÍA MEDICAMENTOS", *FAC,
           "Tablero: AUDITORÍA MEDICAMENTOS Visualización documentada: Filtros: Permiten segmentar "
           "la información por Servicio, Año y Mes.", aliases=["CONTROL FACTURACION"]),
    _chunk("f3", "visual", "EN PROCESO AUDITORÍA MEDICAMENTOS", *FAC,
           "Tablero: EN PROCESO AUDITORÍA MEDICAMENTOS Visualización documentada: Semáforo de rangos "
           "de días: clasifica las facturas en los rangos 0 a 7 días, 8 a 30 días y 31 días o más.",
           aliases=["CONTROL FACTURACION"]),
    _chunk("f4", "visual", "FACTURACIÓN PENDIENTE", *FAC,
           "Tablero: FACTURACIÓN PENDIENTE Visualización documentada: Segmentador de atención: "
           "Permite filtrar la información según el área, como ambulatorio o hospitalario.",
           aliases=["CONTROL FACTURACION"]),
    _chunk("f5", "visual", "FACTURACIÓN", *FAC,
           "Tablero: FACTURACIÓN Visualización documentada: Filtros: Permiten segmentar la "
           "información por Servicio, Año y Mes.", aliases=["CONTROL FACTURACION"]),
]


class _FakeModel:
    """encode() devuelve la pregunta; el cliente falso fija el coseno."""

    def encode(self, text, normalize_embeddings=True):
        return SimpleNamespace(tolist=lambda: text)


class _FakeClient:
    def __init__(self, chunks, scores=None, default=0.30):
        self.chunks = chunks
        self.scores = scores or {}
        self.default = default

    def scroll(self, collection_name, limit=10, offset=None, **kwargs):
        start = int(offset or 0)
        page = self.chunks[start:start + limit]
        following = start + limit if start + limit < len(self.chunks) else None
        points = [SimpleNamespace(id=c["id"], payload=dict(c["payload"])) for c in page]
        return points, following

    def query_points(self, collection_name, query=None, query_filter=None, limit=10, **kwargs):
        per_question = self.scores.get(query, {})
        points = [
            SimpleNamespace(
                id=c["id"],
                payload=dict(c["payload"]),
                score=per_question.get(c["id"], self.default),
            )
            for c in self.chunks
        ]
        points.sort(key=lambda p: p.score, reverse=True)
        return SimpleNamespace(points=points[:limit])

    def close(self):
        pass


def make_retriever(scores=None, default=0.30):
    retriever = HybridRetriever.__new__(HybridRetriever)
    retriever.model = _FakeModel()
    retriever.client = _FakeClient(CHUNKS, scores=scores, default=default)
    retriever.collection_name = "test"
    retriever._load_corpus()
    return retriever


# ============================================================
# TOKENS / INTENCIÓN / LÉXICO
# ============================================================

def test_tokenize_normalizes_accents_plurals_and_stopwords():
    assert tokenize("¿Qué muestra el tablero de Lavandería?") == ["tablero", "lavanderia"]
    assert tokenize("las atenciones y los colores") == ["atencion", "color"]
    assert tokenize("triages") == ["triage"]


def test_query_terms_drop_generic_and_scope_words():
    terms = query_terms("que filtros tiene el tablero de lavanderia", exclude={"lavanderia"})
    assert len(terms) == 1 and "segmentador" in terms[0]  # filtro con variantes
    assert query_terms("que es el tablero cvc", exclude={"cvc"}) == []


def test_detect_question_intent():
    assert detect_question_intent("¿Qué muestra el tablero de lavandería?") == "overview"
    assert detect_question_intent("que filtros tiene el tablero de facturacion") == "filters"
    assert detect_question_intent("como se calcula el turno ok en lavanderia") == "calculation"
    assert detect_question_intent("que significan los colores del semaforo") == "definition"
    assert detect_question_intent("que consulta sql usa el tablero de lavanderia") == "technical"
    assert detect_question_intent("dame una receta de arepas") == "general"


def test_lexical_index_phrase_bonus_and_variants():
    index = LexicalIndex([
        tokenize("medida TURNO_OK turno de la mañana"),
        tokenize("turno laboral y peso ok"),
        tokenize("Segmentador de atención por área"),
    ])
    # «noche» no está en ninguno: sin la bonificación ambos valdrían igual.
    phrase = index.score(0, ["turno", "ok", "noche"])
    loose = index.score(1, ["turno", "ok", "noche"])
    assert phrase > loose, (phrase, loose)
    assert index.score(2, query_terms("filtros")) > 0.5


# ============================================================
# ALCANCE (INFORME / PÁGINA)
# ============================================================

def test_scope_prefers_report_over_shorter_page():
    retriever = make_retriever()
    scope = retriever.detect_scope("que es el boton azul en tiempos de urgencias")
    assert scope["kind"] == "report", scope
    assert scope["source_groups"] == ["tablero_tiempos_urgencias"], scope
    # Página principal del informe, no la página URGENCIAS del Briefing.
    assert retriever.detect_dashboard("que es el boton azul en tiempos de urgencias") == (
        "TIEMPO TOTAL EN URGENCIAS"
    )


def test_scope_by_page_and_by_alias():
    retriever = make_retriever()
    page = retriever.detect_scope("que filtros tiene el tablero de facturacion pendiente")
    assert page["kind"] == "page" and page["pages"] == ["FACTURACIÓN PENDIENTE"], page
    report = retriever.detect_scope("que muestra el tablero de lavanderia")
    assert report["kind"] == "report" and report["source_groups"] == ["tablero_lavanderia"]
    assert retriever.detect_dashboard("que muestra el tablero de lavanderia") == "LAVADERIA"
    assert retriever.detect_scope("cual es la capital de francia") is None


def test_scope_index_tie_prefers_report():
    index = ScopeIndex()
    index.add_report_name("tablero_referencia", "TABLERO REFERENCIA")
    index.add_page("tablero_demanda", "REFERENCIA")
    scope = index.detect("que informacion tiene el tablero de referencia")
    assert scope["kind"] == "report" and scope["source_groups"] == ["tablero_referencia"]


# ============================================================
# RANKING HÍBRIDO Y UMBRAL
# ============================================================

def test_named_report_uses_lower_threshold_and_lexical_match():
    question = "que es el boton azul en tiempos de urgencias"
    # Cosenos bajos dentro del tablero (como con el modelo real): el umbral
    # fijo de 0.35 los descartaba todos.
    retriever = make_retriever(scores={question: {"u1": 0.27, "u2": 0.26, "b1": 0.45}})
    # El IntentParser manda la página URGENCIAS del Briefing: se corrige.
    results = retriever.search_general(question, limit=3, dashboard="URGENCIAS")
    assert results, "no debe quedar «no encontré»"
    assert results[0]["text"].startswith("Tablero: TIEMPO TOTAL EN URGENCIAS Sección"), results[0]
    assert all(r["source_group"] == "tablero_tiempos_urgencias" for r in results)


def test_documented_measure_beats_sql_for_calculation():
    question = "como se calcula el turno ok en lavanderia"
    retriever = make_retriever(scores={question: {"l2": 0.15, "l4": 0.55, "l1": 0.57, "l3": 0.57}})
    results = retriever.search_general(question, limit=5)
    assert results[0]["measure"] == "TURNO_OK", [r["chunk_type"] for r in results]
    types = [r["chunk_type"] for r in results]
    assert types.index("documented_measure") < types.index("sql_query") if "sql_query" in types else True


def test_sql_allowed_for_technical_question():
    question = "que consulta sql usa el tablero de lavanderia"
    retriever = make_retriever(scores={question: {"l4": 0.40}})
    results = retriever.search_general(question, limit=2)
    assert results[0]["chunk_type"] == "sql_query", [r["chunk_type"] for r in results]


def test_out_of_scope_rejected_without_lexical_support():
    question = "como va a estar el clima mañana en manizales"
    # Cosenos «ruidosos» de 0.40 contra todo el corpus, sin términos comunes.
    retriever = make_retriever(default=0.40)
    assert retriever.search_general(question, limit=5) == []
    engine = RAGAnswerEngine(retriever=retriever, default_limit=5, min_score=0.35)
    assert engine.answer({"original_question": question})["status"] == "not_found"


def test_page_scope_adds_other_pages_only_for_new_terms():
    question = "que significan los colores del semaforo en auditoria de medicamentos"
    retriever = make_retriever(scores={question: {"f1": 0.41, "f2": 0.49, "f3": 0.29}})
    results = retriever.search_general(question, limit=3)
    pages = [r["dashboard"] for r in results]
    assert results[0]["dashboard"] == "EN PROCESO AUDITORÍA MEDICAMENTOS", pages

    question = "que filtros tiene el tablero de facturacion pendiente"
    retriever = make_retriever(scores={question: {"f4": 0.45, "f5": 0.56, "f2": 0.55}})
    results = retriever.search_general(question, limit=5)
    assert [r["dashboard"] for r in results] == ["FACTURACIÓN PENDIENTE"], results


def test_select_diverse_skips_duplicates_and_limits_sql():
    base = {"dashboard": "P", "section": "s"}
    candidates = [
        dict(base, final_score=0.9, text="a", chunk_type="visual"),
        dict(base, final_score=0.89, text="a", chunk_type="visual"),
        dict(base, final_score=0.8, text="sql 1", chunk_type="sql_query"),
        dict(base, final_score=0.79, text="sql 2", chunk_type="sql_query"),
        dict(base, final_score=0.5, text="b", chunk_type="dashboard_overview"),
    ]
    selected = select_diverse(candidates, limit=5)
    assert [c["text"] for c in selected] == ["a", "sql 1", "b"], selected
    technical = select_diverse(candidates, limit=5, technical=True)
    assert [c["text"] for c in technical].count("sql 2") == 1


# ============================================================
# SÍNTESIS Y RESPUESTA
# ============================================================

class _FakeProvider:
    def __init__(self, answer="ok", delay=0.0, status="success"):
        self.answer = answer
        self.delay = delay
        self.status = status
        self.messages = None

    def chat(self, messages, **kwargs):
        self.messages = messages
        if self.delay:
            time.sleep(self.delay)
        return {"status": self.status, "answer": self.answer, "model": "fake"}


SOURCES = [
    {"text": CHUNKS[6]["payload"]["text"], "chunk_type": "documented_measure",
     "dashboard": "LAVADERIA", "measure": "TURNO_OK", "semantic_model": "TABLERO LAVANDERIA",
     "intent": "calculation"},
    {"text": CHUNKS[5]["payload"]["text"], "chunk_type": "dashboard_overview",
     "dashboard": "LAVADERIA", "semantic_model": "TABLERO LAVANDERIA", "intent": "calculation"},
]


def test_prompt_keeps_markers_and_calculation_task():
    provider = _FakeProvider()
    synthesizer = AnswerSynthesizer(provider, timeout_seconds=0)
    result = synthesizer.synthesize_rag("como se calcula el turno ok", SOURCES)
    assert result["status"] == "success" and result["intent"] == "calculation"
    system, user = provider.messages[0]["content"], provider.messages[1]["content"]
    assert "CONTEXTO RECUPERADO:" in user and "TAREA:" in user
    assert "cítala" in user and "No escribas consultas DAX ni SQL nuevas" in system
    # Fuente principal primero; el resumen del tablero (qué mide) sube justo
    # después aunque el ranking lo dejara al final.
    three = SOURCES + [dict(SOURCES[0], text="Tablero: LAVADERIA Visualización documentada: X: y",
                            chunk_type="visual", measure=None)]
    synthesizer.synthesize_rag("como se calcula el turno ok", [three[0], three[2], three[1]])
    user = provider.messages[1]["content"]
    assert user.index("medida documentada") < user.index("resumen del tablero") < user.index("visualización")


def test_trailing_no_evidence_phrase_is_removed():
    answer = "Los filtros son:\n* Año\n* Mes\n* Servicio de hospitalización y ambulatorio. " + NO_EVIDENCE_ANSWER
    cleaned = AnswerSynthesizer._clean_answer(answer)
    assert NO_EVIDENCE_ANSWER not in cleaned and cleaned.startswith("Los filtros son")
    assert AnswerSynthesizer._clean_answer(NO_EVIDENCE_ANSWER) == NO_EVIDENCE_ANSWER


def test_llm_no_evidence_becomes_not_found():
    retriever = make_retriever(scores={"como se calcula el turno ok en lavanderia": {"l2": 0.15}})
    synthesizer = AnswerSynthesizer(_FakeProvider(answer=NO_EVIDENCE_ANSWER), timeout_seconds=0)
    engine = RAGAnswerEngine(retriever=retriever, answer_synthesizer=synthesizer)
    result = engine.answer({"original_question": "como se calcula el turno ok en lavanderia"})
    assert result["status"] == "not_found", result
    assert result["not_found_reason"] == "llm_no_evidence"


def test_synthesis_timeout_uses_readable_fallback():
    question = "como se calcula el turno ok en lavanderia"
    retriever = make_retriever(scores={question: {"l2": 0.15}})
    synthesizer = AnswerSynthesizer(_FakeProvider(delay=1.0), timeout_seconds=0.1)
    engine = RAGAnswerEngine(retriever=retriever, answer_synthesizer=synthesizer)
    started = time.perf_counter()
    result = engine.answer({"original_question": question})
    assert time.perf_counter() - started < 0.9
    assert result["status"] == "success" and result["synthesis_mode"] == "extractive"
    answer = result["answer"]
    assert "TURNO_OK" in answer and "Tabla documentada" not in answer, answer
    assert "Consulta técnica" not in answer and not answer.startswith("Tablero:"), answer


def test_readable_source_strips_technical_labels():
    measure = {
        "chunk_type": "measure",
        "text": "Tablero: NEDOCS Medida Power BI: TotalN Tabla: NEDOCS Descripción: Tipo de dato: "
                "Number Formato: Expresión DAX oficial del modelo: Calcula el valor consolidado del "
                "indicador NEDOCS. Expresión documentada: (-20 + 85.8 * SUM(NEDOCS[A1]))",
    }
    assert readable_source(measure) == ("TotalN", "Calcula el valor consolidado del indicador NEDOCS")
    column = {"chunk_type": "calculated_column", "text": CHUNKS[4]["payload"]["text"]}
    title, description = readable_source(column)
    assert title == "total" and "A1" in description and "Expresión DAX" not in description
    visual = {"chunk_type": "visual", "text": CHUNKS[11]["payload"]["text"]}
    assert readable_source(visual)[0] == "Semáforo de rangos de días"
    assert readable_source({"chunk_type": "sql_query", "text": CHUNKS[8]["payload"]["text"]}) is None
    assert readable_fallback([{"chunk_type": "sql_query", "text": "SELECT 1"}]) is None


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

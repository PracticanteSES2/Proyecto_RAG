"""Fábrica del motor: arma el QueryEngine con todas sus piezas (retriever,
Power BI, MedGemma, enrutador de modelos, Query Plan…).

Única fuente del cableado que antes vivía en `app.py::build_system`. La usan
`app.py` (Streamlit, legado) y el backend FastAPI
(`backend/app/services/motor.py`). Los arneses de prueba siguen extrayendo
`build_system` de app.py por AST: esa función solo llama a esta fábrica con
las constantes de rutas de su espacio de nombres (que los arneses pueden
sobrescribir, p. ej. `QDRANT_PATH`).
"""
from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from src.chatbot.answer_synthesizer import AnswerSynthesizer
from src.chatbot.conversation_manager import ConversationManager
from src.chatbot.intent_parser import IntentParser
from src.chatbot.option_describer import OptionDescriber
from src.chatbot.query_engine import QueryEngine
from src.chatbot.rag_answer_engine import RAGAnswerEngine
from src.dax.dax_generator import DAXGenerator
from src.dax.master_metric_dax_generator import MasterMetricDAXGenerator
from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator
from src.llm.medgemma_provider import MedGemmaProvider
from src.providers.powerbi_provider import PowerBIProvider
from src.rag.retriever import HybridRetriever
from src.semantic.master_metric_resolver import MasterMetricResolver
from src.semantic.metric_resolver import MetricResolver
from src.semantic.multi_model_components import (
    MultiModelBusinessFilterResolver,
    MultiModelDAXValidator,
    MultiModelFilterResolver,
)
from src.semantic.query_plan_builder import QueryPlanBuilder
from src.semantic.query_semantic_planner import QuerySemanticPlanner
from src.semantic.source_model_router import SourceModelRouter, documentation_dashboards_from_retriever

LOG = logging.getLogger(__name__)


@dataclass
class SistemaMotor:
    engine: object
    conversation_manager: object
    retriever: object
    source_router: object
    medgemma_status: dict = field(default_factory=dict)
    powerbi_connection: dict = field(default_factory=dict)


def rutas_por_defecto(project_root: Path) -> dict:
    raiz = Path(project_root)
    return {
        "qdrant_path": raiz / "data" / "vector_db" / "qdrant",
        "source_registry": raiz / "data" / "catalog" / "source_registry.json",
        "visual_metrics": raiz / "data" / "rag" / "visual_metrics_catalog.json",
        "master_metrics": raiz / "data" / "rag" / "master_metrics.json",
    }


def construir_sistema(project_root, qdrant_path=None, source_registry=None, visual_metrics=None,
                      master_metrics=None, retriever=None) -> SistemaMotor:
    """Arma el motor. `retriever` permite compartir uno ya abierto (Qdrant local
    admite un solo cliente por carpeta y por proceso)."""
    project_root = Path(project_root)
    defecto = rutas_por_defecto(project_root)
    qdrant_path = qdrant_path or defecto["qdrant_path"]
    source_registry = source_registry or defecto["source_registry"]
    visual_metrics = visual_metrics or defecto["visual_metrics"]
    master_metrics = master_metrics or defecto["master_metrics"]

    if retriever is None:
        retriever = HybridRetriever(qdrant_path)
    intent_parser = IntentParser(retriever)
    conversation_manager = ConversationManager(intent_parser)
    metric_resolver = MetricResolver(retriever, debug=False)
    powerbi_provider = PowerBIProvider()
    # Conservamos la conexión inicial que ya estaba estable.
    powerbi_connection = powerbi_provider.connect()
    modelo_defecto = powerbi_provider.default_semantic_model
    source_router = SourceModelRouter(
        source_registry_path=source_registry, visual_catalog_path=visual_metrics,
        project_root=project_root, default_semantic_model=modelo_defecto,
    )
    # El analizador de intención reconoce los tableros también por los alias
    # del registro de fuentes («tablero de lavandería»).
    intent_parser.source_router = source_router
    # Tableros documentados («TRIAGE», «CIRUGÍAS») con su grupo de fuentes.
    source_router.register_documentation_dashboards(documentation_dashboards_from_retriever(retriever))
    filter_resolver = MultiModelFilterResolver(source_router=source_router, default_semantic_model=modelo_defecto)
    business_filter_resolver = MultiModelBusinessFilterResolver(
        source_router=source_router, powerbi_provider=powerbi_provider, default_semantic_model=modelo_defecto,
    )
    dax_validator = MultiModelDAXValidator(source_router=source_router, default_semantic_model=modelo_defecto)
    medgemma_provider = MedGemmaProvider()
    medgemma_status = medgemma_provider.healthcheck()
    master_metric_resolver = MasterMetricResolver(master_metrics)
    query_semantic_planner = QuerySemanticPlanner(
        master_metric_resolver=master_metric_resolver, business_filter_resolver=business_filter_resolver,
        powerbi_provider=powerbi_provider, source_router=source_router,
    )
    query_plan_builder = QueryPlanBuilder(
        master_metrics_path=master_metrics, visual_catalog_path=visual_metrics, source_router=source_router,
        powerbi_provider=powerbi_provider, project_root=project_root,
    )
    listo = (medgemma_status or {}).get("status") == "ready"
    if listo and callable(getattr(medgemma_provider, "warmup", None)):
        medgemma_provider.warmup()
    answer_synthesizer = AnswerSynthesizer(llm_provider=medgemma_provider, max_sources=5, max_context_chars=7000)
    rag_answer_engine = RAGAnswerEngine(
        retriever=retriever, answer_synthesizer=answer_synthesizer, default_limit=5, min_score=0.35,
    )
    engine = QueryEngine(
        conversation_manager=conversation_manager, metric_resolver=metric_resolver,
        filter_resolver=filter_resolver, business_filter_resolver=business_filter_resolver,
        dax_generator=DAXGenerator(), dax_validator=dax_validator, powerbi_provider=powerbi_provider,
        rag_answer_engine=rag_answer_engine, master_metric_resolver=master_metric_resolver,
        master_metric_dax_generator=MasterMetricDAXGenerator(), query_semantic_planner=query_semantic_planner,
        source_router=source_router, query_plan_builder=query_plan_builder,
        query_plan_dax_generator=QueryPlanDAXGenerator(),
        # MedGemma describe en una frase qué consultaría cada opción.
        option_describer=OptionDescriber(medgemma_provider) if listo else None,
    )
    _precalentar_portero(engine)
    LOG.info("Motor listo · modelos semánticos enrutables: %s", source_router.semantic_models())
    return SistemaMotor(engine=engine, conversation_manager=conversation_manager, retriever=retriever,
                        source_router=source_router, medgemma_status=medgemma_status or {},
                        powerbi_connection=powerbi_connection or {})


def _precalentar_portero(engine) -> None:
    """Portero conversacional precalentado (similitud MiniLM y catálogo): el
    primer «hola» no paga su construcción. Un fallo no impide arrancar."""
    try:
        warm_up = getattr(engine, "warm_up_portero", None)
        if callable(warm_up):
            warm_up()
    except Exception:
        traceback.print_exc()

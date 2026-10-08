from pathlib import Path
import traceback
import streamlit as st

from src.rag.retriever import HybridRetriever
from src.chatbot.intent_parser import IntentParser
from src.chatbot.conversation_manager import ConversationManager
from src.chatbot.query_engine import QueryEngine
from src.chatbot.rag_answer_engine import RAGAnswerEngine
from src.chatbot.answer_synthesizer import AnswerSynthesizer
from src.chatbot.response_formatter import ResponseFormatter
from src.semantic.metric_resolver import MetricResolver
from src.dax.dax_generator import DAXGenerator
from src.semantic.source_model_router import (
    SourceModelRouter,
)
from src.semantic.multi_model_components import (
    MultiModelFilterResolver,
    MultiModelBusinessFilterResolver,
    MultiModelDAXValidator,
)
from src.providers.powerbi_provider import PowerBIProvider
from src.llm.ollama_provider import OllamaProvider
from src.semantic.query_semantic_planner import (
    QuerySemanticPlanner
)
from src.semantic.master_metric_resolver import (
    MasterMetricResolver
)
from src.dax.master_metric_dax_generator import (
    MasterMetricDAXGenerator
)
from src.semantic.query_plan_builder import (
    QueryPlanBuilder,
)
from src.dax.query_plan_dax_generator import (
    QueryPlanDAXGenerator,
)

PROJECT_ROOT = Path(__file__).resolve().parent
QDRANT_PATH = PROJECT_ROOT / "data" / "vector_db" / "qdrant"
SOURCE_REGISTRY = (
    PROJECT_ROOT
    / "data"
    / "catalog"
    / "source_registry.json"
)
VISUAL_METRICS = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "visual_metrics_catalog.json"
)
MASTER_METRICS = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "master_metrics.json"
)

@st.cache_resource
def build_system():
    retriever = HybridRetriever(QDRANT_PATH)
    intent_parser = IntentParser(retriever)
    conversation_manager = ConversationManager(intent_parser)
    metric_resolver = MetricResolver(retriever, debug=False)

    powerbi_provider = PowerBIProvider()

    # Conservamos la conexión inicial que ya estaba estable.
    powerbi_connection = (
        powerbi_provider.connect()
    )

    source_router = SourceModelRouter(
        source_registry_path=
            SOURCE_REGISTRY,
        visual_catalog_path=
            VISUAL_METRICS,
        project_root=
            PROJECT_ROOT,
        default_semantic_model=
            powerbi_provider
            .default_semantic_model,
    )

    filter_resolver = (
        MultiModelFilterResolver(
            source_router=
                source_router,
            default_semantic_model=
                powerbi_provider
                .default_semantic_model,
        )
    )

    business_filter_resolver = (
        MultiModelBusinessFilterResolver(
            source_router=
                source_router,
            powerbi_provider=
                powerbi_provider,
            default_semantic_model=
                powerbi_provider
                .default_semantic_model,
        )
    )

    dax_validator = (
        MultiModelDAXValidator(
            source_router=
                source_router,
            default_semantic_model=
                powerbi_provider
                .default_semantic_model,
        )
    )

    ollama_provider = OllamaProvider()
    ollama_status = ollama_provider.healthcheck()
    master_metric_resolver = (
        MasterMetricResolver(
            MASTER_METRICS
        )
    )

    master_metric_dax_generator = (
        MasterMetricDAXGenerator()
    )

    query_semantic_planner = (
        QuerySemanticPlanner(
            master_metric_resolver=
                master_metric_resolver,
            business_filter_resolver=
                business_filter_resolver,
            powerbi_provider=
                powerbi_provider,
            source_router=
                source_router,
        )
    )

    query_plan_builder = (
        QueryPlanBuilder(
            master_metrics_path=
                MASTER_METRICS,
            visual_catalog_path=
                VISUAL_METRICS,
            source_router=
                source_router,
            powerbi_provider=
                powerbi_provider,
            project_root=
                PROJECT_ROOT,
        )
    )

    query_plan_dax_generator = (
        QueryPlanDAXGenerator()
    )

    if ollama_status.get("status") == "ready":
        warmup = getattr(ollama_provider, "warmup", None)
        if callable(warmup):
            warmup()
    answer_synthesizer = AnswerSynthesizer(llm_provider=ollama_provider, max_sources=3, max_context_chars=5000)
    rag_answer_engine = RAGAnswerEngine(
        retriever=retriever,
        answer_synthesizer=answer_synthesizer,
        default_limit=3,
        min_score=0.35,
    )
    engine = QueryEngine(
        conversation_manager=conversation_manager,
        metric_resolver=metric_resolver,
        filter_resolver=filter_resolver,
        business_filter_resolver=business_filter_resolver,
        dax_generator=DAXGenerator(),
        dax_validator=dax_validator,
        powerbi_provider=powerbi_provider,
        rag_answer_engine=rag_answer_engine,
        master_metric_resolver=master_metric_resolver,
        master_metric_dax_generator=master_metric_dax_generator,
        query_semantic_planner=query_semantic_planner,
        source_router=source_router,
        query_plan_builder=query_plan_builder,
        query_plan_dax_generator=query_plan_dax_generator,
    )

    print("--------------------------------------------------------------------------------------")

    print(
        "\nMASTER METRICS:",
        MASTER_METRICS.resolve()
    )

    print(
        "MASTER RESOLVER ACTIVO:",
        type(
            engine.master_metric_resolver
        ).__name__
    )

    print(
        "QUERY ENGINE:",
        engine.__class__
    )

    print(
        "MODELOS SEMÁNTICOS ENRUTABLES:",
        source_router.semantic_models()
    )
    return engine, conversation_manager, ResponseFormatter(), ollama_status, powerbi_connection

def get_display_answer(result, formatter):
    status = result.get("status")
    route = result.get("route")
    if status == "needs_clarification":
        return result.get("question") or "Necesito una aclaración para continuar."
    if status == "not_found":
        return result.get("answer") or "No encontré información relacionada con esa pregunta."
    if route == "rag":
        return result.get("answer") or "No encontré información suficiente."
    if route == "powerbi" and status == "success":
        if (
            result.get("result_type")
            == "table"
            and result.get("answer")
        ):
            return result.get("answer")

        # Query Plan conoce exactamente la métrica y el modelo. Evitar
        # presentar resultados con textos/periodos heredados de otra ruta.
        if result.get("query_plan"):
            return f"{result.get('metric')}: {result.get('value')}"

        try:
            answer = formatter.format(result)
            if answer:
                return answer
        except Exception:
            pass

        metric = result.get("metric")
        value = result.get("value")

        if metric:
            return f"{metric}: {value}"

        return f"El resultado consultado en Power BI es {value}."
    if status == "metric_not_resolved":
        return "No encontré un indicador suficientemente específico. Incluye la sección o página del tablero."
    if status == "unsupported_filter":
        details = result.get("details", {})
        reason = details.get("reason")
        if reason == "requested_value_not_found":
            return "Identifiqué la métrica, pero no pude verificar el valor del filtro solicitado."
        if reason == "date_dimension_not_found_in_report":
            return "Identifiqué la métrica, pero no encontré una fecha validada para aplicar ese período."
        return "Identifiqué la métrica, pero no pude verificar la dimensión solicitada en este tablero."
    if status == "powerbi_error":
        return "La métrica se identificó, pero Power BI rechazó la consulta. Revisa Modo diagnóstico."
    if status == "empty_result":
        return "Power BI ejecutó la consulta, pero no devolvió datos para los criterios solicitados."
    return "No pude completar la consulta. Activa Modo diagnóstico para ver en qué etapa falló."

def reset_if_finished(result, engine, conversation_manager):
    # Solo conservamos contexto mientras hay una contrapregunta pendiente.
    if result.get("status") == "needs_clarification":
        return
    conversation_manager.reset()
    reset_method = getattr(engine, "reset", None)
    if callable(reset_method):
        reset_method()

st.set_page_config(page_title="Asistente de Gestión Clínica", page_icon="📊", layout="centered")
st.title("📊 Asistente de Gestión Clínica")
st.caption("Consultas sobre tableros institucionales con RAG, Power BI y Qwen local.")

engine, conversation_manager, formatter, ollama_status, powerbi_connection = build_system()

with st.sidebar:
    st.subheader("Estado del sistema")
    if ollama_status.get("status") == "ready":
        st.success("Qwen local: disponible")
    else:
        st.warning("Qwen local: no disponible")
    if (
        powerbi_connection.get(
            "status"
        )
        == "success"
    ):

        st.success(
            "Power BI: conectado"
        )

    else:

        st.warning(
            "Power BI: no conectado"
        )
    debug_mode = st.checkbox("Modo diagnóstico", value=False)
    st.info("El asistente responde únicamente con información respaldada por los tableros y documentos disponibles.")
    if st.button("Nueva conversación", use_container_width=True):
        conversation_manager.reset()

        reset_method = getattr(
            engine,
            "reset",
            None,
        )

        if callable(reset_method):
            reset_method()

        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hola. Puedes preguntarme por indicadores, filtros y datos disponibles en los tableros institucionales."}]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Escribe tu pregunta...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        error_text = None
        with st.spinner("Consultando información..."):
            try:
                result = engine.process(prompt)
                answer = get_display_answer(result, formatter)
            except Exception as exc:
                traceback.print_exc()
                error_text = f"{type(exc).__name__}: {exc}"
                result = {"status": "error", "route": None, "error": error_text}
                answer = "Ocurrió un error al procesar la consulta. Intenta nuevamente."

        st.markdown(answer)

        if result.get("status") == "success":
            with st.expander("Detalles de la consulta", expanded=False):
                st.write("**Ruta:**", result.get("route", "sin ruta"))
                if result.get("report"):
                    st.write("**Informe:**", result.get("report"))
                if result.get("dashboard"):
                    st.write("**Tablero/Página:**", result.get("dashboard"))
                if result.get("semantic_model"):
                    st.write("**Modelo semántico:**", result.get("semantic_model"))
                if result.get("metric"):
                    st.write("**Métrica:**", result.get("metric"))
                if result.get("synthesis_mode"):
                    st.write("**Síntesis:**", result.get("synthesis_mode"))
        elif result.get("status") == "not_found":
            st.caption("Consulta fuera del alcance de la documentación disponible.")

        if debug_mode:
            st.write("**Estado:**", result.get("status"))
            if result.get("stage"):
                st.write("**Etapa:**", result.get("stage"))
            if result.get("details"):
                st.write("**Detalles del diagnóstico:**", result.get("details"))
            if result.get("error"):
                st.write("**Error:**", result.get("error"))

            if error_text:
                st.error(error_text)

            if result.get("source_context"):
                st.write(
                    "**Contexto multi-modelo:**",
                    result.get(
                        "source_context"
                    ),
                )

            if result.get("query_plan"):
                st.write(
                    "**Query Plan:**",
                    result.get(
                        "query_plan"
                    ),
                )

            if result.get("group_by"):
                st.write(
                    "**Agrupaciones:**",
                    result.get(
                        "group_by"
                    ),
                )


            if result.get("dimension_matches"):
                st.write(
                    "**Dimensiones detectadas:**",
                    result.get(
                        "dimension_matches"
                    ),
                )

            if result.get("business_filters"):
                st.write(
                    "**Filtros de negocio:**",
                    result.get(
                        "business_filters"
                    ),
                )

            if result.get("dax"):
                st.code(
                    result.get("dax"),
                    language="text",
                )

    st.session_state.messages.append({"role": "assistant", "content": answer})
    reset_if_finished(result, engine, conversation_manager)

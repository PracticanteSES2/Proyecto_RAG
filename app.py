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
from src.semantic.filter_resolver import FilterResolver
from src.semantic.business_filter_resolver import BusinessFilterResolver
from src.dax.dax_generator import DAXGenerator
from src.dax.dax_validator import DAXValidator
from src.providers.powerbi_provider import PowerBIProvider
from src.llm.ollama_provider import OllamaProvider

from src.semantic.master_metric_resolver import (MasterMetricResolver)
from src.dax.master_metric_dax_generator import (MasterMetricDAXGenerator)

PROJECT_ROOT = Path(__file__).resolve().parent
QDRANT_PATH = PROJECT_ROOT / "data" / "vector_db" / "qdrant"
TECHNICAL_CATALOG = PROJECT_ROOT / "data" / "catalog" / "tablero_de_atenciones_institucionales_rag.json"
CERTIFIED_METRICS = (
    PROJECT_ROOT
    / "data"
    / "catalog"
    / "certified_metrics.json"
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
    filter_resolver = FilterResolver(TECHNICAL_CATALOG)
    powerbi_provider = PowerBIProvider()
    business_filter_resolver = BusinessFilterResolver(TECHNICAL_CATALOG, powerbi_provider)
    ollama_provider = OllamaProvider()
    ollama_status = ollama_provider.healthcheck()
    master_metric_resolver = (MasterMetricResolver(MASTER_METRICS))
    master_metric_dax_generator = (MasterMetricDAXGenerator())

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
        dax_validator=DAXValidator(TECHNICAL_CATALOG),
        powerbi_provider=powerbi_provider,
        rag_answer_engine=rag_answer_engine,
        master_metric_resolver=master_metric_resolver,
        master_metric_dax_generator=master_metric_dax_generator,
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
    return engine, conversation_manager, ResponseFormatter(), ollama_status

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
        try:
            answer = formatter.format(result)
            if answer:
                return answer
        except Exception:
            pass
        return f"El resultado consultado en Power BI es {result.get('value')}."
    if status == "metric_not_resolved":
        return "No pude identificar con suficiente seguridad el indicador solicitado."
    return "No pude completar la consulta. Puedes reformularla o intentar nuevamente."

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

engine, conversation_manager, formatter, ollama_status = build_system()

with st.sidebar:
    st.subheader("Estado del sistema")
    if ollama_status.get("status") == "ready":
        st.success("Qwen local: disponible")
    else:
        st.warning("Qwen local: no disponible")
    debug_mode = st.checkbox("Modo diagnóstico", value=False)
    st.info("El asistente responde únicamente con información respaldada por los tableros y documentos disponibles.")
    if st.button("Nueva conversación", use_container_width=True):
        conversation_manager.reset()
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
                if result.get("dashboard"):
                    st.write("**Tablero:**", result.get("dashboard"))
                if result.get("metric"):
                    st.write("**Métrica:**", result.get("metric"))
                if result.get("synthesis_mode"):
                    st.write("**Síntesis:**", result.get("synthesis_mode"))
        elif result.get("status") == "not_found":
            st.caption("Consulta fuera del alcance de la documentación disponible.")

        if debug_mode and error_text:
            st.error(error_text)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    reset_if_finished(result, engine, conversation_manager)

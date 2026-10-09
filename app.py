from pathlib import Path
import traceback

# Variables de entorno (OLLAMA_*, Power BI...) antes de importar src.*.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

import streamlit as st

from src.rag.retriever import HybridRetriever
from src.chatbot.intent_parser import IntentParser
from src.chatbot.conversation_manager import ConversationManager
from src.chatbot.query_engine import QueryEngine
from src.chatbot.rag_answer_engine import RAGAnswerEngine
from src.chatbot.answer_synthesizer import AnswerSynthesizer
from src.chatbot.option_describer import OptionDescriber
from src.chatbot.reasoning_trace import format_reasoning_text
from src.chatbot.response_formatter import (
    ResponseFormatter,
    clarification_buttons,
    clarification_prompt,
    format_filters_line,
    format_query_plan_answer,
    format_unapplied_line,
)
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
from src.llm.medgemma_provider import MedGemmaProvider
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

    medgemma_provider = MedGemmaProvider()
    medgemma_status = medgemma_provider.healthcheck()
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

    if medgemma_status.get("status") == "ready":
        warmup = getattr(medgemma_provider, "warmup", None)
        if callable(warmup):
            warmup()
    answer_synthesizer = AnswerSynthesizer(llm_provider=medgemma_provider, max_sources=3, max_context_chars=5000)
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
        # MedGemma describe en una frase qué consultaría cada opción.
        option_describer=(
            OptionDescriber(medgemma_provider)
            if medgemma_status.get("status") == "ready"
            else None
        ),
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
    return engine, conversation_manager, ResponseFormatter(), medgemma_status, powerbi_connection

def get_display_answer(result, formatter):
    status = result.get("status")
    route = result.get("route")
    if status == "needs_clarification":
        return clarification_prompt(result)
    if status == "not_found":
        return result.get("answer") or "No encontré información relacionada con esa pregunta."
    if route == "rag":
        return result.get("answer") or "No encontré información suficiente."
    if route == "powerbi" and status == "success":
        # Query Plan conoce exactamente la métrica y el modelo. Evitar
        # presentar resultados con textos/periodos heredados de otra ruta.
        if result.get("query_plan"):
            return format_query_plan_answer(result)

        if (
            result.get("result_type")
            == "table"
            and result.get("answer")
        ):
            return result.get("answer")

        try:
            answer = formatter.format(result)
            if answer and "None" not in answer:
                return answer
        except Exception:
            pass

        metric = result.get("metric")
        value = result.get("value")

        if value is None:
            return "No hay datos para esos filtros."

        if metric:
            return f"{metric}: {value}"

        return f"El resultado consultado en Power BI es {value}."
    if status == "metric_not_resolved":
        return "No encontré un indicador suficientemente específico. Incluye la sección o página del tablero."
    if status == "unsupported_filter":
        details = result.get("details", {})
        reason = details.get("reason")
        if result.get("powerbi_unavailable") or details.get("domain_error"):
            return (
                "Identifiqué la métrica, pero no pude consultar Power BI para "
                "verificar el filtro solicitado. Revisa que Power BI esté "
                "disponible e intenta de nuevo."
            )
        if reason == "requested_value_not_found":
            return "Identifiqué la métrica, pero no pude verificar el valor del filtro solicitado."
        if reason == "date_dimension_not_found_in_report":
            return "Identifiqué la métrica, pero no encontré una fecha validada para aplicar ese período."
        return "Identifiqué la métrica, pero no pude verificar la dimensión solicitada en este tablero."
    if status == "powerbi_error":
        return "La métrica se identificó, pero Power BI rechazó la consulta. Revisa Modo diagnóstico."
    if status == "empty_result":
        plan = result.get("query_plan") or {}
        extras = [
            line
            for line in (
                format_filters_line(result.get("filters") or plan.get("filters")),
                format_unapplied_line(
                    result.get("unapplied_terms") or plan.get("unapplied_terms")
                ),
            )
            if line
        ]
        return "\n\n".join(["No hay datos para esos filtros."] + extras)
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

engine, conversation_manager, formatter, medgemma_status, powerbi_connection = build_system()

def clear_pending_clarification():
    st.session_state.pending_clarification = None
    st.session_state.queued_option = None


def queue_option(option_id, label):
    # Callback de st.button: se ejecuta antes del rerun; el turno se procesa
    # en el siguiente pase del script.
    st.session_state.queued_option = {"id": option_id, "label": label}


def render_clarification_buttons(pending):
    # Un botón por opción, con su descripción corta debajo.
    for index, button in enumerate(pending["buttons"]):
        st.button(
            button["label"],
            key=f"clarification_{pending['id']}_{index}",
            on_click=queue_option,
            args=(button["id"], button["label"]),
            use_container_width=True,
        )
        if button.get("caption"):
            st.caption(button["caption"])


def render_past_options(buttons):
    # Contrapregunta ya respondida o abandonada: las opciones quedan como
    # referencia, sin botones.
    st.caption("Opciones: " + " · ".join(button["label"] for button in buttons))


def render_reasoning(text):
    # Qué revisó el asistente y cómo decidió; el bloque de código trae botón
    # de copiar para compartirlo cuando una respuesta falla.
    if not text:
        return
    with st.expander("🧠 Razonamiento del asistente", expanded=False):
        st.caption("Qué revisó y cómo tomó cada decisión. Cópialo con el botón del recuadro para compartirlo.")
        try:
            st.code(text, language="text", wrap_lines=True)
        except TypeError:  # Streamlit sin wrap_lines
            st.code(text, language="text")


def execute_turn(user_text, runner):
    st.session_state.pending_clarification = None
    st.session_state.queued_option = None
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    with st.chat_message("assistant"):
        error_text = None
        with st.spinner("Consultando información..."):
            try:
                result = runner()
                answer = get_display_answer(result, formatter)
            except Exception as exc:
                traceback.print_exc()
                error_text = f"{type(exc).__name__}: {exc}"
                result = {
                    "status": "error", "route": None, "error": error_text,
                    "reasoning": getattr(engine, "last_reasoning", None),
                }
                answer = "Ocurrió un error al procesar la consulta. Intenta nuevamente."

        st.markdown(answer)

        buttons = clarification_buttons(result)
        clarification_id = None
        if buttons:
            st.session_state.clarification_counter += 1
            clarification_id = st.session_state.clarification_counter
            st.session_state.pending_clarification = {
                "id": clarification_id,
                "buttons": buttons,
            }
            render_clarification_buttons(st.session_state.pending_clarification)

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
        elif result.get("status") == "not_found" and result.get("route") == "out_of_scope":
            st.caption("Consulta fuera del alcance de la documentación disponible.")

        reasoning_text = format_reasoning_text(result.get("reasoning"), answer)
        render_reasoning(reasoning_text)

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

    st.session_state.messages.append({
        "role": "assistant", "content": answer,
        "buttons": buttons, "clarification_id": clarification_id,
        "reasoning": reasoning_text,
    })
    reset_if_finished(result, engine, conversation_manager)


with st.sidebar:
    st.subheader("Estado del sistema")
    if medgemma_status.get("status") == "ready":
        st.success("MedGemma: disponible")
    else:
        st.warning("MedGemma: no disponible")
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
        clear_pending_clarification()
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hola. Puedes preguntarme por indicadores, filtros y datos disponibles en los tableros institucionales."}]
if "pending_clarification" not in st.session_state:
    st.session_state.pending_clarification = None
if "queued_option" not in st.session_state:
    st.session_state.queued_option = None
if "clarification_counter" not in st.session_state:
    st.session_state.clarification_counter = 0

# st.chat_input queda fijo abajo aunque se llame antes del historial; se lee
# primero para saber si la contrapregunta vigente sigue activa en este pase.
prompt = st.chat_input("Escribe tu pregunta...")
queued = st.session_state.queued_option
pending = st.session_state.pending_clarification
active_id = pending["id"] if pending and not prompt and not queued else None

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("buttons"):
            if message.get("clarification_id") == active_id:
                # Rerun por otro widget: botones de la contrapregunta vigente.
                render_clarification_buttons(pending)
            else:
                render_past_options(message["buttons"])
        render_reasoning(message.get("reasoning"))

if prompt:
    execute_turn(prompt, lambda: engine.process(prompt))
elif queued:
    execute_turn(
        queued["label"],
        lambda: engine.select_clarification_option(queued["id"], queued["label"]),
    )

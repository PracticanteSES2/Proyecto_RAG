from pathlib import Path
import html
import json
import time
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
from src.chatbot.runtime_stats import (
    STATS,
    TurnBusy,
    diagnostics_lines,
    status_line,
    turn_slot,
)
from src.chatbot.conversation_export import (
    export_conversation_markdown,
    export_file_name,
)
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
    documentation_dashboards_from_retriever,
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

    # El analizador de intención reconoce los tableros también por los
    # alias del registro de fuentes («tablero de lavandería»).
    intent_parser.source_router = source_router

    # Tableros documentados («TRIAGE», «CIRUGÍAS») con su grupo de fuentes:
    # «tablero de triage» fija el informe correcto aunque esa página no esté
    # en el catálogo visual.
    source_router.register_documentation_dashboards(
        documentation_dashboards_from_retriever(retriever)
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
    answer_synthesizer = AnswerSynthesizer(llm_provider=medgemma_provider, max_sources=5, max_context_chars=7000)
    rag_answer_engine = RAGAnswerEngine(
        retriever=retriever,
        answer_synthesizer=answer_synthesizer,
        default_limit=5,
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
        # El motor redacta el mensaje (pregunta genérica / indicador no
        # identificado, con ejemplos reales del catálogo).
        return result.get("answer") or (
            "No identifiqué el indicador que buscas. Escribe el nombre del "
            "indicador o del tablero donde lo ves."
        )
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
            if details.get("explanation"):
                # «CANTIDAD DE PACIENTES muestra el estado actual de ...»
                return details["explanation"]
            period = details.get("requested_period")
            if period:
                return (
                    "Identifiqué la métrica, pero este tablero no tiene una fecha que permita "
                    f"aplicar el período «{period}». Prueba con un año o un mes."
                )
            return "Identifiqué la métrica, pero no encontré una fecha validada para aplicar ese período."
        if reason == "requested_dimension_not_found_in_report" and details.get("explanation"):
            # «%OCUPACION no se puede desglosar por aseguradores: su tabla ...»
            return details["explanation"]
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
    # engine.reset() (sin full=True) conserva a propósito la última consulta
    # numérica exitosa para seguimientos como «¿y en 2025?».
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


# Segundos sin ningún paso nuevo tras los que el reloj avisa de posible bloqueo.
STALL_WARNING_SECONDS = 45


def render_live_clock(placeholder, started_at, step_started_at, step_title):
    """Reloj que corre en el NAVEGADOR: sigue avanzando aunque Python esté
    bloqueado esperando a Power BI o a MedGemma, para distinguir lentitud de
    un proceso pegado."""
    # Texto del paso como literal JS seguro (sin «</script>» posible).
    title = json.dumps(step_title or "").replace("<", chr(92) + "u003c")
    page = f"""
<div id="clock" style="font-family: sans-serif; font-size: 13px; color: #555;"></div>
<script>
const start = {started_at * 1000:.0f}, stepStart = {step_started_at * 1000:.0f};
const step = {title}, stall = {STALL_WARNING_SECONDS};
const el = document.getElementById("clock");
function tick() {{
  const now = Date.now();
  const total = ((now - start) / 1000).toFixed(0);
  const inStep = ((now - stepStart) / 1000).toFixed(0);
  let text = "⏱ " + total + " s en total · paso actual: " + step + " (" + inStep + " s)";
  if (inStep > stall) {{
    text += " · ⚠ sin avances hace " + inStep + " s: puede estar lento o bloqueado en este paso";
    el.style.color = "#b45309";
  }}
  el.textContent = text;
}}
tick(); setInterval(tick, 500);
</script>
"""
    with placeholder.container():
        if hasattr(st, "iframe"):
            st.iframe(page, height=28)
        else:  # Streamlit anterior
            import streamlit.components.v1 as components

            components.html(page, height=28)


class LiveProgress:
    """Muestra en vivo los pasos del turno dentro de un st.status."""

    def __init__(self):
        self.started_at = time.time()
        self.status = st.status("Pensando… interpretando la pregunta", expanded=True)
        self.clock = st.empty()
        self.steps = 0
        self.queries = 0
        self.waiting_shown = False
        render_live_clock(self.clock, self.started_at, self.started_at, "inicio")

    def waiting(self, waited, holder_for=None):
        """Otro turno (otra pestaña o una ejecución anterior aún bloqueada)
        tiene el motor: se avisa en vivo mientras se espera."""
        since = holder_for if holder_for is not None else waited
        label = f"Esperando a que termine otra consulta en curso (desde hace {since:.0f} s)"
        self.status.update(label=f"Pensando… {label}")
        if not self.waiting_shown:
            self.waiting_shown = True
            self.status.markdown(f"⏳ {html.escape(label)}", unsafe_allow_html=True)
            render_live_clock(self.clock, self.started_at, time.time(), "esperando turno")

    def on_event(self, event):
        title = str(event.get("title") or "")
        seconds = float(event.get("t") or 0.0)
        if event.get("kind") == "activity":
            if title.startswith("Consultando Power BI"):
                self.queries += 1
            detail = (event.get("lines") or [""])[0]
            line = f"`{seconds:5.1f} s` ⏳ {html.escape(title)}"
            if detail:
                line += f" — <small>{html.escape(detail)}</small>"
            self.status.markdown(line, unsafe_allow_html=True)
            self.status.update(label=f"Pensando… {title}")
            render_live_clock(self.clock, self.started_at, time.time(), title)
            return
        self.steps += 1
        self.status.markdown(f"`{seconds:5.1f} s` ✔ {html.escape(title)}", unsafe_allow_html=True)

    def finish(self, error=False):
        elapsed = time.time() - self.started_at
        self.clock.empty()
        summary = f"{elapsed:.1f} s · {self.steps} pasos"
        if self.queries:
            summary += f" · {self.queries} consulta{'s' if self.queries != 1 else ''} a Power BI"
        if error:
            self.status.update(label=f"Error tras {summary}", state="error", expanded=True)
        else:
            self.status.update(label=f"Listo en {summary}", state="complete", expanded=False)


def execute_turn(user_text, runner, via="texto"):
    st.session_state.pending_clarification = None
    st.session_state.queued_option = None
    st.session_state.messages.append({"role": "user", "content": user_text, "via": via})
    with st.chat_message("user"):
        st.markdown(user_text)

    with st.chat_message("assistant"):
        error_text = None
        # Pasos en vivo (qué está haciendo y desde hace cuánto) en lugar de
        # un spinner mudo: así se distingue lentitud de un proceso pegado.
        live = LiveProgress()
        set_listener = getattr(engine, "set_progress_listener", None)
        try:
            # Un turno a la vez: el motor es un único objeto con estado por
            # turno. El candado se libera siempre, también si Streamlit aborta
            # esta ejecución (StopException/RerunException son BaseException).
            with turn_slot(user_text, on_wait=live.waiting):
                if callable(set_listener):
                    set_listener(live.on_event)
                try:
                    try:
                        result = runner()
                    except Exception as exc:
                        traceback.print_exc()
                        error_text = f"{type(exc).__name__}: {exc}"
                        result = {
                            "status": "error", "route": None, "error": error_text,
                            "reasoning": getattr(engine, "last_reasoning", None),
                        }
                    # Dentro del candado: también modifica el estado del motor.
                    reset_if_finished(result, engine, conversation_manager)
                finally:
                    if callable(set_listener):
                        set_listener(None)
            if not error_text:
                try:
                    answer = get_display_answer(result, formatter)
                except Exception as exc:
                    traceback.print_exc()
                    error_text = f"{type(exc).__name__}: {exc}"
            if error_text:
                answer = "Ocurrió un error al procesar la consulta. Intenta nuevamente."
                live.finish(error=True)
            else:
                live.finish()
        except TurnBusy as busy:
            holder = busy.holder or {}
            since = time.time() - holder["since"] if holder.get("since") else busy.waited_s
            error_text = str(busy)
            result = {"status": "busy", "route": None, "error": error_text, "reasoning": None}
            answer = (
                f"Hay otra consulta en curso desde hace {since:.0f} s (puede ser de otra pestaña "
                "o de una pregunta anterior) y no terminó a tiempo. Espera a que termine y vuelve "
                "a intentarlo."
            )
            live.finish(error=True)

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
        "status": result.get("status"), "route": result.get("route"),
    })


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
        try:
            # El motor no se reinicia en medio de otro turno.
            with turn_slot("Nueva conversación", max_wait=5):
                conversation_manager.reset()

                reset_method = getattr(
                    engine,
                    "reset",
                    None,
                )

                if callable(reset_method):
                    # full=True: también olvida el contexto de seguimiento.
                    reset_method(full=True)
        except TurnBusy:
            st.session_state.notice = (
                "Había otra consulta en curso: el historial se borró, pero el contexto "
                "del asistente no. Pulsa «Nueva conversación» otra vez cuando termine."
            )

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
        via="botón",
    )


@st.cache_resource
def code_version():
    # Commit del código en ejecución: ayuda a saber qué versión se probó.
    try:
        import inspect
        import subprocess

        code_root = Path(inspect.getfile(QueryEngine)).resolve().parents[2]
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=code_root, capture_output=True, text=True, timeout=5,
        ).stdout.strip() or None
    except Exception:
        return None


# Al final del script: así el diagnóstico y el archivo incluyen también el
# turno recién respondido.
server_snapshot = STATS.snapshot(getattr(engine, "powerbi_provider", None))
with st.sidebar:
    if st.session_state.get("notice"):
        st.warning(st.session_state.pop("notice"))
    with st.expander("Diagnóstico del servidor", expanded=False):
        st.markdown("\n".join(
            diagnostics_lines(server_snapshot, getattr(engine, "powerbi_provider", None))
        ))
    st.divider()
    st.subheader("Exportar conversación")
    include_reasoning = st.checkbox("Incluir el razonamiento", value=True)
    exported = export_conversation_markdown(
        st.session_state.messages,
        meta={
            "MedGemma": f"{medgemma_status.get('status')} ({medgemma_status.get('model')})",
            "Power BI": powerbi_connection.get("status"),
            "Versión del código": code_version(),
            "Estado del servidor": status_line(server_snapshot),
        },
        include_reasoning=include_reasoning,
    )
    download_args = dict(
        label="Descargar conversación (.md)",
        data=exported.encode("utf-8"),
        file_name=export_file_name(),
        mime="text/markdown",
        use_container_width=True,
    )
    try:
        # on_click="ignore": descargar no vuelve a ejecutar la app.
        st.download_button(**download_args, on_click="ignore")
    except TypeError:
        st.download_button(**download_args)
    st.caption("Descarga un documento con las preguntas, respuestas, opciones y el razonamiento de cada turno para compartirlo.")

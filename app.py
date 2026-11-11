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

from src.ui.estilo import LOGO_PATH, aplicar_estilo
from src.feedback.panel import mostrar_calificacion
from src.feedback.registro import snapshot_turno
from src.chatbot.estado_conversacion import EstadoConversacion
from src.chatbot.fabrica import construir_sistema
from src.chatbot.query_engine import QueryEngine
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
    format_empty_result,
    format_filters_line,
    format_query_plan_answer,
    format_unapplied_line,
)
from src.providers.powerbi_links import enlace_para_opcion, enlace_para_resultado

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
    # El cableado del motor vive en src/chatbot/fabrica.py (lo comparte el
    # backend FastAPI). Las rutas salen de las constantes de este módulo: los
    # arneses (tests/sim, tests/realistic, tests/real) las sobrescriben.
    sistema = construir_sistema(
        PROJECT_ROOT,
        qdrant_path=QDRANT_PATH,
        source_registry=SOURCE_REGISTRY,
        visual_metrics=VISUAL_METRICS,
        master_metrics=MASTER_METRICS,
    )
    engine = sistema.engine

    print("--------------------------------------------------------------------------------------")
    print("\nMASTER METRICS:", MASTER_METRICS.resolve())
    print("MASTER RESOLVER ACTIVO:", type(engine.master_metric_resolver).__name__)
    print("QUERY ENGINE:", engine.__class__)
    print("MODELOS SEMÁNTICOS ENRUTABLES:", sistema.source_router.semantic_models())
    return (
        engine, sistema.conversation_manager, ResponseFormatter(),
        sistema.medgemma_status, sistema.powerbi_connection,
    )

def get_display_answer(result, formatter):
    status = result.get("status")
    route = result.get("route")
    if status == "needs_clarification":
        return clarification_prompt(result)
    if status == "not_found":
        return result.get("answer") or "No encontré información relacionada con esa pregunta."
    if route == "rag":
        return result.get("answer") or "No encontré información suficiente."
    if route == "conversacion":
        # Portero conversacional: texto fijo, sin informe ni métrica.
        return result.get("answer") or ""
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
        # Qué indicador y qué periodo no tienen datos, y hasta qué fecha trae
        # datos la fuente (si se sabe); nunca una tabla vacía sin explicación.
        return format_empty_result(result)
    return "No pude completar la consulta. Activa Modo diagnóstico para ver en qué etapa falló."

def reset_if_finished(result, engine, conversation_manager, sesion=None):
    # Solo conservamos contexto mientras hay una contrapregunta pendiente.
    # engine.reset() (sin full=True) conserva a propósito la última consulta
    # numérica exitosa para seguimientos como «¿y en 2025?».
    if result.get("status") == "needs_clarification":
        return
    if sesion is not None:
        # Conversación de esta pestaña (spec 008): no se toca la de nadie más.
        sesion.cerrar_turno(result)
        return
    conversation_manager.reset()
    reset_method = getattr(engine, "reset", None)
    if callable(reset_method):
        reset_method()

st.set_page_config(
    page_title="Asistente de Gestión Clínica",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "📊",
    layout="centered",
)
aplicar_estilo()
st.title("Asistente de Gestión Clínica")
st.caption("RAG para consultas sobre tableros institucionales con Power BI y MEDGemma local.")

engine, conversation_manager, formatter, medgemma_status, powerbi_connection = build_system()


def conversacion():
    """Estado de la conversación de ESTA pestaña (spec 008): el motor es
    compartido por todas las sesiones y no guarda memoria ni contrapreguntas."""
    if "estado_conversacion" not in st.session_state:
        st.session_state.estado_conversacion = EstadoConversacion()
    return st.session_state.estado_conversacion

def clear_pending_clarification():
    st.session_state.pending_clarification = None
    st.session_state.queued_option = None


def queue_option(option_id, label):
    # Callback de st.button: se ejecuta antes del rerun; el turno se procesa
    # en el siguiente pase del script.
    st.session_state.queued_option = {"id": option_id, "label": label}


POWERBI_LINK_LABEL = "Abrir en Power BI ›"


def safe_link(compute, *args):
    # El enlace es un extra: si algo falla, la respuesta se muestra sin él.
    try:
        return compute(*args)
    except Exception:
        traceback.print_exc()
        return None


def render_powerbi_link(link, key):
    """Botón «Abrir en Power BI ›» al informe/página donde está el dato
    (data/catalog/report_links.json, generado por tools/sync_powerbi_links.py).
    `key` único por mensaje: dos respuestas pueden enlazar la misma página."""
    if not link or not link.get("url"):
        return
    place = str(link.get("etiqueta") or "").removeprefix("Abrir ").strip()
    if link.get("filtrado"):
        place += " · con los filtros de la consulta"
    st.link_button(POWERBI_LINK_LABEL, link["url"], help=link.get("etiqueta"), key=key)
    if place:
        st.caption(place)


def link_markdown(link):
    place = str(link.get("etiqueta") or "").removeprefix("Abrir ").strip()
    text = f"{POWERBI_LINK_LABEL} {place}".strip()
    return f"[{text}]({link['url']})"


def messages_with_links(messages):
    """Copia del historial para exportar (.md): el enlace de cada respuesta va
    al final del texto y el de cada opción, junto a su descripción."""
    exported = []
    for message in messages:
        link = message.get("powerbi_link")
        buttons = message.get("buttons") or []
        if not (link and link.get("url")) and not any(b.get("link") for b in buttons):
            exported.append(message)
            continue
        copy = dict(message)
        if link and link.get("url"):
            copy["content"] = f"{message.get('content') or ''}\n\n{link_markdown(link)}"
        if buttons:
            copy["buttons"] = [
                {**b, "caption": " · ".join(
                    part for part in (b.get("caption"), b.get("link") and link_markdown(b["link"])) if part
                ) or None}
                for b in buttons
            ]
        exported.append(copy)
    return exported


def attach_option_links(buttons, result):
    # Cada opción de la contrapregunta lleva el enlace de su informe/página.
    options = {
        str(option.get("id")): option
        for option in result.get("clarification_options") or []
        if isinstance(option, dict)
    }
    for button in buttons:
        link = safe_link(enlace_para_opcion, options.get(str(button["id"])))
        if link:
            button["link"] = {"url": link["url"], "etiqueta": link["etiqueta"]}
    return buttons


def render_clarification_buttons(pending):
    # Un botón por opción, con su descripción corta debajo. Si la opción tiene
    # informe en Power BI, un enlace al lado (abrirlo no recarga la app).
    for index, button in enumerate(pending["buttons"]):
        link = button.get("link")
        if link:
            left, right = st.columns([5, 2], vertical_alignment="center")
        else:
            left, right = st.container(), None
        with left:
            st.button(
                button["label"],
                key=f"clarification_{pending['id']}_{index}",
                on_click=queue_option,
                args=(button["id"], button["label"]),
                use_container_width=True,
            )
        if right is not None:
            with right:
                st.link_button(
                    "Power BI ›", link["url"], help=link.get("etiqueta"),
                    key=f"powerbi_option_{pending['id']}_{index}",
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
        tiene el motor. Decisión del usuario (specs/009-experiencia-espera):
        nunca se habla de otras consultas ni de filas; se muestra trabajo."""
        label = "Pensando en tu pregunta…"
        self.status.update(label=label)
        if not self.waiting_shown:
            self.waiting_shown = True
            self.status.markdown(f"⏳ {html.escape(label)}", unsafe_allow_html=True)
            render_live_clock(self.clock, self.started_at, time.time(), "pensando")

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
            # Un turno a la vez: la conversación va en st.session_state, pero
            # algunos colaboradores compartidos del motor aún guardan datos
            # del turno (specs/008-memoria-por-sesion/research.md). El candado
            # se libera siempre, también si Streamlit aborta esta ejecución
            # (StopException/RerunException son BaseException).
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
                            "reasoning": conversacion().ultimo_razonamiento,
                        }
                    # El motor ya cerró el turno de esta sesión; repetirlo no cambia nada.
                    reset_if_finished(result, engine, conversation_manager, sesion=conversacion())
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
            error_text = str(busy)  # detalle técnico solo para el diagnóstico
            result = {"status": "busy", "route": None, "error": error_text, "reasoning": None}
            answer = "Esta vez no alcancé a responder tu pregunta. Vuelve a enviarla en un momento, por favor."
            live.finish(error=True)

        st.markdown(answer)

        powerbi_link = None if error_text else safe_link(enlace_para_resultado, result)
        # Mismo índice que tendrá el mensaje en el historial.
        render_powerbi_link(powerbi_link, key=f"powerbi_link_{len(st.session_state.messages)}")

        buttons = clarification_buttons(result)
        clarification_id = None
        if buttons:
            attach_option_links(buttons, result)
            st.session_state.clarification_counter += 1
            clarification_id = st.session_state.clarification_counter
            st.session_state.pending_clarification = {
                "id": clarification_id,
                "buttons": buttons,
            }
            render_clarification_buttons(st.session_state.pending_clarification)

        if result.get("status") == "success" and result.get("route") != "conversacion":
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
                board_filters = ((result.get("query_plan") or {}).get("metric") or {}).get("visual_filters") or []
                if board_filters:
                    # Detalle técnico de los filtros del tablero; la respuesta
                    # solo lleva la frase corta en lenguaje de negocio.
                    st.write("**Filtros del tablero aplicados:**")
                    st.markdown("\n".join(
                        f"- `{item.get('table')}[{item.get('column')}]`: {item.get('text')}"
                        for item in board_filters
                    ))
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

        mensaje = {
            "role": "assistant", "content": answer,
            "buttons": buttons, "clarification_id": clarification_id,
            "reasoning": reasoning_text,
            "status": result.get("status"), "route": result.get("route"),
            "powerbi_link": powerbi_link,
        }
        # Snapshot para calificar el turno (barato, no se muestra); si falla,
        # el mensaje queda sin snapshot y sin panel.
        try:
            mensaje["snapshot"] = snapshot_turno(
                result, answer, user_text, via, [b["label"] for b in buttons or []])
        except Exception:
            traceback.print_exc()
        st.session_state.messages.append(mensaje)
        if debug_mode and mensaje.get("snapshot"):
            # Mismas claves que el bucle del historial: tras un rerun no se duplica.
            mostrar_calificacion(len(st.session_state.messages) - 1, st.session_state.messages)


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
        # Solo la conversación de esta pestaña: las demás sesiones no se tocan
        # y no hace falta esperar al turno de nadie (un turno aún en curso de
        # esta pestaña escribe en el estado viejo, no en el nuevo).
        st.session_state.estado_conversacion = EstadoConversacion()
        st.session_state.messages = []
        # Los índices de mensajes se reinician: sesión nueva para no chocar id_turno.
        st.session_state.pop("id_sesion", None)
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

for message_index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        render_powerbi_link(message.get("powerbi_link"), key=f"powerbi_link_{message_index}")
        if message.get("buttons"):
            if message.get("clarification_id") == active_id:
                # Rerun por otro widget: botones de la contrapregunta vigente.
                render_clarification_buttons(pending)
            else:
                render_past_options(message["buttons"])
        render_reasoning(message.get("reasoning"))
        if debug_mode and message.get("snapshot"):
            mostrar_calificacion(message_index, st.session_state.messages)

if prompt:
    execute_turn(prompt, lambda: engine.process(prompt, sesion=conversacion()))
elif queued:
    execute_turn(
        queued["label"],
        lambda: engine.select_clarification_option(queued["id"], queued["label"], sesion=conversacion()),
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
        messages_with_links(st.session_state.messages),
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

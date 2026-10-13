"""
Exporta la conversación del chat a un documento Markdown: preguntas (escritas
o elegidas con botón), respuestas, opciones ofrecidas y el razonamiento de
cada turno. Pensado para compartir una sesión de pruebas completa en un solo
archivo en lugar de copiar y pegar cada respuesta.
"""
from datetime import datetime


def _quote(text):
    """Texto como cita de Markdown (conserva saltos de línea y tablas)."""
    lines = str(text or "").strip().splitlines() or [""]
    return "\n".join(f"> {line}" if line.strip() else ">" for line in lines)


def _fence(text):
    """Bloque de código que no se rompe si el texto ya trae ``` dentro."""
    fence = "```"
    while fence in str(text):
        fence += "`"
    return f"{fence}text\n{str(text).rstrip()}\n{fence}"


def export_conversation_markdown(messages, meta=None, include_reasoning=True, now=None):
    """messages: lista de st.session_state.messages
    ({role, content, via?, buttons?, reasoning?, status?, route?}).
    meta: {clave: valor} del entorno (LLM, Power BI, versión...)."""
    now = now or datetime.now()
    meta = meta or {}
    questions = sum(1 for message in messages if message.get("role") == "user")
    lines = [
        "# Conversación del Asistente de Gestión Clínica",
        "",
        f"- Exportada: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Turnos del usuario: {questions}",
    ]
    lines += [f"- {key}: {value}" for key, value in meta.items() if value not in (None, "")]
    lines.append("")

    turn = 0
    for message in messages:
        role = message.get("role")
        if role == "user":
            turn += 1
            via = message.get("via") or "texto"
            lines += ["---", "", f"## Turno {turn}", "", f"**Usuario ({via}):**", "", _quote(message.get("content")), ""]
            continue

        header = "**Asistente:**"
        state = " · ".join(
            f"{name}={message[name]}" for name in ("status", "route") if message.get(name)
        )
        if state:
            header += f" _({state})_"
        lines += [header, "", _quote(message.get("content")), ""]

        buttons = message.get("buttons") or []
        if buttons:
            lines.append("Opciones ofrecidas:")
            for index, button in enumerate(buttons, 1):
                caption = f" — {button['caption']}" if button.get("caption") else ""
                lines.append(f"{index}. {button.get('label')}{caption}")
            lines.append("")

        if include_reasoning and message.get("reasoning"):
            lines += ["<details><summary>Razonamiento del asistente</summary>", "", _fence(message["reasoning"]), "", "</details>", ""]

    return "\n".join(lines).rstrip() + "\n"


def export_file_name(now=None):
    now = now or datetime.now()
    return f"conversacion_{now.strftime('%Y%m%d_%H%M%S')}.md"

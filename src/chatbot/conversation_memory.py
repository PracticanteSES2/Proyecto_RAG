"""
Memoria de la conversación: historial acotado de los últimos turnos.

Cada turno guarda lo que dijo el usuario (texto o botón), cómo se interpretó
(si se reescribió con el contexto), un resumen de lo que mostró el asistente y
los datos con los que se respondió:

- Power BI: indicador, modelo, informe, filtros, periodo, agrupación, valor o
  filas (y una copia del contexto de seguimiento, para volver a ese tema);
- documentación (RAG): tablero, páginas y fuentes;
- contrapregunta: opciones ofrecidas y, cuando el usuario elige, la elegida.

Vive en `QueryEngine`: sobrevive a `reset()` (que app.py llama tras cada
respuesta final) y se borra con `reset(full=True)` («Nueva conversación»).
No guarda filas completas ni el razonamiento: solo lo necesario para entender
el siguiente mensaje y para que la redacción use el hilo de la conversación.
"""
from collections import deque
import copy
import re

from src.chatbot.response_formatter import (
    format_filters_line, format_period_es, format_value_es, group_header, is_blank_value,
)

DEFAULT_MAX_TURNS = 12
_ANSWER_CHARS = 420
_TABLE_ROWS_IN_SUMMARY = 5


def _short(text, limit=_ANSWER_CHARS):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _row_parts(row):
    """(etiquetas, valor) de una fila de Power BI ({'T[COL]': x, '[__value]': n})."""
    labels, value = [], None
    for key, item in (row or {}).items():
        if re.search(r"__(?:value|m\d+|orden)", str(key).lower()):
            if value is None:
                value = item
            continue
        labels.append("(en blanco)" if is_blank_value(item) else str(item).strip())
    return labels, value


def _period_text(filters):
    for item in filters or []:
        if item.get("type") == "date_range" or (item.get("temporal") and item.get("label")):
            text = format_period_es(item)
            if text:
                return text
    return None


def _filters_text(filters):
    line = format_filters_line(filters)
    return line[len("Filtros: "):] if line.startswith("Filtros: ") else line


def summarize_result(result):
    """Resumen corto (texto plano) de lo que mostró el asistente."""
    if not isinstance(result, dict):
        return ""
    status = result.get("status")
    route = result.get("route")
    if status == "needs_clarification":
        prompt = result.get("prompt") or result.get("question") or "Te pedí que aclararas la pregunta."
        prompt = str(prompt).split("\n")[0]
        options = [
            str(option.get("label")) for option in result.get("clarification_options") or []
            if isinstance(option, dict) and option.get("label")
        ]
        text = prompt
        if options:
            text += " Opciones: " + " · ".join(options[:6])
        return _short(text)
    if status == "success" and route == "powerbi":
        metric = result.get("metric") or "indicador"
        filters = _filters_text(result.get("filters"))
        unapplied = [str(t) for t in result.get("unapplied_terms") or [] if t]
        if result.get("result_type") == "table":
            groups = ", ".join(
                str(group_header(g)) for g in result.get("group_by") or []
            )
            rows = result.get("rows") or []
            shown = []
            for row in rows[:_TABLE_ROWS_IN_SUMMARY]:
                labels, value = _row_parts(row)
                shown.append(f"{' / '.join(labels) or '-'}: {format_value_es(value, metric) or value}")
            text = f"Tabla de {metric}" + (f" por {groups}" if groups else "")
            text += f" ({result.get('total_rows') or len(rows)} filas"
            text += ("; " + "; ".join(shown) if shown else "") + ")"
        elif result.get("measures"):
            text = _short(result.get("answer") or "", 300)
        else:
            value = result.get("value")
            text = f"{metric}: {format_value_es(value, metric, result.get('metric_format')) or value}"
        if filters:
            text += f". Filtros: {filters}"
        if unapplied:
            text += f". No se pudo aplicar: {', '.join(unapplied)}"
        return _short(text)
    if status == "empty_result":
        filters = _filters_text(result.get("filters") or (result.get("query_plan") or {}).get("filters"))
        return "No hubo datos para esos filtros" + (f" ({filters})" if filters else "") + "."
    answer = result.get("answer")
    if answer:
        return _short(answer)
    if result.get("error"):
        return "No pude completar la consulta."
    return _short(result.get("question") or status or "")


def result_meta(result):
    """Datos estructurados del turno (sin filas completas ni razonamiento)."""
    meta = {"route": result.get("route"), "status": result.get("status")}
    if result.get("status") == "success" and result.get("route") == "powerbi":
        plan = result.get("query_plan") or {}
        filters = result.get("filters") or plan.get("filters") or []
        meta.update({
            "metric": result.get("metric"),
            "metric_id": result.get("metric_id"),
            "semantic_model": result.get("semantic_model"),
            "report": result.get("report") or result.get("dashboard"),
            "filters": _filters_text(
                [item for item in filters if not (item.get("type") == "date_range" or item.get("temporal"))]
            ) or None,
            "period": _period_text(filters),
            "group_by": [str(group_header(g)) for g in result.get("group_by") or []],
            "result_type": result.get("result_type"),
            "value": result.get("value") if result.get("result_type") == "scalar" else None,
            "rows": result.get("total_rows") if result.get("result_type") == "table" else None,
            "unapplied": list(result.get("unapplied_terms") or []),
        })
        if result.get("followup_of"):
            meta["followup_of"] = (result.get("followup_of") or {}).get("question")
    elif result.get("route") in ("rag", "out_of_scope"):
        sources = []
        pages = []
        for source in result.get("sources") or []:
            if not isinstance(source, dict):
                continue
            page = source.get("page") or source.get("page_display_name") or source.get("page_name")
            if page and page not in pages:
                pages.append(page)
            sources.append({
                "dashboard": source.get("dashboard"),
                "page": page,
                "chunk_type": source.get("chunk_type"),
            })
        meta.update({
            "dashboard": result.get("dashboard"),
            "pages": pages[:5],
            "sources": sources[:5],
        })
    if result.get("status") == "needs_clarification":
        meta["options"] = [
            str(option.get("label")) for option in result.get("clarification_options") or []
            if isinstance(option, dict) and option.get("label")
        ]
    return {key: value for key, value in meta.items() if value not in (None, [], "")}


class ConversationMemory:
    """Historial acotado (los últimos `max_turns` turnos)."""

    def __init__(self, max_turns=DEFAULT_MAX_TURNS):
        self._turns = deque(maxlen=max(1, int(max_turns)))

    def __len__(self):
        return len(self._turns)

    def clear(self):
        self._turns.clear()

    def turns(self):
        """Copia de los turnos, del más antiguo al más reciente."""
        return [copy.deepcopy(turn) for turn in self._turns]

    def last(self, predicate=None):
        """Turno más reciente (o el más reciente que cumpla `predicate`)."""
        for turn in reversed(self._turns):
            if predicate is None or predicate(turn):
                return copy.deepcopy(turn)
        return None

    def numeric_topics(self):
        """Contextos de seguimiento de las respuestas de Power BI, del más
        reciente al más antiguo (sirven para volver a un tema anterior)."""
        topics, seen = [], set()
        for turn in reversed(self._turns):
            topic = turn.get("topic")
            if not topic:
                continue
            key = (topic.get("metric_id"), topic.get("question"), repr(topic.get("filters")),
                   repr(topic.get("group_by")))
            if key in seen:
                continue
            seen.add(key)
            topics.append(copy.deepcopy(topic))
        return topics

    def record(self, user_text, result, via="texto", interpreted=None, topic=None):
        """Agrega el turno terminado. `via`: «texto» o «botón»; `interpreted`:
        la pregunta autónoma con que se respondió (si se reescribió); `topic`:
        contexto de seguimiento (indicador, filtros...) si fue un dato de Power BI."""
        if not isinstance(result, dict):
            result = {"status": "error"}
        # Elegir una opción completa la contrapregunta del turno anterior.
        if via == "botón" and self._turns:
            previous = self._turns[-1]
            if previous.get("meta", {}).get("options") and not previous["meta"].get("chosen"):
                previous["meta"]["chosen"] = str(user_text)
        turn = {
            "user": str(user_text or ""),
            "via": via,
            "interpreted": interpreted or None,
            "assistant": summarize_result(result),
            "meta": result_meta(result),
            "topic": copy.deepcopy(topic) if topic else None,
        }
        self._turns.append(turn)
        return copy.deepcopy(turn)

    def history(self, limit=None):
        """Mensajes alternados [{"role": "user"|"assistant", "text", "meta"}]
        de los últimos `limit` turnos (cada turno aporta dos mensajes)."""
        turns = list(self._turns)
        if limit is not None:
            turns = turns[-max(0, int(limit)):] if int(limit) > 0 else []
        messages = []
        for turn in turns:
            user_meta = {"via": turn.get("via")}
            if turn.get("interpreted"):
                user_meta["interpreted"] = turn["interpreted"]
            messages.append({"role": "user", "text": turn.get("user") or "", "meta": user_meta})
            messages.append({
                "role": "assistant", "text": turn.get("assistant") or "",
                "meta": copy.deepcopy(turn.get("meta") or {}),
            })
        return messages

    def transcript(self, limit=3, chars=300):
        """Texto plano de los últimos turnos (para el prompt del LLM)."""
        lines = []
        for message in self.history(limit):
            who = "Usuario" if message["role"] == "user" else "Asistente"
            text = message["text"]
            interpreted = (message.get("meta") or {}).get("interpreted")
            if interpreted and interpreted != text:
                text = f"{text} (entendido como: {interpreted})"
            lines.append(f"{who}: {_short(text, chars)}")
        return "\n".join(lines)

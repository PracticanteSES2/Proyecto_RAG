"""
Registro del razonamiento de un turno: qué revisó el asistente y por qué
tomó cada decisión (ruta, candidatos y puntajes, filtros, DAX, opciones).

La interfaz lo muestra en un desplegable como texto plano, para copiarlo y
compartirlo cuando una respuesta falla con tableros reales.
"""
import time
from datetime import datetime


class ReasoningTrace:

    def __init__(self, kind, text):
        self.started = time.perf_counter()
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.kind = kind
        self.text = text
        self.steps = []

    def add(self, title, *lines):
        """Agrega un paso. Las líneas vacías o None se omiten."""
        self.steps.append({
            "t": round(time.perf_counter() - self.started, 2),
            "title": str(title),
            "lines": [str(line) for line in lines if line not in (None, "")],
        })

    def to_dict(self):
        return {
            "created_at": self.created_at,
            "kind": self.kind,
            "text": self.text,
            "elapsed_s": round(time.perf_counter() - self.started, 2),
            "steps": [dict(step, lines=list(step["lines"])) for step in self.steps],
        }


def short(value, limit=160):
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def format_score(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def format_reasoning_text(reasoning, answer=None):
    """Texto plano del razonamiento (para copiar o descargar)."""
    if not reasoning:
        return ""
    head = "Pregunta" if reasoning.get("kind") == "question" else "Opción elegida"
    lines = [
        "=== RAZONAMIENTO DEL ASISTENTE ===",
        f"Fecha: {reasoning.get('created_at')}",
        f"{head}: {reasoning.get('text')}",
        f"Duración: {reasoning.get('elapsed_s')} s",
        "",
    ]
    for number, step in enumerate(reasoning.get("steps") or [], 1):
        lines.append(f"{number}. [{step.get('t')} s] {step.get('title')}")
        lines.extend(f"   - {line}" for line in step.get("lines") or [])
    if answer:
        lines += ["", "Respuesta mostrada:", str(answer)]
    return "\n".join(lines)


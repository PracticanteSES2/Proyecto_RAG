"""
Llamadas y turnos representativos.

Modo `llm`: cada turno es una secuencia de pasos; cada paso, una o varias
llamadas en paralelo, con los MISMOS prompts de sistema, max_tokens, tiempos
límite y espera de hueco que usa el código real:

  * síntesis RAG           src/chatbot/answer_synthesizer.py (600 tokens, 40 s,
                           espera MEDGEMMA_QUEUE_WAIT; contexto hasta 7000 car.)
  * reescritura contextual src/chatbot/contextual_rewriter.py (80 tokens, 8 s,
                           espera 1 s)
  * descripción de opciones src/chatbot/option_describer.py (60 tokens, 15 s,
                           3 en paralelo)

Las respuestas numéricas de Power BI no llaman al LLM (synthesize_powerbi no
se usa): en el perfil `mixto` cuentan como turnos sin llamadas.

Modo `e2e`: preguntas del simulador (tests/sim) que recorren esas rutas.
"""
import random

from src.chatbot.answer_synthesizer import DEFAULT_SYNTHESIS_TIMEOUT, AnswerSynthesizer
from src.chatbot.contextual_rewriter import LLMContextRewriter
from src.chatbot.option_describer import OptionDescriber

# Documentación sintética (sin datos de pacientes) del largo del contexto real.
_PARRAFO = (
    "Fuente {n} · Tablero de atenciones institucionales, página de indicadores. "
    "El indicador cuenta las atenciones registradas en el periodo seleccionado y se "
    "filtra por servicio, especialidad y aseguradora. La medida usa COUNTROWS sobre la "
    "tabla de hechos y excluye los registros anulados. El tablero muestra la tendencia "
    "mensual, la participación por servicio y el detalle por especialidad. "
)


def _contexto(chars=7000):
    parts, n = [], 1
    while sum(len(p) for p in parts) < chars:
        parts.append(_PARRAFO.format(n=n))
        n += 1
    return "".join(parts)[:chars]


def _mensajes_sintesis():
    user = (
        "PREGUNTA DEL USUARIO:\n¿Qué muestra el tablero de atenciones y cómo se calcula el indicador?\n\n"
        f"CONTEXTO RECUPERADO:\n{_contexto()}\n\nTAREA:\nResponde con base en el CONTEXTO."
    )
    return [{"role": "system", "content": AnswerSynthesizer.SYSTEM_PROMPT},
            {"role": "user", "content": user}]


def _mensajes_reescritura():
    rewriter = LLMContextRewriter(None)
    return rewriter.build_messages(
        "y las de urología?",
        "Usuario: ¿Cuántas cirugías programadas hubo en 2024?\nAsistente: CIRUGÍAS PROGRAMADAS: 6.803.",
    )


def _mensajes_descripcion():
    describer = OptionDescriber(None)
    option = {"id": "o1", "label": "CIRUGÍAS PROGRAMADAS", "measure": "CIRUGÍAS PROGRAMADAS",
              "dax_expression": "COUNTROWS(PROGRAMACION)", "table": "PROGRAMACION",
              "description": "Cirugías agendadas", "report": "QUIRURGICO", "page": "Programación"}
    return [{"role": "system", "content": describer.SYSTEM_PROMPT.format(max_words=describer.max_words)},
            {"role": "user", "content": describer.build_prompt(option)}]


def _mensajes_sonda():
    # Salida de largo fijo: con num_predict=64 todas generan exactamente 64
    # tokens (se cortan a propósito), así la duración solo depende de la carga.
    return [{"role": "user", "content": "Escribe los números del 1 al 300 separados por comas, sin nada más."}]


LLAMADAS = {
    "sonda": {"purpose": "sonda de capacidad", "max_tokens": 64, "timeout": 90.0,
              "queue_wait": None, "temperature": 0.0, "messages": _mensajes_sonda},
    "sintesis": {"purpose": "síntesis RAG", "max_tokens": 600, "timeout": DEFAULT_SYNTHESIS_TIMEOUT,
                 "queue_wait": None, "temperature": 0.1, "messages": _mensajes_sintesis},
    "reescritura": {"purpose": "reescritura contextual", "max_tokens": 80, "timeout": 8.0,
                    "queue_wait": 1.0, "temperature": 0.0, "messages": _mensajes_reescritura},
    "descripcion": {"purpose": "descripción de opciones", "max_tokens": 60, "timeout": 15.0,
                    "queue_wait": None, "temperature": 0.1, "messages": _mensajes_descripcion},
}

# Un turno = lista de pasos; un paso = llamadas que van en paralelo.
TURNOS = {
    "sonda": [["sonda"]],
    "sintesis": [["sintesis"]],
    "seguimiento": [["reescritura"], ["sintesis"]],
    "opciones": [["descripcion", "descripcion", "descripcion"]],
    "powerbi": [],
}

# Mezcla supuesta de un día normal (ajústala con --perfil o editando aquí).
MIXTO = [("sintesis", 0.45), ("seguimiento", 0.15), ("opciones", 0.20), ("powerbi", 0.20)]

PERFILES = ("sonda", "sintesis", "seguimiento", "opciones", "mixto")


def elegir_turno(perfil, rng):
    if perfil != "mixto":
        return perfil
    pick, acc = rng.random(), 0.0
    for name, weight in MIXTO:
        acc += weight
        if pick <= acc:
            return name
    return MIXTO[-1][0]


def nuevo_rng(semilla, usuario):
    return random.Random(f"{semilla}-{usuario}")


# Preguntas del modo e2e (motor del simulador tests/sim): documentales (síntesis
# RAG), numérica de Power BI (sin LLM) y ambigua (descripción de opciones).
PREGUNTAS_E2E = [
    "¿Qué muestra el tablero de atenciones?",
    "cuanto peso hubo en lavanderia en enero de 2026",
    "¿Cómo se calcula el porcentaje de participación del peso en la lavandería?",
    "cuantas cirugias hubo en 2024",
]

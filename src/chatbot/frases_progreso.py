"""Textos que ve la persona mientras espera (catálogo de src/chatbot/progreso.py).

Decisión del usuario (specs/009-experiencia-espera): todo describe el trabajo
con SU pregunta. Nada habla de colas, filas, turnos, posiciones, otras
consultas, el servidor ni saturación (lo verifica tests/progreso).
"""

# Variantes por etapa: todas describen lo que de verdad está pasando, para
# variar sin mentir. Cortas, sin cifras ni términos técnicos.
FRASES = {
    "entendiendo": (
        "Entendiendo tu pregunta",
        "Interpretando lo que necesitas",
        "Revisando qué dato me pides",
        "Leyendo con atención tu pregunta",
    ),
    "buscando_indicador": (
        "Buscando el indicador en los tableros",
        "Ubicando el tablero que tiene ese dato",
        "Buscando el indicador y el periodo que pides",
        "Revisando qué tablero responde mejor",
    ),
    "preparando_opciones": (
        "Preparando las opciones para que elijas",
        "Describiendo las opciones que encontré",
        "Organizando las alternativas encontradas",
    ),
    "conectando_powerbi": (
        "Conectando con Power BI",
        "Abriendo la conexión con los tableros",
        "Estableciendo la conexión con Power BI",
    ),
    "consultando_powerbi": (
        "Consultando los datos en Power BI",
        "Trayendo las cifras del tablero",
        "Consultando el tablero en Power BI",
        "Calculando el dato en Power BI",
    ),
    "revisando_documentacion": (
        "Revisando la documentación de los tableros",
        "Leyendo la documentación para responderte",
        "Buscando en la documentación y preparando la respuesta",
    ),
    "redactando": (
        "Redactando la respuesta",
        "Poniendo en palabras lo que encontré",
        "Preparando la respuesta con lo que encontré",
    ),
    "finalizando": (
        "Ya casi está",
        "Dando los últimos toques a la respuesta",
        "Terminando de preparar la respuesta",
    ),
}
ETAPAS = tuple(FRASES)
ETAPA_INICIAL = "entendiendo"

# Si una etapa se alarga (p. ej. mientras MedGemma se libera para redactar),
# cada ROTACION_S segundos se muestra la siguiente frase de su seguimiento:
# en orden de avance y cíclica, siempre sobre el trabajo con SU pregunta.
ROTACION_S = 8.0
SEGUIMIENTO = {
    "entendiendo": (
        "Pensando…",
        "Precisando qué dato necesitas",
        "Pensando en la mejor forma de responderte",
    ),
    "buscando_indicador": (
        "Comparando los indicadores que podrían servir",
        "Revisando el periodo y los filtros",
        "Pensando…",
    ),
    "preparando_opciones": (
        "Revisando cada opción",
        "Describiendo cada opción con claridad",
        "Pensando…",
    ),
    "conectando_powerbi": (
        "Esperando la conexión con los tableros",
        "Preparando la consulta del dato",
    ),
    "consultando_powerbi": (
        "Esperando las cifras del tablero",
        "Revisando las cifras que llegan",
        "Pensando…",
    ),
    "revisando_documentacion": (
        "Revisando los datos que encontré",
        "Organizando la respuesta",
        "Redactando la respuesta",
        "Pensando…",
    ),
    "redactando": (
        "Organizando la respuesta",
        "Pensando…",
        "Puliendo la redacción",
    ),
    "finalizando": (
        "Dando los últimos toques",
        "Revisando que todo cuadre",
    ),
}


# (segundos desde el inicio del turno, mensaje). Tranquilizan hablando del
# trabajo con la pregunta, nunca de otros ni de la carga. El del nivel 2
# depende de la etapa (ver frase_espera).
UMBRALES_ESPERA = (
    (10, "Sigo trabajando en tu pregunta…"),
    (25, "Estoy armando una respuesta completa; ya casi la tengo…"),
    (50, "Sigo con tu pregunta; no hace falta volver a enviarla."),
    (90, "Me está tomando más de lo habitual, pero sigo en ello."),
)

ESPERA_POWERBI = "Las cifras de Power BI están tardando un poco; sigo pendiente."


# Nota neutra para el resumen extractivo, sea cual sea el motivo: la respuesta
# se presenta como normal y nunca se culpa a la carga. `motivo` queda para el
# modo diagnóstico.
AVISO_EXTRACTIVO = "Te muestro lo que dice la documentación."

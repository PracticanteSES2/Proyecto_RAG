"""
Hechos de un tablero leídos de su PBIP y comparación entre versiones.

CONTRATO (lo implementa el agente «pbip»):

    hechos = extraer_hechos(ruta_pbip)
    # {"paginas": [{"nombre", "visible", "visuales": [{"id", "tipo", "titulo",
    #   "campos": ["AVERAGE(T[c])", ...], "filtros": ["T[c] NOT IN (...)", ...],
    #   "semaforo": ["verde 0-15", ...], "destino": "PAGINA" | None}]}],
    #  "tablas": {"T": {"modo", "sql", "columnas": [...], "calculadas": {...}}},
    #  "medidas": {"T[m]": "DAX"}}

    cambios = comparar(hechos_antes, hechos_despues)
    # -> ["Página CONSULTAS DIA: se agregó el visual Tarjeta «X» (AVERAGE(T[c])).", ...]

    archivos = esqueleto(ruta_pbip, tablero, source_group)
    # -> {"_general.md": texto, "consultas_dia.md": texto, ...}  borradores en el formato estándar

`comparar` alimenta al actualizador: los cambios detectados en el PBIP dicen QUÉ
cambió; la nota de la persona explica POR QUÉ.
"""


def extraer_hechos(ruta_pbip) -> dict:
    raise NotImplementedError("Pendiente: agente pbip")


def comparar(hechos_antes, hechos_despues) -> list:
    raise NotImplementedError("Pendiente: agente pbip")


def esqueleto(ruta_pbip, tablero, source_group) -> dict:
    raise NotImplementedError("Pendiente: agente pbip")

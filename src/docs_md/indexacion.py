"""
Reindexación del RAG para un solo tablero después de aprobar un cambio.

CONTRATO (lo implementa el agente «ingesta»):

    resultado = reindexar_grupo(source_group, qdrant_client=None)
    # -> {"source_group", "documentos", "chunks", "segundos", "errores": [...]}

- Regenera los derivados (processed, semantic_documents, catálogo, chunks)
  y reemplaza en Qdrant solo los puntos de ese source_group.
- Si la app ya tiene abierto el cliente de Qdrant (modo local: un solo cliente
  por carpeta), se le pasa ese cliente para no abrir otro.
"""


def reindexar_grupo(source_group, qdrant_client=None) -> dict:
    raise NotImplementedError("Pendiente: agente ingesta")

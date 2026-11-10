# Script manual (no es una prueba automática). Ejecutar desde la raíz:
#   .venv/Scripts/python.exe -X utf8 tools/manual/test_filter_resolution.py
import sys as _sys
from pathlib import Path as _Path
_RAIZ = str(_Path(__file__).resolve().parents[2])
if _RAIZ not in _sys.path:
    _sys.path.insert(0, _RAIZ)

from pathlib import Path

from src.rag.retriever import (
    HybridRetriever
)

from src.chatbot.intent_parser import (
    IntentParser
)

from src.chatbot.conversation_manager import (
    ConversationManager
)

from src.semantic.metric_resolver import (
    MetricResolver
)

from src.semantic.filter_resolver import (
    FilterResolver
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


QDRANT_PATH = (
    PROJECT_ROOT
    / "data"
    / "vector_db"
    / "qdrant"
)


TECHNICAL_CATALOG = (
    PROJECT_ROOT
    / "data"
    / "catalog"
    / "tablero_de_atenciones_institucionales_rag.json"
)


retriever = HybridRetriever(
    QDRANT_PATH
)

parser = IntentParser(
    retriever
)

conversation = ConversationManager(
    parser
)

metric_resolver = MetricResolver(
    retriever
)

filter_resolver = FilterResolver(
    TECHNICAL_CATALOG
)


# ============================================================
# PREGUNTA
# ============================================================

response = conversation.handle_message(

    "¿Cuál fue el promedio "
    "en agosto de 2026?"
)

print(
    "\nTURNO 1:"
)

print(
    response
)


# ============================================================
# ACLARACIÓN
# ============================================================

if (
    response["status"]
    == "needs_clarification"
):

    response = (
        conversation.handle_message(
            "Cirugías"
        )
    )


print(
    "\nINTENCIÓN COMPLETA:"
)

print(
    response
)


# ============================================================
# MÉTRICA
# ============================================================

metric = (
    metric_resolver.resolve(
        response
    )
)

print(
    "\nMÉTRICA:"
)

print(
    metric
)


# ============================================================
# FILTROS
# ============================================================

filters = (
    filter_resolver.resolve(
        response
    )
)

print(
    "\nFILTROS:"
)

print(
    filters
)


retriever.close()
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


# ============================================================
# PRIMER TURNO
# ============================================================

response = conversation.handle_message(
    "¿Cuál fue el promedio "
    "en agosto de 2026?"
)

print("\nTURNO 1")
print(response)


# ============================================================
# ACLARACIÓN
# ============================================================

response = conversation.handle_message(
    "Cirugías"
)

print("\nTURNO 2")
print(response)


# ============================================================
# RESOLVER MEDIDA
# ============================================================

if response["status"] == "ready":

    metric_result = (
        metric_resolver.resolve(
            response
        )
    )

    print(
        "\nMEDIDA RESUELTA"
    )

    print(
        metric_result
    )


retriever.close()
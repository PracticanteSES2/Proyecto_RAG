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

from src.dax.dax_generator import (
    DAXGenerator
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

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


# ============================================================
# COMPONENTES
# ============================================================

retriever = HybridRetriever(
    QDRANT_PATH
)

intent_parser = IntentParser(
    retriever
)

conversation = ConversationManager(
    intent_parser
)

metric_resolver = MetricResolver(
    retriever
)

filter_resolver = FilterResolver(
    TECHNICAL_CATALOG
)

dax_generator = DAXGenerator()


try:

    # ========================================================
    # PREGUNTA
    # ========================================================

    response = (
        conversation.handle_message(
            "¿Cuál fue el promedio "
            "en agosto de 2026?"
        )
    )

    print(
        "\nINTENCIÓN INICIAL:"
    )

    print(
        response
    )


    # ========================================================
    # ACLARACIÓN
    # ========================================================

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


    # ========================================================
    # MÉTRICA
    # ========================================================

    metric_result = (
        metric_resolver.resolve(
            response
        )
    )


    print(
        "\nMÉTRICA:"
    )

    print(
        metric_result
    )


    # ========================================================
    # FILTROS
    # ========================================================

    filter_result = (
        filter_resolver.resolve(
            response
        )
    )


    print(
        "\nFILTROS:"
    )

    print(
        filter_result
    )


    # ========================================================
    # DAX
    # ========================================================

    dax_result = (
        dax_generator.generate(
            metric_result,
            filter_result
        )
    )


    print(
        "\nDAX GENERADO:"
    )

    print(
        dax_result["dax"]
    )


finally:

    retriever.close()
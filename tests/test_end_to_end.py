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

from src.chatbot.query_engine import (
    QueryEngine
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

from src.dax.dax_validator import (
    DAXValidator
)

from src.providers.powerbi_provider import (
    PowerBIProvider
)


# ============================================================
# RUTAS
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

conversation_manager = (
    ConversationManager(
        intent_parser
    )
)

metric_resolver = (
    MetricResolver(
        retriever
    )
)

filter_resolver = (
    FilterResolver(
        TECHNICAL_CATALOG
    )
)

dax_generator = (
    DAXGenerator()
)

dax_validator = (
    DAXValidator(
        TECHNICAL_CATALOG
    )
)

powerbi_provider = (
    PowerBIProvider()
)


engine = QueryEngine(

    conversation_manager=
        conversation_manager,

    metric_resolver=
        metric_resolver,

    filter_resolver=
        filter_resolver,

    dax_generator=
        dax_generator,

    dax_validator=
        dax_validator,

    powerbi_provider=
        powerbi_provider
)


# ============================================================
# PRUEBA
# ============================================================

try:

    question = (
        "¿Cuál fue el promedio "
        "de cirugías en agosto "
        "de 2026?"
    )

    print(
        "\nPREGUNTA:"
    )

    print(
        question
    )


    result = engine.process(
        question
    )


    print(
        "\nRESULTADO COMPLETO:"
    )

    print(
        result
    )


    if (
        result.get("status")
        == "success"
    ):

        print(
            "\n================================"
        )

        print(
            "RESPUESTA:"
        )

        print(
            result["value"]
        )

        print(
            "================================"
        )


        print(
            "\nMEDIDA:"
        )

        print(
            result["metric"]
        )


        print(
            "\nMODELO:"
        )

        print(
            result["semantic_model"]
        )


        print(
            "\nDAX EJECUTADO:"
        )

        print(
            result["dax"]
        )


finally:

    retriever.close()
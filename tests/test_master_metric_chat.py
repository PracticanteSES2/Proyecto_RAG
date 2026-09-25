from pathlib import Path

from src.rag.retriever import HybridRetriever

from src.chatbot.intent_parser import IntentParser
from src.chatbot.conversation_manager import (
    ConversationManager
)
from src.chatbot.query_engine import QueryEngine
from src.chatbot.rag_answer_engine import (
    RAGAnswerEngine
)

from src.semantic.master_metric_resolver import (
    MasterMetricResolver
)
from src.semantic.metric_resolver import (
    MetricResolver
)
from src.semantic.filter_resolver import (
    FilterResolver
)
from src.semantic.business_filter_resolver import (
    BusinessFilterResolver
)

from src.dax.master_metric_dax_generator import (
    MasterMetricDAXGenerator
)
from src.dax.dax_generator import DAXGenerator
from src.dax.dax_validator import DAXValidator

from src.providers.powerbi_provider import (
    PowerBIProvider
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

MASTER_CATALOG = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "master_metrics.json"
)

TECHNICAL_CATALOG = (
    PROJECT_ROOT
    / "data"
    / "catalog"
    / "tablero_de_atenciones_institucionales_rag.json"
)


def build_engine():

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

    master_metric_resolver = (
        MasterMetricResolver(
            MASTER_CATALOG
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

    powerbi_provider = (
        PowerBIProvider()
    )

    business_filter_resolver = (
        BusinessFilterResolver(
            TECHNICAL_CATALOG,
            powerbi_provider,
        )
    )

    engine = QueryEngine(
        conversation_manager=
            conversation_manager,
        master_metric_resolver=
            master_metric_resolver,
        master_metric_dax_generator=
            MasterMetricDAXGenerator(),
        metric_resolver=
            metric_resolver,
        filter_resolver=
            filter_resolver,
        business_filter_resolver=
            business_filter_resolver,
        dax_generator=
            DAXGenerator(),
        dax_validator=
            DAXValidator(
                TECHNICAL_CATALOG
            ),
        powerbi_provider=
            powerbi_provider,
        rag_answer_engine=
            RAGAnswerEngine(
                retriever
            ),
    )

    return (
        engine,
        conversation_manager,
        retriever,
    )


def main():

    engine = None
    retriever = None

    try:

        (
            engine,
            conversation_manager,
            retriever,
        ) = build_engine()

        print(
            "\nCASO 1 - AMBIGÜEDAD"
        )

        first = engine.process(
            "¿Cuántos pacientes observados "
            "hubo en julio de 2025?"
        )

        print(
            first
        )

        print(
            "\nRESPUESTA A CONTRAPREGUNTA"
        )

        second = engine.process(
            "Consultas prioritarias"
        )

        print(
            second
        )

        print(
            "\nCASO 2 - DIRECTO"
        )

        engine.reset()
        conversation_manager.reset()

        third = engine.process(
            "¿Cuántos pacientes observados "
            "hubo en consultas prioritarias "
            "en julio de 2025?"
        )

        print(
            third
        )

    finally:

        if engine:
            engine.close()

        if retriever:
            retriever.close()


if __name__ == "__main__":
    main()

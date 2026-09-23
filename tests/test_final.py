from pathlib import Path

from src.rag.retriever import HybridRetriever

from src.chatbot.intent_parser import IntentParser
from src.chatbot.conversation_manager import ConversationManager
from src.chatbot.query_engine import QueryEngine
from src.chatbot.rag_answer_engine import RAGAnswerEngine
from src.chatbot.response_formatter import ResponseFormatter

from src.semantic.metric_resolver import MetricResolver
from src.semantic.filter_resolver import FilterResolver

from src.dax.dax_generator import DAXGenerator
from src.dax.dax_validator import DAXValidator

from src.providers.powerbi_provider import PowerBIProvider

from src.semantic.business_filter_resolver import (
    BusinessFilterResolver
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

SHOW_MEASURES_DEBUG = False
SHOW_RESULT_DEBUG = False


# ============================================================
# CONSTRUCCIÓN DEL MOTOR
# ============================================================

def build_engine(retriever):
    """
    Construye todos los componentes utilizando
    una única instancia de HybridRetriever.
    """

    intent_parser = IntentParser(
        retriever
    )

    conversation_manager = ConversationManager(
        intent_parser
    )

    metric_resolver = MetricResolver(
        retriever
    )

    filter_resolver = FilterResolver(
        TECHNICAL_CATALOG
    )

    dax_generator = DAXGenerator()

    dax_validator = DAXValidator(
        TECHNICAL_CATALOG
    )

    powerbi_provider = PowerBIProvider()

    rag_answer_engine = RAGAnswerEngine(
        retriever
    )

    powerbi_provider = PowerBIProvider()

    business_filter_resolver = (
    BusinessFilterResolver(
        TECHNICAL_CATALOG,
        powerbi_provider
    )
)

    engine = QueryEngine(
        conversation_manager=conversation_manager,
        metric_resolver=metric_resolver,
        filter_resolver=filter_resolver,
        dax_generator=dax_generator,
        dax_validator=dax_validator,
        powerbi_provider=powerbi_provider,
        business_filter_resolver=business_filter_resolver,
        rag_answer_engine=rag_answer_engine
    )

    formatter = ResponseFormatter()

    return (
        engine,
        conversation_manager,
        formatter
    )


# ============================================================
# DEBUG OPCIONAL DE MEDIDAS
# ============================================================

def show_measures(retriever):
    """
    Muestra las medidas disponibles del dashboard CIRUGÍAS.
    Útil únicamente para diagnóstico.
    """

    measures = (
        retriever
        .get_measures_by_dashboard(
            "CIRUGÍAS"
        )
    )

    print(
        "\nTODAS LAS MEDIDAS DE CIRUGÍAS:"
    )

    for measure in measures:
        print(
            "-",
            measure.get("measure")
        )


# ============================================================
# PRUEBAS
# ============================================================

def run_tests(
    engine,
    conversation_manager,
    formatter
):
    """
    Ejecuta preguntas independientes para validar:
    - ruta RAG
    - ruta Power BI
    - formato final de respuesta
    """

    questions = [
        "¿Cuál es el total de egresos?"
    ]

    for question in questions:

        # Cada pregunta se prueba como conversación independiente.
        conversation_manager.reset()

        print(
            "\n"
            "============================================================"
        )

        print(
            "PREGUNTA:"
        )

        print(
            question
        )

        result = engine.process(
            question
        )

        formatted_answer = (
            formatter.format(
                result
            )
        )

        print(
            "\nRUTA:"
        )

        print(
            result.get(
                "route",
                "sin_ruta"
            )
        )

        print(
            "\nESTADO:"
        )

        print(
            result.get(
                "status",
                "sin_estado"
            )
        )

        print(
            "\nRESPUESTA PARA EL USUARIO:"
        )

        print(
            formatted_answer
        )

        if SHOW_RESULT_DEBUG:

            print(
                "\nDEBUG INTERNO:"
            )

            print(
                result
            )


# ============================================================
# MAIN
# ============================================================

def main():

    retriever = None

    try:

        # IMPORTANTE:
        # Solo se crea UNA instancia de Qdrant/HybridRetriever.
        retriever = HybridRetriever(
            QDRANT_PATH
        )

        (
            engine,
            conversation_manager,
            formatter
        ) = build_engine(
            retriever
        )

        if SHOW_MEASURES_DEBUG:

            show_measures(
                retriever
            )

        run_tests(
            engine,
            conversation_manager,
            formatter
        )

        print(
            "\n"
            "============================================================"
        )

        print(
            "FIN DE LA PRUEBA"
        )

    finally:

        if retriever is not None:

            retriever.close()


if __name__ == "__main__":
    main()

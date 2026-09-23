from pathlib import Path
from pprint import pprint

from src.rag.retriever import HybridRetriever

from src.chatbot.intent_parser import IntentParser
from src.chatbot.conversation_manager import ConversationManager
from src.chatbot.query_engine import QueryEngine
from src.chatbot.rag_answer_engine import RAGAnswerEngine
from src.chatbot.answer_synthesizer import AnswerSynthesizer
from src.chatbot.response_formatter import ResponseFormatter

from src.semantic.metric_resolver import MetricResolver
from src.semantic.filter_resolver import FilterResolver
from src.semantic.business_filter_resolver import BusinessFilterResolver

from src.dax.dax_generator import DAXGenerator
from src.dax.dax_validator import DAXValidator

from src.providers.powerbi_provider import PowerBIProvider
from src.llm.ollama_provider import OllamaProvider


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
# CONSTRUCCIÓN DEL MOTOR
# ============================================================

def build_engine():

    # --------------------------------------------------------
    # RAG / QDRANT
    # --------------------------------------------------------

    retriever = HybridRetriever(
        QDRANT_PATH
    )

    # --------------------------------------------------------
    # INTENCIÓN + CONVERSACIÓN
    # --------------------------------------------------------

    intent_parser = IntentParser(
        retriever
    )

    conversation_manager = (
        ConversationManager(
            intent_parser
        )
    )

    # --------------------------------------------------------
    # RESOLUCIÓN SEMÁNTICA
    # --------------------------------------------------------

    metric_resolver = MetricResolver(
        retriever
    )

    filter_resolver = FilterResolver(
        TECHNICAL_CATALOG
    )

    # --------------------------------------------------------
    # POWER BI
    # --------------------------------------------------------

    powerbi_provider = (
        PowerBIProvider()
    )

    business_filter_resolver = (
        BusinessFilterResolver(
            TECHNICAL_CATALOG,
            powerbi_provider
        )
    )

    dax_generator = DAXGenerator()

    dax_validator = DAXValidator(
        TECHNICAL_CATALOG
    )

    # --------------------------------------------------------
    # LLM LOCAL: OLLAMA + QWEN
    # --------------------------------------------------------

    ollama_provider = (
        OllamaProvider()
    )

    answer_synthesizer = (
        AnswerSynthesizer(
            llm_provider=
                ollama_provider
        )
    )

    # --------------------------------------------------------
    # MOTOR RAG CON SÍNTESIS QWEN
    # --------------------------------------------------------

    rag_answer_engine = (
        RAGAnswerEngine(
            retriever=retriever,
            answer_synthesizer=
                answer_synthesizer,
            default_limit=5,
            min_score=0.35
        )
    )

    # --------------------------------------------------------
    # MOTOR GENERAL
    # --------------------------------------------------------

    engine = QueryEngine(
        conversation_manager=
            conversation_manager,

        metric_resolver=
            metric_resolver,

        filter_resolver=
            filter_resolver,

        business_filter_resolver=
            business_filter_resolver,

        dax_generator=
            dax_generator,

        dax_validator=
            dax_validator,

        powerbi_provider=
            powerbi_provider,

        rag_answer_engine=
            rag_answer_engine
    )

    formatter = (
        ResponseFormatter()
    )

    return {
        "engine":
            engine,

        "conversation_manager":
            conversation_manager,

        "formatter":
            formatter,

        "retriever":
            retriever,

        "powerbi_provider":
            powerbi_provider,

        "ollama_provider":
            ollama_provider,
    }


# ============================================================
# MOSTRAR ESTADO DEL MODELO
# ============================================================

def show_model_status(
    ollama_provider
):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "VERIFICANDO OLLAMA / QWEN"
    )

    print(
        "=" * 70
    )

    status = (
        ollama_provider
        .healthcheck()
    )

    pprint(
        status,
        sort_dicts=False
    )

    return (
        status.get("status")
        == "ready"
    )


# ============================================================
# MOSTRAR RESULTADO
# ============================================================

def show_result(
    result,
    formatter,
    show_raw=False
):

    print(
        "\nSISTEMA:"
    )

    try:

        answer = (
            formatter.format(
                result
            )
        )

    except Exception:

        answer = None


    if answer:

        print(
            answer
        )

    else:

        # Fallback útil mientras terminamos
        # ResponseFormatter.

        if (
            result.get("status")
            == "needs_clarification"
        ):

            print(
                result.get(
                    "question",
                    "Necesito una aclaración."
                )
            )

        elif (
            result.get("route")
            == "rag"
        ):

            print(
                result.get(
                    "answer",
                    "No se encontró respuesta."
                )
            )

        elif (
            result.get("route")
            == "powerbi"
        ):

            print(
                "Resultado:",
                result.get(
                    "value"
                )
            )

        else:

            print(
                "Estado:",
                result.get(
                    "status"
                )
            )


    print(
        "\nRUTA:",
        result.get(
            "route",
            "sin_ruta"
        )
    )


    # Si la consulta pasó por RAG,
    # verificamos si realmente usó Qwen.
    if (
        result.get("route")
        == "rag"
    ):

        synthesis_mode = (
            result.get(
                "synthesis_mode"
            )
        )

        # Algunas versiones de QueryEngine
        # todavía no propagan synthesis_mode.
        # En ese caso miramos si está dentro
        # de los detalles disponibles.
        if synthesis_mode:

            print(
                "SÍNTESIS:",
                synthesis_mode
            )


    print(
        "ESTADO:",
        result.get(
            "status",
            "sin_estado"
        )
    )


    if show_raw:

        print(
            "\nRESULTADO INTERNO:"
        )

        pprint(
            result,
            sort_dicts=False
        )


    print(
        "\n"
        + "-" * 70
    )


# ============================================================
# PRUEBA DIRECTA DEL MODELO
# ============================================================

def ask_qwen_directly(
    ollama_provider,
    prompt
):

    result = (
        ollama_provider.chat(
            messages=[
                {
                    "role":
                        "system",

                    "content":
                        (
                            "Responde en español, "
                            "de forma breve y clara."
                        )
                },
                {
                    "role":
                        "user",

                    "content":
                        prompt
                }
            ],

            temperature=0.1,

            max_tokens=300,

            think=False
        )
    )

    print(
        "\nQWEN:"
    )

    pprint(
        result,
        sort_dicts=False
    )

    print(
        "\n"
        + "-" * 70
    )


# ============================================================
# CHAT INTERACTIVO
# ============================================================

def main():

    components = None

    show_raw = False

    try:

        components = (
            build_engine()
        )

        engine = (
            components[
                "engine"
            ]
        )

        conversation_manager = (
            components[
                "conversation_manager"
            ]
        )

        formatter = (
            components[
                "formatter"
            ]
        )

        ollama_provider = (
            components[
                "ollama_provider"
            ]
        )


        # ----------------------------------------------------
        # COMPROBAR MODELO
        # ----------------------------------------------------

        model_ready = (
            show_model_status(
                ollama_provider
            )
        )


        if not model_ready:

            print(
                "\nEl modelo no está listo."
            )

            print(
                "Verifica que Ollama esté abierto "
                "y ejecuta:"
            )

            print(
                "\nollama pull qwen3:8b"
            )

            return


        # ----------------------------------------------------
        # INICIO DEL CHAT
        # ----------------------------------------------------

        print(
            "\n"
            + "=" * 70
        )

        print(
            "CHAT INTERACTIVO - RAG + POWER BI + QWEN3"
        )

        print(
            "=" * 70
        )

        print(
            "\nComandos:"
        )

        print(
            "  /raw on      Mostrar resultado interno"
        )

        print(
            "  /raw off     Ocultar resultado interno"
        )

        print(
            "  /reset       Reiniciar conversación"
        )

        print(
            "  /qwen TEXTO  Preguntar directamente a Qwen"
        )

        print(
            "  salir        Terminar"
        )


        while True:

            message = input(
                "\nUSUARIO: "
            ).strip()


            if not message:

                continue


            normalized = (
                message.lower()
            )


            # ------------------------------------------------
            # SALIR
            # ------------------------------------------------

            if normalized in {
                "salir",
                "exit",
                "quit"
            }:

                print(
                    "\nFin de la prueba."
                )

                break


            # ------------------------------------------------
            # RESET
            # ------------------------------------------------

            if normalized == "/reset":

                conversation_manager.reset()

                reset_method = getattr(
                    engine,
                    "reset",
                    None
                )

                if callable(
                    reset_method
                ):

                    reset_method()


                print(
                    "\nSISTEMA: "
                    "Contexto reiniciado."
                )

                continue


            # ------------------------------------------------
            # RAW
            # ------------------------------------------------

            if normalized == "/raw on":

                show_raw = True

                print(
                    "\nSISTEMA: RAW activado."
                )

                continue


            if normalized == "/raw off":

                show_raw = False

                print(
                    "\nSISTEMA: RAW desactivado."
                )

                continue


            # ------------------------------------------------
            # PREGUNTA DIRECTA A QWEN
            # ------------------------------------------------

            if normalized.startswith(
                "/qwen "
            ):

                prompt = (
                    message[6:]
                    .strip()
                )

                if prompt:

                    ask_qwen_directly(
                        ollama_provider=
                            ollama_provider,

                        prompt=
                            prompt
                    )

                continue


            # ------------------------------------------------
            # CHATBOT COMPLETO
            # ------------------------------------------------

            try:

                result = (
                    engine.process(
                        message
                    )
                )

            except Exception as exc:

                print(
                    "\nERROR:"
                )

                print(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

                continue


            show_result(
                result=
                    result,

                formatter=
                    formatter,

                show_raw=
                    show_raw
            )


    finally:

        if components:

            engine = components.get(
                "engine"
            )

            retriever = components.get(
                "retriever"
            )

            powerbi_provider = (
                components.get(
                    "powerbi_provider"
                )
            )


            if engine is not None:

                try:
                    engine.close()

                except Exception:
                    pass


            if powerbi_provider is not None:

                try:
                    powerbi_provider.close()

                except Exception:
                    pass


            if retriever is not None:

                try:
                    retriever.close()

                except Exception:
                    pass


if __name__ == "__main__":
    main()

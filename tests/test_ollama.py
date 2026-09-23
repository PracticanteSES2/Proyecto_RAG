from src.llm.ollama_provider import (
    OllamaProvider
)

from src.chatbot.answer_synthesizer import (
    AnswerSynthesizer
)


def main():

    provider = OllamaProvider()

    health = provider.healthcheck()

    print(
        "\nESTADO OLLAMA:"
    )

    print(
        health
    )

    if (
        health.get("status")
        != "ready"
    ):
        print(
            "\nOllama o el modelo no están listos."
        )
        return

    synthesizer = AnswerSynthesizer(
        provider
    )

    sources = [
        {
            "dashboard":
                "CIRUGÍAS",

            "chunk_type":
                "dashboard_overview",

            "measure":
                None,

            "text":
                (
                    "El indicador Promedio de oportunidad "
                    "muestra el promedio del tiempo de "
                    "oportunidad para la realización de "
                    "cirugías, permitiendo evaluar el tiempo "
                    "de respuesta en la atención quirúrgica."
                ),
        }
    ]

    result = synthesizer.synthesize_rag(
        question=(
            "¿Qué significa el indicador "
            "de oportunidad?"
        ),
        sources=sources,
    )

    print(
        "\nRESPUESTA:"
    )

    print(
        result
    )


if __name__ == "__main__":
    main()

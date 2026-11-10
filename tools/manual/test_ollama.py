# Script manual (no es una prueba automática). Ejecutar desde la raíz:
#   .venv/Scripts/python.exe -X utf8 tools/manual/test_ollama.py
import sys as _sys
from pathlib import Path as _Path
_RAIZ = str(_Path(__file__).resolve().parents[2])
if _RAIZ not in _sys.path:
    _sys.path.insert(0, _RAIZ)

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

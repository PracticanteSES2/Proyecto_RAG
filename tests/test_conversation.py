if __name__ == "__main__":

    from pathlib import Path
    from src.rag.retriever import HybridRetriever
    from src.chatbot.intent_parser import IntentParser

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

    questions = [
        "¿Cuál es el promedio mensual de cirugías?",
        "¿Qué información muestra el tablero de consultas ambulatorias?",
        "¿Qué filtros puedo utilizar para analizar las cirugías?",
        "¿Cuántas atenciones hubo?",
        "¿Cuál fue el promedio en agosto de 2026?",
    ]

    for question in questions:

        print("\n======================================")
        print("PREGUNTA:", question)

        result = parser.parse(
            question
        )

        print(
            result.to_dict()
        )

    # IMPORTANTE:
    # debe estar dentro del if __name__ == "__main__"
    retriever.close()
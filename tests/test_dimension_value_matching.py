from src.semantic.query_semantic_planner import (
    phrase_match_score,
)


CASES = [
    (
        "¿Cuántas cirugías generales se han realizado?",
        "CIRUGIA GENERAL",
    ),
    (
        "¿Cuántas cirugías plásticas se han realizado en total?",
        "CIRUGIA PLASTICA",
    ),
    (
        "¿Cuántas consultas de cardiología hubo?",
        "CARDIOLOGIA",
    ),
    (
        "¿Cuántas cirugías de Nueva EPS hubo?",
        "NUEVA EPS",
    ),
]


def main():

    for question, value in CASES:

        score = phrase_match_score(
            question,
            value,
        )

        print(
            "\nQUESTION:",
            question,
        )

        print(
            "VALUE:",
            value,
        )

        print(
            "SCORE:",
            score,
        )

        assert score >= 0.78


if __name__ == "__main__":
    main()

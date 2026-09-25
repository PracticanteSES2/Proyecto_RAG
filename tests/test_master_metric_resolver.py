from pathlib import Path
from pprint import pprint

from src.semantic.master_metric_resolver import (
    MasterMetricResolver
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

CATALOG = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "master_metrics.json"
)


resolver = MasterMetricResolver(
    CATALOG
)


questions = [

    (
        "¿Cuántos pacientes observados hubo "
        "en consultas prioritarias "
        "en julio de 2025?"
    ),

    (
        "¿Cuántos pacientes observados hubo "
        "en observaciones obstétricas "
        "en julio de 2025?"
    ),
]

for question in questions:

    print(
        "\n"
        + "=" * 70
    )

    print("PREGUNTA:")
    print(question)

    result = resolver.resolve(
        question
    )

    status = result.get(
        "status"
    )

    print(
        "\nSTATUS:",
        status
    )


    # ========================================================
    # AMBIGUO
    # ========================================================

    if status == "ambiguous":

        print("\nRAZÓN:")
        print(
            result.get(
                "reason"
            )
        )

        print("\nOPCIONES:")

        options = result.get(
            "clarification_options",
            []
        )

        if options:

            for option in options:
                print(
                    "-",
                    option
                )

        else:

            print(
                "(sin opciones de dashboard)"
            )


        print(
            "\nCANDIDATOS:"
        )

        candidates = result.get(
            "candidates",
            []
        )

        for index, candidate in enumerate(
            candidates,
            start=1
        ):

            print(
                "\n"
                + "-" * 50
            )

            print(
                f"CANDIDATO {index}"
            )

            print(
                "LABEL:",
                candidate.get(
                    "label"
                )
            )

            print(
                "DASHBOARD:",
                candidate.get(
                    "dashboard"
                )
            )

            print(
                "ORIGEN:",
                candidate.get(
                    "source_type"
                )
            )

            print(
                "BUSINESS SCORE:",
                candidate.get(
                    "business_score"
                )
            )

            print(
                "DASHBOARD SCORE:",
                candidate.get(
                    "dashboard_score"
                )
            )

            print(
                "SCORE FINAL:",
                candidate.get(
                    "score"
                )
            )

            print(
                "TABLA:",
                candidate.get(
                    "table"
                )
            )

            print(
                "COLUMNA:",
                candidate.get(
                    "column"
                )
            )

            print(
                "AGREGACIÓN:",
                candidate.get(
                    "aggregation"
                )
            )

            print(
                "DAX:",
                candidate.get(
                    "dax_expression"
                )
            )


    # ========================================================
    # RESUELTO
    # ========================================================

    elif status == "resolved":

        metric = result.get(
            "metric",
            {}
        )

        print(
            "\nDASHBOARD:",
            (
                result.get(
                    "resolved_dashboard"
                )
                or metric.get(
                    "dashboard"
                )
            )
        )

        print(
            "MÉTRICA:",
            metric.get(
                "label"
            )
        )

        print(
            "ORIGEN:",
            metric.get(
                "source_type"
            )
        )

        print(
            "BUSINESS SCORE:",
            metric.get(
                "business_score"
            )
        )

        print(
            "DASHBOARD SCORE:",
            metric.get(
                "dashboard_score"
            )
        )

        print(
            "DAX:"
        )

        print(
            metric.get(
                "dax_expression"
            )
        )


    # ========================================================
    # NO ENCONTRADO
    # ========================================================

    else:

        print(
            "\nRESULTADO:"
        )

        print(
            result
        )
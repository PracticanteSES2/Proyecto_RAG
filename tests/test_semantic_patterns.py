from pathlib import Path
import json

from src.semantic.master_metric_resolver import (
    MasterMetricResolver
)

from src.semantic.business_filter_resolver import (
    phrase_match_score
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

MASTER_METRICS = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "master_metrics.json"
)

VISUAL_METRICS_CATALOG = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "visual_metrics_catalog.json"
)


def main():

    print(
        "\nTEST 1 - MÉTRICA DE CIRUGÍAS"
    )

    resolver = (
        MasterMetricResolver(
            MASTER_METRICS
        )
    )

    result = resolver.resolve(
        "cuanta cirugia realiz",
        dashboard="CIRUGIAS",
    )

    print(
        "STATUS:",
        result.get(
            "status"
        )
    )

    metric = result.get(
        "metric",
        {},
    )

    print(
        "MÉTRICA:",
        metric.get(
            "label"
        )
    )

    print(
        "DAX:",
        metric.get(
            "dax_expression"
        )
    )

    assert (
        result.get("status")
        == "resolved"
    )

    assert (
        "COUNT("
        in (
            metric.get(
                "dax_expression"
            )
            or ""
        ).upper()
    )


    print(
        "\nTEST 2 - VARIACIONES LINGÜÍSTICAS"
    )

    cases = [
        (
            "¿Cuántas cirugías generales se han realizado?",
            "CIRUGIA GENERAL",
        ),
        (
            "¿Cuántas cirugías plásticas se han realizado?",
            "CIRUGIA PLASTICA",
        ),
        (
            "¿Cuántas cirugías de ortopedia y traumatología hubo?",
            "ORTOPEDIA Y TRAUMATOLOGIA",
        ),
    ]

    for question, value in cases:

        score = phrase_match_score(
            question,
            value,
        )

        print(
            value,
            "=>",
            score,
        )

        assert score >= 0.82


    print(
        "\nTEST 3 - ESTRUCTURA DEL TREEMAP"
    )

    payload = json.loads(
        VISUAL_METRICS_CATALOG
        .read_text(
            encoding="utf-8"
        )
    )

    found = False

    for page in payload.get(
        "pages",
        [],
    ):

        if (
            page.get(
                "page_display_name"
            )
            != "ESPECIALIDADES CIRUGIA"
        ):
            continue

        for visual in page.get(
            "visuals",
            [],
        ):

            if (
                visual.get(
                    "visual_title"
                )
                !=
                "CIRUGÍAS REALIZADAS POR ESPECIALIDAD"
            ):
                continue

            fields = (
                visual.get(
                    "fields",
                    [],
                )
            )

            has_specialty = any(
                field.get(
                    "table"
                )
                == "CIRUGIAS"
                and field.get(
                    "column"
                )
                == "ESPECIALIDAD"
                for field in fields
            )

            has_count = any(
                metric.get(
                    "dax_expression"
                )
                ==
                "COUNT('CIRUGIAS'[INGRESO])"
                for metric in visual.get(
                    "metrics",
                    [],
                )
            )

            print(
                "ESPECIALIDAD:",
                has_specialty
            )

            print(
                "COUNT INGRESO:",
                has_count
            )

            assert has_specialty
            assert has_count

            found = True

    assert found

    print(
        "\nTODAS LAS PRUEBAS ESTÁTICAS PASARON."
    )


if __name__ == "__main__":
    main()

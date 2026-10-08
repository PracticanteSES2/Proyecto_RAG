import json
from pathlib import Path

from src.semantic.master_metric_resolver import (
    MasterMetricResolver,
)
from src.semantic.source_model_router import (
    SourceModelRouter,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent [1]
)

MASTER = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "master_metrics.json"
)

SOURCE_REGISTRY = (
    PROJECT_ROOT
    / "data"
    / "catalog"
    / "source_registry.json"
)

VISUALS = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "visual_metrics_catalog.json"
)

QUESTION = (
    "Cuantos egresos probables hay "
    "por el servicio de urgencias?"
)


def main():
    router = SourceModelRouter(
        SOURCE_REGISTRY,
        VISUALS,
        project_root=
            PROJECT_ROOT,
    )

    source_context = router.resolve(
        question=QUESTION,
        dashboard="URGENCIAS",
    )

    print(
        "\nSOURCE CONTEXT:"
    )
    print(
        json.dumps(
            source_context,
            ensure_ascii=False,
            indent=2,
        )
    )

    # Solo contexto fuerte puede fijar modelo/reporte.
    strong = (
        source_context.get(
            "status"
        )
        == "resolved"
        and source_context.get(
            "routing_strength"
        )
        == "strong"
    )

    resolver = MasterMetricResolver(
        MASTER
    )

    result = resolver.resolve(
        question=QUESTION,
        semantic_model=(
            source_context.get(
                "semantic_model"
            )
            if strong
            else None
        ),
        report=(
            source_context.get(
                "report"
            )
            if strong
            else None
        ),
    )

    print(
        "\nMASTER METRIC:"
    )
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    if (
        result.get(
            "status"
        )
        != "resolved"
    ):
        raise AssertionError(
            "La métrica no quedó resuelta."
        )

    metric = result.get(
        "metric",
        {},
    )

    if (
        metric.get(
            "label"
        )
        != "EGRESOS PROBABLES"
    ):
        raise AssertionError(
            "Se esperaba EGRESOS PROBABLES "
            f"y llegó {metric.get('label')!r}."
        )

    if (
        metric.get(
            "semantic_model"
        )
        != "BRIEFING HOSPITALARIO"
    ):
        raise AssertionError(
            "La métrica debe pertenecer a "
            "BRIEFING HOSPITALARIO."
        )

    print(
        "\nRESOLUCIÓN SEMÁNTICA V3: OK"
    )


if __name__ == "__main__":
    main()

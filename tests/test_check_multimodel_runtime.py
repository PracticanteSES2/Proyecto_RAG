import json
from pathlib import Path

from src.semantic.source_model_router import (
    SourceModelRouter,
)
from src.semantic.master_metric_resolver import (
    MasterMetricResolver,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
)

SOURCE_REGISTRY = (
    PROJECT_ROOT
    / "data"
    / "catalog"
    / "source_registry.json"
)

VISUAL_METRICS = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "visual_metrics_catalog.json"
)

MASTER_METRICS = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "master_metrics.json"
)


def main():
    router = SourceModelRouter(
        SOURCE_REGISTRY,
        VISUAL_METRICS,
        project_root=
            PROJECT_ROOT,
    )

    resolver = MasterMetricResolver(
        MASTER_METRICS
    )

    print(
        "\nMODELOS ENRUTABLES:"
    )

    for model in router.semantic_models():
        print(
            " -",
            model,
        )

    print(
        "\nPRUEBA DE RUTA BRIEFING:"
    )

    route = router.resolve(
        question=(
            "¿Qué indicadores tiene "
            "el Briefing Hospitalario?"
        )
    )

    print(
        json.dumps(
            route,
            ensure_ascii=False,
            indent=2,
        )
    )

    if (
        route.get(
            "semantic_model"
        )
        != "BRIEFING HOSPITALARIO"
    ):
        raise AssertionError(
            "Briefing no fue enrutado a "
            "BRIEFING HOSPITALARIO."
        )

    print(
        "\nMÉTRICAS POR MODELO:"
    )

    payload = json.loads(
        MASTER_METRICS.read_text(
            encoding="utf-8"
        )
    )

    counts = {}

    for metric in payload.get(
        "metrics",
        [],
    ):
        model = metric.get(
            "semantic_model"
        )

        counts[model] = (
            counts.get(
                model,
                0,
            )
            + 1
        )

    for model, count in sorted(
        counts.items(),
        key=lambda item:
            str(item[0]),
    ):
        print(
            f" - {model}: {count}"
        )

    print(
        "\nVALIDACIÓN MULTI-MODELO LOCAL: OK"
    )


if __name__ == "__main__":
    main()

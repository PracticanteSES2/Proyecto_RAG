import json
import tempfile
from pathlib import Path

from src.semantic.source_model_router import (
    SourceModelRouter,
)
from src.semantic.master_metric_resolver import (
    MasterMetricResolver,
)


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)

        catalog_dir = (
            root
            / "data"
            / "catalog"
        )

        rag_dir = (
            root
            / "data"
            / "rag"
        )

        catalog_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        rag_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        for key in (
            "atenciones",
            "briefing_hospitalario",
        ):
            (
                catalog_dir
                / f"{key}_rag.json"
            ).write_text(
                json.dumps({
                    "semantic_model":
                        key,
                    "tables":
                        [],
                }),
                encoding="utf-8",
            )

        registry = {
            "models": [
                {
                    "semantic_model":
                        "ATENCIONES",
                    "semantic_model_key":
                        "atenciones",
                    "technical_catalog":
                        "data/catalog/atenciones_rag.json",
                },
                {
                    "semantic_model":
                        "BRIEFING HOSPITALARIO",
                    "semantic_model_key":
                        "briefing_hospitalario",
                    "technical_catalog":
                        "data/catalog/briefing_hospitalario_rag.json",
                },
            ],
            "sources": [
                {
                    "source_group":
                        "tablero_atenciones",
                    "report":
                        "ATENCIONES",
                    "semantic_model":
                        "ATENCIONES",
                    "aliases":
                        ["atenciones"],
                    "technical_catalog":
                        "data/catalog/atenciones_rag.json",
                },
                {
                    "source_group":
                        "tablero_briefing_hospitalario",
                    "report":
                        "BRIEFING HOSPITALARIO",
                    "semantic_model":
                        "BRIEFING HOSPITALARIO",
                    "aliases":
                        [
                            "briefing",
                            "briefing hospitalario",
                        ],
                    "technical_catalog":
                        "data/catalog/briefing_hospitalario_rag.json",
                },
            ],
        }

        (
            catalog_dir
            / "source_registry.json"
        ).write_text(
            json.dumps(
                registry
            ),
            encoding="utf-8",
        )

        visual = {
            "schema_version": 2,
            "reports": [
                {
                    "report":
                        "BRIEFING HOSPITALARIO",
                    "semantic_model":
                        "BRIEFING HOSPITALARIO",
                    "source_group":
                        "tablero_briefing_hospitalario",
                    "pages": [
                        {
                            "page_name":
                                "p1",
                            "page_display_name":
                                "MEDICAMENTOS DESABASTECIDOS",
                        }
                    ],
                    "metrics":
                        [],
                }
            ],
            "metrics":
                [],
        }

        (
            rag_dir
            / "visual_metrics_catalog.json"
        ).write_text(
            json.dumps(
                visual
            ),
            encoding="utf-8",
        )

        router = SourceModelRouter(
            catalog_dir
            / "source_registry.json",
            rag_dir
            / "visual_metrics_catalog.json",
            project_root=
                root,
        )

        resolved = router.resolve(
            question=(
                "¿Cuántos casos hay en "
                "Briefing Hospitalario?"
            )
        )

        assert (
            resolved[
                "status"
            ]
            == "resolved"
        )

        assert (
            resolved[
                "semantic_model"
            ]
            ==
            "BRIEFING HOSPITALARIO"
        )

        page_resolved = (
            router.resolve(
                dashboard=
                    "MEDICAMENTOS DESABASTECIDOS"
            )
        )

        assert (
            page_resolved[
                "semantic_model"
            ]
            ==
            "BRIEFING HOSPITALARIO"
        )

        master = {
            "metrics": [
                {
                    "metric_id":
                        "a1",
                    "label":
                        "TOTAL CASOS",
                    "aliases":
                        [],
                    "source_type":
                        "visual_aggregation",
                    "semantic_model":
                        "ATENCIONES",
                    "report":
                        "ATENCIONES",
                    "reports":
                        ["ATENCIONES"],
                    "aggregation":
                        "Count",
                    "validation_status":
                        "approved",
                    "appearances": [
                        {
                            "report":
                                "ATENCIONES",
                            "page_display_name":
                                "GENERAL",
                        }
                    ],
                },
                {
                    "metric_id":
                        "b1",
                    "label":
                        "TOTAL CASOS",
                    "aliases":
                        [],
                    "source_type":
                        "visual_aggregation",
                    "semantic_model":
                        "BRIEFING HOSPITALARIO",
                    "report":
                        "BRIEFING HOSPITALARIO",
                    "reports":
                        [
                            "BRIEFING HOSPITALARIO"
                        ],
                    "aggregation":
                        "Count",
                    "validation_status":
                        "approved",
                    "appearances": [
                        {
                            "report":
                                "BRIEFING HOSPITALARIO",
                            "page_display_name":
                                "MEDICAMENTOS DESABASTECIDOS",
                        }
                    ],
                },
            ]
        }

        master_path = (
            rag_dir
            / "master_metrics.json"
        )

        master_path.write_text(
            json.dumps(
                master
            ),
            encoding="utf-8",
        )

        resolver = MasterMetricResolver(
            master_path
        )

        result = resolver.resolve(
            question=(
                "¿Cuántos total casos hay "
                "en Briefing Hospitalario?"
            ),
            semantic_model=
                "BRIEFING HOSPITALARIO",
            report=
                "BRIEFING HOSPITALARIO",
        )

        assert (
            result["status"]
            == "resolved"
        )

        assert (
            result["metric"][
                "semantic_model"
            ]
            ==
            "BRIEFING HOSPITALARIO"
        )

    print(
        "PRUEBA RUNTIME MULTI-MODELO: OK"
    )


if __name__ == "__main__":
    main()

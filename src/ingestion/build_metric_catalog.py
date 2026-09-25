import argparse
from pathlib import Path

from src.semantic.visual_catalog_builder import (
    PBIRVisualCatalogBuilder
)

from src.semantic.master_metric_catalog_builder import (
    MasterMetricCatalogBuilder
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extrae métricas de visuales PBIR y "
            "construye un catálogo maestro."
        )
    )

    parser.add_argument(
        "--report",
        required=True,
        help=(
            "Ruta a la carpeta *.Report "
            "o a su carpeta definition."
        ),
    )

    parser.add_argument(
        "--metadata",
        required=True,
        help=(
            "Ruta a data/model_metadata/"
            "tablero_de_atenciones_institucionales"
        ),
    )

    parser.add_argument(
        "--semantic-model",
        default=(
            "TABLERO DE ATENCIONES "
            "INSTITUCIONALES"
        ),
    )

    parser.add_argument(
        "--output-dir",
        default="data/catalog",
    )

    args = parser.parse_args()

    output_dir = Path(
        args.output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    visual_output = (
        output_dir
        / "data"
        / "rag"
        / "visual_metrics_catalog.json"
    )

    master_output = (
        output_dir
        / "data"
        / "rag"
        / "master_metrics.json"
    )

    visual_builder = (
        PBIRVisualCatalogBuilder(
            report_path=args.report,
            metadata_dir=args.metadata,
            semantic_model=
                args.semantic_model,
        )
    )

    visual_catalog = (
        visual_builder.save(
            visual_output
        )
    )

    print(
        "\nCATÁLOGO DE VISUALES"
    )

    print(
        visual_catalog["stats"]
    )

    master_builder = (
        MasterMetricCatalogBuilder(
            visual_catalog_path=
                visual_output,
            measures_csv=(
                Path(args.metadata)
                / "measures.csv"
            ),
            semantic_model=
                args.semantic_model,
        )
    )

    master_catalog = (
        master_builder.save(
            master_output
        )
    )

    print(
        "\nCATÁLOGO MAESTRO"
    )

    print(
        master_catalog["stats"]
    )

    print(
        "\nArchivos generados:"
    )

    print(
        visual_output
    )

    print(
        master_output
    )


if __name__ == "__main__":
    main()

import json
import tempfile
from pathlib import Path

from src.semantic.visual_catalog_builder import (
    PBIRVisualCatalogBuilder
)


def main():
    with tempfile.TemporaryDirectory() as temp:
        report = (
            Path(temp)
            / "Demo.Report"
        )

        visual_dir = (
            report
            / "definition"
            / "pages"
            / "page1"
            / "visuals"
            / "visual1"
        )

        visual_dir.mkdir(
            parents=True
        )

        page_json = {
            "name": "page1",
            "displayName":
                "CONSULTAS PRIORITARIAS",
        }

        (
            visual_dir.parent.parent
            / "page.json"
        ).write_text(
            json.dumps(
                page_json
            ),
            encoding="utf-8",
        )

        visual_json = {
            "name": "visual1",
            "visual": {
                "visualType":
                    "lineChart",
                "query": {
                    "queryState": {
                        "Y": {
                            "projections": [
                                {
                                    "field": {
                                        "Aggregation": {
                                            "Expression": {
                                                "Column": {
                                                    "Expression": {
                                                        "SourceRef": {
                                                            "Entity":
                                                                "CONSULTAS PRIORITARIAS"
                                                        }
                                                    },
                                                    "Property":
                                                        "ASEGURADOR"
                                                }
                                            },
                                            "Function": 5
                                        }
                                    },
                                    "queryRef":
                                        "Count(CONSULTAS PRIORITARIAS.ASEGURADOR)",
                                    "nativeQueryRef":
                                        "Recuento de ASEGURADOR"
                                }
                            ]
                        }
                    }
                },
                "visualContainerObjects": {
                    "title": [
                        {
                            "properties": {
                                "text": {
                                    "expr": {
                                        "Literal": {
                                            "Value":
                                                "'PACIENTES OBSERVADOS POR MES'"
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            }
        }

        (
            visual_dir
            / "visual.json"
        ).write_text(
            json.dumps(
                visual_json
            ),
            encoding="utf-8",
        )

        builder = (
            PBIRVisualCatalogBuilder(
                report_path=report,
                semantic_model=(
                    "TABLERO DE ATENCIONES "
                    "INSTITUCIONALES"
                ),
            )
        )

        catalog = (
            builder.build()
        )

        metric = (
            catalog["metrics"][0]
        )

        print(
            "\nMÉTRICA DETECTADA:"
        )

        print(
            json.dumps(
                metric,
                indent=2,
                ensure_ascii=False,
            )
        )

        assert (
            metric["aggregation"]
            == "Count"
        )

        assert (
            metric["dax_expression"]
            ==
            "COUNT('CONSULTAS PRIORITARIAS'[ASEGURADOR])"
        )

        assert (
            "PACIENTES OBSERVADOS"
            in metric["aliases"]
        )

        print(
            "\nTEST OK"
        )


if __name__ == "__main__":
    main()

import csv
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


def normalize_text(value):
    value = str(value or "").lower().strip()

    value = "".join(
        char
        for char in unicodedata.normalize(
            "NFD",
            value,
        )
        if unicodedata.category(char) != "Mn"
    )

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def make_id(*parts):
    raw = "|".join(
        normalize_text(part)
        for part in parts
        if part
    )

    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:16]


class MasterMetricCatalogBuilder:

    def __init__(
        self,
        visual_catalog_path,
        measures_csv=None,
        semantic_model=None,
    ):
        self.visual_catalog_path = Path(
            visual_catalog_path
        )

        self.measures_csv = (
            Path(measures_csv)
            if measures_csv
            else None
        )

        self.semantic_model = (
            semantic_model
        )

    def _canonical_key(
        self,
        value,
    ):
        return re.sub(
            r"[^a-z0-9]",
            "",
            normalize_text(value),
        )

    def _canonical_row(
        self,
        row,
    ):
        return {
            self._canonical_key(key):
                value
            for key, value
            in row.items()
        }

    def _get(
        self,
        row,
        *names,
    ):
        canonical = (
            self._canonical_row(
                row
            )
        )

        for name in names:
            value = canonical.get(
                self._canonical_key(
                    name
                )
            )

            if (
                value is not None
                and str(value).strip()
            ):
                return str(
                    value
                ).strip()

        return None

    def _is_valid_alias(
        self,
        value
    ):
        if value is None:
            return False

        text = normalize_text(
            value
        )

        if not text:
            return False

        if text in {
            "true",
            "false",
            "none",
            "null",
            "yes",
            "no"
        }:
            return False

        # Año o número aislado
        if text.isdigit():
            return False

        # Alias excesivamente corto
        if len(text) < 3:
            return False

        return True

    def _load_explicit_measures(
        self,
    ):
        if (
            not self.measures_csv
            or not self.measures_csv.exists()
        ):
            return []

        with open(
            self.measures_csv,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            rows = list(
                csv.DictReader(file)
            )

        metrics = []

        for row in rows:
            measure = self._get(
                row,
                "Name",
                "Measure",
                "MeasureName",
            )

            if not measure:
                continue

            table = self._get(
                row,
                "Table",
                "TableName",
                "Entity",
            )

            expression = self._get(
                row,
                "Expression",
                "DAX",
            )

            description = self._get(
                row,
                "Description",
            )

            metrics.append(
                {
                    "metric_id":
                        make_id(
                            "measure",
                            table,
                            measure,
                        ),
                    "label":
                        measure,
                    "aliases":
                        [measure],
                    "source_type":
                        "explicit_measure",
                    "semantic_model":
                        self.semantic_model,
                    "table":
                        table,
                    "measure":
                        measure,
                    "column":
                        None,
                    "aggregation":
                        None,
                    "dax_expression":
                        f"[{measure}]",
                    "model_expression":
                        expression,
                    "description":
                        description,
                    "validation_status":
                        "approved",
                    "appearances":
                        [],
                }
            )

        return metrics

    def _merge_unique(
        self,
        target,
        values,
    ):
        seen = {
            normalize_text(value)
            for value in target
            if value
        }

        for value in values:
            if not self._is_valid_alias(
                value):
                continue

            key = normalize_text(
                value
            )

            if (
                key
                and key not in seen
            ):
                target.append(value)
                seen.add(key)

    def build(self):
        visual_catalog = json.loads(
            self.visual_catalog_path
            .read_text(
                encoding="utf-8"
            )
        )

        semantic_model = (
            self.semantic_model
            or visual_catalog.get(
                "semantic_model"
            )
        )

        explicit_metrics = (
            self._load_explicit_measures()
        )

        # Índice para combinar apariciones visuales
        # de medidas explícitas ya existentes.
        explicit_index = {}

        for metric in explicit_metrics:
            key = (
                normalize_text(
                    metric.get("table")
                ),
                normalize_text(
                    metric.get("measure")
                ),
            )

            explicit_index[key] = metric

        aggregation_index = {}

        for visual_metric in (
            visual_catalog.get(
                "metrics",
                []
            )
        ):
            appearance = {
                "page_name":
                    visual_metric.get(
                        "page_name"
                    ),
                "page_display_name":
                    visual_metric.get(
                        "page_display_name"
                    ),
                "visual_id":
                    visual_metric.get(
                        "visual_id"
                    ),
                "visual_title":
                    visual_metric.get(
                        "visual_title"
                    ),
                "visual_type":
                    visual_metric.get(
                        "visual_type"
                    ),
                "role":
                    visual_metric.get(
                        "role"
                    ),
                "query_ref":
                    visual_metric.get(
                        "query_ref"
                    ),
            }

            if (
                visual_metric.get(
                    "kind"
                )
                == "measure"
            ):
                key = (
                    normalize_text(
                        visual_metric.get(
                            "table"
                        )
                    ),
                    normalize_text(
                        visual_metric.get(
                            "measure"
                        )
                    ),
                )

                metric = (
                    explicit_index.get(
                        key
                    )
                )

                if metric is None:
                    # Medida usada por un visual pero no
                    # encontrada en measures.csv.
                    metric = {
                        "metric_id":
                            make_id(
                                "measure",
                                visual_metric.get(
                                    "table"
                                ),
                                visual_metric.get(
                                    "measure"
                                ),
                            ),
                        "label":
                            visual_metric.get(
                                "measure"
                            ),
                        "aliases": [],
                        "source_type":
                            "explicit_measure",
                        "semantic_model":
                            semantic_model,
                        "table":
                            visual_metric.get(
                                "table"
                            ),
                        "measure":
                            visual_metric.get(
                                "measure"
                            ),
                        "column":
                            None,
                        "aggregation":
                            None,
                        "dax_expression":
                            visual_metric.get(
                                "dax_expression"
                            ),
                        "model_expression":
                            None,
                        "description":
                            None,
                        "validation_status":
                            visual_metric.get(
                                "validation_status",
                                "needs_review",
                            ),
                        "appearances":
                            [],
                    }

                    explicit_metrics.append(
                        metric
                    )

                    explicit_index[
                        key
                    ] = metric

                self._merge_unique(
                    metric["aliases"],
                    visual_metric.get(
                        "aliases",
                        [],
                    ),
                )

                metric[
                    "appearances"
                ].append(
                    appearance
                )

                continue

            if (
                visual_metric.get(
                    "kind"
                )
                != "aggregation"
            ):
                continue

            key = (
                normalize_text(
                    visual_metric.get(
                        "table"
                    )
                ),
                normalize_text(
                    visual_metric.get(
                        "column"
                    )
                ),
                normalize_text(
                    visual_metric.get(
                        "aggregation"
                    )
                ),
                normalize_text(
                    visual_metric.get(
                        "page_display_name"
                    )
                ),
            )

            metric = (
                aggregation_index.get(
                    key
                )
            )

            if metric is None:
                label = (
                    visual_metric.get(
                        "visual_title"
                    )
                    or
                    visual_metric.get(
                        "native_query_ref"
                    )
                    or
                    (
                        f"{visual_metric.get('aggregation')} "
                        f"de {visual_metric.get('column')}"
                    )
                )

                metric = {
                    "metric_id":
                        make_id(
                            "visual_aggregation",
                            *key,
                        ),
                    "label":
                        label,
                    "aliases":
                        [],
                    "source_type":
                        "visual_aggregation",
                    "semantic_model":
                        semantic_model,
                    "dashboard":
                        visual_metric.get(
                            "page_display_name"
                        ),
                    "table":
                        visual_metric.get(
                            "table"
                        ),
                    "measure":
                        None,
                    "column":
                        visual_metric.get(
                            "column"
                        ),
                    "aggregation":
                        visual_metric.get(
                            "aggregation"
                        ),
                    "aggregation_id":
                        visual_metric.get(
                            "aggregation_id"
                        ),
                    "dax_expression":
                        visual_metric.get(
                            "dax_expression"
                        ),
                    "validation_status":
                        visual_metric.get(
                            "validation_status",
                            "needs_review",
                        ),
                    "appearances":
                        [],
                }

                aggregation_index[
                    key
                ] = metric

            self._merge_unique(
                metric["aliases"],
                visual_metric.get(
                    "aliases",
                    [],
                ),
            )

            metric[
                "appearances"
            ].append(
                appearance
            )

        metrics = (
            explicit_metrics
            + list(
                aggregation_index.values()
            )
        )

        approved = sum(
            1
            for metric in metrics
            if metric.get(
                "validation_status"
            )
            == "approved"
        )

        return {
            "semantic_model":
                semantic_model,
            "stats": {
                "metrics":
                    len(metrics),
                "explicit_measures":
                    sum(
                        1
                        for metric in metrics
                        if metric.get(
                            "source_type"
                        )
                        == "explicit_measure"
                    ),
                "visual_aggregations":
                    sum(
                        1
                        for metric in metrics
                        if metric.get(
                            "source_type"
                        )
                        == "visual_aggregation"
                    ),
                "approved":
                    approved,
                "needs_review":
                    len(metrics)
                    - approved,
            },
            "metrics":
                metrics,
        }

    def save(
        self,
        output_path,
    ):
        catalog = self.build()

        output_path = Path(
            output_path
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path.write_text(
            json.dumps(
                catalog,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return catalog

import csv
import hashlib
import json
import re
import unicodedata
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
        if part is not None
    )

    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:16]


def _canonical_key(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        normalize_text(value),
    )


def _canonical_row(row):
    return {
        _canonical_key(key): value
        for key, value in row.items()
    }


def _get(row, *names):
    canonical = _canonical_row(row)

    for name in names:
        value = canonical.get(
            _canonical_key(name)
        )

        if (
            value is not None
            and str(value).strip()
        ):
            return str(value).strip()

    return None


def _valid_alias(value):
    text = normalize_text(value)

    if not text:
        return False

    if text in {
        "true",
        "false",
        "none",
        "null",
        "yes",
        "no",
    }:
        return False

    if text.isdigit():
        return False

    return len(text) >= 3


def _merge_aliases(target, values):
    seen = {
        normalize_text(value)
        for value in target
        if value
    }

    for value in values or []:
        if not _valid_alias(value):
            continue

        key = normalize_text(value)

        if key not in seen:
            target.append(value)
            seen.add(key)


def _append_unique(target, value):
    if not value:
        return

    key = normalize_text(value)

    if not any(
        normalize_text(item) == key
        for item in target
    ):
        target.append(value)


def _load_measures_csv(path):
    path = Path(path)

    if not path.exists():
        return []

    with open(
        path,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(
            csv.DictReader(file)
        )


def _load_json(path, default=None):
    path = Path(path)

    if not path.exists():
        return default

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def build_global_master_metrics(
    visual_catalog,
    model_lookup,
    output_path,
    existing_master_path=None,
    rebuilt_semantic_models=None,
):
    """
    Construye un único master_metrics.json para múltiples modelos.

    - Las medidas explícitas se identifican por:
      semantic_model + table + measure
    - Las agregaciones visuales se identifican por:
      semantic_model + report + page + table + column + aggregation
    - Si existe un master_metrics previo, conserva los modelos que NO se
      reconstruyeron en esta ejecución. Esto permite incorporar BRIEFING
      sin perder el catálogo ya validado de Atenciones Institucionales.
    """
    output_path = Path(output_path)

    rebuilt_semantic_models = {
        normalize_text(value)
        for value in (
            rebuilt_semantic_models
            or []
        )
        if value
    }

    preserved = []

    if existing_master_path:
        existing = _load_json(
            existing_master_path,
            default={},
        ) or {}

        for metric in existing.get(
            "metrics",
            [],
        ):
            model_norm = normalize_text(
                metric.get(
                    "semantic_model"
                )
            )

            if (
                model_norm
                and model_norm
                not in rebuilt_semantic_models
            ):
                preserved.append(metric)

    explicit_index = {}
    aggregation_index = {}

    # 1) Medidas explícitas de modelos realmente reconstruidos.
    for semantic_model, model_info in (
        model_lookup.items()
    ):
        if (
            normalize_text(
                semantic_model
            )
            not in rebuilt_semantic_models
        ):
            continue

        measures_csv = (
            Path(
                model_info[
                    "metadata_path"
                ]
            )
            / "measures.csv"
        )

        for row in _load_measures_csv(
            measures_csv
        ):
            measure = _get(
                row,
                "Name",
                "Measure",
                "MeasureName",
            )

            if not measure:
                continue

            table = _get(
                row,
                "Table",
                "TableName",
                "Entity",
            )

            expression = _get(
                row,
                "Expression",
                "DAX",
            )

            description = _get(
                row,
                "Description",
            )

            key = (
                normalize_text(
                    semantic_model
                ),
                normalize_text(table),
                normalize_text(measure),
            )

            explicit_index[key] = {
                "metric_id":
                    make_id(
                        "measure",
                        semantic_model,
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
                    semantic_model,
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
                "reports":
                    [],
                "source_groups":
                    [],
                "appearances":
                    [],
            }

    # 2) Enriquecer desde todos los bindings visuales nuevos.
    for visual_metric in visual_catalog.get(
        "metrics",
        [],
    ):
        semantic_model = (
            visual_metric.get(
                "semantic_model"
            )
        )

        if (
            normalize_text(
                semantic_model
            )
            not in rebuilt_semantic_models
        ):
            continue

        report = visual_metric.get(
            "report"
        )
        source_group = visual_metric.get(
            "source_group"
        )

        appearance = {
            "report":
                report,
            "source_group":
                source_group,
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
                    semantic_model
                ),
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

            metric = explicit_index.get(
                key
            )

            if metric is None:
                measure = visual_metric.get(
                    "measure"
                )
                table = visual_metric.get(
                    "table"
                )

                metric = {
                    "metric_id":
                        make_id(
                            "measure",
                            semantic_model,
                            table,
                            measure,
                        ),
                    "label":
                        measure,
                    "aliases":
                        [],
                    "source_type":
                        "explicit_measure",
                    "semantic_model":
                        semantic_model,
                    "table":
                        table,
                    "measure":
                        measure,
                    "column":
                        None,
                    "aggregation":
                        None,
                    "dax_expression":
                        visual_metric.get(
                            "dax_expression"
                        )
                        or (
                            f"[{measure}]"
                            if measure
                            else None
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
                    "reports":
                        [],
                    "source_groups":
                        [],
                    "appearances":
                        [],
                }

                explicit_index[
                    key
                ] = metric

            _merge_aliases(
                metric["aliases"],
                [
                    visual_metric.get(
                        "visual_title"
                    ),
                    visual_metric.get(
                        "native_query_ref"
                    ),
                    visual_metric.get(
                        "query_ref"
                    ),
                    *(
                        visual_metric.get(
                            "aliases",
                            [],
                        )
                        or []
                    ),
                ],
            )

            _append_unique(
                metric["reports"],
                report,
            )
            _append_unique(
                metric["source_groups"],
                source_group,
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

        # Una misma métrica visual puede aparecer en varias páginas
        # del mismo informe. La identidad de negocio no debe depender
        # de la página, sino de:
        #   modelo + informe + etiqueta de negocio + DAX real.
        #
        # Esto evita duplicados como "EGRESOS PROBABLES" cuando el
        # mismo DISTINCTCOUNT se muestra en INICIO y en la página
        # EGRESOS PROBABLES.
        key = (
            normalize_text(
                semantic_model
            ),
            normalize_text(report),
            normalize_text(label),
            normalize_text(
                visual_metric.get(
                    "dax_expression"
                )
            ),
        )

        metric = aggregation_index.get(
            key
        )

        if metric is None:

            metric = {
                "metric_id":
                    make_id(
                        "visual_aggregation",
                        semantic_model,
                        report,
                        label,
                        visual_metric.get(
                            "dax_expression"
                        ),
                    ),
                "label":
                    label,
                "aliases":
                    [],
                "source_type":
                    "visual_aggregation",
                "semantic_model":
                    semantic_model,
                "report":
                    report,
                "source_group":
                    source_group,
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
                "reports":
                    [report]
                    if report
                    else [],
                "source_groups":
                    [source_group]
                    if source_group
                    else [],
                "appearances":
                    [],
            }

            aggregation_index[
                key
            ] = metric

        _merge_aliases(
            metric["aliases"],
            [
                visual_metric.get(
                    "visual_title"
                ),
                visual_metric.get(
                    "native_query_ref"
                ),
                visual_metric.get(
                    "query_ref"
                ),
                *(
                    visual_metric.get(
                        "aliases",
                        [],
                    )
                    or []
                ),
            ],
        )

        metric[
            "appearances"
        ].append(
            appearance
        )

    generated = (
        list(
            explicit_index.values()
        )
        +
        list(
            aggregation_index.values()
        )
    )

    metrics = preserved + generated

    # Última deduplicación por metric_id.
    unique_metrics = []
    seen_ids = set()

    for metric in metrics:
        metric_id = metric.get(
            "metric_id"
        )

        if not metric_id:
            metric_id = make_id(
                metric.get(
                    "source_type"
                ),
                metric.get(
                    "semantic_model"
                ),
                metric.get(
                    "report"
                ),
                metric.get(
                    "table"
                ),
                metric.get(
                    "measure"
                ),
                metric.get(
                    "column"
                ),
                metric.get(
                    "aggregation"
                ),
                metric.get(
                    "label"
                ),
            )
            metric[
                "metric_id"
            ] = metric_id

        if metric_id in seen_ids:
            continue

        seen_ids.add(metric_id)
        unique_metrics.append(
            metric
        )

    semantic_models = sorted({
        metric.get(
            "semantic_model"
        )
        for metric in unique_metrics
        if metric.get(
            "semantic_model"
        )
    })

    payload = {
        "schema_version":
            2,
        "semantic_model":
            (
                semantic_models[0]
                if len(
                    semantic_models
                ) == 1
                else None
            ),
        "semantic_models":
            semantic_models,
        "stats": {
            "metrics":
                len(
                    unique_metrics
                ),
            "explicit_measures":
                sum(
                    1
                    for metric
                    in unique_metrics
                    if metric.get(
                        "source_type"
                    )
                    == "explicit_measure"
                ),
            "visual_aggregations":
                sum(
                    1
                    for metric
                    in unique_metrics
                    if metric.get(
                        "source_type"
                    )
                    == "visual_aggregation"
                ),
            "approved":
                sum(
                    1
                    for metric
                    in unique_metrics
                    if metric.get(
                        "validation_status"
                    )
                    == "approved"
                ),
            "preserved_from_previous":
                len(preserved),
            "generated_or_rebuilt":
                len(generated),
        },
        "metrics":
            unique_metrics,
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return payload

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

from src.semantic.model_catalog_builder import (
    build_model_catalog,
)
from src.semantic.visual_catalog_builder import (
    PBIRVisualCatalogBuilder,
)
from src.semantic.global_master_metric_builder import (
    build_global_master_metrics,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


def normalize_text(value):
    value = str(
        value or ""
    ).strip().lower()

    value = "".join(
        char
        for char in unicodedata.normalize(
            "NFD",
            value,
        )
        if unicodedata.category(char)
        != "Mn"
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


def slugify(value):
    return (
        normalize_text(
            value
        ).replace(
            " ",
            "_",
        )
        or "sin_nombre"
    )


def display_name_from_slug(
    value,
):
    return (
        str(value)
        .replace("_", " ")
        .replace("-", " ")
        .strip()
        .upper()
    )


def load_json(
    path,
    default=None,
):
    path = Path(path)

    if not path.exists():
        return default

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save_json(
    data,
    path,
):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


class PowerBICatalogManager:

    def __init__(
        self,
        project_root=None,
    ):
        self.project_root = Path(
            project_root
            or PROJECT_ROOT
        ).resolve()

        self.data_dir = (
            self.project_root
            / "data"
        )

        self.raw_dir = (
            self.data_dir
            / "raw"
        )

        self.metadata_root = (
            self.data_dir
            / "model_metadata"
        )

        self.pbir_root = (
            self.data_dir
            / "pbir"
        )

        self.catalog_dir = (
            self.data_dir
            / "catalog"
        )

        self.visuals_dir = (
            self.catalog_dir
            / "visuals"
        )

        self.rag_dir = (
            self.data_dir
            / "rag"
        )

        self.model_registry_path = (
            self.catalog_dir
            / "model_registry.json"
        )

        self.source_registry_path = (
            self.catalog_dir
            / "source_registry.json"
        )

        self.global_visual_catalog_path = (
            self.rag_dir
            / "visual_metrics_catalog.json"
        )

        self.master_metrics_path = (
            self.rag_dir
            / "master_metrics.json"
        )

    # ========================================================
    # MODELOS
    # ========================================================

    def discover_models(
        self,
    ):
        models_by_key = {}

        registry = load_json(
            self.model_registry_path,
            default={},
        ) or {}

        for item in registry.get(
            "models",
            [],
        ):
            name = item.get(
                "semantic_model"
            )

            key = (
                item.get(
                    "semantic_model_key"
                )
                or slugify(name)
            )

            metadata_path = item.get(
                "metadata_path"
            )

            if metadata_path:
                metadata_path = (
                    self.project_root
                    / metadata_path
                )

            if (
                name
                and metadata_path
                and metadata_path.exists()
            ):
                models_by_key[
                    key
                ] = {
                    "semantic_model":
                        name,
                    "semantic_model_key":
                        key,
                    "metadata_path":
                        metadata_path,
                }

        if self.metadata_root.exists():
            for folder in sorted(
                self.metadata_root.iterdir()
            ):
                if not folder.is_dir():
                    continue

                if not all(
                    (
                        folder
                        / filename
                    ).exists()
                    for filename in (
                        "tables.csv",
                        "columns.csv",
                        "measures.csv",
                        "relationships.csv",
                    )
                ):
                    continue

                sync_info = load_json(
                    folder
                    / "_metadata_sync.json",
                    default={},
                ) or {}

                name = (
                    sync_info.get(
                        "semantic_model"
                    )
                    or display_name_from_slug(
                        folder.name
                    )
                )

                key = folder.name

                models_by_key[
                    key
                ] = {
                    "semantic_model":
                        name,
                    "semantic_model_key":
                        key,
                    "metadata_path":
                        folder,
                }

        return models_by_key

    # ========================================================
    # FUENTES / MANIFESTS
    # ========================================================

    def _load_manifest(
        self,
        folder,
    ):
        path = (
            Path(folder)
            / "manifest.json"
        )

        if not path.exists():
            return {}, None

        return (
            load_json(
                path,
                default={},
            ) or {},
            path,
        )

    EXCLUDED_SEARCH_DIRS = {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        "graphify-out",
        "documentacion",
        "tests",
        ".claude",
    }

    def _is_excluded_path(
        self,
        path,
        root,
    ):
        try:
            parts = path.relative_to(root).parts[:-1]
        except ValueError:
            parts = path.parts[:-1]

        return any(
            part.lower() in self.EXCLUDED_SEARCH_DIRS
            for part in parts
        )

    def _find_pbir_directories(
        self,
    ):
        directories = []
        roots = [
            self.pbir_root,
            self.data_dir
            / "reports",
            self.project_root,
        ]

        seen = set()

        for root in roots:
            if not root.exists():
                continue

            if (
                root.is_dir()
                and root.name.lower().endswith(
                    ".report"
                )
            ):
                candidates = [
                    root
                ]
            else:
                candidates = [
                    path
                    for path in root.rglob(
                        "*.Report"
                    )
                    if path.is_dir()
                    and not self._is_excluded_path(
                        path,
                        root,
                    )
                ]

            for path in candidates:
                key = str(
                    path.resolve()
                ).casefold()

                if key not in seen:
                    directories.append(
                        path.resolve()
                    )
                    seen.add(key)

        return directories

    def _resolve_explicit_path(
        self,
        value,
    ):
        if not value:
            return None

        path = Path(value)

        if not path.is_absolute():
            path = (
                self.project_root
                / path
            )

        return path.resolve()

    def _score_pbir(
        self,
        path,
        *,
        report,
        source_group,
        semantic_model,
        semantic_model_key,
    ):
        name = normalize_text(
            path.name.removesuffix(
                ".Report"
            )
        )

        candidates = {
            normalize_text(
                report
            ): 100,
            normalize_text(
                source_group
            ): 75,
            normalize_text(
                semantic_model
            ): 65,
            normalize_text(
                semantic_model_key
            ): 55,
        }

        score = 0

        for candidate, weight in (
            candidates.items()
        ):
            if not candidate:
                continue

            if name == candidate:
                score = max(
                    score,
                    weight,
                )

            elif (
                name in candidate
                or candidate in name
            ):
                score = max(
                    score,
                    int(
                        weight * 0.65
                    ),
                )

        return score

    def _match_pbir(
        self,
        *,
        manifest,
        report,
        source_group,
        semantic_model,
        semantic_model_key,
        pbir_directories,
    ):
        explicit = (
            manifest.get(
                "pbir_path"
            )
            or
            manifest.get(
                "report_path"
            )
        )

        if explicit:
            path = self._resolve_explicit_path(
                explicit
            )

            if path.exists():
                return path, "manifest"

            return path, "manifest_not_found"

        scored = []

        for path in pbir_directories:
            score = self._score_pbir(
                path,
                report=report,
                source_group=
                    source_group,
                semantic_model=
                    semantic_model,
                semantic_model_key=
                    semantic_model_key,
            )

            if score > 0:
                scored.append(
                    (
                        score,
                        str(path),
                        path,
                    )
                )

        scored.sort(
            reverse=True
        )

        if not scored:
            return None, "not_found"

        if (
            len(scored) > 1
            and scored[0][0]
            == scored[1][0]
        ):
            return None, "ambiguous"

        return scored[0][2], "auto"

    def discover_sources(
        self,
        models_by_key,
    ):
        sources = []

        models_by_name = {
            normalize_text(
                item[
                    "semantic_model"
                ]
            ):
                item
            for item
            in models_by_key.values()
        }

        pbir_directories = (
            self._find_pbir_directories()
        )

        if not self.raw_dir.exists():
            return sources

        for folder in sorted(
            path
            for path
            in self.raw_dir.iterdir()
            if path.is_dir()
        ):
            manifest, manifest_path = (
                self._load_manifest(
                    folder
                )
            )

            source_group = (
                manifest.get(
                    "source_group"
                )
                or folder.name
            )

            report = (
                manifest.get(
                    "report"
                )
                or
                manifest.get(
                    "default_dashboard"
                )
                or
                display_name_from_slug(
                    source_group
                )
            )

            semantic_model = (
                manifest.get(
                    "semantic_model"
                )
            )

            semantic_model_key = (
                manifest.get(
                    "semantic_model_key"
                )
            )

            model_info = None

            if semantic_model_key:
                model_info = (
                    models_by_key.get(
                        semantic_model_key
                    )
                )

            if (
                model_info is None
                and semantic_model
            ):
                model_info = (
                    models_by_name.get(
                        normalize_text(
                            semantic_model
                        )
                    )
                )

            if model_info is None:
                inferred_key = folder.name

                model_info = (
                    models_by_key.get(
                        inferred_key
                    )
                )

            if model_info:
                semantic_model = (
                    model_info[
                        "semantic_model"
                    ]
                )
                semantic_model_key = (
                    model_info[
                        "semantic_model_key"
                    ]
                )

            elif semantic_model:
                semantic_model_key = (
                    semantic_model_key
                    or slugify(
                        semantic_model
                    )
                )

            pbir_path, pbir_match = (
                self._match_pbir(
                    manifest=manifest,
                    report=report,
                    source_group=
                        source_group,
                    semantic_model=
                        semantic_model,
                    semantic_model_key=
                        semantic_model_key,
                    pbir_directories=
                        pbir_directories,
                )
            )

            technical_catalog = (
                (
                    self.catalog_dir
                    / (
                        f"{semantic_model_key}"
                        "_rag.json"
                    )
                )
                if semantic_model_key
                else None
            )

            visual_catalog = (
                self.visuals_dir
                / (
                    f"{slugify(source_group)}"
                    "_visual_metrics.json"
                )
            )

            status = (
                "ready"
                if (
                    semantic_model
                    and semantic_model_key
                    and model_info
                )
                else "needs_manifest_or_metadata"
            )

            sources.append({
                "workspace":
                    manifest.get(
                        "workspace"
                    )
                    or os.getenv(
                        "POWERBI_WORKSPACE_NAME"
                    )
                    or "Gestion Clinica",
                "source_group":
                    source_group,
                "report":
                    report,
                "aliases":
                    manifest.get(
                        "aliases",
                        [],
                    ),
                "default_dashboard":
                    manifest.get(
                        "default_dashboard"
                    )
                    or report,
                "document_type":
                    manifest.get(
                        "document_type",
                        "dashboard_documentation",
                    ),
                "semantic_model":
                    semantic_model,
                "semantic_model_key":
                    semantic_model_key,
                "metadata_path":
                    (
                        str(
                            model_info[
                                "metadata_path"
                            ]
                        )
                        if model_info
                        else None
                    ),
                "technical_catalog":
                    (
                        str(
                            technical_catalog
                        )
                        if technical_catalog
                        else None
                    ),
                "pbir_path":
                    (
                        str(
                            pbir_path
                        )
                        if pbir_path
                        else None
                    ),
                "pbir_match":
                    pbir_match,
                "visual_catalog":
                    str(
                        visual_catalog
                    ),
                "manifest_path":
                    (
                        str(
                            manifest_path
                        )
                        if manifest_path
                        else None
                    ),
                "status":
                    status,
            })

        return sources

    # ========================================================
    # BUILD TÉCNICO
    # ========================================================

    def build_technical_catalogs(
        self,
        sources,
        models_by_key,
    ):
        built = {}

        selected_keys = {
            source.get(
                "semantic_model_key"
            )
            for source in sources
            if source.get(
                "semantic_model_key"
            )
        }

        for key in sorted(
            selected_keys
        ):
            model = models_by_key.get(
                key
            )

            if not model:
                continue

            print(
                "\nConstruyendo catálogo técnico:",
                model[
                    "semantic_model"
                ],
            )

            result = build_model_catalog(
                metadata_dir=
                    model[
                        "metadata_path"
                    ],
                semantic_model_name=
                    model[
                        "semantic_model"
                    ],
                model_slug=
                    key,
                workspace_name=
                    "Gestion Clinica",
                output_dir=
                    self.catalog_dir,
            )

            built[key] = result

        return built

    # ========================================================
    # BUILD VISUAL
    # ========================================================

    def build_visual_catalogs(
        self,
        sources,
    ):
        self.visuals_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        catalogs = []
        rebuilt_models = set()

        for source in sources:
            pbir_path = source.get(
                "pbir_path"
            )

            semantic_model = source.get(
                "semantic_model"
            )

            metadata_path = source.get(
                "metadata_path"
            )

            if (
                not pbir_path
                or not semantic_model
                or not metadata_path
            ):
                print(
                    "\nVisual omitido:",
                    source.get(
                        "source_group"
                    ),
                    "| falta PBIR o metadata.",
                )
                continue

            pbir_path = Path(
                pbir_path
            )

            if not pbir_path.exists():
                print(
                    "\nVisual omitido:",
                    source.get(
                        "source_group"
                    ),
                    "| PBIR no existe:",
                    pbir_path,
                )
                continue

            print(
                "\nProcesando PBIR:",
                source.get(
                    "report"
                ),
            )

            builder = (
                PBIRVisualCatalogBuilder(
                    report_path=
                        pbir_path,
                    metadata_dir=
                        metadata_path,
                    semantic_model=
                        semantic_model,
                )
            )

            catalog = builder.build()

            catalog[
                "workspace"
            ] = source.get(
                "workspace"
            )
            catalog[
                "source_group"
            ] = source.get(
                "source_group"
            )
            catalog[
                "report"
            ] = source.get(
                "report"
            )
            catalog[
                "semantic_model_key"
            ] = source.get(
                "semantic_model_key"
            )

            enriched_metrics = []

            for metric in catalog.get(
                "metrics",
                [],
            ):
                enriched_metrics.append({
                    **metric,
                    "workspace":
                        source.get(
                            "workspace"
                        ),
                    "source_group":
                        source.get(
                            "source_group"
                        ),
                    "report":
                        source.get(
                            "report"
                        ),
                    "semantic_model":
                        semantic_model,
                    "semantic_model_key":
                        source.get(
                            "semantic_model_key"
                        ),
                })

            catalog[
                "metrics"
            ] = enriched_metrics

            output_path = Path(
                source[
                    "visual_catalog"
                ]
            )

            save_json(
                catalog,
                output_path,
            )

            catalogs.append(
                catalog
            )

            rebuilt_models.add(
                semantic_model
            )

            print(
                "  [OK] Páginas:",
                catalog.get(
                    "stats",
                    {},
                ).get(
                    "pages",
                    0,
                ),
                "| métricas visuales:",
                len(
                    enriched_metrics
                ),
            )

        return (
            catalogs,
            rebuilt_models,
        )

    # ========================================================
    # GLOBAL VISUAL
    # ========================================================

    def build_global_visual_catalog(
        self,
        new_catalogs,
        rebuilt_models,
    ):
        existing = load_json(
            self.global_visual_catalog_path,
            default={},
        ) or {}

        rebuilt_norm = {
            normalize_text(
                item
            )
            for item in rebuilt_models
            if item
        }

        # Se reemplaza por source_group (reporte), no por modelo: reconstruir
        # una fuente no debe borrar los reportes hermanos del mismo modelo.
        rebuilt_groups = {
            normalize_text(
                catalog.get(
                    "source_group"
                )
            )
            for catalog in new_catalogs
            if catalog.get(
                "source_group"
            )
        }

        preserved_reports = []

        if (
            existing.get(
                "schema_version"
            )
            == 2
        ):
            for report in existing.get(
                "reports",
                [],
            ):
                group_norm = normalize_text(
                    report.get(
                        "source_group"
                    )
                )

                if group_norm.startswith("legacy "):
                    # Migración de formato antiguo: se reemplaza cuando el
                    # modelo ya se reconstruye con fuentes reales.
                    keep = (
                        normalize_text(
                            report.get(
                                "semantic_model"
                            )
                        )
                        not in rebuilt_norm
                    )

                elif group_norm:
                    keep = (
                        group_norm
                        not in rebuilt_groups
                    )
                else:
                    # Reportes antiguos sin source_group: compatibilidad
                    # por modelo.
                    keep = (
                        normalize_text(
                            report.get(
                                "semantic_model"
                            )
                        )
                        not in rebuilt_norm
                    )

                if keep:
                    preserved_reports.append(
                        report
                    )

        elif existing.get(
            "semantic_model"
        ):
            if (
                normalize_text(
                    existing.get(
                        "semantic_model"
                    )
                )
                not in rebuilt_norm
            ):
                preserved_reports.append({
                    "workspace":
                        existing.get(
                            "workspace"
                        ),
                    "source_group":
                        (
                            "legacy_"
                            + slugify(
                                existing.get(
                                    "semantic_model"
                                )
                            )
                        ),
                    "report":
                        existing.get(
                            "report"
                        )
                        or existing.get(
                            "semantic_model"
                        ),
                    "semantic_model":
                        existing.get(
                            "semantic_model"
                        ),
                    "semantic_model_key":
                        slugify(
                            existing.get(
                                "semantic_model"
                            )
                        ),
                    "stats":
                        existing.get(
                            "stats",
                            {},
                        ),
                    "report_filters":
                        existing.get(
                            "report_filters",
                            [],
                        ),
                    "pages":
                        existing.get(
                            "pages",
                            [],
                        ),
                    "metrics":
                        [
                            {
                                **metric,
                                "report":
                                    existing.get(
                                        "report"
                                    )
                                    or existing.get(
                                        "semantic_model"
                                    ),
                                "source_group":
                                    (
                                        "legacy_"
                                        + slugify(
                                            existing.get(
                                                "semantic_model"
                                            )
                                        )
                                    ),
                                "semantic_model":
                                    existing.get(
                                        "semantic_model"
                                    ),
                            }
                            for metric
                            in existing.get(
                                "metrics",
                                [],
                            )
                        ],
                })

        reports = (
            preserved_reports
            + new_catalogs
        )

        flat_metrics = []

        for report in reports:
            flat_metrics.extend(
                report.get(
                    "metrics",
                    [],
                )
            )

        semantic_models = sorted({
            report.get(
                "semantic_model"
            )
            for report in reports
            if report.get(
                "semantic_model"
            )
        })

        payload = {
            "schema_version":
                2,
            "semantic_models":
                semantic_models,
            "stats": {
                "reports":
                    len(reports),
                "pages":
                    sum(
                        report.get(
                            "stats",
                            {},
                        ).get(
                            "pages",
                            0,
                        )
                        for report
                        in reports
                    ),
                "visuals":
                    sum(
                        report.get(
                            "stats",
                            {},
                        ).get(
                            "visuals",
                            0,
                        )
                        for report
                        in reports
                    ),
                "metric_bindings":
                    len(
                        flat_metrics
                    ),
            },
            "reports":
                reports,
            "metrics":
                flat_metrics,
        }

        save_json(
            payload,
            self.global_visual_catalog_path,
        )

        return payload

    # ========================================================
    # REGISTRY
    # ========================================================

    def save_source_registry(
        self,
        sources,
        models_by_key,
    ):
        def rel(value):
            if not value:
                return None

            path = Path(value)

            try:
                return str(
                    path.resolve()
                    .relative_to(
                        self.project_root
                    )
                ).replace(
                    "\\",
                    "/",
                )
            except Exception:
                return str(value)

        source_payload = []

        for source in sources:
            source_payload.append({
                **source,
                "metadata_path":
                    rel(
                        source.get(
                            "metadata_path"
                        )
                    ),
                "technical_catalog":
                    rel(
                        source.get(
                            "technical_catalog"
                        )
                    ),
                "pbir_path":
                    rel(
                        source.get(
                            "pbir_path"
                        )
                    ),
                "visual_catalog":
                    rel(
                        source.get(
                            "visual_catalog"
                        )
                    ),
                "manifest_path":
                    rel(
                        source.get(
                            "manifest_path"
                        )
                    ),
            })

        models_payload = []

        for model in sorted(
            models_by_key.values(),
            key=lambda item:
                item[
                    "semantic_model"
                ],
        ):
            models_payload.append({
                "semantic_model":
                    model[
                        "semantic_model"
                    ],
                "semantic_model_key":
                    model[
                        "semantic_model_key"
                    ],
                "metadata_path":
                    rel(
                        model[
                            "metadata_path"
                        ]
                    ),
                "technical_catalog":
                    rel(
                        self.catalog_dir
                        / (
                            f"{model['semantic_model_key']}"
                            "_rag.json"
                        )
                    ),
            })

        payload = {
            "schema_version":
                2,
            "workspace":
                "Gestion Clinica",
            "models":
                models_payload,
            "sources":
                source_payload,
        }

        save_json(
            payload,
            self.source_registry_path,
        )

        return payload

    # ========================================================
    # PIPELINE
    # ========================================================

    def run(
        self,
        source_group=None,
    ):
        models_by_key = (
            self.discover_models()
        )

        if not models_by_key:
            raise RuntimeError(
                "No encontré metadata de modelos en "
                "data/model_metadata."
            )

        all_sources = (
            self.discover_sources(
                models_by_key
            )
        )

        if not all_sources:
            raise RuntimeError(
                "No encontré grupos documentales "
                "dentro de data/raw."
            )

        sources = all_sources

        if source_group:
            target = normalize_text(
                source_group
            )

            sources = [
                source
                for source
                in all_sources
                if normalize_text(
                    source.get(
                        "source_group"
                    )
                )
                == target
            ]

            if not sources:
                raise LookupError(
                    "No encontré source_group: "
                    f"{source_group}"
                )

        print(
            "\n========================================"
        )
        print(
            "CATÁLOGOS POWER BI MULTI-MODELO"
        )
        print(
            "========================================"
        )
        print(
            "Modelos con metadata:",
            len(
                models_by_key
            ),
        )
        print(
            "Fuentes seleccionadas:",
            len(
                sources
            ),
        )

        self.build_technical_catalogs(
            sources,
            models_by_key,
        )

        new_visual_catalogs, rebuilt_models = (
            self.build_visual_catalogs(
                sources
            )
        )

        global_visual = (
            self.build_global_visual_catalog(
                new_visual_catalogs,
                rebuilt_models,
            )
        )

        model_lookup = {
            item[
                "semantic_model"
            ]:
                item
            for item
            in models_by_key.values()
        }

        rebuilt_source_groups = {
            catalog.get(
                "source_group"
            )
            for catalog in new_visual_catalogs
            if catalog.get(
                "source_group"
            )
        }

        master = build_global_master_metrics(
            visual_catalog=
                global_visual,
            model_lookup=
                model_lookup,
            output_path=
                self.master_metrics_path,
            existing_master_path=
                self.master_metrics_path,
            rebuilt_semantic_models=
                rebuilt_models,
            rebuilt_source_groups=
                rebuilt_source_groups,
        )

        registry = (
            self.save_source_registry(
                all_sources,
                models_by_key,
            )
        )

        print(
            "\n========================================"
        )
        print(
            "CATÁLOGOS FINALIZADOS"
        )
        print(
            "========================================"
        )
        print(
            "PBIR reconstruidos/procesados:",
            len(
                new_visual_catalogs
            ),
        )
        print(
            "Modelos reconstruidos:",
            len(
                rebuilt_models
            ),
        )
        print(
            "Métricas maestras:",
            len(
                master.get(
                    "metrics",
                    [],
                )
            ),
        )
        print(
            "Registro:",
            self.source_registry_path,
        )

        return {
            "source_registry":
                registry,
            "visual_catalog":
                global_visual,
            "master_metrics":
                master,
        }


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception:
                pass

    parser = argparse.ArgumentParser(
        description=(
            "Construye catálogos técnicos y visuales "
            "multi-modelo sin usar Microsoft Entra."
        )
    )

    parser.add_argument(
        "--source",
        default=None,
        help=(
            "Procesa solo un source_group. "
            "Ej.: tablero_briefing_hospitalario"
        ),
    )

    args = parser.parse_args()

    manager = PowerBICatalogManager()
    manager.run(
        source_group=
            args.source,
    )


if __name__ == "__main__":
    main()

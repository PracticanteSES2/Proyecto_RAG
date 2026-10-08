import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from src.providers.powerbi_provider import PowerBIProvider


PROJECT_ROOT = Path(__file__).resolve().parent


def configure_console_utf8():
    """Evita UnicodeEncodeError con stdout cp1252 o redirigido."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


INFO_VIEW_QUERIES = {
    "tables.csv": "EVALUATE INFO.VIEW.TABLES()",
    "columns.csv": "EVALUATE INFO.VIEW.COLUMNS()",
    "measures.csv": "EVALUATE INFO.VIEW.MEASURES()",
    "relationships.csv": "EVALUATE INFO.VIEW.RELATIONSHIPS()",
}


def normalize_text(value):
    value = str(value or "").strip().lower()
    value = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def slugify(value):
    text = normalize_text(value)
    return text.replace(" ", "_") or "sin_nombre"


def workspace_name_from_endpoint(endpoint):
    endpoint = str(endpoint or "").strip().rstrip("/")

    if not endpoint:
        return None

    marker = "/myorg/"
    lower = endpoint.lower()
    pos = lower.find(marker)

    if pos < 0:
        return None

    return unquote(
        endpoint[pos + len(marker):]
    )


def save_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def write_csv(path, result):
    columns = list(result.get("columns") or [])
    rows = list(result.get("rows") or [])

    if not columns and rows:
        columns = list(rows[0].keys())

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(
        path,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()

        for row in rows:
            writer.writerow({
                column: row.get(column)
                for column in columns
            })


def choose_folder_name(model_name, used):
    base = slugify(model_name)

    if base not in used:
        used.add(base)
        return base

    digest = hashlib.sha1(
        str(model_name).encode("utf-8")
    ).hexdigest()[:8]

    candidate = f"{base}_{digest}"
    used.add(candidate)
    return candidate


class MetadataSynchronizer:

    def __init__(
        self,
        provider=None,
        project_root=None,
    ):
        self.project_root = Path(
            project_root or PROJECT_ROOT
        ).resolve()

        self.provider = (
            provider or PowerBIProvider()
        )

        self.output_root = (
            self.project_root
            / "data"
            / "model_metadata"
        )

        self.registry_path = (
            self.project_root
            / "data"
            / "catalog"
            / "model_registry.json"
        )

    def list_models(self):
        result = self.provider.list_semantic_models()

        if result.get("status") != "success":
            raise RuntimeError(
                "No se pudieron listar los modelos semánticos: "
                f"{result.get('error')}"
            )

        models = [
            str(model).strip()
            for model in result.get("models", [])
            if str(model).strip()
        ]

        seen = set()
        unique = []

        for model in models:
            key = model.casefold()

            if key in seen:
                continue

            seen.add(key)
            unique.append(model)

        return unique

    def _selected_models(
        self,
        all_models,
        requested_models,
    ):
        if not requested_models:
            return all_models

        lookup = {
            model.casefold(): model
            for model in all_models
        }

        selected = []
        missing = []

        for requested in requested_models:
            exact = lookup.get(
                str(requested).strip().casefold()
            )

            if exact:
                selected.append(exact)
            else:
                missing.append(requested)

        if missing:
            raise LookupError(
                "No encontré estos modelos en el workspace: "
                + ", ".join(missing)
            )

        return selected

    def _all_csv_exist(self, model_dir):
        return all(
            (model_dir / filename).exists()
            for filename in INFO_VIEW_QUERIES
        )

    def export_model(
        self,
        model_name,
        model_dir,
        *,
        force=False,
    ):
        model_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        if (
            not force
            and self._all_csv_exist(model_dir)
        ):
            return {
                "status": "skipped",
                "reason": "metadata_exists",
                "files": {
                    filename: str(
                        model_dir / filename
                    )
                    for filename
                    in INFO_VIEW_QUERIES
                },
            }

        file_results = {}
        errors = []

        for filename, dax in INFO_VIEW_QUERIES.items():
            print(f"    {filename}")

            result = self.provider.execute_dax(
                dax=dax,
                semantic_model=model_name,
            )

            if result.get("status") != "success":
                error = (
                    f"{filename}: "
                    f"{result.get('error_type')}: "
                    f"{result.get('error')}"
                )
                errors.append(error)

                file_results[filename] = {
                    "status": "error",
                    "error": error,
                }
                continue

            output_path = model_dir / filename
            write_csv(output_path, result)

            file_results[filename] = {
                "status": "success",
                "rows": result.get(
                    "row_count",
                    len(result.get("rows", [])),
                ),
                "path": str(output_path),
            }

        overall_status = (
            "success"
            if not errors
            else "partial_error"
        )

        save_json(
            {
                "semantic_model": model_name,
                "status": overall_status,
                "files": file_results,
                "errors": errors,
                "synced_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
            model_dir / "_metadata_sync.json",
        )

        return {
            "status": overall_status,
            "files": file_results,
            "errors": errors,
        }

    def sync(
        self,
        *,
        requested_models=None,
        force=False,
        list_only=False,
        fail_fast=False,
    ):
        print("\n" + "=" * 72)
        print("SINCRONIZACIÓN DE MODELOS SEMÁNTICOS POR XMLA")
        print("=" * 72)

        print(
            "Endpoint:",
            self.provider.endpoint,
        )

        workspace_name = workspace_name_from_endpoint(
            self.provider.endpoint
        )

        if workspace_name:
            print(
                "Workspace:",
                workspace_name,
            )

        print("\nDescubriendo modelos semánticos...")

        all_models = self.list_models()

        print(
            f"Modelos encontrados: {len(all_models)}"
        )

        for model in all_models:
            print("  -", model)

        selected = self._selected_models(
            all_models,
            requested_models or [],
        )

        if list_only:
            return {
                "workspace": workspace_name,
                "models": all_models,
                "selected": selected,
            }

        print(
            "\nModelos a procesar:",
            len(selected),
        )

        used_folders = set()
        records = []

        model_to_folder = {}

        for model in all_models:
            folder = choose_folder_name(
                model,
                used_folders,
            )
            model_to_folder[model] = folder

        success_count = 0
        skipped_count = 0
        error_count = 0

        for index, model_name in enumerate(
            selected,
            start=1,
        ):
            folder_name = model_to_folder[
                model_name
            ]

            model_dir = (
                self.output_root
                / folder_name
            )

            print(
                f"\n[{index}/{len(selected)}] "
                f"{model_name}"
            )
            print(
                "  Carpeta:",
                model_dir,
            )

            # Los prints van fuera del try: un fallo de consola no debe
            # marcar el modelo como fallido.
            message = None

            try:
                export_result = self.export_model(
                    model_name,
                    model_dir,
                    force=force,
                )

                status = export_result["status"]

                if status == "success":
                    success_count += 1
                    message = "  [OK] Metadata exportada."

                elif status == "skipped":
                    skipped_count += 1
                    message = (
                        "  [SKIP] Ya existía. "
                        "Usa --force para regenerar."
                    )

                else:
                    error_count += 1
                    message = "  [!] Exportación parcial."

                    if fail_fast:
                        raise RuntimeError(
                            "\n".join(
                                export_result.get(
                                    "errors",
                                    [],
                                )
                            )
                        )

            except Exception as error:
                error_count += 1

                export_result = {
                    "status": "error",
                    "errors": [str(error)],
                }

                message = f"  [ERROR] Error: {error}"

                if fail_fast:
                    print(message)
                    raise

            if message:
                print(message)

            records.append({
                "semantic_model":
                    model_name,
                "semantic_model_key":
                    folder_name,
                "metadata_path":
                    str(
                        model_dir
                        .relative_to(
                            self.project_root
                        )
                    ).replace("\\", "/"),
                "status":
                    export_result.get(
                        "status"
                    ),
                "errors":
                    export_result.get(
                        "errors",
                        [],
                    ),
            })

        registry = {
            "version": 1,
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "workspace": {
                "name": workspace_name,
                "xmla_endpoint":
                    self.provider.endpoint,
            },
            "models": records,
            "summary": {
                "discovered":
                    len(all_models),
                "selected":
                    len(selected),
                "success":
                    success_count,
                "skipped":
                    skipped_count,
                "errors":
                    error_count,
            },
        }

        save_json(
            registry,
            self.registry_path,
        )

        print("\n" + "=" * 72)
        print("SINCRONIZACIÓN FINALIZADA")
        print("=" * 72)
        print(
            "Correctos:",
            success_count,
        )
        print(
            "Omitidos:",
            skipped_count,
        )
        print(
            "Con errores:",
            error_count,
        )
        print(
            "Registro:",
            self.registry_path,
        )

        return registry


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Descubre los modelos semánticos de un workspace "
            "Power BI mediante XMLA y exporta automáticamente "
            "INFO.VIEW.TABLES/COLUMNS/MEASURES/RELATIONSHIPS."
        )
    )

    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help=(
            "Procesa solamente este modelo semántico. "
            "Puede repetirse."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Regenera los CSV aunque ya existan."
        ),
    )

    parser.add_argument(
        "--list-only",
        action="store_true",
        help=(
            "Solo lista los modelos encontrados; "
            "no exporta archivos."
        ),
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help=(
            "Detiene el proceso al primer modelo con error."
        ),
    )

    return parser


def main():
    configure_console_utf8()
    args = build_parser().parse_args()

    provider = PowerBIProvider()

    try:
        synchronizer = MetadataSynchronizer(
            provider=provider,
            project_root=PROJECT_ROOT,
        )

        synchronizer.sync(
            requested_models=args.model,
            force=args.force,
            list_only=args.list_only,
            fail_fast=args.fail_fast,
        )

    finally:
        provider.close()


if __name__ == "__main__":
    main()

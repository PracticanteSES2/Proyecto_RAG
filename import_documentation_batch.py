import argparse
import json
import re
import shutil
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
CATALOG_DIR = PROJECT_ROOT / "data" / "catalog"
MODEL_REGISTRY = CATALOG_DIR / "model_registry.json"
IMPORT_REPORT = CATALOG_DIR / "documentation_import_report.json"

SUPPORTED_DOCUMENT_EXTENSIONS = {".docx"}
COPYABLE_EXTRA_EXTENSIONS = {".pdf", ".txt", ".md", ".xlsx", ".xls", ".csv"}

REPORT_ROOT_CANDIDATES = (
    PROJECT_ROOT / "data" / "pbir",
    PROJECT_ROOT / "data" / "reports",
    PROJECT_ROOT / "tableros",
    PROJECT_ROOT,
)


def normalize_text(value):
    value = str(value or "").strip().lower()
    value = "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def slugify(value):
    return normalize_text(value).replace(" ", "_") or "sin_nombre"


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def relative_to_project(path):
    if not path:
        return None
    path = Path(path).resolve()
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except Exception:
        return str(path)


def strip_numeric_prefix(name):
    return re.sub(r"^\s*\d+\s*[-_.]?\s*", "", str(name or "")).strip()


def folder_name_candidates(folder_name):
    value = strip_numeric_prefix(folder_name)
    value = re.sub(
        r"^\s*DOCUMENTACI[ÓO]N\s+",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()

    candidates = [value]

    without_tablero = re.sub(
        r"^\s*TABLERO\s+",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()

    if without_tablero and normalize_text(without_tablero) != normalize_text(value):
        candidates.append(without_tablero)

    result = []
    seen = set()

    for candidate in candidates:
        key = normalize_text(candidate)
        if key and key not in seen:
            result.append(candidate.strip())
            seen.add(key)

    return result


def display_name(value):
    value = re.sub(r"[_-]+", " ", str(value or ""))
    return re.sub(r"\s+", " ", value).strip().upper()


def token_set(value):
    return set(normalize_text(value).split())


def similarity(left, right):
    a = normalize_text(left)
    b = normalize_text(right)

    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    a_tokens = token_set(a)
    b_tokens = token_set(b)
    union = a_tokens | b_tokens
    inter = a_tokens & b_tokens

    jaccard = len(inter) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, a, b).ratio()
    containment = 0.92 if (a in b or b in a) else 0.0

    return max(containment, 0.58 * sequence + 0.42 * jaccard)


def source_group_from_report(report_name):
    key = slugify(report_name)
    return key if key.startswith("tablero_") else f"tablero_{key}"


def load_models(model_registry_path):
    payload = load_json(model_registry_path, default={})
    models = []

    for item in payload.get("models", []) or []:
        name = item.get("semantic_model")
        if not name:
            continue

        models.append({
            "semantic_model": name,
            "semantic_model_key": (
                item.get("semantic_model_key") or slugify(name)
            ),
            "metadata_path": item.get("metadata_path"),
            "status": item.get("status"),
        })

    return payload, models


def match_model(folder_candidates, models):
    scored = []

    for model in models:
        best = 0.0
        best_candidate = None

        for candidate in folder_candidates:
            local = max(
                similarity(candidate, model["semantic_model"]),
                similarity(slugify(candidate), model["semantic_model_key"]),
            )

            if local > best:
                best = local
                best_candidate = candidate

        scored.append({
            "score": round(best, 4),
            "matched_candidate": best_candidate,
            **model,
        })

    scored.sort(key=lambda item: item["score"], reverse=True)

    if not scored:
        return {
            "status": "unmatched",
            "confidence": 0.0,
            "best": None,
            "candidates": [],
        }

    best = scored[0]
    second_score = scored[1]["score"] if len(scored) > 1 else 0.0

    if best["score"] >= 0.94 and best["score"] - second_score >= 0.04:
        status = "matched"
    elif best["score"] >= 0.84 and best["score"] - second_score >= 0.08:
        status = "review"
    else:
        status = "unmatched"

    return {
        "status": status,
        "confidence": best["score"],
        "best": best,
        "candidates": scored[:5],
    }


def find_report_directories():
    found = []
    seen = set()

    for root in REPORT_ROOT_CANDIDATES:
        if not root.exists():
            continue

        try:
            candidates = list(root.rglob("*.Report"))
        except Exception:
            continue

        for path in candidates:
            if not path.is_dir():
                continue

            key = str(path.resolve()).casefold()
            if key in seen:
                continue

            found.append(path.resolve())
            seen.add(key)

    return found


def match_report_directory(report_name, semantic_model, report_directories):
    scored = []

    for path in report_directories:
        name = path.name[:-7] if path.name.lower().endswith(".report") else path.name

        score = max(
            similarity(report_name, name),
            similarity(semantic_model, name) if semantic_model else 0.0,
        )

        if score > 0:
            scored.append((score, path))

    scored.sort(key=lambda item: item[0], reverse=True)

    if not scored:
        return None, 0.0, "not_found"

    best_score, best_path = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    if best_score >= 0.92 and best_score - second_score >= 0.04:
        return best_path, round(best_score, 4), "matched"

    if best_score >= 0.82:
        return best_path, round(best_score, 4), "review"

    return None, round(best_score, 4), "not_found"


def choose_report_name(folder_candidates, model_match, report_path):
    if report_path:
        name = report_path.name[:-7] if report_path.name.lower().endswith(".report") else report_path.name
        if name:
            return display_name(name)

    best = model_match.get("best")

    if best and model_match.get("confidence", 0.0) >= 0.96:
        return display_name(best["semantic_model"])

    for candidate in folder_candidates:
        if not normalize_text(candidate).startswith("tablero "):
            return display_name(candidate)

    return display_name(folder_candidates[0])


def inspect_source_files(source_folder):
    supported, extras, ignored = [], [], []

    for path in sorted(source_folder.rglob("*")):
        if not path.is_file():
            continue

        extension = path.suffix.lower()

        if extension in SUPPORTED_DOCUMENT_EXTENSIONS:
            supported.append(path)
        elif extension in COPYABLE_EXTRA_EXTENSIONS:
            extras.append(path)
        else:
            ignored.append(path)

    return supported, extras, ignored


def merge_manifest(existing, generated):
    if not existing:
        return generated

    merged = dict(existing)

    for key, value in generated.items():
        if key not in merged or merged.get(key) in (None, "", []):
            merged[key] = value

    aliases = []
    for value in (
        list(existing.get("aliases", []) or [])
        + list(generated.get("aliases", []) or [])
    ):
        if value and value not in aliases:
            aliases.append(value)

    merged["aliases"] = aliases
    merged["import_metadata"] = generated.get("import_metadata", {})
    return merged


def copy_or_move_file(
    source_file,
    destination_file,
    *,
    move=False,
    overwrite=False,
    dry_run=False,
):
    if destination_file.exists() and not overwrite:
        return "exists"

    if dry_run:
        return "would_move" if move else "would_copy"

    destination_file.parent.mkdir(parents=True, exist_ok=True)

    if move:
        shutil.move(str(source_file), str(destination_file))
        return "moved"

    shutil.copy2(source_file, destination_file)
    return "copied"


def process_folder(
    source_folder,
    models,
    report_directories,
    *,
    include_extra_files=False,
    move=False,
    overwrite_files=False,
    dry_run=False,
):
    folder_candidates = folder_name_candidates(source_folder.name)
    model_match = match_model(folder_candidates, models)

    best_model = model_match.get("best")

    if best_model and model_match["status"] in ("matched", "review"):
        semantic_model = best_model["semantic_model"]
        semantic_model_key = best_model["semantic_model_key"]
    else:
        semantic_model = None
        semantic_model_key = None

    preliminary_report = (
        best_model.get("matched_candidate")
        if best_model and best_model.get("matched_candidate")
        else folder_candidates[-1]
    )

    report_path, report_score, report_status = match_report_directory(
        preliminary_report,
        semantic_model,
        report_directories,
    )

    report_name = choose_report_name(
        folder_candidates,
        model_match,
        report_path,
    )

    source_group = source_group_from_report(report_name)
    destination_folder = RAW_DIR / source_group

    supported, extras, ignored = inspect_source_files(source_folder)
    files_to_import = list(supported)

    if include_extra_files:
        files_to_import.extend(extras)

    file_actions = []

    for source_file in files_to_import:
        relative_path = source_file.relative_to(source_folder)
        destination_file = destination_folder / relative_path

        action = copy_or_move_file(
            source_file,
            destination_file,
            move=move,
            overwrite=overwrite_files,
            dry_run=dry_run,
        )

        file_actions.append({
            "source": str(source_file),
            "destination": relative_to_project(destination_file),
            "action": action,
        })

    aliases = []

    for candidate in folder_candidates:
        alias = display_name(candidate)
        if alias and alias not in aliases:
            aliases.append(alias)

    if report_name and report_name not in aliases:
        aliases.append(report_name)

    needs_review = (
        model_match["status"] != "matched"
        or report_status == "review"
    )

    manifest = {
        "workspace": "Gestion Clinica",
        "report": report_name,
        "semantic_model": semantic_model,
        "semantic_model_key": semantic_model_key,
        "source_group": source_group,
        "default_dashboard": report_name,
        "aliases": aliases,
        "document_type": "dashboard_documentation",
        "pbir_path": relative_to_project(report_path) if report_path else None,
        "import_metadata": {
            "source_folder": str(source_folder),
            "model_match_status": model_match["status"],
            "model_match_confidence": model_match["confidence"],
            "report_match_status": report_status,
            "report_match_confidence": report_score,
            "needs_review": needs_review,
        },
    }

    manifest_path = destination_folder / "manifest.json"
    existing_manifest = (
        load_json(manifest_path, default={})
        if manifest_path.exists()
        else {}
    )

    final_manifest = merge_manifest(existing_manifest, manifest)

    if not dry_run:
        destination_folder.mkdir(parents=True, exist_ok=True)
        save_json(final_manifest, manifest_path)

    return {
        "source_folder": str(source_folder),
        "folder_candidates": folder_candidates,
        "source_group": source_group,
        "destination": relative_to_project(destination_folder),
        "report": report_name,
        "semantic_model": semantic_model,
        "semantic_model_key": semantic_model_key,
        "model_match_status": model_match["status"],
        "model_match_confidence": model_match["confidence"],
        "model_candidates": model_match["candidates"],
        "pbir_path": relative_to_project(report_path) if report_path else None,
        "pbir_match_status": report_status,
        "pbir_match_confidence": report_score,
        "supported_documents": len(supported),
        "extra_files": len(extras),
        "ignored_files": len(ignored),
        "files": file_actions,
        "needs_review": needs_review,
        "manifest": final_manifest,
    }


def print_summary(results, dry_run):
    print("\n" + "=" * 76)
    print("IMPORTACIÓN MASIVA DE DOCUMENTACIÓN")
    print("=" * 76)
    print("Modo:", "SIMULACIÓN (--dry-run)" if dry_run else "APLICADO")
    print("Carpetas:", len(results))
    print(
        "Modelos emparejados:",
        sum(
            1 for item in results
            if item["model_match_status"] == "matched"
        ),
    )
    print(
        "Requieren revisión:",
        sum(
            1 for item in results
            if item["needs_review"]
        ),
    )
    print(
        "DOCX detectados:",
        sum(
            item["supported_documents"]
            for item in results
        ),
    )

    print("\nDETALLE:")

    for item in results:
        marker = "✓" if not item["needs_review"] else "!"

        print(f"\n{marker} {Path(item['source_folder']).name}")
        print("   ->", item["source_group"])
        print("   Informe:", item["report"])
        print("   Modelo:", item["semantic_model"] or "NO RESUELTO")
        print(
            "   Match modelo:",
            f"{item['model_match_status']} ({item['model_match_confidence']:.2f})",
        )
        print("   .Report:", item["pbir_path"] or "no encontrado")
        print("   DOCX:", item["supported_documents"])

    print("\nReporte:", IMPORT_REPORT)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Importa en lote carpetas de documentación de tableros, "
            "las normaliza a data/raw, genera manifest.json y trata de "
            "emparejarlas con model_registry.json y carpetas .Report."
        )
    )

    parser.add_argument(
        "source_dir",
        help=(
            "Carpeta que contiene las carpetas "
            "'N DOCUMENTACION TABLERO ...'."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula todo sin copiar archivos ni escribir manifests.",
    )

    parser.add_argument(
        "--move",
        action="store_true",
        help=(
            "Mueve los archivos en lugar de copiarlos. "
            "Por seguridad, la opción recomendada es copiar."
        ),
    )

    parser.add_argument(
        "--overwrite-files",
        action="store_true",
        help="Sobrescribe documentos ya existentes en data/raw.",
    )

    parser.add_argument(
        "--include-extra-files",
        action="store_true",
        help=(
            "Además de DOCX copia PDF/TXT/MD/XLS/XLSX/CSV. "
            "El pipeline actual puede no ingerir todos esos formatos."
        ),
    )

    args = parser.parse_args()

    source_dir = Path(args.source_dir).expanduser().resolve()

    if not source_dir.exists():
        raise FileNotFoundError(f"No existe: {source_dir}")

    if not source_dir.is_dir():
        raise NotADirectoryError(f"No es una carpeta: {source_dir}")

    if not MODEL_REGISTRY.exists():
        raise FileNotFoundError(
            "No existe data/catalog/model_registry.json. "
            "Ejecuta primero sync_powerbi_metadata.py."
        )

    registry, models = load_models(MODEL_REGISTRY)

    if not models:
        raise RuntimeError(
            "model_registry.json no contiene modelos semánticos."
        )

    report_directories = find_report_directories()

    folders = [
        path
        for path in sorted(source_dir.iterdir())
        if path.is_dir()
        and (
            "documentacion" in normalize_text(path.name)
            or "tablero" in normalize_text(path.name)
        )
    ]

    if not folders:
        raise RuntimeError(
            "No encontré carpetas de documentación dentro de "
            f"{source_dir}"
        )

    results = []

    for folder in folders:
        results.append(
            process_folder(
                source_folder=folder,
                models=models,
                report_directories=report_directories,
                include_extra_files=args.include_extra_files,
                move=args.move,
                overwrite_files=args.overwrite_files,
                dry_run=args.dry_run,
            )
        )

    payload = {
        "schema_version": 1,
        "source_dir": str(source_dir),
        "dry_run": args.dry_run,
        "workspace": (
            registry.get("workspace", {}).get("name")
            or "Gestion Clinica"
        ),
        "summary": {
            "folders": len(results),
            "matched": sum(
                1 for item in results
                if item["model_match_status"] == "matched"
            ),
            "needs_review": sum(
                1 for item in results
                if item["needs_review"]
            ),
            "documents": sum(
                item["supported_documents"]
                for item in results
            ),
        },
        "results": results,
    }

    if not args.dry_run:
        save_json(payload, IMPORT_REPORT)

    print_summary(results, args.dry_run)


if __name__ == "__main__":
    main()

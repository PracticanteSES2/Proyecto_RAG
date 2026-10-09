"""
Reconstruye data/ completo (metadata de modelos, documentación, RAG, Qdrant
y catálogos Power BI) a partir de fuentes LOCALES, sin conexión a Power BI.

Pasos (los mismos del propietario, en su orden):
  1. data/model_metadata/<slug>/  (en lugar de sync_powerbi_metadata.py):
       - TMDL de tableros/*/*.SemanticModel          -> metadata real
       - historial git (commit 3bf7b9f)              -> metadata real exportada
       - reportes PBIR + documentación               -> metadata inferida
     y data/catalog/model_registry.json.
  2. import_documentation_batch.py  -> data/raw/<grupo>/ + manifest.json
  3. build_powerbi_catalogs.py      -> catálogos técnicos, visuales,
                                       master_metrics.json, source_registry
  4. ingest_rag.py                  -> processed, semantic_documents,
                                       knowledge_chunks.json, Qdrant
  5. data/catalog/local_build_report.json (cobertura)

Seguridad ante fallos: el data/ anterior se renombra a data.bak_<fecha>; si
algo falla se borra lo construido y se restaura el respaldo. Al terminar bien
el respaldo se elimina (salvo --keep-backup).

Uso (desde la raíz del repo):
    python -m tools.local_data.build_local_data
    python -m tools.local_data.build_local_data --skip-index   # sin reindexar
"""
import argparse
import contextlib
import io
import json
import shutil
import subprocess
import sys
import zipfile
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[2]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from tools.local_data.metadata_format import (  # noqa: E402
    METADATA_FILES,
    normalize_text,
    save_json,
    slugify,
    write_sync_info,
)
from tools.local_data.tmdl_to_metadata import convert as convert_tmdl  # noqa: E402
from tools.local_data.infer_metadata import build_inferred_metadata  # noqa: E402
from tools.local_data.documented_values import DocumentedValues  # noqa: E402
from tools.local_data.infer_visuals import write_inferred_report  # noqa: E402
from tools.local_data.coverage_report import build_coverage_report, print_coverage_report  # noqa: E402


HISTORY_COMMIT = "3bf7b9f"
REFERENCE_ZIP_NAME = "OneDrive_1_9-10-2026.zip"
WORKSPACE_NAME = "Gestion Clinica"
DOCS_SUBDIR = Path("Documentacion") / "DOCUMENTACION TABLERO"


def configure_console_utf8():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def log(*parts):
    print("[local-data]", *parts, flush=True)


# ============================================================
# RUTAS
# ============================================================

def main_repository_root(code_root=CODE_ROOT):
    """
    Raíz del checkout principal aunque el código corra desde un git worktree
    (los datos, tableros/ y Documentacion/ solo existen en el principal).
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(code_root), "rev-parse", "--path-format=absolute",
             "--git-common-dir"],
            capture_output=True, text=True, check=True,
        )
        common = Path(result.stdout.strip())
        if common.name == ".git" and common.parent.exists():
            return common.parent.resolve()
    except Exception:
        pass
    return code_root


def git_show(repo, revision_path):
    """
    Contenido del archivo tal como quedaría al hacer checkout (--filters
    aplica la conversión de fin de línea: el blob se guardó con LF por
    core.autocrlf, pero el export real de INFO.VIEW usa CRLF).
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--filters", revision_path],
        capture_output=True, check=True,
    )
    return result.stdout


def git_list(repo, commit, prefix):
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", commit, "--", prefix],
            capture_output=True, text=True, check=True, encoding="utf-8",
        )
    except Exception:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def reference_model_slugs(zip_path):
    """Slugs de data/model_metadata del propietario (solo nombres del zip)."""
    if not zip_path or not Path(zip_path).exists():
        return set()
    slugs = set()
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            marker = "__data/model_metadata/"
            if marker not in name:
                continue
            rest = name.split(marker, 1)[1]
            first = rest.split("/", 1)[0]
            if first.endswith("_Error.txt"):
                first = first[: -len("_Error.txt")]
            if first:
                slugs.add(first)
    return slugs


# ============================================================
# 1. MODELOS
# ============================================================

def discover_models(tableros_dir, docs_dir, repo, history_commit, reference_slugs):
    """
    Devuelve OrderedDict slug -> spec con la mejor fuente disponible:
    tmdl > git_history > inferido (reporte y/o documentación).
    """
    import import_documentation_batch as idb

    specs = OrderedDict()

    def spec_for(name):
        slug = slugify(name)
        if slug not in specs:
            specs[slug] = {
                "semantic_model": name,
                "semantic_model_key": slug,
                "source": None,
                "semantic_model_path": None,
                "report_paths": [],
                "history_files": None,
            }
        return specs[slug]

    if tableros_dir.exists():
        for semantic_model in sorted(tableros_dir.glob("*/*.SemanticModel")):
            if (semantic_model / "definition" / "tables").is_dir():
                spec = spec_for(semantic_model.name[: -len(".SemanticModel")])
                spec["source"] = "tmdl"
                spec["semantic_model_path"] = semantic_model

        for report in sorted(tableros_dir.glob("*/*.Report")):
            if (report / "definition" / "pages").is_dir():
                spec = spec_for(report.name[: -len(".Report")])
                spec["report_paths"].append(report)

    history = defaultdict(dict)
    for path in git_list(repo, history_commit, "data/model_metadata"):
        parts = Path(path).parts
        if len(parts) == 4 and parts[3] in METADATA_FILES:
            history[parts[2]][parts[3]] = path
    for slug, files in history.items():
        if set(files) != set(METADATA_FILES):
            continue
        spec = specs.get(slug) or spec_for(idb.display_name(slug))
        if spec["source"] != "tmdl":
            spec["source"] = "git_history"
            spec["history_files"] = files

    # Carpetas de documentación sin modelo: modelo inferido de la documentación.
    if docs_dir.exists():
        for folder in sorted(path for path in docs_dir.iterdir() if path.is_dir()):
            candidates = idb.folder_name_candidates(folder.name)
            models = [
                {"semantic_model": spec["semantic_model"],
                 "semantic_model_key": spec["semantic_model_key"],
                 "metadata_path": None, "status": None}
                for spec in specs.values()
            ]
            match = idb.match_model(candidates, models)
            if match["status"] in ("matched", "review"):
                continue
            chosen = next(
                (c for c in candidates if slugify(c) in reference_slugs),
                candidates[0],
            )
            spec_for(idb.display_name(chosen))

    for spec in specs.values():
        if spec["source"] is None:
            spec["source"] = (
                "inferred_from_report" if spec["report_paths"]
                else "inferred_from_documentation"
            )

    return specs


def write_history_metadata(spec, repo, history_commit, model_dir):
    from src.semantic.visual_catalog_builder import read_csv_rows

    model_dir.mkdir(parents=True, exist_ok=True)
    for filename, git_path in spec["history_files"].items():
        # Bytes tal cual (mismo formato, codificación y fin de línea).
        content = git_show(repo, f"{history_commit}:{git_path}")
        (model_dir / filename).write_bytes(content)

    # El original no traía _metadata_sync.json; se agrega para dejar
    # constancia del origen (mismo esquema que sync_powerbi_metadata).
    counts = {
        filename: len(read_csv_rows(model_dir / filename))
        for filename in METADATA_FILES
    }
    write_sync_info(
        spec["semantic_model"], model_dir, counts,
        source="git_history",
        extra={"source_details": {
            "commit": history_commit,
            "paths": spec["history_files"],
            "note": (
                "Export real de INFO.VIEW del propietario restaurado del "
                "historial git (sin _metadata_sync.json original)."
            ),
        }},
    )
    return counts


def write_model_registry(specs, data_root, results, reference_slugs):
    records = []
    for slug, spec in specs.items():
        result = results.get(slug) or {}
        records.append({
            "semantic_model": spec["semantic_model"],
            "semantic_model_key": slug,
            "metadata_path": f"data/model_metadata/{slug}",
            "status": "success" if result.get("counts") else "pending",
            "errors": result.get("errors", []),
            "source": spec["source"],
            "inferred": spec["source"].startswith("inferred"),
        })

    missing = sorted(reference_slugs - set(specs))
    registry = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "tools/local_data/build_local_data.py (sin Power BI)",
        "workspace": {"name": WORKSPACE_NAME, "xmla_endpoint": None},
        "models": records,
        "summary": {
            "discovered": len(records),
            "selected": len(records),
            "success": sum(1 for item in records if item["status"] == "success"),
            "skipped": 0,
            "errors": sum(1 for item in records if item["status"] != "success"),
            "real_metadata": sum(1 for item in records if not item["inferred"]),
            "inferred_metadata": sum(1 for item in records if item["inferred"]),
        },
        # Modelos que el propietario tiene en Power BI (nombres del zip de
        # OneDrive) pero de los que no hay ninguna fuente local.
        "remote_models_without_local_sources": missing,
    }
    save_json(registry, data_root / "catalog" / "model_registry.json")
    return registry


# ============================================================
# 2-4. PIPELINE DEL PROPIETARIO (con rutas redirigidas)
# ============================================================

def run_import_documentation(project_root, data_root, docs_dir, tableros_dir):
    import import_documentation_batch as idb

    idb.PROJECT_ROOT = project_root
    idb.RAW_DIR = data_root / "raw"
    idb.CATALOG_DIR = data_root / "catalog"
    idb.MODEL_REGISTRY = idb.CATALOG_DIR / "model_registry.json"
    idb.IMPORT_REPORT = idb.CATALOG_DIR / "documentation_import_report.json"
    idb.REPORT_ROOT_CANDIDATES = (
        data_root / "pbir",
        data_root / "reports",
        tableros_dir,
    )

    argv = sys.argv
    sys.argv = ["import_documentation_batch.py", str(docs_dir)]
    try:
        idb.main()
    finally:
        sys.argv = argv

    return json.loads(idb.IMPORT_REPORT.read_text(encoding="utf-8"))


def parse_documents_for_inference(data_root, work_dir):
    """processed + semantic_documents provisionales para inferir metadata."""
    from src.ingestion.document_parser import process_all_documents
    from src.semantic.document_normalizer import normalize_all_documents

    processed = work_dir / "processed"
    semantic = work_dir / "semantic_documents"
    with contextlib.redirect_stdout(io.StringIO()):
        process_all_documents(data_root / "raw", processed)
        normalize_all_documents(processed, semantic)

    by_model = defaultdict(list)
    for path in sorted(semantic.rglob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        key = document.get("semantic_model_key")
        if key:
            by_model[key].append(document)
    return by_model


def manifest_report_names(raw_dir):
    """semantic_model_key -> nombre del reporte según los manifest.json importados."""
    names = {}
    for path in sorted(Path(raw_dir).glob("*/manifest.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        key = manifest.get("semantic_model_key")
        if key and manifest.get("report") and key not in names:
            names[key] = manifest["report"]
    return names


def run_catalogs(project_root, data_root):
    from src.semantic.powerbi_catalog_manager import PowerBICatalogManager

    manager = PowerBICatalogManager(project_root=project_root)
    manager.data_dir = data_root
    manager.raw_dir = data_root / "raw"
    manager.metadata_root = data_root / "model_metadata"
    manager.pbir_root = data_root / "pbir"
    manager.catalog_dir = data_root / "catalog"
    manager.visuals_dir = manager.catalog_dir / "visuals"
    manager.rag_dir = data_root / "rag"
    manager.model_registry_path = manager.catalog_dir / "model_registry.json"
    manager.source_registry_path = manager.catalog_dir / "source_registry.json"
    manager.global_visual_catalog_path = manager.rag_dir / "visual_metrics_catalog.json"
    manager.master_metrics_path = manager.rag_dir / "master_metrics.json"
    return manager.run()


def run_ingest(project_root, data_root, skip_index):
    import ingest_rag

    ingest_rag.PROJECT_ROOT = project_root
    ingest_rag.RAW_DIR = data_root / "raw"
    ingest_rag.PROCESSED_DIR = data_root / "processed"
    ingest_rag.SEMANTIC_DOCUMENTS_DIR = data_root / "semantic_documents"
    ingest_rag.SEMANTIC_CATALOG = data_root / "catalog" / "semantic_knowledge.json"
    ingest_rag.CHUNKS_FILE = data_root / "rag" / "knowledge_chunks.json"
    ingest_rag.QDRANT_PATH = data_root / "vector_db" / "qdrant"

    return ingest_rag.run_pipeline(clean_derived=True, skip_index=skip_index)


# ============================================================
# ORQUESTACIÓN
# ============================================================

def build(args):
    project_root = args.project_root
    data_root = args.data_root
    # El pipeline del propietario resuelve <raíz>/data/...: su raíz es el
    # padre de data_root (igual a project_root en el uso normal).
    owner_root = data_root.parent
    work_dir = data_root / ".local_build_tmp"

    reference_slugs = reference_model_slugs(args.reference_zip)
    log("Proyecto:", project_root)
    log("Destino:", data_root)
    log("Documentación:", args.docs_dir)
    log("Tableros:", args.tableros_dir)
    log("Modelos de referencia (zip OneDrive):", len(reference_slugs))

    # ---------------- 1. Metadata ----------------
    specs = discover_models(
        args.tableros_dir, args.docs_dir, project_root,
        args.history_commit, reference_slugs,
    )
    metadata_root = data_root / "model_metadata"
    results = {}

    for slug, spec in specs.items():
        model_dir = metadata_root / slug
        if spec["source"] == "tmdl":
            converted = convert_tmdl(
                spec["semantic_model_path"], metadata_root,
                model_name=spec["semantic_model"], folder_name=slug,
            )
            results[slug] = {"counts": converted["counts"], "warnings": converted["warnings"]}
        elif spec["source"] == "git_history":
            results[slug] = {"counts": write_history_metadata(
                spec, project_root, args.history_commit, model_dir,
            )}
        log(f"Modelo {spec['semantic_model']!r}: {spec['source']}")

    write_model_registry(specs, data_root, results, reference_slugs)

    # ---------------- 2. Documentación ----------------
    log("Importando documentación (import_documentation_batch)...")
    import_report = run_import_documentation(
        owner_root, data_root, args.docs_dir, args.tableros_dir,
    )

    # ---------------- 1b. Metadata inferida ----------------
    documents_by_model = parse_documents_for_inference(data_root, work_dir)
    report_names = manifest_report_names(data_root / "raw")
    for slug, spec in specs.items():
        documents = documents_by_model.get(slug, [])
        if not spec["source"].startswith("inferred"):
            # Modelos reales: solo los valores categóricos documentados
            # (para dominios realistas del simulador).
            saved = DocumentedValues().ingest_documents(documents).save(
                spec["semantic_model"], metadata_root / slug)
            if saved:
                log(f"Valores documentados {spec['semantic_model']!r}: {saved} columnas")
            continue
        inferred = build_inferred_metadata(
            spec["semantic_model"], metadata_root / slug,
            report_paths=spec["report_paths"], documents=documents,
        )
        spec["source"] = inferred["source"]
        results[slug] = {"counts": inferred["counts"]}
        log(
            f"Metadata inferida {spec['semantic_model']!r}: "
            f"{inferred['counts']} ({len(documents)} documentos)"
        )
        if inferred.get("inferred_report"):
            report_name = report_names.get(slug) or spec["semantic_model"]
            report_path = write_inferred_report(
                report_name, inferred["inferred_report"]["pages"], data_root / "pbir",
                semantic_model=spec["semantic_model"],
            )
            spec["inferred_report_path"] = report_path
            summary = inferred["inferred_report"]["summary"]
            log(
                f"  Reporte inferido de la documentación: {report_path.name} "
                f"({summary['visuals']} visuales, {len(summary['added_measures'])} medidas nuevas)"
            )
    shutil.rmtree(work_dir, ignore_errors=True)

    write_model_registry(specs, data_root, results, reference_slugs)

    # ---------------- 3. Catálogos ----------------
    log("Construyendo catálogos Power BI (build_powerbi_catalogs)...")
    run_catalogs(owner_root, data_root)

    # ---------------- 4. RAG ----------------
    if args.skip_index and args.previous_qdrant and args.previous_qdrant.exists():
        shutil.copytree(args.previous_qdrant, data_root / "vector_db" / "qdrant")
        log("Índice Qdrant anterior conservado (--skip-index).")
    log("Ingesta RAG (ingest_rag)...")
    ingest = run_ingest(owner_root, data_root, args.skip_index)

    # ---------------- 5. Informe ----------------
    report = build_coverage_report(
        data_root,
        specs=specs,
        import_report=import_report,
        ingest_result=ingest,
        skip_index=args.skip_index,
    )
    save_json(report, data_root / "catalog" / "local_build_report.json")
    print_coverage_report(report)
    return report


def parse_args(argv=None):
    default_root = main_repository_root()

    parser = argparse.ArgumentParser(
        description=(
            "Reconstruye data/ desde fuentes locales (TMDL, PBIR, "
            "documentación e historial git) sin Power BI."
        )
    )
    parser.add_argument("--project-root", type=Path, default=default_root,
                        help="Raíz del repo con tableros/ y Documentacion/.")
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Carpeta destino (debe llamarse 'data'). Por defecto <project-root>/data.")
    parser.add_argument("--docs-dir", type=Path, default=None,
                        help="Carpeta con las carpetas 'N DOCUMENTACION TABLERO ...'.")
    parser.add_argument("--tableros-dir", type=Path, default=None,
                        help="Carpeta con los proyectos PBIP (tableros/).")
    parser.add_argument("--reference-zip", type=Path, default=None,
                        help="Zip de OneDrive del propietario (solo se leen nombres).")
    parser.add_argument("--history-commit", default=HISTORY_COMMIT,
                        help="Commit con data/model_metadata real (por defecto 3bf7b9f).")
    parser.add_argument("--skip-index", action="store_true",
                        help="No recalcula embeddings: conserva el Qdrant anterior si existe.")
    parser.add_argument("--keep-backup", action="store_true",
                        help="Conserva data.bak_<fecha> tras un build correcto.")
    args = parser.parse_args(argv)

    args.project_root = args.project_root.resolve()
    args.data_root = (args.data_root or args.project_root / "data").resolve()
    args.docs_dir = (args.docs_dir or args.project_root / DOCS_SUBDIR).resolve()
    args.tableros_dir = (args.tableros_dir or args.project_root / "tableros").resolve()
    if args.reference_zip is None:
        candidate = args.project_root / REFERENCE_ZIP_NAME
        args.reference_zip = candidate if candidate.exists() else None

    if not args.docs_dir.exists():
        parser.error(f"No existe la carpeta de documentación: {args.docs_dir}")
    return args


def main(argv=None):
    configure_console_utf8()
    args = parse_args(argv)

    final_root = args.data_root
    staging = None
    if final_root.name != "data":
        # El pipeline del propietario resuelve rutas relativas como
        # <raíz>/data/... (p. ej. technical_catalog="data/catalog/x_rag.json"):
        # con otro nombre leería el data/ real. Se construye en
        # <padre>/.<nombre>.build/data y al final se renombra a final_root.
        staging = final_root.parent / f".{final_root.name}.build"
        if staging.exists():
            shutil.rmtree(staging)
        args.data_root = staging / "data"
        log("Destino final:", final_root, "(construcción en", staging, ")")
    data_root = args.data_root

    backup = None
    if final_root.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = final_root.with_name(f"{final_root.name}.bak_{stamp}")
        final_root.rename(backup)
        log(f"Respaldo del {final_root.name}/ anterior:", backup)
    args.previous_qdrant = backup / "vector_db" / "qdrant" if backup else None

    data_root.mkdir(parents=True)
    try:
        build(args)
        if staging is not None:
            data_root.rename(final_root)
            shutil.rmtree(staging, ignore_errors=True)
    except BaseException:
        log("ERROR: se descarta el build parcial.")
        shutil.rmtree(staging or data_root, ignore_errors=True)
        if final_root.exists() and staging is not None:
            shutil.rmtree(final_root, ignore_errors=True)
        if backup is not None:
            backup.rename(final_root)
            log(f"Restaurado el {final_root.name}/ anterior.")
        raise

    if backup is not None and not args.keep_backup:
        shutil.rmtree(backup, ignore_errors=True)
        log("Respaldo eliminado.")
    log("Listo:", final_root)


if __name__ == "__main__":
    main()

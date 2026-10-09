"""
Fusiona los modelos sintéticos (tests/realistic/synthetic_models) con un data/ real en una
COPIA en caché, usando el pipeline real del proyecto. El data/ original nunca se modifica.

    project_root = build_merged_root(Path(".../data"))
    # project_root/data = copia de catálogos + rag + model_metadata + Qdrant
    #                     + catálogos técnicos/visuales/maestros de los modelos sintéticos
    #                     + chunks RAG de su documentación, embebidos con el modelo real

Pasos (todo con código de src/):
  1. Copia data/{catalog,rag,model_metadata,vector_db} a <caché>/root/data.
  2. Añade la metadata sintética en data/model_metadata/<slug>, su manifest en data/raw/<grupo>/
     y su PBIR en data/pbir/<Reporte>.Report (generado desde source.json).
  3. PowerBICatalogManager(root).run(): catálogo técnico, visual y métricas maestras de las fuentes
     sintéticas (el catálogo visual global y master_metrics conservan lo existente).
  4. source_registry.json / model_registry.json = originales + entradas sintéticas.
  5. chunk_builder.build_chunks + embedding_indexer.build_vector_index sobre la copia de Qdrant
     (solo se reemplazan los source_group sintéticos).

La caché (por defecto %TEMP%/proyecto_rag_sim/<hash>) se reutiliza mientras no cambien los
archivos de data/, el overlay ni este módulo.
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYNTHETIC_DIR = HERE / "synthetic_models"
COPY_DIRS = ("catalog", "rag", "model_metadata", "vector_db")
SKIP_FILES = {"knowledge_chunks.json", "semantic_knowledge.json"}   # grandes y no los usa app.py


def synthetic_sources():
    sources = []
    if not SYNTHETIC_DIR.exists():
        return sources
    for folder in sorted(p for p in SYNTHETIC_DIR.iterdir() if p.is_dir()):
        file = folder / "source.json"
        if file.exists():
            sources.append(json.loads(file.read_text(encoding="utf-8")))
    return sources


def _fingerprint(data_root, synthetic=True):
    digest = hashlib.sha1()
    digest.update(f"{Path(data_root).resolve()}|synthetic={synthetic}".encode())
    for name in COPY_DIRS:
        base = Path(data_root) / name
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                stat = path.stat()
                digest.update(f"{path.relative_to(data_root)}|{stat.st_size}|{int(stat.st_mtime)}".encode())
    for path in sorted(SYNTHETIC_DIR.rglob("*")) + [Path(__file__), HERE / "build_synthetic_models.py"]:
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def default_cache_dir(data_root, synthetic=True):
    key = hashlib.sha1(f"{Path(data_root).resolve()}|{synthetic}".encode()).hexdigest()[:10]
    return Path(os.getenv("SIM_CACHE_DIR") or Path(tempfile.gettempdir()) / "proyecto_rag_sim") / key


def _copy_data(data_root, target):
    for name in COPY_DIRS:
        source = Path(data_root) / name
        if not source.exists():
            continue
        shutil.copytree(source, target / name,
                        ignore=lambda folder, names: [n for n in names if n in SKIP_FILES or n == ".lock"])


def _load(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_by(original, extra, field):
    seen = {str(item.get(field)).casefold() for item in original}
    return original + [item for item in extra if str(item.get(field)).casefold() not in seen]


def _semantic_catalog(sources, root):
    """Catálogo semántico (formato semantic_merge) de la documentación sintética para build_chunks."""
    dashboards = []
    for source in sources:
        doc = source["documentation"]
        dashboards.append({
            "name": doc["name"],
            "aliases": doc.get("aliases", []),
            "workspace": source.get("workspace"),
            "semantic_model": source["semantic_model"],
            "semantic_model_key": source["semantic_model_key"],
            "technical_catalog": f"data/catalog/{source['semantic_model_key']}_rag.json",
            "source_group": source["source_group"],
            "source_file": f"Documentacion {doc['name']} (sintetica).md",
            "relative_path": f"{source['source_group']}/Documentacion {doc['name']} (sintetica).md",
            "document_type": "dashboard_documentation",
            "description": doc.get("description"),
            "filters": doc.get("filters", []),
            "visuals": doc.get("visuals", []),
            "indicators": doc.get("indicators", []),
            "matched_measures": [
                {"documented": {"table": m["table"], "name": m["name"], "expression": m["expression"],
                                "description": m["description"]},
                 "powerbi": {"table": m["table"], "name": m["name"], "expression": m["expression"],
                             "description": m["description"], "data_type": m["data_type"],
                             "format_string": m["format_string"]},
                 "match_type": "exact"}
                for m in doc.get("measures", [])
            ],
        })
    return {"schema_version": 2, "workspace": "Gestion Clinica", "dashboards": dashboards}


def build_merged_root(data_root, cache_dir=None, force=False, quiet=True, synthetic=True):
    """Devuelve la raíz de proyecto (contiene data/) con data_root + modelos sintéticos.

    Con synthetic=False solo copia data_root: así Qdrant (que crea un .lock en su carpeta) y
    cualquier escritura quedan en la caché y el data/ real no se toca.
    """
    from tests.realistic.build_synthetic_models import write_report

    data_root = Path(data_root).resolve()
    cache = Path(cache_dir) if cache_dir else default_cache_dir(data_root, synthetic)
    root = cache / "root"
    stamp = cache / "fingerprint.txt"
    fingerprint = _fingerprint(data_root, synthetic)
    if not force and stamp.exists() and stamp.read_text().strip() == fingerprint and (root / "data").exists():
        return root

    if root.exists():
        shutil.rmtree(root)
    data = root / "data"
    data.mkdir(parents=True)
    _copy_data(data_root, data)
    sources = synthetic_sources() if synthetic else []
    if not sources:
        cache.mkdir(parents=True, exist_ok=True)
        stamp.write_text(fingerprint)
        return root
    original_sources = _load(data / "catalog" / "source_registry.json", {"models": [], "sources": []})
    original_models = _load(data / "catalog" / "model_registry.json")

    for source in sources:
        slug = source["semantic_model_key"]
        target = data / "model_metadata" / slug
        if target.exists():
            continue   # el data/ real ya trae ese modelo: gana el real
        shutil.copytree(SYNTHETIC_DIR / slug, target, ignore=lambda folder, names: ["source.json"])
        raw = data / "raw" / source["source_group"]
        raw.mkdir(parents=True, exist_ok=True)
        report = write_report(source, data / "pbir")
        manifest = {k: v for k, v in source.items() if k not in ("pages", "documentation")}
        manifest["pbir_path"] = str(report.relative_to(root)).replace("\\", "/")
        _save(raw / "manifest.json", manifest)

    sink = io.StringIO()
    with contextlib.redirect_stdout(sink) if quiet else contextlib.nullcontext():
        from src.semantic.powerbi_catalog_manager import PowerBICatalogManager
        from src.rag.chunk_builder import build_chunks
        from src.rag.embedding_indexer import build_vector_index

        manager = PowerBICatalogManager(project_root=root)
        if (data / "raw").exists():
            manager.run()
        synthetic_registry = _load(data / "catalog" / "source_registry.json", {"models": [], "sources": []})
        merged = dict(original_sources)
        merged["models"] = _merge_by(original_sources.get("models", []), synthetic_registry.get("models", []),
                                     "semantic_model_key")
        merged["sources"] = _merge_by(original_sources.get("sources", []), synthetic_registry.get("sources", []),
                                      "source_group")
        _save(data / "catalog" / "source_registry.json", merged)
        if original_models is not None:
            extra = [{"semantic_model": s["semantic_model"], "semantic_model_key": s["semantic_model_key"],
                      "metadata_path": f"data/model_metadata/{s['semantic_model_key']}", "status": "success",
                      "errors": [], "origin": "synthetic"} for s in sources]
            original_models["models"] = _merge_by(original_models.get("models", []), extra, "semantic_model_key")
            _save(data / "catalog" / "model_registry.json", original_models)

        chunks = build_chunks(_semantic_catalog(sources, root))
        if chunks:
            chunks_file = data / "rag" / "synthetic_chunks.json"
            _save(chunks_file, chunks)
            build_vector_index(chunks_file, data / "vector_db" / "qdrant", replace_source_groups=True)

    cache.mkdir(parents=True, exist_ok=True)
    stamp.write_text(fingerprint)
    return root

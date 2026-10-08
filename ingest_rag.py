import argparse
import shutil
from pathlib import Path

from src.ingestion.document_parser import process_all_documents
from src.semantic.document_normalizer import normalize_all_documents
from src.semantic.semantic_merge import build_semantic_catalog
from src.rag.chunk_builder import build_chunks_file
from src.rag.embedding_indexer import build_vector_index


PROJECT_ROOT = Path(__file__).resolve().parent

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SEMANTIC_DOCUMENTS_DIR = PROJECT_ROOT / "data" / "semantic_documents"
SEMANTIC_CATALOG = PROJECT_ROOT / "data" / "catalog" / "semantic_knowledge.json"
CHUNKS_FILE = PROJECT_ROOT / "data" / "rag" / "knowledge_chunks.json"
QDRANT_PATH = PROJECT_ROOT / "data" / "vector_db" / "qdrant"


def clean_derived_outputs():
    """
    Limpia únicamente artefactos derivados de documentos.
    Nunca borra data/raw ni la base Qdrant completa.
    """
    for path in (PROCESSED_DIR, SEMANTIC_DOCUMENTS_DIR):
        if path.exists():
            shutil.rmtree(path)

    for path in (SEMANTIC_CATALOG, CHUNKS_FILE):
        if path.exists():
            path.unlink()


def run_pipeline(clean_derived=True, skip_index=False):
    print("\n========================================")
    print("PIPELINE RAG - GESTIÓN CLÍNICA")
    print("========================================")

    if clean_derived:
        print("\n[0/5] Limpiando artefactos derivados...")
        clean_derived_outputs()

    print("\n[1/5] Extrayendo documentación...")
    parser_stats = process_all_documents(
        RAW_DIR,
        PROCESSED_DIR,
    )

    if parser_stats.get("errors"):
        raise RuntimeError(
            "La extracción terminó con errores. "
            "Corrígelos antes de indexar."
        )

    print("\n[2/5] Normalizando documentación...")
    normalizer_stats = normalize_all_documents(
        PROCESSED_DIR,
        SEMANTIC_DOCUMENTS_DIR,
    )

    if normalizer_stats.get("errors"):
        raise RuntimeError(
            "La normalización terminó con errores. "
            "Corrígelos antes de indexar."
        )

    print("\n[3/5] Fusionando documentación + Power BI...")
    semantic_catalog = build_semantic_catalog(
        technical_catalog_path=None,
        semantic_documents_dir=SEMANTIC_DOCUMENTS_DIR,
        output_path=SEMANTIC_CATALOG,
        project_root=PROJECT_ROOT,
    )

    print("\n[4/5] Generando chunks...")
    chunks, chunk_stats = build_chunks_file(
        SEMANTIC_CATALOG,
        CHUNKS_FILE,
    )

    index_stats = None

    if not skip_index:
        print("\n[5/5] Actualizando Qdrant...")
        index_stats = build_vector_index(
            CHUNKS_FILE,
            QDRANT_PATH,
        )
    else:
        print("\n[5/5] Indexación omitida (--skip-index).")

    print("\n========================================")
    print("PIPELINE FINALIZADO")
    print("========================================")
    print("Documentos:", parser_stats.get("documents_processed"))
    print("Tableros:", len(semantic_catalog.get("dashboards", [])))
    print("Chunks:", len(chunks))
    print("Grupos:", ", ".join(chunk_stats.get("source_groups", [])))

    if index_stats:
        print("Colección Qdrant:", index_stats.get("collection"))

    return {
        "parser": parser_stats,
        "normalizer": normalizer_stats,
        "semantic_catalog": semantic_catalog,
        "chunks": chunk_stats,
        "index": index_stats,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Construye e indexa el RAG documental de Gestión Clínica."
    )

    parser.add_argument(
        "--no-clean-derived",
        action="store_true",
        help="No limpia data/processed ni data/semantic_documents antes de reconstruir.",
    )

    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Genera documentos/catálogo/chunks pero no modifica Qdrant.",
    )

    args = parser.parse_args()

    run_pipeline(
        clean_derived=not args.no_clean_derived,
        skip_index=args.skip_index,
    )


if __name__ == "__main__":
    main()

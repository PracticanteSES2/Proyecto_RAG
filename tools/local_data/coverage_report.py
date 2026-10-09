"""
Informe de cobertura del data/ reconstruido por build_local_data.py.

Se guarda en data/catalog/local_build_report.json e incluye:
  - modelos con metadata real / inferida y conteos por modelo;
  - documentos importados por tablero (source_group);
  - chunks RAG e índice Qdrant;
  - métricas maestras y métricas visuales;
  - etiquetas de indicador repetidas en más de un modelo o tablero
    (redundancia real, útil para probar la desambiguación).
"""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tools.local_data.metadata_format import normalize_text
from src.semantic.visual_catalog_builder import read_csv_rows


AUTO_DATE_PREFIXES = ("LocalDateTable_", "DateTableTemplate_")

# Palabras que no distinguen un indicador (aparecen en casi cualquier modelo).
GENERIC_TERMS = {
    "total", "totales", "conteo", "distinto", "distinctcount", "count",
    "fecha", "fechas", "nombre", "nombres", "detalle", "inicio", "tablero",
    "documentacion", "promedio", "average", "suma", "valor", "valores",
    "codigo", "descripcion", "estado", "tipo", "numero", "cantidad",
    "completo", "registro", "registros", "general", "mensual", "anual",
    "actual", "anterior", "dinamico", "proyeccion", "color", "colorfila",
}


def _load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _model_counts(model_dir):
    tables = read_csv_rows(model_dir / "tables.csv")
    columns = read_csv_rows(model_dir / "columns.csv")
    measures = read_csv_rows(model_dir / "measures.csv")
    relationships = read_csv_rows(model_dir / "relationships.csv")

    user_tables = [t for t in tables if not str(t.get("Name", "")).startswith(AUTO_DATE_PREFIXES)]
    user_table_names = {t["Name"] for t in user_tables}
    user_columns = [
        c for c in columns
        if c.get("Type") != "RowNumber" and c.get("Table") in user_table_names
    ]
    return {
        "tables": len(tables),
        "tables_without_auto_date": len(user_tables),
        "columns": len(columns),
        "columns_user": len(user_columns),
        "measures": len(measures),
        "measures_with_dax": sum(1 for m in measures if str(m.get("Expression") or "").strip()),
        "relationships": len({r.get("ID") for r in relationships}),
    }


def _is_label_alias(value):
    """Alias que un usuario podría decir (no 'Tabla.Col' ni 'Sum(T.C)')."""
    text = str(value or "").strip()
    if not text or "(" in text or re.fullmatch(r"[^\s.]+\.[^\s.]+", text):
        return False
    return len(normalize_text(text)) >= 3


def _redundant(index, min_count=2):
    result = []
    for key, data in sorted(index.items()):
        owners = sorted(data["owners"])
        if len(owners) >= min_count:
            result.append({
                "label": sorted(data["labels"], key=len)[0],
                "normalized": key,
                "count": len(owners),
                "in": owners,
            })
    result.sort(key=lambda item: (-item["count"], item["normalized"]))
    return result


def redundant_labels(master_metrics, semantic_catalog):
    by_model = defaultdict(lambda: {"owners": set(), "labels": set()})
    by_dashboard = defaultdict(lambda: {"owners": set(), "labels": set()})

    for metric in master_metrics.get("metrics", []) or []:
        names = [metric.get("label")] + [
            alias for alias in metric.get("aliases", []) or [] if _is_label_alias(alias)
        ]
        for name in names:
            key = normalize_text(name)
            if not key:
                continue
            by_model[key]["owners"].add(metric.get("semantic_model"))
            by_model[key]["labels"].add(name)
            for group in metric.get("source_groups", []) or []:
                by_dashboard[key]["owners"].add(group)
                by_dashboard[key]["labels"].add(name)

    # Documentación: medidas, columnas calculadas y nombres de tablero.
    docs = defaultdict(lambda: {"owners": set(), "labels": set()})
    for dashboard in (semantic_catalog or {}).get("dashboards", []) or []:
        group = dashboard.get("source_group")
        names = [dashboard.get("name")]
        names += [m.get("name") for m in dashboard.get("documented_measures", []) or []]
        names += [c.get("name") for c in dashboard.get("calculated_columns", []) or []]
        for name in names:
            key = normalize_text(name)
            if len(key) < 3:
                continue
            docs[key]["owners"].add(group)
            docs[key]["labels"].add(name)

    # Términos de indicador (palabras de etiquetas de métricas y nombres de
    # tablero/medida documentados) compartidos por varios modelos: es lo que
    # hace ambigua una pregunta como "¿cuántos triages hubo?".
    terms = defaultdict(lambda: {"owners": set(), "labels": set()})

    def add_terms(text, owner):
        for token in normalize_text(text).split():
            if len(token) < 5 or token in GENERIC_TERMS or token.isdigit():
                continue
            terms[token]["owners"].add(owner)
            terms[token]["labels"].add(token)

    for metric in master_metrics.get("metrics", []) or []:
        add_terms(metric.get("label"), metric.get("semantic_model"))
    for dashboard in (semantic_catalog or {}).get("dashboards", []) or []:
        owner = dashboard.get("semantic_model") or dashboard.get("source_group")
        add_terms(dashboard.get("name"), owner)
        for measure in dashboard.get("documented_measures", []) or []:
            add_terms(measure.get("name"), owner)

    return {
        "indicator_terms_in_multiple_models": _redundant(terms),
        "master_metric_labels_in_multiple_models": _redundant(by_model),
        "master_metric_labels_in_multiple_dashboards": _redundant(by_dashboard),
        "documentation_names_in_multiple_dashboards": _redundant(docs),
    }


def build_coverage_report(data_root, *, specs, import_report, ingest_result, skip_index):
    data_root = Path(data_root)
    metadata_root = data_root / "model_metadata"

    models = []
    for slug, spec in specs.items():
        model_dir = metadata_root / slug
        sync = _load_json(model_dir / "_metadata_sync.json", {}) or {}
        models.append({
            "semantic_model": spec["semantic_model"],
            "semantic_model_key": slug,
            "source": sync.get("source") or spec["source"],
            "inferred": bool(sync.get("inferred")),
            "has_report_pbir": bool(spec.get("report_paths")),
            **_model_counts(model_dir),
        })

    documents = []
    for item in import_report.get("results", []) or []:
        documents.append({
            "folder": Path(item.get("source_folder", "")).name,
            "source_group": item.get("source_group"),
            "report": item.get("report"),
            "semantic_model": item.get("semantic_model"),
            "model_match_status": item.get("model_match_status"),
            "pbir_path": item.get("pbir_path"),
            "docx": item.get("supported_documents"),
        })

    chunks = _load_json(data_root / "rag" / "knowledge_chunks.json", []) or []
    if isinstance(chunks, dict):
        chunks = chunks.get("chunks", [])
    chunks_by_group = Counter(
        (chunk.get("metadata") or chunk).get("source_group") for chunk in chunks
    )
    chunks_by_type = Counter(
        chunk.get("chunk_type") for chunk in chunks
    )

    index = (ingest_result or {}).get("index") or {}
    master = _load_json(data_root / "rag" / "master_metrics.json", {}) or {}
    visual = _load_json(data_root / "rag" / "visual_metrics_catalog.json", {}) or {}
    semantic_catalog = _load_json(data_root / "catalog" / "semantic_knowledge.json", {}) or {}
    source_registry = _load_json(data_root / "catalog" / "source_registry.json", {}) or {}

    master_metrics = master.get("metrics", []) or []

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_root": str(data_root),
        "summary": {
            "models": len(models),
            "models_real_metadata": sum(1 for m in models if not m["inferred"]),
            "models_inferred_metadata": sum(1 for m in models if m["inferred"]),
            "docx_imported": sum(d["docx"] or 0 for d in documents),
            "documentation_groups": len(documents),
            "sources_ready": sum(
                1 for s in source_registry.get("sources", []) if s.get("status") == "ready"
            ),
            "dashboards_in_semantic_catalog": len(semantic_catalog.get("dashboards", []) or []),
            "chunks": len(chunks),
            "qdrant_collection": index.get("collection"),
            "qdrant_points": index.get("chunks_indexed"),
            "index_rebuilt": not skip_index,
            "visual_reports": (visual.get("stats") or {}).get("reports"),
            "visual_metric_bindings": (visual.get("stats") or {}).get("metric_bindings"),
            "master_metrics": len(master_metrics),
        },
        "models": models,
        "documents_by_dashboard": documents,
        "chunks_by_source_group": dict(sorted(chunks_by_group.items(), key=lambda kv: str(kv[0]))),
        "chunks_by_type": dict(chunks_by_type.most_common()),
        "index": {k: v for k, v in index.items() if k != "collection_info"},
        "master_metrics_by_model": dict(Counter(m.get("semantic_model") for m in master_metrics).most_common()),
        "redundant_indicator_labels": redundant_labels(master, semantic_catalog),
    }


def print_coverage_report(report):
    summary = report["summary"]
    print("\n" + "=" * 76)
    print("INFORME DE COBERTURA - data/ local")
    print("=" * 76)
    for key, value in summary.items():
        print(f"  {key}: {value}")

    print("\nMODELOS (tablas sin fecha automática / columnas / medidas / relaciones):")
    for model in report["models"]:
        print(
            f"  [{model['source']}] {model['semantic_model']}: "
            f"{model['tables_without_auto_date']} ({model['tables']}) / "
            f"{model['columns_user']} / {model['measures']} "
            f"(DAX {model['measures_with_dax']}) / {model['relationships']}"
        )

    print("\nDOCUMENTOS POR TABLERO:")
    for item in report["documents_by_dashboard"]:
        print(
            f"  {item['source_group']}: {item['docx']} docx -> "
            f"{item['semantic_model']} ({item['model_match_status']})"
        )

    redundancy = report["redundant_indicator_labels"]
    for title, key in (
        ("TÉRMINOS DE INDICADOR EN VARIOS MODELOS", "indicator_terms_in_multiple_models"),
        ("ETIQUETAS DE MÉTRICA EN VARIOS MODELOS", "master_metric_labels_in_multiple_models"),
        ("ETIQUETAS DE MÉTRICA EN VARIOS TABLEROS", "master_metric_labels_in_multiple_dashboards"),
        ("NOMBRES DOCUMENTADOS EN VARIOS TABLEROS", "documentation_names_in_multiple_dashboards"),
    ):
        items = redundancy[key]
        print(f"\n{title}: {len(items)}")
        for item in items[:40]:
            print(f"  {item['label']}  ->  {', '.join(map(str, item['in']))}")

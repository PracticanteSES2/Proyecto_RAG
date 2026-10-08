import json
import re
import unicodedata
from pathlib import Path


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalize_name(value):
    if not value:
        return ""

    value = str(value).strip().lower()
    value = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    value = re.sub(r"[^a-z0-9]", "", value)
    return value


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _resolve_path(path_value, project_root):
    if not path_value:
        return None

    path = Path(path_value)
    if not path.is_absolute():
        path = Path(project_root) / path

    return path.resolve()


# ============================================================
# ÍNDICE DEL MODELO POWER BI
# ============================================================

def build_powerbi_indexes(technical_catalog):
    table_index = {}
    measure_index = {}

    for table in technical_catalog.get("tables", []):
        table_name = table.get("name")
        if not table_name:
            continue

        normalized_table = normalize_name(table_name)
        table_index[normalized_table] = table

        for measure in table.get("measures", []):
            measure_name = measure.get("name")
            if not measure_name:
                continue

            normalized_measure = normalize_name(measure_name)
            measure_index[normalized_measure] = {
                "table": table_name,
                **measure,
            }

    return table_index, measure_index


# ============================================================
# BÚSQUEDA DE MEDIDAS
# ============================================================

def match_measure(documented_measure, measure_index):
    name = documented_measure.get("name")
    if not name:
        return None

    normalized = normalize_name(name)
    if not normalized:
        return None

    if normalized in measure_index:
        return {
            "match_type": "exact",
            "documented_name": name,
            "powerbi_measure": measure_index[normalized],
        }

    # Coincidencia parcial conservadora: evitar cadenas demasiado cortas.
    if len(normalized) >= 5:
        candidates = []

        for powerbi_name, measure in measure_index.items():
            if len(powerbi_name) < 5:
                continue

            if (
                normalized in powerbi_name
                or powerbi_name in normalized
            ):
                candidates.append((
                    abs(len(powerbi_name) - len(normalized)),
                    powerbi_name,
                    measure,
                ))

        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1]))
            _, _, measure = candidates[0]
            return {
                "match_type": "partial",
                "documented_name": name,
                "powerbi_measure": measure,
            }

    return None


# ============================================================
# BÚSQUEDA DE TABLAS REFERENCIADAS
# ============================================================

def find_referenced_tables(dashboard, table_index):
    pieces = []

    pieces.append(dashboard.get("description", ""))
    pieces.extend(dashboard.get("sql_queries", []))
    pieces.extend(dashboard.get("filters", []))
    pieces.extend(dashboard.get("visuals", []))
    pieces.extend(dashboard.get("indicators", []))
    pieces.extend(dashboard.get("business_rules", []))
    pieces.extend(dashboard.get("definitions", []))
    pieces.extend(dashboard.get("data_sources", []))
    pieces.extend(dashboard.get("notes", []))

    for measure in dashboard.get("documented_measures", []):
        pieces.append(measure.get("table", "") or "")
        pieces.append(measure.get("name", "") or "")
        pieces.append(measure.get("expression", "") or "")

    for column in dashboard.get("calculated_columns", []):
        pieces.append(column.get("table", "") or "")
        pieces.append(column.get("name", "") or "")
        pieces.append(column.get("expression", "") or "")

    for section in dashboard.get("other_sections", []):
        pieces.append(section.get("heading", "") or "")
        pieces.append(section.get("text", "") or "")
        for row in section.get("table", []) or []:
            pieces.extend(row)

    full_text = "\n".join(
        str(piece)
        for piece in pieces
        if piece
    )
    normalized_text = normalize_name(full_text)

    matches = []

    for normalized_table, table in table_index.items():
        if (
            len(normalized_table) >= 4
            and normalized_table in normalized_text
        ):
            matches.append({
                "name": table.get("name"),
                "description": table.get("description"),
                "storage_mode": table.get("storage_mode"),
            })

    return matches


# ============================================================
# FUSIÓN DE UN TABLERO
# ============================================================

def merge_dashboard(
    dashboard,
    table_index,
    measure_index,
    document_metadata=None,
    enrichment_status="available",
):
    document_metadata = document_metadata or {}

    matched_measures = []
    unmatched_measures = []

    for documented_measure in dashboard.get("documented_measures", []):
        match = match_measure(documented_measure, measure_index)

        if match:
            matched_measures.append({
                "documented": documented_measure,
                "match_type": match["match_type"],
                "powerbi": match["powerbi_measure"],
            })
        else:
            unmatched_measures.append(documented_measure)

    referenced_tables = find_referenced_tables(
        dashboard,
        table_index,
    )

    return {
        "name": dashboard.get("name"),
        "aliases": dashboard.get("aliases", []),

        # Metadata documental
        "workspace": document_metadata.get("workspace"),
        "semantic_model": document_metadata.get("semantic_model"),
        "semantic_model_key": document_metadata.get("semantic_model_key"),
        "technical_catalog": document_metadata.get("technical_catalog"),
        "source_group": document_metadata.get("source_group"),
        "source_file": document_metadata.get("source_file"),
        "source_hash": document_metadata.get("source_hash"),
        "relative_path": document_metadata.get("relative_path"),
        "document_type": document_metadata.get("document_type"),
        "manifest_path": document_metadata.get("manifest_path"),
        "enrichment_status": enrichment_status,

        # Conocimiento funcional
        "description": dashboard.get("description"),
        "filters": dashboard.get("filters", []),
        "visuals": dashboard.get("visuals", []),
        "indicators": dashboard.get("indicators", []),
        "sql_queries": dashboard.get("sql_queries", []),
        "calculated_columns": dashboard.get("calculated_columns", []),
        "business_rules": dashboard.get("business_rules", []),
        "definitions": dashboard.get("definitions", []),
        "data_sources": dashboard.get("data_sources", []),
        "notes": dashboard.get("notes", []),
        "other_sections": dashboard.get("other_sections", []),
        "documented_measures": dashboard.get("documented_measures", []),

        # Conocimiento Power BI
        "powerbi_tables": referenced_tables,
        "matched_measures": matched_measures,
        "unmatched_documented_measures": unmatched_measures,
    }


# ============================================================
# RESOLUCIÓN DE CATÁLOGO TÉCNICO POR DOCUMENTO
# ============================================================

def _catalog_for_document(
    document,
    project_root,
    default_technical_catalog=None,
):
    configured = document.get("technical_catalog")

    if configured:
        return _resolve_path(configured, project_root)

    semantic_model_key = document.get("semantic_model_key")
    if semantic_model_key:
        candidate = (
            Path(project_root)
            / "data"
            / "catalog"
            / f"{semantic_model_key}_rag.json"
        )
        if candidate.exists():
            return candidate.resolve()

    if default_technical_catalog:
        return _resolve_path(default_technical_catalog, project_root)

    return None


# ============================================================
# PROCESAR DOCUMENTOS
# ============================================================

def build_semantic_catalog(
    technical_catalog_path=None,
    semantic_documents_dir=None,
    output_path=None,
    project_root=None,
):
    """
    Construye un catálogo semántico GLOBAL.

    Conserva compatibilidad con la firma anterior:
        build_semantic_catalog(technical_catalog, semantic_docs, output)

    En la arquitectura nueva, cada documento puede declarar su propio
    technical_catalog mediante manifest.json. El primer argumento queda como
    fallback para documentación legacy.
    """
    if semantic_documents_dir is None:
        raise ValueError("semantic_documents_dir es obligatorio")

    if output_path is None:
        raise ValueError("output_path es obligatorio")

    semantic_documents_dir = Path(semantic_documents_dir)
    output_path = Path(output_path)

    if project_root is None:
        project_root = Path(__file__).resolve().parents[2]
    project_root = Path(project_root)

    documents = sorted(
        semantic_documents_dir.rglob("*.json")
    )

    print(
        "Documentos semánticos encontrados:",
        len(documents),
    )

    catalog_cache = {}
    dashboards = []
    sources = []

    for document_path in documents:
        print("\nProcesando:", document_path.relative_to(semantic_documents_dir))
        document = load_json(document_path)

        catalog_path = _catalog_for_document(
            document=document,
            project_root=project_root,
            default_technical_catalog=technical_catalog_path,
        )

        table_index = {}
        measure_index = {}
        enrichment_status = "unavailable"
        resolved_catalog = None

        if catalog_path and catalog_path.exists():
            cache_key = str(catalog_path)

            if cache_key not in catalog_cache:
                technical_catalog = load_json(catalog_path)
                catalog_cache[cache_key] = build_powerbi_indexes(
                    technical_catalog
                )

            table_index, measure_index = catalog_cache[cache_key]
            enrichment_status = "available"

            try:
                resolved_catalog = str(
                    catalog_path.relative_to(project_root)
                )
            except ValueError:
                resolved_catalog = str(catalog_path)

        elif catalog_path:
            enrichment_status = "catalog_not_found"
            resolved_catalog = str(catalog_path)

        document_metadata = {
            "workspace": document.get("workspace"),
            "semantic_model": document.get("semantic_model"),
            "semantic_model_key": document.get("semantic_model_key"),
            "technical_catalog": resolved_catalog,
            "source_group": document.get("source_group"),
            "source_file": document.get("source_file"),
            "source_hash": document.get("source_hash"),
            "relative_path": document.get("relative_path"),
            "document_type": document.get("document_type"),
            "manifest_path": document.get("manifest_path"),
        }

        sources.append({
            **document_metadata,
            "semantic_document": str(
                document_path.relative_to(semantic_documents_dir)
            ),
            "enrichment_status": enrichment_status,
        })

        for dashboard in document.get("dashboards", []):
            merged = merge_dashboard(
                dashboard=dashboard,
                table_index=table_index,
                measure_index=measure_index,
                document_metadata=document_metadata,
                enrichment_status=enrichment_status,
            )

            dashboards.append(merged)

            print(
                "  →",
                merged.get("name"),
                "| grupo:",
                merged.get("source_group"),
                "| medidas relacionadas:",
                len(merged.get("matched_measures", [])),
                "| tablas:",
                len(merged.get("powerbi_tables", [])),
                "| Power BI:",
                enrichment_status,
            )

    unique_workspaces = {
        source.get("workspace")
        for source in sources
        if source.get("workspace")
    }

    unique_models = {
        source.get("semantic_model")
        for source in sources
        if source.get("semantic_model")
    }

    semantic_catalog = {
        "schema_version": 2,
        "workspace": (
            next(iter(unique_workspaces))
            if len(unique_workspaces) == 1
            else None
        ),
        "semantic_model": (
            next(iter(unique_models))
            if len(unique_models) == 1
            else None
        ),
        "sources": sources,
        "dashboards": dashboards,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            semantic_catalog,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("\n============================")
    print("CATÁLOGO SEMÁNTICO GENERADO")
    print("============================")
    print("Fuentes:", len(sources))
    print("Tableros:", len(dashboards))
    print("Archivo:", output_path)

    return semantic_catalog


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

    SEMANTIC_DOCUMENTS_DIR = (
        PROJECT_ROOT / "data" / "semantic_documents"
    )

    OUTPUT_PATH = (
        PROJECT_ROOT
        / "data"
        / "catalog"
        / "semantic_knowledge.json"
    )

    build_semantic_catalog(
        technical_catalog_path=None,
        semantic_documents_dir=SEMANTIC_DOCUMENTS_DIR,
        output_path=OUTPUT_PATH,
        project_root=PROJECT_ROOT,
    )

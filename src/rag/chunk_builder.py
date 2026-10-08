import json
import re
import unicodedata
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


# ============================================================
# UTILIDADES
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_key(value):
    value = clean_text(value).lower()
    value = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def deterministic_id(*parts):
    key = "|".join(
        normalize_key(part)
        for part in parts
        if part is not None
    )
    return str(uuid5(NAMESPACE_URL, key or "empty_chunk"))


def _base_metadata(dashboard, section=None):
    metadata = {
        "workspace": dashboard.get("workspace"),
        "semantic_model": dashboard.get("semantic_model"),
        "semantic_model_key": dashboard.get("semantic_model_key"),
        "technical_catalog": dashboard.get("technical_catalog"),
        "dashboard": clean_text(dashboard.get("name")),
        "dashboard_aliases": dashboard.get("aliases", []),
        "source_group": dashboard.get("source_group"),
        "source_file": dashboard.get("source_file"),
        "source_hash": dashboard.get("source_hash"),
        "relative_path": dashboard.get("relative_path"),
        "document_type": dashboard.get("document_type"),
        "enrichment_status": dashboard.get("enrichment_status"),
    }

    if section:
        metadata["section"] = section

    return {
        key: value
        for key, value in metadata.items()
        if value not in (None, "", [])
    }


def _chunk(
    dashboard,
    chunk_type,
    text,
    entity_key,
    section=None,
    extra_metadata=None,
):
    text = clean_text(text)
    if not text:
        return None

    metadata = _base_metadata(
        dashboard,
        section=section,
    )

    if extra_metadata:
        metadata.update({
            key: value
            for key, value in extra_metadata.items()
            if value not in (None, "", [])
        })

    return {
        "id": deterministic_id(
            metadata.get("semantic_model_key"),
            metadata.get("source_group"),
            metadata.get("source_file"),
            metadata.get("dashboard"),
            chunk_type,
            entity_key,
        ),
        "chunk_type": chunk_type,
        "text": text,
        "metadata": metadata,
    }


def _join_items(items):
    return " ".join(
        clean_text(item)
        for item in items or []
        if clean_text(item)
    )


def _table_to_text(rows):
    lines = []
    for row in rows or []:
        cells = [clean_text(cell) for cell in row]
        if any(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


# ============================================================
# CHUNK GENERAL DEL TABLERO
# ============================================================

def build_dashboard_chunk(dashboard, workspace=None, semantic_model=None):
    dashboard_name = clean_text(dashboard.get("name"))
    description = clean_text(dashboard.get("description"))
    filters_text = _join_items(dashboard.get("filters", []))
    visuals_text = _join_items(dashboard.get("visuals", []))
    indicators_text = _join_items(dashboard.get("indicators", []))
    aliases = ", ".join(dashboard.get("aliases", []) or [])

    text = f"""
Tablero: {dashboard_name}
Alias: {aliases}
Descripción: {description}
Filtros disponibles: {filters_text}
Visualizaciones: {visuals_text}
Indicadores: {indicators_text}
"""

    return _chunk(
        dashboard=dashboard,
        chunk_type="dashboard_overview",
        text=text,
        entity_key="overview",
        section="overview",
    )


# ============================================================
# CHUNKS DE MEDIDAS POWER BI RELACIONADAS
# ============================================================

def build_measure_chunks(dashboard, workspace=None, semantic_model=None):
    chunks = []
    dashboard_name = clean_text(dashboard.get("name"))

    for item in dashboard.get("matched_measures", []):
        documented = item.get("documented", {}) or {}
        powerbi = item.get("powerbi", {}) or {}

        measure_name = clean_text(
            powerbi.get("name")
            or documented.get("name")
        )
        if not measure_name:
            continue

        table_name = clean_text(
            powerbi.get("table")
            or documented.get("table")
        )
        description = clean_text(
            powerbi.get("description")
            or documented.get("description")
        )
        expression = clean_text(powerbi.get("expression"))
        data_type = clean_text(powerbi.get("data_type"))
        format_string = clean_text(powerbi.get("format_string"))
        documented_expression = clean_text(documented.get("expression"))

        text = f"""
Tablero: {dashboard_name}
Medida Power BI: {measure_name}
Tabla: {table_name}
Descripción: {description}
Tipo de dato: {data_type}
Formato: {format_string}
Expresión DAX oficial del modelo: {expression}
Expresión documentada: {documented_expression}
"""

        chunk = _chunk(
            dashboard=dashboard,
            chunk_type="measure",
            text=text,
            entity_key=f"measure:{table_name}:{measure_name}",
            section="measures",
            extra_metadata={
                "table": table_name,
                "measure": measure_name,
                "match_type": item.get("match_type"),
                "powerbi_validated": True,
            },
        )

        if chunk:
            chunks.append(chunk)

    return chunks


def build_documented_measure_chunks(dashboard):
    """
    Conserva métricas documentadas que no pudieron vincularse con Power BI.
    Se indexan para RAG, pero con chunk_type distinto a 'measure' para evitar
    que MetricResolver las trate como una medida ejecutable certificada.
    """
    chunks = []
    dashboard_name = clean_text(dashboard.get("name"))

    for index, measure in enumerate(
        dashboard.get("unmatched_documented_measures", [])
    ):
        measure_name = clean_text(measure.get("name"))
        table_name = clean_text(measure.get("table"))
        expression = clean_text(measure.get("expression"))
        description = clean_text(measure.get("description"))

        text = f"""
Tablero: {dashboard_name}
Medida documentada: {measure_name}
Tabla documentada: {table_name}
Descripción: {description}
Expresión documentada: {expression}
Estado: documentada, no vinculada automáticamente con una medida del modelo Power BI.
"""

        chunk = _chunk(
            dashboard=dashboard,
            chunk_type="documented_measure",
            text=text,
            entity_key=f"documented_measure:{measure_name or index}",
            section="measures",
            extra_metadata={
                "table": table_name,
                "measure": measure_name,
                "powerbi_validated": False,
            },
        )

        if chunk:
            chunks.append(chunk)

    return chunks


# ============================================================
# COLUMNAS CALCULADAS
# ============================================================

def build_calculated_column_chunks(dashboard, workspace=None, semantic_model=None):
    chunks = []
    dashboard_name = clean_text(dashboard.get("name"))

    for index, column in enumerate(dashboard.get("calculated_columns", [])):
        column_name = clean_text(column.get("name"))
        table_name = clean_text(column.get("table"))
        expression = clean_text(column.get("expression"))
        description = clean_text(column.get("description"))

        if not column_name and not expression:
            continue

        text = f"""
Tablero: {dashboard_name}
Columna calculada: {column_name}
Tabla: {table_name}
Descripción: {description}
Expresión DAX: {expression}
"""

        chunk = _chunk(
            dashboard=dashboard,
            chunk_type="calculated_column",
            text=text,
            entity_key=f"column:{table_name}:{column_name or index}",
            section="calculated_columns",
            extra_metadata={
                "table": table_name,
                "column": column_name,
            },
        )

        if chunk:
            chunks.append(chunk)

    return chunks


# ============================================================
# CONTEXTO DE TABLAS
# ============================================================

def build_table_chunks(dashboard, workspace=None, semantic_model=None):
    chunks = []
    dashboard_name = clean_text(dashboard.get("name"))

    for table in dashboard.get("powerbi_tables", []):
        table_name = clean_text(table.get("name"))
        if not table_name:
            continue

        description = clean_text(table.get("description"))
        storage_mode = clean_text(table.get("storage_mode"))

        text = f"""
Tablero: {dashboard_name}
Tabla Power BI: {table_name}
Descripción: {description}
Modo de almacenamiento: {storage_mode}
"""

        chunk = _chunk(
            dashboard=dashboard,
            chunk_type="table_context",
            text=text,
            entity_key=f"table:{table_name}",
            section="tables",
            extra_metadata={
                "table": table_name,
            },
        )

        if chunk:
            chunks.append(chunk)

    return chunks


# ============================================================
# CHUNKS FUNCIONALES
# ============================================================

def build_list_chunks(dashboard, field_name, chunk_type, label):
    chunks = []
    dashboard_name = clean_text(dashboard.get("name"))

    for index, item in enumerate(dashboard.get(field_name, []) or []):
        text_value = clean_text(item)
        if not text_value:
            continue

        text = f"""
Tablero: {dashboard_name}
{label}: {text_value}
"""

        chunk = _chunk(
            dashboard=dashboard,
            chunk_type=chunk_type,
            text=text,
            entity_key=f"{field_name}:{index}:{text_value[:80]}",
            section=field_name,
        )

        if chunk:
            chunks.append(chunk)

    return chunks


def build_sql_chunks(dashboard):
    return build_list_chunks(
        dashboard,
        field_name="sql_queries",
        chunk_type="sql_query",
        label="Consulta técnica documentada",
    )


def build_other_section_chunks(dashboard):
    chunks = []
    dashboard_name = clean_text(dashboard.get("name"))

    for index, section in enumerate(dashboard.get("other_sections", []) or []):
        heading = clean_text(section.get("heading"))
        section_name = clean_text(section.get("section")) or "other"
        text_value = clean_text(section.get("text"))
        table_text = _table_to_text(section.get("table", []))

        content = "\n".join(
            value
            for value in (text_value, table_text)
            if value
        )

        if not content:
            continue

        text = f"""
Tablero: {dashboard_name}
Sección: {heading or section_name}
Contenido: {content}
"""

        chunk = _chunk(
            dashboard=dashboard,
            chunk_type="document_section",
            text=text,
            entity_key=f"other:{index}:{heading or section_name}",
            section=heading or section_name,
            extra_metadata={
                "section_category": section_name,
            },
        )

        if chunk:
            chunks.append(chunk)

    return chunks


# ============================================================
# CREAR TODOS LOS CHUNKS
# ============================================================

def build_chunks(catalog):
    chunks = []

    for dashboard in catalog.get("dashboards", []):
        overview = build_dashboard_chunk(dashboard)
        if overview:
            chunks.append(overview)

        chunks.extend(build_measure_chunks(dashboard))
        chunks.extend(build_documented_measure_chunks(dashboard))
        chunks.extend(build_calculated_column_chunks(dashboard))
        chunks.extend(build_table_chunks(dashboard))

        chunks.extend(build_list_chunks(
            dashboard,
            "filters",
            "filter",
            "Filtro documentado",
        ))
        chunks.extend(build_list_chunks(
            dashboard,
            "visuals",
            "visual",
            "Visualización documentada",
        ))
        chunks.extend(build_list_chunks(
            dashboard,
            "indicators",
            "indicator",
            "Indicador documentado",
        ))
        chunks.extend(build_list_chunks(
            dashboard,
            "business_rules",
            "business_rule",
            "Regla de negocio",
        ))
        chunks.extend(build_list_chunks(
            dashboard,
            "definitions",
            "definition",
            "Definición",
        ))
        chunks.extend(build_list_chunks(
            dashboard,
            "data_sources",
            "data_source",
            "Fuente de datos",
        ))
        chunks.extend(build_list_chunks(
            dashboard,
            "notes",
            "note",
            "Nota u observación",
        ))
        chunks.extend(build_sql_chunks(dashboard))
        chunks.extend(build_other_section_chunks(dashboard))

    # Protección contra IDs duplicados por error de configuración.
    by_id = {}
    for chunk in chunks:
        by_id[chunk["id"]] = chunk

    return list(by_id.values())


# ============================================================
# ESTADÍSTICAS
# ============================================================

def print_statistics(chunks):
    statistics = {}
    groups = set()

    for chunk in chunks:
        chunk_type = chunk["chunk_type"]
        statistics[chunk_type] = statistics.get(chunk_type, 0) + 1

        source_group = chunk.get("metadata", {}).get("source_group")
        if source_group:
            groups.add(source_group)

    print("\n==========================")
    print("CHUNKS GENERADOS")
    print("==========================")
    print("Total:", len(chunks))
    print("Grupos documentales:", len(groups))

    for chunk_type, count in sorted(statistics.items()):
        print(f"{chunk_type}: {count}")

    return {
        "total": len(chunks),
        "source_groups": sorted(groups),
        "by_type": statistics,
    }


def build_chunks_file(input_file, output_file):
    catalog = load_json(input_file)
    chunks = build_chunks(catalog)
    save_json(chunks, output_file)
    stats = print_statistics(chunks)
    print("\nArchivo generado:", output_file)
    return chunks, stats


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

    INPUT_FILE = (
        PROJECT_ROOT
        / "data"
        / "catalog"
        / "semantic_knowledge.json"
    )

    OUTPUT_FILE = (
        PROJECT_ROOT
        / "data"
        / "rag"
        / "knowledge_chunks.json"
    )

    build_chunks_file(
        INPUT_FILE,
        OUTPUT_FILE,
    )

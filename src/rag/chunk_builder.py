import json
import re
from pathlib import Path
from uuid import uuid4


# ============================================================
# UTILIDADES
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(data, path):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# CHUNK GENERAL DEL TABLERO
# ============================================================

def build_dashboard_chunk(
    dashboard,
    workspace,
    semantic_model
):

    dashboard_name = clean_text(
        dashboard.get("name")
    )

    description = clean_text(
        dashboard.get("description")
    )

    filters = dashboard.get(
        "filters",
        []
    )

    visuals = dashboard.get(
        "visuals",
        []
    )

    indicators = dashboard.get(
        "indicators",
        []
    )

    filters_text = " ".join(
        clean_text(item)
        for item in filters
        if item
    )

    visuals_text = " ".join(
        clean_text(item)
        for item in visuals
        if item
    )

    indicators_text = " ".join(
        clean_text(item)
        for item in indicators
        if item
    )

    text = f"""
Tablero: {dashboard_name}

Descripción:
{description}

Filtros disponibles:
{filters_text}

Visualizaciones:
{visuals_text}

Indicadores:
{indicators_text}
"""

    return {
        "id": str(uuid4()),

        "chunk_type": "dashboard_overview",

        "text": clean_text(text),

        "metadata": {
            "workspace": workspace,
            "semantic_model": semantic_model,
            "dashboard": dashboard_name,
            "source_file": dashboard.get(
                "source_file"
            )
        }
    }


# ============================================================
# CHUNKS DE MEDIDAS
# ============================================================

def build_measure_chunks(
    dashboard,
    workspace,
    semantic_model
):

    chunks = []

    dashboard_name = clean_text(
        dashboard.get("name")
    )

    matched_measures = dashboard.get(
        "matched_measures",
        []
    )

    for item in matched_measures:

        documented = item.get(
            "documented",
            {}
        )

        powerbi = item.get(
            "powerbi",
            {}
        )

        measure_name = clean_text(
            powerbi.get("name")
            or documented.get("name")
        )

        table_name = clean_text(
            powerbi.get("table")
            or documented.get("table")
        )

        description = clean_text(
            powerbi.get("description")
        )

        expression = clean_text(
            powerbi.get("expression")
        )

        data_type = clean_text(
            powerbi.get("data_type")
        )

        format_string = clean_text(
            powerbi.get("format_string")
        )

        documented_expression = clean_text(
            documented.get("expression")
        )

        text = f"""
Tablero: {dashboard_name}

Medida Power BI: {measure_name}

Tabla: {table_name}

Descripción:
{description}

Tipo de dato:
{data_type}

Formato:
{format_string}

Expresión DAX oficial del modelo:
{expression}

Expresión documentada:
{documented_expression}
"""

        chunks.append({
            "id": str(uuid4()),

            "chunk_type": "measure",

            "text": clean_text(text),

            "metadata": {
                "workspace": workspace,
                "semantic_model": semantic_model,
                "dashboard": dashboard_name,
                "table": table_name,
                "measure": measure_name,
                "match_type": item.get(
                    "match_type"
                ),
                "source_file": dashboard.get(
                    "source_file"
                )
            }
        })

    return chunks


# ============================================================
# COLUMNAS CALCULADAS
# ============================================================

def build_calculated_column_chunks(
    dashboard,
    workspace,
    semantic_model
):

    chunks = []

    dashboard_name = clean_text(
        dashboard.get("name")
    )

    calculated_columns = dashboard.get(
        "calculated_columns",
        []
    )

    for column in calculated_columns:

        column_name = clean_text(
            column.get("name")
        )

        table_name = clean_text(
            column.get("table")
        )

        expression = clean_text(
            column.get("expression")
        )

        if not column_name:
            continue

        text = f"""
Tablero: {dashboard_name}

Columna calculada: {column_name}

Tabla: {table_name}

Expresión DAX:
{expression}
"""

        chunks.append({
            "id": str(uuid4()),

            "chunk_type":
                "calculated_column",

            "text": clean_text(text),

            "metadata": {
                "workspace": workspace,
                "semantic_model": semantic_model,
                "dashboard": dashboard_name,
                "table": table_name,
                "column": column_name,
                "source_file": dashboard.get(
                    "source_file"
                )
            }
        })

    return chunks


# ============================================================
# CONTEXTO DE TABLAS
# ============================================================

def build_table_chunks(
    dashboard,
    workspace,
    semantic_model
):

    chunks = []

    dashboard_name = clean_text(
        dashboard.get("name")
    )

    tables = dashboard.get(
        "powerbi_tables",
        []
    )

    for table in tables:

        table_name = clean_text(
            table.get("name")
        )

        if not table_name:
            continue

        description = clean_text(
            table.get("description")
        )

        storage_mode = clean_text(
            table.get("storage_mode")
        )

        text = f"""
Tablero: {dashboard_name}

Tabla Power BI: {table_name}

Descripción:
{description}

Modo de almacenamiento:
{storage_mode}
"""

        chunks.append({
            "id": str(uuid4()),

            "chunk_type": "table_context",

            "text": clean_text(text),

            "metadata": {
                "workspace": workspace,
                "semantic_model": semantic_model,
                "dashboard": dashboard_name,
                "table": table_name,
                "source_file": dashboard.get(
                    "source_file"
                )
            }
        })

    return chunks


# ============================================================
# CREAR TODOS LOS CHUNKS
# ============================================================

def build_chunks(catalog):

    workspace = catalog.get(
        "workspace"
    )

    semantic_model = catalog.get(
        "semantic_model"
    )

    chunks = []

    for dashboard in catalog.get(
        "dashboards",
        []
    ):

        # Chunk general
        chunks.append(
            build_dashboard_chunk(
                dashboard,
                workspace,
                semantic_model
            )
        )

        # Medidas
        chunks.extend(
            build_measure_chunks(
                dashboard,
                workspace,
                semantic_model
            )
        )

        # Columnas calculadas
        chunks.extend(
            build_calculated_column_chunks(
                dashboard,
                workspace,
                semantic_model
            )
        )

        # Tablas relacionadas
        chunks.extend(
            build_table_chunks(
                dashboard,
                workspace,
                semantic_model
            )
        )

    return chunks


# ============================================================
# ESTADÍSTICAS
# ============================================================

def print_statistics(chunks):

    statistics = {}

    for chunk in chunks:

        chunk_type = chunk[
            "chunk_type"
        ]

        statistics[chunk_type] = (
            statistics.get(
                chunk_type,
                0
            )
            + 1
        )

    print("\n==========================")
    print("CHUNKS GENERADOS")
    print("==========================")

    print(
        "Total:",
        len(chunks)
    )

    for chunk_type, count in (
        statistics.items()
    ):

        print(
            f"{chunk_type}: {count}"
        )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    PROJECT_ROOT = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    INPUT_FILE = (
        PROJECT_ROOT
        / "data"
        / "catalog"
        / "tablero_de_atenciones_institucionales_semantic.json"
    )

    OUTPUT_FILE = (
        PROJECT_ROOT
        / "data"
        / "rag"
        / "tablero_de_atenciones_institucionales_chunks.json"
    )

    catalog = load_json(
        INPUT_FILE
    )

    chunks = build_chunks(
        catalog
    )

    save_json(
        chunks,
        OUTPUT_FILE
    )

    print_statistics(
        chunks
    )

    print(
        "\nArchivo generado:"
    )

    print(
        OUTPUT_FILE
    )
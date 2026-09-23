import json
import re
import unicodedata
from pathlib import Path


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalize_name(value):
    """
    Normaliza nombres para poder comparar:

    PROM_CIRUGÍAS
    Prom_Cirugias
    prom cirugias

    como conceptos equivalentes.
    """

    if not value:
        return ""

    value = str(value).strip().lower()

    # Eliminar tildes
    value = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )

    # Conservar solo letras y números
    value = re.sub(r"[^a-z0-9]", "", value)

    return value


# ============================================================
# CARGA DE ARCHIVOS
# ============================================================

def load_json(path):
    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


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

            normalized_measure = normalize_name(
                measure_name
            )

            measure_index[normalized_measure] = {
                "table": table_name,
                **measure
            }

    return table_index, measure_index


# ============================================================
# BÚSQUEDA DE MEDIDAS
# ============================================================

def match_measure(
    documented_measure,
    measure_index
):

    name = documented_measure.get("name")

    if not name:
        return None

    normalized = normalize_name(name)

    # Coincidencia exacta
    if normalized in measure_index:

        return {
            "match_type": "exact",
            "documented_name": name,
            "powerbi_measure":
                measure_index[normalized]
        }

    # Coincidencia parcial
    for powerbi_name, measure in measure_index.items():

        if (
            normalized in powerbi_name
            or powerbi_name in normalized
        ):

            return {
                "match_type": "partial",
                "documented_name": name,
                "powerbi_measure": measure
            }

    return None


# ============================================================
# BÚSQUEDA DE TABLAS REFERENCIADAS
# ============================================================

def find_referenced_tables(
    dashboard,
    table_index
):

    # Reunir todo el texto disponible
    pieces = []

    pieces.append(
        dashboard.get("description", "")
    )

    pieces.extend(
        dashboard.get("sql_queries", [])
    )

    pieces.extend(
        dashboard.get("filters", [])
    )

    pieces.extend(
        dashboard.get("visuals", [])
    )

    pieces.extend(
        dashboard.get("indicators", [])
    )

    for measure in dashboard.get(
        "documented_measures",
        []
    ):

        pieces.append(
            measure.get("table", "") or ""
        )

        pieces.append(
            measure.get("name", "") or ""
        )

        pieces.append(
            measure.get("expression", "") or ""
        )

    full_text = "\n".join(
        str(piece)
        for piece in pieces
        if piece
    )

    normalized_text = normalize_name(
        full_text
    )

    matches = []

    for normalized_table, table in table_index.items():

        if (
            len(normalized_table) >= 4
            and normalized_table in normalized_text
        ):

            matches.append({
                "name": table.get("name"),
                "description":
                    table.get("description"),
                "storage_mode":
                    table.get("storage_mode")
            })

    return matches


# ============================================================
# FUSIÓN DE UN TABLERO
# ============================================================

def merge_dashboard(
    dashboard,
    table_index,
    measure_index
):

    matched_measures = []
    unmatched_measures = []

    for documented_measure in dashboard.get(
        "documented_measures",
        []
    ):

        match = match_measure(
            documented_measure,
            measure_index
        )

        if match:

            matched_measures.append({
                "documented": documented_measure,
                "match_type":
                    match["match_type"],
                "powerbi":
                    match["powerbi_measure"]
            })

        else:

            unmatched_measures.append(
                documented_measure
            )

    referenced_tables = find_referenced_tables(
        dashboard,
        table_index
    )

    return {

        "name":
            dashboard.get("name"),

        # ------------------------
        # CONOCIMIENTO FUNCIONAL
        # ------------------------

        "description":
            dashboard.get("description"),

        "filters":
            dashboard.get("filters", []),

        "visuals":
            dashboard.get("visuals", []),

        "indicators":
            dashboard.get("indicators", []),

        "sql_queries":
            dashboard.get("sql_queries", []),

        "calculated_columns":
            dashboard.get(
                "calculated_columns",
                []
            ),

        # ------------------------
        # CONOCIMIENTO POWER BI
        # ------------------------

        "powerbi_tables":
            referenced_tables,

        "matched_measures":
            matched_measures,

        # Muy importante:
        # conservar lo que no pudo relacionarse
        "unmatched_documented_measures":
            unmatched_measures
    }


# ============================================================
# PROCESAR DOCUMENTOS
# ============================================================

def build_semantic_catalog(
    technical_catalog_path,
    semantic_documents_dir,
    output_path
):

    technical_catalog = load_json(
        technical_catalog_path
    )

    table_index, measure_index = (
        build_powerbi_indexes(
            technical_catalog
        )
    )

    documents = sorted(
        Path(
            semantic_documents_dir
        ).rglob("*.json")
    )

    print(
        "Documentos semánticos encontrados:",
        len(documents)
    )

    dashboards = []

    for document_path in documents:

        print(
            "\nProcesando:",
            document_path.name
        )

        document = load_json(
            document_path
        )

        for dashboard in document.get(
            "dashboards",
            []
        ):

            merged = merge_dashboard(
                dashboard,
                table_index,
                measure_index
            )

            merged["source_file"] = (
                document.get("source_file")
            )

            dashboards.append(merged)

            print(
                "  →",
                merged["name"],
                "| medidas relacionadas:",
                len(
                    merged[
                        "matched_measures"
                    ]
                ),
                "| tablas:",
                len(
                    merged[
                        "powerbi_tables"
                    ]
                )
            )

    semantic_catalog = {

        "workspace":
            technical_catalog.get(
                "workspace"
            ),

        "semantic_model":
            technical_catalog.get(
                "semantic_model"
            ),

        "dashboards":
            dashboards
    }

    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            semantic_catalog,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("\n============================")
    print("CATÁLOGO SEMÁNTICO GENERADO")
    print("============================")

    print(
        "Tableros:",
        len(dashboards)
    )

    print(
        "Archivo:",
        output_path
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

    TECHNICAL_CATALOG = (
        PROJECT_ROOT
        / "data"
        / "catalog"
        / "tablero_de_atenciones_institucionales_rag.json"
    )

    SEMANTIC_DOCUMENTS_DIR = (
        PROJECT_ROOT
        / "data"
        / "semantic_documents"
        / "tablero_de_atenciones_institucionales"
    )

    OUTPUT_PATH = (
        PROJECT_ROOT
        / "data"
        / "catalog"
        / "tablero_de_atenciones_institucionales_semantic.json"
    )

    build_semantic_catalog(
        TECHNICAL_CATALOG,
        SEMANTIC_DOCUMENTS_DIR,
        OUTPUT_PATH
    )
import json
import re
from pathlib import Path


# ============================================================
# UTILIDADES
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def normalize_heading(text):
    return (
        clean_text(text)
        .upper()
        .replace("Ó", "O")
        .replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ú", "U")
    )


def is_heading(block):
    """
    Detecta si un párrafo funciona como encabezado.
    """

    if block.get("type") != "paragraph":
        return False

    text = clean_text(block.get("text", ""))

    if not text:
        return False

    style = str(block.get("style", "")).lower()

    if "heading" in style or "titulo" in style or "title" in style:
        return True

    # Encabezados escritos completamente en mayúsculas
    if len(text) <= 120 and text.isupper():
        return True

    return False


# ============================================================
# CLASIFICACIÓN DE SECCIONES
# ============================================================

def classify_heading(text):
    """
    Convierte los encabezados de los Word
    en categorías semánticas comunes.
    """

    text = normalize_heading(text)

    if (
        "CONSULTA UTILIZADA" in text
        or "SIGUIENTE CONSULTA" in text
        or "CONSULTAS PARA ESTE TABLERO" in text
        or text.startswith("QUERY")
    ):
        return "sql"

    if "MEDIDAS UTILIZADAS" in text:
        return "measures"

    if "COLUMNAS CALCULADAS" in text:
        return "calculated_columns"

    if (
        "DESCRIPCION DE LOS VISUALES" in text
        or "DESCRIPCION DE LAS VISUALIZACIONES" in text
    ):
        return "visuals"

    if text == "FILTROS" or "FILTROS Y SEGMENTADORES" in text:
        return "filters"

    if "TARJETAS DE INDICADORES" in text:
        return "indicators"

    return None


# ============================================================
# TABLAS CON DAX
# ============================================================

def parse_measure_table(block):
    """
    Intenta interpretar tablas del tipo:

    Tabla | Nombre Medida | DAX
    """

    rows = block.get("rows", [])

    if not rows:
        return []

    header = [
        normalize_heading(cell)
        for cell in rows[0]
    ]

    # Detectar posiciones
    table_index = None
    name_index = None
    dax_index = None

    for i, cell in enumerate(header):

        if "TABLA" in cell:
            table_index = i

        elif "NOMBRE" in cell or "MEDIDA" in cell or "COLUMNA" in cell:
            if name_index is None:
                name_index = i

        if "DAX" in cell:
            dax_index = i

    results = []

    for row in rows[1:]:

        if not any(clean_text(cell) for cell in row):
            continue

        result = {
            "table": (
                clean_text(row[table_index])
                if table_index is not None
                and table_index < len(row)
                else None
            ),

            "name": (
                clean_text(row[name_index])
                if name_index is not None
                and name_index < len(row)
                else None
            ),

            "expression": (
                clean_text(row[dax_index])
                if dax_index is not None
                and dax_index < len(row)
                else None
            )
        }

        results.append(result)

    return results


# ============================================================
# NORMALIZACIÓN DE UN TABLERO
# ============================================================

def normalize_dashboard(dashboard):
    """
    Transforma blocks sin estructura semántica
    en una ficha funcional del tablero.
    """

    blocks = dashboard.get("blocks", [])

    normalized = {
        "name": dashboard.get("name"),

        "description": [],

        "sql_queries": [],

        "documented_measures": [],

        "calculated_columns": [],

        "filters": [],

        "visuals": [],

        "indicators": [],

        "other_sections": []
    }

    current_section = "description"

    # Permite agrupar SQL repartido
    sql_buffer = []

    for block in blocks:

        # ----------------------------------------------------
        # PÁRRAFOS
        # ----------------------------------------------------

        if block.get("type") == "paragraph":

            text = clean_text(
                block.get("text", "")
            )

            if not text:
                continue

            if is_heading(block):

                detected_section = classify_heading(text)

                if detected_section:

                    # Guardar SQL pendiente antes de cambiar
                    if current_section == "sql" and sql_buffer:
                        normalized["sql_queries"].append(
                            "\n".join(sql_buffer)
                        )
                        sql_buffer = []

                    current_section = detected_section
                    continue

            # Guardar según sección actual

            if current_section == "description":

                normalized["description"].append(text)

            elif current_section == "sql":

                sql_buffer.append(text)

            elif current_section == "filters":

                normalized["filters"].append(text)

            elif current_section == "visuals":

                normalized["visuals"].append(text)

            elif current_section == "indicators":

                normalized["indicators"].append(text)

            else:

                normalized["other_sections"].append({
                    "section": current_section,
                    "text": text
                })

        # ----------------------------------------------------
        # TABLAS
        # ----------------------------------------------------

        elif block.get("type") == "table":

            if current_section == "measures":

                measures = parse_measure_table(block)

                normalized[
                    "documented_measures"
                ].extend(measures)

            elif current_section == "calculated_columns":

                calculated = parse_measure_table(block)

                normalized[
                    "calculated_columns"
                ].extend(calculated)

            else:

                normalized[
                    "other_sections"
                ].append({
                    "section": current_section,
                    "table": block.get("rows", [])
                })

    # SQL final
    if sql_buffer:

        normalized["sql_queries"].append(
            "\n".join(sql_buffer)
        )

    # Convertir descripción a texto
    normalized["description"] = " ".join(
        normalized["description"]
    )

    return normalized


# ============================================================
# NORMALIZACIÓN DEL DOCUMENTO
# ============================================================

def normalize_document(data):
    """
    Normaliza todos los tableros de un documento.
    """

    normalized_dashboards = []

    for dashboard in data.get("dashboards", []):

        normalized_dashboards.append(
            normalize_dashboard(dashboard)
        )

    return {
        "workspace": data.get("workspace"),

        "semantic_model":
            data.get("semantic_model"),

        "semantic_model_key":
            data.get("semantic_model_key"),

        "source_file":
            data.get("source_file"),

        "relative_path":
            data.get("relative_path"),

        "dashboards":
            normalized_dashboards
    }


# ============================================================
# PROCESAMIENTO MASIVO
# ============================================================

def normalize_all_documents(
    processed_dir,
    output_dir
):

    processed_dir = Path(processed_dir)
    output_dir = Path(output_dir)

    documents = sorted(
        processed_dir.rglob("*.json")
    )

    print(
        f"JSON encontrados: {len(documents)}"
    )

    total_dashboards = 0

    for document_path in documents:

        relative_path = (
            document_path.relative_to(
                processed_dir
            )
        )

        print(
            f"\nNormalizando: {relative_path}"
        )

        with open(
            document_path,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        normalized = normalize_document(data)

        output_path = (
            output_dir
            / relative_path
        )

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
                normalized,
                file,
                ensure_ascii=False,
                indent=2
            )

        count = len(
            normalized["dashboards"]
        )

        total_dashboards += count

        print(
            f"  ✓ Tableros normalizados: {count}"
        )

        for dashboard in normalized["dashboards"]:

            print(
                "     →",
                dashboard["name"]
            )

    print("\n===========================")
    print("NORMALIZACION FINALIZADA")
    print("===========================")

    print(
        "Documentos:",
        len(documents)
    )

    print(
        "Tableros:",
        total_dashboards
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

    PROCESSED_DIR = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / "tablero_de_atenciones_institucionales"
    )

    OUTPUT_DIR = (
        PROJECT_ROOT
        / "data"
        / "semantic_documents"
    )

    normalize_all_documents(
        PROCESSED_DIR,
        OUTPUT_DIR
    )
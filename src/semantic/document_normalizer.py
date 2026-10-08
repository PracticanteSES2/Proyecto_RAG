import json
import re
import unicodedata
from pathlib import Path


# ============================================================
# UTILIDADES
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = str(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def normalize_heading(text):
    text = clean_text(text).upper()
    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", text).strip()


def is_heading(block):
    if block.get("type") != "paragraph":
        return False

    text = clean_text(block.get("text", ""))
    if not text:
        return False

    style = str(block.get("style", "")).lower()

    if any(token in style for token in ("heading", "titulo", "title")):
        return True

    # Títulos en mayúsculas, evitando párrafos excesivamente largos.
    if len(text) <= 140 and text.isupper():
        return True

    return False


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ============================================================
# CLASIFICACIÓN DE SECCIONES
# ============================================================

def classify_heading(text):
    """
    Mapea encabezados heterogéneos a secciones semánticas comunes.
    Los títulos no reconocidos se conservan como other_section y no se
    mezclan silenciosamente con la sección anterior.
    """
    text = normalize_heading(text)

    if (
        "CONSULTA UTILIZADA" in text
        or "SIGUIENTE CONSULTA" in text
        or "CONSULTAS PARA ESTE TABLERO" in text
        or "CONSULTA SQL" in text
        or text.startswith("QUERY")
        or text == "SQL"
    ):
        return "sql"

    if (
        "MEDIDAS UTILIZADAS" in text
        or "MEDIDAS DAX" in text
        or text in {"MEDIDAS", "METRICAS", "METRICAS UTILIZADAS"}
    ):
        return "measures"

    if (
        "COLUMNAS CALCULADAS" in text
        or "COLUMNA CALCULADA" in text
    ):
        return "calculated_columns"

    if (
        "DESCRIPCION DE LOS VISUALES" in text
        or "DESCRIPCION DE LAS VISUALIZACIONES" in text
        or text in {"VISUALES", "VISUALIZACIONES", "GRAFICOS"}
    ):
        return "visuals"

    if (
        text == "FILTROS"
        or "FILTROS Y SEGMENTADORES" in text
        or text == "SEGMENTADORES"
        or text.startswith("FILTROS DISPONIBLES")
    ):
        return "filters"

    if (
        "TARJETAS DE INDICADORES" in text
        or text in {"INDICADORES", "INDICADORES PRINCIPALES", "TARJETAS"}
    ):
        return "indicators"

    if any(
        token in text
        for token in (
            "REGLAS DE NEGOCIO",
            "REGLA DE NEGOCIO",
            "LOGICA DE NEGOCIO",
            "CRITERIOS DE NEGOCIO",
        )
    ):
        return "business_rules"

    if any(
        token in text
        for token in (
            "DEFINICIONES",
            "GLOSARIO",
            "CONCEPTOS",
        )
    ):
        return "definitions"

    if any(
        token in text
        for token in (
            "FUENTES DE DATOS",
            "FUENTE DE DATOS",
            "ORIGEN DE DATOS",
            "ORIGENES DE DATOS",
        )
    ):
        return "data_sources"

    if any(
        token in text
        for token in (
            "OBSERVACIONES",
            "NOTAS",
            "CONSIDERACIONES",
        )
    ):
        return "notes"

    if any(
        token in text
        for token in (
            "OBJETIVO",
            "PROPOSITO",
            "DESCRIPCION DEL TABLERO",
            "ALCANCE",
        )
    ):
        return "description"

    return None


# ============================================================
# TABLAS CON DAX
# ============================================================

def parse_measure_table(block):
    """Interpreta tablas tipo Tabla | Nombre Medida/Columna | DAX."""
    rows = block.get("rows", [])
    if not rows:
        return []

    header = [normalize_heading(cell) for cell in rows[0]]

    table_index = None
    name_index = None
    dax_index = None
    description_index = None

    for index, cell in enumerate(header):
        if "TABLA" in cell and table_index is None:
            table_index = index

        if (
            name_index is None
            and (
                "NOMBRE" in cell
                or "MEDIDA" in cell
                or "COLUMNA" in cell
            )
        ):
            name_index = index

        if "DAX" in cell or "EXPRESION" in cell:
            dax_index = index

        if "DESCRIPCION" in cell:
            description_index = index

    # Si no reconocemos ninguna columna estructurada, no inventamos.
    if name_index is None and dax_index is None and table_index is None:
        return []

    results = []

    for row in rows[1:]:
        if not any(clean_text(cell) for cell in row):
            continue

        def get_cell(position):
            if position is None or position >= len(row):
                return None
            return clean_text(row[position]) or None

        result = {
            "table": get_cell(table_index),
            "name": get_cell(name_index),
            "expression": get_cell(dax_index),
            "description": get_cell(description_index),
        }

        if any(result.values()):
            results.append(result)

    return results


# ============================================================
# NORMALIZACIÓN DE UN TABLERO
# ============================================================

def normalize_dashboard(dashboard):
    blocks = dashboard.get("blocks", [])

    normalized = {
        "name": clean_text(dashboard.get("name")),
        "aliases": [
            clean_text(alias)
            for alias in _as_list(dashboard.get("aliases"))
            if clean_text(alias)
        ],
        "source_file": dashboard.get("source_file"),
        "description": [],
        "sql_queries": [],
        "documented_measures": [],
        "calculated_columns": [],
        "filters": [],
        "visuals": [],
        "indicators": [],
        "business_rules": [],
        "definitions": [],
        "data_sources": [],
        "notes": [],
        "other_sections": [],
    }

    current_section = "description"
    current_heading = "Descripción"
    sql_buffer = []

    def flush_sql():
        nonlocal sql_buffer
        if sql_buffer:
            normalized["sql_queries"].append("\n".join(sql_buffer))
            sql_buffer = []

    for block in blocks:
        block_type = block.get("type")

        if block_type == "paragraph":
            text = clean_text(block.get("text", ""))
            if not text:
                continue

            if is_heading(block):
                detected = classify_heading(text)

                if current_section == "sql":
                    flush_sql()

                if detected:
                    current_section = detected
                    current_heading = text
                else:
                    # Encabezado desconocido: creamos una sección propia.
                    current_section = "other"
                    current_heading = text
                continue

            if current_section == "description":
                normalized["description"].append(text)
            elif current_section == "sql":
                sql_buffer.append(text)
            elif current_section in {
                "filters",
                "visuals",
                "indicators",
                "business_rules",
                "definitions",
                "data_sources",
                "notes",
            }:
                normalized[current_section].append(text)
            elif current_section in {"measures", "calculated_columns"}:
                # Algunas documentaciones escriben medidas/columnas como texto
                # en vez de tabla. Se conserva sin inventar estructura DAX.
                normalized["other_sections"].append({
                    "section": current_section,
                    "heading": current_heading,
                    "text": text,
                })
            else:
                normalized["other_sections"].append({
                    "section": "other",
                    "heading": current_heading,
                    "text": text,
                })

        elif block_type == "table":
            if current_section == "sql":
                flush_sql()

            if current_section == "measures":
                parsed = parse_measure_table(block)
                if parsed:
                    normalized["documented_measures"].extend(parsed)
                else:
                    normalized["other_sections"].append({
                        "section": "measures",
                        "heading": current_heading,
                        "table": block.get("rows", []),
                    })

            elif current_section == "calculated_columns":
                parsed = parse_measure_table(block)
                if parsed:
                    normalized["calculated_columns"].extend(parsed)
                else:
                    normalized["other_sections"].append({
                        "section": "calculated_columns",
                        "heading": current_heading,
                        "table": block.get("rows", []),
                    })

            else:
                normalized["other_sections"].append({
                    "section": current_section,
                    "heading": current_heading,
                    "table": block.get("rows", []),
                })

    flush_sql()
    normalized["description"] = " ".join(normalized["description"])

    return normalized


# ============================================================
# NORMALIZACIÓN DEL DOCUMENTO
# ============================================================

def normalize_document(data):
    normalized_dashboards = [
        normalize_dashboard(dashboard)
        for dashboard in data.get("dashboards", [])
    ]

    return {
        "schema_version": 2,
        "workspace": data.get("workspace"),
        "semantic_model": data.get("semantic_model"),
        "semantic_model_key": data.get("semantic_model_key"),
        "technical_catalog": data.get("technical_catalog"),
        "source_group": data.get("source_group"),
        "source_file": data.get("source_file"),
        "source_hash": data.get("source_hash"),
        "relative_path": data.get("relative_path"),
        "source_folder": data.get("source_folder"),
        "document_type": data.get("document_type"),
        "manifest_path": data.get("manifest_path"),
        "default_dashboard": data.get("default_dashboard"),
        "dashboard_aliases": data.get("dashboard_aliases", []),
        "dashboards": normalized_dashboards,
    }


# ============================================================
# PROCESAMIENTO MASIVO
# ============================================================

def normalize_all_documents(processed_dir, output_dir):
    processed_dir = Path(processed_dir)
    output_dir = Path(output_dir)

    documents = sorted(processed_dir.rglob("*.json"))
    print(f"JSON encontrados: {len(documents)}")

    total_dashboards = 0
    processed = 0
    errors = []

    for document_path in documents:
        relative_path = document_path.relative_to(processed_dir)
        print(f"\nNormalizando: {relative_path}")

        try:
            with open(document_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            normalized = normalize_document(data)
            output_path = output_dir / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as file:
                json.dump(
                    normalized,
                    file,
                    ensure_ascii=False,
                    indent=2,
                )

            count = len(normalized.get("dashboards", []))
            total_dashboards += count
            processed += 1

            print(f"  ✓ Tableros normalizados: {count}")
            for dashboard in normalized.get("dashboards", []):
                print("     →", dashboard.get("name"))

        except Exception as error:
            errors.append({
                "file": str(relative_path),
                "error_type": type(error).__name__,
                "error": str(error),
            })
            print(f"  ✗ {type(error).__name__}: {error}")

    print("\n===========================")
    print("NORMALIZACION FINALIZADA")
    print("===========================")
    print("Documentos procesados:", processed)
    print("Tableros:", total_dashboards)
    print("Errores:", len(errors))

    return {
        "documents_found": len(documents),
        "documents_processed": processed,
        "dashboards": total_dashboards,
        "errors": errors,
    }


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
    OUTPUT_DIR = PROJECT_ROOT / "data" / "semantic_documents"

    normalize_all_documents(
        PROCESSED_DIR,
        OUTPUT_DIR,
    )

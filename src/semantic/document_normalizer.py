import json
import re
import sys
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


SQL_START_WORDS = (
    "SELECT", "WITH", "FROM", "WHERE", "LEFT", "RIGHT", "INNER", "OUTER",
    "JOIN", "UNION", "GROUP", "ORDER", "HAVING", "CASE", "WHEN", "THEN",
    "ELSE", "END", "AND", "OR", "ON", "AS", "OVER", "CROSS", "DECLARE",
    "SET", "INSERT", "UPDATE", "DELETE", "CALCULATE", "DIVIDE", "VAR",
    "RETURN", "IF", "SUM", "COUNT", "FORMAT", "COALESCE", "CONVERT",
)


def looks_like_code(text):
    """Heurística: línea de SQL/DAX que nunca debe tratarse como encabezado."""
    text = clean_text(text)
    if not text:
        return False
    if text.startswith(("--", ",", ")", "(", "/*")) or text.endswith((",", ";", "(")):
        return True
    if "=" in text or "<>" in text or "[" in text and "]" in text:
        return True
    first = re.split(r"[\s(]", text, maxsplit=1)[0].upper()
    if first in SQL_START_WORDS and (len(text.split()) > 1 or "(" in text or first in {"SELECT", "END", "ELSE"}):
        return True
    if re.search(r"\b[A-Z_]+\.[A-Za-z_]+\b", text) and len(text.split()) <= 8:
        return True
    return False


def is_heading_style(block):
    style = str(block.get("style") or "").lower()
    return any(token in style for token in ("heading", "titulo", "title"))


def is_heading(block):
    """
    Encabezado = estilo de encabezado de Word O un párrafo corto que
    classify_heading reconoce. Un párrafo en mayúsculas NO es encabezado por
    sí solo: las consultas SQL documentadas suelen estar en mayúsculas.
    """
    if block.get("type") != "paragraph":
        return False

    text = clean_text(block.get("text", ""))
    if not text:
        return False

    if is_heading_style(block):
        return True

    return detect_section(text) is not None


STRONG_SECTIONS = {"sql", "measures", "calculated_columns", "visuals"}


def detect_section(text):
    """
    Devuelve la sección si el párrafo (no necesariamente en mayúsculas ni con
    estilo de encabezado) es un encabezado reconocido, tolerando typos.
    """
    text = clean_text(text)
    if not text or len(text) > 160 or chr(10) in text:
        return None
    if looks_like_code(text) and not re.match(r"(?i)^medidas?\s*:", text):
        return None

    detected = classify_heading(text)
    if detected is None:
        return None
    if detected in STRONG_SECTIONS:
        return detected
    # Secciones genéricas: solo si el texto es corto (evita títulos de visuales).
    if len(text) <= 60 and (text.isupper() or len(text.split()) <= 4):
        return detected
    return None


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
        or re.search(r"\bCONSU?L?TAS? (?:UTILIZAD|IMPLEMENTAD|USAD|REALIZAD)\w*", text)
        or re.search(r"\bSIGUIENTES? CONSU?L?TAS?\b", text)
        or "CONSULTA UTILIZADA" in text
        or "CONSULTAS PARA ESTE TABLERO" in text
        or "CONSULTA SQL" in text
        or text.startswith("QUERY")
        or text == "SQL"
    ):
        return "sql"

    if (
        "MEDIDAS UTILIZADAS" in text
        or re.match(r"^(?:LAS )?MEDIDAS?\b", text)
        or re.search(r"\bSIGUIENTES MEDIDAS\b", text)
        or "MEDIDAS DAX" in text
        or text in {"MEDIDAS", "METRICAS", "METRICAS UTILIZADAS"}
    ):
        return "measures"

    if (
        "COLUMNAS CALCULADAS" in text
        or "COLUMNA CALCULADA" in text
        or re.search(r"\bCOLUMNAS? CA\w{0,3}CULADAS?\b", text)
    ):
        return "calculated_columns"

    if (
        "DESCRIPCION DE LOS VISUALES" in text
        or "DESCRIPCION DE LAS VISUALIZACIONES" in text
        or re.search(r"\bDES\w{0,5}CION(?:ES)? DE (?:LOS |LAS )?VISUAL", text)
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

        if "DAX" in cell or "EXPRESION" in cell or "CONSULTA" in cell:
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

        expression = result.get("expression")
        name = result.get("name")
        if expression and name:
            prefix = re.match(
                r"^\[?" + re.escape(name) + r"\]?\s*=\s*", expression
            )
            if prefix and prefix.end() < len(expression):
                result["expression"] = expression[prefix.end():].strip()

        if any(result.values()):
            results.append(result)

    return results


# ============================================================
# TEXTO LIBRE: MEDIDAS / COLUMNAS "NOMBRE = DAX" Y VISUALES
# ============================================================

MEASURE_START_RE = re.compile(
    r"^(?:medidas?|columna(?:\s+calculada)?)\s*:\s*(?P<name>[^=]{1,80}?)\s*(?:=\s*(?P<rest>.*))?$",
    re.IGNORECASE | re.DOTALL,
)

NAMED_EXPRESSION_RE = re.compile(
    r"^(?P<name>[A-Za-z_%#À-ſ][^=()\"',;]{0,60}?)\s*=\s*(?P<rest>.*)$",
    re.DOTALL,
)


def _is_dax_continuation(text):
    first = re.split(r"[\s(]", text.strip(), maxsplit=1)[0].upper()
    return first in {"VAR", "RETURN"}


def parse_named_expression_line(text):
    """
    Devuelve (nombre, resto) si la línea inicia una medida/columna escrita como
    texto ('Nombre = DAX' o 'Medida: Nombre'); None en caso contrario.
    """
    text = clean_text(text)
    if not text or _is_dax_continuation(text):
        return None

    match = MEASURE_START_RE.match(text)
    if match:
        return clean_text(match.group("name")), clean_text(match.group("rest") or "")

    match = NAMED_EXPRESSION_RE.match(text)
    if match and not text.startswith("--"):
        return clean_text(match.group("name")), clean_text(match.group("rest") or "")

    return None


def _looks_like_description_title(text):
    text = clean_text(text)
    return bool(text) and len(text) <= 110 and not text.endswith((".", ":", ";"))


def append_visual_lines(visuals, state, text):
    """
    Agrupa 'título + descripción' en una entrada de visual.
    visuals: lista de strings; state: dict con el visual en curso.
    """
    lines = [line.strip() for line in str(text).split("\n") if line.strip()]

    for line in lines:
        current = state.get("current")
        is_title = _looks_like_description_title(line)

        if current is None or (is_title and current["description"]):
            if current is not None:
                visuals.append(_render_visual(current))
            state["current"] = {
                "title": line if is_title else "",
                "description": [] if is_title else [line],
            }
        elif is_title and not current["description"] and current["title"]:
            # Dos títulos seguidos: el anterior queda como visual sin descripción.
            visuals.append(_render_visual(current))
            state["current"] = {"title": line, "description": []}
        else:
            current["description"].append(line)


def _render_visual(visual):
    title = clean_text(visual.get("title"))
    description = clean_text(" ".join(visual.get("description", [])))
    if title and description:
        return f"{title}: {description}"
    return title or description


def flush_visual(visuals, state):
    current = state.get("current")
    if current is not None:
        rendered = _render_visual(current)
        if rendered:
            visuals.append(rendered)
    state["current"] = None


def table_target(block, current_section):
    """Decide si una tabla estructurada contiene medidas o columnas calculadas."""
    rows = block.get("rows", [])
    if not rows:
        return None

    header = " ".join(normalize_heading(cell) for cell in rows[0])
    has_expression = (
        "DAX" in header or "EXPRESION" in header or "CONSULTA" in header
    )
    if not has_expression:
        return None

    parsed = parse_measure_table(block)
    if not parsed:
        return None

    if "COLUMNA" in header or current_section == "calculated_columns":
        return "calculated_columns", parsed
    return "measures", parsed


# ============================================================
# NORMALIZACIÓN DE UN TABLERO
# ============================================================

LIST_SECTIONS = {
    "filters",
    "indicators",
    "business_rules",
    "definitions",
    "data_sources",
    "notes",
}


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
    visual_state = {"current": None}
    # Medida/columna escrita como texto que sigue acumulando líneas DAX.
    open_expression = None

    def flush_sql():
        nonlocal sql_buffer
        if sql_buffer:
            normalized["sql_queries"].append("\n".join(sql_buffer))
            sql_buffer = []

    def flush_expression():
        nonlocal open_expression
        if open_expression is not None:
            target, item = open_expression
            item["expression"] = clean_text(
                "\n".join(item.pop("_lines", []))
            ) or None
            if item.get("name") or item.get("expression"):
                normalized[target].append(item)
            open_expression = None

    def close_section():
        flush_sql()
        flush_expression()
        flush_visual(normalized["visuals"], visual_state)

    def switch_section(section, heading):
        nonlocal current_section, current_heading
        close_section()
        current_section = section
        current_heading = heading

    for block in blocks:
        block_type = block.get("type")

        if block_type == "paragraph":
            text = clean_text(block.get("text", ""))
            if not text:
                continue

            detected = detect_section(text)
            styled = is_heading_style(block)

            # Dentro de visuales, 'Filtros' / 'Tarjetas de indicadores' son
            # títulos de visual y no secciones nuevas.
            if (
                current_section == "visuals"
                and detected in {
                    "filters", "indicators", "business_rules", "definitions",
                    "data_sources", "notes", "description",
                }
                and not styled
            ):
                detected = None

            # Dentro de SQL/medidas solo cortan secciones fuertes: el texto
            # técnico nunca se trata como encabezado por estar en mayúsculas.
            if (
                current_section in {"sql", "measures", "calculated_columns"}
                and detected not in STRONG_SECTIONS
                and not styled
            ):
                detected = None

            if detected:
                # 'Medida: Nombre' abre una medida concreta, no una sección.
                single = (
                    detected == "measures"
                    and re.match(r"(?i)^medidas?\s*:", text)
                )
                if single:
                    if current_section != "measures":
                        switch_section("measures", text)
                    flush_expression()
                    parsed = parse_named_expression_line(text)
                    if parsed:
                        name, rest = parsed
                        open_expression = ("documented_measures", {
                            "table": None,
                            "name": name,
                            "description": None,
                            "_lines": [rest] if rest else [],
                        })
                    continue

                switch_section(detected, text)
                continue

            if styled:
                # Encabezado desconocido: sección propia, el texto se conserva.
                switch_section("other", text)
                continue

            if current_section == "description":
                normalized["description"].append(text)
            elif current_section == "sql":
                sql_buffer.append(text)
            elif current_section == "visuals":
                append_visual_lines(normalized["visuals"], visual_state, text)
            elif current_section in LIST_SECTIONS:
                normalized[current_section].append(text)
            elif current_section in {"measures", "calculated_columns"}:
                target = (
                    "documented_measures"
                    if current_section == "measures"
                    else "calculated_columns"
                )
                parsed = parse_named_expression_line(text)

                if parsed:
                    flush_expression()
                    name, rest = parsed
                    open_expression = (target, {
                        "table": None,
                        "name": name,
                        "description": None,
                        "_lines": [rest] if rest else [],
                    })
                elif open_expression is not None:
                    open_expression[1]["_lines"].append(text)
                else:
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
            flush_sql()
            flush_expression()
            flush_visual(normalized["visuals"], visual_state)

            routed = table_target(block, current_section)

            if routed:
                target, parsed = routed
                key = (
                    "documented_measures"
                    if target == "measures"
                    else "calculated_columns"
                )
                normalized[key].extend(parsed)
            else:
                normalized["other_sections"].append({
                    "section": current_section,
                    "heading": current_heading,
                    "table": block.get("rows", []),
                })

    close_section()
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
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

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

        except Exception as error:
            errors.append({
                "file": str(relative_path),
                "error_type": type(error).__name__,
                "error": str(error),
            })
            print(f"  [ERROR] {type(error).__name__}: {error}")
            continue

        # Los prints van fuera del try que decide éxito/fallo.
        print(f"  [OK] Tableros normalizados: {count}")
        for dashboard in normalized.get("dashboards", []):
            print("     ->", dashboard.get("name"))

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

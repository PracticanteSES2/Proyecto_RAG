import json
import re
from pathlib import Path
from typing import Iterator, Union

from docx import Document
from docx.document import Document as DocumentClass
from docx.table import Table
from docx.text.paragraph import Paragraph


# ============================================================
# UTILIDADES
# ============================================================

def clean_text(text: str) -> str:
    """
    Limpia espacios innecesarios sin modificar el contenido.
    """
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def folder_to_display_name(folder_name: str) -> str:
    """
    Convierte:
    tablero_de_atenciones_institucionales

    en:
    TABLERO DE ATENCIONES INSTITUCIONALES
    """
    return folder_name.replace("_", " ").upper()


# ============================================================
# LECTURA DEL DOCX
# ============================================================

def iter_blocks(
    parent: DocumentClass
) -> Iterator[Union[Paragraph, Table]]:
    """
    Recorre párrafos y tablas respetando
    el orden original del documento.
    """

    for child in parent.element.body.iterchildren():

        if child.tag.endswith("}p"):
            yield Paragraph(child, parent)

        elif child.tag.endswith("}tbl"):
            yield Table(child, parent)


def extract_table(table: Table) -> dict:
    """
    Convierte una tabla Word en una estructura JSON.
    """

    rows = []

    for row in table.rows:

        cells = [
            clean_text(cell.text)
            for cell in row.cells
        ]

        rows.append(cells)

    return {
        "type": "table",
        "rows": rows
    }


def extract_document_blocks(file_path: Path) -> list:
    """
    Extrae párrafos y tablas de un DOCX
    manteniendo el orden original.
    """

    document = Document(file_path)

    blocks = []

    for block_index, block in enumerate(iter_blocks(document)):

        if isinstance(block, Paragraph):

            text = clean_text(block.text)

            if not text:
                continue

            blocks.append({
                "index": block_index,
                "type": "paragraph",
                "text": text,
                "style": (
                    block.style.name
                    if block.style
                    else None
                )
            })

        elif isinstance(block, Table):

            table_data = extract_table(block)
            table_data["index"] = block_index

            blocks.append(table_data)

    return blocks


# ============================================================
# DETECCIÓN DE TABLEROS
# ============================================================

def is_dashboard_heading(text: str) -> bool:
    """
    Detecta encabezados como:

    DOCUMENTACIÓN TABLERO CIRUGÍAS
    DOCUMENTACION TABLERO PENDIENTES
    DOCUMENTACIÓN – TABLERO DETALLE ESPECIALIDADES
    """

    text = clean_text(text).upper()

    pattern = (
        r"^DOCUMENTACI[ÓO]N"
        r"\s*(?:[-–—]\s*)?"
        r"TABLERO\b"
    )

    return bool(re.search(pattern, text))


def extract_dashboard_name(text: str) -> str:
    """
    Obtiene el nombre del tablero desde su encabezado.
    """

    text = clean_text(text)

    name = re.sub(
        r"^DOCUMENTACI[ÓO]N"
        r"\s*(?:[-–—]\s*)?"
        r"TABLERO\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    return clean_text(name)


def split_into_dashboards(
    blocks: list,
    file_name: str
) -> list:
    """
    Permite que un único Word contenga
    documentación de varios tableros.
    """

    dashboards = []

    current_dashboard = None

    for block in blocks:

        if block["type"] == "paragraph":

            text = block["text"]

            if is_dashboard_heading(text):

                if current_dashboard:
                    dashboards.append(current_dashboard)

                dashboard_name = extract_dashboard_name(text)

                current_dashboard = {
                    "name": dashboard_name,
                    "source_file": file_name,
                    "blocks": []
                }

                continue

        if current_dashboard is None:

            current_dashboard = {
                "name": Path(file_name).stem,
                "source_file": file_name,
                "blocks": []
            }

        current_dashboard["blocks"].append(block)

    if current_dashboard:
        dashboards.append(current_dashboard)

    return dashboards


# ============================================================
# PROCESAMIENTO INDIVIDUAL
# ============================================================

def process_document(
    file_path: Path,
    raw_dir: Path
) -> dict:
    """
    Procesa un documento y conserva información
    de su ubicación dentro de data/raw.
    """

    relative_path = file_path.relative_to(raw_dir)

    path_parts = relative_path.parts

    # Primera carpeta debajo de data/raw
    # Ej:
    # tablero_atenciones_institucionales
    semantic_model_folder = (
        path_parts[0]
        if len(path_parts) > 1
        else "sin_modelo"
    )

    semantic_model_name = folder_to_display_name(
        semantic_model_folder
    )

    # Si además existen subcarpetas:
    #
    # raw/
    #   tablero_atenciones_institucionales/
    #       cirugias/
    #           archivo.docx
    #
    # guardamos también "cirugias".
    document_group = None

    if len(path_parts) > 2:
        document_group = path_parts[1]

    blocks = extract_document_blocks(file_path)

    dashboards = split_into_dashboards(
        blocks,
        file_path.name
    )

    return {
        "source_file": file_path.name,

        "relative_path": str(relative_path),

        "source_folder": str(
            relative_path.parent
        ),

        "workspace": "Gestion Clinica",

        "semantic_model_key":
            semantic_model_folder,

        "semantic_model":
            semantic_model_name,

        "document_group":
            document_group,

        "dashboards":
            dashboards
    }


# ============================================================
# PROCESAMIENTO MASIVO Y RECURSIVO
# ============================================================

def process_all_documents(
    raw_dir: Path,
    output_dir: Path
):
    """
    Busca automáticamente todos los DOCX
    dentro de data/raw y cualquiera de sus subcarpetas.
    """

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # IMPORTANTE:
    # rglob permite encontrar archivos
    # en cualquier nivel de subcarpetas.
    documents = sorted(
        raw_dir.rglob("*.docx")
    )

    print(
        f"Documentos encontrados: "
        f"{len(documents)}"
    )

    if not documents:
        print(
            "No se encontraron documentos DOCX."
        )
        return

    total_dashboards = 0

    for document_path in documents:

        relative_path = (
            document_path.relative_to(raw_dir)
        )

        print(
            "\nProcesando:",
            relative_path
        )

        try:

            result = process_document(
                document_path,
                raw_dir
            )

            # Reproducir estructura de carpetas
            # dentro de processed.
            #
            # Ej:
            #
            # raw/modelo/cirugias/doc.docx
            #
            # pasa a:
            #
            # processed/modelo/cirugias/doc.json

            output_path = (
                output_dir
                / relative_path
            ).with_suffix(".json")

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
                    result,
                    file,
                    ensure_ascii=False,
                    indent=2
                )

            dashboard_count = len(
                result["dashboards"]
            )

            total_dashboards += (
                dashboard_count
            )

            print(
                f"  ✓ JSON generado:"
                f" {output_path}"
            )

            print(
                f"  ✓ Tableros detectados:"
                f" {dashboard_count}"
            )

            for dashboard in (
                result["dashboards"]
            ):

                print(
                    "     →",
                    dashboard["name"]
                )

        except Exception as error:

            print(
                f"  ✗ Error procesando"
                f" {relative_path}"
            )

            print(
                f"    {type(error).__name__}:"
                f" {error}"
            )

    print("\n==============================")
    print("PROCESAMIENTO FINALIZADO")
    print("==============================")

    print(
        "Documentos:",
        len(documents)
    )

    print(
        "Tableros detectados:",
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

    RAW_DIR = (
        PROJECT_ROOT
        / "data"
        / "raw"
    )

    OUTPUT_DIR = (
        PROJECT_ROOT
        / "data"
        / "processed"
    )

    process_all_documents(
        RAW_DIR,
        OUTPUT_DIR
    )
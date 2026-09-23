import re
from pathlib import Path
from typing import Iterator, Union

from docx import Document
from docx.document import Document as DocumentClass
from docx.table import Table
from docx.text.paragraph import Paragraph


def clean_text(text: str) -> str:
    """Normaliza espacios sin alterar el contenido."""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def iter_blocks(parent: DocumentClass) -> Iterator[Union[Paragraph, Table]]:
    """
    Recorre párrafos y tablas respetando el orden
    en que aparecen dentro del documento.
    """
    for child in parent.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, parent)

        elif child.tag.endswith("}tbl"):
            yield Table(child, parent)


def is_probable_heading(paragraph: Paragraph) -> bool:
    """
    Detecta títulos utilizando:
    - estilos Heading/Título
    - texto en mayúsculas
    """
    text = clean_text(paragraph.text)

    if not text:
        return False

    style_name = paragraph.style.name.lower() if paragraph.style else ""

    if "heading" in style_name or "título" in style_name or "title" in style_name:
        return True

    # Evitamos considerar SQL/DAX como encabezados
    if len(text) <= 100 and text.isupper():
        return True

    return False


def extract_table(table: Table) -> dict:
    rows = []

    for row in table.rows:
        cells = [clean_text(cell.text) for cell in row.cells]
        rows.append(cells)

    return {
        "type": "table",
        "rows": rows
    }


def extract_docx(file_path: str) -> dict:
    file_path = Path(file_path)
    document = Document(file_path)

    blocks = []

    for block in iter_blocks(document):

        if isinstance(block, Paragraph):
            text = clean_text(block.text)

            if not text:
                continue

            block_type = (
                "heading"
                if is_probable_heading(block)
                else "paragraph"
            )

            blocks.append({
                "type": block_type,
                "text": text,
                "style": block.style.name if block.style else None
            })

        elif isinstance(block, Table):
            blocks.append(extract_table(block))

    return {
        "file_name": file_path.name,
        "source_path": str(file_path),
        "blocks": blocks
    }
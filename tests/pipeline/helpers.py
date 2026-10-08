"""Utilidades comunes de las pruebas del pipeline offline (sin dependencias externas)."""
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def install_docx_stub():
    """Registra un modulo `docx` falso para poder importar document_parser."""
    if "docx" in sys.modules and getattr(sys.modules["docx"], "_is_stub", False):
        return
    try:
        import docx  # noqa: F401
        return
    except Exception:
        pass

    class _Dummy:
        def __init__(self, *args, **kwargs):
            pass

    docx = types.ModuleType("docx")
    docx._is_stub = True
    docx.Document = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("docx stub: usar tests.pipeline.docx_xml.read_blocks")
    )
    document = types.ModuleType("docx.document")
    document.Document = _Dummy
    table = types.ModuleType("docx.table")
    table.Table = _Dummy
    text = types.ModuleType("docx.text")
    paragraph = types.ModuleType("docx.text.paragraph")
    paragraph.Paragraph = _Dummy
    sys.modules.update({
        "docx": docx,
        "docx.document": document,
        "docx.table": table,
        "docx.text": text,
        "docx.text.paragraph": paragraph,
    })


def import_document_parser():
    install_docx_stub()
    from src.ingestion import document_parser
    return document_parser

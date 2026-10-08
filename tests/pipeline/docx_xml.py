"""Lector minimo de .docx via zipfile (sin python-docx) para pruebas offline.

Produce los mismos bloques que src/ingestion/document_parser.extract_document_blocks.
"""
import re
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _par_text(p):
    parts = []
    for node in p.iter():
        if node.tag == W + "t" and node.text:
            parts.append(node.text)
        elif node.tag == W + "tab":
            parts.append(" ")
        elif node.tag in (W + "br", W + "cr"):
            parts.append("\n")
    return "".join(parts)


def _clean(t):
    t = str(t or "").replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def read_blocks(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
        styles = {}
        if "word/styles.xml" in z.namelist():
            sroot = ET.fromstring(z.read("word/styles.xml"))
            for s in sroot.iter(W + "style"):
                sid = s.get(W + "styleId")
                name = s.find(W + "name")
                styles[sid] = name.get(W + "val") if name is not None else sid
    body = root.find(W + "body")
    blocks = []
    for i, child in enumerate(body):
        if child.tag == W + "p":
            text = _clean(_par_text(child))
            if not text:
                continue
            ps = child.find(W + "pPr/" + W + "pStyle")
            sid = ps.get(W + "val") if ps is not None else None
            blocks.append({
                "index": i,
                "type": "paragraph",
                "text": text,
                "style": styles.get(sid, sid) or "Normal",
            })
        elif child.tag == W + "tbl":
            rows = []
            for tr in child.iter(W + "tr"):
                cells = []
                for tc in tr.findall(W + "tc"):
                    cells.append(_clean("\n".join(_par_text(p) for p in tc.iter(W + "p"))))
                rows.append(cells)
            blocks.append({"index": i, "type": "table", "rows": rows})
    return blocks

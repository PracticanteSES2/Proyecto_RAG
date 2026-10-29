"""
Filtros de página y de visual de un tablero (PBIR en tableros/) como
argumentos DAX de CALCULATE, para armar el DAX de VERDAD de banco_real.json
siguiendo la lógica del visual del tablero.

    from tests.real import pbir
    pbir.visuals("BRIEFING HOSPITALARIO", "GESTIÓN CAMAS")       # id, tipo, campos
    pbir.filters_dax("BRIEFING HOSPITALARIO", "GESTIÓN CAMAS", "06f2271d25d40aa1e082")

Usa src/semantic/visual_filters.py para traducir cada condición; las que no
se entienden (jerarquías de fecha, medidas, TopN) se devuelven aparte en
`skipped` para revisarlas a mano.
"""
import json
from pathlib import Path

from tests.real.env import MAIN_ROOT, REPO_ROOT


def tableros_root():
    for root in (REPO_ROOT, MAIN_ROOT):
        if (root / "tableros").exists():
            return root / "tableros"
    raise FileNotFoundError("no encontré tableros/")


def definition_dir(report):
    base = tableros_root()
    for folder in base.iterdir():
        for rep in folder.glob("*.Report"):
            if rep.name[: -len(".Report")].casefold() == report.casefold() or folder.name.casefold() == report.casefold():
                return rep / "definition"
    raise FileNotFoundError(report)


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def page_dir(report, page):
    pages = definition_dir(report) / "pages"
    for p in pages.iterdir():
        if p.is_dir() and (p / "page.json").exists():
            data = _json(p / "page.json")
            if (data.get("displayName") or "").strip().casefold() == page.strip().casefold() or p.name == page:
                return p
    raise FileNotFoundError(f"{report} / {page}")


def _field_column(field):
    col = (field or {}).get("Column")
    if not isinstance(col, dict):
        return None
    entity = (((col.get("Expression") or {}).get("SourceRef") or {}).get("Entity"))
    return entity, col.get("Property")


def _filters(config):
    from src.semantic.visual_filters import UnsupportedCondition, filter_dax, parse_condition

    out, skipped = [], []
    for item in ((config or {}).get("filters") or []):
        if not item.get("filter"):
            continue
        target = _field_column(item.get("field"))
        if not target:
            skipped.append(json.dumps(item.get("field"), ensure_ascii=False)[:200])
            continue
        try:
            cond = parse_condition(item, target[1])
        except UnsupportedCondition as exc:
            skipped.append(f"{target}: {exc}")
            continue
        if cond:
            out.append(filter_dax(target[0], target[1], cond))
    return out, skipped


def _fields(visual):
    names = []
    query = ((visual.get("visual") or {}).get("query") or {}).get("queryState") or {}
    for role, body in query.items():
        for proj in (body or {}).get("projections") or []:
            names.append(f"{role}:{proj.get('queryRef')}")
    return names


def visuals(report, page):
    out = []
    for v in sorted((page_dir(report, page) / "visuals").glob("*/visual.json")):
        data = _json(v)
        fields = _fields(data)
        if fields:
            out.append({"id": v.parent.name, "type": (data.get("visual") or {}).get("visualType"), "fields": fields,
                        "filters": _filters(data.get("filterConfig"))[0]})
    return out


def filters_dax(report, page, visual_id=None, include_report=True):
    """(filtros, omitidos): filtros de informe + página (+ visual) como DAX."""
    filters, skipped = [], []
    if include_report:
        rep = definition_dir(report) / "report.json"
        if rep.exists():
            f, s = _filters(_json(rep).get("filterConfig"))
            filters += f
            skipped += s
    pdir = page_dir(report, page)
    f, s = _filters(_json(pdir / "page.json").get("filterConfig"))
    filters += f
    skipped += s
    if visual_id:
        f, s = _filters(_json(pdir / "visuals" / visual_id / "visual.json").get("filterConfig"))
        filters += f
        skipped += s
    return filters, skipped

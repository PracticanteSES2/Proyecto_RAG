"""
Completa con la documentación los informes PBIR reales que llegan INCOMPLETOS.

Varios PBIP locales traen páginas cuyo `visuals/` está vacío (carpetas sin
`visual.json`) o sin un solo visual con campos: Lavandería («Página 1»), CVC,
Perfil de morbilidad, Referencia... La documentación del propietario sí
describe los visuales de esas páginas, así que se tratan como COPIAS
INCOMPLETAS del informe publicado (decisión del coordinador, pendiente de
confirmar con el propietario; ver README):

  - El modelo sigue siendo el TMDL real (no se toca nada de lo que trae).
  - Si NINGUNA página real tiene visuales con campos, las páginas vacías se
    reemplazan por todas las páginas inferidas de la documentación
    (`infer_visuals.py`).
  - Si solo algunas páginas están vacías (informe parcial) no se completa: se
    deja registrado (status «not_completed») y se usa el informe real tal cual.
  - Las medidas que la inferencia necesite y el modelo real no tenga se
    agregan con DisplayFolder `inferred_from_documentation` (solo las que usan
    las páginas elegidas).

El informe resultante se escribe en data/pbir/<Informe>.Report (copia del real
+ páginas inferidas marcadas con "inferred") y el manifest.json del grupo se
redirige allí. Todo queda en `_metadata_sync.json` («completed_from_documentation»).
"""
import copy
import json
import shutil
from pathlib import Path

from tools.local_data.documented_values import DocumentedValues
from tools.local_data.infer_visuals import ORIGIN, _visual_id, infer_documented_report
from tools.local_data.metadata_format import normalize_text

COMPLETION_REASON = (
    "El PBIR local trae páginas sin visuales con campos: se considera copia incompleta "
    "del informe publicado (la documentación sí describe sus visuales). Pregunta abierta "
    "al propietario (tools/local_data/README.md)."
)


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _page_key(name):
    return " ".join(normalize_text(name).split())


def _data_visuals(page_dir):
    """Visuales de la página con al menos un campo en su consulta."""
    count = 0
    for visual_json in sorted((page_dir / "visuals").glob("*/visual.json")):
        try:
            visual = (_read_json(visual_json).get("visual") or {})
        except (OSError, ValueError):
            continue
        state = (visual.get("query") or {}).get("queryState") or {}
        if any(role.get("projections") for role in state.values() if isinstance(role, dict)):
            count += 1
    return count


def report_page_status(report_path):
    """[{folder, display_name, data_visuals}] de un informe PBIR."""
    pages_dir = Path(report_path) / "definition" / "pages"
    pages = []
    if not pages_dir.is_dir():
        return pages
    for page_dir in sorted(path for path in pages_dir.iterdir() if path.is_dir()):
        page_json = page_dir / "page.json"
        if not page_json.exists():
            continue
        data = _read_json(page_json)
        pages.append({
            "folder": page_dir.name,
            "display_name": str(data.get("displayName") or page_dir.name),
            "data_visuals": _data_visuals(page_dir),
        })
    return pages


def empty_pages(status):
    return [page for page in status if page["data_visuals"] == 0]


def has_useful_pages(status):
    return any(page["data_visuals"] > 0 for page in status)


def select_inferred_pages(status, inferred_pages):
    """
    Páginas inferidas que completan el informe real. Solo se completa un
    informe SIN NINGUNA página útil (todas las páginas inferidas). En un
    informe parcial (Atenciones, Tiempos de urgencias, Farmacia) la inferencia
    sobre un modelo real con decenas de tablas empareja indicadores con medidas
    de otras tablas («triages del año actual» -> Triages_Año_Anterior): no se
    completa y queda registrado como pregunta abierta.
    Devuelve (páginas elegidas, {página inferida: página real reemplazada}).
    """
    if has_useful_pages(status):
        return [], {}
    empties = {_page_key(page["display_name"]): page["display_name"] for page in empty_pages(status)}
    replaced = {page["name"]: empties[_page_key(page["name"])]
                for page in inferred_pages if _page_key(page["name"]) in empties}
    return list(inferred_pages), replaced


def _referenced_measures(pages):
    names = set()
    for page in pages:
        for visual in page["visuals"]:
            for field in visual["fields"]:
                node = field["field"].get("Measure")
                if node:
                    names.add((node["Expression"]["SourceRef"]["Entity"], node["Property"]))
    return names


def infer_completion(model, documents, status):
    """
    Corre la inferencia de visuales sobre una COPIA del modelo real y devuelve
    {"pages", "replaced", "added_measures"} sin modificar `model`.
    Todas las columnas reales cuentan como esquema conocido: no se agregan columnas.
    """
    working = copy.deepcopy(model)
    origins = {
        (table["name"], column["name"]): "tmdl"
        for table in working["tables"] for column in table["columns"]
    }
    values = DocumentedValues().ingest_documents(documents).ingest_model(working)
    inference = infer_documented_report(
        working, documents, origins=origins,
        documented_values=values.by_table_column(working),
    )
    pages, replaced = select_inferred_pages(status, inference.pages)
    used = _referenced_measures(pages)
    added = [item for item in inference.added_measures if (item["table"], item["measure"]) in used]
    measures = []
    for item in added:
        table = next(t for t in working["tables"] if t["name"] == item["table"])
        measures.append((item["table"], next(m for m in table["measures"] if m["name"] == item["measure"])))
    return {
        "pages": pages,
        "replaced": replaced,
        "added_measures": added,
        "measure_objects": measures,
        "added_columns": inference.added_columns,
    }


def apply_added_measures(model, completion):
    """Agrega al modelo real las medidas inferidas que usan las páginas elegidas."""
    for table_name, measure in completion["measure_objects"]:
        table = next(t for t in model["tables"] if t["name"] == table_name)
        if not any(m["name"].casefold() == measure["name"].casefold() for m in table["measures"]):
            table["measures"].append(copy.deepcopy(measure))


def write_completed_report(real_report, pages, status, report_root, *, semantic_model=None):
    """
    data/pbir/<Informe>.Report: copia del PBIR real sin sus páginas vacías + las
    páginas inferidas (marcadas "inferred"). Devuelve la carpeta escrita.
    """
    real_report = Path(real_report)
    target = Path(report_root) / real_report.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(real_report, target, ignore=shutil.ignore_patterns(".pbi", "*.abf"))

    pages_dir = target / "definition" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    order_file = pages_dir / "pages.json"
    order = _read_json(order_file) if order_file.exists() else {}
    page_order = [name for name in order.get("pageOrder", []) or []]

    for page in empty_pages(status):
        shutil.rmtree(pages_dir / page["folder"], ignore_errors=True)
        if page["folder"] in page_order:
            page_order.remove(page["folder"])

    report_name = real_report.name[: -len(".Report")]
    marker = {"origin": ORIGIN, "semantic_model": semantic_model,
              "note": "Página reconstruida de la documentación: el PBIR local la trae sin visuales."}
    for page in pages:
        page_name = f"ReportSection{_visual_id(report_name, page['name'])}"
        page_dir = pages_dir / page_name
        (page_dir / "visuals").mkdir(parents=True, exist_ok=True)
        _write_json(page_dir / "page.json", {"name": page_name, "displayName": page["name"], "inferred": marker})
        page_order.append(page_name)
        for index, item in enumerate(page["visuals"], 1):
            visual_name = _visual_id(report_name, page["name"], index, item["visual_type"], item["title"])
            roles = {}
            for field in item["fields"]:
                roles.setdefault(field["role"], {"projections": []})["projections"].append({
                    "field": field["field"], "queryRef": field["queryRef"],
                    "nativeQueryRef": field["nativeQueryRef"],
                })
            visual = {"visualType": item["visual_type"], "query": {"queryState": roles}}
            if item["title"]:
                visual["visualContainerObjects"] = {"title": [{"properties": {
                    "text": {"expr": {"Literal": {"Value": "'" + item["title"].replace("'", "''") + "'"}}},
                }}]}
            visual_dir = page_dir / "visuals" / visual_name
            visual_dir.mkdir(parents=True, exist_ok=True)
            _write_json(visual_dir / "visual.json", {
                "name": visual_name, "visual": visual,
                "inferred": dict(marker, documented_as=item["source"]),
            })

    order["pageOrder"] = page_order
    if order.get("activePageName") not in page_order:
        order["activePageName"] = page_order[0] if page_order else None
    _write_json(order_file, order)
    _write_json(target / "definition" / "_completed_from_documentation.json", {
        "origin": ORIGIN, "semantic_model": semantic_model, "real_report": str(real_report),
        "reason": COMPLETION_REASON,
        "removed_empty_pages": [page["display_name"] for page in empty_pages(status)],
        "inferred_pages": [page["name"] for page in pages],
    })
    return target


def redirect_manifests(raw_dir, semantic_model_key, report_dir, owner_root):
    """manifest.json de los grupos del modelo -> pbir_path relativo a la raíz del pipeline."""
    relative = Path(report_dir).resolve().relative_to(Path(owner_root).resolve()).as_posix()
    changed = []
    for path in sorted(Path(raw_dir).glob("*/manifest.json")):
        manifest = _read_json(path)
        if manifest.get("semantic_model_key") != semantic_model_key:
            continue
        manifest["pbir_path_original"] = manifest.get("pbir_path")
        manifest["pbir_path"] = relative
        _write_json(path, manifest)
        changed.append(path.parent.name)
    return changed

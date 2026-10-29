"""
Sincroniza los enlaces a los informes de Power BI («Abrir en Power BI»).

SOLO LECTURA: únicamente hace peticiones GET a la API REST de Power BI
(https://api.powerbi.com/v1.0/myorg/...): el workspace, sus modelos
semánticos (datasets), sus informes y las páginas de cada informe. Nunca crea,
modifica ni borra nada en Power BI.

  1. Toma el workspace del endpoint XMLA configurado (POWERBI_XMLA_ENDPOINT;
     si no está, el de data/catalog/model_registry.json).
  2. Lista los informes (id, nombre, webUrl, datasetId) y sus páginas
     (name = id interno, displayName).
  3. Empareja cada informe con su modelo semántico por datasetId y, si no
     coincide, por nombre normalizado.
  4. Guarda data/catalog/report_links.json:
       modelo semántico -> informe(s) -> páginas, con la URL
       https://app.powerbi.com/groups/<ws>/reports/<reportId>/<pageName>

Los modelos sin informe propio (p. ej. «Dashboard Gestion») quedan en
`unlinked_models`, sin enlace. Es idempotente: si nada cambió no reescribe el
archivo (la fecha solo cambia cuando cambia el contenido).

Requiere una sesión en caché (python -m src.providers.powerbi_token login).

Ejemplos:
  python sync_powerbi_links.py
  python sync_powerbi_links.py --dry-run          # no escribe el archivo
  python sync_powerbi_links.py --output otra/ruta.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
API_ROOT = "https://api.powerbi.com/v1.0/myorg"
APP_ROOT = "https://app.powerbi.com"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "catalog" / "report_links.json"
MODEL_REGISTRY = PROJECT_ROOT / "data" / "catalog" / "model_registry.json"
SCHEMA_VERSION = 1


class SyncError(RuntimeError):
    pass


def _normalize(text) -> str:
    # Misma normalización que src/providers/powerbi_links (sin importarlo
    # para que el script funcione aunque falle la importación de src).
    from src.providers.powerbi_links import normalizar

    return normalizar(text)


# ----------------------------------------------------------------------------
# Acceso de solo lectura
# ----------------------------------------------------------------------------

class ReadOnlyPowerBIClient:
    """Cliente mínimo de la API REST: SOLO GET (no expone otro verbo)."""

    def __init__(self, token: str, timeout: float = 60.0):
        self._token = token
        self._timeout = timeout

    def get(self, path: str, params: dict | None = None) -> dict:
        if not path.startswith("/"):
            raise ValueError("La ruta debe empezar por «/».")
        url = API_ROOT + path
        if params:
            url += "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
        )
        assert request.get_method() == "GET"
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            raise SyncError(f"GET {path} -> HTTP {error.code} {error.reason}") from None
        except urllib.error.URLError as error:
            raise SyncError(f"GET {path} -> {error.reason}") from None


def workspace_name_from_endpoint(endpoint: str) -> str | None:
    """powerbi://api.powerbi.com/v1.0/myorg/Gestion%20Clinica -> «Gestion Clinica»."""
    endpoint = (endpoint or "").strip().rstrip("/")
    if not endpoint:
        return None
    marker = "/myorg/"
    if marker in endpoint:
        name = endpoint.split(marker, 1)[1]
    else:
        name = endpoint.rsplit("/", 1)[-1]
    name = urllib.parse.unquote(name.split("?", 1)[0]).strip()
    return name or None


def configured_workspace_name(registry: dict) -> str | None:
    try:
        from dotenv import load_dotenv

        # Solo el .env de este checkout (sin buscar en carpetas superiores).
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass
    name = workspace_name_from_endpoint(os.getenv("POWERBI_XMLA_ENDPOINT", ""))
    if name:
        return name
    workspace = (registry or {}).get("workspace") or {}
    return workspace_name_from_endpoint(workspace.get("xmla_endpoint", "")) or workspace.get("name")


def load_registry_models(path: Path) -> list[str]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [m["semantic_model"] for m in data.get("models") or [] if m.get("semantic_model")]


# ----------------------------------------------------------------------------
# Construcción del catálogo (sin red: probado en tests/links)
# ----------------------------------------------------------------------------

def page_url(workspace_id: str, report_id: str, page_name: str | None = None) -> str:
    url = f"{APP_ROOT}/groups/{workspace_id}/reports/{report_id}"
    return f"{url}/{page_name}" if page_name else url


def build_links(workspace: dict, datasets: list[dict], reports: list[dict],
                pages_by_report: dict[str, list[dict]], registry_models: list[str]) -> dict:
    ws_id = workspace["id"]
    dataset_names = {d.get("id"): d.get("name") for d in datasets if d.get("id")}
    # Con registro, solo sus modelos (deja fuera «Report Usage Metrics Model»
    # y otros modelos del sistema); sin registro, todos los del workspace.
    model_by_norm = {}
    for name in (registry_models or list(dataset_names.values())):
        if name and _normalize(name) not in model_by_norm:
            model_by_norm[_normalize(name)] = name

    models: dict[str, dict] = {}
    unmatched_reports = []
    for report in sorted(reports, key=lambda r: (str(r.get("name")), str(r.get("id")))):
        report_id = report.get("id")
        if not report_id:
            continue
        dataset_name = dataset_names.get(report.get("datasetId"))
        model, match = None, None
        if dataset_name and _normalize(dataset_name) in model_by_norm:
            model, match = model_by_norm[_normalize(dataset_name)], "datasetId"
        elif _normalize(report.get("name")) in model_by_norm:
            model, match = model_by_norm[_normalize(report.get("name"))], "nombre"
        if not model:
            paginated = report.get("reportType") == "PaginatedReport"
            unmatched_reports.append({
                "id": report_id, "name": report.get("name"),
                "dataset_id": report.get("datasetId"),
                "report_type": report.get("reportType"),
                "reason": "informe paginado (sin modelo semántico propio)" if paginated
                else "su modelo semántico no está en el registro ni coincide por nombre",
            })
            continue
        pages = sorted(
            pages_by_report.get(report_id) or [],
            key=lambda p: (p.get("order") if isinstance(p.get("order"), int) else 10**6,
                           str(p.get("displayName"))),
        )
        entry = models.setdefault(model, {
            "semantic_model": model,
            "dataset_id": next((i for i, n in dataset_names.items() if n == model), None),
            "reports": [],
        })
        entry["reports"].append({
            "id": report_id,
            "name": report.get("name"),
            "dataset_id": report.get("datasetId"),
            "match": match,
            "web_url": report.get("webUrl"),
            "url": page_url(ws_id, report_id),
            "pages": [
                {
                    "name": p.get("name"),
                    "display_name": p.get("displayName"),
                    "order": p.get("order"),
                    "url": page_url(ws_id, report_id, p.get("name")),
                }
                for p in pages if p.get("name")
            ],
        })

    for entry in models.values():
        # Primero el informe que se llama como el modelo.
        entry["reports"].sort(key=lambda r: (_normalize(r["name"]) != _normalize(entry["semantic_model"]),
                                             str(r["name"]), r["id"]))

    unlinked = sorted({m for m in registry_models if m not in models})
    return {
        "version": SCHEMA_VERSION,
        "generated_at": None,
        "workspace": {"id": ws_id, "name": workspace.get("name")},
        "models": dict(sorted(models.items(), key=lambda kv: _normalize(kv[0]))),
        "unlinked_models": unlinked,
        "unmatched_reports": unmatched_reports,
        "summary": {
            "models_with_link": len(models),
            "reports": sum(len(m["reports"]) for m in models.values()),
            "pages": sum(len(r["pages"]) for m in models.values() for r in m["reports"]),
            "unlinked_models": len(unlinked),
        },
    }


def write_if_changed(data: dict, output: Path) -> bool:
    """Escribe solo si cambió algo más que la fecha. Devuelve True si escribió."""
    if output.exists():
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
            if {**previous, "generated_at": None} == {**data, "generated_at": None}:
                return False
        except (ValueError, OSError):
            pass
    data = {**data, "generated_at": datetime.now(timezone.utc).isoformat()}
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, output)
    return True


# ----------------------------------------------------------------------------
# Ejecución
# ----------------------------------------------------------------------------

def fetch(client: ReadOnlyPowerBIClient, workspace_name: str):
    escaped = workspace_name.replace("'", "''")
    groups = client.get("/groups", {"$filter": f"name eq '{escaped}'"}).get("value") or []
    workspace = next((g for g in groups if g.get("name") == workspace_name), None) or (groups[0] if groups else None)
    if not workspace:
        raise SyncError(f"No se encontró el workspace «{workspace_name}» con la cuenta en caché.")
    ws = workspace["id"]
    datasets = client.get(f"/groups/{ws}/datasets").get("value") or []
    reports = client.get(f"/groups/{ws}/reports").get("value") or []
    pages, errors = {}, []
    for report in reports:
        if report.get("reportType") == "PaginatedReport":
            # Los informes paginados (RDL) no tienen páginas en la API.
            pages[report["id"]] = []
            continue
        try:
            pages[report["id"]] = client.get(f"/groups/{ws}/reports/{report['id']}/pages").get("value") or []
        except SyncError as error:
            # Informes paginados (RDL) u otros sin páginas: enlace al informe.
            pages[report["id"]] = []
            errors.append(f"{report.get('name')}: {error}")
    return workspace, datasets, reports, pages, errors


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Enlaces «Abrir en Power BI» (solo lectura, GET).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--registry", type=Path, default=MODEL_REGISTRY,
                        help="model_registry.json con los modelos semánticos conocidos.")
    parser.add_argument("--dry-run", action="store_true", help="No escribe el archivo.")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(PROJECT_ROOT))
    registry = json.loads(args.registry.read_text(encoding="utf-8")) if args.registry.exists() else {}
    workspace_name = configured_workspace_name(registry)
    if not workspace_name:
        print("ERROR: no hay workspace configurado (POWERBI_XMLA_ENDPOINT).")
        return 2

    from src.providers.powerbi_token import TokenNoDisponible, obtener_token

    try:
        client = ReadOnlyPowerBIClient(obtener_token())
        workspace, datasets, reports, pages, errors = fetch(client, workspace_name)
    except (TokenNoDisponible, SyncError) as error:
        print(f"ERROR: {error}")
        return 1

    data = build_links(workspace, datasets, reports, pages, load_registry_models(args.registry))
    summary = data["summary"]
    print(f"Workspace: {workspace.get('name')} · {len(reports)} informes · {len(datasets)} modelos")
    print(f"Modelos con enlace: {summary['models_with_link']} · páginas: {summary['pages']}")
    if data["unlinked_models"]:
        print("Sin informe propio: " + ", ".join(data["unlinked_models"]))
    for item in data["unmatched_reports"]:
        print(f"Informe sin modelo emparejado: {str(item['name']).strip()} ({item['reason']})")
    for line in errors:
        print(f"Aviso: {line}")
    if args.dry_run:
        print("--dry-run: no se escribió el archivo.")
    elif write_if_changed(data, args.output):
        print(f"Guardado: {args.output}")
    else:
        print(f"Sin cambios: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

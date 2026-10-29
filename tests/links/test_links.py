"""
Enlaces «Abrir en Power BI» (offline, sin red ni Power BI).

Ejecutar:  python -m tests.links.test_links

El catálogo sintético se arma con sync_powerbi_links.build_links a partir de
respuestas falsas de la API REST (las mismas formas que devuelve
GET /groups/{ws}/datasets, /reports y /reports/{id}/pages), así se prueban a la
vez el sincronizador y src/providers/powerbi_links.py.

Casos: normalización (mayúsculas, tildes, «_», espacios), página por nombre
visible o por id interno, caída al informe, modelo sin informe (sin enlace),
página única en el catálogo, filtros por URL, resultados del motor (ruta
powerbi, rag y contrapreguntas), idempotencia y cliente de solo lectura.
"""
import json
import sys
import tempfile
import urllib.parse
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sync_powerbi_links as sync  # noqa: E402
from src.providers import powerbi_links as L  # noqa: E402

WS = "ws-0001"

DATASETS = [
    {"id": "ds-briefing", "name": "BRIEFING HOSPITALARIO"},
    {"id": "ds-farmacia", "name": "TABLERO_FARMACIA"},
    {"id": "ds-gestion", "name": "Dashboard Gestion"},
    {"id": "ds-atenciones", "name": "TABLERO DE ATENCIONES INSTITUCIONALES"},
    {"id": "ds-usage", "name": "Report Usage Metrics Model"},
]

REPORTS = [
    {"id": "r-briefing", "name": "BRIEFING HOSPITALARIO", "datasetId": "ds-briefing",
     "webUrl": f"https://app.powerbi.com/groups/{WS}/reports/r-briefing", "reportType": "PowerBIReport"},
    # Segundo informe del mismo modelo: se ordena detrás del que se llama como el modelo.
    {"id": "r-briefing-2", "name": "BRIEFING (copia)", "datasetId": "ds-briefing",
     "webUrl": "x", "reportType": "PowerBIReport"},
    # Emparejado por nombre: su datasetId no está en el workspace.
    {"id": "r-farmacia", "name": "Tablero Farmacia", "datasetId": "ds-otro-ws",
     "webUrl": "x", "reportType": "PowerBIReport"},
    {"id": "r-atenciones", "name": "TABLERO DE ATENCIONES INSTITUCIONALES", "datasetId": "ds-atenciones",
     "webUrl": "x", "reportType": "PowerBIReport"},
    {"id": "r-usage", "name": "Report Usage Metrics Report", "datasetId": "ds-usage",
     "webUrl": "x", "reportType": "PowerBIReport"},
    {"id": "r-paginado", "name": "TRIAGES INSTITUCIONALES", "webUrl": "x", "reportType": "PaginatedReport"},
]

PAGES = {
    "r-briefing": [
        {"name": "ReportSection1a2b", "displayName": "INICIO", "order": 0},
        {"name": "ReportSection3c4d", "displayName": "Ocupación por servicio", "order": 1},
    ],
    "r-briefing-2": [{"name": "ReportSection9999", "displayName": "DETALLE COPIA", "order": 0}],
    "r-farmacia": [{"name": "abc123", "displayName": "CONSUMO_MEDICAMENTOS", "order": 0}],
    "r-atenciones": [
        {"name": "p-triage", "displayName": "TRIAGE", "order": 0},
        {"name": "p-cx", "displayName": "CIRUGÍAS", "order": 1},
    ],
}

REGISTRY = [
    "BRIEFING HOSPITALARIO", "TABLERO_FARMACIA", "TABLERO DE ATENCIONES INSTITUCIONALES",
    "Dashboard Gestion", "TABLERO CVC",
]


def links():
    return sync.build_links({"id": WS, "name": "Gestion Clinica"}, DATASETS, REPORTS, PAGES, REGISTRY)


# ---------------------------------------------------------------------------
# Sincronizador (sin red)
# ---------------------------------------------------------------------------

def test_builder_pairs_reports_by_dataset_and_by_name():
    data = links()
    models = data["models"]
    assert set(models) == {"BRIEFING HOSPITALARIO", "TABLERO_FARMACIA", "TABLERO DE ATENCIONES INSTITUCIONALES"}
    briefing = models["BRIEFING HOSPITALARIO"]["reports"]
    assert [r["id"] for r in briefing] == ["r-briefing", "r-briefing-2"]
    assert briefing[0]["match"] == "datasetId"
    assert models["TABLERO_FARMACIA"]["reports"][0]["match"] == "nombre"
    page = briefing[0]["pages"][0]
    assert page["url"] == f"https://app.powerbi.com/groups/{WS}/reports/r-briefing/ReportSection1a2b"
    assert briefing[0]["url"] == f"https://app.powerbi.com/groups/{WS}/reports/r-briefing"


def test_builder_lists_models_without_report_and_unmatched_reports():
    data = links()
    assert data["unlinked_models"] == ["Dashboard Gestion", "TABLERO CVC"]
    reasons = {r["name"]: r["reason"] for r in data["unmatched_reports"]}
    assert "paginado" in reasons["TRIAGES INSTITUCIONALES"]
    # Modelo del sistema fuera del registro: no se enlaza.
    assert "Report Usage Metrics Report" in reasons
    assert data["summary"]["models_with_link"] == 3
    assert data["summary"]["pages"] == 6


def test_write_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "catalog" / "report_links.json"
        assert sync.write_if_changed(links(), out) is True
        first = out.read_text(encoding="utf-8")
        assert sync.write_if_changed(links(), out) is False
        assert out.read_text(encoding="utf-8") == first
        changed = links()
        changed["models"]["TABLERO_FARMACIA"]["reports"][0]["pages"][0]["display_name"] = "OTRA"
        assert sync.write_if_changed(changed, out) is True


def test_workspace_from_xmla_endpoint():
    f = sync.workspace_name_from_endpoint
    assert f("powerbi://api.powerbi.com/v1.0/myorg/Gestion%20Clinica") == "Gestion Clinica"
    assert f("powerbi://api.powerbi.com/v1.0/myorg/Gestion Clinica/") == "Gestion Clinica"
    assert f("") is None


def test_client_is_read_only():
    client = sync.ReadOnlyPowerBIClient("token")
    public = {name for name in dir(client) if not name.startswith("_")}
    assert public == {"get"}, public
    source = Path(sync.__file__).read_text(encoding="utf-8")
    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        assert f'method="{verb}"' not in source and f"'{verb}'" not in source, verb


class FakeClient:
    """Respuestas REST simuladas; registra cada GET."""

    def __init__(self):
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path == "/groups":
            return {"value": [{"id": WS, "name": "Gestion Clinica"}]}
        if path == f"/groups/{WS}/datasets":
            return {"value": DATASETS}
        if path == f"/groups/{WS}/reports":
            return {"value": REPORTS}
        rid = path.rsplit("/", 2)[-2]
        if rid == "r-usage":
            raise sync.SyncError("HTTP 400")
        return {"value": PAGES.get(rid, [])}


def test_fetch_with_mocked_rest_api():
    client = FakeClient()
    workspace, datasets, reports, pages, errors = sync.fetch(client, "Gestion Clinica")
    assert workspace["id"] == WS and len(reports) == len(REPORTS)
    assert client.calls[0] == ("/groups", {"$filter": "name eq 'Gestion Clinica'"})
    # El informe paginado no se consulta; un error de páginas avisa y sigue.
    assert not any("r-paginado" in path for path, _ in client.calls)
    assert pages["r-usage"] == [] and errors and "Report Usage" in errors[0]
    data = sync.build_links(workspace, datasets, reports, pages, REGISTRY)
    assert data["summary"]["models_with_link"] == 3


def test_update_rag_has_optional_links_step():
    source = (ROOT / "update_rag.py").read_text(encoding="utf-8")
    assert "--skip-links" in source and "sync_powerbi_links.py" in source
    assert "optional=True" in source


# ---------------------------------------------------------------------------
# enlace_para
# ---------------------------------------------------------------------------

def test_normalization():
    assert L.normalizar("Ocupación_por  servicio") == "OCUPACION POR SERVICIO"
    assert L.normalizar("tablero-farmacia") == "TABLERO FARMACIA"


def test_page_level_with_tolerant_names():
    data = links()
    link = L.enlace_para("briefing hospitalario", page="inicio", links=data)
    assert link["nivel"] == "pagina"
    assert link["etiqueta"] == "Abrir BRIEFING HOSPITALARIO › INICIO"
    assert link["url"].endswith("/reports/r-briefing/ReportSection1a2b")
    # Tildes, mayúsculas y espacios.
    link = L.enlace_para("BRIEFING_HOSPITALARIO", "Briefing Hospitalario", "OCUPACION  POR SERVICIO", links=data)
    assert link["nivel"] == "pagina" and link["pagina"] == "Ocupación por servicio"
    # Modelo con «_» y página con «_».
    link = L.enlace_para("Tablero Farmacia", page="consumo medicamentos", links=data)
    assert link["nivel"] == "pagina" and link["url"].endswith("/r-farmacia/abc123")


def test_page_by_internal_id():
    link = L.enlace_para("BRIEFING HOSPITALARIO", page="ReportSection3c4d", links=links())
    assert link["nivel"] == "pagina" and link["pagina"] == "Ocupación por servicio"


def test_page_in_secondary_report():
    link = L.enlace_para("BRIEFING HOSPITALARIO", page="detalle copia", links=links())
    assert link["informe"] == "BRIEFING (copia)" and link["nivel"] == "pagina"


def test_report_and_page_in_one_field():
    link = L.enlace_para("BRIEFING HOSPITALARIO", page="BRIEFING HOSPITALARIO › INICIO", links=links())
    assert link["nivel"] == "pagina" and link["pagina"] == "INICIO"


def test_falls_back_to_report_when_page_is_unknown():
    link = L.enlace_para("BRIEFING HOSPITALARIO", page="PÁGINA QUE NO EXISTE", links=links())
    assert link["nivel"] == "informe"
    assert link["etiqueta"] == "Abrir BRIEFING HOSPITALARIO"
    assert link["url"] == f"https://app.powerbi.com/groups/{WS}/reports/r-briefing"
    assert L.enlace_para("BRIEFING HOSPITALARIO", links=links())["nivel"] == "informe"


def test_no_link_without_report():
    data = links()
    assert L.enlace_para("Dashboard Gestion", page="INICIO", links=data) is None
    assert L.enlace_para("MODELO DESCONOCIDO", links=data) is None
    assert L.enlace_para(None, links=data) is None
    assert L.enlace_para("BRIEFING HOSPITALARIO", links={}) is None
    # Sin archivo: None (no falla).
    assert L.cargar_enlaces(Path(tempfile.gettempdir()) / "no-existe-report_links.json") is None


def test_report_name_without_model_and_unique_page():
    data = links()
    link = L.enlace_para(None, report="tablero de atenciones institucionales", links=data)
    assert link["nivel"] == "informe" and link["modelo"] == "TABLERO DE ATENCIONES INSTITUCIONALES"
    link = L.enlace_para(None, page="Cirugias", links=data)
    assert link["nivel"] == "pagina" and link["url"].endswith("/r-atenciones/p-cx")


def test_loads_from_env_path():
    import os

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report_links.json"
        path.write_text(json.dumps(links()), encoding="utf-8")
        previous = os.environ.get("POWERBI_LINKS_PATH")
        os.environ["POWERBI_LINKS_PATH"] = str(path)
        try:
            assert L.enlace_para("BRIEFING HOSPITALARIO", page="INICIO")["nivel"] == "pagina"
        finally:
            if previous is None:
                os.environ.pop("POWERBI_LINKS_PATH", None)
            else:
                os.environ["POWERBI_LINKS_PATH"] = previous


# ---------------------------------------------------------------------------
# Filtros por URL
# ---------------------------------------------------------------------------

def _filter_of(url):
    return urllib.parse.unquote(url.split("?filter=", 1)[1])


def test_url_filters_simple_and_escaped():
    base = L.enlace_para("BRIEFING HOSPITALARIO", page="INICIO", links=links())
    link = L.con_filtros(base, [
        {"type": "categorical", "table": "Calendario", "column": "AÑO", "operator": "=", "value": 2024},
        {"type": "categorical", "table": "SERVICIOS", "column": "NOMBRE SERVICIO", "operator": "in",
         "values": ["UCI ADULTOS", "O'HIGGINS"]},
    ])
    assert link["filtrado"] is True
    assert link["url"].startswith(base["url"] + "?filter=")
    assert " " not in link["url"]
    assert _filter_of(link["url"]) == (
        "Calendario/A_x00D1_O eq 2024 and "
        "SERVICIOS/NOMBRE_x0020_SERVICIO in ('UCI ADULTOS','O''HIGGINS')"
    )


def test_url_filters_skip_complex_ones():
    base = L.enlace_para("BRIEFING HOSPITALARIO", page="INICIO", links=links())
    skipped = [
        {"type": "date_range", "table": "Calendario", "column": "Fecha", "operator": "between"},
        {"type": "categorical", "table": "T", "column": "C", "operator": ">", "value": 3},
        {"type": "categorical", "table": "T", "column": "C", "operator": "=", "value": None},
        {"type": "categorical", "table": "T", "column": "C", "operator": "in", "values": list(range(20))},
        {"type": "categorical", "column": "C", "operator": "=", "value": "X"},
    ]
    assert L.con_filtros(base, skipped) == base
    assert L.con_filtros(None, skipped) is None


# ---------------------------------------------------------------------------
# A partir de resultados del motor
# ---------------------------------------------------------------------------

def test_result_powerbi_success_with_filters():
    result = {
        "status": "success", "route": "powerbi", "semantic_model": "BRIEFING HOSPITALARIO",
        "report": "BRIEFING HOSPITALARIO", "dashboard": "Ocupacion por servicio",
        "filters": [{"type": "categorical", "table": "Calendario", "column": "AÑO", "operator": "=", "value": 2025}],
    }
    link = L.enlace_para_resultado(result, links=links())
    assert link["nivel"] == "pagina" and link["filtrado"]
    assert "Calendario/A_x00D1_O eq 2025" in _filter_of(link["url"])


def test_result_without_link():
    data = links()
    assert L.enlace_para_resultado({"status": "success", "route": "powerbi",
                                    "semantic_model": "Dashboard Gestion"}, links=data) is None
    assert L.enlace_para_resultado({"status": "powerbi_error", "route": "powerbi",
                                    "semantic_model": "BRIEFING HOSPITALARIO"}, links=data) is None
    assert L.enlace_para_resultado({"status": "not_found", "route": "out_of_scope"}, links=data) is None
    # RAG sin tablero concreto: fuentes de varios modelos.
    rag = {"status": "success", "route": "rag", "dashboard": None, "sources": [
        {"semantic_model": "BRIEFING HOSPITALARIO", "dashboard": "INICIO"},
        {"semantic_model": "TABLERO_FARMACIA", "dashboard": "CONSUMO_MEDICAMENTOS"},
    ]}
    assert L.enlace_para_resultado(rag, links=data) is None
    assert L.enlace_para_resultado(None, links=data) is None


def test_result_rag_citing_page_or_report():
    data = links()
    rag = {"status": "success", "route": "rag", "dashboard": "TRIAGE", "sources": [
        {"semantic_model": "TABLERO DE ATENCIONES INSTITUCIONALES", "dashboard": "TRIAGE"},
        {"semantic_model": "TABLERO DE ATENCIONES INSTITUCIONALES", "dashboard": "CIRUGÍAS"},
    ]}
    link = L.enlace_para_resultado(rag, links=data)
    assert link["nivel"] == "pagina" and link["url"].endswith("/p-triage")
    # «dashboard» con el nombre del informe (así lo trae la ruta RAG).
    rag["dashboard"] = "Tablero de Atenciones Institucionales"
    assert L.enlace_para_resultado(rag, links=data)["nivel"] == "informe"
    # Sin tablero detectado pero todas las fuentes de una misma página.
    rag = {"status": "success", "route": "rag", "sources": [
        {"semantic_model": "BRIEFING HOSPITALARIO", "dashboard": "INICIO"},
        {"semantic_model": "BRIEFING HOSPITALARIO", "dashboard": "Inicio"},
    ]}
    assert L.enlace_para_resultado(rag, links=data)["nivel"] == "pagina"


def test_clarification_option_from_detail():
    data = links()
    option = {"id": "m1", "label": "Ocupación",
              "detail": "BRIEFING HOSPITALARIO › Ocupación por servicio · BRIEFING HOSPITALARIO"}
    link = L.enlace_para_opcion(option, links=data)
    assert link["nivel"] == "pagina" and link["url"].endswith("/ReportSection3c4d")
    assert L.enlace_para_opcion({"id": "m2", "detail": "TABLERO FARMACIA"}, links=data)["nivel"] == "informe"
    assert L.enlace_para_opcion({"id": "none", "label": "Ninguna"}, links=data) is None
    assert L.enlace_para_opcion({"id": "m3", "detail": "X › Y · Dashboard Gestion"}, links=data) is None
    structured = {"id": "m4", "semantic_model": "TABLERO_FARMACIA", "page": "CONSUMO MEDICAMENTOS"}
    assert L.enlace_para_opcion(structured, links=data)["nivel"] == "pagina"


def _run_all():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, func in tests:
        try:
            func()
            print("PASS ", name)
        except Exception as error:  # noqa: BLE001
            failed += 1
            print("FAIL ", name, "->", type(error).__name__, error)
    print(f"{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())

"""
Enlaces «Abrir en Power BI» con el motor REAL y dependencias falsas
(tests/sim: Power BI y LLM simulados) más un report_links.json sintético con
los informes del fixture. Comprueba que los campos que ya trae el resultado
del motor (modelo, informe, página; detalle de cada opción) bastan.

Además, si existe el catálogo real (data/catalog/report_links.json o
POWERBI_LINKS_PATH), verifica que los 15 tableros documentados tienen enlace.

Ejecutar:  python -m tests.links.test_links_e2e
"""
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.providers import powerbi_links as L  # noqa: E402

WS = "ws-sim"


def _report(rid, name, pages):
    return {
        "id": rid, "name": name, "url": f"https://app.powerbi.com/groups/{WS}/reports/{rid}",
        "pages": [
            {"name": pid, "display_name": label,
             "url": f"https://app.powerbi.com/groups/{WS}/reports/{rid}/{pid}"}
            for pid, label in pages
        ],
    }


SIM_LINKS = {
    "version": 1,
    "workspace": {"id": WS, "name": "Sim"},
    "models": {
        "Gestion Quirurgica": {"semantic_model": "Gestion Quirurgica", "reports": [
            _report("r-qx", "Tablero Quirurgico", [("p-cxr", "CIRUGÍAS REALIZADAS")]),
        ]},
        "Atenciones Institucionales": {"semantic_model": "Atenciones Institucionales", "reports": [
            _report("r-at", "Tablero de Atenciones Institucionales", [("p-cx", "Cirugías"), ("p-ab", "Abortos")]),
        ]},
    },
}

_SYSTEM = {}


def system():
    if "s" not in _SYSTEM:
        from tests.sim import harness
        _SYSTEM["s"] = (harness, harness.build_engine())
    return _SYSTEM["s"]


def test_e2e_clarification_options_and_powerbi_answer_have_page_links():
    harness, (engine, cm, formatter, *_rest) = system()
    harness.new_conversation(engine, cm)
    first, _ui = harness.ask(engine, cm, formatter, "¿Cuántas cirugías realizadas hubo en 2024?")
    assert first["status"] == "needs_clarification", first["status"]
    options = {o["id"]: o for o in first["clarification_options"]}
    for option in options.values():
        link = L.enlace_para_opcion(option, links=SIM_LINKS)
        assert link and link["nivel"] == "pagina", (option.get("detail"), link)
    assert L.enlace_para_opcion(options["a_cx_realizadas"], links=SIM_LINKS)["url"].endswith("/r-at/p-cx")

    result = engine.select_clarification_option("b_cx_realizadas")
    assert result["status"] in ("success", "empty_result"), result["status"]
    link = L.enlace_para_resultado(result, links=SIM_LINKS)
    assert link["nivel"] == "pagina", link
    assert link["etiqueta"] == "Abrir Tablero Quirurgico › CIRUGÍAS REALIZADAS"
    assert link["url"].startswith(f"https://app.powerbi.com/groups/{WS}/reports/r-qx/p-cxr")
    harness.new_conversation(engine, cm)


def test_e2e_rag_answer_links_the_cited_report():
    harness, (engine, cm, formatter, *_rest) = system()
    harness.new_conversation(engine, cm)
    result, _ui = harness.ask(engine, cm, formatter, "¿Qué muestra el tablero de atenciones?")
    assert result["route"] == "rag" and result["status"] == "success", (result["route"], result["status"])
    link = L.enlace_para_resultado(result, links=SIM_LINKS)
    assert link and link["informe"] == "Tablero de Atenciones Institucionales", link
    harness.new_conversation(engine, cm)


DOCUMENTED = [
    "ASIGNACION DE CITAS", "BRIEFING HOSPITALARIO", "Demanda Insatisfecha", "TABLERO_ANTIBIOTICOS",
    "Tablero Control Facturacion", "TABLERO_CVC", "TABLERO DE ATENCIONES INSTITUCIONALES", "TABLERO EPS",
    "TABLERO_FARMACIA", "Tablero_lavanderia", "TABLERO NAOS", "TABLERO PERFIL DE MORBILIDAD",
    "TABLERO RECEPCION TECNICA", "TABLERO_REFERENCIA", "TABLERO TIEMPOS URGENCIAS",
]


def test_real_catalog_links_the_15_documented_boards():
    path = Path(os.getenv("POWERBI_LINKS_PATH") or ROOT / "data" / "catalog" / "report_links.json")
    data = L.cargar_enlaces(path)
    if not data:
        print(f"SKIP  (sin catálogo real en {path}; ejecuta sync_powerbi_links.py)")
        return
    missing = [name for name in DOCUMENTED if not L.enlace_para(name, links=data)]
    assert not missing, missing
    without_pages = [
        name for name in DOCUMENTED
        if not any(r["pages"] for r in data["models"][L.enlace_para(name, links=data)["modelo"]]["reports"])
    ]
    assert not without_pages, without_pages


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

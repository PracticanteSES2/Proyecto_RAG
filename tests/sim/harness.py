"""
Arnés de simulación offline del chatbot (app.py) SIN Power BI / Ollama / Qdrant.

- El código fuente (src/, app.py) se importa de la raíz REAL del repo
  (Path(__file__).resolve().parents[2]); los datos (data/catalog, data/rag,
  data/vector_db) salen de tests/sim/fixtures, que hace el papel de PROJECT_ROOT.
- Las dependencias externas se reemplazan en sys.modules (ver fakes.py). `dotenv`
  queda como no-op: el archivo .env NUNCA se abre.
- build_system() de app.py se ejecuta tal cual (se extrae por AST, sin la UI de
  Streamlit), por lo que se prueba el cableado real.

API:
    engine, cm, formatter, ollama_status, powerbi_connection, dax_log = build_engine()
    result, ui = ask(engine, cm, formatter, "pregunta")
"""
import ast
import contextlib
import io
import os
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = Path(__file__).resolve().parent
DEFAULT_SIM_ROOT = SIM_DIR / "fixtures"

APP_CONSTANTS = {"PROJECT_ROOT", "QDRANT_PATH", "SOURCE_REGISTRY", "VISUAL_METRICS", "MASTER_METRICS"}
APP_FUNCTIONS = {"build_system", "get_display_answer", "reset_if_finished"}

_APP_NS = {}


def _ensure_importable():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def load_app_namespace(sim_root):
    """Ejecuta imports + constantes + build_system/get_display_answer/reset_if_finished de app.py.

    __file__ apunta a <sim_root>/app.py => PROJECT_ROOT (datos) = sim_root.
    """
    app_path = REPO_ROOT / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"), filename=str(app_path))
    body = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            body.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in APP_CONSTANTS for t in node.targets):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in APP_FUNCTIONS:
            body.append(node)
    module = ast.Module(body=body, type_ignores=[])
    ns = {"__name__": "app_sim", "__file__": str(Path(sim_root) / "app.py")}
    exec(compile(module, str(app_path), "exec"), ns)
    return ns


def build_engine(sim_root=None, ollama_up=True, powerbi_up=True, quiet=True):
    """Construye el sistema real con dependencias falsas.

    Devuelve (engine, conversation_manager, formatter, ollama_status,
    powerbi_connection, dax_log). dax_log es la lista (viva) de consultas DAX
    ejecutadas contra el Power BI falso; cada entrada tiene: semantic_model, dax,
    rows, result, error (si falló) y type_mismatch (lista; no vacía si se comparó
    p. ej. una columna entera con DATE()).
    """
    _ensure_importable()
    sim_root = Path(sim_root) if sim_root else DEFAULT_SIM_ROOT
    from . import fakes

    fakes.CONFIG["ollama_up"] = bool(ollama_up)
    fakes.CONFIG["powerbi_up"] = bool(powerbi_up)
    fakes.install_stubs(sim_root)
    fakes.reset_log()
    # Garantía: el .env jamás se carga
    assert getattr(sys.modules["dotenv"], "__sim_fake__", False), "dotenv debe estar stubbeado"

    ns = load_app_namespace(sim_root)
    _APP_NS.clear()
    _APP_NS.update(ns)
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink if quiet else sys.stdout):
        engine, conversation_manager, formatter, ollama_status, powerbi_connection = ns["build_system"]()
    return (engine, conversation_manager, formatter, ollama_status, powerbi_connection,
            fakes.SIM_LOG["dax"])


def new_conversation(engine, conversation_manager):
    """Equivale al botón «Nueva conversación» de app.py."""
    conversation_manager.reset()
    reset = getattr(engine, "reset", None)
    if callable(reset):
        reset()


def ask(engine, conversation_manager, formatter, text, quiet=True):
    """Procesa un mensaje igual que app.py.

    Devuelve (result, ui):
      result -> dict del QueryEngine (o {"status": "error", ...} si lanzó excepción)
                con la clave extra result["_sim"] = {"dax_log", "type_mismatch",
                "warnings", "exception", "traceback", "stdout"}.
      ui     -> el texto exacto que mostraría la UI (get_display_answer).
    Aplica reset_if_finished tras responder, como app.py.
    """
    from . import fakes
    ns = _APP_NS
    dax_before = len(fakes.SIM_LOG["dax"])
    warn_before = len(fakes.SIM_LOG["warnings"])
    sink = io.StringIO()
    exception = tb = None
    try:
        with contextlib.redirect_stdout(sink if quiet else sys.stdout):
            result = engine.process(text)
            ui = ns["get_display_answer"](result, formatter)
    except Exception as exc:  # igual que app.py
        exception = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc()
        result = {"status": "error", "route": None, "error": exception}
        ui = "Ocurrió un error al procesar la consulta. Intenta nuevamente."
    entries = fakes.SIM_LOG["dax"][dax_before:]
    result["_sim"] = {
        "dax_log": entries,
        "type_mismatch": [m for e in entries for m in e.get("type_mismatch", [])],
        "warnings": fakes.SIM_LOG["warnings"][warn_before:],
        "exception": exception,
        "traceback": tb,
        "stdout": sink.getvalue(),
    }
    ns["reset_if_finished"](result, engine, conversation_manager)
    return result, ui


def run_case(case, engine, conversation_manager, formatter):
    """Ejecuta una conversación NUEVA (lista de turnos). Devuelve [(texto, result, ui), ...]."""
    new_conversation(engine, conversation_manager)
    out = []
    for text in case["turns"]:
        result, ui = ask(engine, conversation_manager, formatter, text)
        out.append((text, result, ui))
    new_conversation(engine, conversation_manager)
    return out

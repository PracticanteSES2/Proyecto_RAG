"""
Arnés "realista": el build_system() REAL de app.py con datos, Qdrant y embeddings reales,
MedGemma real u Ollama falso, y Power BI SIMULADO (powerbi_sim) detrás de un cliente
ADOMD/clr falso, de modo que src/providers/powerbi_provider.py corre sin cambios.

Misma API que tests/sim/harness.py:

    engine, cm, formatter, llm_status, powerbi_connection, dax_log = build_engine()
    result, ui = ask(engine, cm, formatter, "¿Cuántos egresos hubo en 2025?")
    result["_sim"] -> {"dax_log", "type_mismatch", "approximate", "warnings", "exception", ...}
    result, ui = choose(engine, cm, formatter, option_id, label)   # botón de contrapregunta

Datos (data_root):
  1. parámetro data_root  2. variable SIM_DATA_ROOT  3. <repo>/data  4. <checkout principal>/data
  (en un git worktree el checkout principal se deduce de .git). Debe contener
  catalog/source_registry.json, rag/*.json, vector_db/qdrant y model_metadata/.

Modelos sintéticos (synthetic=True, por defecto): tests/realistic/synthetic_models se fusiona
con data/ en una copia en caché (ver overlay.py); data_root nunca se modifica.

LLM:
  llm="fake" -> Ollama falso de tests/sim (no lee .env; dotenv queda anulado).
  llm="real" -> el .env del checkout principal se carga con el load_dotenv de app.py; si no
                existe o MedGemma no responde, llm_status lo indica (status != "ready").
"""
import ast
import atexit
import contextlib
import io
import os
import sys
import traceback
import types
from pathlib import Path

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ADOMD_DIR = REPO_ROOT / "tests" / "sim" / "fixtures" / "adomd"     # DLL vacías para PowerBIProvider

APP_CONSTANTS = {"PROJECT_ROOT", "QDRANT_PATH", "SOURCE_REGISTRY", "VISUAL_METRICS", "MASTER_METRICS"}
APP_FUNCTIONS = {"build_system", "get_display_answer", "reset_if_finished"}

STATE = {"backend": None, "simulator": None, "ns": {}, "llm": None, "project_root": None, "engine": None}


# ----------------------------------------------------------------------------
# Rutas
# ----------------------------------------------------------------------------

def main_checkout():
    """Raíz del checkout principal (en un git worktree, .git es un archivo 'gitdir: ...')."""
    git = REPO_ROOT / ".git"
    if git.is_file():
        text = git.read_text(encoding="utf-8").strip()
        if text.startswith("gitdir:"):
            gitdir = Path(text.split(":", 1)[1].strip())
            if not gitdir.is_absolute():
                gitdir = (REPO_ROOT / gitdir).resolve()
            if gitdir.parent.name == "worktrees":
                return gitdir.parents[2]
    return REPO_ROOT


def _has_catalogs(data_dir):
    data_dir = Path(data_dir)
    return (data_dir / "catalog" / "source_registry.json").exists()


def resolve_data_root(data_root=None):
    candidates = [data_root, os.getenv("SIM_DATA_ROOT"), REPO_ROOT / "data", main_checkout() / "data"]
    for candidate in candidates:
        if candidate and _has_catalogs(candidate):
            return Path(candidate).resolve()
    raise FileNotFoundError(
        "No encontré un data_root con catalog/source_registry.json. Construye data/ con el pipeline "
        "(sync_powerbi_metadata/build_powerbi_catalogs/ingest_rag) o pasa data_root=... / SIM_DATA_ROOT.")


def default_env_file():
    for root in (REPO_ROOT, main_checkout()):
        if (root / ".env").exists():
            return root / ".env"
    return main_checkout() / ".env"


def default_tableros_root():
    for root in (REPO_ROOT, main_checkout()):
        if (root / "tableros").exists():
            return root / "tableros"
    return None


# ----------------------------------------------------------------------------
# Stubs
# ----------------------------------------------------------------------------

def _module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    mod.__sim_fake__ = True
    sys.modules[name] = mod
    return mod


def _install_streamlit_stub():
    def cache_resource(func=None, **kwargs):
        if func is None:
            return lambda f: f
        return func
    _module("streamlit", cache_resource=cache_resource, cache_data=cache_resource)


def _install_fake_llm(ollama_up=True):
    from tests.sim import fakes
    fakes.CONFIG["ollama_up"] = bool(ollama_up)
    _module("ollama", Client=fakes.FakeOllamaClient, ResponseError=fakes.FakeResponseError)
    _module("dotenv", load_dotenv=lambda *a, **k: False, find_dotenv=lambda *a, **k: "")
    os.environ["MEDGEMMA_BASE_URL"] = "http://sim.invalid:11434"
    os.environ["MEDGEMMA_MODEL"] = "medgemma:latest"
    os.environ["OLLAMA_HOST"] = "http://sim.invalid:11434"
    return fakes


def _restore_real(name):
    module = sys.modules.get(name)
    if module is not None and getattr(module, "__sim_fake__", False):
        del sys.modules[name]
        for sub in [m for m in sys.modules if m.startswith(name + ".")]:
            del sys.modules[sub]


def _forget_project_modules():
    """Fuerza a reimportar app/src con los stubs actuales (p. ej. al cambiar de llm fake a real)."""
    for name in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
        del sys.modules[name]


# ----------------------------------------------------------------------------
# app.py por AST
# ----------------------------------------------------------------------------

def load_app_namespace(project_root, env_root=None):
    """Ejecuta de app.py: imports, constantes y build_system/get_display_answer/reset_if_finished.

    __file__ = <project_root>/app.py  => PROJECT_ROOT (datos) = project_root.
    Si env_root se indica, se ejecuta además el bloque try/load_dotenv de app.py con
    __file__ = <env_root>/app.py (carga el .env del usuario sin imprimir nada).
    """
    app_path = REPO_ROOT / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"), filename=str(app_path))
    if env_root is not None:
        dotenv_blocks = [node for node in tree.body if isinstance(node, ast.Try)
                         and "load_dotenv" in ast.unparse(node)]
        env_ns = {"__name__": "app_env", "__file__": str(Path(env_root) / "app.py"), "Path": Path}
        exec(compile(ast.Module(body=dotenv_blocks, type_ignores=[]), str(app_path), "exec"), env_ns)
    body = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            body.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in APP_CONSTANTS for t in node.targets):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in APP_FUNCTIONS:
            body.append(node)
    ns = {"__name__": "app_realistic", "__file__": str(Path(project_root) / "app.py")}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(app_path), "exec"), ns)
    return ns


# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------

def build_simulator(data_root=None, synthetic=True, today=None, tableros_root="auto", seed="pbi-sim"):
    """PowerBISimulator sobre data_root/model_metadata (+ overlay sintético)."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from tests.realistic.powerbi_sim import PowerBISimulator
    from tests.realistic import overlay
    data_root = Path(data_root) if data_root else resolve_data_root()
    roots = [Path(data_root) / "model_metadata"]
    if synthetic:
        roots.append((overlay.SYNTHETIC_DIR, "synthetic"))
    if tableros_root == "auto":
        tableros_root = default_tableros_root()
    registry = Path(data_root) / "catalog" / "model_registry.json"
    return PowerBISimulator(roots, registry_path=registry, tableros_root=tableros_root, today=today, seed=seed)


def build_engine(data_root=None, llm="fake", powerbi_up=True, synthetic=None, ollama_up=True, quiet=True,
                 today=None, culture="es-CO", net_types=True, default_model=None, env_file=None,
                 tableros_root="auto"):
    """Construye el sistema real de app.py con Power BI simulado.

    Devuelve (engine, conversation_manager, formatter, llm_status, powerbi_connection, dax_log).
    dax_log es la lista viva de consultas ejecutadas contra el simulador.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")   # el modelo de embeddings ya está en caché local
    from tests.realistic import overlay
    from tests.realistic.powerbi_sim import adomd

    if synthetic is None:   # SIM_SYNTHETIC=0 desactiva el overlay (p. ej. desde tests/eval/run.py)
        synthetic = os.getenv("SIM_SYNTHETIC", "1").strip().lower() not in ("0", "false", "no")
    data_root = resolve_data_root(data_root)
    # Siempre sobre una copia en caché: data_root (p. ej. ROOT/data) nunca se modifica.
    project_root = overlay.build_merged_root(data_root, quiet=quiet, synthetic=synthetic)

    simulator = build_simulator(project_root / "data", synthetic=False, today=today,
                                tableros_root=tableros_root)
    backend = adomd.install(simulator, culture=culture, net_types=net_types, powerbi_up=powerbi_up)
    STATE.update(backend=backend, simulator=simulator, project_root=project_root)

    _close_previous()
    _install_streamlit_stub()
    for name in ("sentence_transformers", "qdrant_client"):
        _restore_real(name)          # por si tests/sim los dejó falsos en este proceso
    _forget_project_modules()
    env_root = None
    llm_note = None
    if llm == "real":
        _restore_real("dotenv")
        _restore_real("ollama")
        env_path = Path(env_file) if env_file else default_env_file()
        if env_path.exists():
            env_root = env_path.parent
        else:
            llm_note = f".env no encontrado en {env_path.parent}"
            # Sin .env: un host que rechaza la conexión al instante.
            os.environ.setdefault("MEDGEMMA_BASE_URL", "http://127.0.0.1:9")
    elif llm in ("fake", "down"):
        # "down" (tests/eval): Ollama falso caído.
        _install_fake_llm(ollama_up=ollama_up and llm != "down")
    else:
        raise ValueError("llm debe ser 'real', 'fake' o 'down'")
    STATE["llm"] = llm

    # Power BI simulado: estas variables ganan sobre el .env (load_dotenv no sobrescribe).
    models = simulator.list_models()
    default_model = default_model or next(
        (m for m in models if m.casefold() == "tablero de atenciones institucionales"), models[0] if models else "")
    os.environ["POWERBI_XMLA_ENDPOINT"] = "powerbi://api.powerbi.com/v1.0/myorg/Gestion%20Clinica%20(SIMULADO)"
    os.environ["POWERBI_SEMANTIC_MODEL"] = default_model
    os.environ["ADOMD_PATH"] = str(ADOMD_DIR)
    os.environ["IDENTITY_PATH"] = str(ADOMD_DIR)
    os.environ.setdefault("QDRANT_COLLECTION_NAME", "gestion_clinica_rag")

    ns = load_app_namespace(project_root, env_root=env_root)
    STATE["engine"] = None
    STATE["ns"] = ns
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink if quiet else sys.stdout):
        engine, conversation_manager, formatter, llm_status, powerbi_connection = ns["build_system"]()
    STATE["engine"] = engine
    atexit.register(_close_previous)   # cierra Qdrant antes del apagado (evita el ruido del __del__)
    llm_status = dict(llm_status or {})
    llm_status["mode"] = llm
    if llm_note:
        llm_status["sim_note"] = llm_note
    return engine, conversation_manager, formatter, llm_status, powerbi_connection, backend.log["dax"]


def _close_previous():
    """Cierra el Qdrant local del motor anterior (Qdrant en disco no admite dos clientes)."""
    engine = STATE.get("engine")
    if engine is None:
        return
    seen = set()
    for holder in (engine, getattr(engine, "rag_answer_engine", None), getattr(engine, "metric_resolver", None)):
        retriever = getattr(holder, "retriever", None)
        client = getattr(retriever, "client", None)
        if client is not None and id(client) not in seen:
            seen.add(id(client))
            with contextlib.suppress(Exception):
                client.close()
    STATE["engine"] = None


def new_conversation(engine, conversation_manager):
    """Equivale al botón «Nueva conversación» de app.py."""
    conversation_manager.reset()
    reset = getattr(engine, "reset", None)
    if callable(reset):
        try:
            reset(full=True)  # también olvida el contexto de seguimiento («¿y en 2025?»)
        except TypeError:
            reset()


def _run(engine, conversation_manager, formatter, runner, quiet=True):
    ns = STATE["ns"]
    log = STATE["backend"].log
    before = len(log["dax"])
    sink = io.StringIO()
    exception = tb = None
    try:
        with contextlib.redirect_stdout(sink if quiet else sys.stdout):
            result = runner()
            ui = ns["get_display_answer"](result, formatter)
    except Exception as exc:  # igual que app.py
        exception = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc()
        result = {"status": "error", "route": None, "error": exception,
                  "reasoning": getattr(engine, "last_reasoning", None)}
        ui = "Ocurrió un error al procesar la consulta. Intenta nuevamente."
    entries = log["dax"][before:]
    result["_sim"] = {
        "dax_log": entries,
        "type_mismatch": [m for e in entries for m in e.get("type_mismatch", [])],
        "approximate": [a for e in entries for a in e.get("approximate", [])],
        "errors": [e["error"] for e in entries if e.get("error")],
        "warnings": [w for e in entries for w in e.get("warnings", [])],
        "exception": exception,
        "traceback": tb,
        "stdout": sink.getvalue(),
    }
    ns["reset_if_finished"](result, engine, conversation_manager)
    return result, ui


def ask(engine, conversation_manager, formatter, text, quiet=True):
    """Procesa un mensaje igual que app.py. Devuelve (result, ui)."""
    return _run(engine, conversation_manager, formatter, lambda: engine.process(text), quiet)


def choose(engine, conversation_manager, formatter, option_id, label=None, quiet=True):
    """Equivale a pulsar un botón de contrapregunta (engine.select_clarification_option)."""
    return _run(engine, conversation_manager, formatter,
                lambda: engine.select_clarification_option(option_id, label), quiet)


ask_option = choose   # nombre que usa tests/eval/run.py


def run_case(case, engine, conversation_manager, formatter):
    """Conversación NUEVA (lista de turnos). Devuelve [(texto, result, ui), ...]."""
    new_conversation(engine, conversation_manager)
    out = []
    for text in case["turns"]:
        result, ui = ask(engine, conversation_manager, formatter, text)
        out.append((text, result, ui))
    new_conversation(engine, conversation_manager)
    return out

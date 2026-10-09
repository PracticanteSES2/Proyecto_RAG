"""
Lanza la app Streamlit REAL (app.py) con Power BI simulado.

    python -m tests.realistic.run_app                 # LLM falso (sin .env)
    python -m tests.realistic.run_app --llm real      # MedGemma real con el .env del checkout principal
    python -m tests.realistic.run_app --no-synthetic --port 8502
    # equivalente directo:
    streamlit run tests/realistic/run_app.py -- --llm real

En cada ejecución del script (Streamlit lo re-ejecuta en cada interacción):
  1. Una sola vez por proceso: arma la raíz fusionada (data/ + modelos sintéticos, overlay.py),
     crea el PowerBISimulator e instala los módulos falsos `clr` y
     `Microsoft.AnalysisServices.AdomdClient`; con --llm fake instala además el Ollama falso
     y anula dotenv.
  2. Ejecuta el código de app.py tal cual con __file__ = <raíz fusionada>/app.py
     (PROJECT_ROOT apunta a los datos fusionados; build_system queda en st.cache_resource).

Opciones tras "--": --llm real|fake, --data-root RUTA, --no-synthetic, --powerbi-down, --culture.
"""
import argparse
import os
import subprocess
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
STATE_MODULE = "_proyecto_rag_sim_app_state"


def _options(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--llm", choices=("fake", "real"), default="fake")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--no-synthetic", action="store_true")
    parser.add_argument("--powerbi-down", action="store_true")
    parser.add_argument("--culture", default="es-CO", choices=("es-CO", "en-US", "invariant"))
    parser.add_argument("--port", default=None)
    return parser.parse_known_args(argv)[0]


def _inside_streamlit():
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


def _setup(options):
    """Prepara stubs y datos una sola vez por proceso de Streamlit."""
    state = sys.modules.get(STATE_MODULE)
    if state is not None:
        return state
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from tests.realistic import harness, overlay
    from tests.realistic.powerbi_sim import adomd

    data_root = harness.resolve_data_root(options.data_root)
    project_root = overlay.build_merged_root(data_root, synthetic=not options.no_synthetic)
    simulator = harness.build_simulator(project_root / "data", synthetic=False)
    backend = adomd.install(simulator, culture=options.culture, powerbi_up=not options.powerbi_down)
    env_root = None
    if options.llm == "fake":
        harness._install_fake_llm(ollama_up=True)
    else:
        env_path = harness.default_env_file()
        env_root = env_path.parent if env_path.exists() else None
    models = simulator.list_models()
    os.environ["POWERBI_XMLA_ENDPOINT"] = "powerbi://api.powerbi.com/v1.0/myorg/Gestion%20Clinica%20(SIMULADO)"
    os.environ["POWERBI_SEMANTIC_MODEL"] = next(
        (m for m in models if m.casefold() == "tablero de atenciones institucionales"), models[0])
    os.environ["ADOMD_PATH"] = str(harness.ADOMD_DIR)
    os.environ["IDENTITY_PATH"] = str(harness.ADOMD_DIR)
    if env_root is not None:
        # El bloque try/load_dotenv de app.py, con __file__ en la carpeta del .env del usuario.
        harness.load_app_namespace(project_root, env_root=env_root)
    state = types.ModuleType(STATE_MODULE)
    state.project_root = project_root
    state.backend = backend
    state.options = options
    state.env_found = env_root is not None
    sys.modules[STATE_MODULE] = state
    return state


def _run_app(state):
    import streamlit as st
    app_path = REPO_ROOT / "app.py"
    code = compile(app_path.read_text(encoding="utf-8"), str(app_path), "exec")
    namespace = {"__name__": "__main__", "__file__": str(Path(state.project_root) / "app.py")}
    exec(code, namespace)
    with st.sidebar:
        st.caption(
            f"🧪 Power BI SIMULADO ({len(state.backend.sim.list_models())} modelos, datos sintéticos) · "
            f"LLM: {state.options.llm}" + ("" if state.options.llm == "fake" or state.env_found else " (sin .env)"))


def launch(argv):
    """Arranca `streamlit run` sobre este archivo pasando las opciones tras "--"."""
    options = _options(argv)
    command = [sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve())]
    if options.port:
        command += ["--server.port", str(options.port)]
    passthrough = [a for a in argv if not a.startswith("--port") and a != options.port]
    command += ["--", *passthrough]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    print("Lanzando:", " ".join(command))
    return subprocess.call(command, cwd=str(REPO_ROOT), env=env)


if _inside_streamlit():
    _run_app(_setup(_options(sys.argv[1:])))
elif __name__ == "__main__":
    sys.exit(launch(sys.argv[1:]))

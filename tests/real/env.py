"""
Entorno común de tests/real: rutas del checkout principal (data/, .env, caché
del token) y conexión de solo lectura al Power BI real.

No imprime ni guarda valores del .env. Fija POWERBI_AUTH=device_code (token
en caché, sin ventana) y POWERBI_TOKEN_CACHE en el data/ del checkout
principal (un worktree no tiene data/).
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main_checkout():
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


MAIN_ROOT = main_checkout()
DATA_ROOT = (REPO_ROOT / "data") if (REPO_ROOT / "data" / "catalog").exists() else (MAIN_ROOT / "data")
PROJECT_ROOT = DATA_ROOT.parent  # PROJECT_ROOT de app.py (datos)


def setup_env():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    os.environ.setdefault("POWERBI_AUTH", "device_code")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    # Igual que app.py: SOLO el .env del checkout desde el que se ejecuta
    # (nunca el de otro checkout). Se corre desde la raíz del checkout
    # principal; load_dotenv no sobrescribe variables ya definidas.
    try:
        from dotenv import load_dotenv
        env = REPO_ROOT / ".env"
        if env.exists():
            load_dotenv(env)
    except ImportError:
        pass


_PROVIDER = None


def provider():
    global _PROVIDER
    if _PROVIDER is None:
        setup_env()
        from src.providers.powerbi_provider import PowerBIProvider
        _PROVIDER = PowerBIProvider()
    return _PROVIDER


def dax(query, model, max_rows=60):
    """Consulta de VERDAD (solo agregados / DISTINCT de dimensiones no personales)."""
    result = provider().execute_dax(query, model)
    if result.get("status") != "success":
        raise RuntimeError(f"{model}: {result.get('error')}")
    return result["rows"][:max_rows]

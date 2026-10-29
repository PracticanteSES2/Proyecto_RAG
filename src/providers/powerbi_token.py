"""
Autenticación de Power BI sin ventana (código de dispositivo).

Con POWERBI_AUTH=device_code en el .env, PowerBIProvider no usa el login
interactivo de ADOMD (que necesita una ventana en el escritorio) sino un token
de Microsoft Entra que se pasa en la cadena de conexión. La primera vez:

    python -m src.providers.powerbi_token login

muestra un código; se escribe en https://microsoft.com/devicelogin con la
cuenta que tiene acceso al workspace. El token (y su renovación) queda en
caché en data/.powerbi_token_cache.bin (carpeta ignorada por git): procesos
en segundo plano, tareas programadas y pruebas lo reutilizan sin ventana.
`logout` borra la caché.

Variables opcionales: POWERBI_CLIENT_ID (aplicación pública; por defecto la
de los cmdlets de Power BI), POWERBI_TENANT (por defecto «organizations»),
POWERBI_TOKEN_CACHE (ruta de la caché).
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLIENT_ID = "ea0616ba-638b-4df5-95b9-636659ae5121"
SCOPES = ["https://analysis.windows.net/powerbi/api/.default"]

_lock = threading.Lock()


class TokenNoDisponible(RuntimeError):
    """No hay sesión en caché: hay que ejecutar `login`."""


def modo_sin_ventana() -> bool:
    load_dotenv()
    return os.getenv("POWERBI_AUTH", "").strip().lower() in {"device_code", "token"}


def _usar_almacen_de_windows():
    # La red corporativa inspecciona HTTPS con su propio certificado raíz:
    # se confía en el almacén de certificados de Windows, como el navegador.
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass


def _ruta_cache() -> Path:
    ruta = os.getenv("POWERBI_TOKEN_CACHE", "").strip()
    return Path(ruta) if ruta else PROJECT_ROOT / "data" / ".powerbi_token_cache.bin"


def _app():
    import msal

    _usar_almacen_de_windows()
    cache = msal.SerializableTokenCache()
    ruta = _ruta_cache()
    if ruta.exists():
        cache.deserialize(ruta.read_text(encoding="utf-8"))
    app = msal.PublicClientApplication(
        os.getenv("POWERBI_CLIENT_ID", "").strip() or DEFAULT_CLIENT_ID,
        authority="https://login.microsoftonline.com/"
        + (os.getenv("POWERBI_TENANT", "").strip() or "organizations"),
        token_cache=cache,
    )
    return app, cache, ruta


def _guardar(cache, ruta: Path) -> None:
    if cache.has_state_changed:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(cache.serialize(), encoding="utf-8")


def obtener_token() -> str:
    """Token vigente desde la caché (lo renueva solo); nunca abre ventanas."""
    load_dotenv()
    with _lock:
        app, cache, ruta = _app()
        cuentas = app.get_accounts()
        resultado = app.acquire_token_silent(SCOPES, account=cuentas[0]) if cuentas else None
        _guardar(cache, ruta)
    if not resultado or "access_token" not in resultado:
        raise TokenNoDisponible(
            "No hay sesión de Power BI en caché. Ejecuta: "
            "python -m src.providers.powerbi_token login"
        )
    return resultado["access_token"]


def login() -> str:
    """Inicio de sesión con código de dispositivo; devuelve la cuenta."""
    load_dotenv()
    app, cache, ruta = _app()
    flujo = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flujo:
        raise RuntimeError(f"No se pudo iniciar el código de dispositivo: {flujo.get('error_description') or flujo}")
    print(flujo["message"], flush=True)
    resultado = app.acquire_token_by_device_flow(flujo)
    _guardar(cache, ruta)
    if "access_token" not in resultado:
        raise RuntimeError(f"Inicio de sesión fallido: {resultado.get('error_description') or resultado.get('error')}")
    return (resultado.get("id_token_claims") or {}).get("preferred_username", "cuenta desconocida")


def logout() -> None:
    ruta = _ruta_cache()
    if ruta.exists():
        ruta.unlink()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    accion = argv[0] if argv else "estado"
    if accion == "login":
        print(f"Sesión iniciada: {login()}. Token en caché: {_ruta_cache()}")
    elif accion == "logout":
        logout()
        print("Caché de sesión eliminada.")
    else:
        try:
            obtener_token()
            print("Hay una sesión de Power BI vigente en caché.")
        except TokenNoDisponible as error:
            print(error)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

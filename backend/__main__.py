"""Puntos de entrada del backend.

    python -m backend api [--host 127.0.0.1] [--port 8000] [--workers 1] [--reload]
    python -m backend trabajador        (solo con REDIS_URL; ver docs/backend.md)

`api` equivale a `uvicorn backend.app.main:app`; `trabajador` a
`python -m backend.worker`.
"""
from __future__ import annotations

import argparse
import sys

import uvicorn

from backend import worker
from backend.app.main import create_app


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(prog="python -m backend", description="Backend del asistente")
    ordenes = analizador.add_subparsers(dest="orden", required=True)
    api = ordenes.add_parser("api", help="API FastAPI (uvicorn)")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--workers", type=int, default=1, help="procesos uvicorn (más de 1 solo con Redis)")
    api.add_argument("--reload", action="store_true", help="recarga al editar (desarrollo)")
    ordenes.add_parser("trabajador", help="proceso dueño del motor (con Redis)")
    return analizador.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    if args.orden == "trabajador":
        return worker.main()
    if args.workers > 1 or args.reload:
        # Varios procesos o recarga: uvicorn necesita la ruta de importación.
        uvicorn.run("backend.app.main:app", host=args.host, port=args.port, workers=args.workers, reload=args.reload)
    else:
        uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())

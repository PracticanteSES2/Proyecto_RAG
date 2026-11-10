"""Aplicación FastAPI del asistente.

    uvicorn backend.app.main:app                  (sin REDIS_URL: todo en un proceso)
    uvicorn backend.app.main:app --workers 4      (con REDIS_URL + `python -m backend.worker`)

Ver docs/backend.md y specs/006-api-backend/.
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.v1 import router as router_v1
from backend.app.core import errores
from backend.app.core.config import Ajustes, obtener_ajustes
from backend.app.core.registro import configurar_registro
from backend.app.services.conversaciones import ServicioConversaciones
from backend.app.services.sistema import crear_servicios, crear_trabajador

LOG = logging.getLogger(__name__)


def _arrancar_trabajador(app: FastAPI, fabrica_piscina) -> None:
    """Modo embebido: arma el motor (lento) en un hilo para no demorar el
    arranque de la API; mientras tanto los turnos esperan en la cola."""
    servicios = app.state.servicios

    def armar():
        try:
            trabajador = crear_trabajador(servicios.ajustes, servicios.almacen_trabajador, fabrica_piscina)
            trabajador.iniciar()
            servicios.trabajador = trabajador
        except Exception:
            LOG.exception("No se pudo arrancar el motor embebido; los turnos quedarán en la cola")

    hilo = threading.Thread(target=armar, name="arranque-motor", daemon=True)
    hilo.start()
    app.state.hilo_arranque = hilo


def _mensaje_validacion(error: RequestValidationError) -> str:
    for detalle in error.errors():
        mensaje = str(detalle.get("msg") or "")
        if mensaje.startswith("Value error, "):
            return mensaje.removeprefix("Value error, ")
    return errores.MENSAJE_INVALIDO


def _registrar_errores(app: FastAPI) -> None:
    @app.exception_handler(errores.ErrorAPI)
    async def _error_api(_: Request, error: errores.ErrorAPI):
        return JSONResponse(error.cuerpo(), status_code=error.estado_http, headers=error.cabeceras)

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, error: RequestValidationError):
        return JSONResponse({"mensaje": _mensaje_validacion(error), "codigo": errores.PETICION_INVALIDA},
                            status_code=422)

    @app.exception_handler(Exception)
    async def _inesperado(request: Request, error: Exception):
        LOG.exception("Error inesperado en %s %s", request.method, request.url.path)
        return JSONResponse({"mensaje": errores.MENSAJE_INTERNO, "codigo": errores.ERROR_INTERNO}, status_code=500)


def create_app(ajustes: Ajustes | None = None, redis_api=None, redis_trabajador=None, fabrica_piscina=None,
               iniciar_motor: bool = True) -> FastAPI:
    """`redis_*` y `fabrica_piscina` permiten inyectar fakeredis y un motor doble."""
    ajustes = ajustes or obtener_ajustes()
    configurar_registro(ajustes.backend_log_nivel)

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        servicios = crear_servicios(ajustes, redis_api, redis_trabajador)
        app.state.servicios = servicios
        app.state.conversaciones = ServicioConversaciones(servicios.almacen, ajustes)
        LOG.info("API lista · almacén %s · motor %s", servicios.modo, "embebido" if servicios.embebido else "externo")
        if servicios.embebido and iniciar_motor:
            _arrancar_trabajador(app, fabrica_piscina)
        try:
            yield
        finally:
            if servicios.trabajador is not None:
                servicios.trabajador.detener()
            await servicios.almacen.cerrar()

    app = FastAPI(
        title="Asistente de Gestión Clínica — API", version="1.0.0", lifespan=ciclo_de_vida,
        openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs", redoc_url=None,
        description="API del asistente que responde sobre los tableros de Power BI y su documentación. "
                    "Contrato: specs/006-api-backend/contracts/api-v1.md",
    )
    app.add_middleware(CORSMiddleware, allow_origins=ajustes.cors_origenes, allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["*"],
                       expose_headers=["Retry-After", "Content-Disposition"])
    _registrar_errores(app)
    app.include_router(router_v1)
    return app


def __getattr__(nombre: str):
    # `uvicorn backend.app.main:app` crea la app al pedirla (las pruebas usan create_app).
    if nombre == "app":
        aplicacion = create_app()
        globals()["app"] = aplicacion
        return aplicacion
    raise AttributeError(nombre)

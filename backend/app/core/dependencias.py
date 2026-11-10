"""Dependencias de FastAPI: los servicios viven en `app.state.servicios`
(los arma `main.create_app` en el arranque). Sin importar `services`: core es
la capa base del backend."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request


def servicios(request: Request) -> Any:
    return request.app.state.servicios


def conversaciones(request: Request) -> Any:
    return request.app.state.conversaciones


def ajustes(request: Request) -> Any:
    return request.app.state.servicios.ajustes


ServiciosDep = Annotated[Any, Depends(servicios)]
ConversacionesDep = Annotated[Any, Depends(conversaciones)]
AjustesDep = Annotated[Any, Depends(ajustes)]

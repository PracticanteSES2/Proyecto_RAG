"""Esquemas de conversaciones (contrato v1)."""
from typing import Literal

from pydantic import BaseModel

from backend.app.schemas.comunes import Error
from backend.app.schemas.turnos import Respuesta


class ConversacionCreada(BaseModel):
    conversacion_id: str


class Mensaje(BaseModel):
    rol: Literal["usuario", "asistente"]
    turno_id: str | None = None
    fecha: str | None = None
    texto: str | None = None
    via: Literal["texto", "opcion"] | None = None
    respuesta: Respuesta | None = None
    error: Error | None = None
    contrapregunta_vigente: bool = False


class Historial(BaseModel):
    conversacion_id: str
    creada: str | None = None
    actualizada: str | None = None
    turno_activo: str | None = None
    mensajes: list[Mensaje]

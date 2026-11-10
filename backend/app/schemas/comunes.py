"""Esquemas comunes del contrato v1."""
from pydantic import BaseModel, Field


class Error(BaseModel):
    mensaje: str = Field(description="Texto amable en español, sin detalles internos")
    codigo: str = Field(description="Código estable para el frontend (p. ej. turno_en_curso)")
    reintentar_en_s: int | None = Field(default=None, description="Solo en 429")


class Enlace(BaseModel):
    titulo: str
    url: str


RESPUESTAS_ERROR = {
    400: {"model": Error, "description": "Petición no soportada"},
    404: {"model": Error, "description": "No existe o expiró"},
    409: {"model": Error, "description": "Conflicto de estado"},
    422: {"model": Error, "description": "Petición inválida"},
    429: {"model": Error, "description": "Demasiadas peticiones (cabecera Retry-After)"},
    503: {"model": Error, "description": "Servicio ocupado"},
}

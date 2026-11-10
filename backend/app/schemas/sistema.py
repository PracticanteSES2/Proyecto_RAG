"""Esquemas de capacidades, salud y diagnóstico (contrato v1)."""
from typing import Any, Literal

from pydantic import BaseModel

EstadoComponente = Literal["ok", "caido", "iniciando", "desconocido", "no_configurado", "degradado"]


class Capacidades(BaseModel):
    listo: bool
    tableros_datos: list[str] = []
    tableros_documentacion: list[str] = []
    ejemplos: list[str] = []


class Componente(BaseModel):
    estado: EstadoComponente
    modelo: str | None = None
    instancias: int | None = None
    ocupadas: int | None = None
    latido_hace_s: float | None = None


class Cola(BaseModel):
    en_espera: int = 0
    en_curso: int = 0


class Salud(BaseModel):
    estado: Literal["ok", "degradado", "caido"]
    listo: bool
    modo: Literal["redis", "memoria"]
    componentes: dict[str, Componente]
    cola: Cola
    version: str | None = None


class DiagnosticoServidor(BaseModel):
    disponible: bool
    actualizado: str | None = None
    lineas_markdown: list[str] = []
    linea_estado: str | None = None
    instantanea: dict[str, Any] | None = None
    cola: Cola = Cola()
    motor: dict[str, Any] | None = None
    presion_llm: dict[str, Any] | None = None

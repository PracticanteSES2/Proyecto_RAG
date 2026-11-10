"""Esquemas de turnos y de los eventos SSE (contrato v1)."""
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from backend.app.schemas.comunes import Enlace

MENSAJE_MAX = 2000


class TurnoEntrada(BaseModel):
    mensaje: str = Field(default="", max_length=MENSAJE_MAX,
                         description="Pregunta. Con opcion_id puede ir el texto del botón o vacío")
    diagnostico: bool = Field(default=False, description="Incluir `diagnostico` en la respuesta")
    opcion_id: str | None = Field(default=None, max_length=200,
                                  description="Respuesta a la contrapregunta pendiente (opciones[].id)")

    @model_validator(mode="after")
    def _mensaje_u_opcion(self):
        self.mensaje = (self.mensaje or "").strip()
        if self.opcion_id is not None:
            self.opcion_id = self.opcion_id.strip() or None
        if not self.mensaje and not self.opcion_id:
            raise ValueError("Escribe una pregunta o elige una opción.")
        return self


class TurnoCreado(BaseModel):
    turno_id: str
    conversacion_id: str
    eventos_url: str


class Fuente(BaseModel):
    titulo: str
    tablero: str | None = None
    pagina: str | None = None


class Opcion(BaseModel):
    id: str
    texto: str
    descripcion: str | None = None
    enlace_powerbi: Enlace | None = None


class Contrapregunta(BaseModel):
    pregunta: str
    opciones: list[Opcion]


class Detalles(BaseModel):
    informe: str | None = None
    tablero: str | None = None
    modelo_semantico: str | None = None
    metrica: str | None = None
    filtros_tablero: list[str] = []
    sintesis: str | None = None


Ruta = Literal["conversacion", "datos", "documentacion", "contrapregunta", "fuera_de_alcance", "otra"]


class Respuesta(BaseModel):
    """Datos del evento SSE `respuesta`."""
    turno_id: str
    texto_markdown: str
    ruta: Ruta
    estado: str | None = None
    fuentes: list[Fuente] = []
    enlaces_powerbi: list[Enlace] = []
    contrapregunta: Contrapregunta | None = None
    detalles: Detalles | None = None
    degradada: bool = False
    aviso: str | None = None
    cacheada: bool = False
    diagnostico: dict[str, Any] | None = Field(
        default=None, description="Solo con diagnostico=true: razonamiento, pasos, tiempos, dax, plan…")


class EventoCola(BaseModel):
    posicion: int = Field(ge=0, description="1 = el siguiente; 0 = desconocida")
    en_curso: int = Field(ge=0)


class EventoProgreso(BaseModel):
    etapa: str
    frase: str
    t: float = Field(description="Segundos desde el inicio (no mostrar)")


class EventoEspera(BaseModel):
    nivel: int
    frase: str
    t: float


class EventoAviso(BaseModel):
    motivo: str
    texto: str


class EventoError(BaseModel):
    mensaje: str
    codigo: str


class EventoToken(BaseModel):
    texto: str


class CatalogoEventosSSE(BaseModel):
    """Datos (`data:`) de cada evento del SSE, por nombre de evento (`event:`).
    Solo documenta el contrato en OpenAPI; el flujo es `text/event-stream`."""
    cola: EventoCola | None = Field(default=None, description="Solo en modo diagnóstico")
    progreso: EventoProgreso | None = None
    espera: EventoEspera | None = None
    token: EventoToken | None = None
    aviso: EventoAviso | None = None
    respuesta: Respuesta | None = None
    error: EventoError | None = None
    fin: dict | None = Field(default=None, description="{} — último evento")


class Calificacion(BaseModel):
    valor: Literal["buena", "mala"]
    comentario: str | None = Field(default=None, max_length=2000,
                                   description="Qué se esperaba (obligatorio si es mala). Sin datos de pacientes")

    @model_validator(mode="after")
    def _comentario_si_mala(self):
        self.comentario = (self.comentario or "").strip() or None
        if self.valor == "mala" and not self.comentario:
            raise ValueError("Cuéntanos qué esperabas para poder guardar la calificación.")
        return self


class CalificacionGuardada(BaseModel):
    guardada: bool

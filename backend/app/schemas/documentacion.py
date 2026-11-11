"""Contrato de la documentación viva (specs/013-documentacion-web/contracts/api-documentacion.md)."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

EstadoPropuesta = Literal["preparando", "lista", "requiere_aclaracion", "error", "aprobada", "descartada"]
EstadoReindexacion = Literal["sin_iniciar", "en_curso", "lista", "error", "no_disponible"]


def _texto_obligatorio(valor: str, mensaje: str) -> str:
    if not (valor or "").strip():
        raise ValueError(mensaje)
    return valor.strip()


# ---------------------------------------------------------------- explorar

class Grupo(BaseModel):
    grupo: str = Field(description="source_group (carpeta en docs_tableros/)")
    tablero: str = Field(description="Nombre del informe (manifest.json)")
    paginas: int


class ListaGrupos(BaseModel):
    grupos: list[Grupo]


class PaginaResumen(BaseModel):
    archivo: str
    pagina: str
    nombre_funcional: str = ""
    bloque: str = ""
    valido: bool
    general: bool = Field(description="True para _general.md (bloque General del tablero)")
    etiqueta: str = Field(description="«Página — nombre funcional · bloque»")


class ListaPaginas(BaseModel):
    grupo: str
    tablero: str
    paginas: list[PaginaResumen]


class FilaFicha(BaseModel):
    dato: str
    valor: str = Field(description="«—» si no hay valor")


class Entrada(BaseModel):
    nombre: str
    texto: str = Field(description="Markdown")


class Seccion(BaseModel):
    titulo: str
    entradas: list[Entrada]


class Cuerpo(BaseModel):
    proposito: str = Field(description="Markdown")
    secciones: list[Seccion]


class Documento(BaseModel):
    grupo: str
    tablero: str
    archivo: str
    ruta: str = Field(description="<grupo>/md/<archivo>")
    pagina: str
    interpretable: bool = Field(description="False si el .md no se pudo interpretar (solo va `texto`)")
    valido: bool
    errores_formato: list[str]
    ficha: list[FilaFicha]
    cuerpo: Cuerpo
    historial: list[Entrada] = Field(description="El más reciente primero")
    texto: str = Field(description="El archivo .md tal como está guardado")


# ---------------------------------------------------------------- propuestas

class SolicitudPropuesta(BaseModel):
    nota: str = Field(max_length=4000, description="Qué cambió, en palabras sencillas")
    grupo: str = Field(min_length=1, max_length=200)
    pagina: str | None = Field(default=None, max_length=300, description="Nombre de la página; null = detectar")
    cambios_pbip: list[str] = Field(default_factory=list, max_length=50,
                                    description="Cambios detectados en el PBIP, uno por línea")
    autor: str = Field(default="", max_length=120)

    @field_validator("nota")
    @classmethod
    def _nota(cls, valor: str) -> str:
        return _texto_obligatorio(valor, "Escribe qué cambió en el tablero.")

    @field_validator("cambios_pbip")
    @classmethod
    def _cambios(cls, valor: list[str]) -> list[str]:
        if any(len(linea) > 500 for linea in valor):
            raise ValueError("Cada cambio del PBIP debe tener como máximo 500 caracteres.")
        return [linea.strip() for linea in valor if linea.strip()]


class Progreso(BaseModel):
    etapa: Literal["leyendo_nota", "eligiendo_pagina", "redactando", "revisando"]
    frase: str = Field(description="Frase de trabajo (rota cada 8 s); nunca habla de colas")
    espera: str | None = Field(default=None, description="Mensaje de espera larga (10/25/50/90 s)")


class Operacion(BaseModel):
    indice: int
    accion: str = Field(description="agregar | modificar | eliminar")
    seccion: str
    entrada: str
    descripcion: str = Field(description="Markdown: «Cambiar la entrada **«X»** de **Sección**»")
    texto: str
    texto_actual: str | None = None
    editable: bool


class LineaDiff(BaseModel):
    tipo: Literal["igual", "sale", "entra"]
    texto: str


class BloqueDiff(BaseModel):
    lineas: list[LineaDiff]


class Diff(BaseModel):
    agregadas: int
    eliminadas: int
    unificado: str
    bloques: list[BloqueDiff] = Field(description="Solo los tramos cambiados, con 1 línea de contexto")


class VistaPrevia(BaseModel):
    cuerpo: Cuerpo
    historial: list[Entrada]


class Candidata(BaseModel):
    pagina: str
    etiqueta: str


class Reindexacion(BaseModel):
    grupo: str
    estado: EstadoReindexacion
    mensaje: str = ""
    documentos: int | None = None
    chunks: int | None = None
    segundos: float | None = None
    conexion_compartida: bool = False
    avisos: list[str] = Field(default_factory=list)
    iniciada: str | None = None
    terminada: str | None = None


class Aprobacion(BaseModel):
    autor: str
    version: int | None = None
    fecha: str
    reindexacion: Reindexacion


class Propuesta(BaseModel):
    propuesta_id: str
    grupo: str
    tablero: str
    estado: EstadoPropuesta
    nota: str
    pagina: str = ""
    nombre_funcional: str = ""
    autor: str = ""
    cambios_pbip: list[str] = Field(default_factory=list)
    progreso: Progreso | None = None
    como_se_eligio: str = ""
    resumen: str = ""
    dudas: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    errores: list[str] = Field(default_factory=list)
    operaciones: list[Operacion] = Field(default_factory=list)
    diff: Diff | None = None
    vista_previa: VistaPrevia | None = None
    formato_valido: bool = False
    errores_formato: list[str] = Field(default_factory=list)
    candidatas: list[Candidata] = Field(default_factory=list)
    tiempos: str = ""
    detalle_tecnico: str | None = Field(default=None, description="Respuesta cruda del modelo (solo en error)")
    puede_aprobar: bool = False
    aprobacion: Aprobacion | None = None
    creada: str
    actualizada: str


class TextoCorregido(BaseModel):
    indice: int = Field(ge=0)
    texto: str = Field(max_length=4000)


class SolicitudCorreccion(BaseModel):
    textos: list[TextoCorregido] = Field(min_length=1, max_length=50)


class SolicitudAclaracion(BaseModel):
    nota: str = Field(max_length=4000)
    pagina: str | None = Field(default=None, max_length=300)

    @field_validator("nota")
    @classmethod
    def _nota(cls, valor: str) -> str:
        return _texto_obligatorio(valor, "La nota no puede quedar vacía.")


class SolicitudAprobacion(BaseModel):
    autor: str = Field(max_length=120)

    @field_validator("autor")
    @classmethod
    def _autor(cls, valor: str) -> str:
        return _texto_obligatorio(valor, "Escribe quién aprueba el cambio.")

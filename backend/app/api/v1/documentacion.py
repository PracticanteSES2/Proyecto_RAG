"""Documentación viva: explorar, proponer (202 + sondeo), revisar, aprobar y reindexar.

Rutas síncronas a propósito: leen archivos y FastAPI las corre en su piscina
de hilos (nunca bloquean el ciclo de eventos). Contrato:
specs/013-documentacion-web/contracts/api-documentacion.md.
"""
from fastapi import APIRouter

from backend.app.core.dependencias import DocumentacionDep
from backend.app.schemas.comunes import RESPUESTAS_ERROR
from backend.app.schemas.documentacion import (
    Documento,
    ListaGrupos,
    ListaPaginas,
    Propuesta,
    Reindexacion,
    SolicitudAclaracion,
    SolicitudAprobacion,
    SolicitudCorreccion,
    SolicitudPropuesta,
)

router = APIRouter(prefix="/documentacion", tags=["documentacion"], responses=RESPUESTAS_ERROR)


@router.get("/grupos", response_model=ListaGrupos, summary="Tableros con documentación .md")
def grupos(servicio: DocumentacionDep):
    return {"grupos": servicio.grupos()}


@router.get("/grupos/{grupo}/paginas", response_model=ListaPaginas, summary="Páginas documentadas de un tablero")
def paginas(grupo: str, servicio: DocumentacionDep):
    return servicio.paginas(grupo)


@router.get("/grupos/{grupo}/paginas/{archivo}", response_model=Documento,
            summary="Documento de una página: ficha, cuerpo e historial")
def documento(grupo: str, archivo: str, servicio: DocumentacionDep):
    return servicio.documento(grupo, archivo)


@router.post("/propuestas", response_model=Propuesta, status_code=202,
             summary="Proponer un cambio desde una nota (MedGemma, asíncrono: sondear GET /propuestas/{id})")
def proponer(solicitud: SolicitudPropuesta, servicio: DocumentacionDep):
    return servicio.crear_propuesta(solicitud.nota, solicitud.grupo, solicitud.pagina, solicitud.cambios_pbip,
                                    solicitud.autor)


@router.get("/propuestas/{propuesta_id}", response_model=Propuesta, summary="Estado y revisión de una propuesta")
def propuesta(propuesta_id: str, servicio: DocumentacionDep):
    return servicio.propuesta(propuesta_id)


@router.post("/propuestas/{propuesta_id}/operaciones", response_model=Propuesta,
             summary="Corregir el texto de las operaciones y actualizar la vista previa")
def corregir(propuesta_id: str, solicitud: SolicitudCorreccion, servicio: DocumentacionDep):
    return servicio.corregir(propuesta_id, {t.indice: t.texto for t in solicitud.textos})


@router.post("/propuestas/{propuesta_id}/aclaracion", response_model=Propuesta, status_code=202,
             summary="Aclarar la nota o la página y volver a generar la propuesta")
def aclarar(propuesta_id: str, solicitud: SolicitudAclaracion, servicio: DocumentacionDep):
    return servicio.aclarar(propuesta_id, solicitud.nota, solicitud.pagina)


@router.post("/propuestas/{propuesta_id}/descartar", response_model=Propuesta, summary="Descartar la propuesta")
def descartar(propuesta_id: str, servicio: DocumentacionDep):
    return servicio.descartar(propuesta_id)


@router.post("/propuestas/{propuesta_id}/aprobar", response_model=Propuesta,
             summary="Aprobar: guardar la página y reindexar el tablero")
def aprobar(propuesta_id: str, solicitud: SolicitudAprobacion, servicio: DocumentacionDep):
    return servicio.aprobar(propuesta_id, solicitud.autor)


@router.post("/grupos/{grupo}/reindexar", response_model=Reindexacion, status_code=202,
             summary="Reindexar (o reintentar) el RAG de un tablero")
def reindexar(grupo: str, servicio: DocumentacionDep):
    return servicio.reindexar(grupo)


@router.get("/grupos/{grupo}/reindexacion", response_model=Reindexacion,
            summary="Último estado de la reindexación de un tablero")
def reindexacion(grupo: str, servicio: DocumentacionDep):
    return servicio.reindexacion(grupo)

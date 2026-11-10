"""Conversaciones: crear, historial, exportar y enviar turnos."""
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response, status

from backend.app.core.dependencias import AjustesDep, ConversacionesDep, ServiciosDep
from backend.app.schemas.comunes import RESPUESTAS_ERROR
from backend.app.schemas.conversaciones import ConversacionCreada, Historial
from backend.app.schemas.turnos import TurnoCreado, TurnoEntrada
from backend.app.services import limites

router = APIRouter(prefix="/conversaciones", tags=["conversaciones"], responses=RESPUESTAS_ERROR)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConversacionCreada,
             summary="Crear una conversación")
async def crear(servicio: ConversacionesDep):
    return {"conversacion_id": await servicio.crear()}


@router.get("/{conversacion_id}", response_model=Historial, summary="Historial de la conversación")
async def historial(conversacion_id: str, servicio: ConversacionesDep):
    return await servicio.historial(conversacion_id)


@router.get("/{conversacion_id}/exportar", summary="Exportar la conversación (Markdown)",
            response_class=Response, responses={200: {"content": {"text/markdown": {}}}})
async def exportar(conversacion_id: str, servicio: ConversacionesDep,
                   formato: Annotated[str, Query(description="Único formato hoy: md")] = "md",
                   razonamiento: Annotated[bool, Query(description="Incluir el razonamiento de cada turno")] = True):
    texto, nombre = await servicio.exportar(conversacion_id, formato, razonamiento)
    return Response(texto, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/{conversacion_id}/turnos", status_code=status.HTTP_202_ACCEPTED, response_model=TurnoCreado,
             summary="Enviar una pregunta (o elegir una opción de la contrapregunta)")
async def crear_turno(conversacion_id: str, entrada: TurnoEntrada, request: Request, servicio: ConversacionesDep,
                      servicios: ServiciosDep, ajustes: AjustesDep,
                      x_cliente_id: Annotated[str | None, Header(description="Id de sesión del navegador")] = None,
                      x_forwarded_for: Annotated[str | None, Header(include_in_schema=False)] = None):
    ip = request.client.host if request.client else None
    sesion, ip = limites.identificar(x_cliente_id, ip, x_forwarded_for, ajustes.confiar_proxy)
    await limites.verificar_turno(servicios.almacen, ajustes, sesion, ip)
    turno_id = await servicio.crear_turno(conversacion_id, entrada.mensaje, entrada.diagnostico, entrada.opcion_id,
                                          sesion or ip)
    return {"turno_id": turno_id, "conversacion_id": conversacion_id,
            "eventos_url": f"/api/v1/turnos/{turno_id}/eventos"}

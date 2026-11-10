"""Turnos: eventos en vivo (SSE) y calificación."""
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from backend.app.core.dependencias import AjustesDep, ConversacionesDep, ServiciosDep
from backend.app.schemas.comunes import RESPUESTAS_ERROR
from backend.app.schemas.turnos import Calificacion, CalificacionGuardada, CatalogoEventosSSE
from backend.app.services.eventos import flujo_eventos

router = APIRouter(prefix="/turnos", tags=["turnos"], responses=RESPUESTAS_ERROR)

DESCRIPCION_SSE = (
    "Flujo `text/event-stream`. Eventos: `cola` {posicion, en_curso} · `progreso` {etapa, frase, t} · "
    "`espera` {nivel, frase, t} · `aviso` {motivo, texto} · `respuesta` (esquema Respuesta) · "
    "`error` {mensaje, codigo} · `fin` {}. Reconexión con `Last-Event-ID` o `?desde=`. "
    "Ver specs/006-api-backend/contracts/api-v1.md."
)


@router.get("/{turno_id}/eventos", summary="Eventos del turno (SSE)", description=DESCRIPCION_SSE,
            response_class=StreamingResponse,
            responses={200: {"model": CatalogoEventosSSE, "content": {"text/event-stream": {}}}})
async def eventos(turno_id: str, request: Request, servicio: ConversacionesDep, servicios: ServiciosDep,
                  ajustes: AjustesDep,
                  desde: Annotated[str | None, Query(description="Id del último evento recibido")] = None,
                  last_event_id: Annotated[str | None, Header()] = None):
    await servicio.turno(turno_id)  # 404 antes de abrir el flujo
    flujo = flujo_eventos(servicios.almacen, turno_id, last_event_id or desde, request.is_disconnected,
                          bloqueo_ms=ajustes.sse_bloqueo_ms, ping_s=ajustes.sse_ping_s)
    return StreamingResponse(flujo, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{turno_id}/calificacion", response_model=CalificacionGuardada, summary="Calificar una respuesta")
async def calificar(turno_id: str, calificacion: Calificacion, servicio: ConversacionesDep):
    return {"guardada": await servicio.calificar(turno_id, calificacion.valor, calificacion.comentario)}

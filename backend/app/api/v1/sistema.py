"""Capacidades, salud y diagnóstico del servidor."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.app.core.dependencias import ServiciosDep
from backend.app.schemas.sistema import Capacidades, DiagnosticoServidor, Salud
from backend.app.services import estado

router = APIRouter(tags=["sistema"])


@router.get("/capacidades", response_model=Capacidades, summary="Tableros consultables y ejemplos de preguntas")
async def capacidades(servicios: ServiciosDep):
    return await estado.capacidades(servicios.almacen)


async def _salud(servicios) -> dict:
    return await estado.salud(servicios.almacen, servicios.modo, bool(servicios.ajustes.redis_url),
                              servicios.embebido)


@router.get("/salud", response_model=Salud, summary="Salud (vida): siempre 200 si la API responde")
async def salud(servicios: ServiciosDep):
    return await _salud(servicios)


@router.get("/salud/listo", response_model=Salud, summary="Preparación: 503 si aún no puede atender turnos",
            responses={503: {"model": Salud}})
async def listo(servicios: ServiciosDep):
    datos = await _salud(servicios)
    return JSONResponse(Salud(**datos).model_dump(), status_code=200 if datos["listo"] else 503)


@router.get("/diagnostico/servidor", response_model=DiagnosticoServidor,
            summary="Diagnóstico del servidor (MedGemma, Power BI, turnos, hilos)")
async def diagnostico(servicios: ServiciosDep):
    if not servicios.ajustes.diagnostico_habilitado:
        return {"disponible": False}
    return await estado.diagnostico(servicios.almacen)

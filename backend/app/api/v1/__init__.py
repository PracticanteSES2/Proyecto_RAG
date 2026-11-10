"""API v1: routers delgados (validan, llaman a un servicio, devuelven el esquema)."""
from fastapi import APIRouter

from backend.app.api.v1 import conversaciones, sistema, turnos

router = APIRouter(prefix="/api/v1")
router.include_router(conversaciones.router)
router.include_router(turnos.router)
router.include_router(sistema.router)

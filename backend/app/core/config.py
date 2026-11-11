"""Configuración del backend: SOLO variables de entorno (pydantic-settings).

No abre ningún archivo `.env` por su cuenta: quien lance el proceso decide el
entorno (ver infra/iniciar_backend.ps1 y docs/backend.md). Ningún valor de aquí
se expone por la API (salud y diagnóstico no devuelven URLs ni secretos).
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.comun.rutas import RAIZ_PROYECTO

RAIZ_REPO = RAIZ_PROYECTO


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    # --- Redis -------------------------------------------------------------
    redis_url: str | None = Field(default=None, description="Sin valor: modo memoria (un proceso)")
    redis_prefijo: str = "rag"

    # --- Motor / trabajador ------------------------------------------------
    # auto: embebido (hilo dentro de la API) si no hay Redis; externo si lo hay.
    motor_modo: str = Field(default="auto", pattern="^(auto|embebido|externo)$")
    motor_instancias: int = Field(default=1, ge=1, le=8)
    # Raíz de los datos (data/, docs_tableros/). Por defecto la del repositorio.
    rag_raiz_datos: Path = RAIZ_REPO
    # Raíz de la documentación .md de los tableros (DOCS_MD_ROOT, la misma que
    # usa src/docs_md). Sin valor: <rag_raiz_datos>/docs_tableros.
    docs_md_root: Path | None = None
    # Secreto para firmar el estado del motor guardado en Redis (HMAC-SHA256).
    # Sin él se genera uno por proceso: el contexto no sobrevive a reinicios.
    backend_secreto: str | None = None

    # --- Tiempos de vida (s) ----------------------------------------------
    conversacion_ttl_s: int = 24 * 3600
    turno_ttl_s: int = 24 * 3600
    eventos_ttl_s: int = 3600
    turno_max_s: int = 600
    cola_max: int = Field(default=200, ge=1)

    # --- Caché de respuestas ----------------------------------------------
    cache_habilitada: bool = True
    cache_ttl_s: int = 15 * 60

    # --- Límite de peticiones (turnos por ventana) ------------------------
    limite_turnos: int = 12
    limite_turnos_ip: int = 120
    limite_ventana_s: int = 60
    confiar_proxy: bool = False  # usar X-Forwarded-For solo detrás de un proxy propio

    # --- HTTP ---------------------------------------------------------------
    cors_origenes: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    diagnostico_habilitado: bool = True

    backend_log_nivel: str = "INFO"
    # Ejemplos fijos para el estado vacío del chat (JSON); vacío = se generan del catálogo.
    capacidades_ejemplos: list[str] = []

    # --- Ritmos (s) ---------------------------------------------------------
    latido_s: float = 5.0
    sse_ping_s: float = 15.0
    sse_bloqueo_ms: int = 1000

    @property
    def modo_embebido(self) -> bool:
        if self.motor_modo == "embebido":
            return True
        if self.motor_modo == "externo":
            return False
        return not self.redis_url


@lru_cache(maxsize=1)
def obtener_ajustes() -> Ajustes:
    return Ajustes()

"""Límite de peticiones por cliente (ventana deslizante en el almacén).

Sin usuarios ni login: el cliente es el identificador de sesión del navegador
(`X-Cliente-Id`) y, además, la IP (con un límite más alto, porque varias
personas pueden compartir IP detrás de un proxy). Rotar el identificador no
evita el límite por IP.
"""
from __future__ import annotations

import re

from backend.app.core import errores

_CLIENTE_VALIDO = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def identificar(cliente_id: str | None, ip: str | None, reenviada: str | None,
                confiar_proxy: bool) -> tuple[str | None, str]:
    """(id de sesión válido o None, ip)."""
    if confiar_proxy and reenviada:
        ip = reenviada.split(",")[0].strip() or ip
    sesion = cliente_id if cliente_id and _CLIENTE_VALIDO.match(cliente_id) else None
    return sesion, (ip or "desconocida")


async def verificar_turno(almacen, ajustes, sesion: str | None, ip: str) -> None:
    """Lanza 429 si el cliente superó el límite de turnos en la ventana."""
    ventana = ajustes.limite_ventana_s
    if sesion:
        espera = await almacen.registrar_peticion(f"sesion:{sesion}", ajustes.limite_turnos, ventana)
        if espera is not None:
            raise errores.demasiadas_peticiones(espera)
    limite_ip = ajustes.limite_turnos_ip if sesion else ajustes.limite_turnos
    espera = await almacen.registrar_peticion(f"ip:{ip}", limite_ip, ventana)
    if espera is not None:
        raise errores.demasiadas_peticiones(espera)

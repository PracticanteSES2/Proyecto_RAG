"""Proceso trabajador: dueño del motor (Qdrant local, MiniLM, ADOMD, MedGemma).

    python -m backend.worker

Requiere REDIS_URL (la API y este proceso se comunican por Redis). Debe haber
UNO solo por carpeta de Qdrant: Qdrant local no admite dos procesos. Sin Redis
no hace falta: la API corre el motor en sus propios hilos (modo embebido).
"""
from __future__ import annotations

import logging
import signal
import sys

from backend.app.core.config import obtener_ajustes
from backend.app.core.registro import configurar_registro
from backend.app.services.sistema import crear_almacenes, crear_trabajador

LOG = logging.getLogger("backend.worker")


def main() -> int:
    ajustes = obtener_ajustes()
    configurar_registro(ajustes.backend_log_nivel)
    if not ajustes.redis_url:
        LOG.error("REDIS_URL no está definido: sin Redis el motor corre dentro de la API "
                  "(uvicorn backend.app.main:app); este proceso no hace falta.")
        return 2
    _, almacen_trabajador, modo = crear_almacenes(ajustes)
    if modo != "redis":
        LOG.error("Redis no responde en REDIS_URL: el trabajador no puede atender la cola.")
        return 3
    LOG.info("Armando el motor (%d instancia(s))…", ajustes.motor_instancias)
    trabajador = crear_trabajador(ajustes, almacen_trabajador)
    trabajador.iniciar()

    def parar(*_):
        LOG.info("Deteniendo el trabajador…")
        trabajador.detener()

    signal.signal(signal.SIGINT, parar)
    signal.signal(signal.SIGTERM, parar)
    trabajador.esperar()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Configuración de logging del proyecto (docs/ARQUITECTURA.md §7).

La librería (``src/``) NO configura logging ni usa ``print``: cada módulo hace
``logger = logging.getLogger(__name__)`` y registra. Quien arranca un proceso decide qué se ve:

* CLIs (``tools/``, bloques ``__main__``): ``configurar_registro()`` al empezar. Los mensajes ``INFO`` salen
  por stdout tal cual (sin prefijos), así que el progreso de los constructores se ve igual que cuando eran
  ``print``.
* App/servidor: su propia configuración (o ninguna: entonces solo se ven ``WARNING`` y superiores en stderr,
  que es el comportamiento por defecto de ``logging``).

``PROYECTO_LOG_NIVEL`` (DEBUG, INFO, WARNING…) cambia el nivel sin tocar código.
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager

_MARCA = "_proyecto_rag"


class _SalidaActual(logging.StreamHandler):
    """Escribe en el ``sys.stdout`` de cada momento (respeta ``contextlib.redirect_stdout``, como ``print``)."""

    def __init__(self):
        super().__init__(sys.stdout)

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, _valor):
        pass


def configurar_registro(nivel: int | str | None = None, *, formato: str = "%(message)s", flujo=None) -> None:
    """Un manejador en la raíz hacia ``flujo`` (stdout por defecto). Idempotente: no duplica manejadores."""
    nivel = nivel or os.environ.get("PROYECTO_LOG_NIVEL") or logging.INFO
    if isinstance(nivel, str):
        nivel = logging.getLevelName(nivel.strip().upper())
        if not isinstance(nivel, int):
            nivel = logging.INFO
    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    for manejador in raiz.handlers:
        if getattr(manejador, _MARCA, False):
            manejador.setLevel(nivel)
            return
    manejador = logging.StreamHandler(flujo) if flujo is not None else _SalidaActual()
    manejador.setFormatter(logging.Formatter(formato))
    manejador.setLevel(nivel)
    setattr(manejador, _MARCA, True)
    raiz.addHandler(manejador)


@contextmanager
def mensajes_de(nombres, *, visibles: bool):
    """Durante el bloque, los registros ``INFO`` y superiores de los loggers ``nombres`` salen por stdout
    (``visibles=True``, como los ``print`` de antes) o se descartan (``visibles=False``, como un
    ``redirect_stdout`` a la nada). Al salir se restauran niveles y manejadores."""
    manejador = _SalidaActual() if visibles else logging.NullHandler()
    if visibles:
        manejador.setFormatter(logging.Formatter("%(message)s"))
    previos = []
    for nombre in nombres:
        logger = logging.getLogger(nombre)
        previos.append((logger, logger.level, logger.propagate))
        logger.addHandler(manejador)
        if visibles and logger.getEffectiveLevel() > logging.INFO:
            logger.setLevel(logging.INFO)
        if not visibles:
            logger.propagate = False
    try:
        yield
    finally:
        for logger, nivel, propaga in previos:
            logger.removeHandler(manejador)
            logger.setLevel(nivel)
            logger.propagate = propaga


def consola_utf8() -> None:
    """stdout y stderr en UTF-8 con reemplazo (la consola de Windows viene en cp1252). Sin efecto si no se puede."""
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            try:
                flujo.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                # Flujos redirigidos (pruebas, servicios) no siempre admiten reconfigurar: se dejan como están.
                logging.getLogger(__name__).debug("no se pudo pasar %r a UTF-8", flujo, exc_info=True)

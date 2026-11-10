"""Configuración del logging del backend (API y trabajador)."""
from __future__ import annotations

import logging

FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configurar_registro(nivel: str = "INFO") -> None:
    nivel = (nivel or "INFO").upper()
    raiz = logging.getLogger()
    if not raiz.handlers:
        logging.basicConfig(level=nivel, format=FORMATO)
    else:
        raiz.setLevel(nivel)

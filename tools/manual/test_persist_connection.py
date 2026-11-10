# Script manual (no es una prueba automática). Ejecutar desde la raíz:
#   .venv/Scripts/python.exe -X utf8 tools/manual/test_persist_connection.py
import sys as _sys
from pathlib import Path as _Path
_RAIZ = str(_Path(__file__).resolve().parents[2])
if _RAIZ not in _sys.path:
    _sys.path.insert(0, _RAIZ)

from src.providers.powerbi_provider import (
    PowerBIProvider
)


provider = PowerBIProvider()


semantic_model = (
    "TABLERO DE ATENCIONES "
    "INSTITUCIONALES"
)


try:

    for number in range(
        1,
        4
    ):

        print(
            f"\nCONSULTA {number}"
        )

        dax = f"""
EVALUATE
ROW(
    "Numero",
    {number}
)
"""

        result = (
            provider.execute_dax(
                dax=dax,
                semantic_model=
                    semantic_model
            )
        )

        print(
            result
        )

        print(
            "Conexiones abiertas:",
            provider.connection_count()
        )


finally:

    provider.close()
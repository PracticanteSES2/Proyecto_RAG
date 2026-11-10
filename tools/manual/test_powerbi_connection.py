# Script manual (no es una prueba automática). Ejecutar desde la raíz:
#   .venv/Scripts/python.exe -X utf8 tools/manual/test_powerbi_connection.py
import sys as _sys
from pathlib import Path as _Path
_RAIZ = str(_Path(__file__).resolve().parents[2])
if _RAIZ not in _sys.path:
    _sys.path.insert(0, _RAIZ)

from src.providers.powerbi_provider import (
    PowerBIProvider
)


provider = PowerBIProvider()


dax = """
EVALUATE
ROW(
    "Conexion",
    1
)
"""


print(
    "Intentando conexión con Power BI..."
)


result = provider.execute_dax(
    dax
)


print(
    "\nRESULTADO:"
)

print(
    result
)
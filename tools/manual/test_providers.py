# Script manual (no es una prueba automática). Ejecutar desde la raíz:
#   .venv/Scripts/python.exe -X utf8 tools/manual/test_providers.py
import sys as _sys
from pathlib import Path as _Path
_RAIZ = str(_Path(__file__).resolve().parents[2])
if _RAIZ not in _sys.path:
    _sys.path.insert(0, _RAIZ)

from src.providers.powerbi_provider import (
    PowerBIProvider
)


provider = PowerBIProvider()


# ============================================================
# MODELO QUE QUEREMOS CONSULTAR
# ============================================================

semantic_model = (
    "TABLERO DE ATENCIONES "
    "INSTITUCIONALES"
)


# ============================================================
# CONSULTA REAL
# ============================================================

dax = """
EVALUATE
ROW(
    "Resultado",
    [PROM_CIRUGÍAS]
)
"""


print(
    "\nEjecutando medida real..."
)


result = provider.execute_dax(
    dax=dax,
    semantic_model=semantic_model
)


print(
    "\nRESULTADO POWER BI:"
)

print(
    result
)
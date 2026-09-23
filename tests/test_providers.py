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
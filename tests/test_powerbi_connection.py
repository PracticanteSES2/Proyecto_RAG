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
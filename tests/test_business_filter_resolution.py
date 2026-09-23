from pathlib import Path

from src.semantic.business_filter_resolver import (
    BusinessFilterResolver
)

from src.providers.powerbi_provider import (
    PowerBIProvider
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


TECHNICAL_CATALOG = (
    PROJECT_ROOT
    / "data"
    / "catalog"
    / "tablero_de_atenciones_institucionales_rag.json"
)


provider = PowerBIProvider()


resolver = BusinessFilterResolver(
    TECHNICAL_CATALOG,
    provider
)


question = (
    "¿Cuántas cirugías de "
    "Nueva EPS hubo en "
    "agosto de 2026?"
)


result = resolver.resolve(

    question=question,

    dashboard="CIRUGÍAS",

    semantic_model=(
        "TABLERO DE ATENCIONES "
        "INSTITUCIONALES"
    )
)


print(
    "\nPREGUNTA:"
)

print(
    question
)


print(
    "\nFILTROS DE NEGOCIO:"
)

print(
    result
)
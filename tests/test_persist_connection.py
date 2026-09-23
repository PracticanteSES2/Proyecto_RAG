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
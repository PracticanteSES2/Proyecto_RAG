from pathlib import Path

from src.providers.powerbi_provider import (
    PowerBIProvider
)

from src.semantic.business_filter_resolver import (
    BusinessFilterResolver
)


# ============================================================
# RUTAS
# ============================================================

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


SEMANTIC_MODEL = (
    "TABLERO DE ATENCIONES INSTITUCIONALES"
)

DASHBOARD = "CIRUGÍAS"


# ============================================================
# PRUEBA
# ============================================================

def main():

    provider = PowerBIProvider()

    resolver = BusinessFilterResolver(
        TECHNICAL_CATALOG,
        provider
    )

    try:

        questions = [

            (
                "¿Cuál fue el promedio de cirugías "
                "de Nueva EPS en agosto de 2026?"
            ),

            (
                "¿Cuántas cirugías de ortopedia "
                "se realizaron?"
            ),

            (
                "¿Cuántas cirugías realizó "
                "determinado cirujano?"
            ),
        ]


        for index, question in enumerate(
            questions,
            start=1
        ):

            print(
                "\n"
                "============================================"
            )

            print(
                f"PRUEBA {index}"
            )

            print(
                "\nPREGUNTA:"
            )

            print(
                question
            )


            result = resolver.resolve(

                question=question,

                dashboard=DASHBOARD,

                semantic_model=
                    SEMANTIC_MODEL
            )


            print(
                "\nFILTROS RESUELTOS:"
            )

            print(
                result
            )


            print(
                "\nCONEXIONES POWER BI ABIERTAS:"
            )

            print(
                provider.connection_count()
            )


            print(
                "\nDOMINIOS PRECARGADOS:"
            )

            print(
                resolver.domain_cache_loaded
            )


            print(
                "\nELEMENTOS EN VALUE CACHE:"
            )

            print(
                len(
                    resolver.value_cache
                )
            )


    finally:

        provider.close()


if __name__ == "__main__":
    main()
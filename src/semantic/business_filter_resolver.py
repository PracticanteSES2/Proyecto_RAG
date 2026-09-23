import json
import re
import unicodedata


class BusinessFilterResolver:

    CONCEPTS = {

        "aseguradora": [
            "asegurador",
            "aseguradora",
            "eps"
        ],

        "especialidad": [
            "especialidad"
        ],

        "cirujano": [
            "cirujano"
        ],

        "tipo_cirugia": [
            "tipo",
            "tipo cirugia",
            "tipo de cirugia"
        ]
    }


    def __init__(
        self,
        technical_catalog_path,
        powerbi_provider
    ):

        with open(
            technical_catalog_path,
            "r",
            encoding="utf-8"
        ) as file:

            self.catalog = json.load(
                file
            )

        self.powerbi_provider = (
            powerbi_provider
        )

        # Cache para no pedir los mismos
        # valores a Power BI continuamente.
        self.value_cache = {}
        self.domain_cache_loaded = set()

        self.columns = (
            self._build_column_index()
        )


    def preload_domains(
        self,
        semantic_model,
        dashboard
    ):
        """
        Precarga los valores de los filtros de negocio
        una sola vez por modelo/dashboard.
        """

        cache_key = (
            semantic_model,
            dashboard
        )

        if (
            cache_key
            in self.domain_cache_loaded
        ):
            return


        for concept in self.CONCEPTS:

            column = self._find_column(
                concept,
                dashboard
            )

            if not column:
                continue


            values = self._get_values(
                semantic_model,
                column["table"],
                column["column"]
            )


            self.value_cache[
                (
                    semantic_model,
                    column["table"],
                    column["column"]
                )
            ] = values


        self.domain_cache_loaded.add(
            cache_key
        )

    # ========================================================
    # NORMALIZACIÓN
    # ========================================================

    def _normalize(
        self,
        value
    ):

        if not value:
            return ""

        value = str(
            value
        ).lower()

        value = "".join(
            char
            for char
            in unicodedata.normalize(
                "NFD",
                value
            )
            if unicodedata.category(
                char
            ) != "Mn"
        )

        value = re.sub(
            r"[^a-z0-9\s]",
            " ",
            value
        )

        value = re.sub(
            r"\s+",
            " ",
            value
        )

        return value.strip()


    # ========================================================
    # ÍNDICE DE COLUMNAS
    # ========================================================

    def _build_column_index(
        self
    ):

        result = []

        for table in self.catalog.get(
            "tables",
            []
        ):

            table_name = table.get(
                "name"
            )

            if not table_name:
                continue

            for column in table.get(
                "columns",
                []
            ):

                column_name = (
                    column.get(
                        "name"
                    )
                )

                if not column_name:
                    continue

                result.append({

                    "table":
                        table_name,

                    "column":
                        column_name,

                    "normalized_table":
                        self._normalize(
                            table_name
                        ),

                    "normalized_column":
                        self._normalize(
                            column_name
                        ),

                    "data_type":
                        column.get(
                            "data_type"
                        )
                })

        return result


    # ========================================================
    # BUSCAR COLUMNA DEL CONCEPTO
    # ========================================================

    def _find_column(
        self,
        concept,
        dashboard
    ):

        aliases = (
            self.CONCEPTS.get(
                concept,
                []
            )
        )

        normalized_dashboard = (
            self._normalize(
                dashboard
            )
        )

        candidates = []


        for column in self.columns:

            column_name = column[
                "normalized_column"
            ]

            table_name = column[
                "normalized_table"
            ]

            score = 0


            for alias in aliases:

                normalized_alias = (
                    self._normalize(
                        alias
                    )
                )

                if (
                    column_name
                    == normalized_alias
                ):

                    score += 100

                elif (
                    normalized_alias
                    in column_name
                ):

                    score += 50


            # Preferir tabla del dashboard
            if (
                table_name
                == normalized_dashboard
            ):

                score += 80

            elif (
                normalized_dashboard
                in table_name
                or table_name
                in normalized_dashboard
            ):

                score += 40


            if score > 0:

                candidates.append({
                    **column,
                    "score": score
                })


        candidates.sort(
            key=lambda item:
                item["score"],
            reverse=True
        )


        if not candidates:
            return None


        return candidates[0]


    # ========================================================
    # ESCAPAR IDENTIFICADORES DAX
    # ========================================================

    def _table_reference(
        self,
        table
    ):

        table = str(
            table
        ).replace(
            "'",
            "''"
        )

        return f"'{table}'"


    def _column_reference(
        self,
        column
    ):

        column = str(
            column
        ).replace(
            "]",
            "]]"
        )

        return f"[{column}]"


    # ========================================================
    # VALORES REALES DESDE POWER BI
    # ========================================================

    def _get_values(
        self,
        semantic_model,
        table,
        column
    ):

        cache_key = (
            semantic_model,
            table,
            column
        )


        if (
            cache_key
            in self.value_cache
        ):

            return self.value_cache[
                cache_key
            ]


        table_ref = (
            self._table_reference(
                table
            )
        )

        column_ref = (
            self._column_reference(
                column
            )
        )


        dax = f"""
EVALUATE
TOPN(
    2000,
    FILTER(
        SELECTCOLUMNS(
            VALUES(
                {table_ref}{column_ref}
            ),
            "Value",
            {table_ref}{column_ref}
        ),
        NOT ISBLANK([Value])
    ),
    [Value],
    ASC
)
"""


        result = (
            self.powerbi_provider
            .execute_dax(
                dax=dax,
                semantic_model=
                    semantic_model
            )
        )


        if (
            result.get("status")
            != "success"
        ):

            return []


        values = []


        for row in result.get(
            "rows",
            []
        ):

            if not row:
                continue

            value = next(
                iter(
                    row.values()
                ),
                None
            )

            if value is not None:

                values.append(
                    str(value)
                )


        self.value_cache[
            cache_key
        ] = values


        return values


    # ========================================================
    # ENCONTRAR VALOR MENCIONADO
    # ========================================================

    def _match_value(
        self,
        question,
        values
    ):

        normalized_question = (
            self._normalize(
                question
            )
        )

        matches = []


        for value in values:

            normalized_value = (
                self._normalize(
                    value
                )
            )

            if (
                len(normalized_value)
                < 3
            ):
                continue


            if (
                normalized_value
                in normalized_question
            ):

                matches.append({

                    "value":
                        value,

                    "normalized":
                        normalized_value,

                    "length":
                        len(
                            normalized_value
                        )
                })


        if not matches:
            return None


        # Preferimos el valor más específico.
        matches.sort(
            key=lambda item:
                item["length"],
            reverse=True
        )


        return matches[0][
            "value"
        ]


    # ========================================================
    # RESOLVER
    # ========================================================

    def resolve(
        self,
        question,
        dashboard,
        semantic_model
    ):

        self.preload_domains(
            semantic_model,
            dashboard
        )

        filters = []


        for concept in self.CONCEPTS:

            column = (
                self._find_column(
                    concept,
                    dashboard
                )
            )


            if not column:
                continue


            values = (
                self._get_values(
                    semantic_model,
                    column["table"],
                    column["column"]
                )
            )


            matched_value = (
                self._match_value(
                    question,
                    values
                )
            )


            if not matched_value:
                continue


            filters.append({

                "status":
                    "resolved",

                "concept":
                    concept,

                "table":
                    column["table"],

                "column":
                    column["column"],

                "operator":
                    "=",

                "value":
                    matched_value,

                "source":
                    "powerbi_value"
            })


        return {

            "status":
                "resolved",

            "filters":
                filters
        }
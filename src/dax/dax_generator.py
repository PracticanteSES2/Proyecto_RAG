class DAXGenerator:

    def __init__(
        self,
        result_alias="Resultado"
    ):
        self.result_alias = result_alias


    # ========================================================
    # ESCAPAR IDENTIFICADORES DAX
    # ========================================================

    def _escape_table(self, table_name):
        """
        Convierte:
        Calendario

        en:
        'Calendario'

        También protege nombres con apostrofes.
        """

        table_name = str(
            table_name
        ).replace(
            "'",
            "''"
        )

        return f"'{table_name}'"


    def _escape_column(self, column_name):
        """
        Convierte:
        Año

        en:
        [Año]
        """

        column_name = str(
            column_name
        ).replace(
            "]",
            "]]"
        )

        return f"[{column_name}]"


    def _escape_measure(self, measure_name):
        """
        Convierte:
        PROM_CIRUGÍAS

        en:
        [PROM_CIRUGÍAS]
        """

        measure_name = str(
            measure_name
        ).replace(
            "]",
            "]]"
        )

        return f"[{measure_name}]"


    # ========================================================
    # FORMATEAR VALORES
    # ========================================================

    def _format_value(self, value):

        # Booleanos
        if isinstance(value, bool):

            return (
                "TRUE()"
                if value
                else "FALSE()"
            )

        # Números
        if isinstance(
            value,
            (int, float)
        ):

            return str(value)

        # Strings
        value = str(value).replace(
            '"',
            '""'
        )

        return f'"{value}"'


    # ========================================================
    # CONSTRUIR UN FILTRO
    # ========================================================

    def _build_filter_expression(
        self,
        filter_data
    ):

        table = (
            self._escape_table(
                filter_data["table"]
            )
        )

        column = (
            self._escape_column(
                filter_data["column"]
            )
        )

        operator = (
            filter_data.get(
                "operator",
                "="
            )
        )

        value = (
            self._format_value(
                filter_data["value"]
            )
        )

        expression = (
            f"{table}{column} "
            f"{operator} "
            f"{value}"
        )

        # KEEPFILTERS evita reemplazar
        # innecesariamente filtros existentes.
        return (
            f"KEEPFILTERS("
            f"{expression}"
            f")"
        )


    # ========================================================
    # GENERAR CONSULTA
    # ========================================================

    def generate(
        self,
        metric_result,
        filter_result
    ):

        # ----------------------------------------------------
        # VALIDAR MÉTRICA
        # ----------------------------------------------------

        if (
            metric_result.get(
                "status"
            )
            != "resolved"
        ):

            return {
                "status":
                    "cannot_generate",

                "reason":
                    "metric_not_resolved",

                "dax":
                    None
            }


        # ----------------------------------------------------
        # VALIDAR FILTROS
        # ----------------------------------------------------

        if (
            filter_result.get(
                "status"
            )
            != "resolved"
        ):

            return {
                "status":
                    "cannot_generate",

                "reason":
                    "filters_not_resolved",

                "dax":
                    None
            }


        measure_name = (
            metric_result[
                "measure"
            ]
        )

        measure_reference = (
            self._escape_measure(
                measure_name
            )
        )


        # ----------------------------------------------------
        # CONSTRUIR FILTROS
        # ----------------------------------------------------

        filters = (
            filter_result.get(
                "filters",
                []
            )
        )

        filter_expressions = [

            self._build_filter_expression(
                filter_data
            )

            for filter_data
            in filters
        ]


        # ----------------------------------------------------
        # CALCULATE
        # ----------------------------------------------------

        if filter_expressions:

            formatted_filters = (
                ",\n            ".join(
                    filter_expressions
                )
            )

            calculation = f"""CALCULATE(
            {measure_reference},
            {formatted_filters}
        )"""

        else:

            calculation = (
                measure_reference
            )


        # ----------------------------------------------------
        # CONSULTA DAX COMPLETA
        # ----------------------------------------------------

        dax = f"""EVALUATE
ROW(
    "{self.result_alias}",
    {calculation}
)"""


        return {

            "status":
                "generated",

            "measure":
                measure_name,

            "dashboard":
                metric_result.get(
                    "dashboard"
                ),

            "filters":
                filters,

            "dax":
                dax
        }
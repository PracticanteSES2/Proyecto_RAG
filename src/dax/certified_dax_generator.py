class CertifiedDAXGenerator:
    """
    Genera DAX únicamente desde expresiones certificadas
    almacenadas en el registro local.

    La expresión nunca proviene del texto del usuario.
    """

    def _quote_identifier(self, value):
        return str(value).replace(
            "'",
            "''",
        )

    def _format_value(self, value):
        if isinstance(
            value,
            bool,
        ):
            return (
                "TRUE()"
                if value
                else "FALSE()"
            )

        if isinstance(
            value,
            (int, float),
        ):
            return str(value)

        escaped = str(value).replace(
            '"',
            '""',
        )

        return f'"{escaped}"'

    def _build_filter(self, item):
        table = item.get("table")
        column = item.get("column")
        operator = item.get(
            "operator",
            "=",
        )
        value = item.get("value")

        if not table or not column:
            return None

        if operator != "=":
            return None

        table = self._quote_identifier(
            table
        )

        column = str(column).replace(
            "]",
            "]]",
        )

        return (
            "KEEPFILTERS("
            f"'{table}'[{column}] "
            f"= {self._format_value(value)}"
            ")"
        )

    def generate(
        self,
        metric_result,
        filter_result,
    ):
        expression = metric_result.get(
            "expression"
        )

        if not expression:
            return {
                "status": "not_generated",
                "reason":
                    "certified_expression_missing",
            }

        filters = []

        for item in filter_result.get(
            "filters",
            [],
        ):
            dax_filter = (
                self._build_filter(item)
            )

            if dax_filter:
                filters.append(
                    dax_filter
                )

        calculate_args = [
            expression,
            *filters,
        ]

        calculate_body = (
            ",\n        ".join(
                calculate_args
            )
        )

        dax = (
            "EVALUATE\n"
            "ROW(\n"
            '    "Resultado",\n'
            "    CALCULATE(\n"
            f"        {calculate_body}\n"
            "    )\n"
            ")"
        )

        return {
            "status": "generated",
            "dax": dax,
            "metric_source":
                "certified_visual",
        }

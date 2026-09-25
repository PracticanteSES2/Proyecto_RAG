class MasterMetricDAXGenerator:
    """
    Genera una consulta escalar desde una métrica APROBADA
    del master_metrics.json.

    IMPORTANTE:
    - La expresión DAX viene del catálogo local.
    - Nunca se construye una expresión desde texto libre del usuario.
    - Los filtros sí se agregan de manera controlada.
    """

    def _quote_table(self, value):
        return str(value).replace(
            "'",
            "''",
        )

    def _quote_column(self, value):
        return str(value).replace(
            "]",
            "]]",
        )

    def _format_value(self, value):

        if isinstance(value, bool):
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

        table = item.get(
            "table"
        )

        column = item.get(
            "column"
        )

        operator = item.get(
            "operator",
            "=",
        )

        value = item.get(
            "value"
        )

        if not table or not column:
            return None

        # Por ahora solo ejecutamos igualdad.
        if operator != "=":
            return None

        table = self._quote_table(
            table
        )

        column = self._quote_column(
            column
        )

        return (
            "KEEPFILTERS("
            f"'{table}'[{column}] "
            f"= {self._format_value(value)}"
            ")"
        )

    def generate(
        self,
        metric,
        filter_result,
    ):

        if (
            metric.get(
                "validation_status"
            )
            != "approved"
        ):
            return {
                "status":
                    "not_generated",
                "reason":
                    "metric_not_approved",
            }

        expression = metric.get(
            "dax_expression"
        )

        if not expression:
            return {
                "status":
                    "not_generated",
                "reason":
                    "dax_expression_missing",
            }

        filters = []

        for item in filter_result.get(
            "filters",
            [],
        ):

            dax_filter = (
                self._build_filter(
                    item
                )
            )

            if dax_filter:
                filters.append(
                    dax_filter
                )

        calculate_args = [
            expression,
            *filters,
        ]

        body = (
            ",\n        ".join(
                calculate_args
            )
        )

        dax = (
            "EVALUATE\n"
            "ROW(\n"
            '    "Resultado",\n'
            "    CALCULATE(\n"
            f"        {body}\n"
            "    )\n"
            ")"
        )

        return {
            "status":
                "generated",
            "dax":
                dax,
            "source_type":
                metric.get(
                    "source_type"
                ),
            "metric_id":
                metric.get(
                    "metric_id"
                ),
        }

class QueryPlanDAXGenerator:

    def _table_ref(self, table):
        return "'" + str(table).replace("'", "''") + "'"

    def _column_ref(self, column):
        return "[" + str(column).replace("]", "]]" ) + "]"

    def _column_expression(self, table, column):
        return f"{self._table_ref(table)}{self._column_ref(column)}"

    def _string_literal(self, value):
        return '"' + str(value).replace('"', '""') + '"'

    def _categorical_filter(self, item):
        column = self._column_expression(item["table"], item["column"])
        value = item.get("value")
        return f"TREATAS({{{self._string_literal(value)}}}, {column})"

    def _date_filter(self, item):
        column = self._column_expression(item["table"], item["column"])
        year = item.get("year")
        month = item.get("month")

        if year and month:
            if month == 12:
                next_year, next_month = year + 1, 1
            else:
                next_year, next_month = year, month + 1
            return (
                f"FILTER(ALL({column}), "
                f"{column} >= DATE({year}, {month}, 1) && "
                f"{column} < DATE({next_year}, {next_month}, 1))"
            )

        if year:
            return (
                f"FILTER(ALL({column}), "
                f"{column} >= DATE({year}, 1, 1) && "
                f"{column} < DATE({year + 1}, 1, 1))"
            )

        return None

    def _filter_expressions(self, plan):
        result = []
        for item in plan.get("filters", []) or []:
            expression = None
            if item.get("type") == "categorical":
                expression = self._categorical_filter(item)
            elif item.get("type") == "date_range":
                expression = self._date_filter(item)
            if expression:
                result.append(expression)
        return result

    def generate(self, plan):
        if plan.get("status") != "ready":
            return {"status": "rejected", "reason": "query_plan_not_ready"}

        metric = plan.get("metric", {})
        expression = metric.get("dax_expression")
        if not expression:
            return {"status": "rejected", "reason": "metric_without_dax_expression"}
        if metric.get("validation_status") != "approved":
            return {"status": "rejected", "reason": "metric_not_approved"}

        filters = self._filter_expressions(plan)

        if plan.get("mode") == "grouped":
            groups = [
                self._column_expression(item["table"], item["column"])
                for item in plan.get("group_by", []) or []
            ]
            if not groups:
                return {"status": "rejected", "reason": "grouped_without_dimensions"}

            arguments = [*groups, *filters, '"__value"', expression]
            dax = (
                "EVALUATE\n"
                "SUMMARIZECOLUMNS(\n    "
                + ",\n    ".join(arguments)
                + "\n)\n"
                "ORDER BY [__value] DESC"
            )
            return {"status": "generated", "mode": "grouped", "dax": dax}

        calculate_args = [expression, *filters]
        if len(calculate_args) == 1:
            value_expression = expression
        else:
            value_expression = (
                "CALCULATE(\n        "
                + ",\n        ".join(calculate_args)
                + "\n    )"
            )

        dax = (
            "EVALUATE\n"
            "ROW(\n"
            '    "__value",\n'
            f"    {value_expression}\n"
            ")"
        )
        return {"status": "generated", "mode": "scalar", "dax": dax}

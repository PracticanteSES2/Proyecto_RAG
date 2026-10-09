import re


class QueryPlanDAXGenerator:

    def _table_ref(self, table):
        return "'" + str(table).replace("'", "''") + "'"

    def _column_ref(self, column):
        return "[" + str(column).replace("]", "]]" ) + "]"

    def _column_expression(self, table, column):
        return f"{self._table_ref(table)}{self._column_ref(column)}"

    def _string_literal(self, value):
        if value is None:
            return '""'
        return '"' + str(value).replace('"', '""') + '"'

    def _number_literal(self, value):
        """Devuelve el número como literal DAX, o None si no es numérico."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return repr(value) if isinstance(value, float) and not value.is_integer() else str(int(value))
        text = str(value).strip()
        if re.fullmatch(r"-?\d+", text):
            return str(int(text))
        if re.fullmatch(r"-?\d+\.\d+", text):
            return text
        return None

    def _value_literal(self, value, data_type=None):
        """Literal DAX según el tipo de la columna: números sin comillas, texto entre comillas."""
        if value is None:
            return "BLANK()"
        kind = str(data_type or "").lower()
        if kind == "number" or (not kind and isinstance(value, (int, float)) and not isinstance(value, bool)):
            literal = self._number_literal(value)
            if literal is not None:
                return literal
        return self._string_literal(value)

    def _categorical_filter(self, item):
        column = self._column_expression(item["table"], item["column"])
        literal = self._value_literal(item.get("value"), item.get("data_type"))
        return f"TREATAS({{{literal}}}, {column})"

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

        if month:
            # Mes sin año: todos los años de ese mes (el plan lo declara en notes).
            return f"FILTER(ALL({column}), MONTH({column}) = {int(month)})"

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

    # ---------------- ranking (orden y límite) ----------------
    def generate_ranked(self, plan):
        """Agrupación ordenada y, si se pidió, limitada con TOPN.

        plan["ranking"] = {"direction": "desc" | "asc", "limit": n | None}.
        Sin ranking (o sin agrupación) equivale a generate().
        """
        result = self.generate(plan)
        ranking = plan.get("ranking") or {}
        if result.get("status") != "generated" or result.get("mode") != "grouped" or not ranking:
            return result
        dax = result["dax"]
        head = "EVALUATE\n"
        order_at = dax.rfind("\nORDER BY")
        if not dax.startswith(head) or order_at < 0:
            return result
        table = dax[len(head):order_at]
        direction = "ASC" if ranking.get("direction") == "asc" else "DESC"
        limit = ranking.get("limit")
        if limit:
            table = (
                "TOPN(\n    "
                f"{int(limit)},\n    "
                + table.replace("\n", "\n    ")
                + f",\n    [__value], {direction}\n)"
            )
        return {
            **result,
            "dax": f"{head}{table}\nORDER BY [__value] {direction}",
            "ranking": {"direction": ranking.get("direction"), "limit": limit},
        }

    # ---------------- participación (% del total) ----------------
    def generate_share(self, plan):
        """Participación de un valor de dimensión sobre el total del período.

        Numerador: métrica con todos los filtros del plan.
        Denominador: misma métrica sin filtro sobre la dimensión (REMOVEFILTERS)
        pero conservando período y demás filtros. Con group_by devuelve una
        fila por grupo (participación de cada grupo sobre el total).
        """
        dimension = plan.get("share_dimension") or {}
        if plan.get("status") != "ready" or not dimension.get("column"):
            return {"status": "rejected", "reason": "share_without_dimension"}

        metric = plan.get("metric", {})
        expression = metric.get("dax_expression")
        if not expression:
            return {"status": "rejected", "reason": "metric_without_dax_expression"}
        if metric.get("validation_status") != "approved":
            return {"status": "rejected", "reason": "metric_not_approved"}

        column = self._column_expression(dimension["table"], dimension["column"])
        remove = f"REMOVEFILTERS({column})"

        if dimension.get("scope") == "group":
            arguments = [
                column, *self._filter_expressions(plan), '"__value"',
                f"DIVIDE({expression}, CALCULATE({expression}, {remove}))",
            ]
            dax = (
                "EVALUATE\n"
                "SUMMARIZECOLUMNS(\n    "
                + ",\n    ".join(arguments)
                + "\n)\n"
                "ORDER BY [__value] DESC"
            )
            return {"status": "generated", "mode": "grouped", "dax": dax}

        def misma_dimension(item):
            return (
                item.get("type") == "categorical"
                and str(item.get("table")).casefold() == str(dimension["table"]).casefold()
                and str(item.get("column")).casefold() == str(dimension["column"]).casefold()
            )

        otros = self._filter_expressions({
            "filters": [i for i in plan.get("filters", []) or [] if not misma_dimension(i)]
        })
        numerador = ",\n            ".join([expression, *self._filter_expressions(plan)])
        denominador = ",\n            ".join([expression, remove, *otros])
        dax = (
            "EVALUATE\n"
            "ROW(\n"
            '    "__value",\n'
            "    DIVIDE(\n"
            f"        CALCULATE(\n            {numerador}\n        ),\n"
            f"        CALCULATE(\n            {denominador}\n        )\n"
            "    )\n"
            ")"
        )
        return {"status": "generated", "mode": "scalar", "dax": dax}

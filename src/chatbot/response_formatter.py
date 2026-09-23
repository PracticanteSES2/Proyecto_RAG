import re

class ResponseFormatter:

    MONTHS = {
        1: "enero",
        2: "febrero",
        3: "marzo",
        4: "abril",
        5: "mayo",
        6: "junio",
        7: "julio",
        8: "agosto",
        9: "septiembre",
        10: "octubre",
        11: "noviembre",
        12: "diciembre",
    }


    # ========================================================
    # FORMATEAR NÚMEROS
    # ========================================================

    def _format_number(
        self,
        value
    ):

        if value is None:
            return None

        # Puede venir como string desde .NET
        if isinstance(
            value,
            str
        ):

            try:
                value = float(
                    value
                )

            except ValueError:
                return value


        if isinstance(
            value,
            float
        ):

            if value.is_integer():
                return f"{int(value):,}".replace(
                    ",",
                    "."
                )

            return (
                f"{value:,.2f}"
                .replace(
                    ",",
                    "X"
                )
                .replace(
                    ".",
                    ","
                )
                .replace(
                    "X",
                    "."
                )
            )


        if isinstance(
            value,
            int
        ):

            return (
                f"{value:,}"
                .replace(
                    ",",
                    "."
                )
            )


        return str(
            value
        )


    # ========================================================
    # PERÍODO
    # ========================================================

    def _format_period(
        self,
        result
    ):

        year = result.get(
            "year"
        )

        month = result.get(
            "month"
        )


        if month and year:

            month_name = (
                self.MONTHS.get(
                    month,
                    str(month)
                )
            )

            return (
                f" en {month_name} "
                f"de {year}"
            )


        if year:

            return (
                f" en {year}"
            )


        if month:

            month_name = (
                self.MONTHS.get(
                    month,
                    str(month)
                )
            )

            return (
                f" en {month_name}"
            )


        return ""


    # ========================================================
    # RESPUESTA POWER BI
    # ========================================================

    def _format_powerbi(
        self,
        result
    ):

        value = result.get(
            "value"
        )


        if value is None:

            return (
                "No se encontró un valor "
                "para los filtros solicitados."
            )


        formatted_value = (
            self._format_number(
                value
            )
        )

        dashboard = (
            result.get(
                "dashboard"
            )
            or "el tablero"
        )

        metric_type = (
            result.get(
                "metric_type"
            )
            or "resultado"
        )

        period = (
            self._format_period(
                result
            )
        )


        dashboard_text = (
            str(dashboard)
            .lower()
        )


        if metric_type == "promedio":

            return (
                f"El promedio de "
                f"{dashboard_text}"
                f"{period} fue de "
                f"{formatted_value}."
            )


        if metric_type == "total":

            return (
                f"El total de "
                f"{dashboard_text}"
                f"{period} fue de "
                f"{formatted_value}."
            )


        if metric_type == "porcentaje":

            return (
                f"El porcentaje de "
                f"{dashboard_text}"
                f"{period} fue de "
                f"{formatted_value}%."
            )


        if metric_type == "proyeccion":

            return (
                f"La proyección de "
                f"{dashboard_text}"
                f"{period} fue de "
                f"{formatted_value}."
            )


        return (
            f"El resultado para "
            f"{dashboard_text}"
            f"{period} fue de "
            f"{formatted_value}."
        )


    # ========================================================
    # RESPUESTA RAG
    # ========================================================

    def _format_rag(
        self,
        result
    ):

        answer = result.get(
            "answer"
        )


        if not answer:

            return (
                "No encontré información "
                "suficiente en la documentación."
            )


        # Limpiar saltos/espacios excesivos
        answer = re.sub(
            r"\s+",
            " ",
            str(answer)
        ).strip()


        return answer


    # ========================================================
    # RESPUESTA PRINCIPAL
    # ========================================================

    def format(
        self,
        result
    ):

        status = result.get(
            "status"
        )


        # ----------------------------------------------------
        # ACLARACIÓN
        # ----------------------------------------------------

        if (
            status
            == "needs_clarification"
        ):

            return (
                result.get(
                    "question"
                )
                or
                "Necesito un poco más de "
                "información para responder."
            )


        # ----------------------------------------------------
        # ÉXITO
        # ----------------------------------------------------

        if status == "success":

            route = result.get(
                "route"
            )


            if route == "powerbi":

                return (
                    self._format_powerbi(
                        result
                    )
                )


            if route == "rag":

                return (
                    self._format_rag(
                        result
                    )
                )


        # ----------------------------------------------------
        # ERRORES CONTROLADOS
        # ----------------------------------------------------

        if status == "metric_not_resolved":

            return (
                "No pude identificar con "
                "seguridad la medida de "
                "Power BI que corresponde "
                "a la consulta."
            )


        if status == "filter_not_resolved":

            return (
                "No pude identificar con "
                "seguridad todos los filtros "
                "necesarios para la consulta."
            )


        if status == "dax_rejected":

            return (
                "La consulta analítica no "
                "superó las validaciones "
                "de seguridad."
            )


        if status == "powerbi_error":

            return (
                "No fue posible obtener "
                "el resultado desde Power BI."
            )


        return (
            "No fue posible procesar "
            "la consulta."
        )
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


# ============================================================
# FORMATO DE RESPUESTAS DE QUERY PLAN (estilo español)
# ============================================================

EMPTY_RESULT_MESSAGE = "No hay datos para esos filtros."
MAX_TABLE_ROWS = 50

_BLANK_TEXT = {"", "blank", "none", "nan", "null"}
_PERCENT_WORDS = ("%", "porcentaje", "participacion", "participación", "proporcion", "proporción")


def is_blank_value(value):
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    return str(value).strip().lower() in _BLANK_TEXT


def _to_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _group_thousands(integer_part):
    return f"{integer_part:,}".replace(",", ".")


def format_number_es(value, max_decimals=2):
    """3906.4 -> '3.906,4'; 1200 -> '1.200'; 1200.0 -> '1.200'."""
    number = _to_number(value)
    if number is None:
        return str(value)
    if isinstance(number, float) and number.is_integer():
        number = int(number)
    if isinstance(number, int):
        return _group_thousands(number)
    text = f"{abs(number):.{max_decimals}f}".rstrip("0").rstrip(",.")
    integer, _, decimals = text.partition(".")
    sign = "-" if number < 0 and (int(integer) or decimals) else ""
    result = sign + _group_thousands(int(integer))
    return result + ("," + decimals if decimals else "")


def format_percent_es(value, fraction=None):
    """12.5 -> '12,5 %'. Con fraction=True (0.125) o por heurística (<=1) se multiplica por 100."""
    number = _to_number(value)
    if number is None:
        return str(value)
    if fraction is None:
        fraction = abs(number) <= 1
    if fraction:
        number = round(number * 100, 6)
    return format_number_es(number) + " %"


def is_percent_metric(label=None, fmt=None, unit=None):
    if str(fmt or "").strip().lower() == "percent":
        return True
    haystack = f"{label or ''} {fmt or ''} {unit or ''}".lower()
    return any(word in haystack for word in _PERCENT_WORDS)


def format_value_es(value, label=None, fmt=None, unit=None):
    """Valor ya formateado para mostrar; nunca devuelve 'None'."""
    if is_blank_value(value):
        return None
    if is_percent_metric(label, fmt, unit):
        # Con formato de Power BI '0.0%' el valor crudo es una fracción.
        raw_fraction = True if "%" in str(fmt or "") else None
        return format_percent_es(value, fraction=raw_fraction)
    text = format_number_es(value)
    if unit and str(unit).strip().lower() not in ("number", "percent"):
        text += f" {unit}"
    return text


def format_filters_line(filters):
    """'Filtros: SERVICIO = ANTIFLUIDOS · enero 2026' o '' si no hay filtros."""
    parts = []
    seen = set()
    months = ResponseFormatter.MONTHS
    for item in filters or []:
        kind = item.get("type")
        if kind == "date_range":
            month = item.get("month_name") or months.get(item.get("month"))
            period = " ".join(str(p) for p in (month, item.get("year")) if p)
            if period:
                parts.append(period)
        elif item.get("value") not in (None, ""):
            name = item.get("concept") or item.get("column") or "Filtro"
            text = f"{str(name).upper()} = {item.get('value')}"
            if text not in seen:
                seen.add(text)
                parts.append(text)
    return "Filtros: " + " · ".join(parts) if parts else ""


def format_unapplied_line(terms):
    terms = [str(t) for t in (terms or []) if t]
    return "No pude aplicar: " + ", ".join(terms) if terms else ""


def format_query_plan_answer(result):
    """Texto de una respuesta de Query Plan (escalar, multi-medida o tabla)."""
    plan = result.get("query_plan") or {}
    filters = result.get("filters") or plan.get("filters") or []
    unapplied = result.get("unapplied_terms") or plan.get("unapplied_terms") or []
    notes = [str(note) for note in (plan.get("notes") or []) if note]
    lines = []

    if result.get("result_type") == "table" and result.get("answer"):
        lines.append(result["answer"])
        total = result.get("total_rows") or len(result.get("rows") or [])
        if total > MAX_TABLE_ROWS and "Mostrando" not in result["answer"]:
            lines.append(f"\nMostrando {MAX_TABLE_ROWS} de {total} filas.")
    else:
        measures = [
            m for m in (result.get("measures") or [])
            if isinstance(m, dict) and not is_blank_value(m.get("value"))
        ]
        if measures:
            measure_lines = []
            for measure in measures:
                text = format_value_es(
                    measure.get("value"), measure.get("label"),
                    measure.get("format"), measure.get("unit"),
                )
                measure_lines.append(f"- **{measure.get('label') or 'Valor'}**: {text}")
            lines.append("\n".join(measure_lines))
        elif result.get("answer") and not result.get("measures"):
            lines.append(str(result["answer"]))
        else:
            text = format_value_es(
                result.get("value"), result.get("metric"),
                result.get("metric_format"),
            )
            if text is None:
                lines.append(EMPTY_RESULT_MESSAGE)
            elif result.get("metric"):
                lines.append(f"**{result['metric']}**: {text}")
            else:
                lines.append(text)

    for extra in (
        format_filters_line(filters),
        format_unapplied_line(unapplied),
        " ".join(notes),
    ):
        if extra:
            lines.append(extra)
    return "\n\n".join(lines)


def clarification_prompt(result):
    """Texto de la contrapregunta. Con botones, solo la pregunta: cada opción
    ya se ve en su botón con su descripción corta (sin lista repetida)."""
    question = result.get("question") or "Necesito una aclaración para continuar."
    if clarification_buttons(result):
        return result.get("prompt") or question
    return question


def clarification_buttons(result):
    """Modelo de botones de una contrapregunta: [{id, label, caption}] (vacío si no aplica).

    `caption` es la descripción corta que se muestra bajo el botón.
    """
    if result.get("status") != "needs_clarification":
        return []
    buttons = []
    seen = set()
    for option in result.get("clarification_options") or []:
        if not isinstance(option, dict) or option.get("id") in (None, ""):
            continue
        if str(option["id"]) in seen:
            continue
        seen.add(str(option["id"]))
        label = str(option.get("label") or option["id"]).strip()
        caption = option.get("summary")
        if caption is None:
            caption = option.get("description")
        caption = " ".join(str(caption or "").split())
        if caption.casefold() in label.casefold():
            caption = ""
        buttons.append({
            "id": option["id"],
            "label": label,
            "caption": caption[:160] or None,
        })
    return buttons

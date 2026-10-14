import re
import unicodedata

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
# Botón «Ninguna de las anteriores» de una contrapregunta de indicadores.
NONE_OF_THE_ABOVE_ID = "__none__"

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


def is_currency_metric(fmt=None, unit=None):
    """Formato de dinero: «currency» (lo marca el planificador para sumas de
    MONTO/VALOR/COSTO...) o un formato de Power BI con símbolo de moneda."""
    text = f"{fmt or ''} {unit or ''}"
    return "currency" in text.lower() or "$" in text or "€" in text


def format_currency_es(value):
    """4952786591 -> '$ 4.952.786.591' (pesos sin decimales salvo montos pequeños)."""
    number = _to_number(value)
    if number is None:
        return str(value)
    if abs(number) >= 100:
        number = round(number)
    return "$ " + format_number_es(number)


def format_value_es(value, label=None, fmt=None, unit=None):
    """Valor ya formateado para mostrar; nunca devuelve 'None'."""
    if is_blank_value(value):
        return None
    if is_currency_metric(fmt, unit) and not is_percent_metric(label, None, None):
        return format_currency_es(value)
    if is_percent_metric(label, fmt, unit):
        # Con formato de Power BI '0.0%' el valor crudo es una fracción.
        raw_fraction = True if "%" in str(fmt or "") else None
        return format_percent_es(value, fraction=raw_fraction)
    text = format_number_es(value)
    if unit and str(unit).strip().lower() not in ("number", "percent"):
        text += f" {unit}"
    return text


def format_period_es(item):
    """Periodo de un filtro temporal en español: «enero–marzo 2025», «2026 hasta hoy»."""
    if item.get("label"):
        return str(item["label"])
    months = ResponseFormatter.MONTHS
    month = item.get("month_name") or months.get(item.get("month"))
    return " ".join(str(p) for p in (month, item.get("year")) if p)


def format_filters_line(filters):
    """'Filtros: SERVICIO = ANTIFLUIDOS · enero 2026' o '' si no hay filtros.

    Los filtros temporales muestran el periodo realmente aplicado una sola vez
    («enero–marzo 2025»), aunque se apliquen con varias columnas (AÑO y MES).
    """
    parts = []
    seen = set()
    for item in filters or []:
        kind = item.get("type")
        if kind == "date_range" or (item.get("temporal") and item.get("label")):
            period = format_period_es(item)
            if period and period not in seen:
                seen.add(period)
                parts.append(period)
        elif item.get("values") and item.get("value") in (None, ""):
            name = item.get("concept") or item.get("column") or "Filtro"
            text = f"{str(name).upper()} = {', '.join(str(v) for v in item['values'])}"
            if text not in seen:
                seen.add(text)
                parts.append(text)
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


# ------------------------------------------------------------------
# Redacción de respuestas numéricas (determinista, sin LLM)
# ------------------------------------------------------------------

_MONTH_NAMES_RE = "|".join(ResponseFormatter.MONTHS.values())
_MONTH_YEAR_RE = re.compile(r"\b(" + _MONTH_NAMES_RE + r") (\d{4})\b")
# Cifras de una celda/medida que se suman para el total de la tabla.
_ADDITIVE_RE = re.compile(r"\b(?:SUM|SUMX|COUNT|COUNTA|COUNTX|COUNTAX|COUNTROWS)\s*\(", re.IGNORECASE)
_NON_ADDITIVE_EXPR_RE = re.compile(
    r"\b(?:AVERAGE|AVERAGEX|AVERAGEA|DIVIDE|MEDIAN|MEDIANX|MIN|MINX|MAX|MAXX|PERCENTILE\w*)\s*\(|/",
    re.IGNORECASE,
)
_NON_ADDITIVE_LABEL_RE = re.compile(
    r"promedio|porcentaje|%|tasa|[ií]ndice|raz[oó]n|proporci|media|giro|estancia|"
    r"oportunidad|tiempo|d[ií]as? de|variaci[oó]n|crecimiento|proyecci",
    re.IGNORECASE,
)
# «CANTIDAD DE PACIENTES» -> «pacientes» (frase «hay 36 pacientes»).
_COUNT_LABEL_RE = re.compile(
    r"^(?:cantidad|n[uú]mero|total|nro\.?|n°|no\.)\s+(?:de\s+)?(?P<noun>[a-záéíóúñü ]+)$",
    re.IGNORECASE,
)
_READABLE_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÑÜáéíóúñü ]{3,30}$")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")


def _plain(text):
    return " ".join(str(text or "").split())


def _norm_label(text):
    text = unicodedata.normalize("NFKD", _plain(text).lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def period_phrase_es(label):
    """Periodo para la frase inicial: «octubre 2026 hasta hoy» -> «en lo que va
    de octubre de 2026»; «enero–marzo 2025» -> «de enero a marzo de 2025»;
    «septiembre 2026 (mes pasado)» -> «en septiembre de 2026 (mes pasado)»."""
    text = _plain(label)
    if not text:
        return ""
    suffix = ""
    match = re.match(r"^(.*?)\s*(\([^()]*\))$", text)
    if match and match.group(1):
        text, suffix = match.group(1), " " + match.group(2)
    text = _MONTH_YEAR_RE.sub(r"\1 de \2", text)
    if text.startswith("desde "):
        return text + suffix
    if text.endswith(" hasta hoy"):
        return f"en lo que va de {text[:-len(' hasta hoy')]}{suffix}"
    if "–" in text:
        first, _, second = text.partition("–")
        if re.fullmatch(r"\d{4}", first) and re.fullmatch(r"\d{4}", second):
            return f"de {first} a {second}{suffix}"
        if first[:1].isdigit() and second[:1].isdigit():
            return f"del {first} al {second}{suffix}"
        if first[:1].isdigit() or not second:
            return f"en {text}{suffix}"
        return f"de {first} a {second}{suffix}"
    if text[:1].isdigit() and " de " in text:
        return f"el {text}{suffix}"
    if text.startswith("semana "):
        return f"la {text}{suffix}"
    return f"en {text}{suffix}"


def _is_temporal_filter(item):
    return (
        item.get("type") in ("date_range", "temporal_set")
        or bool(item.get("temporal"))
        or str(item.get("source") or "") == "query_plan_temporal"
    )


def _period_of(filters, plan):
    for item in filters or []:
        if _is_temporal_filter(item):
            label = format_period_es(item) if item.get("type") != "temporal_set" else item.get("label")
            if label:
                return label
    period = plan.get("period") or {}
    return period.get("label") or ""


def _period_is_past(plan):
    """True si el periodo de la consulta ya terminó (para «hubo»)."""
    period = plan.get("period") or {}
    end, today = period.get("end"), period.get("today")
    if not end or not today:
        return False
    return str(end) <= str(today)


def _categorical_phrases(filters):
    """[«servicio URGENCIAS», «aseguradora SURA o NUEVA EPS»]."""
    phrases = []
    for item in filters or []:
        if _is_temporal_filter(item):
            continue
        values = item.get("values") if item.get("value") in (None, "") else [item.get("value")]
        values = [_plain(value) for value in values or [] if not is_blank_value(value)]
        if not values:
            continue
        joined = values[0] if len(values) == 1 else ", ".join(values[:-1]) + " o " + values[-1]
        concept = _plain(item.get("concept"))
        phrases.append(f"{concept.lower()} {joined}" if concept else joined)
    return list(dict.fromkeys(phrases))


def _scope_text(period, categories):
    """«en enero de 2026, con servicio URGENCIAS» (cualquiera puede faltar)."""
    parts = []
    if period:
        parts.append(period_phrase_es(period))
    if categories:
        parts.append("con " + " y ".join(categories))
    return ", ".join(parts)


def _capitalize(text):
    return text[:1].upper() + text[1:] if text else text


def group_header(group):
    """Cabecera de una columna de agrupación.

    `label` es el primer alias de la columna (la etiqueta que le da un
    visual). Si el alias es el nombre de la columna más un calificativo de
    otro visual («ESPECIALIDAD CIRUGÍA» para la columna ESPECIALIDAD), se usa
    el nombre de la columna, que es lo que realmente se agrupa; si el nombre
    es técnico («HSUNOMBRE») se conserva el alias («SERVICIO»).
    """
    label = _plain(group.get("label"))
    column = _plain(group.get("column"))
    if label and column and _READABLE_RE.match(column):
        if _norm_label(label).startswith(_norm_label(column) + " "):
            return column
    return label or column or "Grupo"


def _readable_lower(text):
    return text.lower() if _READABLE_RE.match(text or "") else text


def _blank_group_label(header):
    return f"(sin {header.lower()})" if _READABLE_RE.match(header or "") else "(sin dato)"


def _measure_kind(result, plan):
    """additive | distinct | other: ¿tiene sentido sumar las filas?"""
    metric = plan.get("metric") or {}
    label = str(result.get("metric") or metric.get("label") or "")
    fmt = result.get("metric_format") or metric.get("format_string") or metric.get("format")
    if is_percent_metric(label, fmt) or _NON_ADDITIVE_LABEL_RE.search(label):
        return "other"
    expression = str(metric.get("dax_expression") or metric.get("expression") or "")
    if re.search(r"\bDISTINCTCOUNT(?:NOBLANK)?\s*\(", expression, re.IGNORECASE):
        return "distinct"
    if _NON_ADDITIVE_EXPR_RE.search(expression):
        return "other"
    if _ADDITIVE_RE.search(expression):
        return "additive"
    return "other"


def _row_metric_value(row):
    for key, value in (row or {}).items():
        if "__value" in str(key).lower():
            return value
    values = list((row or {}).values())
    return values[-1] if values else None


def _rows_total(rows):
    """Suma de la medida en las filas, o None si algún valor no es numérico."""
    total = 0
    counted = 0
    for row in rows or []:
        value = _row_metric_value(row)
        if is_blank_value(value):
            continue
        number = _to_number(value)
        if number is None:
            return None
        total += number
        counted += 1
    return total if counted > 1 else None


def _split_cells(line):
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith("\\|"):
        inner = inner[:-1]
    return [cell.strip() for cell in _CELL_SPLIT_RE.split(inner)]


def _join_cells(cells):
    return "| " + " | ".join(cells) + " |"


def _polish_table(answer, group_by, total_text=None, total_label="**Total**"):
    """Tabla markdown con cabeceras legibles, celdas sin espacios de relleno,
    etiquetas vacías como «(sin especialidad)» y, si se pide, fila de total."""
    lines = str(answer or "").splitlines()
    headers = [group_header(group) for group in group_by or []]
    out = []
    table_index = 0
    last_table_line = None
    width = 0
    for line in lines:
        if not line.lstrip().startswith("|"):
            out.append(line.rstrip())
            continue
        cells = _split_cells(line)
        if table_index == 0:
            for position, group in enumerate(group_by or []):
                if position < len(cells) and cells[position] == _plain(group.get("label") or group.get("column")):
                    cells[position] = headers[position]
            width = len(cells)
        elif table_index > 1:
            for position in range(min(len(headers), len(cells) - 1)):
                if not cells[position] or is_blank_value(cells[position]):
                    cells[position] = _blank_group_label(headers[position])
        out.append(_join_cells(cells))
        last_table_line = len(out) - 1
        table_index += 1
    if total_text and last_table_line is not None and table_index > 2 and width >= 2:
        total_cells = [total_label] + [""] * (width - 2) + [f"**{total_text}**"]
        out.insert(last_table_line + 1, _join_cells(total_cells))
    return "\n".join(out).strip("\n")


def _ranking_text(plan):
    ranking = plan.get("ranking") or {}
    if not ranking:
        return ""
    order = "de menor a mayor" if ranking.get("direction") == "asc" else "de mayor a menor"
    limit = ranking.get("limit")
    return f" ({'los primeros ' + str(limit) + ', ' if limit else ''}{order})"


def _lead_scalar(label, value_text, scope, past):
    """Frase inicial de un valor único."""
    match = _COUNT_LABEL_RE.match(_plain(label)) if label else None
    # Un monto («$ 4.952.786.591») no se cuenta: «TOTAL FACTURACION: $ ...»,
    # no «Hay 4.952.786.591 facturacion».
    if match and not value_text.endswith("%") and not value_text.startswith("$"):
        noun = match.group("noun").strip().lower()
        verb = "hubo" if past else "hay"
        sentence = f"{scope}, {verb}" if scope else verb
        return _capitalize(f"{sentence} **{value_text}** {noun}.")
    if label:
        return f"**{label}** {scope}: **{value_text}**" if scope else f"**{label}**: **{value_text}**"
    return f"{_capitalize(scope)}: **{value_text}**" if scope else f"**{value_text}**"


def format_query_plan_answer(result, followup=None):
    """Texto de una respuesta de Query Plan (escalar, multi-medida o tabla).

    Determinista (sin LLM): todas las cifras salen de `result`. Empieza con
    una frase que dice qué es el dato y su alcance (periodo y filtros), sigue
    el valor o la tabla y cierra con las líneas compactas de filtros, lo que
    no se pudo aplicar y las notas. `followup` (o `result["followup_of"]`):
    la consulta es un seguimiento de la anterior; la frase inicial nombra lo
    que cambia (el periodo) y no repite los filtros heredados, que siguen en
    la línea «Filtros:».
    """
    plan = result.get("query_plan") or {}
    filters = result.get("filters") or plan.get("filters") or []
    unapplied = result.get("unapplied_terms") or plan.get("unapplied_terms") or []
    notes = [str(note) for note in (plan.get("notes") or []) if note]
    followup = followup if followup is not None else (result.get("followup_of") or plan.get("followup_of"))

    period = _period_of(filters, plan)
    categories = [] if followup else _categorical_phrases(filters)
    scope = _scope_text(period, categories)
    past = _period_is_past(plan)
    lines = []

    if result.get("result_type") == "table" and result.get("answer"):
        group_by = result.get("group_by") or plan.get("group_by") or []
        label = result.get("metric") or (plan.get("metric") or {}).get("label") or "Resultado"
        headers = [group_header(group) for group in group_by]
        groups_text = " y ".join(_readable_lower(header) for header in headers)
        subject = f"**{label}**" + (f" por {groups_text}" if groups_text else "")
        subject += _ranking_text(plan)
        lead = f"{_capitalize(scope)}, {subject}:" if scope else f"{subject}:"
        lines.append(lead)

        total_text = None
        total_note = None
        rows = result.get("rows") or []
        limited = bool((plan.get("ranking") or {}).get("limit"))
        if not result.get("composite") and not limited:
            kind = _measure_kind(result, plan)
            total = _rows_total(rows) if kind in ("additive", "distinct") else None
            if total is not None:
                formatted = format_value_es(total, label, result.get("metric_format")) or format_number_es(total)
                if kind == "additive":
                    total_text = formatted
                elif not any("suman" in note for note in notes):
                    total_note = (
                        f"Las filas suman {formatted}; la suma puede diferir del total porque un "
                        "mismo registro puede contarse en más de un grupo."
                    )
        total = result.get("total_rows") or len(rows)
        total_label = "**Total (todas las filas)**" if total > MAX_TABLE_ROWS else "**Total**"
        lines.append(_polish_table(result["answer"], group_by, total_text, total_label))
        if total > MAX_TABLE_ROWS and "Mostrando" not in result["answer"]:
            lines.append(f"Mostrando {MAX_TABLE_ROWS} de {total} filas.")
        if total_note:
            notes.append(total_note)
    else:
        all_measures = [m for m in (result.get("measures") or []) if isinstance(m, dict)]
        measures = [m for m in all_measures if not is_blank_value(m.get("value"))]
        if measures:
            if scope:
                lines.append(_capitalize(scope) + ":")
            # Una medida vacía se declara («sin datos») en vez de omitirse: si
            # no, la respuesta parece completa aunque falte una parte.
            measure_lines = []
            for measure in all_measures:
                label = measure.get("label") or "Valor"
                if is_blank_value(measure.get("value")):
                    measure_lines.append(f"- **{label}**: sin datos para esos filtros")
                    continue
                text = format_value_es(
                    measure.get("value"), measure.get("label"),
                    measure.get("format"), measure.get("unit"),
                )
                measure_lines.append(f"- **{label}**: {text}")
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
            else:
                lines.append(_lead_scalar(result.get("metric"), text, scope, past))

    footer = [part for part in (format_filters_line(filters), format_unapplied_line(unapplied)) if part]
    if footer:
        lines.append(". ".join(footer) + ".")
    if notes:
        lines.append(" ".join(notes))
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

    `caption` es la descripción corta que se muestra bajo el botón. Si la
    contrapregunta lo permite, el último botón es «Ninguna de las anteriores».
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
            "caption": caption[:240] or None,
        })
    none_option = result.get("none_option")
    if buttons and isinstance(none_option, dict) and none_option.get("id"):
        buttons.append({
            "id": none_option["id"],
            "label": str(none_option.get("label") or "Ninguna de las anteriores"),
            "caption": none_option.get("caption") or None,
        })
    return buttons

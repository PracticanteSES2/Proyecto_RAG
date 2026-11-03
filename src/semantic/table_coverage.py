"""
Ventana de datos de una tabla según su descripción documentada.

Muchas tablas de los tableros solo traen una ventana reciente («Triages del día
anterior», «Interconsultas de los últimos 10 días», «Ingresos de hoy») o un
histórico desde una fecha («Triages desde el 01/01/2023»). Un indicador sobre
una de ellas no puede responder un periodo que su tabla no trae («triages en
2025» con la tabla del día anterior) aunque tenga columna de fecha: el DAX da
vacío. Este módulo traduce esas frases a una ventana (inicio, fin) relativa a
hoy; None si la descripción no dice nada de su ventana.
"""
import re
import unicodedata
from datetime import date, timedelta

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_NUMBERS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
            "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "doce": 12, "quince": 15, "treinta": 30,
            "noventa": 90}
_MONTH_RE = "|".join(_MONTHS)
_NUMBER_RE = r"\d{1,3}|" + "|".join(_NUMBERS)


def _normalize(value):
    value = str(value or "").lower()
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _number(text):
    return int(text) if text.isdigit() else _NUMBERS.get(text)


def _safe_date(year, month, day):
    try:
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def _minus(today, amount, unit):
    if unit.startswith("dia"):
        return today - timedelta(days=amount)
    if unit.startswith("semana"):
        return today - timedelta(weeks=amount)
    if unit.startswith("mes"):
        month = today.month - amount
        year = today.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        return date(year, month, 1)
    if unit.startswith("ano"):
        return date(today.year - amount, 1, 1)
    return None


def coverage_window(text, today):
    """(inicio, fin) de los datos que trae la tabla según su descripción, con
    fin exclusivo o None (= hasta hoy). None si la descripción no lo dice."""
    norm = _normalize(text)
    if not norm:
        return None
    starts = []
    # Fechas absolutas: «desde el 2025-01-01», «desde el 01/01/2023»,
    # «desde el 1 de enero de 2025», «desde enero de 2025», «entre el 1 de
    # enero de 2025 y hoy».
    for match in re.finditer(r"(?:desde|entre) (?:el )?(\d{4}) (\d{1,2}) (\d{1,2})(?![0-9])", norm):
        starts.append(_safe_date(match.group(1), match.group(2), match.group(3)))
    for match in re.finditer(r"(?:desde|entre) (?:el )?(\d{1,2}) (\d{1,2}) (\d{4})(?![0-9])", norm):
        starts.append(_safe_date(match.group(3), match.group(2), match.group(1)))
    for match in re.finditer(r"(?:desde|entre) (?:el )?(\d{1,2}) de (" + _MONTH_RE + r") (?:de |del )?(\d{4})", norm):
        starts.append(_safe_date(match.group(3), _MONTHS[match.group(2)], match.group(1)))
    for match in re.finditer(r"desde (" + _MONTH_RE + r") (?:de |del )?(\d{4})", norm):
        starts.append(_safe_date(match.group(2), _MONTHS[match.group(1)], 1))
    # Ventanas relativas: «de los últimos 10 días», «desde hace 3 días».
    for match in re.finditer(
            r"(?:ultimos|ultimas|desde hace) (" + _NUMBER_RE + r") (dias|dia|semanas|semana|meses|mes|anos|ano)",
            norm):
        amount = _number(match.group(1))
        if amount:
            starts.append(_minus(today, amount, match.group(2)))
    for match in re.finditer(r"(?:de |del )?(?:los )?(" + _NUMBER_RE + r") dias anteriores", norm):
        amount = _number(match.group(1))
        if amount:
            starts.append(today - timedelta(days=amount))
    # «Periodo de la semana en curso»: desde el lunes de esta semana.
    if re.search(r"(?<![a-z])(?:semana en curso|semana actual|de esta semana)(?![a-z])", norm):
        starts.append(today - timedelta(days=today.weekday()))
    if re.search(r"(?<![a-z])(?:de ayer|del dia anterior|dia anterior)(?![a-z])", norm):
        starts.append(today - timedelta(days=1))
    # «de hoy», «registrados hoy», «del día de la última actualización»; no
    # «hasta hoy» ni «después de hoy» (son el final de un histórico).
    today_text = re.sub(r"(?:hasta|despues de|antes de|a) hoy", " ", norm)
    if re.search(
            r"(?<![a-z])(?:de hoy|del dia de hoy|registrad[oa]s hoy|asignad[oa] hoy|para hoy|con ingreso hoy|"
            r"hech[oa]s hoy|del dia de la ultima actualizacion)(?![a-z])",
            today_text):
        starts.append(today)
    # Tablas de lo que viene («citas asignadas para los próximos días», «una
    # fila por cita ambulatoria próxima», «agenda futura»): solo traen desde
    # hoy en adelante; no responden un periodo pasado («el mes pasado»).
    if re.search(
            r"(?<![a-z])(?:para |de |en )?(?:los |las )?proxim[oa]s (?:dias|semanas|meses|citas|cirugias)(?![a-z])"
            r"|(?<![a-z])(?:citas?|cirugias?|consultas?|turnos?|programacion(?:es)?)(?: [a-z]+)? proxim[oa]s?(?![a-z])"
            r"|(?<![a-z])(?:a futuro|agenda futura|citas futuras|programad[oa]s a partir de hoy|desde hoy en adelante)(?![a-z])",
            norm):
        starts.append(today)
    # «Sin límite de fechas», «no limita fechas», «todo el histórico»: la
    # tabla trae cualquier periodo (aunque la página sea una foto del día).
    if re.search(
            r"(?<![a-z])(?:sin limite de fechas?|sin limite de tiempo|no limita (?:las )?fechas|"
            r"todo el historico|historico completo)(?![a-z])",
            norm):
        starts.append(date.min)
    starts = [value for value in starts if value is not None]
    end = None
    if re.search(r"hasta el ultimo dia del mes anterior", norm):
        end = date(today.year, today.month, 1)
    if not starts and end is None:
        return None
    return (min(starts) if starts else None), end


def covers(window, start, end, today, slack_days=1):
    """¿La ventana (inicio, fin) trae todo el periodo [start, end)?
    Un periodo «hasta hoy» termina en hoy + 1.

    La holgura (`slack_days`) solo vale para periodos de uno o dos días
    («ayer» sobre la tabla «de hoy», cargada de madrugada). Un periodo más
    largo («este mes», «esta semana») debe empezar dentro de la ventana: el 3
    de noviembre, la tabla «del día anterior» (desde el 2) no trae «este mes»
    (desde el 1) aunque solo falte un día (TU04: 147 triages del corte frente
    a 387 del mes)."""
    if window is None or start is None or end is None:
        return True
    window_start, window_end = window
    slack = timedelta(days=slack_days)
    effective_end = min(end, today + timedelta(days=1))
    short = (effective_end - start) <= timedelta(days=2)
    start_slack = slack if short else timedelta(0)
    if window_start is not None and window_start > start + start_slack:
        return False
    if window_end is not None and window_end < effective_end - slack:
        return False
    return True

"""
Periodos de tiempo y agrupaciones temporales en preguntas en español.

Convierte expresiones como «entre enero y marzo de 2025», «este año»,
«el mes pasado», «primer trimestre», «últimos 3 meses», «en lo que va del
año», «hoy» o «ayer» en rangos de fechas concretos, y detecta pedidos de
agrupación temporal («por mes», «mensual», «mes a mes», «por trimestre»).

Todo es determinista y relativo a `today` (inyectable en las pruebas: nunca
se usa la fecha real si se pasa una). El texto de entrada debe venir
normalizado (minúsculas, sin tildes ni puntuación), como lo produce
query_plan_builder.normalize_text.

Un periodo es un rango semiabierto [start, end) con metadatos:

    {
      "kind": "year" | "month" | "range" | "day" | "months_any_year",
      "start": date | None, "end": date | None,   # end exclusivo
      "months": [1, 2, 3],          # solo months_any_year (mes sin año)
      "year": 2025 | None,          # si TODO el periodo cae en un mismo año
      "month": 3 | None,            # si TODO el periodo cae en un mismo mes
      "month_name": "marzo" | None,
      "label": "enero–marzo 2025",  # texto para mostrar al usuario
      "daily": bool,                # necesita una columna de fecha diaria
      "to_date": bool,              # recortado hasta hoy
      "relative": bool,             # depende de la fecha actual
      "phrase": "entre enero y marzo de 2025",   # texto que lo expresó
    }

Decisiones (documentadas también en las pruebas):
- «últimos N meses/años/trimestres» = N unidades COMPLETAS anteriores a la
  actual (el 9-oct-2026, «últimos 3 meses» = julio–septiembre 2026). Así el
  periodo es el mismo con columna de fecha o con columnas AÑO/MES enteras.
- «últimos N días/semanas» = hasta hoy incluido (requiere fecha diaria).
- «este año», «este mes», «este trimestre» = desde su inicio hasta hoy.
- «primer trimestre» sin año = el del año en curso; si aún no empieza, el
  del año pasado. «último trimestre» sin año = el último completo.
- Mes sin año («en enero») = ese mes en todos los años (como antes).
"""
import re
from datetime import date, datetime, timedelta

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
MONTH_NAMES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre",
    11: "noviembre", 12: "diciembre",
}
MONTH_RE = "(?:" + "|".join(MONTHS) + ")"

NUMBER_WORDS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
    "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciocho": 18,
    "veinte": 20, "veinticuatro": 24, "treinta": 30, "sesenta": 60,
    "noventa": 90,
}
NUMBER_RE = r"(?:\d{1,3}|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"

ORDINALS = {
    "primer": 1, "primero": 1, "primera": 1, "1": 1, "1er": 1, "1ero": 1,
    "1ro": 1, "1o": 1, "1a": 1,
    "segundo": 2, "segunda": 2, "2": 2, "2do": 2, "2o": 2, "2a": 2,
    "tercer": 3, "tercero": 3, "tercera": 3, "3": 3, "3er": 3, "3ero": 3,
    "3ro": 3, "3o": 3,
    "cuarto": 4, "cuarta": 4, "4": 4, "4to": 4, "4o": 4,
    "ultimo": "last", "ultima": "last",
}
ORDINAL_RE = "(?:" + "|".join(sorted(ORDINALS, key=len, reverse=True)) + ")"
ORDINAL_LABELS = {1: "1.er", 2: "2.º", 3: "3.er", 4: "4.º"}

YEAR_WORD = r"an(?:i)?o"

# Referencia de año pegada a un mes / trimestre: « de 2025», « del año
# pasado», « de este año», « 2025».
_YEAR_REF = re.compile(
    r"\s+(?:(?:de|del|en)\s+)?(?:(?:el|la)\s+)?"
    r"(?:"
    r"(?:" + YEAR_WORD + r"\s+)?(?P<abs>(?:19|20)\d{2})"
    r"|(?P<rel>(?:este|presente|el\s+presente)\s+" + YEAR_WORD
    + r"|" + YEAR_WORD + r"\s+(?:actual|en\s+curso|corriente|pasado|anterior|antepasado))"
    r")(?![a-z0-9])"
)

# Marcas de «acumulado hasta hoy»: sin valor como filtro cuando la pregunta
# trae un periodo («cuánto peso LLEVA la lavandería este año»).
TO_DATE_WORDS = {
    "lleva", "llevan", "llevamos", "van", "vamos", "acumulado", "acumulada",
    "acumulados", "acumuladas", "corrido", "transcurrido",
}
_TO_DATE_SUFFIX = r"(?:\s+(?:hasta\s+(?:hoy|la\s+fecha|ahora|el\s+momento)|a\s+la\s+fecha|a\s+hoy))?"
# «hasta hoy» / «a la fecha» sin otro periodo: todo el histórico (no filtra).
_NEUTRAL_RE = re.compile(
    r"(?<![a-z0-9])(?:hasta\s+(?:hoy|la\s+fecha|ahora|el\s+momento)|a\s+la\s+fecha)(?![a-z0-9])"
)

GRANULARITY_LABELS = {
    "day": "Día", "week": "Semana", "month": "Mes", "quarter": "Trimestre",
    "semester": "Semestre", "year": "Año",
}
_GRANULARITY_WORDS = {
    "dia": "day", "dias": "day", "semana": "week", "semanas": "week",
    "mes": "month", "meses": "month", "ano": "year", "anos": "year",
    "anio": "year", "anios": "year", "trimestre": "quarter",
    "trimestres": "quarter", "semestre": "semester", "semestres": "semester",
}
_GRANULARITY_ADJECTIVES = {
    "diario": "day", "diaria": "day", "diarios": "day", "diarias": "day",
    "diariamente": "day", "semanal": "week", "semanalmente": "week",
    "mensual": "month", "mensuales": "month", "mensualmente": "month",
    "trimestral": "quarter", "trimestrales": "quarter", "trimestralmente": "quarter",
    "semestral": "semester", "semestrales": "semester",
    "anual": "year", "anuales": "year", "anualmente": "year",
}
_UNIT_RE = r"(?:dias?|semanas?|mes(?:es)?|an(?:i)?os?|trimestres?|semestres?)"
_GRANULARITY_RES = (
    re.compile(
        r"(?<![a-z0-9])(?:por|cada|segun|agrupad[oa]\s+por|desglosad[oa]\s+por)\s+"
        r"(?:(?:el|la|los|las|cada)\s+)?(?P<unit>" + _UNIT_RE + r")(?![a-z0-9])"
        # «por mes de enero», «por año 2025» no piden agrupar.
        r"(?!\s+(?:de\s+)?(?:" + MONTH_RE + r"|actual|pasad[oa]|anterior|en\s+curso))"
    ),
    re.compile(r"(?<![a-z0-9])(?P<unit>dia|semana|mes|an(?:i)?o|trimestre|semestre)\s+a\s+(?P=unit)(?![a-z0-9])"),
    re.compile(
        r"(?<![a-z0-9])(?<!promedio\s)(?<!media\s)(?<!tasa\s)(?P<adj>"
        + "|".join(sorted(_GRANULARITY_ADJECTIVES, key=len, reverse=True))
        + r")(?![a-z0-9])"
    ),
)

MAX_BUCKETS = 62


# ---------------------------------------------------------------- fechas
def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


def add_months(year, month, delta):
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_start(year, month):
    return date(year, month, 1)


def next_month_start(year, month):
    return month_start(*add_months(year, month, 1))


def _number(text):
    if text is None:
        return None
    if text.isdigit():
        return int(text)
    return NUMBER_WORDS.get(text)


# ---------------------------------------------------------------- etiquetas
def _day_text(value, with_year=True):
    text = f"{value.day} de {MONTH_NAMES[value.month]}"
    return f"{text} de {value.year}" if with_year else text


def _short_date(value):
    return value.strftime("%d/%m/%Y")


def period_label(start, end, to_date=False):
    """Texto en español de [start, end): «2025», «enero–marzo 2025»,
    «noviembre 2024–febrero 2025», «2026 hasta hoy», «9 de octubre de 2026».
    Con `to_date`, `end` es mañana y el periodo se lee «... hasta hoy»."""
    last = end - timedelta(days=1)
    if to_date:
        if start == date(start.year, 1, 1) and last.year == start.year:
            return f"{start.year} hasta hoy"
        if start.day == 1 and (last.year, last.month) == (start.year, start.month):
            return f"{MONTH_NAMES[start.month]} {start.year} hasta hoy"
        if start.day == 1:
            return f"desde {MONTH_NAMES[start.month]} {start.year} hasta hoy"
        return f"desde el {_short_date(start)} hasta hoy"
    month_aligned = start.day == 1 and end.day == 1
    if month_aligned:
        if start.month == 1 and end.month == 1:
            years = end.year - start.year
            if years == 1:
                return str(start.year)
            return f"{start.year}–{end.year - 1}"
        if (start.year, start.month) == (last.year, last.month):
            return f"{MONTH_NAMES[start.month]} {start.year}"
        if start.year == last.year:
            return f"{MONTH_NAMES[start.month]}–{MONTH_NAMES[last.month]} {start.year}"
        return (f"{MONTH_NAMES[start.month]} {start.year}–"
                f"{MONTH_NAMES[last.month]} {last.year}")
    if start == last:
        return _day_text(start)
    if (start.year, start.month) == (last.year, last.month):
        return f"{start.day}–{last.day} de {MONTH_NAMES[start.month]} de {start.year}"
    if start.year == last.year:
        return f"{_day_text(start, False)}–{_day_text(last)}"
    return f"{_day_text(start)}–{_day_text(last)}"


# ---------------------------------------------------------------- parser
class PeriodParser:
    """Detecta periodos y agrupaciones temporales relativos a `today`."""

    def __init__(self, today=None):
        self.today = as_date(today) or date.today()

    # ------------------------------------------------ construcción
    def _range(self, start, end, phrase, description=None, relative=False,
               clip=False, daily=False, kind=None, to_date=False):
        """Periodo [start, end).

        `clip=True` recorta a hoy un periodo en curso («este año», «este
        mes»); un periodo nombrado explícitamente («2026», «octubre de 2026»)
        se respeta completo (puede haber datos programados a futuro).
        `to_date=True` indica que `end` ya es mañana (periodo «hasta hoy»).
        """
        tomorrow = self.today + timedelta(days=1)
        if clip and start <= self.today < end - timedelta(days=1):
            end, to_date = tomorrow, True
        last = end - timedelta(days=1)
        label = period_label(start, end, to_date)
        if description and description not in label:
            label = f"{label} ({description})"
        same_year = start.year == last.year
        same_month = same_year and start.month == last.month
        whole_month = same_month and start.day == 1 and (end.day == 1 or to_date)
        whole_year = same_year and start == date(start.year, 1, 1) and (
            end == date(start.year + 1, 1, 1) or to_date
        )
        if kind is None:
            if start == last and (daily or not to_date):
                kind = "day"
            elif whole_month:
                kind = "month"
            elif whole_year:
                kind = "year"
            else:
                kind = "range"
        return {
            "kind": kind,
            "start": start, "end": end,
            "year": start.year if same_year else None,
            "month": start.month if same_month else None,
            "month_name": MONTH_NAMES[start.month] if same_month else None,
            "months": None,
            "label": label,
            "daily": daily or not (start.day == 1 and (end.day == 1 or to_date)),
            "to_date": to_date,
            "relative": relative,
            "phrase": phrase,
        }

    def _month_range(self, y1, m1, y2, m2, phrase, description=None, relative=False, clip=False):
        return self._range(month_start(y1, m1), next_month_start(y2, m2), phrase,
                           description, relative, clip=clip)

    def _months_any_year(self, months, phrase):
        names = [MONTH_NAMES[m] for m in months]
        single = len(months) == 1
        label = names[0] if single else f"{names[0]}–{names[-1]} (todos los años)"
        return {
            "kind": "months_any_year", "start": None, "end": None,
            "year": None, "month": months[0] if single else None,
            "month_name": names[0] if single else None, "months": list(months),
            "label": label, "daily": False, "to_date": False, "relative": False,
            "phrase": phrase,
        }

    def _year_from_ref(self, match):
        """Año de una referencia «de 2025» / «del año pasado» / «de este año»."""
        if match is None:
            return None, False
        if match.group("abs"):
            return int(match.group("abs")), False
        rel = match.group("rel")
        if "antepasado" in rel:
            return self.today.year - 2, True
        if "pasado" in rel or "anterior" in rel:
            return self.today.year - 1, True
        return self.today.year, True

    def _recent_year_for_month(self, month):
        """Mes sin año en una expresión relativa: su ocurrencia más reciente."""
        return self.today.year if month <= self.today.month else self.today.year - 1

    # ------------------------------------------------ reglas
    def _day_range(self, text):
        pattern = re.compile(
            r"(?<![a-z0-9])(?:del|desde\s+el|entre\s+el|de)\s+(?P<d1>[0-3]?\d)"
            r"(?:\s+de\s+(?P<m1>" + MONTH_RE + r"))?"
            r"\s+(?:al|hasta\s+el|y\s+el|a)\s+(?P<d2>[0-3]?\d)\s+de\s+(?P<m2>" + MONTH_RE + r")"
        )
        match = pattern.search(text)
        if not match:
            return None
        ref = _YEAR_REF.match(text, match.end())
        year, relative = self._year_from_ref(ref)
        m2 = MONTHS[match.group("m2")]
        m1 = MONTHS[match.group("m1")] if match.group("m1") else m2
        y2 = year if year is not None else self.today.year
        y1 = y2 if m1 <= m2 else y2 - 1
        try:
            start = date(y1, m1, int(match.group("d1")))
            last = date(y2, m2, int(match.group("d2")))
        except ValueError:
            return None
        if last < start:
            return None
        end_pos = ref.end() if ref else match.end()
        return self._range(start, last + timedelta(days=1), text[match.start():end_pos],
                           relative=relative or year is None, clip=False, daily=True)

    def _single_day(self, text):
        pattern = re.compile(r"(?<![a-z0-9])(?P<d>[0-3]?\d)\s+de\s+(?P<m>" + MONTH_RE + r")(?![a-z0-9])")
        for match in pattern.finditer(text):
            ref = _YEAR_REF.match(text, match.end())
            year, relative = self._year_from_ref(ref)
            month = MONTHS[match.group("m")]
            day = int(match.group("d"))
            if year is None:
                year = self.today.year
                try:
                    if date(year, month, day) > self.today:
                        year -= 1
                except ValueError:
                    continue
                relative = True
            try:
                value = date(year, month, day)
            except ValueError:
                continue
            end_pos = ref.end() if ref else match.end()
            return self._range(value, value + timedelta(days=1), text[match.start():end_pos],
                               relative=relative, clip=False, daily=True)
        return None

    def _month_span(self, text):
        """«entre enero y marzo de 2025», «de enero a marzo», «noviembre de 2024 a febrero de 2025»."""
        pattern = re.compile(
            r"(?<![a-z0-9])(?:(?P<pre>entre|desde|de)\s+)?(?:(?:el\s+)?mes\s+de\s+)?"
            r"(?P<m1>" + MONTH_RE + r")"
            r"(?:\s+(?:de|del)\s+(?:" + YEAR_WORD + r"\s+)?(?P<y1>(?:19|20)\d{2})|\s+(?P<y1b>(?:19|20)\d{2}))?"
            r"\s+(?P<conn>y|a|al|hasta)\s+(?:(?:el\s+)?mes\s+de\s+)?(?P<m2>" + MONTH_RE + r")(?![a-z0-9])"
        )
        for match in pattern.finditer(text):
            pre, conn = match.group("pre"), match.group("conn")
            # «enero y marzo» son dos meses sueltos; solo «entre ... y ...» es rango.
            if conn == "y" and pre != "entre":
                continue
            ref = _YEAR_REF.match(text, match.end())
            y2, relative = self._year_from_ref(ref)
            m1, m2 = MONTHS[match.group("m1")], MONTHS[match.group("m2")]
            y1 = match.group("y1") or match.group("y1b")
            y1 = int(y1) if y1 else None
            end_pos = ref.end() if ref else match.end()
            phrase = text[match.start():end_pos]
            if y1 is None and y2 is None:
                if m1 <= m2:
                    months = list(range(m1, m2 + 1))
                else:
                    months = list(range(m1, 13)) + list(range(1, m2 + 1))
                return self._months_any_year(months, phrase)
            if y2 is None:
                y2 = y1 if m2 >= m1 else y1 + 1
            if y1 is None:
                y1 = y2 if m1 <= m2 else y2 - 1
            if (y1, m1) > (y2, m2):
                continue
            return self._month_range(y1, m1, y2, m2, phrase, relative=relative)
        return None

    def _year_span(self, text):
        pattern = re.compile(
            r"(?<![a-z0-9])(?P<pre>entre|desde|de)\s+(?:el\s+)?(?:" + YEAR_WORD + r"\s+)?(?P<y1>(?:19|20)\d{2})"
            r"\s+(?P<conn>y|a|al|hasta)\s+(?:el\s+)?(?:" + YEAR_WORD + r"\s+)?(?P<y2>(?:19|20)\d{2})(?![a-z0-9])"
        )
        for match in pattern.finditer(text):
            if match.group("conn") == "y" and match.group("pre") != "entre":
                continue
            y1, y2 = int(match.group("y1")), int(match.group("y2"))
            if y1 > y2:
                continue
            return self._range(date(y1, 1, 1), date(y2 + 1, 1, 1), match.group(0))
        return None

    def _since(self, text):
        pattern = re.compile(
            r"(?<![a-z0-9])(?:a\s+partir\s+de|desde)\s+(?:el\s+)?(?:"
            r"(?:mes\s+de\s+)?(?P<m>" + MONTH_RE + r")"
            r"|(?:" + YEAR_WORD + r"\s+)?(?P<y>(?:19|20)\d{2}))(?![a-z0-9])"
        )
        match = pattern.search(text)
        if not match:
            return None
        end_pos = match.end()
        if match.group("m"):
            month = MONTHS[match.group("m")]
            ref = _YEAR_REF.match(text, end_pos)
            year, _ = self._year_from_ref(ref)
            if ref:
                end_pos = ref.end()
            if year is None:
                year = self._recent_year_for_month(month)
            start = month_start(year, month)
        else:
            start = date(int(match.group("y")), 1, 1)
        suffix = re.compile(_TO_DATE_SUFFIX).match(text, end_pos)
        if suffix:
            end_pos = suffix.end()
        if start > self.today:
            return None
        return self._range(start, self.today + timedelta(days=1), text[match.start():end_pos],
                           relative=True, clip=False, kind="range", to_date=True)

    def _quarter_or_semester(self, text):
        pattern = re.compile(
            r"(?<![a-z0-9])(?P<ord>" + ORDINAL_RE + r")\s+(?P<unit>trimestre|semestre)(?![a-z0-9])"
        )
        for match in pattern.finditer(text):
            ordinal = ORDINALS[match.group("ord")]
            unit = match.group("unit")
            size = 3 if unit == "trimestre" else 6
            count = 12 // size
            ref = _YEAR_REF.match(text, match.end())
            year, relative = self._year_from_ref(ref)
            end_pos = ref.end() if ref else match.end()
            current = (self.today.month - 1) // size + 1
            if ordinal == "last":
                if year is None:  # último completo
                    year, index = (self.today.year, current - 1) if current > 1 else (self.today.year - 1, count)
                    relative = True
                else:
                    index = count
            else:
                if ordinal > count:
                    continue
                index = ordinal
                if year is None:
                    year = self.today.year if index <= current else self.today.year - 1
                    relative = True
            first = (index - 1) * size + 1
            description = f"{ORDINAL_LABELS[index]} {unit}"
            return self._month_range(year, first, year, first + size - 1, text[match.start():end_pos],
                                     description, relative, clip=relative)
        quarter_form = re.compile(r"(?<![a-z0-9])[qt](?P<n>[1-4])\s+(?:(?:de|del)\s+)?(?P<y>(?:19|20)\d{2})(?![a-z0-9])")
        match = quarter_form.search(text)
        if match:
            index, year = int(match.group("n")), int(match.group("y"))
            first = (index - 1) * 3 + 1
            return self._month_range(year, first, year, first + 2, match.group(0),
                                     f"{ORDINAL_LABELS[index]} trimestre")
        return None

    def _relative_quarter_or_semester(self, text):
        pattern = re.compile(
            r"(?<![a-z0-9])(?:(?P<this>este|esta|el\s+presente)\s+(?P<u1>trimestre|semestre)"
            r"|(?:el\s+)?(?P<u2>trimestre|semestre)\s+(?P<when>actual|en\s+curso|pasado|anterior))(?![a-z0-9])"
        )
        match = pattern.search(text)
        if not match:
            return None
        unit = match.group("u1") or match.group("u2")
        size = 3 if unit == "trimestre" else 6
        current = (self.today.month - 1) // size + 1
        previous = bool(match.group("when")) and match.group("when") in ("pasado", "anterior")
        year, index = self.today.year, current
        if previous:
            index -= 1
            if index == 0:
                year, index = year - 1, 12 // size
        first = (index - 1) * size + 1
        return self._month_range(year, first, year, first + size - 1, match.group(0),
                                 f"{ORDINAL_LABELS[index]} {unit}", relative=True, clip=True)

    def _last_n(self, text):
        pattern = re.compile(
            r"(?<![a-z0-9])(?:(?:en|durante|de)\s+)?(?:(?:los|las)\s+)?"
            r"(?:(?:ultim[oa]s|pasad[oa]s)\s+(?P<n1>" + NUMBER_RE + r")|(?P<n2>" + NUMBER_RE + r")\s+ultim[oa]s)"
            r"\s+(?P<unit>" + _UNIT_RE + r")(?![a-z0-9])"
        )
        match = pattern.search(text)
        if not match:
            return None
        count = _number(match.group("n1") or match.group("n2"))
        if not count:
            return None
        unit = _GRANULARITY_WORDS.get(match.group("unit"), _GRANULARITY_WORDS.get(match.group("unit").rstrip("s")))
        phrase = match.group(0)
        today = self.today
        tomorrow = today + timedelta(days=1)
        if unit in ("day", "week"):
            days = count * (7 if unit == "week" else 1)
            words = "días" if unit == "day" else ("semanas" if count > 1 else "semana")
            return self._range(tomorrow - timedelta(days=days), tomorrow, phrase,
                               f"últimos {count} {words}" if count > 1 else None,
                               relative=True, clip=False, daily=True, kind="range")
        if unit == "month":
            y1, m1 = add_months(today.year, today.month, -count)
            y2, m2 = add_months(today.year, today.month, -1)
            return self._month_range(y1, m1, y2, m2, phrase,
                                     f"últimos {count} meses" if count > 1 else "mes pasado", True)
        if unit == "year":
            return self._range(date(today.year - count, 1, 1), date(today.year, 1, 1), phrase,
                               f"últimos {count} años" if count > 1 else "año pasado", relative=True)
        size = 3 if unit == "quarter" else 6
        current = (today.month - 1) // size + 1
        first_current = (current - 1) * size + 1
        y2, m2 = add_months(today.year, first_current, -1)
        y1, m1 = add_months(today.year, first_current, -size * count)
        name = "trimestres" if size == 3 else "semestres"
        return self._month_range(y1, m1, y2, m2, phrase, f"últimos {count} {name}", True)

    def _month_with_year_ref(self, text):
        """«marzo del año pasado», «marzo de este año», «marzo pasado», «marzo de 2025»."""
        pattern = re.compile(r"(?<![a-z0-9])(?:(?:el\s+)?mes\s+de\s+)?(?P<m>" + MONTH_RE + r")(?![a-z0-9])")
        for match in pattern.finditer(text):
            month = MONTHS[match.group("m")]
            ref = _YEAR_REF.match(text, match.end())
            if ref:
                year, relative = self._year_from_ref(ref)
                return self._month_range(year, month, year, month, text[match.start():ref.end()],
                                         relative=relative)
            past = re.compile(r"\s+(?:pasado|anterior)(?![a-z0-9])").match(text, match.end())
            if past:
                year = self.today.year if month < self.today.month else self.today.year - 1
                return self._month_range(year, month, year, month, text[match.start():past.end()],
                                         relative=True)
        return None

    def _relative_single(self, text):
        today = self.today
        tomorrow = today + timedelta(days=1)
        year_now = date(today.year, 1, 1)
        month_now = month_start(today.year, today.month)
        monday = today - timedelta(days=today.weekday())
        rules = (
            (r"(?:en\s+)?(?:lo\s+que\s+(?:va|llevamos|lleva|van)|lo\s+corrido|lo\s+transcurrido)\s+"
             r"(?:del|de\s+este|de\s+el)\s+" + YEAR_WORD,
             lambda p: self._range(year_now, date(today.year + 1, 1, 1), p, relative=True, clip=True)),
            (r"(?:en\s+)?(?:lo\s+que\s+(?:va|llevamos|lleva|van)|lo\s+corrido|lo\s+transcurrido)\s+"
             r"(?:del|de\s+este|de\s+el)\s+mes",
             lambda p: self._range(month_now, next_month_start(today.year, today.month), p,
                                   relative=True, clip=True)),
            (r"(?:el\s+)?" + YEAR_WORD + r"\s+antepasado",
             lambda p: self._range(date(today.year - 2, 1, 1), date(today.year - 1, 1, 1), p,
                                   "año antepasado", relative=True)),
            (r"(?:el\s+)?(?:" + YEAR_WORD + r"\s+(?:pasado|anterior)|ultimo\s+" + YEAR_WORD + r")",
             lambda p: self._range(date(today.year - 1, 1, 1), year_now, p, "año pasado", relative=True)),
            (r"(?:en\s+)?(?:(?:este|el\s+presente|presente)\s+" + YEAR_WORD
             + r"|(?:el\s+)?" + YEAR_WORD + r"\s+(?:actual|en\s+curso|corriente))",
             lambda p: self._range(year_now, date(today.year + 1, 1, 1), p, relative=True, clip=True)),
            (r"(?:el\s+)?(?:mes\s+(?:pasado|anterior)|ultimo\s+mes)",
             lambda p: self._month_range(*add_months(today.year, today.month, -1),
                                         *add_months(today.year, today.month, -1), p,
                                         "mes pasado", True)),
            (r"(?:en\s+)?(?:(?:este|el\s+presente|presente)\s+mes|(?:el\s+)?mes\s+(?:actual|en\s+curso|corriente))",
             lambda p: self._range(month_now, next_month_start(today.year, today.month), p,
                                   relative=True, clip=True)),
            (r"(?:la\s+)?semana\s+(?:pasada|anterior)",
             lambda p: self._range(monday - timedelta(days=7), monday, p, "semana pasada",
                                   relative=True, clip=False, daily=True, kind="range")),
            (r"(?:la\s+)?ultima\s+semana",
             lambda p: self._range(tomorrow - timedelta(days=7), tomorrow, p, "últimos 7 días",
                                   relative=True, clip=False, daily=True, kind="range")),
            (r"(?:en\s+)?(?:(?:esta|la\s+presente)\s+semana|(?:la\s+)?semana\s+(?:actual|en\s+curso))",
             lambda p: self._range(monday, tomorrow, p, "esta semana", relative=True,
                                   clip=False, daily=True, kind="range", to_date=True)),
            (r"(?:anteayer|antier|antes\s+de\s+ayer)",
             lambda p: self._range(today - timedelta(days=2), today - timedelta(days=1), p,
                                   "anteayer", relative=True, clip=False, daily=True)),
            (r"ayer",
             lambda p: self._range(today - timedelta(days=1), today, p, "ayer", relative=True,
                                   clip=False, daily=True)),
            (r"(?<!hasta\s)(?<!a\s)(?:el\s+dia\s+de\s+)?hoy",
             lambda p: self._range(today, tomorrow, p, "hoy", relative=True, clip=False, daily=True)),
        )
        for expression, build in rules:
            match = re.search(r"(?<![a-z0-9])" + expression + _TO_DATE_SUFFIX + r"(?![a-z0-9])", text)
            if match:
                return build(match.group(0))
        return None

    def _legacy(self, text):
        """Mes y/o año sueltos en cualquier parte («2025 ... junio», «en enero»)."""
        year_match = re.search(r"(?<![0-9])((?:19|20)\d{2})(?![0-9])", text)
        month_match = re.search(r"(?<![a-z0-9])(" + MONTH_RE + r")(?![a-z0-9])", text)
        if year_match and month_match:
            year, month = int(year_match.group(1)), MONTHS[month_match.group(1)]
            phrase = " ".join(sorted({month_match.group(1), year_match.group(1)}))
            return self._month_range(year, month, year, month, phrase)
        if year_match:
            year = int(year_match.group(1))
            return self._range(date(year, 1, 1), date(year + 1, 1, 1), year_match.group(1))
        if month_match:
            return self._months_any_year([MONTHS[month_match.group(1)]], month_match.group(1))
        return None

    # ------------------------------------------------ API
    def parse(self, text):
        """Periodo de la pregunta normalizada, o None."""
        text = _compact_ordinals(text or "")
        if not text:
            return None
        for rule in (
            self._day_range, self._month_span, self._year_span, self._since,
            self._quarter_or_semester, self._relative_quarter_or_semester,
            self._last_n, self._single_day, self._month_with_year_ref,
            self._relative_single, self._legacy,
        ):
            period = rule(text)
            if period:
                period = self._narrow_to_month(period, text)
                tokens = set(period["phrase"].split())
                period["tokens"] = sorted(tokens)
                # Otros meses / años de la pregunta que el periodo no usa
                # («enero y marzo de 2025»): se declaran, nunca se pierden.
                period["ignored"] = [
                    word for word in dict.fromkeys(text.split())
                    if word not in tokens and (word in MONTHS or re.fullmatch(r"(?:19|20)\d{2}", word))
                ]
                return period
        return None

    def _narrow_to_month(self, period, text):
        """«este año ... en marzo» / «el año pasado en junio»: un mes del año del periodo."""
        if period.get("kind") != "year" or not period.get("relative") or not period.get("year"):
            return period
        rest = text.replace(period["phrase"], " ")
        match = re.search(r"(?<![a-z0-9])(" + MONTH_RE + r")(?![a-z0-9])", rest)
        if not match:
            return period
        year, month = period["year"], MONTHS[match.group(1)]
        narrowed = self._month_range(year, month, year, month, period["phrase"], relative=True)
        narrowed["phrase"] = f"{period['phrase']} {match.group(1)}"
        return narrowed

    def granularity(self, text):
        """Agrupación temporal pedida: {"unit": "month"|..., "phrase": "por mes"} o None."""
        text = text or ""
        for pattern in _GRANULARITY_RES:
            match = pattern.search(text)
            if not match:
                continue
            unit = match.groupdict().get("unit")
            if unit:
                key = "mes" if unit.startswith("mes") else unit
                value = _GRANULARITY_WORDS.get(key) or _GRANULARITY_WORDS.get(key.rstrip("s"))
            else:
                value = _GRANULARITY_ADJECTIVES.get(match.group("adj"))
            if value:
                return {"unit": value, "phrase": match.group(0)}
        return None

    def default_window(self, unit):
        """Periodo por defecto para agrupar cuando la pregunta no trae uno."""
        today = self.today
        tomorrow = today + timedelta(days=1)
        if unit == "month":
            y1, m1 = add_months(today.year, today.month, -12)
            y2, m2 = add_months(today.year, today.month, -1)
            return self._month_range(y1, m1, y2, m2, "", "últimos 12 meses", True)
        if unit in ("quarter", "semester"):
            size = 3 if unit == "quarter" else 6
            count = 4 if unit == "quarter" else 2
            first_current = ((today.month - 1) // size) * size + 1
            y2, m2 = add_months(today.year, first_current, -1)
            y1, m1 = add_months(today.year, first_current, -size * count)
            name = "trimestres" if size == 3 else "semestres"
            return self._month_range(y1, m1, y2, m2, "", f"últimos {count} {name}", True)
        if unit == "year":
            return self._range(date(today.year - 4, 1, 1), date(today.year + 1, 1, 1), "",
                               "últimos 5 años", relative=True, clip=True)
        if unit == "week":
            monday = today - timedelta(days=today.weekday())
            return self._range(monday - timedelta(days=7 * 7), tomorrow, "", "últimas 8 semanas",
                               relative=True, clip=False, daily=True, kind="range")
        return self._range(tomorrow - timedelta(days=30), tomorrow, "", "últimos 30 días",
                           relative=True, clip=False, daily=True, kind="range")


def _compact_ordinals(text):
    """«1 er trimestre» (de «1.er») -> «1er trimestre»."""
    return re.sub(r"(?<![0-9])([1-4])\s+(er|ero|ro|do|to|o|a)\s+(?=trimestre|semestre)", r"\1\2 ", text)


# ---------------------------------------------------------------- buckets
def split_period(period, unit, today=None):
    """Subperiodos de `period` por unidad («month», «quarter», «year»...).

    Cada uno: {"order", "label", "start", "end", "year", "month", "months",
    "daily"}. Devuelve None si el periodo no tiene límites (mes sin año) y
    se pide algo distinto de mes, o si superaría MAX_BUCKETS.
    """
    today = as_date(today) or date.today()
    if period.get("kind") == "months_any_year":
        if unit != "month":
            return None
        return [{
            "order": index, "label": f"{MONTH_NAMES[m]} (todos los años)",
            "start": None, "end": None, "year": None, "month": m, "months": [m], "daily": False,
        } for index, m in enumerate(period["months"], 1)]

    start, end = as_date(period["start"]), as_date(period["end"])
    buckets = []
    cursor = start
    while cursor < end:
        if unit == "day":
            following = cursor + timedelta(days=1)
            label = _short_date(cursor)
        elif unit == "week":
            following = cursor - timedelta(days=cursor.weekday()) + timedelta(days=7)
            label = f"semana del {_short_date(cursor)}"
        elif unit == "month":
            following = next_month_start(cursor.year, cursor.month)
            label = f"{MONTH_NAMES[cursor.month]} {cursor.year}"
        elif unit in ("quarter", "semester"):
            size = 3 if unit == "quarter" else 6
            index = (cursor.month - 1) // size + 1
            following = month_start(*add_months(cursor.year, (index - 1) * size + 1, size))
            name = "trimestre" if size == 3 else "semestre"
            label = f"{ORDINAL_LABELS[index]} {name} {cursor.year}"
        elif unit == "year":
            following = date(cursor.year + 1, 1, 1)
            label = str(cursor.year)
        else:
            return None
        bucket_end = min(following, end)
        partial = cursor != _unit_start(cursor, unit) or bucket_end != following
        if partial and bucket_end > today and unit != "day":
            label += " (hasta hoy)"
        last = bucket_end - timedelta(days=1)
        buckets.append({
            "order": len(buckets) + 1, "label": label,
            "start": cursor, "end": bucket_end,
            "year": cursor.year if cursor.year == last.year else None,
            "month": cursor.month if (cursor.year, cursor.month) == (last.year, last.month) else None,
            "months": None,
            "daily": unit in ("day", "week") or not (cursor.day == 1 and (bucket_end.day == 1 or bucket_end > today)),
        })
        if len(buckets) > MAX_BUCKETS:
            return None
        cursor = bucket_end
    return buckets


def _unit_start(value, unit):
    if unit == "week":
        return value - timedelta(days=value.weekday())
    if unit == "month":
        return month_start(value.year, value.month)
    if unit in ("quarter", "semester"):
        size = 3 if unit == "quarter" else 6
        return month_start(value.year, ((value.month - 1) // size) * size + 1)
    if unit == "year":
        return date(value.year, 1, 1)
    return value


def year_months(start, end):
    """[(año, mes), ...] de los meses que toca [start, end)."""
    result = []
    year, month = start.year, start.month
    last = end - timedelta(days=1)
    while (year, month) <= (last.year, last.month):
        result.append((year, month))
        year, month = add_months(year, month, 1)
    return result


def neutral_phrases(text):
    """«hasta hoy», «a la fecha»: frases temporales que no filtran por sí solas."""
    return [match.group(0) for match in _NEUTRAL_RE.finditer(text or "")]

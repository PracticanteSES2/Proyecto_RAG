"""Etapa «periodo»: columna de fecha, periodos de la pregunta y filtros temporales.

Tipos de columna, columna de fecha del indicador (auditoría: la de su tabla o su calendario
relacionado, la del evento que mide; r3 AI05), análisis de periodos (PeriodParser), filtros de
año/mes/rango, buckets, «estado actual» y corte del día (r5) y _periods_for_metric. Mixin de
QueryPlanBuilder, métodos movidos sin cambios.
"""
import logging
import re

from datetime import date, timedelta
from src.semantic.period_parser import (
    as_date,
    GRANULARITY_LABELS,
    MONTH_NAMES as PERIOD_MONTH_NAMES,
    MONTHS as PERIOD_MONTHS,
    neutral_phrases,
    PeriodParser,
    split_period,
    TO_DATE_WORDS,
    year_months,
)
from src.semantic.resolucion.texto import (
    _exact_phrase,
    _original_phrase,
    _stem_token,
    canonical_token,
    canonical_tokens,
    MONTHS,
    normalize_text,
    TEMPORAL_WORDS,
)

logger = logging.getLogger(__name__)


class PeriodoMixin:


    # ---------------- column types ----------------
    def _technical_column_types(self, semantic_model):
        key = normalize_text(semantic_model)
        cache = self.__dict__.setdefault("_column_type_cache", {})
        if key in cache:
            return cache[key]
        types = {}
        try:
            path = self.source_router.catalog_path_for_model(semantic_model, required=False)
            catalog = self._load_json(path, {}) if path else {}
        except Exception:
            catalog = {}
        for table in catalog.get("tables", []) or []:
            for column in table.get("columns", []) or []:
                types[(normalize_text(table.get("name")), normalize_text(column.get("name")))] = (
                    self._classify_data_type(column.get("data_type"))
                )
        cache[key] = types
        return types

    @staticmethod
    def _classify_data_type(data_type):
        text = normalize_text(data_type)
        if not text:
            return None
        if "date" in text or "time" in text:
            return "date"
        if any(item in text for item in ("int", "decimal", "double", "number", "currency", "float", "whole")):
            return "number"
        return "text"

    def _column_type(self, semantic_model, table, column):
        """'date' | 'number' | 'text' | None (desconocido) según el catálogo técnico."""
        types = self._technical_column_types(semantic_model)
        return types.get((normalize_text(table), normalize_text(column)))

    def _raw_column_type(self, semantic_model, table, column):
        """Tipo de dato tal cual lo trae el catálogo técnico («String», «Int64»...)
        o None. Solo columnas del mismo tipo exacto se consultan en lote."""
        key = normalize_text(semantic_model)
        cache = self.__dict__.setdefault("_raw_column_type_cache", {})
        if key not in cache:
            types = {}
            try:
                path = self.source_router.catalog_path_for_model(semantic_model, required=False)
                catalog = self._load_json(path, {}) if path else {}
            except Exception:
                catalog = {}
            for table_item in catalog.get("tables", []) or []:
                for column_item in table_item.get("columns", []) or []:
                    types[(normalize_text(table_item.get("name")), normalize_text(column_item.get("name")))] = (
                        column_item.get("data_type")
                    )
            cache[key] = types
        return cache[key].get((normalize_text(table), normalize_text(column)))

    # ---------------- time ----------------
    def _is_temporal_field(self, field):
        words = set()
        for value in [*field.get("aliases", []), field.get("column"), field.get("level")]:
            words.update(normalize_text(value).split())
        table = normalize_text(field.get("table"))
        column = normalize_text(field.get("column"))
        level = normalize_text(field.get("level"))
        return (
            table in {"calendario", "calendar", "fecha", "dates"}
            or level in {"ano", "mes", "dia", "year", "month", "day"}
            or bool(words & TEMPORAL_WORDS)
            or column in {"date", "fecha", "fecha servicio", "fecha atencion"}
        )

    def _is_period_field(self, field):
        """¿Es una columna de periodo (fecha, año, mes) y no una categoría
        con nombre temporal? DIA_SEMANA («1. LUNES»…) o un rango de horas de
        texto se agrupan como cualquier dimensión («por día de la semana»)."""
        if not self._is_temporal_field(field):
            return False
        model = field.get("semantic_model")
        if model and self._column_type(model, field.get("table"), field.get("column")) == "text":
            words = set(normalize_text(field.get("column")).replace("_", " ").split())
            if not words & {"ano", "anio", "year", "mes", "month", "fecha", "date"}:
                return False
        return True

    def _detect_year_month(self, question):
        normalized = normalize_text(question)
        year_match = re.search(r"\b(20\d{2})\b", normalized)
        year = int(year_match.group(1)) if year_match else None
        month = None
        month_name = None
        for name, number in MONTHS.items():
            if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", normalized):
                month = number
                month_name = name
                break
        return year, month, month_name

    def _temporal_role(self, field, semantic_model):
        """'date' | 'year' | 'month' | None para un campo temporal."""
        column_type = self._column_type(semantic_model, field.get("table"), field.get("column"))
        words = set(normalize_text(field.get("column")).split())
        if column_type == "date":
            return "date"
        if words & {"ano", "anio", "year"}:
            return "year"
        if words & {"mes", "month"}:
            return "month"
        if column_type is None and (words & {"date", "fecha"} or field.get("kind") == "hierarchy_level"):
            return "date"
        return None

    def _best_date_field(self, candidates, semantic_model=None):
        temporal = [
            field for field in candidates
            if self._is_temporal_field(field)
            and (semantic_model is None or self._temporal_role(field, semantic_model) == "date")
        ]
        metric = self.__dict__.get("_date_metric")
        if metric and semantic_model and temporal:
            # Con el indicador conocido: solo fechas que filtran SU tabla y,
            # entre ellas, la del evento que mide (`_metric_date_score`).
            try:
                temporal = self._metric_date_fields(temporal, metric, semantic_model)
            except Exception:
                logger.debug("no se pudieron acotar las fechas al indicador; se usan todas las temporales", exc_info=True)
        elif metric and semantic_model:
            # Ninguna fecha entre las candidatas (la tabla del indicador solo
            # tiene fechas de texto, CONSULTA_URGENCIAS): el calendario que la
            # filtra por sus relaciones, aunque sea a través de una dimensión.
            try:
                temporal = [
                    field for field in self._metric_date_fields([], metric, semantic_model)
                    if field.get("source") == "metric_calendar"
                ]
            except Exception:
                temporal = []
        if not temporal:
            return None

        def score(field):
            value = field.get("relevance_score", 0)
            column = normalize_text(field.get("column"))
            table = normalize_text(field.get("table"))
            if column in {"date", "fecha"}:
                value += 80
            if table in {"calendario", "calendar"}:
                value += 60
            if field.get("kind") == "hierarchy_level":
                value += 30
            return value + field.get("_metric_date_score", 0)

        temporal.sort(key=score, reverse=True)
        return temporal[0]

    # ---------------- fecha del indicador ----------------
    # Palabras de evento en nombres de columnas de fecha (FECHA_EGRESO,
    # FechaSolicitud...): la fecha de un evento distinto al que mide el
    # indicador no es su periodo (EGRESOS no se filtra por FECHA_INGRESO).
    _EVENT_STEMS = {
        _stem_token(word) for word in (
            "ingreso", "egreso", "salida", "entrada", "admision", "alta", "solicitud", "respuesta",
            "cierre", "apertura", "asignacion", "cita", "atencion", "triage", "registro", "creacion",
            "nacimiento", "cancelacion", "programacion", "cirugia", "orden", "factura", "radicacion",
            "vencimiento", "consulta", "interconsulta", "despacho", "entrega", "dispensacion",
            "facturacion", "glosa", "defuncion", "muerte", "parto", "remision", "llegada", "inicio", "fin",
        )
    }
    # Mismo evento con otro nombre (EGRESOS de BRIEFING usa SALIDA_SERV).
    _EVENT_SYNONYMS = [
        {_stem_token(word) for word in group} for group in (
            ("egreso", "salida", "alta"),
            ("ingreso", "entrada", "admision", "llegada"),
        )
    ]
    _TIME_OF_DAY_RE = re.compile(r"(?<![a-z])(?:hora|horas|tramo|tramohorario|time|minuto|turno)")
    _DATE_NOISE = {"fecha", "date", "fec", "hora", "dia", "de", "del", "la", "el"}

    def _metric_event_stems(self, metric):
        """(raíces del nombre del indicador y de su tabla, raíces de las
        columnas de su expresión). EGRESOS cuenta EGRESOS[INGRESO]: manda el
        nombre («egreso»), la columna contada pesa menos."""
        def stems_of(texts):
            stems = set()
            for text in texts:
                for token in normalize_text(str(text or "").replace("_", " ")).split():
                    if len(token) >= 4:
                        stems.add(_stem_token(token))
            return stems

        expression = str(metric.get("base_dax_expression") or metric.get("dax_expression") or "")
        expression += " " + str(metric.get("model_expression") or "")
        named = stems_of([metric.get("label"), metric.get("measure"), metric.get("table")])
        used = stems_of([metric.get("column"), *re.findall(r"\[([^\]]+)\]", expression)])
        for group in self._EVENT_SYNONYMS:
            if any(self._stem_in(stem, group) for stem in named):
                named |= group  # EGRESOS → también SALIDA_SERV / ALTA
        return named, used - named

    @staticmethod
    def _stem_in(stem, stems):
        """¿La raíz está en el conjunto, admitiendo que una sea prefijo de la
        otra («triag» de TRIAGES y «triage» de FECHA_TRIAGE)?"""
        return any(
            stem == other or (min(len(stem), len(other)) >= 4 and (stem.startswith(other) or other.startswith(stem)))
            for other in stems
        )

    def _date_column_stems(self, column):
        tokens = re.findall(r"[a-z]+", normalize_text(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(column or ""))
                                                       .replace("_", " ")))
        return {_stem_token(token) for token in tokens if token not in self._DATE_NOISE and len(token) >= 4}

    def _metric_date_tables(self, metric, semantic_model):
        """(tablas del indicador, dimensiones que lo filtran, {calendario:
        {table, column, from: [columnas del indicador que lo usan]}}) según las
        relaciones del modelo, o None si el modelo no las declara."""
        if not self._has_relationship_metadata(semantic_model):
            return None
        base = {**metric, "dax_expression": metric.get("base_dax_expression") or metric.get("dax_expression")}
        tables = {normalize_text(name) for name in self._expression_tables(semantic_model, base)}
        own = self._metric_fact_table(metric)
        if own and not self._CALENDAR_TABLE_RE.match(normalize_text(own)):
            tables.add(normalize_text(own))
        if not tables:
            return None
        relations = [
            relation for relation in self._technical_catalog(semantic_model).get("relationships", []) or []
            if relation.get("IsActive") is not False
        ]
        dimensions, calendars = set(), {}
        frontier = set(tables)
        for _ in range(2):  # dimensión y dimensión de la dimensión
            reached = set()
            for relation in relations:
                source = normalize_text(relation.get("FromTable"))
                target = normalize_text(relation.get("ToTable"))
                if source not in frontier or not target:
                    continue
                # Solo filtra la tabla una relación que llega por el lado «uno»
                # (un muchos-a-muchos por documento del paciente no es su fecha).
                if str(relation.get("ToCardinality") or "One").lower() != "one":
                    continue
                if self._CALENDAR_TABLE_RE.match(target):
                    if source in tables:
                        entry = calendars.setdefault(target, {
                            "table": relation.get("ToTable"), "column": relation.get("ToColumn"), "from": [],
                        })
                        entry["from"].append(relation.get("FromColumn"))
                        entry.pop("via", None)
                    elif not target.startswith("localdatetable"):
                        # Calendario de una dimensión que filtra la tabla del
                        # indicador (Calendario → OPORTUNIDAD_TRIAGE[FECHA] →
                        # CONSULTA_URGENCIAS): también filtra el indicador.
                        entry = calendars.setdefault(target, {
                            "table": relation.get("ToTable"), "column": relation.get("ToColumn"), "from": [],
                            "via": relation.get("FromTable"),
                        })
                        entry["from"].append(relation.get("FromColumn"))
                    continue
                reached.add(target)
            reached -= tables | dimensions
            dimensions |= reached
            frontier = reached
        return tables, dimensions, calendars

    def _metric_visual_date_tables(self, metric):
        """Tablas/columnas de fecha que los visuales del indicador usan como eje
        o filtro: {(tabla, columna)} normalizados."""
        index = self._visual_index()
        model = normalize_text(metric.get("semantic_model"))
        used = set()
        for appearance in metric.get("appearances") or []:
            visual = index.get((model, str(appearance.get("visual_id"))))
            if not visual:
                continue
            fields = list(visual.get("fields") or [])
            for scope in ("visual", "page"):
                try:
                    items = self._scope_filter_items(metric.get("semantic_model"), visual, scope)
                except Exception:
                    items = []
                fields.extend(item.get("field") or {} for item in items)
            for field in fields:
                if field.get("table") and field.get("column"):
                    used.add((normalize_text(field["table"]), normalize_text(field["column"])))
        return used

    def _metric_date_fields(self, temporal, metric, semantic_model):
        """Fechas candidatas puntuadas para el indicador (`_metric_date_score`).

        - Se descartan las de tablas que no filtran la del indicador (TRIAGES
          no se filtra por CONSULTAS PRIORITARIAS[FECHA], ligada solo por el
          documento del paciente).
        - Si no queda ninguna propia ni de un calendario relacionado, se usa
          la fecha de la propia tabla del indicador (TRIAGES[FECHA]).
        - Entre varias, la del evento que mide (EGRESOS → FECHA_EGRESO) y la
          que usan sus visuales del tablero como eje o filtro."""
        layout = self._metric_date_tables(metric, semantic_model)
        if layout is None:
            return temporal
        tables, dimensions, calendars = layout
        named_stems, used_stems = self._metric_event_stems(metric)
        visual_dates = self._metric_visual_date_tables(metric)

        def kind_of(field):
            table = normalize_text(field.get("table"))
            if table in tables:
                return "own"
            if table in calendars:
                return "calendar"
            if table in dimensions:
                return "dimension"
            return "foreign"

        pool = [dict(field) for field in temporal if kind_of(field) != "foreign"]
        # Su calendario relacionado (no los automáticos) y las fechas de su
        # propia tabla siempre compiten, aunque no estén entre las candidatas
        # (TRIAGES[FECHA] frente a TRIAGES[TramoHorario], la hora del día).
        present = {(normalize_text(field.get("table")), normalize_text(field.get("column"))) for field in pool}
        pool.extend(
            {"table": entry["table"], "column": entry["column"], "aliases": [entry["column"]],
             "kind": "column", "relevance_score": 0, "source": "metric_calendar"}
            for name, entry in calendars.items()
            if entry.get("column") and not name.startswith("localdatetable")
            and (name, normalize_text(entry["column"])) not in present
        )
        pool.extend(self._own_date_fields(metric, semantic_model, tables, pool))
        for field in pool:
            kind = kind_of(field)
            table = normalize_text(field.get("table"))
            columns = [field.get("column")]
            value = {"own": 150, "calendar": 160, "dimension": 20}[kind]
            if kind == "calendar":
                # Un calendario automático (LocalDateTable) es la fecha de la
                # columna de la tabla del indicador que lo usa.
                columns = [*calendars[table]["from"], field.get("column")]
                if table.startswith("localdatetable") or calendars[table].get("via"):
                    value = 140
            column_stems = set()
            for column in columns:
                column_stems |= self._date_column_stems(column)
            events = {stem for stem in column_stems if self._stem_in(stem, self._EVENT_STEMS)}
            if any(self._stem_in(stem, named_stems) for stem in events):
                value += 100  # FECHA_EGRESO para EGRESOS
            elif any(self._stem_in(stem, used_stems) for stem in events):
                value += 20
            elif events:
                value -= 60  # FECHA_INGRESO para EGRESOS
            if self._TIME_OF_DAY_RE.search(normalize_text(str(field.get("column") or "").replace("_", " "))):
                value -= 120  # hora o tramo horario: no es la fecha del periodo
            if (table, normalize_text(field.get("column"))) in visual_dates or (
                kind == "calendar" and any(item[0] == table for item in visual_dates)
            ):
                value += 120  # la fecha que usa el visual del tablero
            field["_metric_date_score"] = value
        return pool

    def _own_date_fields(self, metric, semantic_model, tables, existing):
        """Columnas de fecha de la tabla del indicador (catálogo técnico) como
        candidatas de periodo cuando las candidatas no la filtran."""
        seen = {(normalize_text(field.get("table")), normalize_text(field.get("column"))) for field in existing}
        result = []
        for entry in self._technical_catalog(semantic_model).get("tables", []) or []:
            if normalize_text(entry.get("name")) not in tables:
                continue
            for column in entry.get("columns") or []:
                name = column.get("name")
                if not name or column.get("is_hidden") or column.get("IsHidden"):
                    continue
                if self._classify_data_type(column.get("data_type")) != "date":
                    continue
                key = (normalize_text(entry.get("name")), normalize_text(name))
                if key in seen:
                    continue
                seen.add(key)
                result.append({
                    "table": entry.get("name"), "column": name, "aliases": [name],
                    "kind": "column", "relevance_score": 0, "source": "metric_own_date",
                })
        return result

    def _best_temporal_field(self, candidates, semantic_model, role):
        found = [
            field for field in candidates
            if self._is_temporal_field(field) and self._temporal_role(field, semantic_model) == role
        ]
        found.sort(key=lambda field: field.get("relevance_score", 0), reverse=True)
        return found[0] if found else None

    # ---------------- periodos (src/semantic/period_parser.py) ----------------
    def _today(self):
        """Fecha de referencia de los periodos relativos (inyectable en pruebas)."""
        value = self.__dict__.get("today")
        if callable(value):
            value = value()
        return as_date(value) or date.today()

    def _period_parser(self):
        return PeriodParser(self._today())

    @staticmethod
    def _strip_phrase(text, phrase):
        """Quita una frase temporal del texto normalizado (o sus meses/años sueltos)."""
        phrase = normalize_text(phrase)
        if not phrase:
            return text
        # Con la preposición que lo introduce: «servicio en 2024» -> «servicio».
        lead = r"(?:(?:en|de|del|durante|para|desde|hasta)\s+(?:(?:el|la|los|las)\s+)?)?"
        pattern = r"(?<![a-z0-9])" + lead + re.escape(phrase) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            text = re.sub(pattern, " ", text)
        else:
            for word in phrase.split():
                if word in PERIOD_MONTHS or re.fullmatch(r"(?:19|20)\d{2}", word):
                    text = re.sub(
                        r"(?<![a-z0-9])" + lead + re.escape(word) + r"(?![a-z0-9])", " ", text,
                    )
        return re.sub(r"\s+", " ", text).strip()

    def _analyze_periods(self, question, metric=None, matched_name=None):
        """Periodo y agrupación temporal de la pregunta.

        Devuelve {"period", "granularity", "tokens", "clean_question"}:
        `tokens` son las palabras que expresaron el periodo (no son filtros
        de dimensión) y `clean_question` la pregunta sin esas frases, para
        buscar agrupaciones y filtros explícitos sin confundirlas con valores.
        Una frase que forma parte del nombre de la métrica («Egresos año
        anterior», «Promedio mensual») no se toma como periodo.
        """
        normalized = normalize_text(question)
        parser = self._period_parser()
        period = parser.parse(normalized)
        granularity = parser.granularity(normalized)
        names = [
            normalize_text(name)
            for name in ((metric or {}).get("label"), (metric or {}).get("measure"), matched_name)
            if name
        ]

        def in_metric_name(phrase):
            phrase = normalize_text(phrase)
            return bool(phrase) and any(_exact_phrase(name, phrase) for name in names)

        if period and in_metric_name(period["phrase"]):
            period = None
        if granularity and in_metric_name(granularity["phrase"]):
            granularity = None

        clean = normalized
        tokens = set()
        phrases = [*(neutral_phrases(normalized))]
        if period:
            phrases.append(period["phrase"])
            tokens.update(canonical_token(word) for word in TO_DATE_WORDS)
            # «el día de ayer», «del día de hoy»: «día de» es parte del periodo.
            day_of = re.search(
                r"(?<![a-z0-9])(?:(?:el|del)\s+)?dia\s+de\s+(?=" + re.escape(normalize_text(period["phrase"])) + r")",
                normalized,
            )
            if day_of:
                phrases.append(day_of.group(0).strip())
        if granularity:
            phrases.append(granularity["phrase"])
        for phrase in phrases:
            tokens.update(canonical_tokens(phrase))
            clean = self._strip_phrase(clean, phrase)
        return {
            "period": period, "granularity": granularity,
            "tokens": tokens, "clean_question": clean, "question": question,
        }

    def _period_words(self, text):
        """Palabras canónicas de las expresiones de periodo del texto (con caché).

        Solo las que de verdad forman un periodo («este año», «últimos 3
        meses»): «días de estancia» no es un periodo y sigue contando.
        """
        cache = self.__dict__.setdefault("_period_words_cache", {})
        key = normalize_text(text)
        if key not in cache:
            if len(cache) > 512:
                cache.clear()
            cache[key] = frozenset(self._analyze_periods(key)["tokens"])
        return cache[key]

    def _month_values(self, field, semantic_model, months):
        """Valores de la columna MES para esos meses (número o nombre según su tipo)."""
        month_type = self._column_type(semantic_model, field["table"], field["column"])
        if month_type != "text":
            return list(months), "number"
        domain = self._get_values(semantic_model, field["table"], field["column"], essential=True) or []
        names = {normalize_text(item): item for item in domain}
        values = [names.get(PERIOD_MONTH_NAMES[month]) for month in months]
        if any(value is None for value in values):
            return None, "text"
        return values, "text"

    def _period_filters(self, period, candidates, semantic_model=None):
        """Filtros de un periodo según el TIPO real de las columnas temporales.

        Devuelve (filtros, términos_sin_aplicar, notas):
        - columna de fecha -> date_range [start, end) (o MONTH() IN {...} para
          meses sin año);
        - columnas AÑO/MES enteras (o MES de texto) -> filtros categóricos por
          valor: AÑO = 2025 + MES IN {1, 2, 3}; varios años completos -> AÑO IN
          {...}; meses de años distintos -> pares (AÑO, MES).
        Sin fecha diaria, un periodo por días no se aplica (se devuelve vacío).
        Cada filtro lleva `label` con el periodo legible («enero–marzo 2025»).
        """
        label = period.get("label")
        unapplied, notes = [], []
        kind = period.get("kind")
        months_any_year = kind == "months_any_year"
        if months_any_year:
            names = label if len(period["months"]) > 1 else period.get("month_name")
            notes.append(f"Mes sin año ({names}): se consideran todos los años.")

        date_field = (
            self._best_date_field(candidates, semantic_model) if semantic_model
            else self._best_date_field(candidates)
        )
        if date_field:
            item = {
                "type": "date_range",
                "table": date_field["table"],
                "column": date_field["column"],
                "year": period.get("year"),
                "month": period.get("month"),
                "month_name": period.get("month_name"),
                "label": label,
                "period_kind": kind,
                "source": "query_plan_temporal",
            }
            if months_any_year:
                item["months"] = list(period["months"])
            else:
                item["start"] = as_date(period["start"]).isoformat()
                item["end"] = as_date(period["end"]).isoformat()
            return [item], unapplied, notes

        if period.get("daily"):
            # AÑO/MES no bastan para «hoy», «ayer» o «últimos 7 días».
            return [], [f"periodo {label} (el tablero no tiene fecha diaria)"], notes

        year_field = self._best_temporal_field(candidates, semantic_model, "year")
        month_field = self._best_temporal_field(candidates, semantic_model, "month")

        def year_filter(values):
            single = len(values) == 1
            return {
                "type": "categorical", "concept": "año",
                "table": year_field["table"], "column": year_field["column"],
                "operator": "=" if single else "IN",
                "value": values[0] if single else None,
                **({} if single else {"values": list(values)}),
                "data_type": "number", "temporal": "year", "label": label,
                "source": "query_plan_temporal",
            }

        def month_filter(months):
            values, data_type = self._month_values(month_field, semantic_model, months)
            if values is None:
                return None
            single = len(values) == 1
            return {
                "type": "categorical", "concept": "mes",
                "table": month_field["table"], "column": month_field["column"],
                "operator": "=" if single else "IN",
                "value": values[0] if single else None,
                **({} if single else {"values": values}),
                "data_type": data_type, "temporal": "month", "label": label,
                "source": "query_plan_temporal",
            }

        filters = []
        if months_any_year:
            item = month_filter(period["months"]) if month_field else None
            if item:
                filters.append(item)
            else:
                unapplied.append(f"mes {label}")
            return filters, unapplied, notes

        pairs = year_months(as_date(period["start"]), as_date(period["end"]))
        years = sorted({year for year, _ in pairs})
        by_year = {year: [m for y, m in pairs if y == year] for year in years}
        whole_years = all(len(by_year[year]) == 12 for year in years)
        if len(years) == 1 or whole_years:
            if year_field:
                filters.append(year_filter(years))
            else:
                unapplied.append(f"año {', '.join(str(year) for year in years)}")
            if not whole_years:
                item = month_filter(by_year[years[0]]) if month_field else None
                if item:
                    filters.append(item)
                else:
                    unapplied.append(f"meses de {label}")
            return filters, unapplied, notes

        # Meses de años distintos (noviembre 2024–febrero 2025): pares (AÑO, MES).
        if year_field and month_field and self._column_type(
            semantic_model, month_field["table"], month_field["column"]
        ) != "text":
            filters.append({
                "type": "temporal_set", "concept": "año y mes",
                "columns": [
                    {"table": year_field["table"], "column": year_field["column"]},
                    {"table": month_field["table"], "column": month_field["column"]},
                ],
                "values": [[year, month] for year, month in pairs],
                "label": label, "temporal": "year_month",
                "source": "query_plan_temporal",
            })
        else:
            unapplied.append(f"periodo {label}")
        return filters, unapplied, notes

    def _temporal_filters(self, question, candidates, semantic_model=None):
        """Filtros del periodo de la pregunta según el TIPO real de la columna.

        Devuelve (filtros, términos_sin_aplicar, notas). Columna de fecha ->
        date_range; columnas enteras AÑO/MES -> filtro por valor numérico.
        Un mes sin año filtra el mes en todos los años y lo dice en las notas.
        """
        period = self._period_parser().parse(normalize_text(question))
        if not period:
            return [], [], []
        return self._period_filters(period, candidates, semantic_model)

    def _bucket_period(self, bucket):
        """Subperiodo de split_period con la forma de un periodo."""
        today = self._today()
        if bucket.get("start") is None:
            month = bucket["months"][0]
            return {
                "kind": "months_any_year", "months": [month], "year": None, "month": month,
                "month_name": PERIOD_MONTH_NAMES[month], "label": bucket["label"],
                "daily": False, "start": None, "end": None,
            }
        start, end = as_date(bucket["start"]), as_date(bucket["end"])
        last = end - timedelta(days=1)
        same_month = (start.year, start.month) == (last.year, last.month)
        return {
            "kind": "range", "start": start, "end": end,
            "year": start.year if start.year == last.year else None,
            "month": start.month if same_month else None,
            "month_name": None, "label": bucket["label"],
            "daily": bucket.get("daily", False), "to_date": end > today,
        }

    def _year_domain_period(self, candidates, semantic_model):
        """Años con datos (columna AÑO entera) como periodo para «por año» sin periodo."""
        year_field = self._best_temporal_field(candidates, semantic_model, "year")
        if not year_field or self._best_date_field(candidates, semantic_model):
            return None
        values = self._get_values(semantic_model, year_field["table"], year_field["column"], essential=True) or []
        years = sorted({int(v) for v in values if str(v).isdigit()})[-10:]
        if not years:
            return None
        parser = self._period_parser()
        period = parser._range(date(years[0], 1, 1), date(years[-1] + 1, 1, 1), "")
        period["label"] = f"{period['label']} (años con datos)"
        return period

    def _current_state_period(self, period):
        """¿El periodo incluye el día de hoy («hoy», «este mes», «este año»)?"""
        start, end = as_date(period.get("start")), as_date(period.get("end"))
        today = self._today()
        return bool(start and end and start <= today < end)

    def _daily_cut_for_today(self, period, metric):
        """Tabla del indicador que, según su documentación, es el corte del día
        anterior («Triages del día anterior») cuando la pregunta pide «hoy»;
        None en otro caso."""
        if not metric:
            return None
        from src.semantic.table_coverage import coverage_window

        start, end = as_date(period.get("start")), as_date(period.get("end"))
        today = self._today()
        if not (start and end and start == today and end <= today + timedelta(days=1)):
            return None
        model = normalize_text(metric.get("semantic_model"))
        for table in self._metric_coverage_tables(metric):
            text = self._table_coverage_text(model, table)
            if not text or not re.search(r"(?<![a-z])(?:del dia anterior|de ayer)(?![a-z])", normalize_text(text)):
                continue
            window = coverage_window(text, today)
            if window and window[0] == today - timedelta(days=1):
                return table
        return None

    def _snapshot_table(self, metric, candidates):
        """(tabla, tiene_fechas) de un indicador sin ninguna columna temporal
        válida (propia o relacionada) entre las candidatas: su tabla refleja el
        estado actual (CAMAS DISPONIBLES no tiene fechas; PACIENTES X
        ASEGURADORA tiene FechaSalida, que no es la fecha de un periodo). None
        si queda alguna fecha válida o no se conoce la tabla del indicador."""
        if metric is None or any(self._is_temporal_field(field) for field in candidates):
            return None
        entry = self._fact_table_entry(metric)
        if not entry or not entry.get("columns"):
            return None
        dated = any(
            self._classify_data_type(column.get("data_type")) == "date"
            or set(normalize_text(column.get("name")).split()) & TEMPORAL_WORDS
            for column in entry.get("columns") or []
        )
        return entry.get("name"), dated

    def _apply_temporal(self, analysis, candidates, semantic_model, group_by, metric=None):
        """`_apply_temporal_for` con el indicador como contexto de la columna
        de fecha (`_best_date_field` elige la fecha que filtra SU tabla)."""
        previous = self.__dict__.get("_date_metric")
        self._date_metric = metric
        try:
            return self._apply_temporal_for(analysis, candidates, semantic_model, group_by, metric)
        finally:
            self._date_metric = previous

    def _apply_temporal_for(self, analysis, candidates, semantic_model, group_by, metric=None):
        """Filtros del periodo + agrupación temporal («por mes») del plan.

        Devuelve {"filters", "unapplied", "notes", "unsupported_period",
        "group", "buckets"}. La agrupación usa subperiodos explícitos
        (`buckets`, uno por mes/trimestre/año...) que el generador DAX evalúa
        con los mismos filtros de periodo: funciona igual con columna de fecha
        o con columnas AÑO/MES enteras. Si no se puede agrupar, se declara.
        Las fechas de tablas que no filtran el indicador ya no están en
        `candidates` (`_metric_dimensions`): «hoy» sobre una tabla sin fecha
        (estado actual, p. ej. CAMAS DISPONIBLES) responde el valor actual.
        """
        result = {
            "filters": [], "unapplied": [], "notes": [], "unsupported_period": None,
            "group": None, "buckets": [],
        }
        period = analysis.get("period")
        granularity = analysis.get("granularity")
        cut = self._daily_cut_for_today(period, metric) if period else None
        if cut:
            # «hoy» sobre una tabla que es el corte del día anterior (TRIAGES
            # del BRIEFING): filtrar hoy daría vacío; se responde el corte
            # del tablero y se dice de cuándo es.
            phrase = _original_phrase(analysis.get("question") or "", period.get("phrase")) or period.get("label")
            result["notes"].append(
                f"«{phrase}»: la tabla {cut} trae solo el corte del día anterior según su documentación; "
                "se muestra ese corte (la cifra del tablero), no la de hoy."
            )
            result["current_state"] = True
            result["daily_cut"] = cut
            period = None
        if period:
            filters, unapplied, notes = self._period_filters(period, candidates, semantic_model)
            snapshot = None if filters else self._snapshot_table(metric, candidates)
            phrase = _original_phrase(analysis.get("question") or "", period.get("phrase")) or period.get("label")
            if not filters and snapshot and self._current_state_period(period):
                table, dated = snapshot
                why = (
                    "el tablero no usa ninguna de sus fechas como periodo" if dated
                    else "la tabla refleja el momento presente, sin histórico por fechas"
                )
                result["notes"].append(f"«{phrase}»: se muestra el estado actual de {table} ({why}).")
                result["current_state"] = True
                period = None
            elif not filters:
                result["unsupported_period"] = period
                result["unapplied"] = unapplied
                if snapshot:
                    # Un periodo pasado en una tabla de estado actual: se dice por qué.
                    result["explanation"] = (
                        f"{metric.get('label')} muestra el estado actual de {snapshot[0]}: no tiene "
                        f"una fecha con la que filtrar «{phrase}»."
                    )
                return result
        if period:
            result["filters"].extend(filters)
            result["unapplied"].extend(unapplied)
            result["notes"].extend(notes)
            for word in period.get("ignored") or []:
                what = "mes" if word in PERIOD_MONTHS else "año"
                result["unapplied"].append(f"{what} {word} (solo se aplicó {period['label']})")

        if not granularity:
            return result
        unit = granularity["unit"]
        name = GRANULARITY_LABELS[unit]
        if group_by:
            result["unapplied"].append(
                f"agrupar por {name.lower()} (ya se agrupa por {group_by[0].get('column')})"
            )
            return result

        base = period
        if base is None:
            base = (self._year_domain_period(candidates, semantic_model) if unit == "year" else None) \
                or self._period_parser().default_window(unit)
            filters, unapplied, _ = self._period_filters(base, candidates, semantic_model)
            if filters and not unapplied:
                result["filters"].extend(filters)
                result["notes"].append(f"Sin periodo en la pregunta: se muestra {base['label']}.")
        buckets = split_period(base, unit, self._today())
        if not buckets:
            result["unapplied"].append(
                f"agrupar por {name.lower()} (más de 62 periodos o periodo sin año: acota el periodo)"
            )
            return result
        planned = []
        table = None
        for bucket in buckets:
            filters, unapplied, _ = self._period_filters(
                self._bucket_period(bucket), candidates, semantic_model,
            )
            if not filters or unapplied:
                result["unapplied"].append(
                    f"agrupar por {name.lower()} (el tablero no tiene la columna de fecha necesaria)"
                )
                # Sin agrupación, el filtro por defecto ya no tiene sentido.
                if period is None:
                    result["filters"] = []
                    result["notes"] = [n for n in result["notes"] if not n.startswith("Sin periodo")]
                return result
            table = table or filters[0].get("table") or (filters[0].get("columns") or [{}])[0].get("table")
            planned.append({"order": bucket["order"], "label": bucket["label"], "filters": filters})
        result["buckets"] = planned
        result["group"] = {
            "table": table, "column": name, "label": name,
            "source": "query_plan_temporal_group", "temporal": unit,
        }
        return result

    def _periods_for_metric(self, question, metric, matched_name):
        """_analyze_periods, salvo una medida atada al MISMO año que pide la
        pregunta (TRIAGES_PEDIATRICOS_2025 «en 2025»): ahí el año sí se aplica
        como filtro (no cambia el valor y deja el periodo explícito en la
        respuesta). Con otro año, o sin año en la medida, nada cambia."""
        temporal = self._analyze_periods(question, metric, matched_name)
        if temporal.get("period") is not None:
            return temporal
        names = [metric.get("label"), metric.get("measure"), matched_name]
        name_years = {
            int(token) for name in names if name
            for token in canonical_tokens(name) if re.fullmatch(r"(?:19|20)\d{2}", token)
        }
        if not name_years:
            return temporal
        plain = self._analyze_periods(question)
        period = plain.get("period")
        if plain.get("granularity") and not temporal.get("granularity"):
            return temporal  # «mensual» era parte del nombre: no se agrupa
        if period and period.get("kind") == "year" and period.get("year") in name_years:
            self._note(
                f"la medida {metric.get('label')} ya es del año {period.get('year')}; "
                "el año pedido se aplica igual como filtro"
            )
            return plain
        return temporal

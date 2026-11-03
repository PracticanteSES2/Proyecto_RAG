"""Etapa «filtros»: valores de dimensión explícitos, implícitos y aproximados.

Palabras de alcance («en el hospital», «general»: no son filtro), tipo de medida, valores
documentados, «por X»/«de X» explícitos, valores implícitos (_resolve_implicit_filter /
_resolve_implicit_value) con sus guardas contra espurios (auditoría: «total» ≠ SALUD TOTAL,
«interconsultas» ≠ INTERCONSULTAS SAS; r2 BH11/BH16/FC02/FC04), familias de valores (r5, r6 H05) y
valores aproximados de calificativos (_fuzzy_qualifier_filters). Mixin de QueryPlanBuilder, métodos
movidos sin cambios.
"""
import json
import re

from src.providers.domain_cache import identifier_column
from src.semantic import plan_budget
from src.semantic.resolucion.texto import (
    _alias_prefix,
    _GROUP_NEUTRAL_TAIL_WORDS,
    _is_question_form_word,
    _is_request_word,
    _phrase_score,
    _QUESTION_FORM_TOKENS,
    _tokens_match_loosely,
    _TRAILING_DETAIL_RE,
    _unique_strings,
    _value_words,
    _word_in_text,
    canonical_token,
    canonical_tokens,
    FILTER_NEUTRAL_WORDS,
    GENERIC_QUERY_WORDS,
    MONTHS,
    normalize_text,
    STOPWORDS,
    value_contradiction,
)


class FiltrosMixin:


    # ---------------- valores categóricos documentados ----------------
    def _documented_values_index(self):
        """{modelo normalizado: [(tabla normalizada o None, columna, [valores])]}
        de data/model_metadata/*/_documented_values.json (valores CASE/IN del
        SQL documentado y literales DAX; tools/local_data). table=None: aplica
        a las columnas con ese nombre en cualquier tabla."""
        cached = self.__dict__.get("_documented_values_cache")
        if cached is not None:
            return cached
        index = {}
        root = self.project_root / "data" / "model_metadata"
        try:
            paths = sorted(root.glob("*/_documented_values.json")) if root.exists() else []
        except OSError:
            paths = []
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            model = normalize_text(payload.get("semantic_model"))
            for item in payload.get("columns") or []:
                if not isinstance(item, dict) or not item.get("column"):
                    continue
                values = [str(value) for value in item.get("values") or [] if value not in (None, "")]
                if values:
                    table = normalize_text(item.get("table")) or None
                    index.setdefault(model, []).append((table, str(item["column"]), values))
        self._documented_values_cache = index
        return index

    def _table_documented_values(self, semantic_model, table):
        """[(columna, [valores])] documentados (o filtros estáticos del PBIR)
        de las columnas de `table` en el modelo."""
        table_norm = normalize_text(table)
        if not table_norm:
            return []
        columns = {}
        for item in self._technical_catalog(semantic_model).get("tables", []) or []:
            if normalize_text(item.get("name")) == table_norm:
                for column in item.get("columns", []) or []:
                    if column.get("name"):
                        columns[normalize_text(column.get("name"))] = column.get("name")
        result = {}
        for doc_table, column, values in self._documented_values_index().get(normalize_text(semantic_model), []):
            column_norm = normalize_text(column)
            if doc_table == table_norm or (doc_table is None and column_norm in columns):
                name = columns.get(column_norm, column)
                result.setdefault(name, [])
                result[name].extend(value for value in values if value not in result[name])
        model_norm = normalize_text(semantic_model)
        for (model, static_table, column), values in self.static_values.items():
            if model == model_norm and static_table == table_norm:
                name = columns.get(column, column)
                result.setdefault(name, [])
                result[name].extend(value for value in values if value not in result[name])
        return list(result.items())

    def _name_inside_value_phrase(self, business_question, item):
        """Valor documentado (de varias palabras, todas en la pregunta) de la
        tabla del candidato que contiene todas las palabras con que coincidió
        su nombre, o None: «hospitalización general» contiene HOSPITALIZACIÓN."""
        metric = item.get("metric") or {}
        name_tokens = [token for token in self._name_key(item.get("matched_name")) if len(token) >= 3]
        if not name_tokens:
            return None
        question_words = normalize_text(business_question).split()
        table = self._metric_fact_table(metric)
        for _, values in self._table_documented_values(metric.get("semantic_model"), table):
            for value in values:
                words = [word for word in _value_words(value) if len(word) >= 3]
                if len(words) < 2 or len(words) <= len(name_tokens):
                    continue
                if not all(_word_in_text(word, words, question_words) for word in words):
                    continue
                if all(any(_tokens_match_loosely(token, canonical_token(word)) for word in words)
                       for token in name_tokens):
                    return value
        return None

    # ---------------- alcance «todo el hospital» ----------------
    # «en el hospital», «de la clínica», «en la institución»: el lugar donde se
    # mide todo; «ocupación general», «el total», «global», «institucional»:
    # sin filtro. Nunca son un filtro, un término «no aplicado» ni motivo para
    # explorar valores de columnas.
    _SCOPE_PLACE_WORDS = {"hospital", "institucion", "clinica"}
    _SCOPE_ADJECTIVE_WORDS = {"general", "global", "total", "institucional", "institucionales"}
    _SCOPE_CONNECTORS = {
        "en", "de", "del", "la", "el", "los", "las", "a", "al", "para", "todo", "toda",
        "nivel", "este", "esta", "nuestro", "nuestra", "y",
    }
    _SCOPE_FOLLOWERS = {"hoy", "ayer", "actualmente", "ahora", "actual", "manana"}
    # Palabras sueltas demasiado genéricas para elegir por sí solas un valor de
    # varias palabras («general» no es HOSPITALIZACIÓN GENERAL).
    _GENERIC_VALUE_WORDS = _SCOPE_ADJECTIVE_WORDS | {
        "otro", "otra", "otros", "otras", "todo", "toda", "todos", "todas", "varios",
        "varias", "normal", "comun", "nuevo", "nueva", "principal",
    }

    def _scope_words(self, question, metric):
        """Palabras de la pregunta que solo dicen «todo el hospital»:
        - lugar («hospital», «institución», «clínica») precedido de en/de/del
          (+ artículo) y no seguido de otra palabra con contenido («hospital
          día» sí puede ser un valor);
        - «general», «global», «total», «institucional» al inicio, tras un
          conector («en general») o tras una palabra que explica el indicador
          («ocupación general»). Tras otra palabra («hospitalización general»)
          son parte de un valor y no se tocan."""
        words = normalize_text(question).split()
        if not words:
            return []
        vocabulary = self._metric_vocabulary_tokens(metric or {}, with_pages=False)
        period_words = set(self._period_words(question))
        stop = {canonical_token(word) for word in STOPWORDS}
        found = []
        for index, word in enumerate(words):
            if word in self._SCOPE_PLACE_WORDS:
                previous = words[index - 1] if index else ""
                following = words[index + 1] if index + 1 < len(words) else ""
                if previous not in self._SCOPE_CONNECTORS:
                    continue
                if following and not (
                    following in self._SCOPE_CONNECTORS or following in self._SCOPE_FOLLOWERS
                    or canonical_token(following) in stop or canonical_token(following) in period_words
                    or following.isdigit() or following in MONTHS
                ):
                    continue
                found.append(word)
            elif word in self._SCOPE_ADJECTIVE_WORDS:
                position = index - 1
                while position >= 0 and words[position] in self._SCOPE_CONNECTORS:
                    position -= 1
                if position < 0 or position < index - 1:
                    found.append(word)
                    continue
                previous = canonical_token(words[position])
                if (
                    previous in stop or _is_request_word(previous)
                    or self._explains(previous, vocabulary)
                ):
                    found.append(word)
        return found

    # ---------------- palabras del tipo de medida ----------------
    # «porcentaje de inasistencia», «tasa de...», «promedio de...», «total
    # de...», «cantidad de...», «número de...»: dicen QUÉ TIPO de dato se pide,
    # no un filtro. Las explica un indicador de ese tipo (%, promedio, conteo
    # o suma) aunque su nombre no las contenga (%INASISTENCIA).
    _MEASURE_TYPE_WORDS = {
        "porcentaje": "percent", "porcentual": "percent", "%": "percent", "tasa": "percent",
        "proporcion": "percent", "promedio": "average", "total": "amount",
        "cantidad": "amount", "numero": "amount", "conteo": "amount", "suma": "amount",
        "sumatoria": "amount", "recuento": "amount",
    }
    # Formas genéricas de nombrar un indicador, de cualquier tipo de dato.
    _INDICATOR_FORM_WORDS = {"nivel", "niveles", "indice", "indices", "grado", "indicador"}
    _AVERAGE_FUNCTION_RE = re.compile(r"\b(?:AVERAGE|AVERAGEX|AVERAGEA|MEDIAN|MEDIANX)\s*\(", re.IGNORECASE)
    _AMOUNT_FUNCTION_RE = re.compile(
        r"\b(?:SUM|SUMX|COUNT|COUNTA|COUNTX|COUNTAX|COUNTROWS|DISTINCTCOUNT|DISTINCTCOUNTNOBLANK)\s*\(",
        re.IGNORECASE,
    )

    # Nombres de indicadores de cosas aún pendientes: «sin respuesta», «en espera»...
    _PENDING_LABEL_RE = re.compile(
        r"(?<![a-z0-9])(?:sin\s+(?:respuesta|responder|atender|atencion|cerrar|cierre|resolver|asignar|gestion"
        r"|entregar|entrega)|en\s+espera|por\s+(?:responder|atender|entregar|asignar))(?![a-z0-9])"
    )

    def _metric_measure_kinds(self, metric):
        """Tipos de dato que da el indicador: {'percent', 'average', 'amount'}."""
        label = normalize_text(f"{metric.get('label') or ''} {metric.get('measure') or ''}")
        expression = " ".join(
            str(value) for value in (
                metric.get("base_dax_expression") or metric.get("dax_expression"), metric.get("model_expression"),
                self._measure_expression(metric.get("semantic_model"), metric),
            ) if value
        )
        fmt = str(metric.get("format_string") or metric.get("format") or "")
        kinds = set()
        if (
            "%" in label or "%" in fmt or fmt.lower() == "percent"
            or re.search(r"(?<![a-z])(?:porcentaje|tasa|proporcion|indice)(?![a-z])", label)
        ):
            kinds.add("percent")
        elif re.search(r"\bDIVIDE\s*\(", expression, re.IGNORECASE) and not self._AVERAGE_FUNCTION_RE.search(expression):
            kinds.add("percent")
        if "promedio" in label.split() or self._AVERAGE_FUNCTION_RE.search(expression):
            kinds.add("average")
        if not kinds and (
            self._AMOUNT_FUNCTION_RE.search(expression)
            or re.search(r"(?<![a-z])(?:total|cantidad|numero|conteo)(?![a-z])", label)
        ):
            kinds.add("amount")
        return kinds

    def _measure_type_words(self, question, metric):
        """Palabras de la pregunta que solo dicen el tipo de dato y que el
        indicador elegido da («porcentaje» con %INASISTENCIA): no son filtros."""
        kinds = self._metric_measure_kinds(metric or {})
        words = normalize_text(question).split()
        found = []
        for index, word in enumerate(words):
            following = words[index + 1] if index + 1 < len(words) else ""
            # «nivel de ocupación», «índice de rotación», «grado de...»: forma
            # de nombrar un indicador (cualquier tipo), nunca un filtro. Solo
            # seguida de «de/del» («nivel 3» sí puede ser un valor).
            if word in self._INDICATOR_FORM_WORDS and following in ("de", "del"):
                found.append(word)
                continue
            if not kinds:
                continue
            kind = self._MEASURE_TYPE_WORDS.get(word) or self._MEASURE_TYPE_WORDS.get(canonical_token(word))
            if kind and kind in kinds:
                found.append(word)
        return found

    # ---------------- palabra de la tabla que además es un valor ----------------
    def _table_word_filters(self, metric, words, candidates, used_fields, semantic_model):
        """Palabras que solo explica el NOMBRE DE LA TABLA del indicador (no su
        etiqueta, medida ni títulos) y que además son un valor categórico
        documentado de una columna de esa tabla: se filtran en lugar de darlas
        por explicadas. «camas disponibles» con CAMAS (tabla CAMAS
        DISPONIBLES) -> ESTADOS_CAM = DISPONIBLE. Devuelve [(palabra, campo, resuelto)]."""
        table = self._metric_fact_table(metric)
        table_tokens = [token for token in canonical_tokens(table) if len(token) >= 3]
        if not table_tokens or not words:
            return []
        names = [metric.get("label"), metric.get("measure")]
        names.extend(appearance.get("visual_title") for appearance in metric.get("appearances") or [])
        name_tokens = {
            token for name in names if name and "." not in str(name)
            for token in canonical_tokens(name) if len(token) >= 3
        }
        documented = self._table_documented_values(semantic_model, table)
        if not documented:
            return []
        used = set(used_fields)
        found = []
        for word in words:
            token = canonical_token(word)
            if not self._explains(token, table_tokens) or self._explains(token, name_tokens):
                continue
            for column, values in documented:
                key = (normalize_text(table), normalize_text(column))
                if key in used:
                    continue
                # Valor de una sola palabra (sin conectores) que es esta palabra.
                matches = [
                    value for value in values
                    if len(_value_words(value)) == 1 and _tokens_match_loosely(token, canonical_token(_value_words(value)[0]))
                ]
                if len(matches) != 1:
                    continue
                value = matches[0]
                field = next(
                    (item for item in candidates
                     if (normalize_text(item.get("table")), normalize_text(item.get("column"))) == key),
                    None,
                ) or {"table": table, "column": column, "aliases": [column], "kind": "column"}
                # Se confirma con el dominio real si se puede (con su forma escrita).
                domain = self._get_values(semantic_model, field["table"], field["column"])
                if domain:
                    actual = next((item for item in domain if normalize_text(item) == normalize_text(value)), None)
                    if actual is None:
                        continue
                    value = actual
                used.add(key)
                found.append((word, field, {
                    "value": value, "score": 1.0, "phrase": word,
                    "tokens": {token, *canonical_tokens(value)},
                }))
                break
        return found

    def _generic_partial_value(self, span_tokens, value_tokens, question):
        """¿El calificativo es solo una palabra genérica («general») que cubre
        parte de un valor de varias palabras cuyo resto no está en la pregunta?"""
        generic = {canonical_token(word) for word in self._GENERIC_VALUE_WORDS}
        if not span_tokens or not all(token in generic for token in span_tokens):
            return False
        rest = [
            token for token in value_tokens
            if not any(_tokens_match_loosely(token, other) for other in span_tokens)
        ]
        if not rest:
            return False
        question_tokens = canonical_tokens(question)
        return not all(
            any(_tokens_match_loosely(token, other) for other in question_tokens) for token in rest
        )

    # Alcance de toda la institución («la institución», «el hospital»): no es
    # un valor de la dimensión agrupada.
    _SCOPE_GROUP_WORDS = {canonical_token(word) for word in ("institucion", "hospital", "clinica", "entidad")}

    def _detect_group_or_dimension_filter(self, question, metric, candidates, source_context=None):
        normalized = normalize_text(question)
        match = re.search(
            r"\b(?:por|segun|agrupado por|agrupada por|desglosado por|desglosada por)\s+(?:el|la|los|las)?\s*(.+)$",
            normalized,
        )
        if not match:
            return {"group_by": [], "explicit_filters": []}

        tail = self._clean_tail(match.group(1), metric)
        tail = self._strip_group_interrogative(tail) if tail else tail
        if not tail:
            return {"group_by": [], "explicit_filters": []}

        best = self._best_dimension(tail, candidates, exclude_temporal=True)
        if not best or not any(_alias_prefix(tail, alias) for alias in best.get("aliases") or []):
            # Ningún nombre de columna abre la cola: la dimensión puede
            # nombrarse por su descripción documentada («rango de horas»).
            described = self._described_group_field(tail, candidates)
            if described is not None:
                field, phrase = described
                return {"group_by": [field], "explicit_filters": [], "phrase": phrase}
        if not best:
            return {"group_by": [], "explicit_filters": []}

        matched_alias = None
        aliases = sorted(best.get("aliases", []), key=lambda value: len(normalize_text(value)), reverse=True)
        for alias in aliases:
            alias_norm = normalize_text(alias)
            if alias_norm and (tail == alias_norm or tail.startswith(alias_norm + " ")):
                matched_alias = alias_norm
                break
        # Plural/género del nombre («por aseguradores» = ASEGURADORA/ASEGURADOR;
        # «por areas de servicio» = AREA DE SERVICIO entero, no «areas» + valor
        # «de servicio»): gana la coincidencia que cubre más palabras.
        loose = max(
            (prefix for prefix in (_alias_prefix(tail, alias) for alias in aliases) if prefix),
            key=lambda prefix: len(prefix.split()), default=None,
        )
        if loose and (not matched_alias or len(loose.split()) > len(matched_alias.split())):
            matched_alias = loose
        if not matched_alias:
            return {"group_by": [], "explicit_filters": []}

        remainder = tail[len(matched_alias):].strip()
        # «peso por servicio en lavanderia»: lo que sigue a la dimensión con
        # «en» es el tablero/informe nombrado, no un valor de SERVICIO.
        if re.match(r"^en\s+", remainder) and self._names_board(remainder, source_context, metric):
            self._note(
                f"«{matched_alias} {remainder}»: «{remainder}» nombra el tablero; "
                f"se agrupa por {best.get('table')}[{best.get('column')}] (no es un valor del filtro)"
            )
            return {"group_by": [best], "explicit_filters": [], "phrase": matched_alias}
        remainder = re.sub(r"^(?:de|del|en|igual a|=)\s+", "", remainder).strip()
        # «por aseguradora, las 5 más altas»: un ranking, no un valor.
        top, _ = self._postfix_top(remainder)
        if top is not None and not remainder[:top.start()].strip(" ,;"):
            self._note(
                f"«{matched_alias} {remainder}»: «{top.group(0)}» pide un ranking, no un valor de "
                f"{best.get('table')}[{best.get('column')}]; se agrupa"
            )
            remainder = remainder[top.end():].strip(" ,;")
        # «por asegurador en total / en general»: forma de la pregunta, no el
        # valor SALUD TOTAL EPS; se agrupa.
        content = [
            word for word in remainder.split()
            if word not in _GROUP_NEUTRAL_TAIL_WORDS and not _is_question_form_word(word)
            and canonical_token(word) not in self._content_ignored_tokens()
            and canonical_token(word) not in self._SCOPE_GROUP_WORDS
        ]
        # «por qué motivos CANCELÓ CITAS LA INSTITUCIÓN»: lo que sigue a la
        # dimensión son verbos o palabras que el propio indicador dice (su
        # nombre, página o nombre funcional), no un valor de la dimensión.
        if remainder and content and metric and not self.implied_words(metric, content)[1]:
            content = []
        if remainder and not content:
            self._note(
                f"«{matched_alias} {remainder}»: «{remainder}» no es un valor de "
                f"{best.get('table')}[{best.get('column')}]; se agrupa"
            )
            remainder = ""
        if not remainder:
            return {"group_by": [best], "explicit_filters": [], "phrase": matched_alias}
        return {"group_by": [], "explicit_filters": [{"field": best, "value_hint": remainder, "from_group": True}]}

    def _remove_metric_and_report_phrases(self, question, metric, source_context):
        """Descarta los nombres de métrica/informe ANTES de buscar filtros.

        Antes, un campo llamado EGRESOS se interpretaba como dimensión
        dentro de la expresión EGRESOS PROBABLES y exigía un valor «probables hay».
        """
        cleaned = normalize_text(question)
        phrases = [
            metric.get("label"),
            source_context.get("report"), source_context.get("semantic_model"),
            metric.get("semantic_model"),
            *self._metric_reports(metric),
        ]
        # Quitar matched_name si es alias coincidente con la pregunta se
        # gestiona adicionalmente en _implicit_value_text.
        for phrase in sorted(_unique_strings(phrases), key=len, reverse=True):
            norm = normalize_text(phrase)
            if norm:
                cleaned = re.sub(r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", " ", cleaned)
        cleaned = re.sub(r"\b(?:tablero|informe)\b", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    # Palabras con las que no empieza el valor de un filtro «<columna> <valor>»:
    # preposiciones y verbos conjugados (copulativos y auxiliares).
    _VALUE_INVALID_START = {
        "hay", "hubo", "habia", "habra", "tiene", "tienen", "tenia", "tenian", "tenemos",
        "es", "son", "era", "eran", "fue", "fueron", "sera", "seran",
        "esta", "estan", "estaba", "estaban", "estuvo", "estuvieron", "estara", "estaran",
        "queda", "quedan", "quedaba", "quedaban", "quedaron", "sigue", "siguen",
        "va", "van", "iba", "iban", "ha", "han", "habian", "se",
        "por", "para", "con",
    }

    def _detect_explicit_dimension_filters(
        self, question, candidates, already_fields=None,
        metric=None, source_context=None,
    ):
        """Filtros «<dimensión> <valor>» pedidos de forma explícita.

        Cada mención («sede norte») produce UN filtro: el campo mejor ubicado
        (el de la tabla de la métrica / visuales de la métrica) y, como
        respaldo, los demás campos con el mismo alias en `alternatives`.
        """
        normalized = (
            self._remove_metric_and_report_phrases(question, metric, source_context or {})
            if metric else normalize_text(question)
        )
        already_fields = already_fields if already_fields is not None else set()
        metric_table = normalize_text((metric or {}).get("table"))

        def priority(field):
            bonus = 60 if metric_table and normalize_text(field.get("table")) == metric_table else 0
            return -(field.get("relevance_score", 0) + bonus)

        ordered = sorted(candidates, key=priority)
        mentions = {}
        order = []
        for field in ordered:
            if self._is_temporal_field(field):
                continue
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in already_fields:
                continue
            aliases = sorted(field.get("aliases", []), key=lambda v: len(normalize_text(v)), reverse=True)
            for alias in aliases:
                alias_norm = normalize_text(alias)
                if not alias_norm or len(alias_norm) < 3:
                    continue
                pattern = (
                    r"(?<![a-z0-9])" + re.escape(alias_norm) + r"(?![a-z0-9])"
                    + r"(?:\s+(?:de|del|igual a|=|:))?"
                    # {0,80}: un código de una letra al final («sexo M»)
                    # también vale cuando se quitó «en el tablero ...».
                    + r"\s+([a-z0-9][a-z0-9\s\.\-]{0,80})"
                )
                match = re.search(pattern, normalized)
                if not match:
                    continue
                # «en qué turno se lava más ropa», «cuál servicio tuvo más»: la
                # dimensión es lo que se pregunta (agrupación), no «<dimensión>
                # <valor>».
                if re.search(r"(?<![a-z0-9])(?:que|cual|cuales)\s*$", normalized[:match.start()]):
                    continue
                hint = re.split(
                    r"\b(?:en|durante|para el|para la|del tablero|del informe|y|con|pero)\b",
                    match.group(1), maxsplit=1,
                )[0].strip()
                # «servicio de urgencias» es filtro; «servicio por...»,
                # «servicio hay...» o «servicio en ...» no lo son. Tampoco lo
                # que empieza por un verbo conjugado («de cama ESTÁN
                # pendientes»): un valor se nombra, no se conjuga.
                tokens = canonical_tokens(hint)
                if (
                    not hint or not tokens or tokens[0] in self._VALUE_INVALID_START
                    or normalize_text(hint).split()[0] in self._VALUE_INVALID_START
                ):
                    continue
                if len(hint.split()) == 1 and hint in GENERIC_QUERY_WORDS:
                    continue
                # «…, las 5 más altas» es un ranking, no un valor.
                top, _ = self._postfix_top(normalize_text(hint))
                if top is not None and top.start() == 0:
                    continue
                if all(
                    word in _GROUP_NEUTRAL_TAIL_WORDS or _is_question_form_word(word)
                    for word in hint.split()
                ):
                    continue
                # Misma mención (mismo texto pedido) = mismo filtro, aunque
                # varias tablas tengan una columna llamada igual (SEDE).
                mention = (alias_norm, hint)
                if mention not in mentions:
                    mentions[mention] = {"field": field, "value_hint": hint, "alternatives": [], "alias": alias_norm}
                    order.append(mention)
                else:
                    mentions[mention]["alternatives"].append(field)
                break
        filters = [mentions[key] for key in order]
        for spec in filters:
            already_fields.add(
                (normalize_text(spec["field"].get("table")), normalize_text(spec["field"].get("column")))
            )
        return filters

    def _metric_removal_tokens(self, metric, matched_name, source_context):
        values = [matched_name, metric.get("label"), metric.get("semantic_model")]
        # El tablero enrutado solo explica palabras si es el del indicador: con
        # «tiempo de triage por eps» (enrutado a TABLERO EPS) y un indicador de
        # TIEMPOS URGENCIAS, «eps» sigue pendiente (es una agrupación).
        routed_model = normalize_text(source_context.get("semantic_model"))
        if not routed_model or routed_model == normalize_text(metric.get("semantic_model")):
            values.append(source_context.get("report"))
        values.extend(self._metric_reports(metric))
        tokens = set()
        for value in values:
            for token in canonical_tokens(value):
                tokens.add(token)
                without_numeric_suffix = re.sub(r"\d+$", "", token)
                if len(without_numeric_suffix) >= 3:
                    tokens.add(without_numeric_suffix)
                # «%OCUPACION» explica «ocupación»: sin esto la palabra quedaba
                # como posible valor y se exploraban los dominios de la tabla.
                if token.startswith("%") and len(token) > 3:
                    tokens.add(canonical_token(token.lstrip("%")))
        return tokens

    def _implicit_value_text(
        self, question, metric, matched_name, source_context, group_by,
        extra_removals=None,
    ):
        removals = self._metric_removal_tokens(metric, matched_name, source_context)
        for group in group_by:
            for alias in group.get("aliases", []):
                removals.update(canonical_tokens(alias))
        removals.update(canonical_token(word) for word in GENERIC_QUERY_WORDS)
        removals.update(canonical_token(word) for word in STOPWORDS)
        removals.update(canonical_token(word) for word in FILTER_NEUTRAL_WORDS)
        removals.update({"a", "al", "del", "de", "en", "hay", "hubo", "dentro", "segun"})
        removals.update(canonical_token(word) for word in MONTHS)
        removals.update(extra_removals or ())
        # Página/dashboard mencionada completa («programación quirúrgica»).
        question_tokens = set(canonical_tokens(question))
        for page in self._metric_pages(metric):
            page_tokens = canonical_tokens(page)
            if page_tokens and all(token in question_tokens for token in page_tokens):
                removals.update(page_tokens)

        result = []
        text = normalize_text(question)
        # «… y en qué camas»: la entidad del listado pedido no es un filtro.
        trailing = _TRAILING_DETAIL_RE.search(text)
        if trailing and re.search(r"(?<![a-z0-9])cuant[oa]s\s", text[:trailing.start()]):
            text = text[:trailing.start()]
        for word in text.split():
            token = canonical_token(word)
            if (
                token in removals or re.fullmatch(r"20\d{2}", token)
                or token.isdigit() or _is_request_word(token)
                # Solo la lista fija: un pretérito («tomaron») sí ayuda a
                # elegir otro indicador (IMÁGENES TOMADAS) y se conserva aquí.
                or normalize_text(word) in _QUESTION_FORM_TOKENS
            ):
                continue
            result.append(word)
        return " ".join(result).strip()

    _FAMILY_MAX_VALUES = 6

    def _value_family(self, leftover, tied, values):
        """Valores que comparten la palabra pedida como cabeza («uci» ->
        UCI ADULTOS, UCI NEONATAL): {"values", "words", "tokens"} o None.

        Solo si la palabra pedida es el INICIO de todos los valores
        empatados, la familia está completa (todos los valores del dominio
        que empiezan así), tiene entre 2 y _FAMILY_MAX_VALUES miembros y no
        es todo el dominio (filtrar por todo no filtra nada)."""
        leftover_tokens = set(canonical_tokens(leftover))
        heads = set()
        for value in tied:
            tokens = canonical_tokens(value)
            prefix = []
            for token in tokens:
                if token in leftover_tokens:
                    prefix.append(token)
                else:
                    break
            if not prefix:
                return None
            heads.add(tuple(prefix))
        if len(heads) != 1:
            return None
        head = next(iter(heads))
        if not any(len(token) >= 3 for token in head):
            return None
        family = [
            value for value in values
            if tuple(canonical_tokens(value)[:len(head)]) == head and len(canonical_tokens(value)) > len(head)
        ]
        if not (2 <= len(family) <= self._FAMILY_MAX_VALUES) or len(family) >= len(values):
            return None
        if set(family) != set(tied) and not set(tied) <= set(family):
            return None
        return {
            "values": sorted(family, key=normalize_text),
            "words": [word for word in normalize_text(leftover).split() if canonical_token(word) in head],
            "tokens": head,
        }

    def _value_word_family(self, leftover, tied, values, question=None):
        """Regla general: la palabra pedida es una palabra COMÚN a varios
        valores de la columna, en cualquier posición («obstétricos» ->
        URGENCIA OBSTETRICA, TRIAGE OBSTETRICA, CONSULTA OBSTETRICA): se
        filtra por todos los que la contienen (no por uno solo ni por
        ninguno). Solo si son todos los empatados, entre 2 y
        _FAMILY_MAX_VALUES, no todo el dominio y ninguno contradice la pregunta."""
        leftover_tokens = {token for token in canonical_tokens(leftover) if len(token) >= 4}
        if not leftover_tokens:
            return None
        common = None
        for value in tied:
            tokens = set(canonical_tokens(value)) & leftover_tokens
            common = tokens if common is None else common & tokens
        if not common:
            return None
        family = [value for value in values if common <= set(canonical_tokens(value))]
        if not (2 <= len(family) <= self._FAMILY_MAX_VALUES) or len(family) >= len(values):
            return None
        if not set(tied) <= set(family):
            return None
        # Polaridad: «no obstétricos» / «sin antibiótico» no es la familia.
        if re.search(r"(?<![a-z])(?:no|sin)\s+(?:\w+\s+)?(?:" + "|".join(
                re.escape(word) for word in normalize_text(leftover).split()
                if canonical_token(word) in common) + r")(?![a-z])", normalize_text(question or leftover)):
            return None
        return {
            "values": sorted(family, key=normalize_text),
            "words": [word for word in normalize_text(leftover).split() if canonical_token(word) in common],
            "tokens": tuple(sorted(common)),
        }

    def _context_word_family(self, leftover, field, semantic_model, question, context_tokens):
        """Familia de valores sin las palabras de contexto (páginas del
        indicador) cuando esas palabras eran lo que elegía un solo valor."""
        if not context_tokens:
            return None
        words = normalize_text(leftover).split()
        context = [word for word in words if canonical_token(word) in context_tokens]
        rest = [word for word in words if canonical_token(word) not in context_tokens]
        if not context or not [word for word in rest if len(canonical_token(word)) >= 4]:
            return None
        full = self._resolve_implicit_value(" ".join(words), field, semantic_model, None, question)
        if not full or full.get("values") or full.get("value") is None:
            return None
        if not set(canonical_tokens(full["value"])) & {canonical_token(word) for word in context}:
            return None
        # La pregunta también sin esas palabras: si no, «urgencias» vuelve a
        # «contradecir» a los demás valores de la familia.
        reduced_question = " ".join(
            word for word in normalize_text(question or "").split() if canonical_token(word) not in context_tokens
        )
        reduced = self._resolve_implicit_value(" ".join(rest), field, semantic_model, None, reduced_question)
        if not reduced or not reduced.get("values") or full["value"] not in reduced["values"]:
            return None
        return {
            **reduced,
            "reason": reduced["reason"] + f"; «{' '.join(context)}» es la página donde se ve el indicador, "
                      "no distingue entre esos valores",
        }

    def _categorical_filter(self, field, resolved, source, semantic_model):
        data_type = self._column_type(semantic_model, field["table"], field["column"])
        if resolved.get("values") and resolved.get("value") is None:
            # Familia de valores («uci» -> UCI ADULTOS, UCI NEONATAL): IN {...}.
            return {
                "type": "categorical",
                "concept": (field.get("aliases") or [field["column"]])[0],
                "table": field["table"],
                "column": field["column"],
                "operator": "in",
                "value": None,
                "values": list(resolved["values"]),
                "data_type": data_type,
                "match_score": resolved["score"],
                "source": source,
            }
        return {
            "type": "categorical",
            "concept": (field.get("aliases") or [field["column"]])[0],
            "table": field["table"],
            "column": field["column"],
            "operator": "=",
            "value": resolved["value"],
            "data_type": data_type,
            "match_score": resolved["score"],
            "source": source,
        }

    def _implicit_eligible(self, field, semantic_model):
        """Columnas categóricas de cualquier visual (slicer, tabla, matriz, gráfico)."""
        if field.get("kind") not in ("column", "hierarchy_level"):
            return False
        if self._is_temporal_field(field):
            return False
        # Un código numérico o una fecha no es un valor que se nombre en texto libre.
        return self._column_type(semantic_model, field.get("table"), field.get("column")) not in ("number", "date")

    def _resolve_implicit_filter(
        self, question, metric, matched_name, source_context,
        candidates, group_by, used_fields, extra_removals=None, decisions=None,
    ):
        """Valor de dimensión nombrado sin su columna («cirugías de ortopedia»).

        Más estricto que un filtro explícito («especialidad ortopedia»):
        - la palabra no puede ser una que ya explica la métrica o el tablero
          nombrado (se quitan antes, ver `_metric_explaining_tokens`);
        - se revisan primero las columnas plausibles para un valor nombrado
          suelto (servicio, especialidad, aseguradora, sede...);
        - la coincidencia debe ser fuerte y única en la columna («triage» no
          elige TRIAGE III entre TRIAGE I..V);
        - en columnas de entidades (aseguradora, sede, persona...) una palabra
          que es un concepto del catálogo («cirugía») no es un valor.
        Cada decisión se anota en `decisions` para el razonamiento.
        """
        removals = set(extra_removals or ())
        removals.update(self._metric_explaining_tokens(metric))
        leftover = self._implicit_value_text(
            question, metric, matched_name, source_context, group_by,
            extra_removals=removals,
        )
        if not leftover:
            return None

        semantic_model = metric.get("semantic_model")
        eligible = []
        unrelated = []
        for field in candidates:
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in used_fields or field.get("own_fallback") or not self._implicit_eligible(field, semantic_model):
                continue
            if not self._field_filters_metric(metric, field):
                if field.get("table") not in unrelated:
                    unrelated.append(field.get("table"))
                continue
            eligible.append(field)
        if unrelated and decisions is not None:
            decisions.append(
                "no revisadas (sus tablas no filtran " + str(metric.get("table")) + "): "
                + ", ".join(str(table) for table in unrelated[:5]) + ("…" if len(unrelated) > 5 else "")
            )
        # Primero las columnas del propio indicador (su tabla o los visuales
        # de su página): «interconsultas de pediatría» filtra la especialidad
        # de INTERCONSULTAS antes que el SERVICIO de otra página del informe.
        own = self._own_dimension_fields(metric, eligible)
        own_keys = {(normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in own}
        rest = [
            field for field in eligible
            if (normalize_text(field.get("table")), normalize_text(field.get("column"))) not in own_keys
        ]
        plausible = [field for field in rest if self._plausible_value_column(field)]
        others = [field for field in rest if not self._plausible_value_column(field)]
        # Todas las plausibles (hasta un tope) y luego las demás dentro del
        # presupuesto original de columnas revisadas.
        ordered = plausible[:max(self.max_implicit_dimensions, 10)]
        ordered += others[:max(0, self.max_implicit_dimensions - len(ordered))]
        ordered = own + ordered
        # Identificadores y datos de personas (documento, ingreso, OID...) nunca
        # son un valor nombrado suelto (como ya no lo son en las columnas propias):
        # se quitan después de armar la lista, sin que otra columna ocupe su lugar.
        # En Power BI real su dominio tiene miles de valores (TOPN 2500 solo trae
        # los primeros en orden alfabético) y consultarlo cuesta segundos.
        ordered = [field for field in ordered if not identifier_column(field.get("column"))]

        # Búsqueda incremental: los dominios se traen en lotes pequeños (solo
        # columnas de baja cardinalidad) a medida que el bucle los revisa, en su
        # orden de prioridad; al encontrar una coincidencia fuerte (≥ 1.0) no se
        # consulta el resto. Mismo orden y mismos valores que antes.
        # Las páginas donde se ve el indicador («URGENCIAS» para TRIAGES) son
        # su contexto: no distinguen entre valores de una familia.
        page_tokens = {
            token for page in self._metric_pages(metric) for token in canonical_tokens(page) if len(token) >= 4
        }
        best = None
        for position, field in enumerate(ordered):
            self._prefetch_next(semantic_model, ordered, position)
            resolved = self._resolve_implicit_value(
                leftover, field, semantic_model, decisions, question=question,
                context_tokens=page_tokens,
            )
            if not resolved:
                continue
            candidate = {"field": field, **resolved}
            if best is None or candidate["score"] > best["score"]:
                best = candidate
            if best["score"] >= 1.0:
                break
        if best is not None and decisions is not None:
            decisions.append(f"aplicado: {best['reason']}")
        return best

    def _field_filters_metric(self, metric, field):
        """¿Un filtro sobre la tabla de `field` puede cambiar el indicador?

        No, si el indicador se calcula sobre su tabla, el catálogo técnico
        trae las relaciones del modelo y la tabla del campo no es esa tabla ni
        una de las que la filtran (p. ej. BRIEFING: tablas independientes, un
        SERVICIO de la página SEGUIMIENTO RECEPCIÓN no filtra INTERCONSULTAS).
        Con información incompleta se asume que sí (no se descarta). Misma
        regla que la agrupación y el periodo (`_dimension_relation`)."""
        return self._dimension_relation(metric, field) != "unrelated"

    _OWN_FIELD_LIMIT = 8

    def _own_dimension_fields(self, metric, fields):
        """Campos de la tabla del indicador o de los visuales de sus páginas
        (sin columnas de personas/identificadores), en su orden, hasta un tope."""
        table = normalize_text(self._metric_fact_table(metric))
        pages = {normalize_text(page) for page in self._metric_pages(metric)}
        own, seen = [], set()
        for field in fields:
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in seen:
                continue
            column = normalize_text(field.get("column")).replace(" ", "")
            if any(part in column for part in self._PRIVATE_COLUMN_PARTS):
                continue
            if (table and key[0] == table) or (pages and normalize_text(field.get("page")) in pages):
                own.append(field)
                seen.add(key)
            if len(own) >= self._OWN_FIELD_LIMIT:
                break
        return own

    # ---------------- valores implícitos: reglas estrictas ----------------
    # Palabras de columna en las que un valor suele nombrarse suelto en la
    # pregunta («cirugías de ortopedia», «egresos de urgencias», «de sura»).
    PLAUSIBLE_VALUE_COLUMN_WORDS = {
        "servicio", "servicios", "especialidad", "especialidades", "asegurador",
        "aseguradora", "aseguradoras", "eps", "entidad", "pagador", "sede", "sedes",
        "unidad", "area", "ubicacion", "almacen", "bodega", "tipo", "clasificacion",
        "estado", "sexo", "genero", "modalidad", "menores", "mayores", "edad",
        "etario", "turno", "causa", "motivo", "programa", "convenio", "regimen",
        "categoria", "procedimiento", "piso", "grupo",
    }
    # Columnas de entidades (no de conceptos clínicos): un concepto del
    # catálogo («cirugía», «triage») nunca es una aseguradora o una sede.
    ENTITY_COLUMN_WORDS = {
        "asegurador", "aseguradora", "aseguradoras", "eps", "entidad", "pagador",
        "sede", "sedes", "municipio", "departamento", "cirujano", "medico",
        "profesional", "usuario", "colaborador", "nombre", "convenio", "regimen",
    }

    def _column_words(self, field):
        words = set()
        for value in (field.get("column"), field.get("display_name"), field.get("level")):
            words.update(normalize_text(value).split())
        return words

    def _plausible_value_column(self, field):
        return bool(self._column_words(field) & self.PLAUSIBLE_VALUE_COLUMN_WORDS)

    def _metric_explaining_tokens(self, metric):
        """Palabras que explican la métrica (etiqueta, medida, alias propios):
        no pueden ser además un valor implícito («cirugías realizadas de
        ortopedia» -> «cirugías» no es ASEGURADOR = CIRUGIA)."""
        values = [metric.get("label"), metric.get("measure"), *(metric.get("aliases") or [])]
        tokens = set()
        for value in values:
            for token in canonical_tokens(value):
                if len(token) >= 3 and not token.isdigit():
                    tokens.add(token)
                    stripped = re.sub(r"\d+$", "", token)
                    if len(stripped) >= 3:
                        tokens.add(stripped)
        return tokens

    def _metric_concept_tokens(self):
        """Palabras (canónicas) de los nombres de indicadores aprobados."""
        if getattr(self, "_concept_tokens", None) is not None:
            return self._concept_tokens
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS}
        tokens = set()
        for metric in self.metrics:
            if metric.get("validation_status") != "approved":
                continue
            for value in (metric.get("label"), metric.get("measure")):
                for token in canonical_tokens(value):
                    if len(token) >= 4 and token not in ignored and not token.isdigit():
                        tokens.add(token)
        self._concept_tokens = tokens
        return tokens

    def _spurious_value_reason(self, asked_tokens, value_tokens, field, question, exact=False):
        """Motivo por el que un valor NO nombrado en la pregunta solo comparte
        con ella una palabra (None si el valor es legítimo):
        - el valor debe nombrarse completo: compartir una palabra que es un
          concepto de los indicadores no basta («interconsultas» no es
          INTERCONSULTAS SAS: falta «sas»);
        - lo que se cuenta («cuántas CUENTAS hay...») es la unidad del
          indicador, no un valor de una columna poco habitual (PERFIL = CUENTAS)."""
        asked = {token for token in asked_tokens if token}
        value = {token for token in value_tokens if len(token) >= 3}
        matched = {
            token for token in value
            if any(_tokens_match_loosely(token, other) for other in asked)
        }
        if not matched:
            return None
        missing = value - matched
        if missing and not exact and len(matched) == 1 and matched <= self._metric_concept_tokens():
            return (
                f"la pregunta solo comparte «{' '.join(sorted(matched))}» (un concepto de los "
                f"indicadores) con el valor; no nombra «{' '.join(sorted(missing))}»"
            )
        counted = self._counted_noun(question or "")
        if (
            counted and not self._plausible_value_column(field)
            and all(_tokens_match_loosely(token, counted) for token in matched)
        ):
            return f"«{counted}» es lo que se cuenta en la pregunta, no un filtro"
        return None

    def _resolve_implicit_value(self, leftover, field, semantic_model, decisions=None, question=None,
                                context_tokens=None):
        """Valor de `field` nombrado en `leftover` con las reglas estrictas, o None.

        `context_tokens`: palabras de las páginas del indicador. Si una de
        ellas es lo único que separa el mejor valor de su familia («triages
        obstétricos en URGENCIAS»: URGENCIA OBSTETRICA frente a EMERGENCIA
        OBSTETRICA, CONSULTA EXTERNA OBSTETRICA...), se filtra por la familia:
        la página nombra dónde se ve el indicador, no un valor (holdout H05)."""
        family = self._context_word_family(leftover, field, semantic_model, question, context_tokens)
        if family is not None:
            if decisions is not None:
                decisions.append(f"aplicado: {family['reason']}")
            return family
        values = self._get_values(semantic_model, field["table"], field["column"])
        if not values:
            return None
        scored = []
        for value in values:
            score = self._value_match_score(leftover, value, value_hint=leftover, allow_short=True)
            if score > 0:
                scored.append((score, value))
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], len(normalize_text(item[1]))), reverse=True)
        column = f"{field['table']}[{field['column']}]"
        # Nunca un valor opuesto a la palabra distintiva («menores» no es
        # MAYORES DE EDAD; «aceptadas» no es NO ACEPTADO).
        consistent, contradicted = [], []
        for score, value in scored:
            plan_budget.check("valor implícito")
            # Solo importan el mejor valor coherente y sus empates (hasta el
            # tamaño máximo de una familia): con miles de valores parecidos
            # (nombres de personas) no se revisa todo el dominio.
            if consistent and (
                score < consistent[0][0] - 1e-9 or len(consistent) > self._FAMILY_MAX_VALUES + 1
            ):
                break
            if len(contradicted) > self._FAMILY_MAX_VALUES * 4:
                break
            # La pregunta completa conserva la polaridad («no aceptadas»),
            # que el texto sobrante pierde al quitar palabras vacías.
            reason = (
                value_contradiction(f"{leftover} {question or ''}", value, values)
                if score >= 0.84 else None
            )
            if reason:
                contradicted.append((value, reason))
                continue
            consistent.append((score, value))
        if decisions is not None and contradicted:
            if not consistent and len(contradicted) > 1:
                names = [value for value, _ in contradicted]
                decisions.append(
                    f"descartado: {column} = {names[0]} (la palabra coincide con varios valores de la columna: "
                    + ", ".join(names[:4]) + ("…" if len(names) > 4 else "")
                    + " y la pregunta no nombra lo que los distingue)"
                )
            else:
                decisions.extend(f"descartado: {column} = {value} ({reason})" for value, reason in contradicted)
        scored = consistent
        if not scored:
            return None
        top_score, top_value = scored[0]
        plausible = self._plausible_value_column(field)

        def reject(reason):
            if decisions is not None:
                decisions.append(f"descartado: {column} = {top_value} ({reason})")
            return None

        # Columna plausible: el valor completo o todas las palabras pedidas
        # deben coincidir (≥ 0.94). Otra columna: solo el valor exacto.
        if top_score < (0.94 if plausible else 1.10):
            if top_score >= 0.84:
                return reject(
                    f"coincidencia parcial {top_score:.2f}"
                    + ("" if plausible else " en una columna poco habitual para un valor suelto")
                )
            return None
        ties = [value for score, value in scored[1:] if score >= top_score - 1e-9]
        if ties and top_score < 1.10 and plausible:
            family = self._value_family(leftover, [top_value, *ties], values) or self._value_word_family(
                leftover, [top_value, *ties], values, question,
            )
            if family:
                words = " ".join(family["words"])
                return {
                    "value": None, "values": family["values"], "score": round(top_score, 4),
                    "tokens": set(family["tokens"]),
                    "reason": (
                        f"«{words}» nombra a varios valores de {column} que empiezan igual "
                        f"({', '.join(family['values'])}) y la pregunta no dice cuál: se suman todos "
                        "(pregunta por uno si lo quieres por separado)"
                    ),
                }
        if ties and top_score < 1.10:
            return reject(
                "la palabra coincide con varios valores de la columna: "
                + ", ".join([top_value, *ties][:4]) + ("…" if len(ties) > 3 else "")
            )
        value_tokens = {token for token in canonical_tokens(top_value) if len(token) >= 3}
        leftover_tokens = set(canonical_tokens(leftover))
        matched = value_tokens & leftover_tokens
        if (
            self._column_words(field) & self.ENTITY_COLUMN_WORDS
            and matched and matched <= self._metric_concept_tokens()
        ):
            return reject(
                f"«{' '.join(sorted(matched))}» es un concepto de los indicadores, "
                "no una entidad de esa columna"
            )
        spurious = self._spurious_value_reason(
            leftover_tokens, value_tokens, field, question, exact=top_score >= 1.10,
        )
        if spurious:
            return reject(spurious)
        words = " ".join(sorted(matched)) or normalize_text(top_value)
        kind = "columna plausible para un valor nombrado" if plausible else "valor exacto"
        return {
            "value": top_value, "score": round(top_score, 4),
            "tokens": set(canonical_tokens(top_value)),
            "reason": (
                f"«{words}» coincide con {column} = {top_value} "
                f"({kind}, coincidencia {top_score:.2f}, único valor de la columna que coincide)"
            ),
        }
    # Campos con más valores distintos que esto son identificadores o
    # personas: no se usan para emparejar calificativos aproximados.
    _QUALIFIER_MAX_DOMAIN = 500
    _QUALIFIER_FIELD_LIMIT = 20

    @staticmethod
    def _loose_phrase_score(question, name, weights=None):
        """_phrase_score tolerando plural/género/conjugación: las palabras de la
        pregunta que coinciden por raíz con una del nombre se reemplazan por
        ella («imágenes se tomaron» cubre «IMAGENES TOMADAS»)."""
        name_tokens = canonical_tokens(name)
        rewritten = []
        for word in normalize_text(question).split():
            token = canonical_token(word)
            match = next((other for other in name_tokens if _tokens_match_loosely(token, other)), None)
            rewritten.append(match or word)
        return _phrase_score(" ".join(rewritten), name, weights)

    def _value_token_index(self, semantic_model, field):
        """Valores del campo con sus palabras canónicas (caché por campo)."""
        cache = self.__dict__.setdefault("_value_token_cache", {})
        key = (normalize_text(semantic_model), normalize_text(field.get("table")), normalize_text(field.get("column")))
        # Un dominio de más de _QUALIFIER_MAX_DOMAIN valores no se indexa (abajo):
        # si ya se sabe que los pasa (consulta de cardinalidad o dominio ya
        # traído) o es un identificador/dato de persona (documento, ingreso,
        # OID...: siempre miles de valores), no se consulta. Para el resto basta
        # pedir _QUALIFIER_MAX_DOMAIN + 1 valores: con eso se sabe si los pasa.
        domains = self._domain_cache()
        if domains is not None and (
            identifier_column(field.get("column"))
            or domains.exceeds(semantic_model, field["table"], field["column"], self._QUALIFIER_MAX_DOMAIN)
        ):
            domains.note_avoided(semantic_model, field["table"], field["column"])
            return []
        values = self._get_values(semantic_model, field["table"], field["column"],
                                  limit=self._QUALIFIER_MAX_DOMAIN + 1)
        if values is None:
            return None  # fallo temporal: no se cachea
        cached = cache.get(key)
        if cached is not None and cached[0] is values:
            return cached[1]  # mismo dominio (la caché lo renueva al vencer)
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}
        index = []
        if len(values) <= self._QUALIFIER_MAX_DOMAIN:
            for value in values:
                tokens = [t for t in canonical_tokens(value) if t not in ignored and t != "%"]
                if tokens and not all(t.isdigit() for t in tokens):
                    index.append((value, tokens))
        cache[key] = (values, index)
        return index

    @staticmethod
    def _fuzzy_value_score(span_tokens, value_tokens):
        """Todas las palabras del calificativo están en el valor (por raíz o
        tipeo leve) y cubren al menos la mitad del valor. 0.90-1.00."""
        if not span_tokens or not any(len(token) >= 4 for token in span_tokens):
            return 0.0
        matched = set()
        for token in span_tokens:
            hit = next(
                (i for i, other in enumerate(value_tokens) if _tokens_match_loosely(token, other)),
                None,
            )
            if hit is None:
                return 0.0
            matched.add(hit)
        coverage = len(matched) / len(value_tokens)
        if coverage < 0.5:
            return 0.0
        return round(0.90 + 0.10 * coverage, 4)

    def _fuzzy_value_family(self, tokens, tied, field, semantic_model):
        """Valores empatados por una coincidencia aproximada que comparten la
        palabra de la pregunta (lista ordenada), o None si es uno solo, son
        demasiados o son todo el dominio (entonces la palabra no filtra)."""
        values = list(dict.fromkeys(value for value, _ in tied))
        if not (2 <= len(values) <= self._FAMILY_MAX_VALUES):
            return None
        domain = self._get_values(semantic_model, field["table"], field["column"]) or []
        if domain and len(values) >= len([value for value in domain if value is not None]):
            return None
        for _, value_tokens in tied:
            if not all(any(_tokens_match_loosely(token, other) for other in value_tokens) for token in tokens):
                return None
        return sorted(values, key=normalize_text)

    def _fuzzy_qualifier_filters(self, metric, candidates, used_fields, words, question=None):
        """Regla 3b: valores de dimensión aproximados del modelo del indicador.
        Prueba primero la frase completa y luego frases más cortas (cada una
        puede ser un filtro distinto: «ortopedia» -> ESPECIALIDAD, «sura» ->
        ASEGURADORA). Revisa hasta _QUALIFIER_FIELD_LIMIT campos."""
        semantic_model = metric.get("semantic_model")
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS}
        used = set(used_fields)
        fields = []
        for field in candidates:
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in used or field.get("own_fallback") or not self._implicit_eligible(field, semantic_model):
                continue
            if any(key == (normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in fields):
                continue
            if not self._field_filters_metric(metric, field):
                continue  # un filtro en una tabla que no filtra al indicador no cambia nada
            fields.append(field)
            if len(fields) >= self._QUALIFIER_FIELD_LIMIT:
                break

        # Búsqueda incremental: los dominios se traen en lotes pequeños (solo
        # columnas de baja cardinalidad; basta el tope _QUALIFIER_MAX_DOMAIN + 1)
        # cuando el bucle llega a cada campo, y una frase deja de revisar campos
        # al encontrar una coincidencia de 1.0 (el máximo: ningún campo
        # posterior la reemplaza). Mismo orden y mismos valores que antes.
        qualifier_limit = self._QUALIFIER_MAX_DOMAIN + 1
        remaining = list(words)
        found = []
        progress = True
        while remaining and progress:
            progress = False
            for size in range(len(remaining), 0, -1):
                for start in range(0, len(remaining) - size + 1):
                    span = remaining[start:start + size]
                    tokens = [canonical_token(word) for word in span if canonical_token(word) not in ignored]
                    if not tokens:
                        continue
                    best = None
                    ties = []   # otros valores del mismo campo con el mismo puntaje
                    for position, field in enumerate(fields):
                        if best is not None and best[0] >= 1.0:
                            break
                        plan_budget.check("calificativo aproximado")
                        key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
                        if key in used:
                            continue
                        self._prefetch_next(semantic_model, fields, position, limit=qualifier_limit, skip=used)
                        index = self._value_token_index(semantic_model, field) or []
                        domain = (
                            self._get_values(semantic_model, field["table"], field["column"])
                            if index else []
                        ) or [value for value, _ in index]
                        for value, value_tokens in index:
                            score = self._fuzzy_value_score(tokens, value_tokens)
                            same = best is not None and best[1] is field and score == best[0]
                            if not score or (best is not None and score <= best[0] and not same):
                                continue
                            # Una palabra genérica sola («general») no elige un
                            # valor de varias palabras (HOSPITALIZACIÓN GENERAL)
                            # salvo que el resto del valor esté en la pregunta.
                            if self._generic_partial_value(tokens, value_tokens, question):
                                continue
                            spurious = self._spurious_value_reason(
                                set(tokens), set(value_tokens), field, question,
                            )
                            if spurious:
                                self._note(
                                    f"calificativo aproximado: no se eligió {field.get('table')}"
                                    f"[{field.get('column')}] = {value}: {spurious}"
                                )
                                continue
                            # La coincidencia por raíz no puede elegir el
                            # valor opuesto («de edad» de MAYORES DE EDAD
                            # cuando se pidió «menores de edad»).
                            if self._value_contradiction(
                                f"{' '.join(span)} {question or ''}", value, domain, field,
                                "calificativo aproximado",
                            ):
                                continue
                            if same:
                                ties.append((value, value_tokens))
                                continue
                            best = (score, field, value, value_tokens)
                            ties = []
                    if best is None:
                        continue
                    score, field, value, value_tokens = best
                    used.add((normalize_text(field.get("table")), normalize_text(field.get("column"))))
                    family = self._fuzzy_value_family(tokens, [(value, value_tokens), *ties], field, semantic_model)
                    if family is not None:
                        # «obstétricos» con URGENCIA OBSTETRICA, EMERGENCIA
                        # OBSTETRICA...: la palabra es común a todos y la
                        # pregunta no dice cuál -> se filtra por todos (holdout H05).
                        found.append((field, {
                            "value": None, "values": family, "score": score, "phrase": " ".join(span),
                            "tokens": {t for _, toks in [(value, value_tokens), *ties] for t in toks}
                                      | {canonical_token(word) for word in span},
                        }))
                        self._note(
                            f"«{' '.join(span)}» es común a varios valores de {field['table']}[{field['column']}] "
                            f"({', '.join(family)}) y la pregunta no dice cuál: se suman todos"
                        )
                    else:
                        found.append((field, {
                            "value": value, "score": score, "phrase": " ".join(span),
                            "tokens": set(value_tokens) | {canonical_token(word) for word in span},
                        }))
                    remaining = remaining[:start] + remaining[start + size:]
                    progress = True
                    break
                if progress:
                    break
        return found

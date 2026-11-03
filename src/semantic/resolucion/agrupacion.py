"""Etapa «agrupación y forma de respuesta»: «por X», hermanos que sí se desglosan y ranking.

Cola de agrupación (_requested_group_tail; «y su respectiva X», auditoría TU12), columna nombrada
o descrita (r5), indicador hermano de la misma página que sí se desglosa (r2-indicador-2 BH18),
opciones factibles por X (tmdl_real), grupos casi en blanco, ranking («top 5», «el que más»).
Mixin de QueryPlanBuilder, métodos movidos sin cambios.
"""
import re

from src.semantic.resolucion.texto import (
    _ALIAS_CONNECTORS,
    _alias_prefix,
    _original_phrase,
    _stem_token,
    _unique_strings,
    canonical_token,
    canonical_tokens,
    DIMENSION_SYNONYMS,
    GENERIC_PAGE_WORDS,
    GENERIC_QUERY_WORDS,
    normalize_text,
    STOPWORDS,
)


class AgrupacionMixin:


    # ---------------- «M por X» con un indicador que no se desglosa por X ----------------
    _GROUP_TAIL_RE = re.compile(
        r"(?<![a-z0-9])(?:por|segun|agrupad[oa]s?\s+por|desglosad[oa]s?\s+por"
        # «… y su respectiva especialidad», «con sus correspondientes servicios»
        r"|(?:(?:y|con|junto\s+con)\s+)?(?:su|sus)\s+(?:respectiv[oa]s?|correspondientes?))\s+"
        r"(?:(?:el|la|los|las|cada)\s+)?(.+)$"
    )

    def _requested_group_tail(self, question):
        """Lo que sigue a «por/según» (o a «y su respectiva») en la pregunta,
        sin el periodo («ocupación por servicio hoy» -> «servicio»), o None."""
        text = self._analyze_periods(question)["clean_question"]
        match = self._GROUP_TAIL_RE.search(text)
        tail = match.group(1).strip() if match else ""
        return tail or None

    def _group_field_in(self, tail, fields):
        """Campo de `fields` que nombra el comienzo de `tail` («aseguradores» ->
        TERNOMCOM «ASEGURADORA»), sin columnas temporales; o None."""
        if not tail:
            return None
        # Primero el filtro barato (algún alias abre `tail`); luego el mejor
        # de esos por coincidencia y relevancia, como `_best_dimension`.
        tail = self._strip_group_interrogative(tail)
        named = [
            field for field in fields
            if any(_alias_prefix(tail, alias) for alias in field.get("aliases") or [])
        ]
        if named:
            return self._best_dimension(tail, named, exclude_temporal=True)
        described = self._described_group_field(tail, fields)
        return described[0] if described else None

    # «por QUÉ motivos», «según CUÁL servicio»: el interrogativo no es parte
    # del nombre de la dimensión.
    _GROUP_INTERROGATIVE_RE = re.compile(r"^(?:que|cual|cuales|cada)\s+")
    # Sinónimos de nombres de dimensión (genéricos, no de un tablero).
    _DIMENSION_NAME_SYNONYMS = {
        "motivo": ("causa", "razon", "motivo"), "causa": ("motivo", "razon", "causa"),
        "razon": ("motivo", "causa", "razon"),
    }

    def _strip_group_interrogative(self, tail):
        return self._GROUP_INTERROGATIVE_RE.sub("", normalize_text(tail)).strip() if tail else tail

    def _column_description_head(self, field):
        """Frase inicial con que el diccionario describe la columna («Rango de
        horas de espera de la orden», «Causa de cancelación de la cita»)."""
        index = self._dictionary_index()
        key = (
            normalize_text(field.get("semantic_model")),
            f"c:{normalize_text(field.get('table'))}[{normalize_text(field.get('column'))}]",
        )
        text = index.get(key) or ""
        return re.split(r"[.,;:(\n]", text, maxsplit=1)[0].strip()

    def _described_group_field(self, tail, fields):
        """«por rango de horas» -> HORAS_SUMINISTRO («Rango de horas de espera…»);
        «por motivos» -> CCCDESCRI («Causa de cancelación…»): la dimensión
        también se nombra con el comienzo de su descripción documentada (dos
        palabras o más, o una de ≥ 5 letras, con sinónimos genéricos).
        Devuelve (campo, texto de la pregunta que la nombra) o None."""
        tail = self._strip_group_interrogative(tail)
        if not tail:
            return None
        words = tail.split()
        first = canonical_token(words[0]) if words else ""
        variants = [tail]
        synonyms = next(
            (values for key, values in self._DIMENSION_NAME_SYNONYMS.items()
             if canonical_token(key) == first or _stem_token(key) == _stem_token(words[0])),
            (),
        )
        for synonym in synonyms:
            if canonical_token(synonym) != first:
                variants.append(" ".join([synonym, *words[1:]]))
        best = None
        for field in fields:
            if self._is_period_field(field):
                continue
            head_words = normalize_text(self._column_description_head(field)).split()
            for size in range(min(len(head_words), 4), 0, -1):
                phrase = " ".join(head_words[:size])
                content = [w for w in phrase.split() if w not in _ALIAS_CONNECTORS]
                if not content or (len(content) == 1 and len(content[0]) < 5):
                    continue
                if phrase.split()[-1] in _ALIAS_CONNECTORS:
                    continue
                matched = next((prefix for prefix in (_alias_prefix(v, phrase) for v in variants) if prefix), None)
                if matched:
                    score = (len(content), field.get("relevance_score", 0))
                    if best is None or score > best[0]:
                        best = (score, field, " ".join(words[:len(matched.split())]))
                    break
        if best is None:
            return None
        self._note(
            f"«por {best[2]}» nombra la dimensión {best[1].get('table')}[{best[1].get('column')}] "
            "según su descripción documentada"
        )
        return best[1], best[2]

    def _group_topic_words(self, question, source_context, tail):
        """Palabras del tema de «detalle de ocupación por aseguradores»
        («ocupacion»): sin la agrupación, unidades ni palabras de página genéricas."""
        ignored = {canonical_token(word) for word in self._OPTION_UNIT_WORDS
                   | self._PAGE_IGNORED_NAME_WORDS | GENERIC_PAGE_WORDS}
        ignored |= set(canonical_tokens(tail))
        return [word for word in self._option_words(question, source_context) if word not in ignored]

    def _table_pages(self, semantic_model, table):
        """Páginas del informe que usan la tabla (columnas en visuales o
        indicadores de esa tabla): PACIENTES X ASEGURADORA -> DETALLE OCUPACIÓN."""
        index = self.__dict__.get("_table_pages_index")
        if index is None:
            index = {}
            for field in self.dimension_fields or []:
                key = (normalize_text(field.get("semantic_model")), normalize_text(field.get("table")))
                if field.get("page") and field["page"] not in index.setdefault(key, []):
                    index[key].append(field["page"])
            for metric in self.metrics:
                key = (normalize_text(metric.get("semantic_model")), normalize_text(metric.get("table")))
                for page in self._metric_pages(metric):
                    if page not in index.setdefault(key, []):
                        index[key].append(page)
            self._table_pages_index = index
        return list(index.get((normalize_text(semantic_model), normalize_text(table)), []))

    def _metric_topic_page(self, metric, words):
        """Página (de sus visuales o de su tabla) cuyo nombre explica TODAS las
        palabras del tema («ocupacion» -> DETALLE OCUPACIÓN); "" si las explica
        el nombre/tabla del indicador; None si nada las explica."""
        if not words:
            return None
        pages = _unique_strings([
            *self._metric_pages(metric),
            *self._table_pages(metric.get("semantic_model"), self._metric_fact_table(metric)),
        ])
        for page in pages:
            tokens = self._page_name_tokens(page)
            if tokens and all(self._explains(word, tokens) for word in words):
                return page
        vocabulary = self._metric_vocabulary_tokens(metric, with_pages=False)
        if all(self._explains(word, vocabulary) for word in words):
            return ""
        return None

    def _groupable_on_topic(self, metric, tail, words):
        """¿El indicador se desglosa por `tail` y su página/nombre trata el tema?"""
        return (
            self._metric_topic_page(metric, words) is not None
            and self._group_field_in(tail, self._metric_dimensions(metric)) is not None
        )

    def _group_siblings(self, question, source_context, tail, models, exclude=()):
        """Indicadores de esos modelos que SÍ se desglosan por `tail` y cuya
        página o nombre trata el tema de la pregunta («detalle de ocupación por
        aseguradores»: %OCUPACION no tiene aseguradora, pero la página DETALLE
        OCUPACIÓN cuenta los pacientes de PACIENTES X ASEGURADORA por
        TERNOMCOM). Uno por expresión (TOTAL PACIENTES = PACIENTES por
        ASEGURADORA): el de la página del tema, tarjeta, nombre más corto."""
        words = self._group_topic_words(question, source_context, tail)
        if not words or not tail:
            return []
        models = {normalize_text(model) for model in models if model}
        excluded = {self._logical_key(metric) for metric in exclude}
        groups = {}
        for metric in self.metrics:
            model = metric.get("semantic_model")
            if (
                metric.get("validation_status") != "approved" or normalize_text(model) not in models
                or self._logical_key(metric) in excluded
            ):
                continue
            page = self._metric_topic_page(metric, words)
            if page is None:
                continue
            field = self._group_field_in(tail, self._metric_dimensions(metric))
            if field is None:
                continue
            key = (normalize_text(model), normalize_text(self._measure_expression(model, metric)))
            groups.setdefault(key, []).append({"metric": metric, "page": page, "field": field, "words": words})

        def rank(item):
            metric = item["metric"]
            on_page = [a for a in metric.get("appearances") or []
                       if normalize_text(a.get("page_display_name")) == normalize_text(item["page"])]
            generic = bool(re.match(r"^(?:recuento|conteo|count|suma|sum)\b", normalize_text(metric.get("label"))))
            return (
                0 if on_page else 1,
                0 if any(normalize_text(a.get("visual_type")) == "card" for a in on_page) else 1,
                1 if generic else 0,
                len(str(metric.get("label") or "")),
            )

        return [sorted(members, key=rank)[0] for members in groups.values()]

    def _ungroupable_text(self, metrics, tail, question):
        """«%OCUPACION no se puede desglosar por aseguradores: su tabla CAMAS
        DISPONIBLES no tiene esa columna ni se relaciona con una que la tenga.»"""
        labels = _unique_strings(metric.get("label") for metric in metrics)
        tables = _unique_strings(self._metric_fact_table(metric) for metric in metrics)
        dimension = _original_phrase(question, tail.split()[0]) if tail else "esa dimensión"
        if len(labels) == 1:
            where = f"su tabla {tables[0]}" if tables else "su tabla"
            return (
                f"{labels[0]} no se puede desglosar por {dimension}: {where} no tiene esa columna "
                "ni se relaciona con una que la tenga."
            )
        listed = ", ".join(labels[:-1]) + " y " + labels[-1]
        return f"{listed} no se pueden desglosar por {dimension}: sus tablas no tienen esa columna."

    def _group_sibling_note(self, originals, sibling, tail, question):
        """Nota visible: qué no se pudo desglosar y qué se muestra en su lugar."""
        metric = sibling["metric"]
        field = sibling["field"]
        topic = " ".join(_original_phrase(question, word) for word in sibling.get("words") or [])
        where = metric.get("report") or metric.get("semantic_model")
        if sibling.get("page"):
            where = f"{where} › página {sibling['page']}"
        name = (field.get("aliases") or [field.get("column")])[0]
        lead = f"Para ver «{topic}» por {name.lower()}" if topic else "En su lugar"
        return (
            f"{self._ungroupable_text(originals, tail, question)} {lead} se muestra "
            f"{metric.get('label')} ({where}), que sí se desglosa por {name}."
        )

    def _group_sibling_plan(self, question, intent_result, originals, tail, source_context, why_prefix=""):
        """Plan con el único indicador hermano que se desglosa por `tail`, o None."""
        models = _unique_strings(metric.get("semantic_model") for metric in originals)
        siblings = self._group_siblings(question, source_context, tail, models, exclude=originals)
        if len(siblings) != 1:
            if siblings:
                self._note(
                    f"varios indicadores se desglosan por «{tail}» y tratan el tema: "
                    + ", ".join(str(item["metric"].get("label")) for item in siblings[:5])
                )
            return None
        sibling = siblings[0]
        note = self._group_sibling_note(originals, sibling, tail, question)
        item = {"metric": sibling["metric"], "matched_name": sibling["metric"].get("label"), "score": None}
        return self._forced_plan(
            question, intent_result, item,
            f"{why_prefix}{self._ungroupable_text(originals, tail, question)} Se usa el indicador del "
            f"mismo tablero que sí se desglosa por «{tail}» y trata el tema de la pregunta",
            consumed_tokens=self._option_words(question, source_context),
            visible_note=note, group_sibling=True,
        )

    def blank_group_alternative(self, plan, blank_share):
        """La agrupación pedida salió casi toda en blanco («(sin especialidad)»
        40 de 41): esa tabla no tiene la dimensión poblada. Plan con el ÚNICO
        indicador del mismo tema (de cualquier tablero) que se desglosa por esa
        dimensión en OTRA columna; None si no hay uno solo (entonces se le dice
        al usuario)."""
        groups = plan.get("group_by") or []
        metric = plan.get("metric") or {}
        if len(groups) != 1 or not metric:
            return None
        field = groups[0]
        names = [*(field.get("aliases") or []), field.get("label"), field.get("column")]
        tail = next((normalize_text(name) for name in names if normalize_text(name)), "")
        question = plan.get("question") or ""
        source_context = plan.get("source_context") or {}
        if not tail or not question:
            return None
        models = _unique_strings(item.get("semantic_model") for item in self.metrics)
        same_column = (normalize_text(field.get("table")), normalize_text(field.get("column")))
        siblings = [
            item for item in self._group_siblings(question, source_context, tail, models, exclude=[metric])
            if (normalize_text(item["field"].get("table")), normalize_text(item["field"].get("column")))
            != same_column
        ]
        if len(siblings) != 1:
            self._note(
                f"{field.get('table')}[{field.get('column')}] está en blanco en el {blank_share:.0%} del "
                f"resultado y ningún otro indicador del tema se desglosa por «{tail}»"
                + (f" (varios: {', '.join(str(i['metric'].get('label')) for i in siblings[:4])})" if siblings else "")
            )
            return None
        sibling = siblings[0]
        other = sibling["metric"]
        note = (
            f"{metric.get('label')} tiene {field.get('column')} en blanco en el {blank_share:.0%} de los "
            f"registros: no sirve para desglosar por {tail}. Se muestra {other.get('label')} "
            f"({other.get('report') or other.get('semantic_model')}), que sí trae {tail}."
        )
        item = {"metric": other, "matched_name": other.get("label"), "score": None}
        return self._forced_plan(
            question, None, item,
            f"la agrupación por «{tail}» de {metric.get('label')} salió casi toda en blanco; se usa el "
            "indicador del mismo tema que sí la trae",
            consumed_tokens=self._option_words(question, source_context),
            visible_note=note, group_sibling=True,
        )

    _VALUE_ROLES = {"values", "y", "y2", "size", "tooltips", "tooltip"}

    def _shown_by_field(self, metric, field):
        """¿Algún visual del tablero muestra este indicador desglosado por esa
        columna (eje, categoría, filas o leyenda del MISMO visual)?"""
        visual_ids = {str(value) for value in self._metric_visual_ids(metric)}
        if not visual_ids or not field:
            return False
        model = normalize_text(metric.get("semantic_model"))
        table, column = normalize_text(field.get("table")), normalize_text(field.get("column"))
        return any(
            str(item.get("visual_id")) in visual_ids
            and normalize_text(item.get("semantic_model")) == model
            and normalize_text(item.get("table")) == table
            and normalize_text(item.get("column")) == column
            and normalize_text(item.get("role")) not in self._VALUE_ROLES
            for item in self.dimension_fields or []
        )

    def _group_shown_option(self, question, intent_result, plan, groupable, tail):
        """«M por X» y todas las opciones se desglosan por X: si todas miden la
        misma tabla del mismo modelo (variantes del mismo conteo: PACIENTES
        de NAOS como DISTINCTCOUNT de AINCONSEC en la tarjeta y de ADNINGRESO en
        la dona por servicio) y un solo indicador aparece en un visual
        desglosado por X, ese es el que el tablero usa para responder: se
        responde con él. Opciones de tablas o modelos distintos siguen siendo
        una ambigüedad real (None: se contrapregunta)."""
        owners = {
            (normalize_text(item["metric"].get("semantic_model")), normalize_text(self._metric_fact_table(item["metric"])))
            for item in groupable
        }
        if len(owners) != 1:
            return None
        shown = []
        for item in groupable:
            field = self._group_field_in(tail, self._metric_dimensions(item["metric"]))
            if self._shown_by_field(item["metric"], field):
                shown.append(item)
        if len({self._logical_key(item["metric"]) for item in shown}) != 1 or len(shown) == len(groupable):
            return None
        chosen = shown[0]
        source_context = plan.get("source_context") or {}
        return self._forced_plan(
            question, intent_result, chosen,
            f"todas las opciones miden la tabla {self._metric_fact_table(chosen['metric'])}; solo esta aparece "
            f"en un visual del tablero desglosada por «{tail}»: se responde con ella",
            consumed_tokens=self._option_words(question, source_context),
        )

    def _group_feasible_options(self, question, intent_result, plan):
        """Contrapregunta de «M por X» (sin opción elegida): las opciones que no
        se pueden desglosar por X no responden la pregunta.
        - Algunas sí y otras no: quedan solo las que sí (una -> se responde).
        - Ninguna: el indicador hermano del mismo tablero que sí se desglosa
          por X y trata el tema (página DETALLE OCUPACIÓN), si es uno solo.
        Devuelve un plan o None (sin cambios)."""
        if plan.get("status") != "ambiguous" or plan.get("reason") is not None:
            return None
        tail = self._requested_group_tail(question)
        resolution = plan.get("metric_resolution") or {}
        items = list(resolution.get("candidates") or [])
        if not tail or len(items) < 2:
            return None
        groupable = [
            item for item in items
            if self._group_field_in(tail, self._metric_dimensions(item.get("metric") or {})) is not None
        ]
        source_context = plan.get("source_context") or {}
        if not groupable:
            return self._group_sibling_plan(
                question, intent_result, [item["metric"] for item in items], tail, source_context,
            )
        if len(groupable) == len(items):
            return self._group_shown_option(question, intent_result, plan, groupable, tail)
        others = [item["metric"] for item in items if item not in groupable]
        text = self._ungroupable_text(others, tail, question)
        self._note(f"opciones depuradas: {text}")
        if len({self._logical_key(item["metric"]) for item in groupable}) == 1:
            chosen = groupable[0]
            words = self._group_topic_words(question, source_context, tail)
            page = self._metric_topic_page(chosen["metric"], words)
            note = self._group_sibling_note(
                others, {"metric": chosen["metric"], "page": page,
                         "field": self._group_field_in(tail, self._metric_dimensions(chosen["metric"])),
                         "words": words},
                tail, question,
            )
            return self._forced_plan(
                question, intent_result, chosen,
                f"única opción que se desglosa por «{tail}»; {text}",
                consumed_tokens=self._option_words(question, source_context),
                visible_note=note, group_sibling=True,
            )
        return {**plan, "metric_resolution": {**resolution, "candidates": groupable}}

    # ---------------- ranking («top 5», «el servicio con más peso») ----------------
    _RANKING_WORDS = {"top", "mas", "mayor", "mayores", "menos", "menor", "menores", "ranking"}
    # «con más de 3 días» / «más que» comparan con una cifra: no son ranking.
    _RANKING_HINT_RE = re.compile(
        r"(?<![a-z0-9])(?:top\s+\d{1,2}|ranking|"
        r"(?:con|tuvo|tiene|tuvieron|tienen|registro|registraron|hizo|hicieron)\s+"
        r"(?:el\s+|la\s+|los\s+|las\s+)?(?:mas|mayor|menos|menor)(?:es)?)(?![a-z0-9])"
        r"(?!\s+(?:de|que)(?![a-z0-9]))"
    )
    _NUMBER_WORDS = {
        "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
        "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    }

    # Ranking pospuesto a la agrupación: «por aseguradora, las 5 más altas»,
    # «por servicio los 10 primeros», «los 3 menores».
    _POSTFIX_TOP_RE = re.compile(
        r"(?<![a-z0-9])(?:(?:los|las)\s+)?(?:top\s+)?"
        r"(?P<n>\d{1,2}|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+"
        r"(?P<how>(?:mas|menos)\s+(?:alt|baj|grand|pequen|import|frecuent|car|barat)[a-z]*"
        r"|mayores|menores|primer[oa]s|ultim[oa]s|principales)(?![a-z0-9])"
    )
    _POSTFIX_ASC_RE = re.compile(r"^(?:menos\b|mas\s+(?:baj|pequen|barat)|menores|ultim)")

    def _postfix_top(self, normalized):
        """(match, dirección) de un ranking pospuesto, o (None, None)."""
        match = self._POSTFIX_TOP_RE.search(normalized)
        if not match:
            return None, None
        return match, ("asc" if self._POSTFIX_ASC_RE.match(match.group("how")) else "desc")

    def _mentions_ranking(self, normalized):
        return bool(self._RANKING_HINT_RE.search(normalized)) or self._postfix_top(normalized)[0] is not None

    def is_ranking(self, question):
        """«top 5 ...», «el servicio con más ...»: pide orden/límite sobre un indicador."""
        return self._mentions_ranking(normalize_text(question))

    def _detect_ranking(self, question, candidates, group_by=None):
        """Orden y límite sobre una agrupación.

        «cuál fue el servicio con más peso» -> SERVICIO, desc, 1;
        «top 5 especialidades con más cirugías» -> ESPECIALIDAD, desc, 5;
        «las sedes con menos atenciones» -> SEDE, asc, sin límite.
        Devuelve None si la pregunta no pide un ranking.
        """
        text = normalize_text(question)
        informal = self._informal_ranking(text)
        if not (self._mentions_ranking(text) or informal):
            return None
        verb = (
            r"(?:con|que\s+(?:tuvo|tiene|tuvieron|tienen|registro|registraron|hizo|hicieron)|"
            r"tuvo|tiene|tuvieron|tienen)\s+(?:el\s+|la\s+|los\s+|las\s+)?"
            r"(?P<dir>mas|mayor(?:es)?|menos|menor(?:es)?)(?![a-z0-9])"
            r"(?!\s+(?:de|que)(?![a-z0-9]))"
        )
        number = r"(?P<n>\d{1,2}|" + "|".join(self._NUMBER_WORDS) + r")"
        fields = [field for field in (group_by or [])] or [
            field for field in candidates if not self._is_temporal_field(field)
        ]
        best = None
        for field in fields:
            aliases = sorted(
                {normalize_text(alias) for alias in field.get("aliases", []) or [] if normalize_text(alias)},
                key=len, reverse=True,
            )
            for alias in aliases:
                if len(alias) < 3:
                    continue
                escaped = re.escape(alias)
                match = re.search(
                    r"(?:(?:top|los|las|primeros|primeras)\s+" + number + r"\s+)?"
                    r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])\s+" + verb,
                    text,
                )
                if not match and informal:
                    # «en qué turno se lava más ropa», «cuál es el antibiótico
                    # que más se usa»: el elemento con más/menos de algo.
                    match = re.search(
                        r"(?<![a-z0-9])(?:que|cual|cuales)\s+(?:es\s+|son\s+|fue\s+|fueron\s+)?"
                        r"(?:el\s+|la\s+|los\s+|las\s+)?" + escaped
                        + r"(?![a-z0-9])\s+(?:[a-z]+\s+){0,4}?(?P<dir>mas|menos)(?![a-z0-9])(?!\s+o\s+menos)",
                        text,
                    )
                top = None
                if not match:
                    top = re.search(
                        r"(?<![a-z0-9])top\s+" + number + r"\s+" + escaped + r"(?![a-z0-9])", text,
                    )
                    if not top:
                        continue
                found = match or top
                raw_n = found.groupdict().get("n")
                limit = None
                if raw_n:
                    limit = int(raw_n) if raw_n.isdigit() else self._NUMBER_WORDS.get(raw_n)
                direction_word = (match.group("dir") if match else "mas")
                direction = "asc" if direction_word.startswith(("menos", "menor")) else "desc"
                plural = alias.endswith("s") and canonical_token(alias) != alias
                if limit is None and match and not plural:
                    limit = 1  # «el servicio con más peso»: solo el primero
                candidate = {
                    "field": field, "direction": direction, "limit": limit,
                    "phrase": found.group(0).strip(),
                    "tokens": {canonical_token(word) for word in self._RANKING_WORDS},
                }
                if best is None or len(candidate["phrase"]) > len(best["phrase"]):
                    best = candidate
                break
        if best is None:
            best = self._postfix_ranking(text, fields)
        return best

    def _postfix_ranking(self, text, fields):
        """«<dimensión> ..., las 5 más altas»: el ranking va DESPUÉS de la
        dimensión nombrada (la última nombrada antes de la frase)."""
        match, direction = self._postfix_top(text)
        if match is None:
            return None
        head = text[:match.start()]
        chosen, position = None, -1
        for field in fields:
            for alias in {normalize_text(alias) for alias in field.get("aliases", []) or []}:
                if len(alias) < 3:
                    continue
                for found in re.finditer(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", head):
                    if found.start() > position:
                        chosen, position = field, found.start()
        if chosen is None:
            return None
        raw_n = match.group("n")
        limit = int(raw_n) if raw_n.isdigit() else self._NUMBER_WORDS.get(raw_n)
        tokens = {canonical_token(word) for word in self._RANKING_WORDS}
        tokens.update(canonical_token(word) for word in match.group(0).split())
        return {
            "field": chosen, "direction": direction, "limit": limit,
            "phrase": match.group(0).strip(), "tokens": tokens,
        }

    @staticmethod
    def _ranking_note(ranking, label):
        order = "de menor a mayor" if ranking.get("direction") == "asc" else "de mayor a menor"
        limit = ranking.get("limit")
        if limit == 1:
            which = "menor" if ranking.get("direction") == "asc" else "mayor"
            return f"Se muestra solo el {label} con {which} valor."
        if limit:
            return f"Ordenado {order}; se muestran los {limit} primeros ({label})."
        return f"Ordenado {order} ({label})."

    # ---------------- preguntas sin indicador ----------------
    _GENERIC_MEASURE_WORDS = {
        "promedio", "media", "mensual", "mensuales", "anual", "anuales", "diario",
        "diaria", "semanal", "porcentaje", "porcentual", "suma", "sumatoria", "tasa",
        "variacion", "proporcion", "participacion", "indicador", "indicadores",
        "metrica", "metricas", "resultado", "resultados", "pendiente", "pendientes",
    }

    def _catalog_vocabulary(self):
        """Palabras (canónicas) que el catálogo conoce: nombres de indicadores,
        informes, páginas, modelos y alias de dimensiones."""
        if getattr(self, "_vocabulary", None) is not None:
            return self._vocabulary
        values = []
        for metric in self.metrics:
            if metric.get("validation_status") != "approved":
                continue
            values.extend(self._metric_names(metric))
            values.extend(self._metric_reports(metric))
            values.extend(self._metric_pages(metric))
            values.append(metric.get("semantic_model"))
        for field in self.dimension_fields:
            values.extend(field.get("aliases", []) or [])
            values.extend([field.get("report"), field.get("page"), field.get("semantic_model")])
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_PAGE_WORDS}
        vocabulary = set()
        for value in values:
            for token in canonical_tokens(value):
                if len(token) >= 3 and token not in ignored and not token.isdigit():
                    vocabulary.add(token)
        self._vocabulary = vocabulary
        return vocabulary

    def catalog_examples(self, limit=2):
        """Indicadores reales para dar ejemplos: uno por modelo, visibles en un
        tablero y sin cifras en el nombre. -> [{"label", "report"}]."""
        by_model = {}
        for metric in self._dedupe_metrics(self.metrics):
            label = str(metric.get("label") or "").strip()
            if (
                metric.get("validation_status") != "approved" or not label
                or not (metric.get("appearances") or []) or re.search(r"\d", label)
            ):
                continue
            model = normalize_text(metric.get("semantic_model"))
            reports = self._metric_reports(metric)
            current = by_model.get(model)
            if current is None or len(label) < len(current["label"]):
                by_model[model] = {"label": label, "report": reports[0] if reports else None}
        return [by_model[key] for key in sorted(by_model)][:limit]

    _GROUPING_TIME_WORDS = {"mes", "ano", "anio", "trimestre", "semestre", "semana", "dia"}

    def grouping_dimension_name(self, text):
        """Nombre (singular) de la dimensión que nombra `text` («especialidades»
        -> «especialidad», «grupo etario») si es un alias de alguna dimensión del
        catálogo, un sinónimo conocido o una granularidad de tiempo; si no, None.
        Lo usa la reescritura de «cada una de las X» / «desglose por X»."""
        from src.semantic.request_phrases import singular

        aliases = self.__dict__.get("_grouping_aliases")
        if aliases is None:
            aliases = set(self._GROUPING_TIME_WORDS)
            for field in self.dimension_fields or []:
                if self._is_temporal_field(field):
                    continue
                for alias in field.get("aliases", []) or []:
                    norm = normalize_text(alias)
                    if norm and len(norm) >= 3 and len(norm.split()) <= 3:
                        aliases.add(norm)
            for canonical, synonyms in DIMENSION_SYNONYMS.items():
                aliases.add(canonical)
                aliases.update(normalize_text(item) for item in synonyms)
            self._grouping_aliases = aliases
        norm = normalize_text(text)
        if not norm:
            return None
        words = norm.split()
        # Primero el singular («especialidades» -> «especialidad»): es la forma
        # con la que se nombra la agrupación («por especialidad»).
        candidates = [" ".join(singular(word) for word in words), norm]
        for candidate in candidates:
            if candidate in self._GROUPING_TIME_WORDS:
                return candidate
            if candidate in aliases and candidate not in GENERIC_QUERY_WORDS and candidate not in STOPWORDS:
                return candidate
        return None

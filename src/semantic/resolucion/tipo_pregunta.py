"""Etapa «clasificar el tipo de pregunta»: descriptiva, numérica, ranking de entidad, listado.

is_descriptive / looks_numeric (auditoría causa 6: preguntas de datos enviadas a RAG; r5 frase
nominal con página), preguntas de entidad activa y ranking (r3 AB04), página con datos nombrada,
indicador nombrado exactamente, periodo no cubierto. Mixin de QueryPlanBuilder, métodos movidos sin
cambios.
"""
import re

from src.semantic.answer_shape import detail_request
from src.semantic.period_parser import PeriodParser
from src.semantic.question_kind import descriptive_phrase
from src.semantic.resolucion.texto import (
    _exact_phrase,
    canonical_phrases,
    canonical_token,
    canonical_tokens,
    DESCRIPTIVE_PATTERNS,
    GENERIC_QUERY_WORDS,
    MONTHS,
    normalize_text,
    NUMERIC_TERM_PATTERNS,
    QUERY_VERB_PATTERNS,
    STOPWORDS,
)


class TipoPreguntaMixin:


    # ---------------- public API ----------------
    def is_descriptive(self, question):
        return self._is_descriptive(normalize_text(question))

    def _is_descriptive(self, normalized):
        return self.descriptive_reason(normalized) is not None

    def descriptive_reason(self, question):
        """Frase que vuelve descriptiva la pregunta («como se calcula», «los
        rangos del», «para que sirve»...) o None. Una pregunta descriptiva va
        al RAG aunque contenga palabras numéricas («porcentaje», «total»)."""
        normalized = normalize_text(question)
        for pattern in DESCRIPTIVE_PATTERNS:
            if re.search(r"(?<![a-z0-9])" + re.escape(pattern) + r"(?![a-z0-9])", normalized):
                return pattern
        return descriptive_phrase(normalized)

    @staticmethod
    def _has_period(normalized):
        months = "|".join(MONTHS)
        return bool(
            re.search(r"(?<![a-z0-9])(?:" + months + r")(?![a-z0-9])", normalized)
            or re.search(r"(?<![0-9])20\d{2}(?![0-9])", normalized)
            # Periodos relativos («este año», «mes pasado», «últimos 3 meses»)
            # y agrupaciones temporales («por mes», «mensual»).
            or PeriodParser().parse(normalized)
            or PeriodParser().granularity(normalized)
        )

    def looks_numeric(self, question, dashboard=None):
        """Detecta intención cuantitativa sin depender del orden ni del género.

        Orden de decisión: 1) definicional -> RAG; 2) término numérico
        (cuánto/cuánta/participación/promedio...); 3) la pregunta resuelve a
        una métrica conocida y pide un dato con verbo ("dime", "cuál fue"),
        menciona un período o «por <dimensión>» (incluye estilo telegráfico).
        """
        normalized = normalize_text(question)
        if not normalized or self._is_descriptive(normalized):
            return False
        # «qué antibióticos se están usando»: valores de una entidad con
        # actividad en un gráfico del tablero (datos, no documentación).
        if self.active_entity_question(question):
            return True
        question = canonical_phrases(question)[0]
        normalized = normalize_text(question)

        if any(
            re.search(r"(?<![a-z0-9])" + term + r"(?![a-z0-9])", normalized)
            for term in NUMERIC_TERM_PATTERNS
        ):
            return True
        # «qué camas están disponibles en UCI», «lista de camas bloqueadas»:
        # piden el listado de un indicador (src/semantic/answer_shape.py).
        if self._detail_list_question(question, dashboard):
            return True

        has_verb = any(
            re.search(r"(?<![a-z0-9])(?:" + verb + r")(?![a-z0-9])", normalized)
            for verb in QUERY_VERB_PATTERNS
        )
        has_period = self._has_period(normalized)
        has_group = bool(re.search(r"(?<![a-z0-9])(?:por|segun)\s+[a-z]", normalized))
        # «top 5 ...», «el servicio con más ...»: un ranking siempre es numérico.
        if self._mentions_ranking(normalized) or self._informal_ranking(normalized):
            return True
        # «cómo va(n) ...», «lista de ...», «los próximos 30 días»: piden datos.
        if self._INFORMAL_DATA_RE.search(normalized):
            return True
        if not (has_verb or has_period or has_group):
            return self._nominal_metric_with_filter(question, dashboard)

        source_context = self._source_context(question, dashboard=dashboard)
        metric_result = self._resolve_metric_flexible(question, source_context)
        if metric_result.get("status") in ("resolved", "ambiguous"):
            return True
        if (has_group or has_period) and self._names_metric_of_named_board(question, source_context):
            return True
        if (has_group or has_period) and self._head_names_visible_metric(question, source_context):
            return True
        # Ningún indicador coincide, pero la pregunta nombra una página que sí
        # tiene indicadores («hospitalizaciones parciales de marzo»).
        pages = self._named_pages(source_context) or (
            [] if source_context.get("board_mentions") else self._topic_pages(question)
        )
        return any(self._page_members(page) for page in pages)

    # Pedidos de datos dichos de forma informal: «cómo va la ocupación», «cómo
    # vamos en cirugías», «lista de pacientes en espera», «los próximos 30
    # días», «las últimas 2 semanas».
    _INFORMAL_DATA_RE = re.compile(
        r"(?<![a-z0-9])(?:"
        r"como\s+(?:va|van|vamos|estuvo|estuvieron)"
        r"|(?:lista|listado|relacion)\s+de\s+(?!(?:l[oa]s\s+)?(?:indicador|pagina|visual|filtro|tablero|medida|"
        r"grafic|reporte|informe|campo|columna|tabla|variable|documento)[a-z]*(?![a-z0-9]))(?:l[oa]s\s+)?[a-z]{3,}"
        r"|(?:proxim|ultim|siguient)[a-z]*\s+(?:\d{1,3}|[a-z]+)\s+(?:dias|semanas|meses|anos|horas)"
        r")(?![a-z0-9])"
    )
    _INFORMAL_RANKING_RE = re.compile(
        r"(?<![a-z0-9])(?:que|cual|cuales)\s+(?:es\s+|son\s+|fue\s+)?(?:el\s+|la\s+|los\s+|las\s+)?"
        r"[a-z]{3,}(?:\s+[a-z]+){0,4}?\s+(?:mas|menos)(?![a-z0-9])(?!\s+o\s+menos)"
    )

    _RANKED_ENTITY_RE = re.compile(
        r"(?<![a-z0-9])(?:que|cual|cuales)\s+(?:es\s+|son\s+|fue\s+|fueron\s+)?(?:el\s+|la\s+|los\s+|las\s+)?"
        r"(?P<entity>[a-z]{4,})(?:\s+[a-z]+){0,4}?\s+(?:mas|menos)(?![a-z0-9])(?!\s+o\s+menos)"
    )

    def _ranked_entity_metric(self, question, intent_result):
        """«¿cuál es el antibiótico que más se está usando?»: ranking informal
        de una entidad sin indicador nombrado. Si un solo indicador visible se
        muestra en un gráfico agrupado por esa entidad (PACIENTES ACTIVOS POR
        TIPO DE ANTIBIÓTICO: PAC_ACT por ANTIBIOTICO), se responde con él
        (agrupado y ordenado); si no hay uno solo, None."""
        normalized = normalize_text(question)
        match = self._RANKED_ENTITY_RE.search(normalized)
        active = None
        if not match or not self._informal_ranking(normalized):
            # «qué antibióticos se están usando (ahorita)»: qué valores de la
            # entidad tienen actividad = el indicador del gráfico por esa
            # entidad, agrupado (holdout H29).
            active = self._ACTIVE_ENTITY_RE.search(normalized)
            if not active:
                return None
            match = active
        entity = canonical_token(match.group("entity"))
        if entity in {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}:
            return None
        found = self._entity_chart_metrics(entity)
        if len(found) != 1:
            return None
        metric, appearance = next(iter(found.values()))
        label = appearance.get("visual_title") or metric.get("label")
        if active is not None:
            self._note(
                f"«{match.group(0).strip()}» pide qué {match.group('entity')} tienen actividad: se usa el "
                f"indicador que el tablero muestra por {match.group('entity')} ({label}), agrupado"
            )
            consumed = {canonical_token(word) for word in (match.group("verb"), "se", "esta", "estan")}
            forced = {
                "status": "resolved", "metric": metric, "matched_name": metric.get("label"),
                "score": self.min_metric_score, "final": True, "consumed_tokens": consumed,
                "candidates": [{"metric": metric, "score": self.min_metric_score,
                                "business_score": self.min_metric_score, "matched_name": metric.get("label")}],
            }
            plan = self._build_plan(f"{question} por {match.group('entity')}", intent_result,
                                    forced_resolution=forced)
            if isinstance(plan, dict) and plan.get("status") == "ready" and plan.get("group_by"):
                return plan
            return None
        return self._ranked_entity_plan(question, intent_result, match, normalized, metric, label)

    # «qué antibióticos se están usando», «qué medicamentos se están dispensando».
    _ACTIVE_ENTITY_RE = re.compile(
        r"(?<![a-z0-9])(?:que|cuales)\s+(?P<entity>[a-z]{4,}s)\s+se\s+(?:esta|estan)\s+(?P<verb>[a-z]{3,}ndo)(?![a-z0-9])"
    )

    def active_entity_question(self, question):
        """¿«qué <entidades> se están <verbo>» con un único gráfico por esa entidad?"""
        match = self._ACTIVE_ENTITY_RE.search(normalize_text(question))
        return bool(match) and len(self._entity_chart_metrics(canonical_token(match.group("entity")))) == 1

    def _entity_chart_metrics(self, entity):
        """{clave lógica: (indicador, aparición)} de los gráficos que agregan por la entidad."""
        index = self._visual_index()
        found = {}
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            model = normalize_text(metric.get("semantic_model"))
            for appearance in metric.get("appearances") or []:
                # Solo gráficos que agregan por la entidad (barras, anillos...):
                # no tarjetas ni tablas de detalle, que listan registros.
                kind = str(appearance.get("visual_type") or "").lower()
                if not kind or any(word in kind for word in ("card", "table", "pivot", "matrix", "slicer")):
                    continue
                visual = index.get((model, str(appearance.get("visual_id"))))
                for field in (visual or {}).get("fields") or []:
                    if field.get("kind") not in (None, "column") or not field.get("column"):
                        continue
                    names = [field.get("column"), field.get("display_name")]
                    if any(
                        canonical_tokens(name) and canonical_tokens(name)[-1] == entity
                        or canonical_tokens(name) == [entity]
                        for name in names if name
                    ):
                        found.setdefault(self._logical_key(metric), (metric, appearance))
                        break
        return found

    def _ranked_entity_plan(self, question, intent_result, match, normalized, metric, label):
        self._note(
            f"«{match.group(0)}» es un ranking de {match.group('entity')} sin indicador nombrado: "
            f"se usa el que el tablero muestra por {match.group('entity')} ({label})"
        )
        # «que más SE ESTÁ USANDO»: el verbo tras «más» es lo que mide el
        # indicador del gráfico, no un filtro.
        rest = normalized[match.end():].split()
        consumed = {canonical_token(word) for word in rest[:4]} if len(rest) <= 4 else set()
        forced = {
            "status": "resolved", "metric": metric, "matched_name": metric.get("label"),
            "score": self.min_metric_score, "final": True, "consumed_tokens": consumed,
            "candidates": [{"metric": metric, "score": self.min_metric_score,
                            "business_score": self.min_metric_score, "matched_name": metric.get("label")}],
        }
        plan = self._build_plan(question, intent_result, forced_resolution=forced)
        if isinstance(plan, dict) and plan.get("status") == "ready" and plan.get("group_by"):
            return plan
        return None

    def _informal_ranking(self, normalized):
        """«¿cuál es el antibiótico que más se usa?», «¿en qué turno se lava
        más ropa?»: el elemento con más/menos de algo es un ranking."""
        if re.search(r"(?<![a-z0-9])mas\s+o\s+menos(?![a-z0-9])", normalized):
            return False
        return bool(self._INFORMAL_RANKING_RE.search(normalized))

    def _head_names_visible_metric(self, question, source_context):
        """«peso de ropa por servicio en lo que va del año»: con agrupación o
        periodo, el sustantivo principal es una palabra del nombre de un
        indicador visible (PESO TOTAL por Mes) aunque el nombre completo no
        coincida: pide datos, no documentación."""
        head = self._head_token(question, source_context)
        if not head or self._weak_name_kind(head):
            return False
        return any(
            metric.get("validation_status") == "approved" and metric.get("appearances")
            and any(
                self._explains(head, [token for token in canonical_tokens(name) if len(token) >= 3])
                for name in (metric.get("label"), metric.get("measure"))
            )
            for metric in self._dedupe_metrics(self.metrics)
        )

    def _names_metric_of_named_board(self, question, source_context):
        """«peso por servicio en lavandería»: la pregunta nombra un tablero
        (routing fuerte) y su sustantivo principal es una palabra del nombre o
        la tabla de un indicador visible de ese tablero (PESO TOTAL por Mes):
        con «por <dimensión>» o un periodo pide datos, no documentación, aunque
        el nombre completo del indicador no coincida."""
        if not (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
            and self._board_named_explicitly(question, source_context)
        ):
            return False
        head = self._head_token(question, source_context)
        if not head:
            return False
        model = normalize_text(source_context.get("semantic_model"))
        return any(
            metric.get("validation_status") == "approved" and metric.get("appearances")
            and normalize_text(metric.get("semantic_model")) == model
            and self._explains(head, self._metric_vocabulary_tokens(metric, with_pages=False))
            for metric in self._dedupe_metrics(self.metrics)
        )

    def _detail_list_question(self, question, dashboard=None):
        """Pregunta de listado («qué <entidad> hay/están», «lista de …») cuya
        entidad resuelve a un indicador: es una pregunta de datos, no de
        documentación."""
        if detail_request(question) is None:
            return False
        source_context = self._source_context(question, dashboard=dashboard)
        metric_result = self._resolve_metric_flexible(question, source_context)
        return metric_result.get("status") in ("resolved", "ambiguous")

    _NOMINAL_MAX_WORDS = 8

    _NOMINAL_NAME_MAX_WORDS = 4
    _LEADING_ARTICLE_RE = re.compile(r"^(?:el|la|los|las|un|una|unos|unas)\s+")

    def _names_indicator_exactly(self, text, source_context):
        """¿La frase completa (sin artículo inicial, 2 a 4 palabras) es el nombre
        de un indicador visible (etiqueta o título de su visual) o de una página
        de un informe que tiene indicadores?"""
        phrase = self._LEADING_ARTICLE_RE.sub("", normalize_text(text).replace("_", " ")).strip()
        words = phrase.split()
        if len(words) < 2 or len(words) > self._NOMINAL_NAME_MAX_WORDS:
            return False
        if self._weak_name_kind(phrase):
            return False

        def same(name):
            return normalize_text(str(name or "").replace("_", " ")) == phrase

        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved" or not metric.get("appearances"):
                continue
            titles = [item.get("visual_title") for item in metric.get("appearances") or []]
            if any(same(name) for name in [metric.get("label"), *titles]):
                return True
        for key, item in self._page_index().items():
            if same(item.get("page")) and self._page_members({
                "semantic_model": item.get("semantic_model"), "page": item.get("page"),
            }):
                return True
        return False

    def period_not_covered(self, question, metric):
        """Tabla del indicador que, según su documentación, no trae el periodo
        de la pregunta («el mes pasado» con las citas de los próximos días);
        None si lo trae o la pregunta no tiene periodo."""
        period, start, end = self._requested_period_bounds(self._metric_business_question(
            question, self._source_context(question)))
        if period is None:
            return None
        return self._metric_misses_period(metric, start, end, pages=True)

    def names_data_page(self, question, dashboard=None):
        """¿La pregunta (frase nominal) es el nombre de una página o indicador
        con datos, solo o seguido de su tablero?"""
        text, _ = canonical_phrases(question)
        if self._is_descriptive(normalize_text(text)):
            return False
        source_context = self._source_context(text, dashboard=dashboard)
        return self._names_indicator_exactly(text, source_context) or self._names_data_page_with_context(text)

    def _names_data_page_with_context(self, text):
        """Frase nominal que empieza por el nombre (2+ palabras) de una página
        con indicadores y cuyo resto solo nombra su tablero o lo que dice su
        documentación («cirugías pendientes de los pacientes de NAOS» ->
        página CIRUGÍAS PENDIENTES del TABLERO NAOS, «pacientes» en su nombre
        funcional): pide las cifras de esa página, no su descripción."""
        phrase = self._LEADING_ARTICLE_RE.sub("", normalize_text(text).replace("_", " ")).strip()
        words = phrase.split()
        if len(words) < 3:
            return False
        functional = self._functional_name_index()
        ignored = self._content_ignored_tokens()
        for item in self._page_index().values():
            page_words = normalize_text(item.get("page")).replace("_", " ").split()
            if len(page_words) < 2 or words[:len(page_words)] != page_words:
                continue
            model = normalize_text(item.get("semantic_model"))
            vocabulary = set(canonical_tokens(item.get("semantic_model")))
            for report in [item.get("report"), *(item.get("reports") or [])]:
                vocabulary.update(canonical_tokens(report))
            for key in (normalize_text(item.get("page")), ""):
                vocabulary.update(canonical_tokens(functional.get((model, key)) or ""))
            rest = [
                canonical_token(word) for word in words[len(page_words):]
                if canonical_token(word) not in ignored and len(word) >= 3
            ]
            if rest and all(self._explains(token, vocabulary) for token in rest) and self._page_members({
                "semantic_model": item.get("semantic_model"), "page": item.get("page"),
            }):
                return True
        return False

    def _nominal_metric_with_filter(self, question, dashboard=None):
        """Frase nominal sin verbo, periodo ni «por ...» que nombra TAL CUAL un
        indicador más un valor de filtro («interconsultas sin responder de
        pediatría»): pide el dato filtrado -> Power BI. El nombre del indicador
        solo («interconsultas sin respuesta») o un tablero («tablero de
        interconsultas») siguen siendo preguntas para la documentación."""
        text, _ = canonical_phrases(question)
        normalized = normalize_text(text)
        words = normalized.split()
        if not words or len(words) > self._NOMINAL_MAX_WORDS:
            return False
        if re.match(r"^(?:el |la |los |las )?(?:tablero|informe|reporte|pagina|dashboard)\b", normalized):
            return False
        source_context = self._source_context(text, dashboard=dashboard)
        # Frase corta que es TAL CUAL el nombre de un indicador o de una página
        # con indicadores («medicamentos vencidos», «interconsultas sin
        # respuesta»): se pide el dato (si es una página, se ofrecen sus
        # indicadores), no la documentación.
        if self._names_indicator_exactly(text, source_context):
            return True
        if self._names_data_page_with_context(text):
            return True
        metric_result = self._resolve_metric_flexible(text, source_context)
        if metric_result.get("status") != "resolved":
            return False
        matched = normalize_text(metric_result.get("matched_name"))
        label = normalize_text((metric_result.get("metric") or {}).get("label"))
        business = normalize_text(self._metric_business_question(text, source_context))
        if not any(name and _exact_phrase(business, name) for name in (matched, label)):
            return False
        notes = self.__dict__.get("_resolution_notes")
        try:
            self._resolution_notes = []
            plan = self._build_plan(text, {"dashboard": dashboard} if dashboard else None)
        except Exception:
            return False
        finally:
            self._resolution_notes = notes
        if not isinstance(plan, dict) or plan.get("status") != "ready" or plan.get("unapplied_terms"):
            return False
        return any(
            item.get("type") == "categorical" and not item.get("temporal")
            and item.get("source") != "query_plan_temporal"
            for item in plan.get("filters") or []
        )

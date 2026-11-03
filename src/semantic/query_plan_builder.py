import json
import math
import os
import re
import threading
import unicodedata
from datetime import date, timedelta
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from src.providers.domain_cache import connection_open, domain_cache_for, identifier_column
from src.semantic import plan_budget
from src.semantic.question_kind import descriptive_phrase
from src.semantic.answer_shape import DETAIL_REQUEST_WORDS, detail_request
from src.semantic.period_parser import (
    GRANULARITY_LABELS,
    MONTH_NAMES as PERIOD_MONTH_NAMES,
    MONTHS as PERIOD_MONTHS,
    TO_DATE_WORDS,
    PeriodParser,
    as_date,
    neutral_phrases,
    split_period,
    year_months,
)

# Funciones y constantes de texto: viven en src/semantic/resolucion/texto.py y se
# reexportan aquí con los mismos nombres (las importan query_engine, app.py y las pruebas).
from src.semantic.resolucion.texto import (  # noqa: F401,E402
    MONTHS,
    GENERIC_QUERY_WORDS,
    FILTER_NEUTRAL_WORDS,
    STOPWORDS,
    REQUEST_WORDS,
    COMMON_VERB_WORDS,
    QUESTION_FORM_WORDS,
    _QUESTION_FORM_TOKENS,
    _GROUP_NEUTRAL_TAIL_WORDS,
    _is_question_form_word,
    BUSINESS_TOKEN_SYNONYMS,
    GENERIC_PAGE_WORDS,
    TECHNICAL_SUFFIXES,
    TEMPORAL_WORDS,
    DESCRIPTIVE_PATTERNS,
    NUMERIC_TERM_PATTERNS,
    QUERY_VERB_PATTERNS,
    SHARE_PHRASES,
    SHARE_RE,
    FILLER_WORDS,
    DIMENSION_SYNONYMS,
    normalize_text,
    _normalize_str,
    _NON_ALNUM_RE,
    _SPACES_RE,
    canonical_token,
    _canonical_str,
    canonical_tokens,
    _VERB_ENDINGS,
    _TRAILING_DETAIL_RE,
    _derived_noun_match,
    _NEGATING_PREFIXES,
    _negated_form,
    _FINITE_VERB_ENDINGS,
    _PARTICIPLE_ENDINGS,
    _verb_participle_match,
    _token_similarity,
    _token_similarity_cached,
    _token_similarity_raw,
    _TYPO_REQUEST_TOKENS,
    _REQUEST_TOKENS,
    _phonetic_token,
    _PHONETIC_REQUEST_TOKENS,
    _is_request_word,
    _stem_token,
    _tokens_match_loosely,
    _alias_prefix,
    _ALIAS_CONNECTORS,
    PHRASE_SYNONYMS,
    PROGRESSIVE_VERB_RE,
    DISTRIBUTION_VERB_RE,
    canonical_phrases,
    _VALUE_CONNECTORS,
    _POLARITY_WORDS,
    _ROMAN_DIGITS,
    _value_word_forms,
    _value_words,
    _word_in_text,
    _value_word_key,
    _stem_token_cached,
    _DOMAIN_ANALYSIS_LOCK,
    _DOMAIN_WORDS_CACHE,
    _DOMAIN_TEXT_CACHE,
    _DOMAIN_CACHE_LIMIT,
    _bounded_put,
    _domain_word_analysis,
    _domain_text_analysis,
    value_contradiction,
    _WORD_CHARS,
    _exact_phrase,
    _phrase_score,
    _original_phrase,
    _unique_strings,
)


# --- etapas del motor (mixins) ---
from src.semantic.resolucion.agrupacion import AgrupacionMixin  # noqa: E402
from src.semantic.resolucion.calificativos import CalificativosMixin  # noqa: E402
from src.semantic.resolucion.catalogo import CatalogoMixin  # noqa: E402
from src.semantic.resolucion.cobertura import CoberturaMixin  # noqa: E402
from src.semantic.resolucion.compuestas import CompuestasMixin  # noqa: E402
from src.semantic.resolucion.contrapregunta import ContrapreguntaMixin  # noqa: E402
from src.semantic.resolucion.dimensiones import DimensionesMixin  # noqa: E402
from src.semantic.resolucion.filtros import FiltrosMixin  # noqa: E402
from src.semantic.resolucion.filtros_tablero import FiltrosTableroMixin  # noqa: E402
from src.semantic.resolucion.homonimos import HomonimosMixin  # noqa: E402
from src.semantic.resolucion.indicador import IndicadorMixin  # noqa: E402
from src.semantic.resolucion.paginas import PaginasMixin  # noqa: E402
from src.semantic.resolucion.periodo import PeriodoMixin  # noqa: E402
from src.semantic.resolucion.tablero import TableroMixin  # noqa: E402
from src.semantic.resolucion.tipo_pregunta import TipoPreguntaMixin  # noqa: E402
from src.semantic.resolucion.valores import ValoresMixin  # noqa: E402


class QueryPlanBuilder(
    CatalogoMixin,
    FiltrosTableroMixin,
    TableroMixin,
    ValoresMixin,
    DimensionesMixin,
    PeriodoMixin,
    FiltrosMixin,
    IndicadorMixin,
    CoberturaMixin,
    TipoPreguntaMixin,
    CompuestasMixin,
    AgrupacionMixin,
    HomonimosMixin,
    PaginasMixin,
    ContrapreguntaMixin,
    CalificativosMixin,
):
    """Planificador determinista: métrica -> modelo -> dimensiones -> DAX."""

    def __init__(
        self,
        master_metrics_path,
        visual_catalog_path,
        source_router,
        powerbi_provider,
        project_root=None,
        min_metric_score=0.74,
        ambiguity_margin=0.055,
        max_implicit_dimensions=6,
        today=None,
    ):
        # Fecha de referencia de los periodos relativos («este año», «mes
        # pasado»): date, callable o None (= hoy). Las pruebas la fijan.
        self.today = today
        self.master_metrics_path = Path(master_metrics_path)
        self.visual_catalog_path = Path(visual_catalog_path)
        self.source_router = source_router
        self.powerbi_provider = powerbi_provider
        self.project_root = Path(
            project_root or self.master_metrics_path.resolve().parents[2]
        ).resolve()
        self.min_metric_score = float(min_metric_score)
        self.ambiguity_margin = float(ambiguity_margin)
        self.max_implicit_dimensions = int(max_implicit_dimensions)
        self.master = self._load_json(self.master_metrics_path, {})
        self.visual_catalog = self._load_json(self.visual_catalog_path, {})
        self.metrics = list(self.master.get("metrics", []) or [])
        self.value_cache = {}
        self.domain_errors = {}  # Fallos temporales XMLA: nunca cachear como dominio vacío.
        self.reports = self._normalize_reports(self.visual_catalog)
        self.dimension_fields = self._build_dimension_index()
        self.static_values = self._build_static_value_index()
        # Agregaciones implícitas documentadas («suma de LAVANDERIA[Peso]»):
        # indicador legítimo de un modelo sin medidas aunque el informe local
        # no traiga el visual (src/semantic/documented_aggregations.py).
        self.metrics = self._with_documented_aggregations(self.metrics)
        # Tarjetas cuyo visual filtra el dato («0-30 DÍAS» = mes <= 1): la
        # expresión del indicador lleva ese filtro.
        self.metrics = self._with_visual_filters(self.metrics)
        # Sumas de dinero (SUM de MONTO/VALOR/COSTO...): se muestran como pesos.
        self.metrics = self._with_value_formats(self.metrics)
        # Título de una tabla («PACIENTES HOSPITALIZADOS») usado como nombre de
        # la columna que suma (TIEMPO_PARA_HOSPITALIZACION): se rotula por su
        # agregación (src/semantic/table_titles.py).
        self.metrics = self._with_table_title_labels(self.metrics)
        # Opcional (POWERBI_DOMAIN_PREWARM=1): precalienta en segundo plano los
        # dominios de las columnas más usadas para nombrar valores.
        self.prewarm_thread = self._maybe_prewarm_domains()

    def _note(self, text):
        """Decisión de resolución que se mostrará en el razonamiento del turno."""
        notes = self.__dict__.get("_resolution_notes")
        if notes is not None and text and text not in notes:
            notes.append(text)

    def build(self, question, intent_result=None, selected_metric_id=None):
        """Plan de la consulta. Las decisiones de resolución del indicador
        (nombres descartados, ambigüedades, calificativos) quedan en
        plan["resolution_notes"] para el razonamiento del turno."""
        notes = []
        previous = self.__dict__.get("_resolution_notes")
        self._resolution_notes = notes
        original_question = question
        question, rewrites = canonical_phrases(question)
        for phrase, replacement in rewrites:
            notes.append(
                f"«{phrase}» se interpretó como «{replacement}»" if replacement
                else f"«{phrase}» es el verbo de la pregunta (no es un indicador ni un filtro): se ignora"
            )
        try:
            # «qué antibióticos se están aplicando»: antes de que el verbo se
            # quite como relleno (canonical_phrases), se mira la forma de la
            # pregunta (valores de una entidad con actividad).
            active = None
            if selected_metric_id is None and self.active_entity_question(original_question):
                active = self._ranked_entity_metric(original_question, intent_result)
                if not (isinstance(active, dict) and active.get("status") == "ready"):
                    active = None
            plan = active or self._build_plan(question, intent_result, selected_metric_id)
            if rewrites and isinstance(plan, dict) and plan.get("question") == question:
                plan["question"] = original_question
            # Si el indicador elegido no admite el filtro/periodo/agrupación
            # pedido pero existe con el mismo nombre en otro tablero, se
            # pregunta cuál antes de decir que no se pudo.
            if (
                selected_metric_id is None and isinstance(plan, dict)
                and plan.get("status") == "unsupported_filter"
                and plan.get("reason") != "possible_dimension_value_not_resolved"
                and (plan.get("metric_resolution") or {}).get("metric")
            ):
                same_name = self._same_name_ambiguity(
                    question, plan.get("source_context") or {}, plan["metric_resolution"],
                )
                if same_name is not None:
                    plan = same_name
            if selected_metric_id is None and active is None:
                plan = self._refine_options(question, intent_result, plan)
        finally:
            self._resolution_notes = previous
        # Filtros del tablero (visual + página) del indicador: la pregunta
        # manda sobre la misma columna y la respuesta dice cuáles se aplicaron.
        plan = self._apply_board_filter_context(plan)
        if notes and isinstance(plan, dict):
            plan["resolution_notes"] = list(dict.fromkeys([*(plan.get("resolution_notes") or []), *notes]))
        return plan

    def _build_plan(self, question, intent_result=None, selected_metric_id=None,
                    forced_resolution=None):
        plan_budget.check("armado del plan")
        intent_result = intent_result or {}
        dashboard = intent_result.get("dashboard")
        source_context = self._source_context(question, dashboard=dashboard)
        metric_result = forced_resolution or self._resolve_metric_flexible(
            question, source_context, selected_metric_id=selected_metric_id,
            with_suggestions=True,
        )
        exploring = selected_metric_id is None and forced_resolution is None

        # Página nombrada sin ese indicador: no se usa el de otra página.
        if exploring and metric_result.get("page_hint_ignored"):
            # La página tiene un indicador principal para la pregunta (única
            # tarjeta que la explica sin palabras de más): se responde con él.
            page = metric_result["page_hint_ignored"]
            try:
                choice = self._page_choices(question, source_context, page, [])
            except Exception:
                choice = {}
            if choice.get("direct") and len(choice.get("items") or []) == 1:
                member = choice["items"][0]
                self._note(
                    f"la pregunta nombra la página {self._page_label(page)}: se usa su indicador "
                    f"{member.get('title') or member['metric'].get('label')}"
                )
                forced = {
                    "status": "resolved", "metric": member["metric"],
                    "matched_name": member.get("title") or member["metric"].get("label"),
                    "score": metric_result.get("score"), "final": True,
                    "candidates": [{"metric": member["metric"], "score": metric_result.get("score"),
                                    "business_score": metric_result.get("score"),
                                    "matched_name": member.get("title") or member["metric"].get("label")}],
                }
                plan = self._build_plan(question, intent_result, forced_resolution=forced)
                if isinstance(plan, dict) and plan.get("status") == "ready":
                    return plan
            return self._named_page_rejection(
                question, source_context, metric_result, metric_result["page_hint_ignored"],
            )

        if exploring and (
            metric_result.get("status") == "not_found"
            or (metric_result.get("status") == "ambiguous"
                and self._ACTIVE_ENTITY_RE.search(normalize_text(question)))
        ):
            ranked = self._ranked_entity_metric(question, intent_result)
            if ranked is not None:
                return ranked

        if metric_result.get("status") != "resolved":
            if exploring and metric_result.get("status") == "ambiguous":
                metric_result = self._promote_qualifier_metrics(question, source_context, metric_result)
                same_name = self._homonym_tie_ambiguity(question, source_context, metric_result)
                if same_name is not None:
                    return same_name
            metric_result = self._tidy_unresolved_resolution(question, metric_result)
            plan = {
                "status": metric_result.get("status", "not_found"),
                "stage": "metric",
                "question": question,
                "source_context": source_context,
                "metric_resolution": metric_result,
            }
            if (
                source_context.get("status") == "resolved"
                and source_context.get("routing_strength") == "strong"
                and self._board_named_explicitly(question, source_context)
            ):
                # Para decir «en el tablero X no encontré...» y no «fuera de alcance».
                plan["named_report"] = source_context.get("report") or source_context.get("semantic_model")
            return plan

        # Tablero nombrado en la pregunta sin ese indicador: no se responde con
        # el de otro tablero (ni se ofrece «consultar sin ...» con él).
        if (
            exploring and metric_result.get("source_hint_ignored")
            and self._board_named_explicitly(question, source_context)
        ):
            return self._named_board_rejection(question, source_context, metric_result)

        metric = metric_result["metric"]
        semantic_model = metric.get("semantic_model")
        reports = metric.get("reports", []) or []
        report = metric.get("report") or (reports[0] if reports else source_context.get("report"))
        dropped_dimensions = []
        candidates = self._metric_dimensions(metric, dropped_dimensions)
        # Periodo («entre enero y marzo», «este año») y agrupación temporal
        # («por mes»): sus palabras no son valores ni dimensiones.
        temporal = self._periods_for_metric(question, metric, metric_result.get("matched_name"))
        dimension_question = temporal["clean_question"]
        # «tablero de triage»: las palabras del tablero nombrado no son
        # agrupaciones ni valores de filtro.
        dimension_question, board_tokens = self._strip_board_mentions(
            dimension_question, source_context,
        )

        group_detection = self._detect_group_or_dimension_filter(
            dimension_question, metric, candidates, source_context=source_context,
        )
        group_by = group_detection["group_by"]
        # Un indicador ya decidido al depurar las opciones (`final`) no se
        # vuelve a cambiar por resolver la pregunta sin la agrupación.
        final = selected_metric_id is not None or bool((forced_resolution or {}).get("final"))
        switched = None if final else self._metric_without_group_phrase(
            question, metric_result, group_by, source_context,
        )
        if switched is not None:
            metric_result = switched
            metric = metric_result["metric"]
            semantic_model = metric.get("semantic_model")
            reports = metric.get("reports", []) or []
            report = metric.get("report") or (reports[0] if reports else source_context.get("report"))
            dropped_dimensions = []
            candidates = self._metric_dimensions(metric, dropped_dimensions)
            temporal = self._periods_for_metric(question, metric, metric_result.get("matched_name"))
            dimension_question, board_tokens = self._strip_board_mentions(
                temporal["clean_question"], source_context,
            )
            group_detection = self._detect_group_or_dimension_filter(
                dimension_question, metric, candidates, source_context=source_context,
            )
            group_by = group_detection["group_by"]
        # Ranking («el servicio con más peso», «top 5 especialidades»): la
        # dimensión nombrada se agrupa y el resultado se ordena/limita.
        ranking = self._detect_ranking(question, candidates, group_by)
        if ranking and not group_by:
            group_by = [ranking["field"]]

        # Nunca convertir silenciosamente "por servicio" en total escalar
        # si la metadata de ese informe no expone SERVICIO.
        requested_group = re.search(
            r"\b(?:por|segun|agrupad[oa] por|desglosad[oa] por)\s+"
            r"(?:el|la|los|las)?\s*"
            r"(servicio|servicios|especialidad|especialidades|asegurador(?:a|as|es)?|eps|sexo|estados?|tipos?)\b",
            normalize_text(question),
        )
        # «por X» que solo nombra columnas de tablas que no filtran el
        # indicador: tampoco se agrupa en silencio por ellas.
        group_tail = self._requested_group_tail(question)
        unrelated_group = self._group_field_in(group_tail, dropped_dimensions) if group_tail else None
        if (requested_group or unrelated_group) and not group_by and not group_detection["explicit_filters"]:
            # Otro indicador del mismo tablero que sí se desglosa por X y trata
            # el tema («detalle de ocupación por aseguradores»).
            if not (forced_resolution or {}).get("group_sibling"):
                sibling = self._group_sibling_plan(question, intent_result, [metric], group_tail, source_context)
                if sibling is not None:
                    return sibling
            # Antes de decir que ESTE indicador no se desglosa, ¿la pregunta
            # nombra otro? («tiempo promedio de TRIAGE por eps» eligió TIEMPO
            # GESTION FACTURACION por «promedio de tiempo»).
            if exploring:
                vocabulary = self._metric_vocabulary_tokens(metric)
                tail_tokens = set(canonical_tokens(group_tail))
                pending = [
                    word for word in self._question_content_words(
                        self._metric_business_question(question, source_context)
                    )
                    if canonical_token(word) not in tail_tokens
                    and not self._explains(canonical_token(word), vocabulary)
                ]
                if pending:
                    switched_plan = self._qualifier_metric_switch(
                        question, intent_result, metric, metric_result, source_context, pending,
                    )
                    if switched_plan is not None:
                        return switched_plan
            if unrelated_group is not None:
                self._note(
                    f"«{group_tail}» solo está en {unrelated_group.get('table')}[{unrelated_group.get('column')}], "
                    f"tabla que no filtra {self._metric_fact_table(metric)}: no se agrupa por ella"
                )
            return {
                "status": "unsupported_filter", "stage": "dimensions",
                "reason": "requested_dimension_not_found_in_report",
                "requested_dimension": requested_group.group(1) if requested_group else group_tail,
                "explanation": self._ungroupable_text([metric], group_tail, question) if group_tail else None,
                "question": question, "semantic_model": semantic_model,
                "source_context": source_context, "metric_resolution": metric_result,
            }

        explicit_specs = list(group_detection["explicit_filters"])
        used_fields = {
            (normalize_text(spec["field"].get("table")), normalize_text(spec["field"].get("column")))
            for spec in explicit_specs
        }
        used_fields.update(
            (normalize_text(field.get("table")), normalize_text(field.get("column")))
            for field in group_by
        )
        explicit_specs.extend(
            self._detect_explicit_dimension_filters(
                # La frase de la agrupación ya está explicada: «por areas de
                # servicio» no es además el filtro SERVICIO = «servicio».
                re.sub(
                    r"(?<![a-z0-9])(?:por|segun|agrupad[oa]s?\s+por|desglosad[oa]s?\s+por)\s+"
                    r"(?:(?:el|la|los|las|cada)\s+)?" + re.escape(group_detection["phrase"]) + r"(?![a-z0-9])",
                    " ", dimension_question,
                ) if group_by and group_detection.get("phrase") else dimension_question,
                candidates, already_fields=used_fields,
                metric=metric, source_context=source_context,
            )
        )

        # Un indicador hermano elegido porque el pedido no se desglosaba por X
        # ya se justificó por el tema de la pregunta (su página).
        if selected_metric_id is None and not (forced_resolution or {}).get("group_sibling"):
            rejection = self._metric_evidence_rejection(
                question, metric, metric_result, group_by, explicit_specs, source_context,
            )
            if rejection is not None:
                # El que desplazó al nombre exacto («VALOR ESTIMADO POR
                # SERVICIO» frente a VALOR ESTIMADO) solo coincidía por la
                # agrupación: vuelve el exacto (holdout H24).
                exact = next((
                    item for item in (metric_result or {}).get("candidates") or []
                    if item.get("exact_name_displaced")
                    and self._logical_key(item["metric"]) != self._logical_key(metric)
                ), None)
                if exact is not None and not forced_resolution:
                    self._note(
                        f"{metric.get('label')} solo coincidía por la agrupación: se vuelve al nombre exacto "
                        f"{exact['metric'].get('label')}"
                    )
                    chosen = {key: value for key, value in exact.items() if not str(key).startswith("_")}
                    return self._build_plan(question, intent_result, forced_resolution={
                        "status": "resolved", "metric": exact["metric"], "matched_name": exact.get("matched_name"),
                        "score": exact.get("score"), "final": True, "candidates": [chosen],
                    })
                return rejection

        filters = []
        unapplied_terms = []
        notes = []
        if (forced_resolution or {}).get("visible_note"):
            notes.append(forced_resolution["visible_note"])
        consumed_tokens = set(temporal["tokens"])
        consumed_tokens.update(board_tokens)
        if group_by:
            # «detalle de X por Y»: «detalle» pide la tabla que ya se arma.
            consumed_tokens.update(self._SHAPE_WORDS)
        # Palabras con que se eligió un indicador ya decidido (página nombrada:
        # «promedio» eligió PROM_PD): no son filtros pendientes.
        consumed_tokens.update((forced_resolution or {}).get("consumed_tokens") or ())
        # Indicador general elegido en lugar del de un subservicio: las palabras
        # que explicó («hospitalizados») no son filtros pendientes.
        consumed_tokens.update((metric_result or {}).get("consumed_tokens") or ())
        # «en el hospital», «ocupación general»: todo el hospital, sin filtro
        # (ni exploración de valores ni «No pude aplicar»).
        scope = self._scope_words(dimension_question, metric)
        if scope:
            consumed_tokens.update(canonical_token(word) for word in scope)
            self._note(
                f"«{' '.join(dict.fromkeys(scope))}» se refiere a todo el hospital (sin filtro)"
            )
        # «porcentaje de inasistencia» con %INASISTENCIA: tipo de dato, no filtro.
        measure_words = [
            word for word in self._measure_type_words(dimension_question, metric)
            if canonical_token(word) not in consumed_tokens
        ]
        # «interconsultas pendientes» con INTERCONSULTAS SIN RESPUESTA: el
        # estado pendiente ya es el del indicador.
        if re.search(r"(?<![a-z0-9])pendientes?(?![a-z0-9])", normalize_text(dimension_question)) and (
            self._PENDING_LABEL_RE.search(normalize_text(f"{metric.get('label')} {metric.get('measure') or ''}"))
        ):
            measure_words.append("pendientes")
            consumed_tokens.update({"pendiente", "pendientes"})
        if measure_words:
            consumed_tokens.update(canonical_token(word) for word in measure_words)
            self._note(
                f"«{' '.join(dict.fromkeys(measure_words))}» ya lo dice el indicador "
                f"{metric.get('label')} (tipo de dato o estado): no es un filtro"
            )
        unit = self._counted_unit(question, metric, source_context)
        if unit and unit not in consumed_tokens:
            consumed_tokens.add(unit)
            self._note(
                f"«{unit}» es lo que se cuenta (ningún indicador del catálogo se llama así) y "
                f"{metric.get('label')} es un conteo: es la unidad, no un filtro"
            )
        implicit_decisions = []
        if ranking:
            consumed_tokens.update(ranking["tokens"])
            notes.append(self._ranking_note(
                ranking, (ranking["field"].get("aliases") or [ranking["field"]["column"]])[0],
            ))
        if metric_result.get("source_hint_ignored"):
            notes.append(
                "La métrica no existe en el informe mencionado; se usó "
                f"{report or semantic_model}."
            )
        absorbed = self._period_in_metric_note(question, temporal, metric, metric_result)
        if absorbed:
            notes.append(absorbed)
        for spec in explicit_specs:
            field = spec["field"]
            resolved = None
            for option in [field, *spec.get("alternatives", [])]:
                resolved = self._resolve_value(
                    question=question, field=option, semantic_model=semantic_model,
                    value_hint=spec.get("value_hint"), context=spec.get("alias"),
                )
                if resolved:
                    field = option
                    break
            if not resolved and self._names_board(spec.get("value_hint"), source_context, metric, loose=True):
                # El «valor» no existe en la columna pero es el nombre del
                # tablero/informe («... por servicio del tablero lavanderia»):
                # se consume como tablero; con «por <dimensión>» se agrupa.
                key = (normalize_text(field["table"]), normalize_text(field["column"]))
                if spec.get("from_group") and key not in {
                    (normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in group_by
                }:
                    group_by = [*group_by, field]
                self._note(
                    f"«{spec.get('value_hint')}» no es un valor de {field['table']}[{field['column']}] "
                    "sino el nombre del tablero: se toma como tablero"
                    + (f" y se agrupa por {field['column']}" if spec.get("from_group") else "")
                )
                consumed_tokens.update(canonical_tokens(spec.get("value_hint")))
                if not spec.get("from_group"):
                    used_fields.discard(key)
                continue
            if not resolved:
                return {
                    "status": "unsupported_filter", "stage": "dimension_value",
                    "reason": "requested_value_not_found",
                    "requested_value": spec.get("value_hint"),
                    "dimension": {"table": field["table"], "column": field["column"]},
                    "question": question, "semantic_model": semantic_model,
                    "source_context": source_context, "metric_resolution": metric_result,
                    "domain_error": self.domain_errors.get((semantic_model, field["table"], field["column"])),
                }
            filters.append(self._categorical_filter(
                field, resolved, "query_plan_explicit_dimension", semantic_model,
            ))
            used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))
            consumed_tokens.update(resolved.get("tokens", ()))
            consumed_tokens.update(canonical_tokens(spec.get("value_hint")))
            for alias in field.get("aliases", []) or []:
                consumed_tokens.update(canonical_tokens(alias))

        # Valores implícitos («cirugía plástica»): se buscan SIEMPRE, también
        # cuando ya hay filtros explícitos o agrupación; así ninguna palabra
        # específica se pierde porque otro filtro coincidió primero.
        self._add_implicit_filters(
            3, question, metric, metric_result, source_context, candidates, group_by,
            used_fields, consumed_tokens, implicit_decisions, filters, semantic_model,
        )

        temporal_result = self._apply_temporal(temporal, candidates, semantic_model, group_by, metric=metric)
        requested_period = temporal_result["unsupported_period"]
        if requested_period:
            rejection = {
                "status": "unsupported_filter", "stage": "temporal_filters",
                "reason": "date_dimension_not_found_in_report",
                "requested_year": requested_period.get("year"),
                "requested_month": requested_period.get("month"),
                "requested_period": requested_period.get("label"),
                "unapplied_terms": temporal_result["unapplied"],
                "explanation": temporal_result.get("explanation"),
                "question": question, "semantic_model": semantic_model,
                "source_context": source_context, "metric_resolution": metric_result,
            }
            # Antes de rendirse por el periodo, un calificativo puede nombrar
            # otro indicador que sí tiene fecha («triages pediátricos en 2025»:
            # TRIAGES de BRIEFING no tiene fecha, TRIAGES_PEDIATRICOS_2025 sí).
            if exploring:
                qualifier = self._resolve_qualifiers(
                    question, intent_result, metric, metric_result, source_context, candidates,
                    group_by, used_fields, consumed_tokens, allow_switch=True,
                )
                if qualifier.get("plan") is not None and qualifier["plan"].get("status") == "ready":
                    return qualifier["plan"]
                # Un candidato casi igual de cercano que sí tiene fecha: «cuánto
                # se demoran en el triage el mes pasado» no es la tarjeta del día
                # (TRIAGES_DIA) sino TIEMPO PARA TRIAGE, que se filtra por mes.
                dated = self._candidate_with_period(question, intent_result, metric, metric_result)
                if dated is not None:
                    return dated
            return rejection
        filters.extend(temporal_result["filters"])
        unapplied_terms.extend(temporal_result["unapplied"])
        notes.extend(temporal_result["notes"])

        # Calificativos que quedaron sin interpretar («triages pediátricos»,
        # «consultas ambulatorias», «de ortopedia de sura»): antes de darlos por
        # no entendidos se prueba (a) otro indicador que los nombre y (b) un
        # valor de dimensión aproximado (plural/género/raíz) del modelo.
        qualifier = self._resolve_qualifiers(
            question, intent_result, metric, metric_result, source_context, candidates,
            group_by, used_fields, consumed_tokens, allow_switch=exploring,
        )
        if qualifier.get("plan") is not None:
            return qualifier["plan"]
        for field, resolved in qualifier.get("filters", []):
            filters.append(self._categorical_filter(
                field, resolved, "query_plan_approximate_value", semantic_model,
            ))
            used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))
            consumed_tokens.update(resolved.get("tokens", ()))
            consumed_tokens.update(canonical_tokens(resolved.get("phrase")))
        consumed_tokens.update(qualifier.get("consumed", ()))
        # Con esas palabras ya explicadas, lo que queda puede ser por sí solo un
        # valor («camas ocupadas en uci»: tras ESTADOS_CAM = OCUPADA, «uci» es
        # SERVICIOS = UCI ADULTOS; antes «ocupadas uci» no coincidía con nada).
        if qualifier.get("filters"):
            self._add_implicit_filters(
                2, question, metric, metric_result, source_context, candidates, group_by,
                used_fields, consumed_tokens, implicit_decisions, filters, semantic_model,
            )

        # El mismo indicador (mismo nombre) en otro tablero/modelo y nada en la
        # pregunta que los distinga: se contrapregunta en lugar de elegir uno.
        # Va después de los calificativos: «triages pediátricos» ya eligió
        # TRIAGES_PEDIATRICOS_2025 y no debe preguntar entre los TRIAGES.
        if exploring:
            same_name = self._same_name_ambiguity(question, source_context, metric_result)
            if same_name is not None:
                return same_name

        # Palabras específicas que ningún filtro explicó. Sin ningún filtro
        # categórico el resultado sería un total engañoso: se detiene. Con
        # otros filtros ya aplicados se continúa, pero se declara lo omitido.
        # Con un indicador elegido por el usuario (botón) no se vuelve a
        # preguntar, pero lo que no se pudo aplicar se declara: «ortopedia» no
        # desaparece en silencio si el indicador elegido no tiene especialidad.
        leftover = self._implicit_value_text(
            question, metric, metric_result.get("matched_name"),
            source_context, group_by, extra_removals=consumed_tokens,
        )
        significant = [token for token in leftover.split() if len(token) >= 3]
        if significant:
            # Verbos y palabras que el indicador ya dice (nombre, página,
            # diccionario, nombre funcional de su página) no son filtros.
            implied, remaining = self.implied_words(metric, significant)
            if implied:
                self._note(
                    f"«{' '.join(implied)}» no es un filtro: es forma de la pregunta o lo dice el propio "
                    f"indicador {metric.get('label')} (su nombre, página o documentación)"
                )
                significant = remaining
                leftover = " ".join(word for word in leftover.split() if word not in implied)
        if significant and exploring:
            # Si lo no interpretado es el núcleo de la pregunta (el sustantivo
            # principal) o pesa más que lo que coincidió con el indicador, no
            # se ofrece «consultarlo sin ...»: se sugieren otros indicadores.
            outweighed = self._unresolved_outweighs_metric(
                question, metric, metric_result, significant, source_context,
            )
            if outweighed is not None:
                return outweighed
        if significant:
            if selected_metric_id is None and not any(
                item.get("type") == "categorical" and item.get("source") != "query_plan_temporal"
                for item in filters
            ) and not group_by:
                # Otro candidato cercano sí entiende esas palabras como filtros
                # («camas ocupadas en uci»: CAMAS de la tabla CAMAS DISPONIBLES
                # tiene ESTADOS_CAM = OCUPADA y SERVICIOS = UCI ADULTOS).
                if exploring:
                    alternative = self._candidate_that_filters(
                        question, intent_result, metric, metric_result, significant,
                    )
                    if alternative is not None:
                        return alternative
                return {
                    "status": "unsupported_filter", "stage": "implicit_dimension",
                    "reason": "possible_dimension_value_not_resolved",
                    "unresolved_text": leftover,
                    "implicit_decisions": implicit_decisions,
                    "question": question, "semantic_model": semantic_model,
                    "source_context": source_context, "metric_resolution": metric_result,
                }
            unapplied_terms.append(" ".join(significant))

        # Nunca se agrupa por una columna de una tabla que no filtra el
        # indicador (repetiría el total en cada fila).
        normalized_group_by = [{
            "table": field["table"],
            "column": field["column"],
            "label": self._group_label(field, metric),
            "source": "query_plan_group_by",
        } for field in group_by if self._dimension_relation(metric, field) != "unrelated"]
        if temporal_result["group"]:
            normalized_group_by = [temporal_result["group"]]

        if not normalized_group_by:
            metric = self._scalar_representative(metric)
        pages = self._metric_pages(metric)
        return {
            "status": "ready",
            "intent": "numeric_query",
            "mode": "grouped" if normalized_group_by else "scalar",
            "question": question,
            "source_context": source_context,
            "semantic_model": semantic_model,
            "report": report,
            "dashboard": metric.get("dashboard") or (pages[0] if pages else None),
            "metric": metric,
            "metric_match": {
                "matched_name": metric_result.get("matched_name"),
                "score": metric_result.get("score"),
                "interpretation": metric_result.get("interpretation"),
            },
            "filters": filters,
            "unapplied_terms": unapplied_terms,
            "notes": notes,
            "implicit_decisions": implicit_decisions,
            "technical_columns_used": self._technical_columns_used(candidates, filters, group_by),
            "board_mentions": [
                mention.get("phrase") for mention in source_context.get("board_mentions") or []
            ],
            "group_by": normalized_group_by,
            "ranking": (
                {key: ranking[key] for key in ("direction", "limit", "phrase")}
                if ranking and normalized_group_by else None
            ),
            "temporal_buckets": temporal_result["buckets"],
            # Estado actual: la respuesta no se presenta como «en lo que va de ...».
            "period": None if temporal_result.get("current_state") else self._period_summary(temporal),
            "dimension_candidates_checked": min(len(candidates), 20),
        }

    def _add_implicit_filters(self, rounds, question, metric, metric_result, source_context, candidates,
                              group_by, used_fields, consumed_tokens, implicit_decisions, filters,
                              semantic_model):
        """Hasta `rounds` filtros de valores implícitos («cirugía plástica»). Agrega a `filters`,
        `used_fields` y `consumed_tokens` (los modifica en el sitio). Antes era un bloque copiado
        dos veces en _build_plan (3 y 2 vueltas)."""
        for _ in range(rounds):
            implicit = self._resolve_implicit_filter(
                question=question, metric=metric,
                matched_name=metric_result.get("matched_name"),
                source_context=source_context, candidates=candidates,
                group_by=group_by, used_fields=used_fields,
                extra_removals=consumed_tokens, decisions=implicit_decisions,
            )
            if not implicit:
                break
            field = implicit["field"]
            implicit_filter = self._categorical_filter(
                field, implicit, "query_plan_implicit_value", semantic_model,
            )
            if implicit.get("reason"):
                implicit_filter["reason"] = implicit["reason"]
            filters.append(implicit_filter)
            used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))
            consumed_tokens.update(implicit.get("tokens", ()))

    _PERIOD_SWITCH_SCORE_GAP = 0.25

    def _candidate_with_period(self, question, intent_result, metric, metric_result):
        """Plan listo con el siguiente candidato cercano (mismo tema, a menos
        de _PERIOD_SWITCH_SCORE_GAP) cuando el elegido no admite el periodo
        pedido; None si ninguno lo admite."""
        candidates = [
            item for item in metric_result.get("candidates") or []
            if self._logical_key(item["metric"]) != self._logical_key(metric)
        ]
        top = float(metric_result.get("score") or 0.0)
        for item in candidates[: self._FILTER_SWITCH_CANDIDATES]:
            if float(item.get("business_score") or 0.0) < self.min_metric_score:
                continue
            if top - float(item.get("score") or 0.0) > self._PERIOD_SWITCH_SCORE_GAP:
                break
            forced = {
                "status": "resolved", "metric": item["metric"], "matched_name": item.get("matched_name"),
                "score": item.get("score"), "candidates": [item], "final": True,
            }
            plan = self._build_plan(question, intent_result, forced_resolution=forced)
            if isinstance(plan, dict) and plan.get("status") == "ready":
                note = (
                    f"{metric.get('label')} no tiene fecha para el periodo pedido; "
                    f"{item['metric'].get('label')} sí y es casi igual de cercano a la pregunta: se usa"
                )
                self._note(note)
                return plan
        return None

    _FILTER_SWITCH_CANDIDATES = 3
    _FILTER_SWITCH_SCORE_GAP = 0.35

    def _candidate_that_filters(self, question, intent_result, metric, metric_result, unresolved):
        """El indicador elegido no entiende palabras de la pregunta como filtro
        («uci» con CAMAS OCUPADAS de GESTIÓN CAMAS). Si exactamente uno de los
        siguientes candidatos (por puntaje, a poca distancia) arma la consulta
        con filtros y sin palabras pendientes, se usa ese. None si no."""
        best_score = float(metric_result.get("score") or 0.0)
        current = self._logical_key(metric)
        tried, ready = 0, []
        for item in metric_result.get("candidates") or []:
            other = item.get("metric") or {}
            if self._logical_key(other) == current or not other.get("metric_id"):
                continue
            if float(item.get("business_score") or 0.0) < self.min_metric_score:
                continue
            if best_score - float(item.get("score") or 0.0) > self._FILTER_SWITCH_SCORE_GAP:
                continue
            tried += 1
            if tried > self._FILTER_SWITCH_CANDIDATES:
                break
            forced = {
                "status": "resolved", "metric": other,
                "matched_name": item.get("matched_name"), "score": item.get("score"),
                "candidates": [{key: value for key, value in item.items() if not key.startswith("_")}],
                "final": True,
            }
            notes = list(self.__dict__.get("_resolution_notes") or [])
            attempt_notes = []
            previous_exempt = self.__dict__.get("_sibling_exempt")
            self._sibling_exempt = {current}
            try:
                plan = self._build_plan(question, intent_result, forced_resolution=forced)
            except Exception:
                plan = None
            finally:
                self._sibling_exempt = previous_exempt
                if self.__dict__.get("_resolution_notes") is not None:
                    attempt_notes = self._resolution_notes[len(notes):]
                    self._resolution_notes[:] = notes
            if isinstance(plan, dict):
                plan["_attempt_notes"] = attempt_notes
            categorical = [
                entry for entry in (plan.get("filters") or [] if isinstance(plan, dict) else [])
                if entry.get("type") == "categorical" and not entry.get("temporal")
                and entry.get("source") != "query_plan_temporal"
            ]
            # Las palabras que el elegido no entendía deben ser valores de los
            # filtros del otro (no basta con que arme la consulta).
            value_tokens = {
                token for entry in categorical
                for value in [entry.get("value"), *(entry.get("values") or [])] if value is not None
                for token in canonical_tokens(value)
            }
            if (
                isinstance(plan, dict) and plan.get("status") == "ready" and not plan.get("unapplied_terms")
                and categorical
                and all(
                    any(_tokens_match_loosely(canonical_token(word), token) for token in value_tokens)
                    for word in unresolved
                )
            ):
                ready.append((item, plan))
        if len(ready) != 1:
            return None
        item, plan = ready[0]
        for note in plan.pop("_attempt_notes", None) or []:
            self._note(note)
        interpretation = (
            f"{metric.get('label')} no entiende «{' '.join(unresolved)}» como filtro; "
            f"{item['metric'].get('label')} ({item['metric'].get('semantic_model')}) sí: se usa"
        )
        self._note(interpretation)
        plan.setdefault("metric_match", {})["interpretation"] = interpretation
        return plan

    def _period_summary(self, temporal):
        """Periodo interpretado (para el razonamiento y la respuesta), o None."""
        period, granularity = temporal.get("period"), temporal.get("granularity")
        if not period and not granularity:
            return None
        summary = {"today": self._today().isoformat()}
        question = temporal.get("question") or ""
        if period:
            summary.update({
                "phrase": _original_phrase(question, period.get("phrase")),
                "label": period.get("label"),
                "kind": period.get("kind"), "relative": period.get("relative"),
                "start": as_date(period.get("start")).isoformat() if period.get("start") else None,
                "end": as_date(period.get("end")).isoformat() if period.get("end") else None,
                "months": period.get("months"),
            })
        if granularity:
            summary["granularity"] = granularity.get("unit")
            summary["granularity_phrase"] = _original_phrase(question, granularity.get("phrase"))
        return summary

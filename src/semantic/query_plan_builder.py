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
from src.semantic.resolucion.catalogo import CatalogoMixin  # noqa: E402
from src.semantic.resolucion.cobertura import CoberturaMixin  # noqa: E402
from src.semantic.resolucion.compuestas import CompuestasMixin  # noqa: E402
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

    def metric_words(self, question):
        """Palabras de la pregunta que nombran un indicador del catálogo (sin
        contar alias de dimensiones como «especialidad» o «servicio»). Sirve
        para distinguir un seguimiento («y por especialidad») de una pregunta
        nueva completa («y cuántas cirugías programadas»)."""
        if getattr(self, "_metric_vocabulary", None) is None:
            dimension_tokens = set()
            for field in self.dimension_fields:
                table_tokens = set(canonical_tokens(field.get("table")))
                for alias in field.get("aliases", []) or []:
                    dimension_tokens.update(set(canonical_tokens(alias)) - table_tokens)
            for synonyms in DIMENSION_SYNONYMS.values():
                for synonym in synonyms:
                    dimension_tokens.update(canonical_tokens(synonym))
            ignored = {
                canonical_token(word)
                for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
            }
            vocabulary = set()
            for metric in self.metrics:
                if metric.get("validation_status") != "approved":
                    continue
                for name in self._metric_names(metric):
                    for token in canonical_tokens(name):
                        if (
                            len(token) >= 3 and not token.isdigit()
                            and token not in ignored and token not in dimension_tokens
                        ):
                            vocabulary.add(token)
            self._metric_vocabulary = vocabulary
        return [
            word for word in normalize_text(question).split()
            if len(word) >= 3 and any(
                _token_similarity(canonical_token(word), token) >= 0.88
                for token in self._metric_vocabulary
            )
        ]

    def describe_unresolved(self, question):
        """Clasifica una pregunta para la que no se encontró indicador:

        - "generic": solo palabras genéricas («promedio mensual», «cuántos hay»);
        - "unknown": tiene palabras que el catálogo conoce, pero ningún indicador;
        - "out_of_scope": ninguna palabra distintiva aparece en el catálogo
          («cuánto gana un médico en Colombia»).
        """
        ignored = {
            canonical_token(word)
            for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS
            | set(MONTHS) | self._GENERIC_MEASURE_WORDS | self._RANKING_WORDS
        }
        words = [
            word for word in normalize_text(question).split()
            if canonical_token(word) not in ignored and not word.isdigit()
            and len(word) >= 3 and not _is_request_word(canonical_token(word))
        ]
        vocabulary = self._catalog_vocabulary()
        known = [
            word for word in words
            if any(_token_similarity(canonical_token(word), token) >= 0.88 for token in vocabulary)
        ]
        if not words:
            kind = "generic"
        elif known:
            kind = "unknown"
        else:
            kind = "out_of_scope"
        return {
            "kind": kind, "words": words, "known_words": known,
            "examples": self.catalog_examples(),
        }

    def _note(self, text):
        """Decisión de resolución que se mostrará en el razonamiento del turno."""
        notes = self.__dict__.get("_resolution_notes")
        if notes is not None and text and text not in notes:
            notes.append(text)

    def _refine_options(self, question, intent_result, plan):
        """Revisión final de un plan explorado (sin opción elegida):
        1. tablero nombrado sin opciones de él -> opciones de ese tablero (o
           respuesta directa si una sola explica la pregunta);
        2. opciones sin relación con la pregunta -> fuera;
        3. una sola opción tras agrupar/depurar -> se responde con ella;
        4. respuesta lista pero con un indicador de nombre casi igual en otra
           tabla/tablero -> se contrapregunta."""
        if not isinstance(plan, dict):
            return plan
        # 0. Página nombrada (con «tablero/página de X» o por su tema).
        refined = self._named_page_refinement(question, intent_result, plan)
        if refined is not None:
            if refined.get("status") == "ready" or refined.get("reason") == "options_from_named_page":
                return refined
            if refined.get("status") != plan.get("status"):
                return refined
            plan = refined
        source_context = plan.get("source_context") or {}
        status = plan.get("status")
        if status == "ready":
            similar = self._similar_name_ambiguity(question, source_context, plan)
            return similar if similar is not None else plan
        if status not in ("ambiguous", "not_found") or plan.get("reason") not in (None, "metric_not_in_named_report"):
            if status == "not_found" and (plan.get("metric_resolution") or {}).get("suggestions"):
                plan["metric_resolution"] = self._prune_unrelated_options(
                    question, source_context, plan["metric_resolution"],
                )
            return plan

        resolution = plan.get("metric_resolution") or {}
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        board_model = normalize_text(source_context.get("semantic_model"))
        if strong and plan.get("reason") == "metric_not_in_named_report":
            # El indicador elegido era de otro tablero y se ofrecen los del
            # tablero nombrado: si uno solo explica la pregunta, se responde.
            board_items = [
                item for item in resolution.get("suggestions") or []
                if normalize_text((item.get("metric") or {}).get("semantic_model")) == board_model
            ]
            words = self._option_words(question, source_context)
            full = [
                item for item in board_items
                if words and len(self._option_coverage(item.get("metric"), words)) == len(words)
            ]
            if len(full) == 1:
                board = source_context.get("report") or source_context.get("semantic_model")
                return self._forced_plan(
                    question, intent_result, full[0],
                    f"único indicador del tablero nombrado ({board}) que explica la pregunta",
                )
        if (
            strong and status == "not_found" and plan.get("reason") is None
            and self._board_named_explicitly(question, source_context)
        ):
            # «peso por servicio en lavandería»: ningún nombre alcanzó el
            # puntaje, pero el tablero nombrado tiene UN indicador visible que
            # explica todas las palabras distintivas (PESO TOTAL por Mes): es
            # ese, no una contrapregunta de una sola opción ni la documentación.
            words = self._option_words(question, source_context)
            seen, full = set(), []
            for item in [*(resolution.get("candidates") or []), *(resolution.get("suggestions") or [])]:
                metric = item.get("metric") or {}
                key = self._logical_key(metric)
                if (
                    key in seen or not metric.get("appearances")
                    or normalize_text(metric.get("semantic_model")) != board_model
                ):
                    continue
                seen.add(key)
                # Una palabra que nombra una columna del indicador («el servicio
                # con más peso») también la explica: es la dimensión pedida.
                covered = self._option_coverage(metric, words)
                pending = [word for word in words if word not in covered]
                if pending:
                    dimensions = self._metric_dimensions(metric)
                    covered |= {word for word in pending if self._group_field_in(word, dimensions) is not None}
                if words and len(covered) == len(words):
                    full.append(item)
            if len(full) == 1:
                board = source_context.get("report") or source_context.get("semantic_model")
                return self._forced_plan(
                    question, intent_result, full[0],
                    f"único indicador visible del tablero nombrado ({board}) que explica la pregunta",
                )
        if strong and plan.get("reason") is None and self._board_named_explicitly(question, source_context):
            offered =[*(resolution.get("candidates") or []), *(resolution.get("suggestions") or [])]
            if offered and not any(
                normalize_text((item.get("metric") or {}).get("semantic_model")) == board_model
                for item in offered
            ):
                kind, found = self._named_board_options(question, source_context, resolution)
                board = source_context.get("report") or source_context.get("semantic_model")
                if kind == "resolved":
                    return self._forced_plan(
                        question, intent_result, found,
                        f"único indicador del tablero nombrado ({board}) que explica la pregunta; "
                        "las opciones de otros tableros se descartaron",
                    )
                if kind == "options":
                    self._note(
                        f"la pregunta nombra el tablero {board}: se ofrecen sus indicadores "
                        f"({', '.join(str(i['metric'].get('label')) for i in found)}) y no los de otros tableros"
                    )
                    best = max(float(item.get("score") or 0.0) for item in found)
                    plan = {**plan, "status": "ambiguous", "reason": "options_from_named_board",
                            "named_report": board,
                            "metric_resolution": {"status": "ambiguous",
                                                  "candidates": [{**i, "score": best} for i in found]}}
                    return plan
                plan = {**plan, "reason": "metric_not_in_named_report", "named_report": board}
                self._note(
                    f"la pregunta nombra el tablero {board}, pero no tiene indicadores parecidos: "
                    "se ofrecen los de otros tableros"
                )

        resolution = self._prune_unrelated_options(question, source_context, resolution)
        plan = {**plan, "metric_resolution": resolution}
        # «M por X»: fuera las opciones que no se desglosan por X.
        grouped = self._group_feasible_options(question, intent_result, plan)
        if grouped is not None:
            if grouped.get("status") != "ambiguous":
                return grouped
            plan = grouped
            resolution = plan["metric_resolution"]
        candidates = resolution.get("candidates") or []
        if status == "ambiguous" and plan.get("reason") is None and len(candidates) > 1:
            counting = self._count_question_options(question, candidates)
            # Con solo palabras genéricas («cuántos pendientes hay») la pregunta
            # no nombra ningún indicador: no se reduce a una sola opción.
            _, generic = self._weak_token_sets()
            generic_only = all(
                word in generic or word in {canonical_token(w) for w in self._OPTION_TOPIC_WORDS}
                for word in self._option_words(question, source_context)
            )
            if generic_only and len(counting) < 2:
                counting = []
            if counting and len(counting) < len(candidates):
                plan = {**plan, "metric_resolution": {**resolution, "candidates": counting}}
                resolution = plan["metric_resolution"]
                candidates = counting
        if status == "ambiguous" and plan.get("reason") is None and len(candidates) > 1:
            named = self._options_named_by_question(question, source_context, candidates)
            if len({self._logical_key(item["metric"]) for item in named}) == 1:
                return self._forced_plan(
                    question, intent_result, named[0],
                    "la pregunta dice su nombre completo; las demás opciones añaden palabras que "
                    "la pregunta no dice: se responde sin contrapreguntar",
                )
        if (
            status == "ambiguous" and plan.get("reason") is None and len(candidates) == 1
            and float(candidates[0].get("business_score") or 0.0) >= self.min_metric_score
        ):
            return self._forced_plan(
                question, intent_result, candidates[0],
                "única opción tras agrupar variantes y depurar las que no tienen que ver "
                "con la pregunta: se responde sin contrapreguntar",
            )
        return plan

    # ---------------- calificativos sin interpretar ----------------
    def _resolve_qualifiers(self, question, intent_result, metric, metric_result, source_context,
                            candidates, group_by, used_fields, consumed_tokens, allow_switch=True):
        """Palabras que quedan sin interpretar tras métrica, periodo y filtros:
        0) si nombran la tabla o la página del propio indicador, ya están
           explicadas («consultas ambulatorias» -> tabla CONSULTAS_AMBULATORIAS);
        a) si otro indicador las contiene en su nombre (TRIAGES_PEDIATRICOS_2025),
           se cambia a ese indicador o se contrapregunta entre los que las tienen;
        b) si coinciden de forma aproximada con un valor de dimensión del modelo
           (pediátricos -> PEDIATRIA, menores de edad -> MENORES DE EDAD), se filtra.
        Devuelve {"plan": plan|None, "filters": [(campo, valor)], "consumed": tokens}."""
        result = {"plan": None, "filters": [], "consumed": set()}
        leftover = self._implicit_value_text(
            question, metric, metric_result.get("matched_name"), source_context, group_by,
            extra_removals=consumed_tokens,
        )
        words = [word for word in leftover.split() if len(word) >= 3]
        vocabulary = self._metric_vocabulary_tokens(metric)
        # La agrupación «por servicio» (SERVICIOS de la tabla CAMAS DISPONIBLES)
        # no explica «disponibles»: se buscan las palabras de la tabla también
        # entre las que quitó el nombre de la columna agrupada.
        table_words = list(words)
        if group_by:
            ungrouped = self._implicit_value_text(
                question, metric, metric_result.get("matched_name"), source_context, [],
                extra_removals=consumed_tokens,
            )
            table_words.extend(word for word in ungrouped.split() if len(word) >= 3 and word not in table_words)
        if not words and not table_words:
            return result

        own = [word for word in words if self._explains(canonical_token(word), vocabulary)]
        own_table = [word for word in table_words if self._explains(canonical_token(word), vocabulary)]
        # Una palabra que solo nombra la tabla del indicador pero también es un
        # valor documentado de una de sus columnas se filtra («camas
        # disponibles» en la tabla CAMAS DISPONIBLES -> ESTADOS_CAM = DISPONIBLE).
        for word, field, resolved in self._table_word_filters(
            metric, own_table, candidates, used_fields, metric.get("semantic_model"),
        ):
            result["filters"].append((field, resolved))
            result["consumed"].add(canonical_token(word))
            own = [item for item in own if item != word]
            words = [item for item in words if item != word]
            self._note(
                f"«{word}» nombra la tabla {metric.get('table')} del indicador y además es el valor "
                f"{resolved['value']} de {field['table']}[{field['column']}]: se aplica como filtro"
            )
        if own:
            result["consumed"].update(canonical_token(word) for word in own)
            self._note(
                f"«{' '.join(own)}» ya lo explica el indicador {metric.get('label')} "
                f"(su tabla {metric.get('table')} o su página)"
            )
            words = [word for word in words if word not in own]
        # «hoy», «en este momento» con un indicador sin fecha (estado actual) y
        # unidades genéricas («pacientes»): no son filtros ni otro indicador.
        loose = [word for word in words if canonical_token(word) in self._loose_qualifier_tokens(question)]
        if loose:
            result["consumed"].update(canonical_token(word) for word in loose)
            words = [word for word in words if word not in loose]
            self._note(
                f"«{' '.join(loose)}» es un momento/periodo o una unidad genérica: no es un filtro "
                "ni elige otro indicador"
            )
        if not words:
            return result

        if allow_switch:
            plan = self._qualifier_metric_switch(
                question, intent_result, metric, metric_result, source_context, words,
            )
            if plan is not None:
                result["plan"] = plan
                return result

        # Una palabra que nombra OTRO indicador del mismo modelo («realizadas»
        # junto a CIRUGÍAS PROGRAMADAS) es probablemente otra medida, no un
        # valor: no se aproxima a un valor de dimensión.
        core = [
            canonical_token(word)
            for word in self._question_content_words(self._metric_business_question(question, source_context))
            if word not in words and self._explains(canonical_token(word), vocabulary)
        ]
        siblings = self._sibling_metric_tokens(metric, core)
        candidates_words = [
            word for word in words
            if not self._explains(canonical_token(word), siblings)
        ]
        for field, resolved in self._fuzzy_qualifier_filters(
            metric, candidates, used_fields, candidates_words, question=question,
        ):
            result["filters"].append((field, resolved))
            shown = resolved["value"] if resolved.get("value") is not None else " o ".join(resolved.get("values") or [])
            self._note(
                f"«{resolved['phrase']}» se interpretó como {field['table']}[{field['column']}] = "
                f"{shown} (coincidencia aproximada por raíz/plural)"
            )
        # c) Lo que sigue sin interpretar y la documentación del propio
        # indicador usa para describirlo («aumento de PRECIO», «imágenes
        # DIAGNÓSTICAS»): es parte del indicador, no un filtro.
        filtered = {
            canonical_token(word)
            for _, resolved in result["filters"] for word in str(resolved.get("phrase") or "").split()
        }
        # Sin las palabras de indicadores hermanos («realizadas» junto a
        # CIRUGÍAS PROGRAMADAS es otra medida aunque la documentación la nombre).
        remaining = [word for word in candidates_words if canonical_token(word) not in filtered]
        # El sustantivo principal («LISTA DE PACIENTES en espera») no lo explica
        # la documentación: si el indicador no lo nombra, cuenta otra cosa.
        head = self._head_token(question, source_context)
        remaining = [word for word in remaining if canonical_token(word) != head]
        skip = set(consumed_tokens) | filtered
        for word, evidence in self._documented_qualifiers(question, metric, remaining, skip_tokens=skip):
            result["consumed"].add(canonical_token(word))
            self._note(
                f"«{word}» describe al propio indicador {metric.get('label')} según su documentación "
                f"(«{evidence}»): no es un filtro"
            )
        return result

    # ---------------- documentación del indicador ----------------
    _DOC_TEXT_FIELDS = (
        "description", "visuals", "indicators", "documented_measures", "definitions",
        "business_rules", "notes",
    )

    def _semantic_documents_index(self):
        """{modelo normalizado: [tableros documentados]} de data/semantic_documents."""
        cached = self.__dict__.get("_semantic_documents_cache")
        if cached is not None:
            return cached
        index = {}
        root = self.project_root / "data" / "semantic_documents"
        try:
            paths = sorted(root.rglob("*.json")) if root.exists() else []
        except OSError:
            paths = []
        for path in paths:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(document, dict):
                continue
            model = normalize_text(document.get("semantic_model"))
            for dashboard in document.get("dashboards") or []:
                # El diccionario de variables no es una página: sus medidas y
                # textos no deben contar como documentación de una página.
                if isinstance(dashboard, dict) and not dashboard.get("is_dictionary"):
                    index.setdefault(model, []).append(dashboard)
        self._semantic_documents_cache = index
        return index

    @staticmethod
    def _flatten_texts(value):
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [text for item in value.values() for text in QueryPlanBuilder._flatten_texts(item)]
        if isinstance(value, (list, tuple)):
            return [text for item in value for text in QueryPlanBuilder._flatten_texts(item)]
        return []

    def _metric_documentation(self, metric):
        """Textos que describen el indicador: su descripción, su DAX y la
        documentación del tablero donde está (tablero con el nombre de su
        página o de su nombre/tabla, o cuyas visualizaciones lo nombran)."""
        cache = self.__dict__.setdefault("_metric_documentation_cache", {})
        key = (self._logical_key(metric), normalize_text(metric.get("label")))
        if key in cache:
            return cache[key]
        texts = [str(metric.get(field)) for field in ("description", "model_expression") if metric.get(field)]
        vocabulary = self._metric_vocabulary_tokens(metric, with_pages=False)
        pages = {normalize_text(page) for page in self._metric_pages(metric)}
        stop = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS}
        label = normalize_text(metric.get("label"))
        label_specific = len([t for t in canonical_tokens(label) if t not in stop and not t.isdigit()]) >= 2
        for dashboard in self._semantic_documents_index().get(normalize_text(metric.get("semantic_model")), []):
            name = normalize_text(dashboard.get("name"))
            name_tokens = [t for t in canonical_tokens(name) if t not in stop and len(t) >= 3]
            dashboard_texts = [
                text for field in self._DOC_TEXT_FIELDS for text in self._flatten_texts(dashboard.get(field))
            ]
            linked = name in pages or (name_tokens and all(self._explains(t, vocabulary) for t in name_tokens))
            if linked:
                texts.extend(dashboard_texts)
                continue
            mentions = [text for text in dashboard_texts if label_specific and _exact_phrase(normalize_text(text), label)]
            if mentions:
                texts.extend(mentions)
                texts.extend(self._flatten_texts(dashboard.get("description")))
        cache[key] = texts
        return texts

    def _same_measure_metrics(self, metric):
        """El indicador y los demás aprobados con su misma medida (modelo,
        tabla y expresión), el propio primero."""
        key = self._logical_key(metric)
        result = [metric]
        if not key[-1]:
            return result
        for other in self._dedupe_metrics(self.metrics):
            if other is metric or other.get("validation_status") != "approved":
                continue
            if self._logical_key(other) == key and other.get("metric_id") != metric.get("metric_id"):
                result.append(other)
        return result

    _BREAKDOWN_LABEL_RE = re.compile(r"(?<![a-z0-9])(?:por|x|segun)\s+[a-z]")

    def _scalar_representative(self, metric):
        """Para un valor único, el nombre de un gráfico «PACIENTES por
        ASEGURADORA» describe un desglose que no se muestra: si la misma
        medida está en una tarjeta («TOTAL PACIENTES»), se responde con ella."""
        if not self._BREAKDOWN_LABEL_RE.search(normalize_text(metric.get("label"))):
            return metric
        for other in self._same_measure_metrics(metric)[1:]:
            if self._BREAKDOWN_LABEL_RE.search(normalize_text(other.get("label"))):
                continue
            if any(item.get("visual_type") == "card" for item in other.get("appearances") or []):
                self._note(
                    f"{metric.get('label')} es la misma medida que la tarjeta {other.get('label')}: "
                    "para un valor único se responde con la tarjeta"
                )
                return other
        return metric

    def _documented_qualifiers(self, question, metric, words, skip_tokens=()):
        """[(palabra, evidencia)] de las palabras que la documentación del
        indicador usa y que en la pregunta califican a una palabra del propio
        indicador (vecina inmediata, saltando conectores): «compras con
        aumento de PRECIO» (aumento ∈ nombre; «precios» en la documentación).
        Nunca palabras de dimensión (servicio, especialidad...)."""
        if not words:
            return []
        # La misma medida publicada en otra página (TOTAL PACIENTES de DETALLE
        # OCUPACIÓN = PACIENTES por ASEGURADORA de INICIO) trae también la
        # documentación de esa página.
        texts = []
        for same in self._same_measure_metrics(metric):
            texts.extend(text for text in self._metric_documentation(same) if text not in texts)
        if not texts:
            return []
        forms = {}
        excluding = {"excluye", "excluyen", "excluia", "excluian", "excluir", "excluyendo", "sin",
                     "salvo", "excepto", "menos", "no"}
        for text in texts:
            normalized = normalize_text(text)
            doc_words = normalized.split()
            for position, doc_word in enumerate(doc_words):
                if len(doc_word) < 4:
                    continue
                # «excluye los triages OBSTETRICOS»: lo que la documentación
                # excluye no describe al indicador.
                if excluding & set(doc_words[max(0, position - 4):position]):
                    continue
                for form in (canonical_token(doc_word), _stem_token(doc_word)):
                    forms.setdefault(form, normalized)
        dimension_words = {
            canonical_token(word) for synonyms in DIMENSION_SYNONYMS.values() for word in synonyms
        } | {canonical_token(word) for word in self.PLAUSIBLE_VALUE_COLUMN_WORDS}
        vocabulary = self._metric_vocabulary_tokens(metric)
        connectors = {
            "de", "del", "la", "el", "los", "las", "con", "en", "y", "a", "al", "por",
            "estan", "esta", "estaban", "estuvieron", "hay", "son", "es", "fueron",
        }
        question_words = normalize_text(question).split()
        found = []
        for word in words:
            token = canonical_token(word)
            if len(token) < 4 or token in dimension_words:
                continue
            evidence = forms.get(token) or forms.get(_stem_token(word))
            if not evidence:
                continue
            adjacent = False
            for index, other in enumerate(question_words):
                if other != word:
                    continue
                for step in (-1, 1):
                    position = index + step
                    while 0 <= position < len(question_words) and (
                        question_words[position] in connectors
                        or (
                            canonical_token(question_words[position]) in skip_tokens
                            and not self._explains(canonical_token(question_words[position]), vocabulary)
                        )
                    ):
                        position += step
                    if 0 <= position < len(question_words) and self._explains(
                        canonical_token(question_words[position]), vocabulary,
                    ):
                        adjacent = True
            if not adjacent:
                continue
            # Fragmento de la documentación alrededor de la palabra (para el razonamiento).
            doc_words = evidence.split()
            spot = next(
                (i for i, doc_word in enumerate(doc_words)
                 if canonical_token(doc_word) == token or _stem_token(doc_word) == _stem_token(word)),
                0,
            )
            snippet = " ".join(doc_words[max(0, spot - 4):spot + 4])
            found.append((word, snippet))
        return found

    def _sibling_metric_tokens(self, metric, core):
        """Palabras de los nombres de los indicadores «hermanos»: del mismo
        modelo y que también nombran el sustantivo de la pregunta (`core`):
        CIRUGÍAS REALIZADAS es hermano de CIRUGÍAS PROGRAMADAS."""
        model = normalize_text(metric.get("semantic_model"))
        own = self._logical_key(metric)
        # Al probar otro candidato porque el elegido no entendía un filtro
        # (_candidate_that_filters), el elegido no cuenta como «hermano»: sus
        # palabras («ocupadas» de CAMAS OCUPADAS) pueden ser valores del otro.
        exempt = frozenset(self.__dict__.get("_sibling_exempt") or ())
        cache = self.__dict__.setdefault("_sibling_tokens_cache", {})
        key = (model, own, tuple(sorted(core)), exempt)
        if key in cache:
            return cache[key]
        _, generic = self._weak_token_sets()
        own_tokens = self._metric_vocabulary_tokens(metric, with_pages=False)
        tokens = set()
        if core:
            for other in self._dedupe_metrics(self.metrics):
                if (
                    other.get("validation_status") != "approved"
                    or normalize_text(other.get("semantic_model")) != model
                    or self._logical_key(other) == own
                    or self._logical_key(other) in exempt
                ):
                    continue
                names = [other.get("label"), other.get("measure")] + [
                    appearance.get("visual_title") for appearance in other.get("appearances") or []
                ]
                for name in names:
                    name_tokens = [t for t in canonical_tokens(name) if not t.isdigit()]
                    if not all(self._explains(token, name_tokens) for token in core):
                        continue
                    tokens.update(
                        token for token in name_tokens
                        if len(token) >= 4 and token not in generic and token not in own_tokens
                    )
        cache[key] = tokens
        return tokens

    _RELATIVE_TIME_TOKENS = frozenset(
        canonical_token(word) for word in (
            "hoy", "ayer", "anteayer", "ahora", "ahorita", "actualmente", "momento",
        )
    )

    def _loose_qualifier_tokens(self, question):
        """Palabras que nunca califican al indicador: el periodo de la
        pregunta, momentos relativos («hoy», «momento») y unidades genéricas."""
        return (
            set(self._period_words(question)) | self._RELATIVE_TIME_TOKENS
            | {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        )

    def _qualifier_metric_switch(self, question, intent_result, metric, metric_result,
                                 source_context, words):
        """Regla 3a: ¿con el calificativo cambia la mejor métrica? Busca
        indicadores cuyo nombre (o tabla/página) contiene el calificativo y el
        sustantivo principal. Uno claramente mejor -> se usa; varios -> se
        contrapregunta entre ellos (y el elegido originalmente).

        Un momento o periodo («hoy», «ayer», «en este momento») y las unidades
        genéricas («pacientes», «casos») no son calificativos: «egresos
        probables para HOY» no es EGRESOS EFECTIVOS HOY ni «cuánto duran los
        PACIENTES en urgencias» es el tiempo de los pacientes hospitalizados."""
        if (metric_result or {}).get("general_indicator"):
            return None  # ya se cambió el de un subservicio por el general
        ignored = self._loose_qualifier_tokens(question)
        dropped = [word for word in words if canonical_token(word) in ignored]
        words = [word for word in words if canonical_token(word) not in ignored]
        if dropped:
            self._note(
                f"«{' '.join(dropped)}» es un momento/periodo o una unidad genérica: "
                "no elige otro indicador"
            )
        if not words:
            return None
        qualifiers = [canonical_token(word) for word in words]
        current_vocabulary = self._metric_vocabulary_tokens(metric)
        # Lo que ya explicaba el indicador elegido (sin palabras genéricas de
        # medida) debe seguir explicado: «cirugías programadas y realizadas»
        # no cambia CIRUGÍAS PROGRAMADAS por CIRUGÍAS REALIZADAS (son dos medidas).
        core = [
            canonical_token(word)
            for word in self._question_content_words(self._metric_business_question(question, source_context))
            if canonical_token(word) not in qualifiers
            and self._explains(canonical_token(word), current_vocabulary)
        ]
        found = self._qualifier_candidates(
            question, source_context, qualifiers, core, exclude={self._logical_key(metric)},
        )
        # «M por X»: si el elegido se desglosa por X, un indicador que no se
        # puede desglosar no responde la pregunta aunque nombre el calificativo.
        groups_by = self._rival_group_check(question, metric)
        found = [item for item in found if groups_by(item["metric"])]
        if not found:
            return None
        # Solo compiten los que responden la pregunta tal como está: fuera los
        # de tablas o páginas del día cuando se pide «mes pasado», y una sola
        # vez el indicador que la misma página muestra en tarjeta y en gráfico.
        covering = self._items_covering_period(
            self._metric_business_question(question, source_context), found,
        )
        if covering is not None:
            found = covering
        found = self._collapse_page_twins(found)
        top = found[0]
        second = found[1] if len(found) > 1 else None
        words_text = " ".join(words)
        clear = (
            top["business_score"] >= self.min_metric_score
            and (second is None or second["_covered"] < top["_covered"]
                 or second.get("_explained", 0) < top.get("_explained", 0)
                 or top["score"] - second["score"] >= self.ambiguity_margin)
        )
        if clear:
            # «hospitalizados» lleva a la tarjeta de un subservicio (URGENCIAS)
            # que la pregunta no nombra: se usa el indicador general del tablero.
            business_question = self._metric_business_question(question, source_context)
            general = self._general_indicator(business_question, source_context, top)
            if general is not None:
                forced = {
                    "status": "resolved", "metric": general["metric"],
                    "matched_name": general["matched_name"], "score": top["score"],
                    "candidates": [{key: value for key, value in general.items() if not key.startswith("_")}],
                    "final": True, "consumed_tokens": general["_consumed"], "general_indicator": True,
                }
                return self._build_plan(question, intent_result, forced_resolution=forced)
            chosen = {key: value for key, value in top.items() if not key.startswith("_")}
            interpretation = (
                f"«{words_text}» forma parte del indicador {top['metric'].get('label')} "
                f"(en lugar de {metric.get('label')}, que no lo explicaba)"
            )
            self._note(interpretation)
            forced = {
                "status": "resolved", "metric": top["metric"],
                "matched_name": top["matched_name"], "score": top["score"],
                "candidates": [chosen], "interpretation": interpretation,
            }
            return self._build_plan(question, intent_result, forced_resolution=forced)

        options = [
            {key: value for key, value in item.items() if not key.startswith("_")}
            for item in found[: self._SUGGESTION_LIMIT - 1]
        ]
        options.append({
            "metric": metric, "score": metric_result.get("score"),
            "business_score": metric_result.get("score"),
            "matched_name": metric_result.get("matched_name"),
        })
        best_score = max(float(item.get("score") or 0.0) for item in options)
        for item in options:
            item["score"] = best_score  # todas se muestran: la pregunta no decide
        self._note(
            f"«{words_text}» aparece en el nombre de otros indicadores "
            f"({', '.join(str(i['metric'].get('label')) for i in options[:-1])}); "
            f"no se ofrece {metric.get('label')} sin ese calificativo: se contrapregunta"
        )
        return {
            "status": "ambiguous", "stage": "metric",
            "reason": "qualifier_matches_other_metrics",
            "question": question, "source_context": source_context,
            "unresolved_text": words_text,
            "metric_resolution": {"status": "ambiguous", "candidates": options},
        }

    def _qualifier_candidates(self, question, source_context, qualifiers, core, exclude=()):
        """Indicadores cuyo nombre, tabla o página explican al menos un
        calificativo y todas las palabras `core`, ordenados (más calificativos
        cubiertos, mejor coincidencia por nombre) y sin variantes por año repetidas.
        Con un tablero nombrado (routing fuerte) solo los de ese modelo; una
        palabra que solo coincide con su nombre pero es una dimensión («por
        eps» no es el TABLERO EPS) no restringe."""
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
            and self._board_named_explicitly(question, source_context)
        )
        named_model = normalize_text(source_context.get("semantic_model")) if strong else ""
        business_question = self._metric_business_question(question, source_context)
        weights = self._token_weight_index()
        stop = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}
        question_words = [
            token for token in canonical_tokens(business_question)
            if token not in stop and len(token) >= 3 and not _is_request_word(token)
        ]

        found, seen = [], set(exclude)
        for other in self._dedupe_metrics(self.metrics):
            if other.get("validation_status") != "approved":
                continue
            if named_model and normalize_text(other.get("semantic_model")) != named_model:
                continue
            logical = self._logical_key(other)
            if logical in seen:
                continue
            # También lo que el filtro de inclusión de su visual le da al
            # indicador («Triages Gineco» filtrada por los valores OBSTETRICA).
            vocabulary = self._metric_vocabulary_tokens(other) | self._inclusion_filter_tokens(other)
            covered = [token for token in qualifiers if self._explains(token, vocabulary)]
            if not covered or not all(self._explains(token, vocabulary) for token in core):
                continue
            # Nombres sin contenido propio («Promedio de MIN») no cuentan, pero
            # tampoco descartan el indicador si su etiqueta sí nombra algo; los
            # conectores del nombre («TIEMPO PROMEDIO PARA ATENCIÓN EN TRIAGE»)
            # no se exigen en la pregunta.
            names = [name for name in self._metric_names(other) if not self._weak_name_kind(name)]
            scored = []
            for name in names:
                scored.append((self._loose_phrase_score(business_question, name, weights), name))
                content_name = " ".join(
                    word for word in normalize_text(name).split() if canonical_token(word) not in stop
                )
                if content_name and content_name != normalize_text(name) and len(content_name.split()) >= 2:
                    scored.append((self._loose_phrase_score(business_question, content_name, weights), name))
            if other.get("table") and other.get("label") and not self._weak_name_kind(other.get("label")):
                scored.append((
                    self._loose_phrase_score(
                        business_question, f"{other.get('label')} {other.get('table')}", weights,
                    ),
                    other.get("label"),
                ))
            # Un visual filtrado («Triages Gineco» con DESCRI_TRIGE en los
            # valores OBSTETRICA, en la página TRIAGES ATENDIDOS) se nombra
            # por su página más lo que su filtro le da: «triages obstétricos
            # atendidos».
            inclusion = self._inclusion_filter_tokens(other)
            if inclusion and other.get("label") and any(self._explains(token, inclusion) for token in covered):
                for page in self._metric_pages(other):
                    scored.append((
                        self._loose_phrase_score(business_question, f"{page} {' '.join(sorted(inclusion))}", weights),
                        other.get("label"),
                    ))
            score, name = max(scored, key=lambda pair: pair[0], default=(0.0, None))
            if score <= 0 or not name:
                continue
            seen.add(logical)
            business = score
            if not other.get("appearances"):
                score -= 0.10
            # Palabras de la pregunta que su propio nombre explica («tiempo
            # PROMEDIO ... triage»): desempata entre los que cubren el calificativo.
            name_tokens = {token for value in names for token in canonical_tokens(value) if len(token) >= 3}
            explained = sum(1 for token in question_words if self._explains(token, name_tokens))
            found.append({
                "metric": other, "score": round(score, 4), "business_score": round(business, 4),
                "matched_name": name, "_covered": len(covered), "_explained": explained,
            })
        # «Recuento de PACNUMDOC» (conteo implícito de un identificador) va
        # detrás de cualquier indicador cuyo propio nombre dice la entidad de la
        # pregunta: su página o su filtro no lo convierten en «triages».
        named = any(item["_explained"] > 0 and not self._implicit_identifier_count(item["metric"])
                    for item in found)
        found.sort(key=lambda item: (
            named and self._implicit_identifier_count(item["metric"]),
            -item["_covered"], -item["_explained"], -item["score"], normalize_text(item["metric"].get("label")),
        ))
        # Un calificativo no lleva a un indicador cuya tabla no trae el periodo
        # pedido («triages de este mes en urgencias» no vuelve a los TRIAGES
        # del día anterior del Briefing).
        period, start, end = self._requested_period_bounds(business_question)
        if period is not None and found:
            kept = [item for item in found if self._metric_misses_period(item["metric"], start, end) is None]
            if len(kept) < len(found):
                self._note(
                    f"«{period.get('label')}»: no se cambia a indicadores cuya tabla no trae ese periodo: "
                    + ", ".join(str(item["metric"].get("label")) for item in found if item not in kept)
                )
                found = kept
        return self._collapse_year_variants(found, question)

    def _promote_qualifier_metrics(self, question, source_context, metric_result):
        """Empate entre indicadores que NO explican una palabra de la pregunta
        («consultas PRIORITARIAS»: Consultas de dos tableros): los indicadores
        que sí la nombran (PRIORITARIAS_2025, tabla CONSULTAS PRIORITARIAS) se
        ofrecen primero. Se sigue contrapreguntando: no se elige por el usuario."""
        candidates = list(metric_result.get("candidates") or [])
        if not candidates:
            return metric_result
        best = max(float(item.get("score") or 0.0) for item in candidates)
        tied = [item for item in candidates if best - float(item.get("score") or 0.0) < self.ambiguity_margin]
        # El tablero del indicador también lo nombra («urgencias» para CANTIDAD
        # DE TRIAGES del TABLERO TIEMPOS URGENCIAS), como en _resolve_metric.
        vocabularies = [
            self._metric_vocabulary_tokens(item["metric"]) | self._board_tokens(item["metric"]) for item in tied
        ]
        business_question = self._metric_business_question(question, source_context)
        content = [canonical_token(word) for word in self._question_content_words(business_question)]
        qualifiers = [t for t in content if not any(self._explains(t, v) for v in vocabularies)]
        if not qualifiers:
            return metric_result
        core = [t for t in content if t not in qualifiers]
        found = self._qualifier_candidates(
            question, source_context, qualifiers, core,
            exclude={self._logical_key(item["metric"]) for item in tied},
        )[:3]
        if not found:
            return metric_result
        promoted = [
            {**{k: v for k, v in item.items() if not k.startswith("_")}, "score": best}
            for item in found
        ]
        promoted_keys = {self._logical_key(item["metric"]) for item in promoted}
        rest = [item for item in candidates if self._logical_key(item["metric"]) not in promoted_keys]
        self._note(
            f"ningún indicador empatado explica «{' '.join(qualifiers)}»; se ofrecen primero los que sí: "
            + ", ".join(str(item["metric"].get("label")) for item in promoted)
        )
        return {**metric_result, "candidates": promoted + rest}

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
        for _ in range(3):
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
            for _ in range(2):
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

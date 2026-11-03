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
from src.semantic.resolucion.catalogo import CatalogoMixin  # noqa: E402
from src.semantic.resolucion.cobertura import CoberturaMixin  # noqa: E402
from src.semantic.resolucion.dimensiones import DimensionesMixin  # noqa: E402
from src.semantic.resolucion.filtros import FiltrosMixin  # noqa: E402
from src.semantic.resolucion.filtros_tablero import FiltrosTableroMixin  # noqa: E402
from src.semantic.resolucion.indicador import IndicadorMixin  # noqa: E402
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

    # ---------------- participación / multi-métrica ----------------
    def _share_match(self, normalized):
        """Frase de participación en el texto, salvo que sea parte del nombre de una métrica."""
        match = SHARE_RE.search(normalized)
        if not match:
            return None
        phrase = match.group(0).strip()
        for metric in self._dedupe_metrics(self.metrics):
            for name in self._metric_names(metric):
                norm = normalize_text(name)
                if norm and phrase in norm and re.search(
                    r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", normalized
                ):
                    return None
        return match

    def _mentioned_metrics(self, normalized, source_context):
        """Métricas nombradas literalmente (frases completas, sin solaparse)."""
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        model_hint = normalize_text(source_context.get("semantic_model")) if strong else None
        found = []
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            if model_hint and normalize_text(metric.get("semantic_model")) != model_hint:
                continue
            for name in self._metric_names(metric):
                norm = normalize_text(name)
                if len(norm) < 3 or norm in GENERIC_QUERY_WORDS or norm.isdigit():
                    continue
                for m in re.finditer(
                    r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", normalized
                ):
                    found.append({
                        "metric": metric, "name": norm,
                        "start": m.start(), "end": m.end(),
                    })
        found.sort(key=lambda item: (-(item["end"] - item["start"]), item["start"]))
        accepted = []
        for item in found:
            if any(item["start"] < o["end"] and o["start"] < item["end"] for o in accepted):
                continue
            accepted.append(item)
        accepted.sort(key=lambda item: item["start"])
        return accepted

    @staticmethod
    def _metric_key(metric):
        return (
            normalize_text(metric.get("semantic_model")),
            normalize_text(metric.get("label")),
            normalize_text(metric.get("dax_expression")),
        )

    def _distinct_mentions(self, mentions):
        """Una mención por métrica distinta y del mismo modelo semántico."""
        if not mentions:
            return []
        models = {}
        for item in mentions:
            models.setdefault(normalize_text(item["metric"].get("semantic_model")), []).append(item)
        group = max(models.values(), key=len)
        result, seen = [], set()
        for item in group:
            key = self._metric_key(item["metric"])
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    @staticmethod
    def _cut_spans(text, spans):
        """Quita tramos [(ini, fin)] y la conjunción pegada a ellos."""
        for start, end in sorted(spans, reverse=True):
            left, right = text[:start], text[end:]
            if re.search(r"(?<![a-z0-9])(?:y|e)\s+$", left):
                left = re.sub(r"(?:y|e)\s+$", "", left)
            else:
                right = re.sub(r"^\s*(?:y|e)(?![a-z0-9])", "", right)
            text = left + " " + right
        return re.sub(r"\s+", " ", text).strip()

    def _default_share_metric(self, source_context):
        """Métrica base cuando solo se pide la participación ("participación de X")."""
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        if not strong:
            return {"status": "not_found", "candidates": []}
        model_hint = normalize_text(source_context.get("semantic_model"))
        report_hint = normalize_text(source_context.get("report"))
        pool = []
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            if normalize_text(metric.get("semantic_model")) != model_hint:
                continue
            reports = self._metric_reports(metric)
            if report_hint and reports and not any(normalize_text(r) == report_hint for r in reports):
                continue
            if not metric.get("dax_expression"):
                continue
            if self._is_ratio_metric(metric):
                continue  # un porcentaje/promedio no es la base de una participación
            pool.append(metric)
        if not pool:
            return {"status": "not_found", "candidates": []}

        def rank(metric):
            visuals = sum(
                1 for ap in metric.get("appearances", []) or []
                if "participacion" in normalize_text(ap.get("visual_title"))
            )
            return (visuals, len(metric.get("appearances", []) or []))

        ranked = sorted(pool, key=rank, reverse=True)
        if len(ranked) == 1 or rank(ranked[0]) > rank(ranked[1]):
            return {"status": "resolved", "metric": ranked[0]}
        return {
            "status": "ambiguous",
            "candidates": [
                {"metric": m, "score": 1.0, "business_score": 1.0, "matched_name": m.get("label")}
                for m in ranked[:8]
            ],
        }

    def _unresolved_neighbor(self, normalized, share_span, mentions):
        """Palabra suelta unida con «y» a la participación que no se pudo interpretar."""
        before = normalized[:share_span[0]]
        after = normalized[share_span[1]:]
        word = None
        m = re.search(r"([a-z0-9]+)\s+y\s*$", before)
        if m:
            word = m.group(1)
        else:
            m = re.match(r"\s*y\s+([a-z0-9]+)", after)
            if m:
                word = m.group(1)
        if not word or word in FILLER_WORDS or word in MONTHS or word.isdigit():
            return None
        if any(word in item["name"].split() for item in mentions):
            return None
        dimension_words = {
            canonical_token(alias)
            for field in self.dimension_fields
            for entry in field.get("aliases", [])
            for alias in normalize_text(entry).split()
        }
        if canonical_token(word) in dimension_words:
            return None
        return word

    def build_composite(self, question, intent_result=None, selections=None):
        """Preguntas con participación y/o varias métricas ("peso y participación",
        "cirugías programadas y realizadas", "total de X y promedio de X").

        Devuelve None cuando la pregunta es de una sola métrica (flujo normal).
        Si no: {"status": "composite", "items": [...], "unresolved": [...],
        "grouped": bool} con items {"kind": "metric"|"share", "plan": plan,
        "label": str}, o el plan fallido (ambiguous / unsupported_filter /
        not_found, con "composite": True). Un plan ambiguo de UNA parte trae
        "composite_context" para retomar la compuesta tras la contrapregunta.

        `selections` = {parte: metric_id} elegidos en contrapreguntas previas
        de esta misma compuesta (parte "share" o el índice de la parte).
        """
        intent_result = intent_result or {}
        selections = {str(k): v for k, v in (selections or {}).items()}
        normalized = normalize_text(question)
        if not normalized or self._is_descriptive(normalized):
            return None
        source_context = self._source_context(question, dashboard=intent_result.get("dashboard"))
        share = self._share_match(normalized)
        share_question = None if share else self._share_question_match(normalized)
        share = share or share_question
        mentions = self._distinct_mentions(self._mentioned_metrics(normalized, source_context))

        if not share and not self._mentions_are_coordinated(normalized, mentions):
            # Sin nombres literales coordinados: coordinación por partes
            # («programadas y realizadas», «total de X y promedio de X»).
            return self._coordinated_composite(
                question, intent_result, source_context, selections,
            )

        unresolved = []
        rest_text = normalized
        coordinated_with_share = False
        if share:
            all_mentions = self._mentioned_metrics(normalized, source_context)
            neighbor = self._unresolved_neighbor(normalized, share.span(), all_mentions)
            coordinated_with_share = any(
                self._joined_by_conjunction(normalized, share.span(), (m["start"], m["end"]))
                for m in all_mentions
            )
            rest_text = self._cut_spans(normalized, [share.span()])
            # Muletillas interrogativas que quedan al quitar la participación.
            rest_text = re.sub(
                r"(?<![a-z0-9])(?:que|cual|cuales|fue|fueron|tuvo|tuvieron|tiene|tienen"
                r"|es|son|corresponde|corresponden|correspondio|correspondieron)(?![a-z0-9])",
                " ", rest_text,
            )
            rest_text = re.sub(r"\s+", " ", rest_text).strip()
            if neighbor:
                unresolved.append(neighbor)
                rest_text = re.sub(
                    r"(?<![a-z0-9])y\s+" + re.escape(neighbor) + r"(?![a-z0-9])", " ", rest_text
                )
                rest_text = re.sub(
                    r"(?<![a-z0-9])" + re.escape(neighbor) + r"\s+y(?![a-z0-9])", " ", rest_text
                )
            # La frase de participación puede solaparse con una métrica
            # ("peso relativo"): las menciones se recalculan sobre el resto.
            mentions = self._distinct_mentions(
                self._mentioned_metrics(rest_text, source_context)
            )
            # «qué porcentaje de las atenciones...»: «atenciones» nombra tal
            # cual %ATENCIONES, pero la participación divide un total entre
            # otro; un porcentaje o promedio no es su base.
            ratios = [m for m in mentions if self._is_ratio_metric(m["metric"])]
            if ratios:
                self._note(
                    "en la participación no se usa como base "
                    + ", ".join(str(m["metric"].get("label")) for m in ratios)
                    + " (porcentaje o promedio)"
                )
                mentions = [m for m in mentions if m not in ratios]

        share_note = None
        if share and selections.get("share"):
            chosen = self._approved_metric(selections["share"])
            if chosen is None:
                return None
            targets = [(chosen, rest_text)]
            mentions = []
        elif share and not mentions:
            base = self._share_base_metric(question, rest_text, intent_result, source_context)
            if base.get("status") != "resolved":
                return base
            targets = [(base["metric"], rest_text)]
            share_note = base.get("note")
        else:
            targets = []
            for item in mentions:
                others = [(o["start"], o["end"]) for o in mentions if o is not item]
                targets.append((item["metric"], self._cut_spans(rest_text, others)))

        items, failures, failed_labels = [], [], []
        for metric, sub_question in targets:
            plan = self.build(
                sub_question, intent_result=intent_result,
                selected_metric_id=metric.get("metric_id"),
            )
            if plan.get("status") != "ready":
                plan["composite"] = True
                failures.append(plan)
                failed_labels.append(metric.get("label"))
                continue
            plan["question"] = question
            plan["composite_sub_question"] = sub_question
            items.append({"kind": "metric", "plan": plan, "label": metric.get("label")})

        if not items:
            return failures[0]
        grouped = any(i["plan"].get("mode") == "grouped" for i in items)
        if grouped and (
            not self._same_grouping([i["plan"] for i in items])
            or (not share and len(items) < 2)
        ):
            return None  # Agrupaciones distintas: se mantiene el flujo de una sola.

        if share:
            base = items[0]["plan"]
            if base.get("mode") == "grouped":
                dimension = dict(base["group_by"][0])
                dimension["scope"] = "group"
            else:
                categorical = [
                    f for f in base.get("filters", [])
                    if f.get("type") == "categorical" and not f.get("temporal")
                ]
                if not categorical:
                    return {
                        "status": "unsupported_filter", "stage": "share",
                        "reason": "share_requires_dimension_value",
                        "question": question,
                        "semantic_model": base.get("semantic_model"),
                        "source_context": source_context,
                        "query_plan": base, "composite": True,
                    }
                dimension = {
                    "table": categorical[0]["table"], "column": categorical[0]["column"],
                    "label": categorical[0].get("concept"),
                    "value": categorical[0].get("value"), "scope": "filter",
                }
            share_plan = dict(base)
            share_plan["share_dimension"] = dimension
            items.append({"kind": "share", "plan": share_plan, "label": "Participación"})
            if (
                not mentions or share_question
                or (base.get("mode") == "grouped" and not coordinated_with_share)
            ):
                # Solo participación cuando la pregunta no pidió la métrica
                # base («¿qué participación tuvo X?», «qué porcentaje del peso
                # fue de X», «participación del peso por servicio»). «peso y
                # participación por servicio» pide las dos columnas.
                items = [items[-1]]
            grouped = base.get("mode") == "grouped"

        composite = {
            "status": "composite", "question": question, "items": items,
            "unresolved": unresolved, "failures": failures,
            "failed_labels": failed_labels,
            "source_context": source_context,
            "grouped": grouped,
            "split": "share" if share else "mentions",
        }
        if share_note:
            composite["notes"] = [share_note]
        return composite

    # ---------------- compuestas: utilidades ----------------
    # «qué porcentaje de las atenciones de 2025 fueron de nueva eps»: el
    # verbo final («fueron de», «corresponden a») distingue la participación
    # de un indicador que ya es un porcentaje («qué porcentaje de ocupación»).
    _SHARE_QUESTION_RE = re.compile(
        r"(?<![a-z0-9])(?:que|cual\s+(?:es|fue)\s+el|el)\s+(?:porcentaje|%)\s+(?:de|del)"
        r"(?=\s+(?:(?:el|la|los|las)\s+)?[a-z0-9].*?\s"
        r"(?:fueron|fue|son|es|corresponde|corresponden|correspondio|correspondieron"
        r"|pertenece|pertenecen|pertenecio|pertenecieron)\s+(?:de|a|al|del|para)\s)"
    )

    def _share_question_match(self, normalized):
        match = self._SHARE_QUESTION_RE.search(normalized)
        if not match:
            return None
        core = re.search(r"(?:porcentaje|%)\s+de", match.group(0)).group(0)
        for metric in self._dedupe_metrics(self.metrics):
            for name in self._metric_names(metric):
                norm = normalize_text(name)
                if norm and norm.startswith(core) and re.search(
                    r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", normalized
                ):
                    return None
        return match

    def _approved_metric(self, metric_id):
        for metric in self._dedupe_metrics(self.metrics):
            if (
                metric.get("validation_status") == "approved"
                and str(metric.get("metric_id")) == str(metric_id)
            ):
                return metric
        return None

    @staticmethod
    def _joined_by_conjunction(normalized, left_span, right_span):
        """True si entre los dos tramos solo hay «y»/«e» y muletillas."""
        (a_start, a_end), (b_start, b_end) = sorted([left_span, right_span])
        if a_end > b_start:
            return False
        words = normalized[a_end:b_start].split()
        return (
            bool({"y", "e"} & set(words)) and len(words) <= 4
            and all(w in FILLER_WORDS for w in words)
        )

    def _mentions_are_coordinated(self, normalized, mentions):
        """Varias métricas nombradas literalmente y unidas por «y», «e» o coma."""
        if len(mentions) < 2:
            return False
        for left, right in zip(mentions, mentions[1:]):
            words = normalized[left["end"]:right["start"]].split()
            if (
                not ({"y", "e", "con", "ademas"} & set(words))
                or len(words) > 4
                or any(w not in FILLER_WORDS and w not in {"ademas"} for w in words)
            ):
                return False
        return True

    @staticmethod
    def _grouping_signature(plan):
        if plan.get("mode") != "grouped":
            return None
        if plan.get("temporal_buckets"):
            return ("temporal", tuple(b.get("label") for b in plan["temporal_buckets"]))
        return tuple(
            (normalize_text(g.get("table")), normalize_text(g.get("column")))
            for g in plan.get("group_by") or []
        )

    def _same_grouping(self, plans):
        signatures = {self._grouping_signature(plan) for plan in plans}
        return len(signatures) == 1 and None not in signatures

    def _is_ratio_metric(self, metric):
        """¿El indicador es un porcentaje o un promedio (no se puede sumar)?
        Además de `_metric_measure_kinds`: «%» en el nombre sin normalizar o
        en el formato, o una división entre dos agregaciones
        («DISTINCTCOUNT(...)/DISTINCTCOUNT(...)», sin DIVIDE)."""
        metric = metric or {}
        if self._metric_measure_kinds(metric) & {"percent", "average"}:
            return True
        names = f"{metric.get('label') or ''} {metric.get('measure') or ''}"
        fmt = str(metric.get("format_string") or metric.get("format") or "")
        if "%" in names or "%" in fmt:
            return True
        expression = " ".join(
            str(value) for value in (
                metric.get("base_dax_expression") or metric.get("dax_expression"), metric.get("model_expression"),
                self._measure_expression(metric.get("semantic_model"), metric),
            ) if value
        )
        return bool(re.search(r"\)\s*/\s*\(?\s*[A-Z]+\s*\(", expression, re.IGNORECASE))

    def _share_base_metric(self, question, rest_text, intent_result, source_context):
        """Métrica base de una participación sin indicador nombrado literalmente.

        El resto de la pregunta («las atenciones de 2025 de nueva eps») se
        resuelve como cualquier pregunta. Si el indicador existe en varios
        tableros, se queda el único en el que el valor pedido es un filtro
        válido (la participación lo necesita) o, entre los válidos, el de
        participación del tablero enrutado; si quedan varios, se contrapregunta
        esa parte. Sin indicador reconocible: el de participación del tablero
        enrutado (_default_share_metric).
        """
        default = self._default_share_metric(source_context)
        plan = self.build(rest_text, intent_result=intent_result)
        status = plan.get("status")
        if status == "ready" and self._is_ratio_metric(plan["metric"]):
            # Una participación divide el total con el filtro entre el total
            # sin él: con un porcentaje o un promedio («%ATENCIONES» para «qué
            # porcentaje de las atenciones fueron de nueva eps») esa división
            # no tiene sentido. Se buscan los conteos/sumas que también
            # nombran la pregunta.
            additive = [
                candidate for candidate in self.alternative_metrics(
                    rest_text, intent_result, exclude_ids=[plan["metric"].get("metric_id")], limit=8,
                )
                if not self._is_ratio_metric(candidate.get("metric") or {})
                and float(candidate.get("business_score") or 0.0) >= self.min_metric_score
            ]
            if additive:
                self._note(
                    f"{plan['metric'].get('label')} es un porcentaje/promedio: no sirve de base para una "
                    "participación; se prueban los indicadores que cuentan o suman: "
                    + ", ".join(str(c["metric"].get("label")) for c in additive[:5])
                )
                plan = {**plan, "status": "ambiguous",
                        "metric_resolution": {**(plan.get("metric_resolution") or {}), "candidates": additive}}
                status = "ambiguous"
        if status == "ready":
            return {"status": "resolved", "metric": plan["metric"]}
        if status == "ambiguous":
            viable, seen = [], set()
            for candidate in (plan.get("metric_resolution") or {}).get("candidates") or []:
                metric = candidate.get("metric") or {}
                if self._is_ratio_metric(metric):
                    continue
                key = metric.get("metric_id")
                if not key or key in seen:
                    continue
                seen.add(key)
                trial = self.build(rest_text, intent_result=intent_result, selected_metric_id=key)
                if trial.get("status") == "ready" and (
                    trial.get("mode") == "grouped" or any(
                        f.get("type") == "categorical" and not f.get("temporal")
                        for f in trial.get("filters") or []
                    )
                ):
                    viable.append({**candidate, "_trial": trial})
            if default.get("status") == "resolved" and any(
                self._metric_key(c["metric"]) == self._metric_key(default["metric"]) for c in viable
            ):
                return default
            # Entre los válidos, los que filtran por una columna que el
            # tablero muestra con ese indicador (no una columna técnica sin
            # visual) tienen evidencia de que esa participación tiene sentido.
            shown = [c for c in viable if not c["_trial"].get("technical_columns_used")]
            for group, why in (
                (viable, "el único donde el valor pedido es un filtro válido"),
                (shown, "el único donde el valor pedido se filtra por una columna que el tablero muestra"),
            ):
                if len(group) == 1:
                    metric = group[0]["metric"]
                    where = metric.get("report") or metric.get("semantic_model")
                    return {
                        "status": "resolved", "metric": metric,
                        "note": (
                            f"«{metric.get('label')}» existe en varios tableros; usé el de {where}, "
                            f"{why} para calcular la participación."
                        ),
                    }
            viable = [{k: v for k, v in c.items() if k != "_trial"} for c in viable]
            ambiguous = dict(plan)
            if viable:
                ambiguous["metric_resolution"] = {
                    **(plan.get("metric_resolution") or {}), "candidates": viable,
                }
            ambiguous["question"] = rest_text
            ambiguous["composite"] = True
            ambiguous["composite_context"] = {
                "question": question, "part": "share", "part_text": rest_text,
                "selections": {}, "ready_labels": [],
            }
            return ambiguous
        if default.get("status") == "resolved":
            return default
        return {
            "status": default.get("status", "not_found"),
            "stage": "metric", "question": question,
            "source_context": source_context,
            "metric_resolution": default, "composite": True,
        }

    # ---------------- compuestas por coordinación de partes ----------------
    # «cirugías programadas y realizadas», «interconsultas solicitadas y
    # respondidas», «pacientes atendidos y no atendidos» (coordinación
    # elíptica: la segunda parte comparte el sustantivo de la primera) y
    # «total de triages y promedio mensual de triages» (partes completas).
    # Inicio del resto común (periodo, filtros, tablero) tras la última parte.
    _COORD_HARD_STOPS = {
        "en", "durante", "para", "por", "segun", "desde", "hasta", "entre",
        "este", "esta", "ultimo", "ultimos", "ultima", "ultimas", "hoy", "ayer",
        "agrupado", "agrupada", "desglosado", "desglosada",
    }
    _COORD_VERBS = {
        "hubo", "hay", "fue", "fueron", "tuvo", "tuvieron", "tiene", "tienen",
        "se", "registro", "registraron", "llevamos", "lleva", "van", "va",
    }
    # Palabras de petición/interrogativas antes de cada parte.
    _COORD_LEAD = {
        "cuanto", "cuanta", "cuantos", "cuantas", "cual", "cuales", "que", "dime",
        "dame", "muestrame", "muestra", "indica", "indicame", "necesito", "saber",
        "quiero", "quisiera", "conocer", "consultar", "me", "puedes", "podrias",
        "decir", "dar", "el", "la", "los", "las", "y", "e", "tambien", "ademas",
    }
    _COORD_ARTICLES = {"el", "la", "los", "las"}
    # Terminaciones de participios/adjetivos («programadas», «atendidos»,
    # «ambulatorias»): solo entre ellas se completa la parte elíptica.
    _COORD_ADJ_RE = re.compile(
        r"(?:ad[oa]s?|id[oa]s?|ert[oa]s?|uest[oa]s?|ales?|ic[oa]s?|iv[oa]s?|ari[oa]s?|ori[oa]s?)$"
    )

    @staticmethod
    def _coord_tokens(question):
        """Tokens normalizados conservando las comas (separan partes)."""
        tokens = []
        for index, chunk in enumerate(str(question or "").split(",")):
            if index:
                tokens.append(",")
            tokens.extend(normalize_text(chunk).split())
        return tokens

    def _is_coord_stop(self, token):
        return (
            token in self._COORD_HARD_STOPS or token in self._COORD_VERBS
            or token in MONTHS or bool(re.fullmatch(r"(?:19|20)\d{2}", token))
        )

    def _coordination_splits(self, question, protected_spans=()):
        """Posibles divisiones de la pregunta en partes coordinadas.

        Cada división: {"parts": [{"text", "sub_question", "elliptical",
        "fallback"}], "conjunction": índice}. La primera parte va desde el
        inicio de la frase nominal (tras «cuántas», «el»...) hasta la
        conjunción; las siguientes, hasta el resto común (periodo, «en ...»,
        «de ...», verbo). El resto común se agrega a cada sub-pregunta.
        """
        tokens = self._coord_tokens(question)
        splits = []
        normalized = " ".join(t for t in tokens if t != ",")
        # Posición en el texto normalizado de cada token (para no partir el
        # nombre literal de un indicador como «INGRESOS Y EGRESOS»).
        offsets, cursor = [], 0
        for token in tokens:
            if token == ",":
                offsets.append(cursor)
                continue
            offsets.append(cursor)
            cursor += len(token) + 1

        for k, token in enumerate(tokens):
            if token not in ("y", "e") or k == 0:
                continue
            if any(start <= offsets[k] < end for start, end in protected_spans):
                continue
            # ---- partes antes de la conjunción (la primera y las separadas
            # por comas: «programadas, realizadas y canceladas»), hacia atrás
            # hasta una parada (periodo, «en», verbo) o una palabra de petición.
            segments = []
            end = k
            while True:
                start = end - 1
                while start >= 0:
                    word = tokens[start]
                    if word == "," or self._is_coord_stop(word):
                        break
                    if word in self._COORD_LEAD:
                        previous = tokens[start - 1] if start > 0 else ""
                        if not (word in self._COORD_ARTICLES and previous in ("de", "del", "a", "al")):
                            break
                    start -= 1
                if start + 1 >= end:
                    break
                segments.insert(0, (start + 1, end))
                if start >= 0 and tokens[start] == "," and end - start - 1 <= 3 and len(segments) < 6:
                    end = start
                    continue
                break
            if not segments:
                continue
            first = tokens[segments[0][0]:segments[0][1]]
            middles = [tokens[a:b] for a, b in segments[1:]]
            if not any(w not in self._COORD_LEAD for w in first):
                continue
            prefix = [t for t in tokens[:segments[0][0]] if t != ","]
            # ---- última parte: tras la conjunción hasta el resto común
            pos = k + 1
            own_lead = []
            while pos < len(tokens) and tokens[pos] in self._COORD_LEAD:
                own_lead.append(tokens[pos])
                pos += 1
            last_start = pos
            if pos < len(tokens) and tokens[pos] in ("no", "sin"):
                pos += 1
            while pos < len(tokens):
                word = tokens[pos]
                if word in (",", "y", "e", "de", "del") or self._is_coord_stop(word):
                    break
                pos += 1
            last = tokens[last_start:pos]
            if not last or all(w in ("no", "sin") for w in last):
                continue
            rest = [t for t in tokens[pos:] if t != ","]
            others = [*middles, last]
            parts = [{"text": " ".join(first), "words": first, "own_lead": False}]
            for words in others:
                parts.append({
                    "text": " ".join(words), "words": words,
                    "own_lead": bool(own_lead) and words is last,
                })
            splits.append({
                "conjunction": k, "prefix": prefix, "first": first,
                "parts": parts, "rest": rest, "normalized": normalized,
            })
        return splits

    def _coordination_variants(self, split):
        """Sub-preguntas de cada parte: elíptica («cirugías» + «realizadas»)
        y, como respaldo, la parte tal cual."""
        first = split["first"]
        prefix, rest = split["prefix"], split["rest"]
        # «total de triages y promedio mensual de triages»: el «de triages»
        # del resto ya está en la primera parte (no se repite).
        rest_first = rest
        if rest and rest[0] in ("de", "del"):
            end = 1
            while end < len(rest) and rest[end] not in ("de", "del") and not self._is_coord_stop(rest[end]):
                end += 1
            segment = [w for w in rest[1:end] if w not in self._COORD_ARTICLES]
            if segment and all(w in first for w in segment):
                rest_first = rest[end:]
        variants = [[{
            "text": " ".join(first), "elliptical": False,
            "sub_question": " ".join([*prefix, *first, *rest_first]),
        }]]
        head = first[:-1]
        last_first = first[-1]
        for part in split["parts"][1:]:
            words = part["words"]
            content = [w for w in words if w not in ("no", "sin")]
            options = []
            if (
                head and len(content) == 1
                and self._COORD_ADJ_RE.search(last_first) and self._COORD_ADJ_RE.search(content[0])
            ):
                expanded = [*head, *words]
                options.append({
                    "text": " ".join(expanded), "elliptical": True,
                    "shared": " ".join(head), "original": " ".join(words),
                    "sub_question": " ".join([*prefix, *expanded, *rest]),
                })
            options.append({
                "text": " ".join(words), "elliptical": False,
                "sub_question": " ".join([*prefix, *words, *rest]),
            })
            variants.append(options)
        return variants

    def _coordinated_composite(self, question, intent_result, source_context, selections):
        """Compuesta por partes coordinadas o None si la pregunta no lo es.

        Exige al menos dos partes resueltas con indicadores DISTINTOS (si
        coinciden, la «y» une valores de filtro o dimensiones: flujo normal).
        Una parte ambigua se contrapregunta (con el contexto para retomar la
        compuesta); una parte que no se resuelve se declara.
        """
        normalized = normalize_text(question)
        # «cuántas camas ocupadas hay en uci y cuáles son»: la «y» pide el
        # listado del mismo indicador (answer_shape), no otra medida.
        request = detail_request(question)
        if request is not None and request.get("cue") == "y cuales":
            return None
        protected = [
            (m["start"], m["end"])
            for m in self._mentioned_metrics(normalized, source_context)
            if re.search(r"(?<![a-z0-9])(?:y|e)(?![a-z0-9])", m["name"])
        ]
        for split in self._coordination_splits(question, protected):
            result = self._evaluate_coordination(
                question, split, intent_result, source_context, selections,
            )
            if result is not None:
                return result
        return None

    def _evaluate_coordination(self, question, split, intent_result, source_context, selections):
        built = []
        for index, options in enumerate(self._coordination_variants(split)):
            chosen_id = selections.get(str(index))
            outcome = None
            for option in options:
                plan = self.build(
                    option["sub_question"], intent_result=intent_result,
                    selected_metric_id=chosen_id,
                )
                outcome = {**option, "index": index, "plan": plan}
                if plan.get("status") in ("ready", "ambiguous"):
                    break
            built.append(outcome)

        ready = [b for b in built if b["plan"].get("status") == "ready"]
        keys = {self._metric_key(b["plan"]["metric"]) for b in ready}
        # Una parte ambigua solo cuenta si ofrece indicadores distintos de los
        # ya resueltos; si no, se declara como no resuelta.
        ambiguous = []
        for b in built:
            if b["plan"].get("status") != "ambiguous":
                continue
            resolution = b["plan"].get("metric_resolution") or {}
            options = [
                c for c in resolution.get("candidates") or []
                if self._metric_key(c.get("metric") or {}) not in keys
            ]
            if options:
                b["plan"] = {**b["plan"], "metric_resolution": {**resolution, "candidates": options}}
                ambiguous.append(b)
            else:
                b["plan"] = {**b["plan"], "status": "not_found"}
        if not ready or len(keys) + len(ambiguous) < 2 or (len(keys) < 2 and not ambiguous):
            return None
        if len(keys) < len(ready):
            return None  # Dos partes con el mismo indicador: la «y» une filtros.

        # «peso de antifluidos y urgencias»: «urgencias» es un valor de filtro
        # del primer indicador, no otro indicador.
        first = built[0]
        if first["plan"].get("status") == "ready":
            first_metric = first["plan"]["metric"]
            first_filters = {
                (normalize_text(f.get("table")), normalize_text(f.get("column")), str(f.get("value")))
                for f in first["plan"].get("filters") or []
            }
            for item in built[1:]:
                if item["elliptical"] or len(item["text"].split()) > 2:
                    continue
                trial = self.build(
                    " ".join([*split["prefix"], *split["first"], "de", item["text"], *split["rest"]]),
                    intent_result=intent_result,
                    selected_metric_id=first_metric.get("metric_id"),
                )
                extra = [
                    f for f in trial.get("filters") or []
                    if f.get("type") == "categorical" and not f.get("temporal")
                    and (normalize_text(f.get("table")), normalize_text(f.get("column")), str(f.get("value")))
                    not in first_filters
                ]
                if trial.get("status") == "ready" and extra:
                    return None

        split_note = None
        elliptical = [b for b in built if b.get("elliptical")]
        if elliptical:
            # La segunda parte comparte el sustantivo de la primera.
            split_note = "Interpreté " + ", ".join(
                f"«{b['original']}» como «{b['text']}»" for b in elliptical
            ) + "."

        if ambiguous:
            target = ambiguous[0]
            plan = dict(target["plan"])
            plan["composite"] = True
            plan["composite_context"] = {
                "question": question, "part": str(target["index"]),
                "part_text": target["text"], "selections": dict(selections),
                "ready_labels": [b["plan"]["metric"].get("label") for b in ready],
                "parts": [b["text"] for b in built],
            }
            return plan

        # Todas las partes se presentan con la agrupación de la primera.
        signature = self._grouping_signature(ready[0]["plan"])
        items, failed_labels, failures = [], [], []
        for b in built:
            plan = b["plan"]
            if plan.get("status") != "ready":
                plan["composite"] = True
                failures.append(plan)
                failed_labels.append(b["text"])
                continue
            if self._grouping_signature(plan) != signature:
                failed_labels.append(f"{b['text']} (con otra agrupación)")
                continue
            plan["question"] = question
            plan["composite_sub_question"] = b["sub_question"]
            items.append({
                "kind": "metric", "plan": plan, "label": plan["metric"].get("label"),
                "part": b["text"],
            })
        if len(items) < 2:
            return None
        return {
            "status": "composite", "question": question, "items": items,
            "unresolved": [], "failures": failures, "failed_labels": failed_labels,
            "source_context": source_context,
            "grouped": items[0]["plan"].get("mode") == "grouped",
            "split": "coordination",
            "split_parts": [b["text"] for b in built],
            "notes": [split_note] if split_note else [],
        }

    # ---------------- «cuántas X» ≈ «total de X» ----------------
    _COUNT_WORDS_RE = re.compile(
        r"(?<![a-z0-9])(?:cuant[oa]s?|numero\s+(?:de|del)|cantidad\s+(?:de|del))(?![a-z0-9])"
    )

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

    def _rival_group_check(self, question, best):
        """Filtro para los rivales de nombre igual o parecido en «M por X»: si
        el indicador elegido se desglosa por X, un rival que no se puede
        desglosar por X no responde la pregunta y no se ofrece (PACIENTES
        OBSERVADOS de BRIEFING, tabla sin aseguradora, frente a PACIENTES
        OBSERVADOS POR MES de CONSULTAS PRIORITARIAS para «... por aseguradora»)."""
        tail = self._requested_group_tail(question)
        if not tail or self._group_field_in(tail, self._metric_dimensions(best)) is None:
            return lambda metric: True
        return lambda metric: self._group_field_in(tail, self._metric_dimensions(metric)) is not None

    # Pregunta por el estado presente («cuántas camas hay AHORITA», «cuántas
    # TENEMOS», «ESTÁN ocupadas»), no por lo ocurrido («cuántos egresos hubo»)
    # ni un simple «hay» («¿cuántas cirugías hay?» sigue siendo ambigua).
    _PRESENT_STATE_RE = re.compile(
        r"(?<![a-z0-9])(?:tenemos|estan|quedan|ahorita|ahora|actualmente"
        r"|en\s+este\s+momento|en\s+el\s+momento)(?![a-z0-9])"
    )

    def _homonyms_that_answer(self, question, metric_result, items, current_state=True):
        """Homónimos entre los que vale la pena preguntar. Regla general: solo
        se contrapregunta entre fuentes que pueden dar una cifra para la
        pregunta tal como está escrita.
        1. Con periodo o «por X», se arma la consulta con cada uno: el que no
           queda lista (sin fecha para «mes pasado», sin la columna X) no
           responde y sale. Si ninguno responde, no hay nada que preguntar ([]).
        2. Sin periodo (estado actual: «cuántas camas hay ahorita»), una medida
           que ningún visual muestra no es lo que el usuario ve en el tablero:
           si exactamente un homónimo está en un visual, es ese.
        Devuelve None si no descarta nada; si no, la lista que queda."""
        normalized = normalize_text(question)
        period = bool(self._has_period(normalized))
        tail = self._requested_group_tail(question)
        kept = list(items)
        if period or tail:
            ready, dropped = [], []
            for item in kept:
                forced = {
                    "status": "resolved", "metric": item["metric"],
                    "matched_name": item.get("matched_name") or item["metric"].get("label"),
                    "score": item.get("score"),
                    "candidates": [{key: value for key, value in item.items() if not key.startswith("_")}],
                    "final": True,
                }
                notes = list(self.__dict__.get("_resolution_notes") or [])
                try:
                    plan = self._build_plan(question, None, forced_resolution=forced)
                except Exception:
                    plan = None
                finally:
                    if self.__dict__.get("_resolution_notes") is not None:
                        self._resolution_notes[:] = notes
                (ready if isinstance(plan, dict) and plan.get("status") == "ready" else dropped).append(item)
            what = "el periodo" if period else ""
            what += (" y " if what and tail else "") + (f"«por {tail}»" if tail else "")
            if not ready:
                self._note(
                    f"ninguno de los indicadores de nombre «{metric_result.get('matched_name')}» admite "
                    f"{what}: no se contrapregunta entre ellos"
                )
                return []
            if dropped:
                self._note(
                    "no responden " + what + ": "
                    + ", ".join(f"{i['metric'].get('label')} ({i['metric'].get('semantic_model')})" for i in dropped)
                    + "; no se ofrecen"
                )
            kept = ready
        present = bool(self._PRESENT_STATE_RE.search(normalized))
        if current_state and present and not period and len(kept) > 1:
            shown = [item for item in kept if item["metric"].get("appearances")]
            current = [
                item for item in shown
                if self._snapshot_table(item["metric"], self._metric_dimensions(item["metric"])) is not None
            ]
            if len(shown) == 1 and current == shown:
                hidden = [item for item in kept if item is not shown[0]]
                self._note(
                    f"«{metric_result.get('matched_name')}»: sin periodo se pregunta por el estado actual; "
                    f"solo {shown[0]['metric'].get('label')} ({shown[0]['metric'].get('semantic_model')}) "
                    "lo muestra en un tablero (su tabla es el estado del momento); "
                    + ", ".join(f"{i['metric'].get('label')} ({i['metric'].get('semantic_model')})" for i in hidden)
                    + " no está en ningún visual y sin periodo sumaría todo su histórico: se responde con el primero"
                )
                kept = shown
        return kept if len(kept) < len(items) else None

    def _same_name_ambiguity(self, question, source_context, metric_result):
        """Regla: si el indicador elegido tiene el mismo nombre (o casi:
        sin «total», años ni mayúsculas/guiones) que otros de OTRO modelo o
        informe, y nada en la pregunta los distingue (tablero nombrado,
        página, tabla o palabra que solo uno explica), se contrapregunta.
        Las variantes por año de un mismo modelo cuentan como una opción.

        La penalización de -0.25 a medidas sin visual sigue ordenando las
        opciones, pero ya no basta para responder sin preguntar."""
        best = metric_result.get("metric") or {}
        if not best.get("metric_id"):
            return None
        # El indicador general que reemplazó a la tarjeta de un subservicio se
        # eligió por el tablero de esa tarjeta: no compite por nombre con otros.
        if metric_result.get("general_indicator"):
            return None
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        if strong and normalize_text(source_context.get("semantic_model")) == normalize_text(best.get("semantic_model")):
            return None
        keys = {self._name_key(metric_result.get("matched_name")), self._name_key(best.get("label"))}
        keys.discard(())
        if not keys:
            return None

        business_question = self._metric_business_question(question, source_context)
        question_tokens = canonical_tokens(business_question)
        content = {canonical_token(word) for word in self._question_content_words(business_question)}
        # El tablero también nombra al indicador («en urgencias» para CANTIDAD
        # DE TRIAGES del TABLERO TIEMPOS URGENCIAS, TU04): lo distingue de sus
        # homónimos de otros tableros.
        best_explained = {
            t for t in content
            if self._explains(t, self._metric_vocabulary_tokens(best) | self._board_tokens(best))
        }
        best_page = self._page_bonus(question_tokens, best, set(canonical_tokens(best.get("label"))))

        def where(metric):
            reports = metric.get("reports") or []
            report = metric.get("report") or (reports[0] if reports else "")
            return normalize_text(metric.get("semantic_model")), normalize_text(report)

        # La pregunta nombra el TÍTULO de un visual del elegido («giro cama» =
        # visual «GIRO CAMA» de GIRO_CAMA1): las homónimas que ningún visual
        # muestra (GIRO_CAMA de otra tabla) no son lo que el usuario ve.
        shown_titles = {
            normalize_text(item.get("visual_title")) for item in best.get("appearances") or []
            if item.get("visual_title")
        }
        # Solo si el título no es la propia etiqueta del elegido (TRIAGES con
        # visual «TRIAGES» sigue compitiendo con TOTAL_TRIAGES).
        matched = normalize_text(metric_result.get("matched_name"))
        named_by_title = matched in shown_titles and matched not in {
            normalize_text(best.get("label")), normalize_text(best.get("measure")),
        }
        rivals, seen = [], {self._logical_key(best)}
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            logical = self._logical_key(metric)
            if logical in seen:
                continue
            if named_by_title and not metric.get("appearances"):
                continue
            names =[metric.get("label"), metric.get("measure")] + [
                appearance.get("visual_title") for appearance in metric.get("appearances") or []
            ]
            if not any(name and self._name_key(name) in keys for name in names):
                continue
            explained = {
                t for t in content
                if self._explains(t, self._metric_vocabulary_tokens(metric) | self._board_tokens(metric))
            }
            if best_explained - explained:
                continue  # la pregunta nombra algo que solo explica el elegido
            if best_page and not self._page_bonus(question_tokens, metric, set(canonical_tokens(metric.get("label")))):
                continue
            seen.add(logical)
            rivals.append(metric)

        elsewhere = [metric for metric in rivals if where(metric) != where(best)]
        if not elsewhere:
            return None
        rivals.sort(key=lambda metric: 0 if metric.get("appearances") else 1)
        score = metric_result.get("score")
        items = [
            {"metric": metric, "score": score, "business_score": score,
             "matched_name": metric_result.get("matched_name") if metric is best else metric.get("label")}
            for metric in [best, *rivals]
        ]
        items = self._collapse_year_variants(items, question)[: self._SUGGESTION_LIMIT]
        if len(items) < 2:
            return None
        # «triages en 2025»: entre los del mismo nombre no responden los que
        # trabajan sobre una tabla que no trae el periodo (TRIAGES del día
        # anterior); si solo queda uno, es la respuesta aunque no tenga visual.
        covering = self._items_covering_period(business_question, items)
        if covering is not None and len(covering) < len(items):
            items = covering
            if len(items) == 1:
                if items[0]["metric"] is best:
                    return None
                return {
                    "status": "ambiguous", "stage": "metric", "reason": None,
                    "question": question, "source_context": source_context,
                    "metric_resolution": {"status": "ambiguous", "candidates": items},
                }
        # «M por X»: entre los del mismo nombre solo responden los que se
        # desglosan por X. Si queda uno, es la respuesta (aunque no sea el
        # que puntuó más); si es el elegido, no hay nada que preguntar.
        tail = self._requested_group_tail(question)
        if tail:
            groupable = [
                item for item in items
                if self._group_field_in(tail, self._metric_dimensions(item["metric"])) is not None
            ]
            if groupable and len(groupable) < len(items):
                self._note(
                    f"«{metric_result.get('matched_name')}» existe en varios tableros; solo "
                    + ", ".join(f"{i['metric'].get('label')} ({i['metric'].get('semantic_model')})" for i in groupable)
                    + f" se desglosa(n) por «{tail}»"
                )
                items = groupable
                if len(items) == 1:
                    if items[0]["metric"] is best:
                        return None
                    return {
                        "status": "ambiguous", "stage": "metric", "reason": None,
                        "question": question, "source_context": source_context,
                        "metric_resolution": {"status": "ambiguous", "candidates": items},
                    }
        # Solo uno de los homónimos es de un modelo con informe; los demás son
        # de modelos SIN ningún informe («Dashboard Gestion»), que el usuario
        # no ve: se responde con el del informe, sin contrapreguntar. Si dos o
        # más modelos tienen informe (aunque esa medida no esté en un visual),
        # la ambigüedad es real y se pregunta.
        documented = [item for item in items if self._model_has_report(item["metric"].get("semantic_model"))]
        if len(documented) == 1:
            chosen = documented[0]
            others = [item for item in items if item is not chosen]
            self._note(
                f"«{metric_result.get('matched_name')}» existe con el mismo nombre en "
                + ", ".join(f"{i['metric'].get('label')} ({i['metric'].get('semantic_model')}, modelo sin informe)"
                            for i in others)
                + f"; solo {chosen['metric'].get('label')} ({chosen['metric'].get('semantic_model')}) está en "
                "un tablero con informe: se usa ese sin contrapreguntar"
            )
            if chosen["metric"] is best:
                return None
            return {
                "status": "ambiguous", "stage": "metric", "reason": None,
                "question": question, "source_context": source_context,
                "metric_resolution": {"status": "ambiguous", "candidates": [chosen]},
            }
        # Solo se pregunta entre fuentes que pueden responder la pregunta TAL
        # COMO ESTÁ y que el usuario ve en un tablero (ver `_homonyms_that_answer`).
        narrowed = self._homonyms_that_answer(question, metric_result, items)
        if narrowed is not None:
            if not narrowed:
                return None
            if len(narrowed) == 1:
                chosen = narrowed[0]
                if chosen["metric"] is best:
                    return None
                return {
                    "status": "ambiguous", "stage": "metric", "reason": None,
                    "question": question, "source_context": source_context,
                    "metric_resolution": {"status": "ambiguous", "candidates": [chosen]},
                }
            items = narrowed
        self._note(
            f"«{metric_result.get('matched_name')}» existe con el mismo nombre en varios tableros/modelos "
            f"({', '.join(sorted({str(i['metric'].get('semantic_model')) for i in items}))}) y la "
            "pregunta no indica cuál: se contrapregunta"
        )
        return {
            "status": "ambiguous", "stage": "metric",
            "reason": "same_name_in_several_boards",
            "question": question, "source_context": source_context,
            "metric_resolution": {"status": "ambiguous", "candidates": items},
        }

    def _homonym_tie_ambiguity(self, question, source_context, metric_result):
        """Empate entre indicadores que son el MISMO concepto con otro nombre
        técnico (TRIAGES, CANTIDAD DE TRIAGES: misma `_name_key`): la
        contrapregunta es la de «existe en varios tableros», con TODOS los
        homónimos (TOTAL_TRIAGES institucional incluido) y su filtro de
        cobertura del periodo, no solo los dos que empataron por puntaje
        («cuántos triages hubo en 2025», AI04). None si el empate no es de
        homónimos o la regla de homónimos no tiene nada que preguntar."""
        if metric_result.get("status") != "ambiguous":
            return None
        candidates = [item for item in metric_result.get("candidates") or [] if (item or {}).get("metric")]
        if len(candidates) < 2:
            return None
        best = max(float(item.get("score") or 0.0) for item in candidates)
        candidates = [item for item in candidates if best - float(item.get("score") or 0.0) < self.ambiguity_margin]
        if len(candidates) < 2:
            return None
        keys = set()
        for item in candidates:
            metric = item["metric"]
            item_keys = {self._name_key(metric.get("label")), self._name_key(item.get("matched_name"))}
            item_keys.discard(())
            keys.add(tuple(sorted(item_keys)))
        flat = {key for group in keys for key in group}
        if len(flat) != 1:
            return None
        # Si la pregunta nombra algo que solo explica uno de los empatados (su
        # tablero: «en urgencias» para CANTIDAD DE TRIAGES, TU04), ya los
        # distingue: no se abre a los homónimos de otros tableros.
        business_question = self._metric_business_question(question, source_context)
        content = {canonical_token(word) for word in self._question_content_words(business_question)}
        explained = [
            frozenset(t for t in content if self._explains(
                t, self._metric_vocabulary_tokens(item["metric"]) | self._board_tokens(item["metric"])))
            for item in candidates
        ]
        if len(set(explained)) != 1:
            return None
        top = max(candidates, key=lambda item: float(item.get("score") or 0.0))
        resolved = {**metric_result, "status": "resolved", "metric": top["metric"],
                    "matched_name": top.get("matched_name") or top["metric"].get("label"),
                    "score": top.get("score")}
        plan = self._same_name_ambiguity(question, source_context, resolved)
        if not plan or plan.get("reason") != "same_name_in_several_boards":
            return None
        offered = {self._logical_key(item["metric"]) for item in plan["metric_resolution"]["candidates"]}
        if not all(self._logical_key(item["metric"]) in offered for item in candidates):
            return None  # la regla de homónimos descartó a uno de los empatados: no se arriesga
        if len(offered) <= len(candidates):
            return None  # no agrega a nadie: la contrapregunta original sirve
        return plan

    def _counted_unit(self, question, metric, source_context):
        """«cuántas CUENTAS hay en proceso de facturación» con
        PROCESO_FACTURACION: lo contado es la unidad del conteo, no un filtro ni
        otro indicador, si (1) ningún indicador aprobado del catálogo lo
        nombra (no es un concepto: «cirugías» sí lo es y sigue pidiendo su
        indicador), (2) el indicador elegido no es un tiempo, promedio ni
        porcentaje y (3) explica las demás palabras con contenido de la
        pregunta. Devuelve el token canónico o None."""
        business_question = self._metric_business_question(question, source_context)
        counted = self._counted_noun(business_question)
        if not counted or counted in self._metric_concept_tokens():
            return None
        vocabulary = self._metric_vocabulary_tokens(metric)
        if self._explains(counted, vocabulary) or self._is_duration_or_ratio(metric):
            return None
        others = [
            canonical_token(word) for word in self._question_content_words(business_question)
            if canonical_token(word) != counted
        ]
        if not others or not all(self._explains(token, vocabulary) for token in others):
            return None
        return counted

    def _unresolved_outweighs_metric(self, question, metric, metric_result, significant, source_context):
        """Regla: no se ofrece «consultar X sin <palabras>» cuando las palabras
        sin interpretar son el núcleo de la pregunta: incluyen el sustantivo
        principal («cuánto PESO hay...» con el indicador Asignadas) o pesan
        claramente más (≥ 2,5 veces, por peso IDF) que lo que coincidió con el
        indicador. Se devuelve not_found con sugerencias o, si nada de lo no
        interpretado existe en el catálogo, fuera de alcance.
        No aplica a un indicador elegido por el diccionario de variables: ya
        se comprobó que el diccionario o su tabla explican cada palabra."""
        if (metric_result or {}).get("dictionary_match") or (metric_result or {}).get("general_indicator"):
            return None
        unit = self._counted_unit(question, metric, source_context)
        significant = [word for word in significant if canonical_token(word) != unit]
        if not significant:
            return None
        leftover = [canonical_token(word) for word in significant]
        head = self._head_token(question, source_context)
        vocabulary = self._metric_vocabulary_tokens(metric)
        business_question = self._metric_business_question(question, source_context)
        evidence = [
            canonical_token(word) for word in self._question_content_words(business_question)
            if canonical_token(word) not in leftover and self._explains(canonical_token(word), vocabulary)
        ]
        left_weight = sum(self._token_weight(token) for token in leftover)
        evidence_weight = sum(self._token_weight(token) for token in evidence)
        head_missing = (
            bool(head) and head in leftover and not self._explains(head, vocabulary)
            and not self._metric_counts(metric, head)
        )
        heavier = len(leftover) >= 2 and left_weight >= 2.5 * max(evidence_weight, 0.01)
        if not (head_missing or heavier):
            return None

        reason_text = (
            f"el sustantivo principal «{head}» no corresponde al indicador"
            if head_missing else
            f"las palabras sin interpretar pesan {left_weight:.2f} frente a {evidence_weight:.2f} de la coincidencia"
        )
        unresolved_text = " ".join(significant)
        kind = self.describe_unresolved(unresolved_text).get("kind")
        out_of_scope = head_missing and kind == "out_of_scope"
        resolved_routing = source_context.get("status") == "resolved"
        strength = source_context.get("routing_strength")
        model_hint = (
            normalize_text(source_context.get("semantic_model"))
            if resolved_routing and strength in ("strong", "weak") else ""
        )
        suggestions = [] if out_of_scope else [
            item for item in self._metric_suggestions(
                business_question, model_hint=model_hint, strong=strength == "strong",
            )
            if self._logical_key(item["metric"]) != self._logical_key(metric)
        ]
        suggestions = self._collapse_year_variants(suggestions, question)
        self._note(
            f"se descartó {metric.get('label')} ({metric.get('semantic_model')}): {reason_text}; "
            + ("ninguna de esas palabras existe en el catálogo: fuera de alcance" if out_of_scope
               else f"no se ofrece consultarlo sin «{unresolved_text}»")
        )
        plan = {
            "status": "not_found", "stage": "metric",
            "reason": "unresolved_words_outweigh_metric",
            "question": question, "source_context": source_context,
            "unresolved_text": unresolved_text,
            "rejected_metric": {
                "metric_id": metric.get("metric_id"), "label": metric.get("label"),
                "matched_name": metric_result.get("matched_name"),
                "why": reason_text,
            },
            "metric_resolution": {
                "status": "not_found", "candidates": [],
                "suggestions": [
                    {key: value for key, value in item.items() if not key.startswith("_")}
                    for item in suggestions
                ],
            },
        }
        if out_of_scope:
            plan["unresolved_kind"] = "out_of_scope"
        return plan

    # ---------------- opciones de una contrapregunta ----------------
    # Palabras que nombran la unidad contada («pacientes», «casos»): «cuántos
    # pacientes observados» y OBSERVADOS cuentan lo mismo aunque el nombre no
    # diga «pacientes». No distinguen un indicador de otro.
    _OPTION_UNIT_WORDS = {
        "paciente", "pacientes", "persona", "personas", "usuario", "usuarios",
        "registro", "registros", "caso", "casos",
    }
    # Palabras genéricas en un NOMBRE de medida, pero que en la pregunta son el
    # tema («pacientes con PENDIENTES»): cuentan para decidir si una opción
    # tiene que ver con la pregunta.
    _OPTION_TOPIC_WORDS = {"pendiente", "pendientes"}
    # «por servicio», «según la EPS»: la agrupación no dice de qué indicador se trata.
    _OPTION_GROUP_RE = re.compile(
        r"(?<![a-z0-9])(?:por|segun|agrupad[oa]s?\s+por|desglosad[oa]s?\s+por)\s+"
        r"(?:(?:el|la|los|las|cada)\s+)?[a-z0-9%]+"
    )

    def _option_words(self, question, source_context):
        """Palabras distintivas de la pregunta con las que se juzga si una
        opción tiene que ver con ella: sin relleno, petición, periodo, palabras
        de agregación («total», «promedio»), la agrupación («por servicio») ni
        el nombre del tablero nombrado («en naos», «tablero de triage»)."""
        text = self._metric_business_question(question, source_context)
        text, board_tokens = self._strip_board_mentions(text, source_context)
        text = self._OPTION_GROUP_RE.sub(" ", text)
        content_free, _ = self._weak_token_sets()
        aggregation = {
            canonical_token(word)
            for word in (self._GENERIC_MEASURE_WORDS | self._TECHNICAL_NAME_WORDS) - self._OPTION_TOPIC_WORDS
        }
        ignored = set(content_free) | aggregation | set(self._period_words(text)) | set(board_tokens)
        # «en el hospital», «en general»: alcance, no un rasgo del indicador.
        ignored |= {canonical_token(word) for word in self._scope_words(text, {})}
        if (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        ):
            for name in (source_context.get("report"), source_context.get("semantic_model"),
                         source_context.get("source_group")):
                ignored.update(token for token in canonical_tokens(name) if len(token) >= 4)
        words = []
        for token in canonical_tokens(text):
            if (
                len(token) < 3 or token.isdigit() or token in ignored
                or _is_request_word(token) or token in words
            ):
                continue
            words.append(token)
        return words

    def _reflexive_verbs(self, question):
        """Verbos en pasiva refleja («se tomaron», «se realizaron»): describen
        la acción contada, no un calificativo que distinga un indicador.
        Salvo los que nombran el dato («se demoran» = TIEMPO, «se pesaron» = PESO)."""
        return {
            canonical_token(match.group(1))
            for match in re.finditer(r"(?<![a-z0-9])se\s+([a-z]{4,})", normalize_text(question))
            if match.group(1) not in BUSINESS_TOKEN_SYNONYMS
        }

    def _option_coverage(self, metric, words):
        """Palabras de `words` que explica el indicador (nombres, tabla o página).
        «%ATENDIDO» explica «atendidas» (el signo no es parte de la palabra) y
        un indicador de cosas pendientes («SIN RESPUESTA», «EN ESPERA»)
        explica «pendientes»."""
        vocabulary = set(self._metric_vocabulary_tokens(metric or {}))
        vocabulary.update(
            canonical_token(token.lstrip("%")) for token in list(vocabulary)
            if token.startswith("%") and len(token) > 3
        )
        if self._PENDING_LABEL_RE.search(
            normalize_text(f"{(metric or {}).get('label') or ''} {(metric or {}).get('measure') or ''}")
        ):
            vocabulary.update({canonical_token("pendiente"), canonical_token("pendientes")})
        return {word for word in words if self._explains(word, vocabulary)}

    _COUNT_QUESTION_RE = re.compile(r"(?<![a-z0-9])(?:cuant[oa]s|cantidad\s+de|numero\s+de)(?![a-z0-9])")
    _DURATION_WORDS = {"tiempo", "tiempos", "minutos", "minuto", "horas", "hora", "dias", "duracion", "estancia",
                       "min"}

    def _is_duration_or_ratio(self, metric):
        """Promedio, porcentaje o suma/promedio de una duración (TIEMPO_PARA_...,
        MIN, DIAS_ESTANCIA): no responde «cuántos»."""
        if self._is_ratio_metric(metric):
            return True
        names = set(normalize_text(f"{metric.get('label') or ''} {metric.get('measure') or ''}").split())
        expression = str(metric.get("base_dax_expression") or metric.get("dax_expression") or "")
        columns = set(normalize_text(" ".join(re.findall(r"\[([^\]]+)\]", expression))).split())
        return bool((names | columns) & self._DURATION_WORDS)

    def _count_question_options(self, question, candidates):
        """«¿Cuántos pacientes hospitalizados...?» pide un conteo: entre las
        opciones, las que cuentan (no un promedio, un porcentaje ni la suma
        de un tiempo: PACIENTES HOSPITALIZADOS = suma de
        TIEMPO_PARA_HOSPITALIZACION en TIEMPOS URGENCIAS). Devuelve [] si la
        pregunta no pide un conteo, si todas cuentan o si ninguna lo hace."""
        normalized = normalize_text(question)
        if not self._COUNT_QUESTION_RE.search(normalized):
            return []
        if set(normalized.split()) & (self._DURATION_WORDS | {"promedio", "porcentaje", "tasa"}):
            return []  # «cuántos minutos...», «cuántos días de estancia»: sí pide un tiempo
        kept = [item for item in candidates if not self._is_duration_or_ratio(item.get("metric") or {})]
        if not kept or len(kept) == len(candidates):
            return []
        self._note(
            "la pregunta pide un conteo: se descartan "
            + ", ".join(str((item.get("metric") or {}).get("label")) for item in candidates if item not in kept)
            + " (promedio, porcentaje o suma de un tiempo)"
        )
        return kept

    def _options_named_by_question(self, question, source_context, candidates):
        """Desempate por la frase que nombra la pregunta. Entre opciones que
        explican todas sus palabras distintivas, se quedan las que la pregunta
        nombra enteras: cada palabra de su nombre (sin conectores, «total» ni
        años) está en la pregunta. «cuántos triages pediátricos hubo en 2025»
        nombra TRIAGES_PEDIATRICOS_2025, no PROMEDIO_TRIAGES_PEDIATRICOS_2025
        ni PROM_TRIAGE_PEDIATRICOS (añaden «promedio», que no se dijo). Si varias
        quedan, solo las de nombre más largo (más específico); si ninguna o
        todas, devuelve [] (lo deciden otras reglas). Dos indicadores del mismo
        nombre en tableros distintos siguen siendo ambiguos."""
        words = self._option_words(question, source_context)
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        core = [word for word in words if word not in units] or words
        if not core:
            return []
        question_tokens = set(canonical_tokens(self._metric_business_question(question, source_context)))

        def said(token):
            return any(_tokens_match_loosely(token, other) for other in question_tokens)

        considered, named = [], []
        for item in candidates:
            metric = item.get("metric") or {}
            if float(item.get("business_score") or 0.0) < self.min_metric_score:
                continue
            considered.append(item)
            if len(self._option_coverage(metric, core)) < len(core):
                continue
            keys = [self._name_key(metric.get("label")), self._name_key(item.get("matched_name"))]
            sizes = [len(key) for key in keys if key and all(said(token) for token in key)]
            if sizes:
                named.append((item, max(sizes)))
        if len(considered) < 2 or not named:
            return []
        top = max(size for _, size in named)
        if top < 2:
            # Un nombre de una sola palabra («PENDIENTES», «CIRUGÍAS») no
            # distingue: «cuántos pendientes hay» sigue siendo ambiguo.
            return []
        kept = [item for item, size in named if size == top]
        if len(kept) == len(considered):
            return []
        return kept

    def options_explain_question(self, question, candidates, source_context=None):
        """¿Las opciones de una contrapregunta explican la pregunta lo bastante
        como para que tenga intención analítica? Al menos una opción debe
        explicar (nombre, tabla o página) la mitad de sus palabras distintivas
        sin contar las de unidad («pacientes»). «¿Qué medicamento le doy a un
        paciente con fiebre?» solo comparte «paciente» y «escríbeme un código
        en Python» solo «código» (una columna): no se contrapregunta por
        indicadores, se responde fuera de alcance. Sin palabras distintivas
        no se juzga (True)."""
        if source_context is None:
            source_context = self._source_context(question)
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        core = [word for word in self._option_words(question, source_context) if word not in units]
        if not core:
            return True
        best = max(
            (len(self._option_coverage(item.get("metric") or {}, core)) for item in candidates or []),
            default=0,
        )
        return 2 * best >= len(core)

    def _prune_unrelated_options(self, question, source_context, metric_result):
        """Depura las opciones de una contrapregunta:
        - fuera las que no comparten ninguna palabra distintiva de la pregunta
          («% Ocupación» para «pacientes con pendientes por servicio»);
        - si algunas explican TODAS las palabras distintivas, solo esas
          («consultas prioritarias»: las de consultas prioritarias, no
          cualquier «Consultas»). Las palabras de unidad («pacientes») no
          obligan. Esas opciones quedan con el mismo puntaje: la pregunta no
          decide entre ellas y la contrapregunta las muestra todas."""
        words = self._option_words(question, source_context)
        if not words:
            return metric_result
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        core = [word for word in words if word not in units] or words
        # «detalle de ocupación por aseguradores»: una opción que se desglosa
        # por la dimensión pedida y cuya página/nombre trata el tema (PACIENTES
        # por ASEGURADORA, tabla de la página DETALLE OCUPACIÓN) no se descarta
        # por no compartir una palabra con «detalle ocupacion».
        tail = self._requested_group_tail(question)
        topic = self._group_topic_words(question, source_context, tail) if tail else []
        result = dict(metric_result)
        for key in ("candidates", "suggestions"):
            items = list(result.get(key) or [])
            if len(items) < 2:
                continue
            covered = [self._option_coverage(item.get("metric"), core) for item in items]
            related = [index for index, words_covered in enumerate(covered) if words_covered]
            if not related:
                continue  # nada comparte palabras: lo decide otra regla
            full = [index for index in related if len(covered[index]) == len(core)]
            keep = full or related
            if topic and len(keep) < len(items):
                protected = [
                    index for index in range(len(items))
                    if index not in keep and self._groupable_on_topic(items[index].get("metric") or {}, tail, topic)
                ]
                if protected:
                    self._note(
                        "se conservan (se desglosan por «" + tail + "» y su página trata «"
                        + " ".join(topic) + "»): "
                        + ", ".join(str((items[i].get("metric") or {}).get("label")) for i in protected)
                    )
                    keep = sorted(set(keep) | set(protected))
            if len(keep) == len(items):
                continue
            dropped = [
                str((items[index].get("metric") or {}).get("label"))
                for index in range(len(items)) if index not in keep
            ]
            kept = [dict(items[index]) for index in keep]
            if full and len(kept) > 1:
                best = max(float(item.get("score") or 0.0) for item in kept)
                for item in kept:
                    item["score"] = best
            result[key] = kept
            self._note(
                "opciones depuradas: "
                + (f"solo las que explican «{' '.join(core)}»" if full
                   else f"solo las que comparten alguna palabra de «{' '.join(core)}»")
                + f"; fuera: {', '.join(dropped[:6])}" + (" ..." if len(dropped) > 6 else "")
            )
        return result

    def _named_board_options(self, question, source_context, metric_result):
        """Tablero nombrado (routing fuerte) y ninguna opción es de él
        («pacientes con pendientes EN NAOS por servicio» ofrecía %PENDIENTE de
        ASIGNACION DE CITAS): se buscan opciones en ese tablero. Devuelve
        ("resolved", item) si una sola explica todas las palabras de la
        pregunta, ("options", items) si hay varias, o (None, []) si el
        tablero no tiene ninguna parecida (se mantienen las de otros tableros)."""
        board_model = normalize_text(source_context.get("semantic_model"))
        business_question = self._metric_business_question(question, source_context)
        found = [
            item for item in self._metric_suggestions(
                business_question, model_hint=board_model, strong=True, ratio=0.0, limit=None,
            )
            if normalize_text(item["metric"].get("semantic_model")) == board_model
        ]
        found = self._collapse_year_variants(found, question)
        words = self._option_words(question, source_context)
        if not found or not words:
            return None, []
        coverage = [len(self._option_coverage(item["metric"], words)) for item in found]
        best = max(coverage)
        if best == 0:
            return None, []
        top = [item for item, count in zip(found, coverage) if count == best]
        clean = [{key: value for key, value in item.items() if not key.startswith("_")} for item in top]
        if len(top) == 1 and best == len(words):
            return "resolved", clean[0]
        return "options", clean[: self._SUGGESTION_LIMIT]

    # ---------------- páginas nombradas ----------------
    # Una página se nombra por su tema («hospitalizaciones parciales de marzo»,
    # «partos de 2025») o con «tablero/página de X». Sus indicadores salen de
    # las visualizaciones del catálogo (tarjetas primero), de las medidas
    # documentadas de esa página en el RAG y, si el catálogo no tiene sus
    # visualizaciones, de los indicadores del modelo cuyo nombre o tabla
    # explica el nombre de la página (tema).
    _PAGE_IGNORED_NAME_WORDS = {
        "cantidades", "cantidad", "tiempos", "tiempo", "cuentas", "detalle", "resumen", "inicio",
        "general", "listado", "consolidado", "seguimiento", "total", "totales", "indicadores",
        "principal", "portada", "home", "menu", "tablero", "informe", "reporte", "pagina",
    }
    _PAGE_PRINCIPAL_RE = re.compile(r"^(?:total|totales|numero|nro|cantidad|conteo|recuento)(?:\s|$)")
    _PAGE_RANKS = {"card": 0, "visual": 1, "documentation": 2, "topic": 3}

    def _page_index(self):
        """{(modelo, página) normalizados: {"page", "semantic_model", "report",
        "visual", "members": {clave lógica: miembro}}}. Un miembro es
        {"metric", "visual_type", "source", "title", "rank"}."""
        cached = self.__dict__.get("_page_index_cache")
        if cached is not None:
            return cached
        index = {}
        metrics = [m for m in self._dedupe_metrics(self.metrics) if m.get("validation_status") == "approved"]
        model_names = {normalize_text(m.get("semantic_model")): m.get("semantic_model") for m in metrics}

        def entry(model, page, report=None):
            key = (normalize_text(model), normalize_text(page))
            if not key[0] or not key[1]:
                return None
            item = index.setdefault(key, {
                "page": str(page).strip(), "semantic_model": model_names.get(key[0], model),
                "report": report, "visual": False, "members": {},
            })
            if report and not item.get("report"):
                item["report"] = report
            return item

        def add(item, metric, source, visual_type=None, title=None):
            if item is None:
                return
            rank = self._PAGE_RANKS["card"] if visual_type == "card" else self._PAGE_RANKS[
                "visual" if source == "visual" else source
            ]
            key = self._logical_key(metric)
            current = item["members"].get(key)
            if current is None or rank < current["rank"]:
                item["members"][key] = {
                    "metric": metric, "visual_type": visual_type, "source": source,
                    "title": title, "rank": rank, "order": len(item["members"]) if current is None else current["order"],
                }

        for metric in metrics:
            for appearance in metric.get("appearances") or []:
                page = appearance.get("page_display_name")
                item = entry(metric.get("semantic_model"), page, appearance.get("report"))
                if item is None:
                    continue
                item["visual"] = True
                add(item, metric, "visual", appearance.get("visual_type"), appearance.get("visual_title"))

        # Medidas documentadas en la página («TRIAGE»: TOTAL_TRIAGES, PROMEDIO_TRIAGE_2025...).
        by_name = {}
        for metric in metrics:
            for name in (metric.get("measure"), metric.get("label")):
                key = (normalize_text(metric.get("semantic_model")), normalize_text(name))
                if key[1] and metric not in by_name.setdefault(key, []):
                    by_name[key].append(metric)
        for model_key, dashboards in self._semantic_documents_index().items():
            for dashboard in dashboards:
                item = entry(model_names.get(model_key, model_key), dashboard.get("name"))
                if item is None:
                    continue
                for measure in dashboard.get("documented_measures") or []:
                    raw = measure.get("name") if isinstance(measure, dict) else measure
                    name = normalize_text(str(raw or "").split("=")[0])
                    for metric in by_name.get((model_key, name), []):
                        add(item, metric, "documentation")

        # Páginas que el enrutador conoce aunque no tengan indicadores.
        known = getattr(self.source_router, "known_pages", None)
        try:
            pages = known() if callable(known) else []
        except Exception:
            pages = []
        for page in pages or []:
            entry(page.get("semantic_model"), page.get("name"), page.get("report"))
        self._page_index_cache = index
        return index

    def _page_name_tokens(self, page):
        """Palabras con contenido del nombre de una página (sin genéricas)."""
        ignored = self._content_ignored_tokens() | {
            canonical_token(word) for word in self._PAGE_IGNORED_NAME_WORDS | GENERIC_PAGE_WORDS
        }
        return [
            token for token in dict.fromkeys(canonical_tokens(page))
            if len(token) >= 3 and not token.isdigit() and token not in ignored
        ]

    def _page_members(self, page):
        """Indicadores de una página {"semantic_model", "page"} en orden:
        tarjetas, otras visualizaciones, medidas documentadas y, si el catálogo
        no tiene sus visualizaciones, los del modelo cuyo nombre o tabla
        explica el nombre de la página."""
        key = (normalize_text(page.get("semantic_model")), normalize_text(page.get("page")))
        cache = self.__dict__.setdefault("_page_members_cache", {})
        if key in cache:
            return cache[key]
        item = self._page_index().get(key)
        members = list((item or {}).get("members", {}).values())
        if item is not None and not item.get("visual"):
            tokens = self._page_name_tokens(item["page"])
            present = {self._logical_key(member["metric"]) for member in members}
            if tokens:
                for metric in self._dedupe_metrics(self.metrics):
                    if (
                        metric.get("validation_status") != "approved"
                        or normalize_text(metric.get("semantic_model")) != key[0]
                        or self._logical_key(metric) in present
                    ):
                        continue
                    vocabulary = self._metric_vocabulary_tokens(metric, with_pages=False)
                    if all(self._explains(token, vocabulary) for token in tokens):
                        present.add(self._logical_key(metric))
                        members.append({
                            "metric": metric, "visual_type": None, "source": "topic", "title": None,
                            "rank": self._PAGE_RANKS["topic"], "order": len(members),
                        })
        members.sort(key=lambda member: (member["rank"], member["order"]))
        cache[key] = members
        return members

    def _page_report(self, page):
        item = self._page_index().get((normalize_text(page.get("semantic_model")), normalize_text(page.get("page"))))
        report = page.get("report") or (item or {}).get("report")
        if report:
            return report
        sources_for_model = getattr(self.source_router, "sources_for_model", None)
        try:
            sources = sources_for_model(page.get("semantic_model")) if callable(sources_for_model) else []
        except Exception:
            sources = []
        return next((source.get("report") for source in sources or [] if source.get("report")),
                    page.get("semantic_model"))

    def _is_report_page(self, page):
        """Página documentada que en realidad es el informe completo
        («TABLERO DE ATENCIONES INSTITUCIONALES» como nombre de página)."""
        name = normalize_text(page.get("page"))
        names = {normalize_text(page.get("semantic_model")), normalize_text(page.get("report"))}
        sources_for_model = getattr(self.source_router, "sources_for_model", None)
        try:
            sources = sources_for_model(page.get("semantic_model")) if callable(sources_for_model) else []
        except Exception:
            sources = []
        for source in sources or []:
            names.update(normalize_text(value) for value in [source.get("report"), *(source.get("aliases") or [])])
        stripped = {re.sub(r"^(?:tablero|informe|reporte)\s+(?:(?:de|del)\s+)?", "", value) for value in names if value}
        return name in names or name in stripped

    def _named_pages(self, source_context):
        """Páginas nombradas con «tablero/página de X» (no un informe):
        la del enrutamiento fuerte o, si el nombre existe en varios modelos,
        todas las páginas con ese nombre."""
        context = source_context or {}
        pages = []
        if context.get("status") == "resolved" and context.get("routing_strength") == "strong":
            if context.get("board_kind") in ("page", "documentation") and context.get("dashboard"):
                pages.append({"semantic_model": context.get("semantic_model"), "page": context.get("dashboard"),
                              "report": context.get("report")})
        elif context.get("board_mentions"):
            for mention in context.get("board_mentions") or []:
                for item in mention.get("contexts") or []:
                    if item.get("kind") in ("page", "documentation") and item.get("dashboard"):
                        pages.append({"semantic_model": item.get("semantic_model"), "page": item.get("dashboard"),
                                      "report": item.get("report")})
        return self._dedupe_pages(pages)

    def _dedupe_pages(self, pages):
        result, seen = [], set()
        for page in pages:
            key = (normalize_text(page.get("semantic_model")), normalize_text(page.get("page")))
            if key in seen or self._is_report_page(page):
                continue
            seen.add(key)
            result.append(page)
        return result

    def _topic_pages(self, question):
        """Páginas nombradas por su tema, sin «tablero de» («partos de 2025»)."""
        mentions_for = getattr(self.source_router, "page_topic_mentions", None)
        if not callable(mentions_for):
            return []
        ignored = (
            STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS) | GENERIC_PAGE_WORDS
            | self._GENERIC_MEASURE_WORDS | self._TECHNICAL_NAME_WORDS | self._PAGE_IGNORED_NAME_WORDS
        )
        try:
            mentions = mentions_for(question, ignored_words=ignored) or []
        except Exception:
            return []
        # «pacientes por especialidad»: la agrupación no nombra la página
        # DETALLE ESPECIALIDADES (sí «atenciones por asegurador» entera).
        tail = self._requested_group_tail(question)
        if tail:
            tail_tokens = set(canonical_tokens(tail))
            mentions = [
                mention for mention in mentions
                if not set(canonical_tokens(mention.get("phrase"))) <= tail_tokens
            ]
        pages = [
            {"semantic_model": item.get("semantic_model"), "page": item.get("dashboard"),
             "report": item.get("report"), "phrase": mention.get("phrase")}
            for mention in mentions for item in mention.get("contexts") or []
            if item.get("dashboard")
        ]
        return self._dedupe_pages(pages)

    def _page_extra_words(self, metric, question):
        """Palabras con contenido del nombre del indicador que la pregunta no
        dice («pediátricos» en PROMEDIO_TRIAGES_PEDIATRICOS_2025)."""
        content_free, generic = self._weak_token_sets()
        said = set(canonical_tokens(question))
        extra = set()
        for token in canonical_tokens(metric.get("label")):
            if len(token) < 4 or token.isdigit() or token in generic or token in content_free:
                continue
            if not self._explains(token, said):
                extra.add(token)
        return len(extra)

    def _page_principal(self, pool):
        """Indicador principal de una página entre las opciones: el único,
        la única tarjeta o la única «Total …/Número de …»."""
        if len(pool) == 1:
            return pool[0]
        cards = [member for member in pool if member.get("visual_type") == "card"]
        if len(cards) == 1:
            return cards[0]
        candidates = cards or pool
        totals = [
            member for member in candidates
            if self._PAGE_PRINCIPAL_RE.match(normalize_text(member.get("title") or member["metric"].get("label")))
        ]
        return totals[0] if len(totals) == 1 else None

    def _page_choices(self, question, source_context, page, offered, topic=False):
        """Opciones de una página para la pregunta: primero los indicadores ya
        ofrecidos que están en la página; si no hay, los de la página que
        comparten palabras con la pregunta (o todos).

        Devuelve {"items", "principal", "direct"}: `principal` es el indicador
        principal elegido entre varios (tarjeta única o única «Total …», sin
        palabras que la pregunta no dice) y `direct` dice si se puede responder
        sin contrapreguntar."""
        members = self._page_members(page)
        if not members:
            return {"items": [], "principal": None, "direct": False}
        by_key = {self._logical_key(member["metric"]): member for member in members}
        pool, seen = [], set()
        for item in offered:
            key = self._logical_key(item.get("metric") or {})
            if key in by_key and key not in seen:
                seen.add(key)
                pool.append(by_key[key])
        pool.sort(key=lambda member: (member["rank"], member["order"]))
        words = self._option_words(question, source_context)
        candidates = pool or members
        if words:
            coverage = [len(self._option_coverage(member["metric"], words)) for member in candidates]
            best = max(coverage)
            if best > 0:
                candidates = [member for member, count in zip(candidates, coverage) if count == best]
            elif not pool:
                # La pregunta solo nombra la página: se ofrecen sus indicadores.
                candidates = members
        # «promedio mensual de partos»: la agregación pedida elige entre los
        # indicadores de la página (PROM_PD y no la tarjeta «Total»).
        before = len(candidates)
        candidates = self._page_aggregation_match(question, candidates)
        by_aggregation = len(candidates) < before
        if not topic:
            # Página nombrada: sin palabras que la pregunta no dice
            # («pediátricos» en PROMEDIO_TRIAGES_PEDIATRICOS_2025).
            extras = [self._page_extra_words(member["metric"], question) for member in candidates]
            fewest = min(extras)
            candidates = [member for member, count in zip(candidates, extras) if count == fewest]
        # Variantes por año (PROMEDIO_TRIAGE_20xx, ATEHP2024/2025) = una opción.
        collapsed = self._collapse_year_variants(
            [{"metric": member["metric"], "_member": member} for member in candidates], question,
        )
        candidates = self._collapse_glued_year_members([item["_member"] for item in collapsed], question)
        if len(candidates) == 1:
            # Una sola opción: se responde si no añade palabras que la pregunta
            # no dice; es «la principal» solo si la pregunta solo nombró la página.
            direct = not self._page_extra_words(candidates[0]["metric"], question)
            principal = candidates[0] if (direct and not pool and not by_aggregation) else None
            return {"items": candidates, "principal": principal, "direct": direct}
        principal = self._page_principal(candidates)
        if principal is not None and not self._page_extra_words(principal["metric"], question):
            return {"items": [principal], "principal": principal, "direct": True}
        # «INTERCONSULTAS SIN RESPUESTA» no es la principal de «cuántas
        # interconsultas» aunque sea la única tarjeta: se contrapregunta.
        return {"items": candidates, "principal": None, "direct": False}

    _PAGE_AGGREGATIONS = {
        "promedio": {"promedio", "prom", "media", "avg"},
        "total": {"total", "totales", "conteo", "recuento", "count"},
        "porcentaje": {"porcentaje", "porcentual", "pct", "proporcion", "tasa"},
    }

    def _page_aggregation_match(self, question, members):
        """Miembros cuyo nombre lleva la agregación que pide la pregunta
        («promedio», «total», «porcentaje»); todos si ninguno o no se pide."""
        said = set(normalize_text(question).split())
        asked = [words for words in self._PAGE_AGGREGATIONS.values() if said & words]
        if len(asked) != 1:
            return members
        matching = [
            member for member in members
            if set(normalize_text(f"{member['metric'].get('label')} {member.get('title') or ''}").split()) & asked[0]
        ]
        return matching or members

    def _collapse_glued_year_members(self, members, question):
        """ATEHP2024 / ATEHP2025 / ATEHP2026 (año pegado al nombre) cuentan
        como una opción: la del año pedido o, si no hay, la más reciente."""
        year = self._detect_year_month(question)[0]
        groups, order = {}, []
        for member in members:
            label = normalize_text(member["metric"].get("label")).replace(" ", "")
            match = re.fullmatch(r"(.*?[a-z])((?:19|20)\d{2})", label)
            key = (normalize_text(member["metric"].get("semantic_model")), match.group(1) if match else label)
            if key not in groups:
                order.append(key)
            groups.setdefault(key, []).append((int(match.group(2)) if match else None, member))
        result = []
        for key in order:
            items = groups[key]
            dated = [(value, member) for value, member in items if value is not None]
            if len(dated) < 2:
                result.extend(member for _, member in items)
                continue
            chosen = next((member for value, member in dated if value == year), None)
            if chosen is None:
                chosen = max(dated, key=lambda pair: pair[0])[1]
            result.extend(member for value, member in items if value is None or member is chosen)
            self._note(
                f"variantes por año agrupadas en {chosen['metric'].get('label')}: "
                + ", ".join(str(member["metric"].get("label")) for _, member in dated if member is not chosen)
            )
        return result

    def _page_label(self, page):
        return f"{page.get('page')} ({self._page_report(page)})"

    def _named_page_refinement(self, question, intent_result, plan):
        """Regla de páginas nombradas sobre un plan explorado:
        - «tablero/página de X» nombra una página (o varias homónimas en otros
          modelos): solo se ofrecen indicadores de esas páginas; si queda uno
          (o uno claramente principal por página y una sola página), se
          responde con él.
        - Ninguna métrica coincide pero la pregunta nombra una página por su
          tema («partos de 2025»): se ofrecen sus indicadores (tarjetas
          primero) o se responde con el principal («tomé el indicador
          principal de la página X»).
        - La página no tiene indicadores en los modelos: el plan lo indica
          (`pages_without_metrics`) para decirlo junto a la respuesta documental.
        Devuelve el plan nuevo o None."""
        status = plan.get("status")
        source_context = plan.get("source_context") or {}
        pages = self._named_pages(source_context)
        topic = False
        if not pages:
            if status != "not_found" or source_context.get("board_mentions"):
                return None
            if plan.get("reason") in ("metric_not_in_named_report", "metric_not_in_named_page"):
                return None
            pages = self._topic_pages(question)
            topic = True
        if not pages:
            return None
        if status == "ready":
            metric_key = self._logical_key(plan.get("metric") or {})
            if topic or any(
                metric_key in {self._logical_key(member["metric"]) for member in self._page_members(page)}
                for page in pages
            ):
                return None
        elif status not in ("ambiguous", "not_found"):
            return None
        if status == "not_found" and plan.get("reason") in ("metric_not_in_named_report", "metric_not_in_named_page"):
            return None

        resolution = plan.get("metric_resolution") or {}
        offered = [*(resolution.get("candidates") or []), *(resolution.get("suggestions") or [])]
        if status == "ready":
            offered = [{"metric": plan.get("metric")}, *offered]
        if topic and self._topic_offered_elsewhere(pages, offered):
            return None
        groups = []
        for page in pages:
            choice = self._page_choices(question, source_context, page, offered, topic=topic)
            if choice["items"]:
                groups.append((page, choice["items"], choice["principal"], choice["direct"]))
        names = ", ".join(self._page_label(page) for page in pages)
        if not groups:
            if all(not self._page_members(page) for page in pages):
                self._note(
                    f"la pregunta nombra la página {names}, pero esa página no tiene indicadores "
                    "en los modelos disponibles"
                )
                return {**plan, "pages_without_metrics": [self._page_label(page) for page in pages]}
            return None
        scores = [float(item.get("score") or 0.0) for item in offered if item.get("score") is not None]
        best = max(scores) if scores else 1.0
        items, seen = [], set()
        for page, members, _, _ in groups:
            for member in members:
                key = self._logical_key(member["metric"])
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "metric": member["metric"], "score": best, "business_score": best,
                    "matched_name": member.get("title") or member["metric"].get("label"),
                    "page": page.get("page"),
                })
        how = "por su tema" if topic else "con «tablero/página de»"
        # Una página nombrada (o un servicio que se llama como una página:
        # «urgencias») no arrastra la respuesta a una tabla que no trae el
        # periodo pedido («este mes» frente al corte del día anterior del
        # Briefing, TU04): esas opciones se quitan y, si no queda ninguna, la
        # página no decide (sigue el plan general).
        period, start, end = self._requested_period_bounds(question)
        if period is not None:
            missing = [self._metric_misses_period(item["metric"], start, end) for item in items]
            if any(missing):
                dropped = ", ".join(_unique_strings(
                    f"{item['metric'].get('label')} ({table})" for item, table in zip(items, missing) if table
                ))
                lost = [item for item, table in zip(items, missing) if table]
                items = [item for item, table in zip(items, missing) if not table]
                # Lo que queda de la página explica menos de lo que se pide
                # («triages»: solo quedan consultas): la página tampoco decide.
                words = self._option_words(question, source_context)
                best_lost = max((len(self._option_coverage(i["metric"], words)) for i in lost), default=0)
                best_kept = max((len(self._option_coverage(i["metric"], words)) for i in items), default=0)
                if best_lost > best_kept:
                    items = []
                if not items:
                    self._note(
                        f"la pregunta nombra la página {names}, pero sus indicadores no traen «{period.get('label')}» "
                        f"según su documentación ({dropped}): la página no decide el indicador"
                    )
                    return None
                self._note(
                    f"«{period.get('label')}»: de la página {names} se descartan los indicadores cuya tabla no "
                    f"trae ese periodo: {dropped}"
                )
                kept_keys = {self._logical_key(item["metric"]) for item in items}
                groups = [
                    group for group in groups
                    if any(self._logical_key(member["metric"]) in kept_keys for member in group[1])
                ]
        # Páginas homónimas de varios tableros: cada una ya dejó sus opciones
        # que más palabras de la pregunta explican; entre páginas rige lo mismo
        # («interconsultas PENDIENTES»: solo SIN RESPUESTA lo explica, aunque
        # la otra página INTERCONSULTAS tenga más indicadores).
        if len(groups) > 1 and len(items) > 1:
            words = self._option_words(question, source_context)
            coverage = [len(self._option_coverage(item["metric"], words)) for item in items]
            top = max(coverage) if coverage else 0
            if top > 0 and min(coverage) < top:
                dropped = [item for item, count in zip(items, coverage) if count < top]
                items = [item for item, count in zip(items, coverage) if count == top]
                self._note(
                    "entre las páginas homónimas se descartan "
                    + ", ".join(str(item["metric"].get("label")) for item in dropped)
                    + ": explican menos palabras de la pregunta"
                )
                if len(items) == 1:
                    chosen = items[0]
                    return self._forced_plan(
                        question, intent_result, {key: value for key, value in chosen.items() if key != "page"},
                        f"la pregunta nombra la página {chosen.get('page')} {how}; es el único indicador "
                        "de esas páginas que explica todo lo que la pregunta pide",
                        consumed_tokens=self._page_choice_consumed(question, source_context, chosen),
                    )
        narrowed = self._narrow_page_options(question, items)
        if len(narrowed) < len(items) and len({self._logical_key(i["metric"]) for i in narrowed}) == 1:
            chosen = narrowed[0]
            return self._forced_plan(
                question, intent_result, {key: value for key, value in chosen.items() if key != "page"},
                f"la pregunta nombra la página {chosen.get('page')} {how}; es su único indicador que "
                "responde la forma pedida (conteo / desglose)",
                consumed_tokens=self._page_choice_consumed(question, source_context, chosen),
            )
        items = narrowed[: self._SUGGESTION_LIMIT]
        if len(items) == 1 and len(groups) == 1 and groups[0][3]:
            page, _, principal, _ = groups[0]
            label = items[0]["metric"].get("label")
            visible = (
                f"Tomé el indicador principal de la página {page.get('page')} ({self._page_report(page)}): {label}."
                if principal is not None
                else f"Usé el indicador de la página {page.get('page')} ({self._page_report(page)}): {label}."
            )
            # El nombre de la página y las palabras de agregación («promedio
            # mensual») ya explicaron la elección: no son filtros pendientes.
            generic = {
                canonical_token(word) for word in self._GENERIC_MEASURE_WORDS | self._TECHNICAL_NAME_WORDS
                | FILTER_NEUTRAL_WORDS
            }
            consumed = self._page_choice_consumed(question, source_context, items[0], page) | {
                token for token in canonical_tokens(question) if token in generic
            }
            forced = self._forced_plan(
                question, intent_result, {key: value for key, value in items[0].items() if key != "page"},
                f"la pregunta nombra la página {self._page_label(page)} {how}; "
                + ("es su indicador principal" if principal is not None else "es su único indicador que coincide"),
                consumed_tokens=consumed,
            )
            if isinstance(forced, dict) and forced.get("status") == "ready":
                forced["notes"] = [visible, *(forced.get("notes") or [])]
                forced["named_page"] = page.get("page")
            return forced
        models = {normalize_text(page.get("semantic_model")) for page, *_ in groups}
        self._note(
            f"la pregunta nombra la página {names} {how}: se ofrecen solo sus indicadores ("
            + ", ".join(str(item["metric"].get("label")) for item in items) + ")"
        )
        # «CIRUGIAS», «Cirugías» y «CIRUGÍAS» son el mismo nombre.
        names_by_key = {}
        for page, *_ in groups:
            names_by_key.setdefault(normalize_text(page.get("page")), str(page.get("page")).strip())
        page_names = list(names_by_key.values())
        return {
            **plan, "status": "ambiguous", "stage": "metric", "reason": "options_from_named_page",
            "named_page": page_names[0] if len(page_names) == 1 else ", ".join(page_names),
            "named_page_report": self._page_report(groups[0][0]) if len(models) == 1 else None,
            "named_page_models": len(models),
            "metric_resolution": {
                "status": "ambiguous",
                "candidates": [{key: value for key, value in item.items() if key != "page"} for item in items],
            },
        }

    def _page_choice_consumed(self, question, source_context, item, page=None):
        """Palabras que ya explicó elegir este indicador de la página: el nombre
        de la página y las palabras de la pregunta que su nombre explica
        («atendidas» con %ATENDIDO, «pendientes» con SIN RESPUESTA)."""
        name = (page or {}).get("page") or item.get("page")
        words = self._option_words(question, source_context)
        return set(canonical_tokens(name)) | set(self._option_coverage(item.get("metric") or {}, words))

    def _narrow_page_options(self, question, items):
        """Opciones de una página nombrada que responden la FORMA de la
        pregunta: «cantidad de X» descarta porcentajes, promedios y sumas de
        tiempo; «X por especialidad» descarta las que no se desglosan por la
        especialidad. Nunca deja la lista vacía."""
        kept = self._count_question_options(question, items) or list(items)
        # Sin pedir un tiempo, promedio ni porcentaje, un indicador de ese tipo
        # no responde «interconsultas pendientes por especialidad» (TIEMPO EN
        # ESPERA también es «pendiente», pero mide horas).
        said = set(normalize_text(question).split())
        if len(kept) > 1 and not said & (self._DURATION_WORDS | {
            "promedio", "porcentaje", "tasa", "proporcion", "media", "cuanto", "demora", "demoran",
        }):
            plain = [item for item in kept if not self._is_duration_or_ratio(item.get("metric") or {})]
            if plain and len(plain) < len(kept):
                self._note(
                    "opciones de la página depuradas: "
                    + ", ".join(str(i["metric"].get("label")) for i in kept if i not in plain)
                    + " (tiempo, promedio o porcentaje que la pregunta no pide)"
                )
                kept = plain
        tail = self._requested_group_tail(question)
        if tail and len(kept) > 1:
            groupable = [
                item for item in kept
                if self._group_field_in(tail, self._metric_dimensions(item.get("metric") or {})) is not None
            ]
            if groupable and len(groupable) < len(kept):
                self._note(
                    f"opciones de la página depuradas: "
                    + ", ".join(str(i["metric"].get("label")) for i in kept if i not in groupable)
                    + f" no se desglosa(n) por «{tail}»"
                )
                kept = groupable
        return kept

    def _topic_offered_elsewhere(self, pages, offered):
        """¿Alguna opción ya ofrecida nombra el tema de la página pero está
        fuera de ella? («cirugías»: TOTAL CIRUGÍAS de otro informe) Entonces
        el tema no identifica la página y se mantiene la contrapregunta."""
        member_keys = {
            self._logical_key(member["metric"]) for page in pages for member in self._page_members(page)
        }
        topics = [tokens for tokens in (self._page_name_tokens(page.get("page")) for page in pages) if tokens]
        for item in offered:
            metric = item.get("metric") or {}
            if not metric or self._logical_key(metric) in member_keys:
                continue
            vocabulary = self._metric_vocabulary_tokens(metric)
            if any(all(self._explains(token, vocabulary) for token in tokens) for tokens in topics):
                return True
        return False

    def _routed_page(self, source_context):
        """Página fijada por el enrutamiento fuerte («tablero de triage» ->
        TRIAGE de TABLERO DE ATENCIONES), o None."""
        context = source_context or {}
        if not (
            context.get("status") == "resolved" and context.get("routing_strength") == "strong"
            and context.get("board_kind") in ("page", "documentation") and context.get("dashboard")
        ):
            return None
        page = {"semantic_model": context.get("semantic_model"), "page": context.get("dashboard"),
                "report": context.get("report")}
        return None if self._is_report_page(page) else page

    def _page_named_in_report(self, question, source_context):
        """Con el informe nombrado («en el tablero eps»), la página de ese
        modelo cuyo nombre completo (dos o más palabras con contenido) va
        seguido en la pregunta: «cuántos TRIAGES ATENDIDOS hay en el tablero
        eps» -> página TRIAGES ATENDIDOS. La de más palabras; None si no hay
        o si empatan."""
        context = source_context or {}
        if not (
            context.get("status") == "resolved" and context.get("routing_strength") == "strong"
            and context.get("semantic_model")
        ):
            return None
        model = normalize_text(context.get("semantic_model"))
        connectors = {"de", "del", "la", "el", "los", "las", "y", "a", "al", "en", "por"}
        question_seq = [token for token in canonical_tokens(question) if token not in connectors]
        ignored = {canonical_token(word) for word in self._PAGE_IGNORED_NAME_WORDS} | set(GENERIC_PAGE_WORDS)
        best, best_size, tie = None, 0, False
        for (page_model, _), item in self._page_index().items():
            if page_model != model or not item.get("visual"):
                continue
            page_seq = [token for token in canonical_tokens(item["page"]) if token not in connectors]
            content = [token for token in page_seq if token not in ignored and not token.isdigit()]
            if len(content) < 2 or not any(
                question_seq[start:start + len(page_seq)] == page_seq
                for start in range(len(question_seq) - len(page_seq) + 1)
            ):
                continue
            page = {"semantic_model": item["semantic_model"], "page": item["page"], "report": item.get("report")}
            if self._is_report_page(page):
                continue
            if len(content) > best_size:
                best, best_size, tie = page, len(content), False
            elif len(content) == best_size:
                tie = True
        return None if tie else best

    def _named_page_rejection(self, question, source_context, metric_result, page):
        """Página nombrada y el indicador elegido no está en ella: no se
        responde con el de otra página. Se ofrecen los de la página que
        comparten palabras con la pregunta; si no hay, el encontrado fuera."""
        metric = metric_result.get("metric") or (
            (metric_result.get("candidates") or [{}])[0].get("metric") or {}
        )
        words = self._option_words(question, source_context)
        members = self._page_members(page)
        related = [
            member for member in members
            if words and self._option_coverage(member["metric"], words)
        ]
        collapsed = self._collapse_year_variants(
            [{"metric": member["metric"], "score": metric_result.get("score"),
              "business_score": metric_result.get("score"),
              "matched_name": member.get("title") or member["metric"].get("label")} for member in related],
            question,
        )[: self._SUGGESTION_LIMIT]
        elsewhere = None
        if not collapsed and metric.get("metric_id"):
            elsewhere = {"metric": metric, "score": metric_result.get("score"),
                         "business_score": metric_result.get("score"),
                         "matched_name": metric_result.get("matched_name") or metric.get("label")}
        label = self._page_label(page)
        self._note(
            f"la pregunta nombra la página {label}, pero el indicador elegido ({metric.get('label')}) "
            "no aparece en ella: no se responde con el de otra página; "
            + (f"se ofrecen {len(collapsed)} indicadores de esa página" if collapsed
               else "esa página no tiene indicadores parecidos")
        )
        return {
            "status": "not_found", "stage": "metric",
            "reason": "metric_not_in_named_page",
            "named_page": page.get("page"), "named_page_report": self._page_report(page),
            "named_report": f"{self._page_report(page)} (página {page.get('page')})",
            "found_elsewhere": {
                "metric_id": metric.get("metric_id"), "label": metric.get("label"),
                "semantic_model": metric.get("semantic_model"),
                "pages": self._metric_pages(metric),
            } if metric.get("metric_id") else None,
            "question": question, "source_context": source_context,
            "metric_resolution": {
                "status": "not_found", "candidates": [],
                "suggestions": collapsed or ([elsewhere] if elsewhere else []),
            },
        }

    def named_page_without_metrics(self, question):
        """Páginas («ABORTOS (TABLERO DE ATENCIONES INSTITUCIONALES)») que la
        pregunta nombra al pedir un dato y que no tienen indicadores en los
        modelos disponibles; [] si no aplica. Sirve para decirlo junto a la
        respuesta documental."""
        try:
            normalized = normalize_text(canonical_phrases(question)[0])
            if not normalized or self._is_descriptive(normalized):
                return []
            asks_value = (
                any(re.search(r"(?<![a-z0-9])" + term + r"(?![a-z0-9])", normalized) for term in NUMERIC_TERM_PATTERNS)
                or any(re.search(r"(?<![a-z0-9])(?:" + verb + r")(?![a-z0-9])", normalized)
                       for verb in QUERY_VERB_PATTERNS)
                or self._has_period(normalized)
                or bool(re.search(r"(?<![a-z0-9])(?:por|segun)\s+[a-z]", normalized))
            )
            if not asks_value:
                return []
            source_context = self._source_context(question)
            pages = self._named_pages(source_context) or (
                [] if source_context.get("board_mentions") else self._topic_pages(question)
            )
            if not pages or any(self._page_members(page) for page in pages):
                return []
            return [self._page_label(page) for page in pages]
        except Exception:
            return []

    def _similar_name_ambiguity(self, question, source_context, plan):
        """Regla: el indicador elegido tiene un nombre CASI igual a otro
        indicador distinto (otra tabla o expresión, a menudo de otro tablero)
        y la pregunta no los distingue: IMAGENES TOMADAS (BRIEFING) e
        IMAGENES (ATENCIONES) para «cuántas imágenes se tomaron»; PACIENTES
        OBSERVADOS POR MES y OBSERVADOS_2025 para «cuántos pacientes
        observados hay». Ni la unidad («pacientes») ni el verbo en pasiva
        refleja («se tomaron») distinguen; el rival no puede añadir palabras
        que la pregunta no dice (PROM_IMAGENES, «Total de triages no
        atendidos» no compiten). Dentro del mismo modelo solo compite una
        medida auxiliar sobre la tabla del tema (ver abajo). La MISMA medida
        (mismo modelo, tabla y expresión) en varias páginas no es ambigua: se
        responde una vez."""
        best = plan.get("metric") or {}
        if not best.get("metric_id"):
            return None
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        if strong and normalize_text(source_context.get("semantic_model")) == normalize_text(best.get("semantic_model")):
            return None
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        neutral = units | self._reflexive_verbs(question)
        words = self._option_words(question, source_context)
        core = [word for word in words if word not in neutral]
        if not core or len(self._option_coverage(best, core)) < len(core):
            return None
        matched_name = (plan.get("metric_match") or {}).get("matched_name")
        best_keys = {self._name_key(best.get("label")), self._name_key(matched_name)}
        best_keys.discard(())
        best_tokens = {token for key in best_keys for token in key}
        if not best_tokens:
            return None
        question_tokens = set(canonical_tokens(self._metric_business_question(question, source_context)))

        def said(token):
            return any(_tokens_match_loosely(token, other) for other in question_tokens)

        def table_explains(metric, word):
            return self._explains(word, set(canonical_tokens(metric.get("table"))))

        best_model = normalize_text(best.get("semantic_model"))
        best_table_explains = any(table_explains(best, word) for word in core)
        groups_by = self._rival_group_check(question, best)
        rivals, seen = [], {self._logical_key(best)}
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            logical = self._logical_key(metric)
            if logical in seen:
                continue
            key = self._name_key(metric.get("label"))
            if not key or key in best_keys or not set(key) & best_tokens:
                continue
            if not all(said(token) for token in key):
                continue  # el rival nombra algo que la pregunta no dice
            # Polaridad opuesta: «triages no atendidos» no es «Total de triages
            # atendidos» (solo cuenta la negación: «se tomaron» no distingue).
            polar = (
                set(normalize_text(best.get("label")).split()) ^ set(normalize_text(metric.get("label")).split())
            ) & _POLARITY_WORDS
            if polar and value_contradiction(
                self._metric_business_question(question, source_context),
                metric.get("label"), [best.get("label"), metric.get("label")],
            ):
                continue
            if len(self._option_coverage(metric, core)) < len(core):
                continue
            if not groups_by(metric):
                continue
            # En el MISMO modelo, las tarjetas de nombre parecido suelen ser
            # variantes del propio tablero (CITAS ASIGNADAS / ASIGNADAS): no se
            # pregunta. Solo compite una medida auxiliar (sin visual) sobre la
            # tabla del tema (OBSERVADOS_2025 sobre OBSERVADOS) cuando la
            # elegida se calcula sobre otra tabla que no lo nombra.
            if normalize_text(metric.get("semantic_model")) == best_model and (
                metric.get("appearances") or best_table_explains
                or not all(table_explains(metric, word) for word in core)
            ):
                continue
            seen.add(logical)
            rivals.append(metric)
        if not rivals:
            return None
        rivals.sort(key=lambda metric: 0 if metric.get("appearances") else 1)
        score = (plan.get("metric_match") or {}).get("score")
        items = [
            {"metric": metric, "score": score, "business_score": score,
             "matched_name": matched_name if metric is best else metric.get("label")}
            for metric in [best, *rivals]
        ]
        items = self._collapse_year_variants(items, question)[: self._SUGGESTION_LIMIT]
        if len(items) < 2:
            return None
        # Igual que con los homónimos: solo fuentes que responden y que el
        # usuario ve en un tablero.
        with_report = [item for item in items if self._model_has_report(item["metric"].get("semantic_model"))]
        if with_report and len(with_report) < len(items):
            self._note(
                "de modelos sin ningún informe (el usuario no los ve): "
                + ", ".join(f"{i['metric'].get('label')} ({i['metric'].get('semantic_model')})"
                            for i in items if i not in with_report)
                + "; no se ofrecen"
            )
            if len(with_report) == 1:
                if with_report[0]["metric"] is best:
                    return None
                return self._forced_plan(
                    question, None, with_report[0],
                    "es la única de las fuentes de nombre casi igual de un tablero con informe",
                )
            items = with_report
        narrowed = self._homonyms_that_answer(
            question, {"matched_name": best.get("label")}, items, current_state=False,
        )
        if narrowed is not None:
            if len(narrowed) <= 1:
                if not narrowed or narrowed[0]["metric"] is best:
                    return None
                return self._forced_plan(
                    question, None, narrowed[0],
                    "es la única de las fuentes de nombre casi igual que responde la pregunta "
                    "y que muestra un tablero",
                )
            items = narrowed
        self._note(
            f"«{best.get('label')}» tiene un nombre casi igual a otros indicadores distintos ("
            + ", ".join(f"{i['metric'].get('label')} de {i['metric'].get('semantic_model')}" for i in items[1:])
            + ") y la pregunta no indica cuál: se contrapregunta"
        )
        return {
            "status": "ambiguous", "stage": "metric",
            "reason": "similar_name_in_several_boards",
            "question": question, "source_context": source_context,
            "metric_resolution": {"status": "ambiguous", "candidates": items},
        }

    def _forced_plan(self, question, intent_result, item, why, consumed_tokens=(),
                     visible_note=None, group_sibling=False):
        """Plan con un indicador ya decidido (única opción razonable).
        `consumed_tokens`: palabras de la pregunta que ya explicó la elección.
        `visible_note`: nota que se muestra con la respuesta. `group_sibling`:
        indicador elegido porque el pedido no se podía desglosar (no se repite)."""
        metric = item["metric"]
        interpretation = f"{metric.get('label')}: {why}"
        self._note(interpretation)
        forced = {
            "status": "resolved", "metric": metric,
            "matched_name": item.get("matched_name") or metric.get("label"),
            "score": item.get("score"),
            "candidates": [{key: value for key, value in item.items() if not key.startswith("_")}],
            "interpretation": interpretation,
            "final": True,
            "consumed_tokens": set(consumed_tokens or ()),
            "visible_note": visible_note,
            "group_sibling": bool(group_sibling),
        }
        return self._build_plan(question, intent_result, forced_resolution=forced)

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

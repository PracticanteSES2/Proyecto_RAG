"""Etapa «contrapreguntas»: depuración final de opciones y palabras para describir lo no resuelto.

_refine_options (r3/r4/r6: opciones que se reducen a una o se responden directo),
metric_words y describe_unresolved (usados por query_engine al redactar la contrapregunta). Mixin
de QueryPlanBuilder, métodos movidos sin cambios.
"""
from src.semantic.resolucion.texto import (
    _is_request_word,
    _token_similarity,
    canonical_token,
    canonical_tokens,
    DIMENSION_SYNONYMS,
    FILTER_NEUTRAL_WORDS,
    GENERIC_QUERY_WORDS,
    MONTHS,
    normalize_text,
    STOPWORDS,
)


class ContrapreguntaMixin:


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

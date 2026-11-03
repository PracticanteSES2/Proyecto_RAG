"""Etapa «elegir tablero y modelo»: contexto de la fuente y tablero nombrado en la pregunta.

_source_context (enrutador de fuentes), _refine_board_context, quitar las menciones del tablero de
la pregunta (_strip_board_mentions), «tablero nombrado sin ese indicador» (_named_board_rejection,
fix-indicador-ruta / r3 EP02). Mixin de QueryPlanBuilder, métodos movidos sin cambios.
"""
import re

from src.semantic.resolucion.texto import (
    canonical_token,
    canonical_tokens,
    DIMENSION_SYNONYMS,
    GENERIC_QUERY_WORDS,
    normalize_text,
    STOPWORDS,
)


class TableroMixin:


    def _source_context(self, question, dashboard=None):
        try:
            return self._refine_board_context(
                self.source_router.resolve(question=question, dashboard=dashboard)
            )
        except Exception as error:
            return {
                "status": "error",
                "routing_strength": "none",
                "error": f"{type(error).__name__}: {error}",
            }

    # ---------------- tablero / página nombrado ----------------
    def _models_with_metrics(self):
        if getattr(self, "_metric_models", None) is None:
            self._metric_models = {
                normalize_text(metric.get("semantic_model")) for metric in self.metrics
                if metric.get("validation_status") == "approved" and metric.get("semantic_model")
            }
        return self._metric_models

    def _refine_board_context(self, context):
        """Nombre de tablero presente en varios modelos («tablero de
        cirugías»): si solo uno tiene indicadores, se fija ese (routing fuerte)."""
        if not isinstance(context, dict):
            return context
        models = context.get("board_mention_models") or []
        if len(models) < 2:
            return context
        if context.get("status") == "resolved" and context.get("routing_strength") == "strong":
            return context
        mentions = context.get("board_mentions") or []
        with_metrics = [m for m in models if normalize_text(m) in self._models_with_metrics()]
        why = "el único con indicadores"
        if len(with_metrics) > 1:
            # Desempate por la forma escrita: «tablero de triage» es TRIAGE
            # antes que TRIAGES (solo coincide en singular/plural).
            exact_models = {
                normalize_text(item.get("semantic_model"))
                for mention in mentions for item in mention.get("contexts") or []
                if item.get("exact")
            }
            exact = [m for m in with_metrics if normalize_text(m) in exact_models]
            if len(exact) == 1:
                with_metrics = exact
                why = "el único con indicadores cuyo nombre coincide tal como se escribió"
        board_context = getattr(self.source_router, "board_context", None)
        if len(with_metrics) != 1 or not callable(board_context):
            return context
        target = normalize_text(with_metrics[0])
        entry = next(
            (item for mention in mentions for item in mention.get("contexts") or []
             if normalize_text(item.get("semantic_model")) == target),
            None,
        )
        if entry is None:
            return context
        refined = board_context(entry, mentions=mentions, candidates=context.get("candidates"))
        refined["board_note"] = (
            f"«{entry.get('name')}» existe en {len(models)} modelos; se usa "
            f"{with_metrics[0]}: {why}"
        )
        return refined

    def _strip_board_mentions(self, text, source_context):
        """Quita «tablero/página de X» del texto donde se buscan agrupaciones y
        filtros; devuelve (texto, palabras canónicas del nombre). Esas
        palabras nombran el tablero: no son valores de filtro («tablero de
        triage» no es CLASIFICACIÓN = TRIAGE III)."""
        mentions = (source_context or {}).get("board_mentions") or []
        text = normalize_text(text)
        tokens = set()
        explicit = re.search(r"(?<![a-z0-9])(?:tablero|informe|reporte|dashboard|pagina)(?![a-z0-9])", text)
        dimension_words = {
            canonical_token(word) for synonyms in DIMENSION_SYNONYMS.values() for word in synonyms
        }
        for mention in mentions:
            phrase = normalize_text(mention.get("phrase"))
            # «por eps» agrupa por aseguradora: no nombra el TABLERO EPS. Una
            # mención que solo es una palabra de dimensión cuenta como tablero
            # solo si la pregunta dice «tablero/informe».
            if phrase and not explicit and (
                re.search(r"(?<![a-z0-9])(?:por|segun)\s+(?:(?:el|la|los|las)\s+)?" + re.escape(phrase)
                          + r"(?![a-z0-9])", text)
                or all(token in dimension_words for token in canonical_tokens(phrase))
            ):
                continue
            if phrase:
                pattern = r"(?<![a-z0-9])(?:(?:en|de|del|desde|para)\s+(?:(?:el|la|los|las)\s+)?)?" \
                          + re.escape(phrase) + r"(?![a-z0-9])"
                text = re.sub(pattern, " ", text)
            tokens.update(canonical_tokens(mention.get("name")))
        return re.sub(r"\s+", " ", text).strip(), tokens

    def _board_name_phrases(self, source_context, metric=None):
        """Nombres normalizados con los que la pregunta puede nombrar el
        tablero/informe del contexto (o del indicador): informe, modelo,
        grupo, alias del registro y tableros nombrados, también sin la
        palabra «tablero/informe» delante («TABLERO LAVANDERIA» -> «lavanderia»).
        No incluye páginas: «servicio de urgencias» sigue siendo un valor
        aunque exista una página URGENCIAS."""
        context = source_context or {}
        names = [
            context.get("report"), context.get("semantic_model"),
            str(context.get("source_group") or "").replace("_", " ").replace("-", " "),
        ]
        for mention in context.get("board_mentions") or []:
            names.extend([mention.get("phrase"), mention.get("name")])
        models = {normalize_text(context.get("semantic_model"))}
        if metric:
            names.extend(self._metric_reports(metric))
            names.append(metric.get("semantic_model"))
            models.add(normalize_text(metric.get("semantic_model")))
        sources_for_model = getattr(self.source_router, "sources_for_model", None)
        if callable(sources_for_model):
            for model in models:
                if not model:
                    continue
                try:
                    sources = sources_for_model(model) or []
                except Exception:
                    sources = []
                for source in sources:
                    names.extend([source.get("report"), *(source.get("aliases") or [])])
                    names.append(str(source.get("source_group") or "").replace("_", " ").replace("-", " "))
        phrases = set()
        for name in names:
            norm = normalize_text(name)
            if not norm:
                continue
            phrases.add(norm)
            short = re.sub(r"^(?:tablero|informe|reporte)\s+(?:(?:de|del|de la|de los)\s+)?", "", norm).strip()
            if short and short not in GENERIC_QUERY_WORDS and len(short) >= 3:
                phrases.add(short)
        return phrases

    def _names_board(self, text, source_context, metric=None, loose=False):
        """¿`text` («lavanderia», «el tablero de lavanderia») es solo el
        nombre del tablero/informe del contexto?

        `loose`: también vale la palabra distintiva del nombre («el briefing»
        por BRIEFING HOSPITALARIO): todas sus palabras están en el nombre de
        ese tablero y ninguna es un concepto de los indicadores ni una palabra
        genérica (así «urgencias» sigue siendo un valor posible aunque el
        tablero se llame TIEMPOS URGENCIAS). Solo se usa cuando el texto ya
        no es un valor de la columna."""
        norm = normalize_text(text)
        norm = re.sub(r"^(?:(?:en|de|del)\s+)?(?:(?:el|la|los|las)\s+)?", "", norm)
        norm = re.sub(r"^(?:tablero|informe|reporte)\s+(?:(?:de|del)\s+)?", "", norm).strip()
        if not norm:
            return False
        phrases = self._board_name_phrases(source_context, metric)
        if norm in phrases:
            return True
        if not loose:
            return False
        tokens = [token for token in canonical_tokens(norm) if token]
        generic = {canonical_token(word) for word in GENERIC_QUERY_WORDS | STOPWORDS}
        concepts = self._metric_concept_tokens()
        if not tokens or any(
            len(token) < 4 or token in generic or token in concepts or token.isdigit()
            for token in tokens
        ):
            return False
        return any(
            set(tokens) <= set(canonical_tokens(phrase)) for phrase in phrases
        )

    def _board_named_explicitly(self, question, source_context):
        """¿La pregunta nombra de verdad el tablero al que se enrutó? Sí si dice
        «tablero/informe/reporte» o una palabra distintiva de su nombre (≥ 4
        letras y que no sea a la vez un nombre de dimensión: «eps» en «nueva
        eps» es una aseguradora, no el TABLERO EPS)."""
        normalized = normalize_text(question)
        if re.search(r"(?<![a-z0-9])(?:tablero|informe|reporte|dashboard)(?![a-z0-9])", normalized):
            return True
        dimension_words = {
            canonical_token(word) for synonyms in DIMENSION_SYNONYMS.values() for word in synonyms
        }
        generic = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS | {"tablero", "informe"}}
        question_tokens = set(canonical_tokens(normalized))
        for name in (source_context.get("report"), source_context.get("semantic_model"),
                     source_context.get("source_group")):
            for token in canonical_tokens(name):
                if (
                    len(token) >= 4 and token not in generic and token not in dimension_words
                    and token in question_tokens
                ):
                    return True
        return False

    def _named_board_rejection(self, question, source_context, metric_result):
        """Regla: la pregunta nombra un tablero (routing fuerte) y el mejor
        indicador es de otro modelo. No se responde con él: se dice que en ese
        tablero no se encontró y se ofrecen indicadores de ese tablero; si no
        hay, se ofrece el encontrado en el otro tablero como opción."""
        metric = metric_result.get("metric") or {}
        board = source_context.get("report") or source_context.get("semantic_model")
        board_model = normalize_text(source_context.get("semantic_model"))
        business_question = self._metric_business_question(question, source_context)
        options = [
            item for item in self._metric_suggestions(
                business_question, model_hint=board_model, strong=True, ratio=0.0, limit=None,
            )
            if normalize_text(item["metric"].get("semantic_model")) == board_model
        ]
        options = self._collapse_year_variants(options, question)[: self._SUGGESTION_LIMIT]
        elsewhere = None
        if not options and metric.get("metric_id"):
            elsewhere = {
                "metric": metric, "score": metric_result.get("score"),
                "business_score": metric_result.get("score"),
                "matched_name": metric_result.get("matched_name"),
            }
        self._note(
            f"la pregunta nombra el tablero {board}, pero el indicador elegido "
            f"({metric.get('label')}) es de {metric.get('semantic_model')}: no se responde con él; "
            + (f"se ofrecen {len(options)} indicadores de {board}" if options
               else "ese tablero no tiene indicadores parecidos")
        )
        reports = metric.get("reports") or []
        return {
            "status": "not_found", "stage": "metric",
            "reason": "metric_not_in_named_report",
            "named_report": board,
            "found_elsewhere": {
                "metric_id": metric.get("metric_id"), "label": metric.get("label"),
                "report": metric.get("report") or (reports[0] if reports else None),
                "semantic_model": metric.get("semantic_model"),
            } if metric.get("metric_id") else None,
            "question": question, "source_context": source_context,
            "metric_resolution": {
                "status": "not_found", "candidates": [],
                "suggestions": [
                    {k: v for k, v in item.items() if not k.startswith("_")}
                    for item in (options or ([elsewhere] if elsewhere else []))
                ],
            },
        }

    def _model_has_report(self, semantic_model):
        """¿El modelo tiene algún informe publicado (algún indicador suyo en un
        visual o página documentada)? «Dashboard Gestion» no tiene ninguno."""
        models = self.__dict__.get("_models_with_report")
        if models is None:
            models = {
                normalize_text(metric.get("semantic_model")) for metric in self.metrics
                if metric.get("appearances") or self._metric_pages(metric)
            }
            self._models_with_report = models
        return normalize_text(semantic_model) in models

import inspect

from src.rag.extractive import readable_fallback


class RAGAnswerEngine:

    def __init__(self, retriever, default_limit=5, answer_synthesizer=None, min_score=0.35):
        self.retriever = retriever
        self.answer_synthesizer = answer_synthesizer
        self.default_limit = default_limit
        self.min_score = min_score

    def _deduplicate_results(self, results):
        unique_results = []
        seen_texts = set()
        for result in results:
            text = (result.get("text", "") or "").strip()
            if not text or text in seen_texts:
                continue
            seen_texts.add(text)
            unique_results.append(result)
        return unique_results

    # Preguntas sobre el tablero completo («¿qué muestra?», «¿qué filtros
    # tiene?»): su resumen (dashboard_overview) es la mejor evidencia.
    _OVERVIEW_INTENTS = ("describe_dashboard", "get_filters")

    def _dashboard_overview(self, intent_data):
        dashboard = intent_data.get("dashboard")
        search = getattr(self.retriever, "search", None)
        if intent_data.get("intent") not in self._OVERVIEW_INTENTS or not dashboard or not callable(search):
            return []
        try:
            results = search(
                intent_data.get("original_question") or "",
                limit=2,
                dashboard=dashboard,
                chunk_type="dashboard_overview",
            ) or []
        except Exception:
            return []
        return [
            result for result in results
            if result.get("dashboard") == dashboard
            and result.get("chunk_type") == "dashboard_overview"
        ][:1]

    def _is_hybrid(self):
        """El HybridRetriever actual aplica él mismo umbral, alcance y
        diversidad (search_general acepta min_score)."""
        search_general = getattr(self.retriever, "search_general", None)
        if not callable(search_general):
            return False
        try:
            return "min_score" in inspect.signature(search_general).parameters
        except (TypeError, ValueError):
            return False

    def _retrieve_general_context(self, intent_data, limit=None):
        question = intent_data.get("original_question") or ""
        dashboard = intent_data.get("dashboard")
        overview = self._dashboard_overview(intent_data)

        if self._is_hybrid():
            results = self.retriever.search_general(
                question=question,
                limit=limit or self.default_limit,
                dashboard=dashboard,
                min_score=self.min_score,
            ) or []
            filtered_results = [
                result
                for result in results
                if result.get("relevant", True)
            ]
            # El resumen del tablero que detectó el IntentParser solo se
            # antepone si pertenece al informe en que buscó el retriever
            # («tiempos de urgencias» no es la página URGENCIAS del Briefing).
            scope = (filtered_results[0].get("scope") if filtered_results else None) or None
            if overview and scope:
                groups = set(scope.get("source_groups") or [])
                overview = [
                    result for result in overview
                    if (result.get("source_group") or "") in groups
                ]
            # «¿Qué filtros tiene?»: los chunks de filtros/segmentadores que
            # ya priorizó el retriever van primero; el resumen se incluye al
            # final (dentro del límite) como contexto.
            # (Si el texto no habla de filtros, p. ej. la respuesta a «¿a qué
            # tablero?» es solo el nombre, el resumen sigue yendo primero.)
            ranked_for_filters = bool(filtered_results) and filtered_results[0].get("intent") == "filters"
            if overview and intent_data.get("intent") == "get_filters" and ranked_for_filters:
                overview_text = (overview[0].get("text") or "").strip()
                kept = [
                    result
                    for result in self._deduplicate_results(filtered_results)
                    if (result.get("text") or "").strip() != overview_text
                ]
                # Solo si alguna otra fuente habla de filtros/segmentadores.
                if any(float(result.get("lexical_score") or 0) > 0 for result in kept):
                    return kept[:max(self.default_limit - 1, 1)] + overview
        else:
            retrieval_limit = limit or max(self.default_limit * 2, 6)
            results = self.retriever.search_general(
                question=question,
                limit=retrieval_limit,
                dashboard=dashboard,
            ) or []
            filtered_results = [
                result
                for result in results
                if float(result.get("score", 0) or 0) >= self.min_score
            ]

        # IMPORTANTE: si nada supera el umbral, no usamos resultados débiles
        # (el resumen del tablero nombrado sí es evidencia válida).
        if not filtered_results and not overview:
            return []

        return self._deduplicate_results(overview + filtered_results)[:self.default_limit]

    NOT_FOUND_ANSWER = (
        "No encontré información relacionada con esa pregunta en la "
        "documentación de los tableros disponibles."
    )

    def _fallback_answer(self, results):
        """Resumen extractivo legible (sin prefijos técnicos ni DAX); si no
        se puede armar, el texto de las fuentes como antes."""
        readable = readable_fallback(results)
        if readable:
            return readable
        contexts = [r.get("text", "") for r in results if r.get("text")]
        return "\n\n".join(contexts)

    def _synthesize_answer(self, question, results):
        """(respuesta, modo, sin_evidencia)."""
        if self.answer_synthesizer is None:
            return self._fallback_answer(results), "extractive", False

        synthesis = self.answer_synthesizer.synthesize_rag(
            question=question,
            sources=results,
        )

        if synthesis.get("status") == "success":
            return synthesis.get("answer"), "llm", bool(synthesis.get("no_evidence"))

        return self._fallback_answer(results), "extractive", False

    def _not_found_response(self, sources=None, synthesis_mode="none", reason="no_relevant_context"):
        return {
            "status": "not_found",
            # no_relevant_context: ninguna fuente superó el umbral de
            # evidencia; llm_no_evidence: el LLM leyó las fuentes y no halló
            # respuesta. En ambos casos la pregunta queda fuera de la
            # documentación (QueryEngine puede tratarla como fuera de alcance).
            "not_found_reason": reason,
            "answer": self.NOT_FOUND_ANSWER,
            "contexts": [],
            "sources": sources or [],
            "retrieval_mode": "open",
            "synthesis_mode": synthesis_mode,
        }

    def _build_context_response(self, question, results):
        if not results:
            return self._not_found_response()

        answer, synthesis_mode, no_evidence = self._synthesize_answer(question, results)

        # El LLM leyó las fuentes y no halló respuesta: es «no encontrado»
        # (QueryEngine lo trata como fuera de alcance / sin evidencia).
        if no_evidence:
            return self._not_found_response(results, synthesis_mode, reason="llm_no_evidence")

        return {
            "status": "success",
            "answer": answer,
            "contexts": [r.get("text", "") for r in results if r.get("text")],
            "sources": results,
            "retrieval_mode": "open",
            "synthesis_mode": synthesis_mode,
        }

    def _answer_general(self, intent_data):
        question = intent_data.get("original_question") or ""
        results = self._retrieve_general_context(intent_data)
        return self._build_context_response(question, results)

    def answer(self, intent_data):
        return self._answer_general(intent_data)

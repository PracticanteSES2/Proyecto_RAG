import inspect


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

    def _synthesize_answer(self, question, results):
        contexts = [r.get("text", "") for r in results if r.get("text")]
        fallback = "\n\n".join(contexts)

        if self.answer_synthesizer is None:
            return fallback, "extractive"

        synthesis = self.answer_synthesizer.synthesize_rag(
            question=question,
            sources=results,
        )

        if synthesis.get("status") == "success":
            return synthesis.get("answer"), "llm"

        return fallback, "extractive"

    def _build_context_response(self, question, results):
        if not results:
            return {
                "status": "not_found",
                "answer": (
                    "No encontré información relacionada con esa pregunta en la "
                    "documentación de los tableros disponibles."
                ),
                "contexts": [],
                "sources": [],
                "retrieval_mode": "open",
                "synthesis_mode": "none",
            }

        answer, synthesis_mode = self._synthesize_answer(question, results)

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

class RAGAnswerEngine:

    def __init__(self, retriever, default_limit=3, answer_synthesizer=None, min_score=0.35):
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

    def _retrieve_general_context(self, intent_data, limit=None):
        question = intent_data.get("original_question") or ""
        dashboard = intent_data.get("dashboard")
        retrieval_limit = limit or max(self.default_limit * 2, 6)

        results = self.retriever.search_general(
            question=question,
            limit=retrieval_limit,
            dashboard=dashboard,
        )

        if not results:
            return []

        filtered_results = [
            result
            for result in results
            if float(result.get("score", 0) or 0) >= self.min_score
        ]

        # IMPORTANTE: si nada supera el umbral, no usamos resultados débiles.
        if not filtered_results:
            return []

        return self._deduplicate_results(filtered_results)[:self.default_limit]

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

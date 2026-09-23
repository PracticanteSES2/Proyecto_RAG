class RAGAnswerEngine:

    def __init__(
        self,
        retriever,
        default_limit=5,
        answer_synthesizer=None,
        min_score=0.35,
    ):

        self.retriever = retriever
        self.answer_synthesizer = (
            answer_synthesizer
        )
        self.default_limit = (
            default_limit
        )
        self.min_score = (
            min_score
        )
    def _synthesize_answer(
        self,
        question,
        results
    ):

        contexts = [
            result.get(
                "text",
                ""
            )
            for result in results
            if result.get(
                "text"
            )
        ]


        # ========================================================
        # FALLBACK SIN LLM
        # ========================================================

        fallback_answer = (
            "\n\n".join(
                contexts
            )
        )


        if (
            self.answer_synthesizer
            is None
        ):

            return fallback_answer


        # ========================================================
        # SÍNTESIS CON QWEN
        # ========================================================

        synthesis = (
            self.answer_synthesizer
            .synthesize_rag(
                question=question,
                sources=results
            )
        )


        if (
            synthesis.get(
                "status"
            )
            == "success"
        ):

            return synthesis.get(
                "answer"
            )


        # Si Ollama falla, el RAG
        # continúa funcionando.
        return fallback_answer

    # ========================================================
    # HELPERS
    # ========================================================

    def _deduplicate_results(
        self,
        results,
    ):
        """
        Elimina chunks vacíos o duplicados preservando el orden.
        """

        unique_results = []
        seen_texts = set()

        for result in results:

            text = (
                result.get(
                    "text",
                    "",
                )
                or ""
            ).strip()

            if not text:
                continue

            if text in seen_texts:
                continue

            seen_texts.add(
                text
            )

            unique_results.append(
                result
            )

        return unique_results


    def _retrieve_general_context(
        self,
        intent_data,
        limit=None,
    ):
        """
        Recuperación abierta para preguntas documentales.

        No obliga a dashboard_overview, measure, etc.
        Deja que la similitud semántica encuentre el tipo de
        evidencia más útil para la pregunta.
        """

        question = (
            intent_data.get(
                "original_question"
            )
            or ""
        )

        dashboard = (
            intent_data.get(
                "dashboard"
            )
        )

        retrieval_limit = (
            limit
            or max(
                self.default_limit * 2,
                8,
            )
        )

        results = (
            self.retriever
            .search_general(
                question=question,
                limit=retrieval_limit,
                dashboard=dashboard,
            )
        )

        if not results:
            return []

        # Primero intentamos conservar solamente evidencia
        # con una similitud razonable.
        filtered_results = [
            result
            for result in results
            if result.get(
                "score",
                0,
            ) >= self.min_score
        ]

        # Si todos quedaron debajo del umbral, no dejamos la
        # pregunta completamente sin contexto: conservamos los
        # mejores resultados como fallback.
        if not filtered_results:
            filtered_results = (
                results[:self.default_limit]
            )

        unique_results = (
            self._deduplicate_results(
                filtered_results
            )
        )

        return unique_results[
            :self.default_limit
        ]


    def _build_context_response(
        self,
        question,
        results,
    ):
        """
        Empaqueta la evidencia recuperada y, si existe un
        AnswerSynthesizer, utiliza Qwen para redactar la respuesta.

        Si el LLM no está configurado o falla, conserva el fallback
        extractivo con los chunks recuperados.
        """

        if not results:

            return {
                "status": "not_found",
                "answer": None,
                "contexts": [],
                "sources": [],
                "retrieval_mode": "open",
                "synthesis_mode": "none",
            }

        contexts = [
            result.get(
                "text",
                "",
            )
            for result in results
            if result.get(
                "text"
            )
        ]

        answer = self._synthesize_answer(
            question=question,
            results=results,
        )

        fallback_answer = "\n\n".join(
            contexts
        )

        synthesis_mode = (
            "llm"
            if self.answer_synthesizer is not None
            and answer
            and answer != fallback_answer
            else "extractive"
        )

        return {
            "status": "success",
            "answer": answer,
            "contexts": contexts,
            "sources": results,
            "retrieval_mode": "open",
            "synthesis_mode": synthesis_mode,
        }


    # ========================================================
    # DESCRIPCIÓN DE DASHBOARD
    # ========================================================

    def _answer_dashboard_description(
        self,
        intent_data,
    ):
        """
        También utiliza recuperación abierta.

        Esto evita que una pregunta como
        "¿para qué sirve la proyección de cirugías?"
        quede forzada únicamente a dashboard_overview.
        """

        results = (
            self._retrieve_general_context(
                intent_data
            )
        )

        question = (
            intent_data.get(
                "original_question"
            )
            or ""
        )

        return self._build_context_response(
            question=question,
            results=results,
        )


    # ========================================================
    # FILTROS DEL DASHBOARD
    # ========================================================

    def _answer_filters(
        self,
        intent_data,
    ):
        """
        Usa recuperación abierta dentro del dashboard.
        La pregunta original ya aporta la intención de filtros,
        por lo que no es necesario forzar chunk_type.
        """

        results = (
            self._retrieve_general_context(
                intent_data
            )
        )

        question = (
            intent_data.get(
                "original_question"
            )
            or ""
        )

        return self._build_context_response(
            question=question,
            results=results,
        )


    # ========================================================
    # CONSULTA GENERAL RAG
    # ========================================================

    def _answer_general(
        self,
        intent_data,
    ):

        results = (
            self._retrieve_general_context(
                intent_data
            )
        )

        question = (
            intent_data.get(
                "original_question"
            )
            or ""
        )

        return self._build_context_response(
            question=question,
            results=results,
        )


    # ========================================================
    # ROUTER
    # ========================================================

    def answer(
        self,
        intent_data,
    ):

        intent = intent_data.get(
            "intent"
        )

        if intent == "describe_dashboard":

            return (
                self
                ._answer_dashboard_description(
                    intent_data
                )
            )

        if intent == "get_filters":

            return (
                self
                ._answer_filters(
                    intent_data
                )
            )

        # Cualquier otra pregunta documental usa recuperación
        # general abierta.
        return (
            self._answer_general(
                intent_data
            )
        )
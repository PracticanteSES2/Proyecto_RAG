class QueryEngine:

    def __init__(
        self,
        conversation_manager,
        metric_resolver,
        filter_resolver,
        business_filter_resolver,
        dax_generator,
        dax_validator,
        powerbi_provider,
        rag_answer_engine,
    ):
        self.conversation_manager = conversation_manager
        self.metric_resolver = metric_resolver
        self.filter_resolver = filter_resolver
        self.business_filter_resolver = business_filter_resolver
        self.dax_generator = dax_generator
        self.dax_validator = dax_validator
        self.powerbi_provider = powerbi_provider
        self.rag_answer_engine = rag_answer_engine

    def _extract_value(self, powerbi_result):
        rows = powerbi_result.get("rows", [])
        if not rows:
            return None
        first_row = rows[0]
        if not first_row:
            return None
        return next(iter(first_row.values()), None)

    def process(self, message):
        intent_result = self.conversation_manager.handle_message(message)

        if intent_result.get("status") == "needs_clarification":
            return {
                "status": "needs_clarification",
                "route": "clarification",
                "question": intent_result.get("clarification_question"),
                "intent": intent_result,
            }

        if intent_result.get("status") != "ready":
            return {"status": "error", "stage": "intent", "details": intent_result}

        intent = intent_result.get("intent")

        if intent in ["describe_dashboard", "get_filters", "general_question"]:
            rag_result = self.rag_answer_engine.answer(intent_result)

            if rag_result.get("status") == "not_found":
                return {
                    "status": "not_found",
                    "route": "out_of_scope",
                    "question": intent_result.get("original_question"),
                    "dashboard": None,
                    "answer": rag_result.get("answer"),
                    "sources": [],
                    "synthesis_mode": "none",
                }

            return {
                "status": rag_result.get("status"),
                "route": "rag",
                "question": intent_result.get("original_question"),
                "dashboard": intent_result.get("dashboard"),
                "answer": rag_result.get("answer"),
                "sources": rag_result.get("sources", []),
                "synthesis_mode": rag_result.get("synthesis_mode"),
            }

        metric_result = self.metric_resolver.resolve(intent_result)

        if metric_result.get("status") != "resolved":
            return {"status": "metric_not_resolved", "stage": "metric", "details": metric_result}

        resolved_dashboard = intent_result.get("dashboard") or metric_result.get("dashboard")

        semantic_model = (
            metric_result.get("semantic_model")
            or self.powerbi_provider.default_semantic_model
        )

        temporal_filter_result = self.filter_resolver.resolve(intent_result)
        if temporal_filter_result.get("status") != "resolved":
            return {"status": "filter_not_resolved", "stage": "temporal_filters", "details": temporal_filter_result}

        business_filter_result = self.business_filter_resolver.resolve(
            question=intent_result.get("original_question") or "",
            dashboard=resolved_dashboard,
            semantic_model=semantic_model,
        )
        if business_filter_result.get("status") != "resolved":
            return {"status": "filter_not_resolved", "stage": "business_filters", "details": business_filter_result}

        combined_filters = (
            temporal_filter_result.get("filters", [])
            + business_filter_result.get("filters", [])
        )

        filter_result = {"status": "resolved", "filters": combined_filters, "problems": []}

        dax_result = self.dax_generator.generate(metric_result, filter_result)
        if dax_result.get("status") != "generated":
            return {"status": "dax_not_generated", "stage": "dax_generator", "details": dax_result}

        validation_result = self.dax_validator.validate(dax_result, metric_result, filter_result)
        if not validation_result.get("valid", False):
            return {"status": "dax_rejected", "stage": "dax_validator", "details": validation_result}

        powerbi_result = self.powerbi_provider.execute_validated(
            validation_result,
            semantic_model=semantic_model,
        )
        if powerbi_result.get("status") != "success":
            return {"status": "powerbi_error", "stage": "powerbi", "details": powerbi_result}

        value = self._extract_value(powerbi_result)

        return {
            "status": "success",
            "route": "powerbi",
            "question": intent_result.get("original_question"),
            "dashboard": resolved_dashboard,
            "semantic_model": semantic_model,
            "metric": metric_result.get("measure"),
            "metric_type": intent_result.get("metric_type"),
            "year": intent_result.get("year"),
            "month": intent_result.get("month"),
            "filters": combined_filters,
            "business_filters": business_filter_result.get("filters", []),
            "value": value,
            "dax": validation_result.get("dax"),
            "powerbi": powerbi_result,
        }

    def close(self):
        if self.powerbi_provider:
            self.powerbi_provider.close()

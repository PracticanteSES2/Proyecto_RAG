import inspect
import os
import re

from src.chatbot.runtime_stats import STATS
from src.rag.extractive import readable_fallback
from src.rag.grounding import ground_answer, has_content
from src.rag.ranking import detect_question_intent
from src.semantic.question_normalizer import fold


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

    def _fallback_answer(self, results, question=None):
        """Resumen extractivo legible (sin prefijos técnicos ni DAX): primero
        la entrada más pertinente a la pregunta y solo las de su mismo tablero;
        si no se puede armar, el texto de las fuentes como antes."""
        readable = readable_fallback(results, question=question)
        if readable:
            return readable
        contexts = [r.get("text", "") for r in results if r.get("text")]
        return "\n\n".join(contexts)

    @staticmethod
    def _synthesis_issue(synthesis):
        """Por qué no se usó el LLM (texto para el razonamiento) o None."""
        details = synthesis.get("details") or {}
        status = details.get("status") or synthesis.get("status")
        if status == "llm_timeout":
            return (f"MedGemma no respondió en {details.get('timeout_seconds') or '-'} s "
                    "(se cortó la llamada): se usa el resumen extractivo")
        if status == "llm_saturated":
            return (f"MedGemma estaba saturado ({details.get('error') or 'sin hueco libre'}): "
                    "se usa el resumen extractivo sin esperar")
        if status:
            error = details.get("error")
            return f"MedGemma no disponible ({status}{': ' + str(error)[:120] if error else ''}): "                    "se usa el resumen extractivo"
        return None

    # Tipos de fuente cuya descripción puede ser, tal cual, la definición.
    _DIRECT_TYPES = ("measure", "documented_measure", "indicator", "calculated_column")

    @staticmethod
    def _compact(text):
        return re.sub(r"[^a-z0-9]+", "", fold(text or ""))

    @classmethod
    def _names_its_definition(cls, question, top):
        """«¿Qué es X?» y la fuente principal es la entrada documentada de X."""
        named = cls._compact(top.get("measure"))
        return (
            (top.get("intent") or detect_question_intent(question)) == "definition"
            and top.get("chunk_type") in cls._DIRECT_TYPES
            and len(named) >= 4 and named in cls._compact(question)
        )

    @classmethod
    def _direct_extract(cls, question, results, history=None):
        """Respuesta extractiva que ya ES la respuesta (palanca OPCIONAL,
        RAG_EXTRACTO_DIRECTO=on; specs/010-rendimiento-llm): «¿qué es X?» sin
        conversación previa, cuando la mejor fuente es la entrada documentada
        de X (la pregunta nombra su medida) y su descripción es una frase
        completa. Ahorra la síntesis (1 llamada a MedGemma). Apagada por
        defecto hasta compararla con MedGemma en los bancos reales."""
        enabled = os.getenv("RAG_EXTRACTO_DIRECTO", "off").strip().lower() in ("on", "1", "si", "true")
        if not enabled or history or not results or not cls._names_its_definition(question, results[0]):
            return None
        answer = readable_fallback([results[0]], question=question)
        description = (answer or "").split(":", 1)[-1]
        if not answer or "\n- " in answer or len(re.findall(r"\w{2,}", description)) < 6:
            return None
        STATS.llm_call_avoided("extracto: síntesis RAG")
        return answer

    def _synthesize_answer(self, question, results, history=None):
        """(respuesta, modo, sin_evidencia). Si no se usa el LLM, el motivo
        queda en self.last_synthesis_issue (lo muestra el razonamiento)."""
        self.last_synthesis_issue = None
        if self.answer_synthesizer is None:
            return self._fallback_answer(results, question), "extractive", False
        direct = self._direct_extract(question, results, history)
        if direct:
            # No es un respaldo: el extracto ya responde (no se marca degradado).
            return direct, "extracto", False

        # El historial solo se pasa si existe: los sintetizadores que no lo
        # aceptan (dobles de prueba antiguos) siguen funcionando.
        kwargs = {"question": question, "sources": results}
        if history:
            kwargs["history"] = history
        synthesis = self.answer_synthesizer.synthesize_rag(**kwargs)

        if synthesis.get("status") == "success":
            return synthesis.get("answer"), "llm", bool(synthesis.get("no_evidence"))

        self.last_synthesis_issue = self._synthesis_issue(synthesis)
        return self._fallback_answer(results, question), "extractive", False

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

    def _build_context_response(self, question, results, history=None):
        if not results:
            return self._not_found_response()

        answer, synthesis_mode, no_evidence = self._synthesize_answer(question, results, history)

        # El LLM leyó las fuentes y no halló respuesta: es «no encontrado»
        # (QueryEngine lo trata como fuera de alcance / sin evidencia).
        if no_evidence:
            return self._not_found_response(results, synthesis_mode, reason="llm_no_evidence")

        # Salvaguarda (también para el respaldo extractivo): la respuesta
        # documental no afirma cifras, tendencias ni listas que no estén en
        # lo recuperado (src/rag/grounding.py).
        answer, unsupported = ground_answer(answer, self._evidence_texts(results), question)
        if unsupported and not has_content(answer):
            return self._not_found_response(results, synthesis_mode, reason="unsupported_claims")

        return {
            "status": "success",
            "answer": answer,
            "contexts": [r.get("text", "") for r in results if r.get("text")],
            "sources": results,
            "retrieval_mode": "open",
            "synthesis_mode": synthesis_mode,
            "synthesis_issue": getattr(self, "last_synthesis_issue", None),
        }

    @staticmethod
    def _evidence_texts(results):
        """Todo lo recuperado (texto y metadatos legibles) que respalda la respuesta."""
        texts = []
        for result in results or []:
            for value in result.values():
                if isinstance(value, str):
                    texts.append(value)
                elif isinstance(value, dict):
                    texts.extend(str(item) for item in value.values() if isinstance(item, (str, int, float)))
                elif isinstance(value, (list, tuple)):
                    texts.extend(str(item) for item in value if isinstance(item, (str, int, float)))
        return texts

    def _answer_general(self, intent_data, history=None):
        question = intent_data.get("original_question") or ""
        results = self._retrieve_general_context(intent_data)
        return self._build_context_response(question, results, history)

    def answer(self, intent_data, history=None):
        """Respuesta documental. `history` (opcional): últimos turnos de la
        conversación [{"role": "user"|"assistant", "text": str, "meta": {}}];
        solo orienta la redacción (referencias, no repetir), nunca es
        evidencia: la respuesta se respalda únicamente en lo recuperado."""
        return self._answer_general(intent_data, history)

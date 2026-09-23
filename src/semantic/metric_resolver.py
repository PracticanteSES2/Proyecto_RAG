import re
import unicodedata


class MetricResolver:

    METRIC_HINTS = {
        "promedio": "promedio mensual media valor promedio",
        "total": "total cantidad conteo número total",
        "proyeccion": "proyección estimación valor proyectado",
        "porcentaje": "porcentaje proporción porcentual",
        "variacion": "variación crecimiento comparación cambio",
    }

    METRIC_POSITIVE_TERMS = {
        "promedio": [
            "prom",
            "promedio",
            "media",
        ],
        "total": [
            "total",
            "cantidad",
            "conteo",
            "numero",
        ],
        "proyeccion": [
            "proyeccion",
            "proyectado",
            "estimado",
        ],
        "porcentaje": [
            "porcentaje",
            "porcentual",
            "pct",
        ],
        "variacion": [
            "variacion",
            "crecimiento",
            "cambio",
        ],
    }

    METRIC_NEGATIVE_TERMS = {
        "promedio": [
            "ano anterior",
            "ano actual",
            "proyeccion",
            "porcentaje",
            "variacion",
        ],
        "total": [
            "promedio",
            "prom",
            "proyeccion",
            "porcentaje",
            "variacion",
        ],
        "proyeccion": [
            "promedio",
            "ano anterior",
            "porcentaje",
        ],
        "porcentaje": [
            "promedio",
            "proyeccion",
            "total",
        ],
        "variacion": [
            "promedio",
            "proyeccion",
            "total",
        ],
    }

    def __init__(
        self,
        retriever,
        min_score=0.35,
        ambiguity_margin=0.025,
        debug=True,
    ):
        self.retriever = retriever
        self.min_score = min_score
        self.ambiguity_margin = ambiguity_margin
        self.debug = debug

    # ========================================================
    # UTILIDADES
    # ========================================================

    def _normalize_text(self, value):
        if not value:
            return ""

        value = str(value).lower()

        value = "".join(
            char
            for char in unicodedata.normalize("NFD", value)
            if unicodedata.category(char) != "Mn"
        )

        value = value.replace("_", " ")
        value = re.sub(r"[^a-z0-9\s]", " ", value)
        value = re.sub(r"\s+", " ", value)

        return value.strip()

    # ========================================================
    # CONSTRUIR CONSULTA SEMÁNTICA
    # Se conserva para una futura capa híbrida de ranking.
    # ========================================================

    def _build_query(self, intent_data):
        original_question = intent_data.get("original_question") or ""
        dashboard = intent_data.get("dashboard") or ""
        metric_type = self._normalize_text(
            intent_data.get("metric_type") or ""
        )

        hints = self.METRIC_HINTS.get(
            metric_type,
            metric_type,
        )

        return (
            f"{original_question} "
            f"{dashboard} "
            f"{hints}"
        ).strip()

    # ========================================================
    # RERANKING DE CANDIDATOS
    # ========================================================

    def _rerank_candidates(
        self,
        candidates,
        intent_data,
    ):
        metric_type = self._normalize_text(
            intent_data.get("metric_type") or ""
        )

        question = self._normalize_text(
            intent_data.get("original_question")
        )

        positive_terms = self.METRIC_POSITIVE_TERMS.get(
            metric_type,
            [],
        )

        negative_terms = self.METRIC_NEGATIVE_TERMS.get(
            metric_type,
            [],
        )

        question_words = {
            word
            for word in question.split()
            if len(word) >= 4
        }

        reranked = []

        # IMPORTANTE:
        # recorremos TODOS los candidatos antes de ordenar y retornar.
        for candidate in candidates:
            vector_score = float(
                candidate.get("score", 0) or 0
            )

            measure_name = self._normalize_text(
                candidate.get("measure")
            )

            context = self._normalize_text(
                candidate.get("text")
            )

            final_score = vector_score

            # ----------------------------------------------------
            # Señales positivas
            # ----------------------------------------------------

            for term in positive_terms:
                normalized_term = self._normalize_text(term)

                # Coincidencia en el nombre real de la medida:
                # señal fuerte.
                if normalized_term in measure_name:
                    final_score += 0.50

                # Coincidencia solo en el contexto/documentación:
                # señal más débil.
                elif normalized_term in context:
                    final_score += 0.10

            # ----------------------------------------------------
            # Penalizaciones por conceptos incompatibles
            # ----------------------------------------------------

            for term in negative_terms:
                normalized_term = self._normalize_text(term)

                if normalized_term in measure_name:
                    final_score -= 0.40

            # ----------------------------------------------------
            # Coincidencia entre la pregunta y el nombre
            # de la medida
            # ----------------------------------------------------

            measure_words = set(
                measure_name.split()
            )

            overlap = (
                question_words
                & measure_words
            )

            final_score += (
                len(overlap)
                * 0.05
            )

            candidate_copy = candidate.copy()
            candidate_copy["vector_score"] = vector_score
            candidate_copy["final_score"] = final_score

            reranked.append(
                candidate_copy
            )

        # ESTAS DOS INSTRUCCIONES DEBEN ESTAR FUERA DEL FOR.
        reranked.sort(
            key=lambda item: item["final_score"],
            reverse=True,
        )

        return reranked

    # ========================================================
    # RESOLVER MEDIDA
    # ========================================================

    def resolve(self, intent_data):
        dashboard = intent_data.get("dashboard")
        metric_type = self._normalize_text(
            intent_data.get("metric_type") or ""
        )

        if not metric_type:
            return {
                "status": "not_ready",
                "reason": "metric_type_missing",
            }

        question = (
            intent_data.get("original_question")
            or ""
        )

        # ----------------------------------------------------
        # 1. Recuperar candidatos
        # ----------------------------------------------------
        #
        # Si el usuario mencionó un dashboard, usamos TODAS sus
        # medidas. Si no lo mencionó, buscamos semánticamente
        # entre TODAS las medidas indexadas.
        # ----------------------------------------------------

        if dashboard:

            candidates = (
                self.retriever
                .get_measures_by_dashboard(
                    dashboard
                )
            )

        else:

            candidates = (
                self.retriever
                .search_measure_candidates(
                    question=question,
                    limit=20,
                    dashboard=None,
                )
            )

        candidates = [
            candidate
            for candidate in candidates
            if candidate.get("measure")
        ]

        if not candidates:
            return {
                "status": "not_found",
                "dashboard": dashboard,
                "metric_type": metric_type,
                "candidates": [],
            }

        # ----------------------------------------------------
        # 2. Reordenar candidatos
        # ----------------------------------------------------

        candidates = self._rerank_candidates(
            candidates,
            intent_data,
        )

        if not candidates:
            return {
                "status": "not_found",
                "dashboard": dashboard,
                "metric_type": metric_type,
                "candidates": [],
            }

        # ----------------------------------------------------
        # 3. Diagnóstico
        # ----------------------------------------------------

        if self.debug:
            print("\nCANDIDATOS DE MÉTRICA:")

            for candidate in candidates[:10]:
                print(
                    f"- {candidate['measure']} "
                    f"| dashboard={candidate.get('dashboard')} "
                    f"| vector={candidate['vector_score']:.4f} "
                    f"| final={candidate['final_score']:.4f}"
                )

        # ----------------------------------------------------
        # 4. Seleccionar mejor candidato
        # ----------------------------------------------------

        best = candidates[0]

        if best["final_score"] < self.min_score:
            return {
                "status": "not_found",
                "dashboard": dashboard,
                "metric_type": metric_type,
                "best_score": best["final_score"],
                "candidates": candidates[:5],
            }

        # ----------------------------------------------------
        # 5. Detectar ambigüedad
        # ----------------------------------------------------

        if len(candidates) > 1:
            second = candidates[1]

            score_difference = (
                best["final_score"]
                - second["final_score"]
            )

            if (
                best.get("measure") != second.get("measure")
                and score_difference < self.ambiguity_margin
            ):
                return {
                    "status": "ambiguous",
                    "dashboard": dashboard,
                    "metric_type": metric_type,
                    "candidates": candidates[:3],
                }

        # ----------------------------------------------------
        # 6. Medida resuelta
        # ----------------------------------------------------

        resolved_dashboard = (
            dashboard
            or best.get("dashboard")
        )

        return {
            "status": "resolved",
            "dashboard": resolved_dashboard,
            "metric_type": metric_type,
            "semantic_model": best.get("semantic_model"),
            "measure": best["measure"],
            "table": best.get("table"),
            "score": best["final_score"],
            "vector_score": best["vector_score"],
            "context": best.get("text", ""),
            "alternatives": candidates[1:3],
        }

    

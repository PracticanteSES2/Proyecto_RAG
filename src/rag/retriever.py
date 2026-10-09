import os
from pathlib import Path

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
)

from src.rag.ranking import (
    LexicalIndex,
    ScopeIndex,
    detect_question_intent,
    normalize_text,
    query_terms,
    select_diverse,
    tokenize,
    type_prior,
)


MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

COLLECTION_NAME = os.getenv(
    "QDRANT_COLLECTION_NAME",
    "gestion_clinica_rag",
)

LEGACY_COLLECTION_NAME = (
    "tablero_de_atenciones_institucionales"
)

# Volcados técnicos: su coseno con preguntas en lenguaje natural es engañoso
# (nombres de aseguradoras, ciudades...), así que sin tablero nombrado solo
# cuentan como evidencia si además coinciden léxicamente.
TECHNICAL_CHUNK_TYPES = {"sql_query", "table_context"}


# ============================================================
# NORMALIZACIÓN
# ============================================================

# normalize_text vive en ranking.py (lógica pura); se reexporta aquí por
# compatibilidad con quienes la importan desde src.rag.retriever.


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ============================================================
# RETRIEVER HÍBRIDO
# ============================================================

class HybridRetriever:

    # Pesos de la puntuación híbrida (vectorial + léxica + tipo + alcance).
    VECTOR_WEIGHT = 0.6
    LEXICAL_WEIGHT = 0.4
    # Página nombrada: sus chunks pesan más que los de otras páginas del
    # mismo informe (que siguen siendo candidatos: el semáforo de «auditoría
    # de medicamentos» está en «EN PROCESO AUDITORÍA MEDICAMENTOS»).
    FOCUS_PAGE_BONUS = 0.15
    OTHER_PAGE_PENALTY = 0.08
    FOCUS_REPORT_PAGE_BONUS = 0.06

    # Umbrales de evidencia.
    DEFAULT_MIN_SCORE = 0.35
    # Con tablero nombrado explícitamente los cosenos dentro del tablero son
    # bajos (0.25-0.35); se confía en el filtro con un umbral menor.
    SCOPED_MIN_SCORE = 0.20
    SCOPED_MIN_LEXICAL = 0.20
    # Sin tablero: el coseno debe superar min_score Y estar respaldado por
    # coincidencia léxica (o ser alto). Así «capital de Francia» o «clima en
    # Manizales» (coseno 0.35-0.45 contra textos genéricos, sin términos en
    # común) no llegan al LLM.
    UNSCOPED_MIN_LEXICAL_SUPPORT = 0.30
    UNSCOPED_STRONG_VECTOR = 0.50
    # Evidencia léxica fuerte compensa un coseno algo menor.
    UNSCOPED_MIN_LEXICAL = 0.50
    UNSCOPED_LEXICAL_MARGIN = 0.10

    MAX_VECTOR_CANDIDATES = 5000
    RERANK_POOL = 60

    def __init__(
        self,
        qdrant_path: Path,
        collection_name=None,
    ):
        self.model = SentenceTransformer(MODEL_NAME)
        self.client = QdrantClient(path=str(qdrant_path))

        preferred = collection_name or COLLECTION_NAME

        if self.client.collection_exists(preferred):
            self.collection_name = preferred
        elif self.client.collection_exists(LEGACY_COLLECTION_NAME):
            # Compatibilidad durante la migración. Una vez se construya
            # gestion_clinica_rag, el retriever usará automáticamente la nueva.
            self.collection_name = LEGACY_COLLECTION_NAME
            print(
                "ADVERTENCIA RAG: usando colección legacy:",
                LEGACY_COLLECTION_NAME,
            )
        else:
            raise RuntimeError(
                "No existe una colección RAG utilizable. "
                "Ejecuta primero: python ingest_rag.py"
            )

        self._load_corpus()

    # --------------------------------------------------------
    # HELPERS DE PAYLOAD
    # --------------------------------------------------------

    def _payload_value(
        self,
        payload,
        key,
        default=None,
    ):
        payload = payload or {}
        metadata = payload.get("metadata", {}) or {}

        value = payload.get(key)
        if value is None:
            value = metadata.get(key, default)

        return value

    def _point_to_result(
        self,
        point,
        default_score=0.0,
    ):
        payload = point.payload or {}
        score = getattr(point, "score", default_score)

        if score is None:
            score = default_score

        return {
            "score": float(score),
            "chunk_type": self._payload_value(payload, "chunk_type"),
            "dashboard": self._payload_value(payload, "dashboard"),
            "dashboard_aliases": self._payload_value(
                payload,
                "dashboard_aliases",
                [],
            ) or [],
            "table": self._payload_value(payload, "table"),
            "measure": self._payload_value(payload, "measure"),
            "semantic_model": self._payload_value(
                payload,
                "semantic_model",
            ),
            "semantic_model_key": self._payload_value(
                payload,
                "semantic_model_key",
            ),
            "source_group": self._payload_value(
                payload,
                "source_group",
            ),
            "source_file": self._payload_value(
                payload,
                "source_file",
            ),
            "relative_path": self._payload_value(
                payload,
                "relative_path",
            ),
            "document_type": self._payload_value(
                payload,
                "document_type",
            ),
            "section": self._payload_value(payload, "section"),
            "text": self._payload_value(payload, "text", "") or "",
        }

    def _scroll_all(self, limit_per_page=512):
        """Recorre toda la colección sin asumir un máximo de 10.000 puntos."""
        offset = None

        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=limit_per_page,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            for point in points:
                yield point

            if next_offset is None:
                break

            offset = next_offset

    # --------------------------------------------------------
    # TABLEROS / ALIAS
    # --------------------------------------------------------

    def _load_dashboard_metadata(self, points=None):
        dashboards = set()
        aliases = {}

        for point in points if points is not None else self._scroll_all():
            payload = point.payload or {}
            dashboard = self._payload_value(payload, "dashboard")

            if not dashboard:
                continue

            dashboards.add(dashboard)

            candidate_aliases = [dashboard]
            candidate_aliases.extend(
                _as_list(
                    self._payload_value(
                        payload,
                        "dashboard_aliases",
                        [],
                    )
                )
            )

            source_group = self._payload_value(payload, "source_group")
            if source_group:
                candidate_aliases.append(
                    str(source_group).replace("_", " ")
                )

            for alias in candidate_aliases:
                normalized = normalize_text(alias)
                if not normalized:
                    continue

                current = aliases.get(normalized)
                if current is None or len(dashboard) > len(current):
                    aliases[normalized] = dashboard

        return sorted(dashboards), aliases

    def _load_corpus(self):
        """Carga en memoria los payloads (parte léxica y alcance).

        Los vectores siguen en Qdrant; aquí solo se guardan textos y metadatos
        (unos pocos MB para ~2.500 chunks).
        """
        points = list(self._scroll_all())

        (
            self.dashboards,
            self.dashboard_aliases,
        ) = self._load_dashboard_metadata(points)

        corpus = []
        documents = []
        scope_index = ScopeIndex()
        pages_by_group = {}

        for point in points:
            result = self._point_to_result(point)
            result["id"] = point.id
            corpus.append(result)

            documents.append(
                tokenize(
                    " ".join(
                        str(part)
                        for part in (
                            result.get("text"),
                            result.get("measure"),
                        )
                        if part
                    )
                )
            )

            group = result.get("source_group") or ""
            page = result.get("dashboard")

            if page:
                scope_index.add_page(group, page)
                group_pages = pages_by_group.setdefault(group, {})
                group_pages[page] = group_pages.get(page, 0) + 1

            if group:
                scope_index.add_report_name(group, group.replace("_", " "))
                if result.get("semantic_model"):
                    scope_index.add_report_name(group, result["semantic_model"])
                for alias in _as_list(result.get("dashboard_aliases")):
                    scope_index.add_report_name(group, alias)

        self._corpus = corpus
        self._lexical_index = LexicalIndex(documents)
        self._scope_index = scope_index
        self._pages_by_group = pages_by_group

    def refresh_metadata(self):
        self._load_corpus()

    # --------------------------------------------------------
    # DETECTAR TIPO DE PREGUNTA
    # --------------------------------------------------------

    def detect_chunk_type(self, question):
        question_normalized = normalize_text(question)

        filter_keywords = [
            "filtro",
            "filtros",
            "filtrar",
            "segmentar",
            "segmentadores",
        ]

        # Se conserva dashboard_overview por compatibilidad con IntentParser
        # y porque el overview contiene el resumen de filtros.
        if any(
            keyword in question_normalized
            for keyword in filter_keywords
        ):
            return "dashboard_overview"

        overview_patterns = [
            "que informacion",
            "que muestra",
            "que contiene",
            "para que sirve",
            "de que trata",
        ]

        if any(
            pattern in question_normalized
            for pattern in overview_patterns
        ):
            return "dashboard_overview"

        measure_keywords = [
            "promedio",
            "total",
            "cantidad",
            "numero",
            "cuantas",
            "cuantos",
            "porcentaje",
            "proyeccion",
            "variacion",
            "crecimiento",
            "indicador",
        ]

        if any(
            keyword in question_normalized
            for keyword in measure_keywords
        ):
            return "measure"

        return None

    # --------------------------------------------------------
    # DETECTAR TABLERO
    # --------------------------------------------------------

    def detect_scope(self, question):
        """Informe o página que nombra la pregunta (ver ScopeIndex)."""
        scope_index = getattr(self, "_scope_index", None)
        if scope_index is None:
            return None
        return scope_index.detect(question)

    def _main_page(self, source_group, report_tokens):
        """Página representativa de un informe (para detect_dashboard)."""
        pages = self._pages_by_group.get(source_group) or {}
        if not pages:
            return None

        report_tokens = set(report_tokens or [])
        containing = [
            page
            for page in pages
            if report_tokens and report_tokens <= set(tokenize(page))
        ]
        if containing:
            return min(
                containing,
                key=lambda page: (len(tokenize(page)), page),
            )

        return max(pages, key=lambda page: (pages[page], page))

    def detect_dashboard(self, question):
        """Devuelve la PÁGINA (campo `dashboard`) más probable.

        Coincidencia por tokens (sin «de», «del», «tablero», tildes ni
        plurales). Si la pregunta nombra un informe, se devuelve su página
        principal: la que contiene el nombre del informe o la más documentada.
        """
        scope = self.detect_scope(question)

        if scope is None:
            return None

        pages = scope.get("pages") or []
        if pages:
            return max(pages, key=lambda page: (len(page), page))

        for group in scope.get("source_groups") or []:
            page = self._main_page(group, scope.get("matched_tokens"))
            if page:
                return page

        return None

    # --------------------------------------------------------
    # CREAR FILTROS QDRANT
    # --------------------------------------------------------

    def build_filter(
        self,
        dashboard=None,
        chunk_type=None,
        semantic_model=None,
        source_group=None,
        source_file=None,
        section=None,
    ):
        conditions = []

        values = {
            "dashboard": dashboard,
            "chunk_type": chunk_type,
            "semantic_model": semantic_model,
            "source_group": source_group,
            "source_file": source_file,
            "section": section,
        }

        for key, value in values.items():
            if value:
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    )
                )

        if not conditions:
            return None

        return Filter(must=conditions)

    # --------------------------------------------------------
    # TODAS LAS MEDIDAS DE UN DASHBOARD
    # --------------------------------------------------------

    def get_measures_by_dashboard(
        self,
        dashboard,
        limit=500,
    ):
        results = []

        for point in self._scroll_all():
            result = self._point_to_result(
                point,
                default_score=0.0,
            )

            if result.get("chunk_type") != "measure":
                continue

            if result.get("dashboard") != dashboard:
                continue

            results.append(result)

            if len(results) >= limit:
                break

        return results

    # --------------------------------------------------------
    # BÚSQUEDA GLOBAL DE CANDIDATOS DE MÉTRICA
    # --------------------------------------------------------

    def search_measure_candidates(
        self,
        question,
        limit=20,
        dashboard=None,
        semantic_model=None,
    ):
        query_vector = self.model.encode(
            question,
            normalize_embeddings=True,
        )

        query_filter = self.build_filter(
            dashboard=dashboard,
            chunk_type="measure",
            semantic_model=semantic_model,
        )

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector.tolist(),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

        return [
            self._point_to_result(point)
            for point in response.points
        ]

    # --------------------------------------------------------
    # BÚSQUEDA ESTRUCTURADA
    # --------------------------------------------------------

    def search(
        self,
        question,
        limit=5,
        dashboard=None,
        chunk_type=None,
        semantic_model=None,
        source_group=None,
    ):
        if dashboard is None:
            dashboard = self.detect_dashboard(question)

        if chunk_type is None:
            chunk_type = self.detect_chunk_type(question)

        print("\nInterpretación de consulta")
        print("Dashboard detectado:", dashboard)
        print("Tipo esperado:", chunk_type)

        query_vector = self.model.encode(
            question,
            normalize_embeddings=True,
        )

        query_filter = self.build_filter(
            dashboard=dashboard,
            chunk_type=chunk_type,
            semantic_model=semantic_model,
            source_group=source_group,
        )

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector.tolist(),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

        if not response.points:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector.tolist(),
                limit=limit,
                with_payload=True,
            )

        return [
            self._point_to_result(point)
            for point in response.points
        ]

    # --------------------------------------------------------
    # BÚSQUEDA RAG ABIERTA
    # --------------------------------------------------------

    def _vector_scores(self, question):
        """Coseno de la pregunta contra toda la colección (candidatos amplios)."""
        query_vector = self.model.encode(
            question,
            normalize_embeddings=True,
        )

        limit = max(
            1,
            min(len(self._corpus), self.MAX_VECTOR_CANDIDATES),
        )

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector.tolist(),
            limit=limit,
            with_payload=False,
        )

        return {
            point.id: float(point.score or 0.0)
            for point in response.points
        }

    def _resolve_scope(self, question, dashboard=None):
        """Combina el alcance detectado aquí con el tablero que llega del
        IntentParser (que compara nombres de página y alias literales)."""
        scope = self.detect_scope(question)

        if not dashboard:
            return scope

        hinted_groups = sorted({
            result.get("source_group") or ""
            for result in self._corpus
            if result.get("dashboard") == dashboard
        })

        if not hinted_groups:
            return scope

        hinted_tokens = set(tokenize(dashboard))

        if scope is not None:
            covered = set(hinted_groups) <= set(scope["source_groups"])
            # La detección por tokens gana si es al menos igual de específica
            # (p. ej. «tiempos de urgencias» → informe TIEMPOS URGENCIAS, no
            # la página URGENCIAS del Briefing).
            if covered or scope["weight"] >= len(hinted_tokens):
                return scope

        return {
            "kind": "page",
            "source_groups": hinted_groups,
            "pages": [dashboard],
            "matched_tokens": sorted(hinted_tokens),
            "weight": len(hinted_tokens),
        }

    def rank_documental(
        self,
        question,
        limit=5,
        dashboard=None,
        semantic_model=None,
        source_group=None,
        min_score=None,
    ):
        """Recuperación híbrida para preguntas documentales.

        1. Coseno contra toda la colección (candidatos amplios).
        2. Puntaje léxico BM25 normalizado con los términos de la pregunta
           (sin los que solo nombran el tablero) y bonificación por frases.
        3. Pesos por tipo de chunk según la intención (qué muestra / filtros /
           cómo se calcula / qué significa / técnica).
        4. Alcance: si la pregunta nombra un informe o página se busca dentro
           de él con umbral menor; si allí no hay evidencia, búsqueda global
           con el umbral normal (rechazo de lo irrelevante).
        5. Selección con diversidad de fuentes.
        """
        min_score = (
            self.DEFAULT_MIN_SCORE
            if min_score is None
            else float(min_score)
        )

        intent = detect_question_intent(question)
        scope = self._resolve_scope(question, dashboard)

        scope_tokens = set(scope["matched_tokens"]) if scope else set()

        # «qué es el perfil de morbilidad»: solo nombra el tablero.
        if (
            scope
            and not query_terms(question, exclude=scope_tokens)
            and intent in ("definition", "general")
        ):
            intent = "overview"

        question_terms = query_terms(question, intent=intent)
        residual_terms = query_terms(question, exclude=scope_tokens, intent=intent)

        vector_scores = self._vector_scores(question)

        def score_candidates(active_scope):
            candidates = []
            coverage = []
            groups = set(active_scope["source_groups"]) if active_scope else None
            focus_pages = set(active_scope.get("pages") or []) if active_scope else set()
            query_tokens = residual_terms if active_scope else question_terms

            for index, result in enumerate(self._corpus):
                if semantic_model and result.get("semantic_model") != semantic_model:
                    continue
                if source_group and result.get("source_group") != source_group:
                    continue
                if groups is not None and (result.get("source_group") or "") not in groups:
                    continue

                vector = vector_scores.get(result["id"], 0.0)
                lexical = self._lexical_index.score(index, query_tokens)

                if active_scope:
                    relevant = (
                        vector >= self.SCOPED_MIN_SCORE
                        or lexical >= self.SCOPED_MIN_LEXICAL
                    )
                else:
                    relevant = (
                        (
                            vector >= min_score
                            and (
                                lexical >= self.UNSCOPED_MIN_LEXICAL_SUPPORT
                                or (
                                    vector >= self.UNSCOPED_STRONG_VECTOR
                                    and (
                                        intent == "technical"
                                        or result.get("chunk_type") not in TECHNICAL_CHUNK_TYPES
                                    )
                                )
                            )
                        )
                        or (
                            lexical >= self.UNSCOPED_MIN_LEXICAL
                            and vector >= min_score - self.UNSCOPED_LEXICAL_MARGIN
                        )
                    )

                if not relevant:
                    continue

                bonus = 0.0
                if active_scope and result.get("dashboard") in focus_pages:
                    bonus = (
                        self.FOCUS_PAGE_BONUS
                        if active_scope["kind"] == "page"
                        else self.FOCUS_REPORT_PAGE_BONUS
                    )
                elif active_scope and active_scope["kind"] == "page":
                    bonus = -self.OTHER_PAGE_PENALTY

                final = (
                    self.VECTOR_WEIGHT * vector
                    + self.LEXICAL_WEIGHT * lexical
                    + type_prior(result.get("chunk_type"), intent)
                    + bonus
                )

                item = dict(result)
                item.update({
                    "score": round(max(0.0, min(final, 1.0)), 4),
                    "final_score": final,
                    "vector_score": round(vector, 4),
                    "lexical_score": round(lexical, 4),
                    "relevant": True,
                    "intent": intent,
                    "scope": (
                        {
                            "kind": active_scope["kind"],
                            "source_groups": list(active_scope["source_groups"]),
                            "pages": list(active_scope.get("pages") or []),
                        }
                        if active_scope
                        else None
                    ),
                })
                candidates.append(item)
                in_focus = bool(active_scope) and result.get("dashboard") in focus_pages
                matched = (
                    self._lexical_index.matched_terms(index, query_tokens)
                    if query_tokens
                    else set()
                )
                coverage.append((item, in_focus, matched))

            # Página nombrada: las demás páginas del informe solo entran si
            # aportan términos de la pregunta que la página no cubre (el
            # «semáforo» de auditoría de medicamentos está en otra página);
            # si no, solo meterían filtros/visuales ajenos.
            if active_scope and active_scope["kind"] == "page":
                focus_items = [entry for entry in coverage if entry[1]]
                if focus_items:
                    covered = set().union(*(entry[2] for entry in focus_items))
                    candidates = [
                        item
                        for item, in_focus, matched in coverage
                        if in_focus or (matched - covered)
                    ]

            candidates.sort(key=lambda item: item["final_score"], reverse=True)
            return candidates[:self.RERANK_POOL]

        candidates = score_candidates(scope)

        if scope is not None and not candidates:
            candidates = score_candidates(None)

        return select_diverse(
            candidates,
            limit=limit,
            technical=(intent == "technical"),
        )

    def search_general(
        self,
        question,
        limit=8,
        dashboard=None,
        semantic_model=None,
        source_group=None,
        min_score=None,
    ):
        """Búsqueda RAG abierta (híbrida).

        Solo devuelve evidencia que supera el umbral (relevant=True). Cada
        resultado trae score (híbrido, 0-1), vector_score y lexical_score.
        """
        if not getattr(self, "_corpus", None):
            return []

        return self.rank_documental(
            question=question,
            limit=limit,
            dashboard=dashboard,
            semantic_model=semantic_model,
            source_group=source_group,
            min_score=min_score,
        )

    # --------------------------------------------------------
    # CIERRE
    # --------------------------------------------------------

    def close(self):
        client = getattr(self, "client", None)

        if client is not None:
            try:
                client.close()
            finally:
                self.client = None


# ============================================================
# PRUEBA MANUAL
# ============================================================

if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    QDRANT_PATH = PROJECT_ROOT / "data" / "vector_db" / "qdrant"

    retriever = None

    try:
        retriever = HybridRetriever(QDRANT_PATH)

        question = "¿Qué información muestra el briefing hospitalario?"
        results = retriever.search_general(
            question=question,
            limit=8,
        )

        print("\nPregunta:", question)
        print("\nResultados:\n")

        for index, result in enumerate(results, start=1):
            print(f"RESULTADO {index}")
            print("Score:", round(result["score"], 4))
            print("Tipo:", result["chunk_type"])
            print("Tablero:", result["dashboard"])
            print("Grupo:", result["source_group"])
            print("Medida:", result["measure"])
            print("Texto:", result["text"][:500])
            print("-" * 70)

    finally:
        if retriever is not None:
            retriever.close()

import os
import re
import unicodedata
from pathlib import Path

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
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


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalize_text(text):
    text = str(text or "").lower().strip()
    text = "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if unicodedata.category(character) != "Mn"
    )
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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

        (
            self.dashboards,
            self.dashboard_aliases,
        ) = self._load_dashboard_metadata()

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

    def _load_dashboard_metadata(self):
        dashboards = set()
        aliases = {}

        for point in self._scroll_all():
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

    def refresh_metadata(self):
        (
            self.dashboards,
            self.dashboard_aliases,
        ) = self._load_dashboard_metadata()

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

    def detect_dashboard(self, question):
        question_normalized = normalize_text(question)
        candidates = []

        for alias, dashboard in self.dashboard_aliases.items():
            if alias and alias in question_normalized:
                candidates.append((
                    len(alias),
                    dashboard,
                ))

        if not candidates:
            return None

        # El alias más específico/largo tiene prioridad.
        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )
        return candidates[0][1]

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

    def search_general(
        self,
        question,
        limit=8,
        dashboard=None,
        semantic_model=None,
        source_group=None,
    ):
        if dashboard is None:
            dashboard = self.detect_dashboard(question)

        query_vector = self.model.encode(
            question,
            normalize_embeddings=True,
        )

        query_filter = self.build_filter(
            dashboard=dashboard,
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

        if query_filter is not None and not response.points:
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

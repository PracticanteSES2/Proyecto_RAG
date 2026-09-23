import re
import unicodedata
from pathlib import Path

from sentence_transformers import SentenceTransformer

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
)


MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

COLLECTION_NAME = (
    "tablero_de_atenciones_institucionales"
)


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalize_text(text):

    text = str(text).lower().strip()

    text = "".join(
        character
        for character in unicodedata.normalize(
            "NFD",
            text,
        )
        if unicodedata.category(character) != "Mn"
    )

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# RETRIEVER HÍBRIDO
# ============================================================

class HybridRetriever:

    def __init__(
        self,
        qdrant_path: Path,
    ):

        self.collection_name = (
            COLLECTION_NAME
        )

        self.model = SentenceTransformer(
            MODEL_NAME
        )

        self.client = QdrantClient(
            path=str(qdrant_path)
        )

        self.dashboards = (
            self._load_dashboards()
        )


    # --------------------------------------------------------
    # HELPERS DE PAYLOAD
    # --------------------------------------------------------

    def _payload_value(
        self,
        payload,
        key,
        default=None,
    ):
        """
        Soporta payload plano y metadata anidada.
        """

        payload = payload or {}

        metadata = (
            payload.get(
                "metadata",
                {},
            )
            or {}
        )

        value = payload.get(key)

        if value is None:
            value = metadata.get(
                key,
                default,
            )

        return value


    def _point_to_result(
        self,
        point,
        default_score=0.0,
    ):
        """
        Convierte un punto Qdrant a la estructura uniforme
        usada por el resto del proyecto.
        """

        payload = (
            point.payload
            or {}
        )

        score = getattr(
            point,
            "score",
            default_score,
        )

        if score is None:
            score = default_score

        return {
            "score": float(score),
            "chunk_type": self._payload_value(
                payload,
                "chunk_type",
            ),
            "dashboard": self._payload_value(
                payload,
                "dashboard",
            ),
            "table": self._payload_value(
                payload,
                "table",
            ),
            "measure": self._payload_value(
                payload,
                "measure",
            ),
            "semantic_model": self._payload_value(
                payload,
                "semantic_model",
            ),
            "source_file": self._payload_value(
                payload,
                "source_file",
            ),
            "text": self._payload_value(
                payload,
                "text",
                "",
            ) or "",
        }


    # --------------------------------------------------------
    # OBTENER TABLEROS DISPONIBLES
    # --------------------------------------------------------

    def _load_dashboards(self):

        points, _ = self.client.scroll(
            collection_name=
                self.collection_name,
            limit=10000,
            with_payload=True,
            with_vectors=False,
        )

        dashboards = set()

        for point in points:

            payload = (
                point.payload
                or {}
            )

            dashboard = self._payload_value(
                payload,
                "dashboard",
            )

            if dashboard:
                dashboards.add(
                    dashboard
                )

        return sorted(
            dashboards
        )


    # --------------------------------------------------------
    # DETECTAR TIPO DE PREGUNTA
    # --------------------------------------------------------

    def detect_chunk_type(
        self,
        question,
    ):

        question_normalized = (
            normalize_text(
                question
            )
        )

        filter_keywords = [
            "filtro",
            "filtros",
            "filtrar",
            "segmentar",
            "segmentadores",
        ]

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

    def detect_dashboard(
        self,
        question,
    ):

        question_normalized = (
            normalize_text(
                question
            )
        )

        candidates = []

        for dashboard in self.dashboards:

            normalized_dashboard = (
                normalize_text(
                    dashboard
                )
            )

            if (
                normalized_dashboard
                and normalized_dashboard
                in question_normalized
            ):
                candidates.append(
                    dashboard
                )

        if candidates:

            # Preferimos el nombre más específico/largo.
            candidates.sort(
                key=len,
                reverse=True,
            )

            return candidates[0]

        return None


    # --------------------------------------------------------
    # CREAR FILTROS QDRANT
    # --------------------------------------------------------

    def build_filter(
        self,
        dashboard=None,
        chunk_type=None,
    ):

        conditions = []

        if dashboard:

            conditions.append(
                FieldCondition(
                    key="dashboard",
                    match=MatchValue(
                        value=dashboard
                    ),
                )
            )

        if chunk_type:

            conditions.append(
                FieldCondition(
                    key="chunk_type",
                    match=MatchValue(
                        value=chunk_type
                    ),
                )
            )

        if not conditions:
            return None

        return Filter(
            must=conditions
        )


    # --------------------------------------------------------
    # TODAS LAS MEDIDAS DE UN DASHBOARD
    # --------------------------------------------------------

    def get_measures_by_dashboard(
        self,
        dashboard,
        limit=500,
    ):
        """
        Recupera todas las medidas indexadas de un dashboard.
        No depende de similitud vectorial.
        """

        points, _ = self.client.scroll(
            collection_name=
                self.collection_name,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        results = []

        for point in points:

            result = self._point_to_result(
                point,
                default_score=0.0,
            )

            if (
                result.get("chunk_type")
                != "measure"
            ):
                continue

            if (
                result.get("dashboard")
                != dashboard
            ):
                continue

            results.append(
                result
            )

        return results


    # --------------------------------------------------------
    # BÚSQUEDA GLOBAL DE CANDIDATOS DE MÉTRICA
    # --------------------------------------------------------

    def search_measure_candidates(
        self,
        question,
        limit=20,
        dashboard=None,
    ):
        """
        Busca medidas por similitud semántica.

        Si se conoce el dashboard, limita la búsqueda a ese dashboard.
        Si no se conoce, busca entre TODAS las medidas indexadas.

        Esta función permite resolver preguntas numéricas aunque el
        usuario no conozca el nombre técnico del tablero.
        """

        query_vector = self.model.encode(
            question,
            normalize_embeddings=True,
        )

        query_filter = self.build_filter(
            dashboard=dashboard,
            chunk_type="measure",
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
    ):
        """
        Búsqueda estructurada para componentes que sí conocen
        el dashboard y/o tipo de chunk esperado.

        Se conserva para MetricResolver y consultas específicas.
        """

        if dashboard is None:
            dashboard = self.detect_dashboard(
                question
            )

        if chunk_type is None:
            chunk_type = self.detect_chunk_type(
                question
            )

        print(
            "\nInterpretación de consulta"
        )

        print(
            "Dashboard detectado:",
            dashboard,
        )

        print(
            "Tipo esperado:",
            chunk_type,
        )

        query_vector = self.model.encode(
            question,
            normalize_embeddings=True,
        )

        query_filter = self.build_filter(
            dashboard=dashboard,
            chunk_type=chunk_type,
        )

        response = self.client.query_points(
            collection_name=
                self.collection_name,
            query=
                query_vector.tolist(),
            query_filter=
                query_filter,
            limit=limit,
            with_payload=True,
        )

        # Fallback global si los filtros fueron demasiado estrictos.
        if not response.points:

            response = self.client.query_points(
                collection_name=
                    self.collection_name,
                query=
                    query_vector.tolist(),
                limit=limit,
                with_payload=True,
            )

        return [
            self._point_to_result(
                point
            )
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
    ):
        """
        Búsqueda semántica abierta para preguntas documentales.

        NO obliga a un chunk_type concreto. Puede recuperar:
        - dashboard_overview
        - measure
        - table_context
        - calculated_column
        - cualquier otro tipo indexado

        Si se conoce el dashboard, se utiliza como restricción.
        Si no se pasa, intenta detectarlo desde la pregunta.
        """

        if dashboard is None:
            dashboard = self.detect_dashboard(
                question
            )

        query_vector = self.model.encode(
            question,
            normalize_embeddings=True,
        )

        query_filter = self.build_filter(
            dashboard=dashboard,
            chunk_type=None,
        )

        response = self.client.query_points(
            collection_name=
                self.collection_name,
            query=
                query_vector.tolist(),
            query_filter=
                query_filter,
            limit=limit,
            with_payload=True,
        )

        # Si un dashboard detectado resultó demasiado restrictivo,
        # hacemos fallback global para no dejar la pregunta sin contexto.
        if (
            query_filter is not None
            and not response.points
        ):

            response = self.client.query_points(
                collection_name=
                    self.collection_name,
                query=
                    query_vector.tolist(),
                limit=limit,
                with_payload=True,
            )

        return [
            self._point_to_result(
                point
            )
            for point in response.points
        ]


    # --------------------------------------------------------
    # CIERRE
    # --------------------------------------------------------

    def close(self):

        client = getattr(
            self,
            "client",
            None,
        )

        if client is not None:

            try:
                client.close()

            finally:
                self.client = None


# ============================================================
# PRUEBA MANUAL
# ============================================================

if __name__ == "__main__":

    PROJECT_ROOT = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    QDRANT_PATH = (
        PROJECT_ROOT
        / "data"
        / "vector_db"
        / "qdrant"
    )

    retriever = None

    try:

        retriever = HybridRetriever(
            QDRANT_PATH
        )

        question = (
            "¿Para qué sirve la proyección "
            "de cirugías?"
        )

        results = retriever.search_general(
            question=question,
            limit=8,
        )

        print(
            "\nPregunta:",
            question,
        )

        print(
            "\nResultados:\n"
        )

        for index, result in enumerate(
            results,
            start=1,
        ):

            print(
                f"RESULTADO {index}"
            )

            print(
                "Score:",
                round(
                    result["score"],
                    4,
                ),
            )

            print(
                "Tipo:",
                result["chunk_type"],
            )

            print(
                "Tablero:",
                result["dashboard"],
            )

            print(
                "Medida:",
                result["measure"],
            )

            print(
                "Texto:",
                (
                    result["text"][:500]
                    if result["text"]
                    else ""
                ),
            )

            print(
                "-" * 70
            )

    finally:

        if retriever is not None:
            retriever.close()


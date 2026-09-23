import json
from pathlib import Path

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

COLLECTION_NAME = (
    "tablero_de_atenciones_institucionales"
)


# ============================================================
# UTILIDADES
# ============================================================

def load_chunks(path: Path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ============================================================
# CREAR ÍNDICE VECTORIAL
# ============================================================

def build_vector_index(
    chunks_file: Path,
    qdrant_path: Path
):

    print("Cargando chunks...")

    chunks = load_chunks(
        chunks_file
    )

    print(
        f"Chunks encontrados: {len(chunks)}"
    )

    # --------------------------------------------------------
    # CARGAR MODELO DE EMBEDDINGS
    # --------------------------------------------------------

    print(
        "\nCargando modelo de embeddings..."
    )

    model = SentenceTransformer(
        MODEL_NAME
    )

    vector_size = (
        model.get_sentence_embedding_dimension()
    )

    print(
        "Dimensión del embedding:",
        vector_size
    )

    # --------------------------------------------------------
    # QDRANT LOCAL
    # --------------------------------------------------------

    qdrant_path.mkdir(
        parents=True,
        exist_ok=True
    )

    client = QdrantClient(
        path=str(qdrant_path)
    )

    # Para el desarrollo recreamos el índice.
    # Más adelante haremos actualizaciones incrementales.

    if client.collection_exists(
        COLLECTION_NAME
    ):

        print(
            "\nEliminando colección anterior..."
        )

        client.delete_collection(
            collection_name=COLLECTION_NAME
        )

    client.create_collection(

        collection_name=
            COLLECTION_NAME,

        vectors_config=
            VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            )
    )

    print(
        "Colección creada:",
        COLLECTION_NAME
    )

    # --------------------------------------------------------
    # GENERAR EMBEDDINGS
    # --------------------------------------------------------

    texts = [
        chunk["text"]
        for chunk in chunks
    ]

    print(
        "\nGenerando embeddings..."
    )

    embeddings = model.encode(

        texts,

        batch_size=32,

        show_progress_bar=True,

        normalize_embeddings=True
    )

    print(
        "Embeddings generados:",
        embeddings.shape
    )

    # --------------------------------------------------------
    # CREAR PUNTOS QDRANT
    # --------------------------------------------------------

    points = []

    for chunk, embedding in zip(
        chunks,
        embeddings
    ):

        payload = {

            "text":
                chunk["text"],

            "chunk_type":
                chunk["chunk_type"],

            **chunk.get(
                "metadata",
                {}
            )
        }

        point = PointStruct(

            id=chunk["id"],

            vector=
                embedding.tolist(),

            payload=payload
        )

        points.append(point)

    # --------------------------------------------------------
    # GUARDAR EN QDRANT
    # --------------------------------------------------------

    print(
        "\nGuardando vectores en Qdrant..."
    )

    client.upsert(

        collection_name=
            COLLECTION_NAME,

        points=points
    )

    collection_info = (
        client.get_collection(
            COLLECTION_NAME
        )
    )

    print(
        "\n============================"
    )

    print(
        "INDEXACIÓN FINALIZADA"
    )

    print(
        "============================"
    )

    print(
        "Chunks indexados:",
        len(points)
    )

    print(
        "Colección:",
        COLLECTION_NAME
    )

    print(
        "Base vectorial:",
        qdrant_path
    )

    return client


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    PROJECT_ROOT = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    CHUNKS_FILE = (
        PROJECT_ROOT
        / "data"
        / "rag"
        / "tablero_de_atenciones_institucionales_chunks.json"
    )

    QDRANT_PATH = (
        PROJECT_ROOT
        / "data"
        / "vector_db"
        / "qdrant"
    )

    build_vector_index(
        CHUNKS_FILE,
        QDRANT_PATH
    )
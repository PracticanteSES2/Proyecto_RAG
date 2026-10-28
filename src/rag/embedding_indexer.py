import json
import os
from pathlib import Path

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)


MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

COLLECTION_NAME = os.getenv(
    "QDRANT_COLLECTION_NAME",
    "gestion_clinica_rag",
)


# ============================================================
# UTILIDADES
# ============================================================

def load_chunks(path: Path):
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("El archivo de chunks debe contener una lista JSON.")

    return data


def _chunk_source_group(chunk):
    return (
        chunk.get("metadata", {}).get("source_group")
        or "__legacy__"
    )


def _ensure_collection(client, collection_name, vector_size):
    if client.collection_exists(collection_name):
        return False

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=vector_size,
            distance=Distance.COSINE,
        ),
    )

    return True


def _existing_source_groups(client, collection_name, page_size=512):
    """Devuelve los source_group presentes en la colección (scroll paginado)."""
    groups = set()
    offset = None

    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            limit=page_size,
            offset=offset,
            with_payload=["source_group"],
            with_vectors=False,
        )

        for point in points:
            group = (point.payload or {}).get("source_group")
            if group:
                groups.add(group)

        if offset is None:
            break

    return groups


def stale_source_groups(existing_groups, current_groups):
    """Grupos que están en Qdrant pero ya no existen en el corpus actual."""
    current = set(current_groups)
    return sorted(set(existing_groups) - current)


def _delete_source_group(client, collection_name, source_group):
    selector = FilterSelector(
        filter=Filter(
            must=[
                FieldCondition(
                    key="source_group",
                    match=MatchValue(value=source_group),
                )
            ]
        )
    )

    client.delete(
        collection_name=collection_name,
        points_selector=selector,
        wait=True,
    )


def chunk_payload(chunk):
    """Payload plano del punto en Qdrant (texto, tipo y metadatos)."""
    metadata = dict(chunk.get("metadata", {}) or {})
    metadata.setdefault(
        "source_group",
        _chunk_source_group(chunk),
    )

    return {
        "text": chunk["text"],
        "chunk_type": chunk["chunk_type"],
        **metadata,
    }


def _upsert_chunks(client, collection_name, chunks, embeddings, batch_size=64):
    """Inserta los chunks con sus embeddings (payload plano, como siempre)."""
    total_upserted = 0

    for start in range(0, len(chunks), batch_size):
        batch_chunks = chunks[start:start + batch_size]
        batch_embeddings = embeddings[start:start + batch_size]

        points = []

        for chunk, embedding in zip(batch_chunks, batch_embeddings):
            payload = chunk_payload(chunk)

            vector = (
                embedding.tolist()
                if hasattr(embedding, "tolist")
                else list(embedding)
            )

            points.append(
                PointStruct(
                    id=chunk["id"],
                    vector=vector,
                    payload=payload,
                )
            )

        client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )

        total_upserted += len(points)

    return total_upserted


def replace_source_group_points(
    client,
    collection_name,
    source_group,
    chunks,
    embeddings,
    vector_size,
    batch_size=64,
):
    """Reemplaza en Qdrant SOLO los puntos de un source_group (los demás
    grupos no se tocan). Los embeddings deben estar calculados antes de
    llamar: si fallan, la colección queda intacta."""
    if any(_chunk_source_group(chunk) != source_group for chunk in chunks):
        raise ValueError(
            f"Todos los chunks deben ser del grupo «{source_group}»."
        )

    _ensure_collection(client, collection_name, vector_size)
    _delete_source_group(client, collection_name, source_group)
    return _upsert_chunks(
        client,
        collection_name,
        chunks,
        embeddings,
        batch_size,
    )


def source_group_payloads(client, collection_name, source_group, page_size=512):
    """{id: payload} de los puntos de un source_group (sin vectores)."""
    selector = Filter(
        must=[
            FieldCondition(
                key="source_group",
                match=MatchValue(value=source_group),
            )
        ]
    )
    payloads = {}
    offset = None

    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=selector,
            limit=page_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        for point in points:
            payloads[str(point.id)] = point.payload or {}

        if offset is None:
            break

    return payloads


def update_source_group_points(
    client,
    collection_name,
    source_group,
    chunks,
    existing_payloads,
    changed_chunks,
    changed_embeddings,
    batch_size=64,
):
    """Actualización incremental de un source_group ya indexado.

    - changed_chunks (texto nuevo o distinto): se insertan con su embedding.
    - Mismo texto y otros metadatos (p. ej. source_hash): solo se reescribe
      el payload; el vector se conserva.
    - Puntos del grupo que ya no están en `chunks`: se eliminan.
    Los demás grupos no se tocan.
    """
    from qdrant_client.models import PointIdsList

    if any(_chunk_source_group(chunk) != source_group for chunk in chunks):
        raise ValueError(
            f"Todos los chunks deben ser del grupo «{source_group}»."
        )

    current_ids = {str(chunk["id"]) for chunk in chunks}
    changed_ids = {str(chunk["id"]) for chunk in changed_chunks}

    stale = sorted(set(existing_payloads) - current_ids)
    if stale:
        client.delete(
            collection_name=collection_name,
            points_selector=PointIdsList(points=stale),
            wait=True,
        )

    payload_only = 0
    for chunk in chunks:
        chunk_id = str(chunk["id"])
        if chunk_id in changed_ids:
            continue
        payload = chunk_payload(chunk)
        if existing_payloads.get(chunk_id) != payload:
            client.overwrite_payload(
                collection_name=collection_name,
                payload=payload,
                points=[chunk_id],
                wait=True,
            )
            payload_only += 1

    upserted = _upsert_chunks(
        client,
        collection_name,
        changed_chunks,
        changed_embeddings,
        batch_size,
    )

    return {
        "upserted": upserted,
        "payload_only": payload_only,
        "deleted": len(stale),
    }


# ============================================================
# INDEXACIÓN
# ============================================================

def build_vector_index(
    chunks_file: Path,
    qdrant_path: Path,
    collection_name=None,
    batch_size=64,
    replace_source_groups=True,
    full_rebuild=False,
):
    """
    Indexa el corpus sin borrar toda la colección.

    Estrategia:
      1. Genera embeddings antes de tocar datos existentes.
      2. Para cada source_group presente en el archivo, elimina únicamente
         los puntos anteriores de ese grupo.
      3. Inserta la versión actual de sus chunks.

    Así agregar BRIEFING HOSPITALARIO no destruye los demás grupos.

    Con full_rebuild=True (reconstrucción completa del corpus) también se
    eliminan los source_group que ya no están en los chunks actuales, para no
    dejar documentación obsoleta en la colección.
    """
    chunks_file = Path(chunks_file)
    qdrant_path = Path(qdrant_path)
    collection_name = collection_name or COLLECTION_NAME

    print("Cargando chunks...")
    chunks = load_chunks(chunks_file)
    print("Chunks encontrados:", len(chunks))

    if not chunks:
        raise ValueError("No hay chunks para indexar.")

    ids = [chunk.get("id") for chunk in chunks]
    if any(not chunk_id for chunk_id in ids):
        raise ValueError("Todos los chunks deben tener un id.")

    if len(ids) != len(set(ids)):
        raise ValueError("Hay IDs de chunks duplicados.")

    texts = [str(chunk.get("text") or "").strip() for chunk in chunks]
    if any(not text for text in texts):
        raise ValueError("Todos los chunks deben tener texto no vacío.")

    print("\nCargando modelo de embeddings...")
    model = SentenceTransformer(MODEL_NAME)
    vector_size = model.get_sentence_embedding_dimension()
    print("Dimensión del embedding:", vector_size)

    # Primero calculamos los embeddings. Si esto falla, Qdrant queda intacto.
    print("\nGenerando embeddings...")
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    print("Embeddings generados:", embeddings.shape)

    qdrant_path.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(qdrant_path))

    try:
        created = _ensure_collection(
            client,
            collection_name,
            vector_size,
        )

        if created:
            print("\nColección creada:", collection_name)
        else:
            print("\nColección existente:", collection_name)

        source_groups = sorted({
            _chunk_source_group(chunk)
            for chunk in chunks
        })

        if replace_source_groups:
            print("\nActualizando grupos documentales:")
            for source_group in source_groups:
                print("  -", source_group)
                _delete_source_group(
                    client,
                    collection_name,
                    source_group,
                )

        removed_groups = []

        if full_rebuild and not created:
            removed_groups = stale_source_groups(
                _existing_source_groups(client, collection_name),
                source_groups,
            )

            if removed_groups:
                print("\nEliminando grupos obsoletos:")
                for source_group in removed_groups:
                    print("  -", source_group)
                    _delete_source_group(
                        client,
                        collection_name,
                        source_group,
                    )

        print("\nGuardando vectores en Qdrant...")

        total_upserted = _upsert_chunks(
            client,
            collection_name,
            chunks,
            embeddings,
            batch_size,
        )

        collection_info = client.get_collection(collection_name)

        print("\n============================")
        print("INDEXACIÓN FINALIZADA")
        print("============================")
        print("Chunks indexados:", total_upserted)
        print("Grupos actualizados:", len(source_groups))
        print("Colección:", collection_name)
        print("Base vectorial:", qdrant_path)

        return {
            "status": "success",
            "chunks_indexed": total_upserted,
            "source_groups": source_groups,
            "removed_source_groups": removed_groups,
            "collection": collection_name,
            "collection_info": str(collection_info),
        }

    finally:
        client.close()


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

    CHUNKS_FILE = (
        PROJECT_ROOT
        / "data"
        / "rag"
        / "knowledge_chunks.json"
    )

    QDRANT_PATH = (
        PROJECT_ROOT
        / "data"
        / "vector_db"
        / "qdrant"
    )

    build_vector_index(
        CHUNKS_FILE,
        QDRANT_PATH,
    )

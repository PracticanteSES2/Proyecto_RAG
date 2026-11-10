"""
Reindexación del RAG para un solo tablero después de aprobar un cambio.

Vivía en src/docs_md/indexacion.py. Está en src/catalogo/ porque orquesta la construcción (ingestion,
semantic, rag) y esa construcción lee el formato de src/docs_md: en docs_md formaba los ciclos
«docs_md ↔ ingestion» y «docs_md ↔ semantic» (docs/ARQUITECTURA.md, fase 4). `_reindexar` está
partida en sus etapas (extracción, normalización, catálogo, chunks, embeddings, Qdrant, archivos).

CONTRATO:

    resultado = reindexar_grupo(source_group, qdrant_client=None)
    # -> {"source_group", "documentos", "chunks", "segundos", "errores": [...],
    #     "tableros", "embebidos", "docx_ignorados", "avisos", "etapas",
    #     "retriever_actualizado"}

- Regenera los derivados SOLO de ese grupo (data/processed/<grupo> y
  data/semantic_documents/<grupo>), reemplaza sus tableros en el catálogo
  semántico, reconstruye knowledge_chunks.json y reemplaza en Qdrant solo los
  puntos de ese source_group. Solo se calculan embeddings de los chunks del
  grupo que cambiaron (incremental); los demás grupos no se tocan.
- Todo se prepara en un directorio temporal: si la extracción, la
  normalización o los embeddings fallan, ni los archivos ni Qdrant cambian.
- Qdrant local admite un solo cliente por carpeta. Si la app ya lo tiene
  abierto se reutiliza: se le pasa `qdrant_client`, o se detecta solo el
  HybridRetriever abierto en este proceso sobre la misma carpeta (ver
  `cliente_qdrant_de_la_app`). En ese caso también se reutiliza su modelo de
  embeddings y, al terminar, se recarga su corpus en memoria
  (`refresh_metadata`) para que la búsqueda léxica vea el texto nuevo.
- Rutas: derivados en <project_root>/data/... (por defecto el data/ del
  proyecto). Las páginas .md se leen de `md_root`; si no se indica: de
  repositorio.raiz_documentos() (DOCS_MD_ROOT o docs_tableros/) cuando no se
  pasa project_root, y si no de <project_root>/data/raw. El manifest se busca junto a los .md y si no en
  data/raw/<grupo>/manifest.json. Las pruebas pasan project_root (y md_root)
  para no tocar el data/ real.

Nota para la app: QueryPlanBuilder guarda en memoria data/semantic_documents
(`_semantic_documents_cache`, `_page_index_cache`,
`_metric_documentation_cache`); tras reindexar conviene borrar esas cachés o
reconstruir el sistema para que el plan de consulta vea la documentación nueva.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

from src.comun.json_io import escribir_json, leer_json
from src.comun.registro import mensajes_de
from src.comun.rutas import RAIZ_PROYECTO

PROJECT_ROOT = RAIZ_PROYECTO

# Dos reindexaciones a la vez (dos sesiones de Streamlit) se pisarían los
# archivos derivados: se serializan.
_LOCK = threading.Lock()
# Loggers de la construcción: su progreso se ve con verbose=True (ver src.comun.registro.mensajes_de).
_CONSTRUCTORES = ("src.ingestion", "src.semantic", "src.rag")
_MODELO = None


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

def rutas_datos(project_root: str | Path | None = None, md_root: str | Path | None = None) -> dict:
    """Rutas de entrada y derivados del RAG (parametrizables para pruebas)."""
    data = (Path(project_root) if project_root is not None else PROJECT_ROOT) / "data"
    raw = data / "raw"
    if md_root is not None:
        md = Path(md_root)
    elif project_root is None:
        from src.docs_md.repositorio import raiz_documentos

        md = raiz_documentos()
    else:
        md = raw
    return {
        "proyecto": data.parent,
        "raw": raw,
        "md": md,
        "processed": data / "processed",
        "semantic_documents": data / "semantic_documents",
        "catalogo": data / "catalog" / "semantic_knowledge.json",
        "chunks": data / "rag" / "knowledge_chunks.json",
        "qdrant": data / "vector_db" / "qdrant",
    }


def carpetas_del_grupo(raw_dir: Path, source_group: str, md_root: Path | None = None) -> list[str]:
    """Nombres de las carpetas del grupo en data/raw y en la raíz md (por
    nombre de carpeta o por el source_group de su manifest)."""
    from src.ingestion.document_parser import folder_source_group, markdown_manifest

    raw_dir = Path(raw_dir)
    nombres = []
    for base in dict.fromkeys([raw_dir, Path(md_root) if md_root is not None else raw_dir]):
        if not base.is_dir():
            continue
        for carpeta in sorted(p for p in base.iterdir() if p.is_dir()):
            manifest = markdown_manifest(carpeta.name, base, raw_dir)
            if source_group in (carpeta.name, folder_source_group(carpeta, manifest)):
                if carpeta.name not in nombres:
                    nombres.append(carpeta.name)
    return nombres


# ---------------------------------------------------------------------------
# Cliente Qdrant y modelo de la app
# ---------------------------------------------------------------------------

def retriever_de_la_app(qdrant_path: str | Path | None = None):
    """HybridRetriever abierto en este proceso sobre la carpeta Qdrant (el que
    crea app.build_system y guarda st.cache_resource); None si no hay."""
    from src.rag.retriever import active_retriever

    return active_retriever(qdrant_path if qdrant_path is not None else rutas_datos()["qdrant"])


def cliente_qdrant_de_la_app(qdrant_path: str | Path | None = None):
    """Cliente Qdrant que ya usa la app (retriever.client) o None. Úselo en vez
    de abrir otro: Qdrant local rechaza un segundo cliente sobre la carpeta."""
    retriever = retriever_de_la_app(qdrant_path)
    return getattr(retriever, "client", None) if retriever is not None else None


def _raiz_proyecto_de_la_app(retriever=None):
    """Raíz de datos que usa la app en este proceso: RAG_PROJECT_ROOT o la que
    se deduce del retriever abierto (<raíz>/data/vector_db/qdrant). Así la
    reindexación escribe donde lee el chat aunque la app corra con otra raíz
    (p. ej. el arnés tests/realistic). None si no se puede saber."""
    env = os.getenv("RAG_PROJECT_ROOT", "").strip()
    if env:
        return Path(env)
    if retriever is None:
        modulo = sys.modules.get("src.rag.retriever")
        retriever = modulo.active_retriever() if modulo is not None else None
    ruta = getattr(retriever, "qdrant_path", None) if retriever is not None else None
    if ruta:
        qdrant = Path(ruta).resolve()
        if qdrant.name == "qdrant" and qdrant.parent.name == "vector_db" and qdrant.parents[1].name == "data":
            return qdrant.parents[2]
    return None


def _modelo_embeddings():
    """Mismo modelo que embedding_indexer (se carga una sola vez por proceso)."""
    global _MODELO
    if _MODELO is None:
        from sentence_transformers import SentenceTransformer

        from src.rag.embedding_indexer import MODEL_NAME

        _MODELO = SentenceTransformer(MODEL_NAME)
    return _MODELO


def _dimension(embedder, embeddings) -> int:
    for nombre in ("get_embedding_dimension", "get_sentence_embedding_dimension"):
        obtener = getattr(embedder, nombre, None)
        if callable(obtener):
            valor = obtener()
            if valor:
                return int(valor)
    return len(embeddings[0])


# ---------------------------------------------------------------------------
# Catálogo y archivos
# ---------------------------------------------------------------------------

def _leer_json(ruta: Path, defecto):
    return leer_json(ruta, defecto)


def _escribir_json(datos, ruta: Path) -> None:
    """Escritura atómica (temporal + reemplazo)."""
    escribir_json(datos, ruta, atomico=True)


def _reemplazar_del_grupo(items: list, nuevos: list, source_group: str) -> list:
    """Quita los elementos del grupo y pone los nuevos donde estaba el primero
    (así el orden del catálogo no cambia entre reindexaciones)."""
    items = list(items or [])
    primero = next(
        (i for i, item in enumerate(items) if item.get("source_group") == source_group),
        len(items),
    )
    antes = [item for item in items[:primero] if item.get("source_group") != source_group]
    despues = [item for item in items[primero:] if item.get("source_group") != source_group]
    return antes + list(nuevos) + despues


def fusionar_catalogo(existente: dict | None, del_grupo: dict, source_group: str) -> dict:
    """Catálogo semántico global con los tableros y fuentes del grupo renovados."""
    existente = existente or {}
    fuentes = _reemplazar_del_grupo(existente.get("sources"), del_grupo.get("sources", []), source_group)
    tableros = _reemplazar_del_grupo(existente.get("dashboards"), del_grupo.get("dashboards", []), source_group)
    workspaces = {f.get("workspace") for f in fuentes if f.get("workspace")}
    modelos = {f.get("semantic_model") for f in fuentes if f.get("semantic_model")}
    return {
        **existente,
        "schema_version": existente.get("schema_version", 2),
        "workspace": next(iter(workspaces)) if len(workspaces) == 1 else None,
        "semantic_model": next(iter(modelos)) if len(modelos) == 1 else None,
        "sources": fuentes,
        "dashboards": tableros,
    }


def _reemplazar_carpeta(origen: Path, destino: Path) -> None:
    if destino.exists():
        shutil.rmtree(destino)
    if origen.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(origen, destino)


# ---------------------------------------------------------------------------
# Reindexación
# ---------------------------------------------------------------------------

def reindexar_grupo(
    source_group,
    qdrant_client=None,
    *,
    project_root: str | Path | None = None,
    md_root: str | Path | None = None,
    embedder=None,
    retriever=None,
    collection_name: str | None = None,
    batch_size: int = 64,
    verbose: bool = True,
    incremental: bool = True,
) -> dict:
    """Regenera e indexa solo el grupo documental `source_group`.

    qdrant_client: cliente ya abierto (el de la app). Si es None se usa el del
        HybridRetriever abierto sobre la misma carpeta y, si no hay, se abre
        uno propio que se cierra al terminar.
    embedder: objeto con encode(textos, ...) (SentenceTransformer o un doble
        de pruebas). Si es None: el modelo del retriever o el de embedding_indexer.
    retriever: HybridRetriever a refrescar al terminar (se detecta solo).
    project_root / md_root: rutas (ver rutas_datos); las pruebas las fijan.
    incremental: solo se calculan embeddings de los chunks nuevos o con texto
        distinto a lo que ya hay en Qdrant (ids deterministas); los demás
        conservan su vector. False = se borra y reinserta todo el grupo.
    verbose: False silencia los mensajes de consola del pipeline.
    """
    inicio = time.perf_counter()
    resultado = {
        "source_group": source_group,
        "documentos": 0,
        "tableros": 0,
        "chunks": 0,
        "segundos": 0.0,
        "errores": [],
        "avisos": [],
        "docx_ignorados": [],
        "etapas": {},
        "retriever_actualizado": False,
        "embebidos": 0,
    }
    errores = resultado["errores"]
    etapas = resultado["etapas"]
    marca = [time.perf_counter()]

    def etapa(nombre):
        ahora = time.perf_counter()
        etapas[nombre] = round(ahora - marca[0], 3)
        marca[0] = ahora

    def terminar():
        resultado["segundos"] = round(time.perf_counter() - inicio, 3)
        return resultado

    if project_root is None:
        project_root = _raiz_proyecto_de_la_app(retriever)
        if project_root is not None and md_root is None and os.getenv("DOCS_MD_ROOT", "").strip():
            from src.docs_md.repositorio import raiz_documentos

            md_root = raiz_documentos()

    salida = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(io.StringIO())
    with _LOCK, salida, mensajes_de(_CONSTRUCTORES, visibles=verbose):
        try:
            _reindexar(
                source_group, qdrant_client, rutas_datos(project_root, md_root), embedder, retriever,
                collection_name, batch_size, resultado, etapa, incremental,
            )
        except Exception as exc:  # el resultado siempre vuelve con el error
            errores.append(f"{type(exc).__name__}: {exc}")
    return terminar()


def _reindexar(source_group, qdrant_client, rutas, embedder, retriever, collection_name,
               batch_size, resultado, etapa, incremental=True):
    from src.rag.embedding_indexer import COLLECTION_NAME

    errores = resultado["errores"]
    carpetas = carpetas_del_grupo(rutas["raw"], source_group, rutas["md"])
    if not carpetas:
        errores.append(
            f"No hay documentación en {rutas['raw']} ni en {rutas['md']} para el grupo «{source_group}»."
        )
        return

    # Cliente y retriever de la app (si existen) antes de calcular embeddings:
    # así se reutiliza también su modelo.
    retriever, qdrant_client = _cliente_y_retriever(rutas, retriever, qdrant_client)
    if collection_name is None:
        collection_name = getattr(retriever, "collection_name", None) or COLLECTION_NAME

    with tempfile.TemporaryDirectory(prefix="reindexar_") as tmp:
        tmp = Path(tmp)
        processed_tmp = tmp / "processed"
        semantic_tmp = tmp / "semantic_documents"

        if not _extraer(source_group, rutas, processed_tmp, resultado, etapa):
            return
        if not _normalizar(processed_tmp, semantic_tmp, errores, etapa):
            return
        catalogo = _catalogo_del_grupo(source_group, rutas, semantic_tmp, tmp / "catalogo_grupo.json",
                                       resultado, etapa)
        if catalogo is None:
            return

        # 4. Chunks: el archivo completo se reconstruye; se embeben solo los del grupo.
        from src.rag.chunk_builder import build_chunks

        chunks = build_chunks(catalogo)
        del_grupo_chunks = [
            chunk for chunk in chunks
            if (chunk.get("metadata") or {}).get("source_group") == source_group
        ]
        resultado["chunks"] = len(del_grupo_chunks)
        etapa("chunks")

        destino = _Destino(qdrant_client, collection_name, source_group, batch_size)
        if not _indexar(destino, rutas, del_grupo_chunks, embedder, retriever, incremental, resultado, etapa):
            return
        etapa("qdrant")

        # 7. Archivos derivados (solo las carpetas del grupo + catálogo y chunks).
        for carpeta in carpetas:
            _reemplazar_carpeta(processed_tmp / carpeta, rutas["processed"] / carpeta)
            _reemplazar_carpeta(semantic_tmp / carpeta, rutas["semantic_documents"] / carpeta)
        _escribir_json(catalogo, rutas["catalogo"])
        _escribir_json(chunks, rutas["chunks"])
        etapa("archivos")

    # 8. El retriever de la app recarga su corpus (parte léxica y alcance).
    if retriever is not None and getattr(retriever, "client", None) is not None:
        refrescar = getattr(retriever, "refresh_metadata", None)
        if callable(refrescar):
            refrescar()
            resultado["retriever_actualizado"] = True
    etapa("retriever")


def _cliente_y_retriever(rutas, retriever, qdrant_client):
    """(retriever, cliente) de la app: el retriever abierto sobre la misma carpeta se reutiliza solo si
    usa el mismo cliente que se pasó; sin cliente, se toma el del retriever."""
    if retriever is None:
        retriever = retriever_de_la_app(rutas["qdrant"])
        if retriever is not None and qdrant_client is not None and retriever.client is not qdrant_client:
            retriever = None
    if qdrant_client is None and retriever is not None:
        qdrant_client = retriever.client
    return retriever, qdrant_client


def _extraer(source_group, rutas, processed_tmp, resultado, etapa) -> bool:
    """1. Extracción (solo el grupo; .md manda sobre .docx). False si hay que parar."""
    from src.ingestion.document_parser import process_all_documents

    errores = resultado["errores"]
    estadisticas = process_all_documents(
        rutas["raw"], processed_tmp, source_group=source_group, md_root=rutas["md"],
    )
    resultado["docx_ignorados"] = estadisticas.get("ignored_docx", [])
    resultado["documentos"] = estadisticas.get("documents_processed", 0)
    for error in estadisticas.get("errors") or []:
        errores.append(f"{error.get('file')}: {error.get('error_type')}: {error.get('error')}")
    for archivo in sorted(processed_tmp.rglob("*.json")):
        datos = _leer_json(archivo, {})
        for aviso in datos.get("format_warnings") or []:
            resultado["avisos"].append(f"{datos.get('source_file')}: {aviso}")
    etapa("extraccion")
    if errores:
        return False
    if not resultado["documentos"]:
        errores.append(f"El grupo «{source_group}» no tiene documentos .md ni .docx.")
        return False
    return True


def _normalizar(processed_tmp, semantic_tmp, errores, etapa) -> bool:
    """2. Normalización. False si hubo errores."""
    from src.semantic.document_normalizer import normalize_all_documents

    normalizacion = normalize_all_documents(processed_tmp, semantic_tmp)
    for error in normalizacion.get("errors") or []:
        errores.append(f"{error.get('file')}: {error.get('error_type')}: {error.get('error')}")
    etapa("normalizacion")
    return not errores


def _catalogo_del_grupo(source_group, rutas, semantic_tmp, salida, resultado, etapa):
    """3. Catálogo semántico: los tableros del grupo reemplazan a los anteriores. None si hay que parar."""
    from src.semantic.semantic_merge import build_semantic_catalog

    del_grupo = build_semantic_catalog(
        technical_catalog_path=None,
        semantic_documents_dir=semantic_tmp,
        output_path=salida,
        project_root=rutas["proyecto"],
    )
    ajenos = sorted({
        tablero.get("source_group")
        for tablero in del_grupo.get("dashboards", [])
        if tablero.get("source_group") != source_group
    } - {None})
    if ajenos:
        resultado["errores"].append(
            f"La carpeta del grupo «{source_group}» declara otros grupos: {', '.join(ajenos)}."
        )
        return None
    catalogo = fusionar_catalogo(_leer_json(rutas["catalogo"], {}), del_grupo, source_group)
    resultado["tableros"] = len(del_grupo.get("dashboards", []))
    etapa("catalogo")
    return catalogo


class _Destino:
    """Colección de Qdrant donde se escriben los puntos del grupo."""

    def __init__(self, cliente, coleccion, source_group, batch_size):
        self.cliente = cliente
        self.coleccion = coleccion
        self.source_group = source_group
        self.batch_size = batch_size


def _indexar(destino, rutas, del_grupo_chunks, embedder, retriever, incremental, resultado, etapa) -> bool:
    """5-6. Embeddings y Qdrant. Abre (y cierra) un cliente propio si la app no tiene uno. False si no se
    pudo abrir Qdrant."""
    propio = None
    if destino.cliente is None:
        rutas["qdrant"].mkdir(parents=True, exist_ok=True)
        try:
            from qdrant_client import QdrantClient

            propio = destino.cliente = QdrantClient(path=str(rutas["qdrant"]))
        except Exception as exc:
            resultado["errores"].append(
                "No se pudo abrir Qdrant en "
                f"{rutas['qdrant']} ({type(exc).__name__}: {exc}). Si la app lo tiene "
                "abierto en otro proceso, reindexe desde la app (pasando su cliente)."
            )
            return False
    try:
        existentes, a_embeber, embeddings, embedder = _embeber(
            destino, del_grupo_chunks, embedder, retriever, incremental)
        resultado["embebidos"] = len(a_embeber)
        etapa("embeddings")
        _guardar_puntos(destino, del_grupo_chunks, existentes, a_embeber, embeddings, embedder)
    finally:
        if propio is not None:
            propio.close()
    return True


def _embeber(destino, del_grupo_chunks, embedder, retriever, incremental):
    """5. Embeddings (antes de escribir en Qdrant: si fallan, nada cambia). Incremental: solo los chunks
    nuevos o con texto distinto (los ids son deterministas); los demás conservan su vector.
    -> (existentes o None, a_embeber, embeddings, embedder)."""
    from src.rag.embedding_indexer import source_group_payloads

    existentes = None
    if incremental and destino.cliente.collection_exists(destino.coleccion):
        existentes = source_group_payloads(destino.cliente, destino.coleccion, destino.source_group)
    if existentes is None:
        a_embeber = del_grupo_chunks
    else:
        a_embeber = [
            chunk for chunk in del_grupo_chunks
            if (existentes.get(str(chunk["id"])) or {}).get("text") != chunk["text"]
        ]
    if a_embeber and embedder is None:
        embedder = getattr(retriever, "model", None) or _modelo_embeddings()
    textos = [str(chunk.get("text") or "").strip() for chunk in a_embeber]
    embeddings = (
        embedder.encode(
            textos,
            batch_size=destino.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        if textos
        else []
    )
    return existentes, a_embeber, embeddings, embedder


def _guardar_puntos(destino, del_grupo_chunks, existentes, a_embeber, embeddings, embedder) -> None:
    """6. Qdrant: solo los puntos del grupo."""
    from src.rag.embedding_indexer import replace_source_group_points, update_source_group_points

    if existentes is not None:
        update_source_group_points(
            destino.cliente,
            destino.coleccion,
            destino.source_group,
            del_grupo_chunks,
            existentes,
            a_embeber,
            embeddings,
            batch_size=destino.batch_size,
        )
    elif a_embeber:
        replace_source_group_points(
            destino.cliente,
            destino.coleccion,
            destino.source_group,
            a_embeber,
            embeddings,
            _dimension(embedder, embeddings),
            batch_size=destino.batch_size,
        )

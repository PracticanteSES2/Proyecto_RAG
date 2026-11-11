"""Reindexación de la documentación de un tablero, segura con el chat en uso.

Hallazgos (ver specs/013-documentacion-web/plan.md):

- Qdrant local admite UN cliente por carpeta y el motor ya lo tiene abierto:
  hay que reindexar en el proceso dueño del motor y con SU retriever (cliente
  Qdrant + MiniLM), como hacía Streamlit (`interfaz.reindexar`).
- `reindexar_grupo` reescribe los puntos del grupo y termina con
  `retriever.refresh_metadata()`, que reemplaza el corpus en memoria que usan
  los turnos. Para que ningún turno vea un índice a medias, se retienen TODAS
  las instancias de la piscina mientras dura (los turnos en curso terminan
  primero; los nuevos esperan en la cola, como cualquier turno).
- Después se invalida la huella de la caché de respuestas: una respuesta
  cacheada con la documentación anterior no se vuelve a servir.
- Con el motor en otro proceso (Redis + `python -m backend.worker`) la API no
  es dueña de Qdrant: no se reindexa desde aquí (`IndiceNoDisponible`).
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path

MENSAJE_EXTERNO = ("El cambio quedó guardado, pero el asistente corre en un proceso aparte y desde aquí no se puede "
                   "actualizar su buscador. Reinicia el trabajador del asistente (python -m backend.worker) para "
                   "que use el texto nuevo.")
MENSAJE_ARRANCANDO = ("El cambio quedó guardado, pero el asistente todavía está arrancando. Reintenta la "
                      "reindexación en un momento.")


class IndiceNoDisponible(Exception):
    """No se puede reindexar desde este proceso (el mensaje es para el usuario)."""


def _reindexar_real(source_group, qdrant_client=None, **opciones) -> dict:
    from src.docs_md.indexacion import reindexar_grupo

    return reindexar_grupo(source_group, qdrant_client, **opciones)


class CoordinadorIndice:
    """`reindexar(grupo)` con la piscina del motor embebido retenida."""

    def __init__(self, embebido: bool, trabajador: Callable[[], object | None], raiz_datos: Path, raiz_docs: Path,
                 reindexar: Callable[..., dict] | None = None):
        self.embebido = embebido
        self._trabajador = trabajador
        self.raiz_datos = Path(raiz_datos)
        self.raiz_docs = Path(raiz_docs)
        self._reindexar = reindexar or _reindexar_real

    def reindexar(self, grupo: str) -> dict:
        """Resultado de `reindexar_grupo` + `cliente_compartido`. Lanza
        IndiceNoDisponible si este proceso no es dueño del motor."""
        if not self.embebido:
            raise IndiceNoDisponible(MENSAJE_EXTERNO)
        trabajador = self._trabajador()
        piscina = getattr(trabajador, "piscina", None)
        if piscina is None:
            raise IndiceNoDisponible(MENSAJE_ARRANCANDO)
        with ExitStack() as pila:
            instancias = [pila.enter_context(piscina.tomar()) for _ in range(piscina.total)]
            retriever = next((i.retriever for i in instancias if getattr(i, "retriever", None) is not None), None)
            cliente = getattr(retriever, "client", None)
            resultado = dict(self._reindexar(grupo, cliente, retriever=retriever, project_root=self.raiz_datos,
                                             md_root=self.raiz_docs, verbose=False) or {})
        resultado["cliente_compartido"] = cliente is not None
        huella = getattr(trabajador, "huella", None)
        if huella is not None and callable(getattr(huella, "invalidar", None)):
            huella.invalidar()
        return resultado


def mensaje_resultado(resultado: dict, tablero: str) -> tuple[str, str]:
    """(estado, mensaje) para quien aprobó el cambio."""
    errores = [str(e) for e in resultado.get("errores") or []]
    if errores:
        return "error", "La reindexación falló: " + " ".join(errores)
    partes = []
    if resultado.get("documentos") is not None:
        partes.append(f"{resultado['documentos']} documentos")
    if resultado.get("chunks") is not None:
        partes.append(f"{resultado['chunks']} fragmentos")
    if resultado.get("segundos") is not None:
        partes.append(f"{float(resultado['segundos']):.1f} s")
    detalle = f" ({', '.join(partes)})" if partes else ""
    conexion = ("con la conexión del chat" if resultado.get("cliente_compartido")
                else "con una conexión propia (el chat no estaba abierto)")
    return "lista", f"El asistente ya usa el texto nuevo: se reindexó {tablero}{detalle} {conexion}."

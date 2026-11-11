"""El motor (QueryEngine de src/) dentro del backend.

Hallazgos que dan forma a este módulo (ver specs/006-api-backend/plan.md):

- El estado de cada conversación NO vive en el motor: viaja en una
  `EstadoConversacion` (src/chatbot/estado_conversacion.py, spec 008) que se
  pasa con `process(texto, sesion=estado)` y se guarda como JSON firmado
  (`SesionExplicita` + `SerializadorEstado`). El estado del turno en curso es
  por hilo (contextvars).
  → Aun así, una instancia atiende UN turno a la vez (`PiscinaMotores`):
  algunos colaboradores compartidos del motor todavía guardan temporales de la
  llamada en atributos (specs/008-memoria-por-sesion/research.md §5).
- Qdrant local admite un solo cliente por carpeta y por proceso; MiniLM pesa.
  → Todas las instancias del proceso comparten UN retriever, protegido por un
  candado (`RecuperadorConCandado`; la búsqueda tarda milisegundos).
- El proveedor de Power BI (ADOMD) tiene conexiones y oyentes por turno.
  → Uno por instancia.

El cableado del motor es `src/chatbot/fabrica.py` (el mismo de app.py).
"""
from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import logging
import queue
import secrets
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

LOG = logging.getLogger(__name__)

@dataclass
class InstanciaMotor:
    engine: object
    conversation_manager: object
    formatter: object
    nombre: str = "motor-1"
    estado_medgemma: dict = field(default_factory=dict)
    estado_powerbi: dict = field(default_factory=dict)
    estado_indice: dict = field(default_factory=dict)
    # HybridRetriever del motor (Qdrant + MiniLM): la reindexación de la
    # documentación lo reutiliza (Qdrant local admite un solo cliente).
    retriever: object | None = None


# ======================================================================
# Estado de conversación: sesión explícita y serialización firmada
# ======================================================================

def sin_contexto(estado: dict | None) -> bool:
    """True si la conversación (`EstadoConversacion.to_dict()`) no tiene nada que
    pueda cambiar la interpretación del siguiente mensaje: ni pendientes, ni
    dato previo, ni memoria, ni aclaración de tablero abierta."""
    if not estado:
        return True
    if any(valor is not None for valor in (estado.get("pendiente") or {}).values()):
        return False
    if estado.get("seguimiento") is not None or (estado.get("memoria") or {}).get("turnos"):
        return False
    return not bool((estado.get("intencion") or {}).get("awaiting_clarification"))


def _llamar(funcion, *args, on_token=None, **kwargs):
    """Pasa `on_token` solo si el motor lo acepta (streaming de la redacción:
    agente/ux-espera); así el backend ya queda listo para el evento `token`."""
    if on_token is not None:
        try:
            if "on_token" in inspect.signature(funcion).parameters:
                return funcion(*args, on_token=on_token, **kwargs)
        except (TypeError, ValueError):
            pass
    return funcion(*args, **kwargs)


class SesionExplicita:
    """Cómo viaja el estado de la conversación hasta el motor (contrato:
    specs/008-memoria-por-sesion/contracts/sesion-conversacion.md). El estado
    es el dict JSON de `EstadoConversacion.to_dict()`; el motor lo recibe con
    `sesion=`, cierra el turno solo y no guarda nada de la conversación."""

    @staticmethod
    def sin_contexto(estado) -> bool:
        return sin_contexto(estado)

    def ejecutar(self, instancia: InstanciaMotor, estado, texto: str, opcion: dict | None = None,
                 on_token=None) -> tuple[dict, dict]:
        """(result, estado nuevo). Si el motor lanza, la excepción sube y el
        estado previo de la conversación queda intacto (se trabaja sobre una
        copia restaurada del dict)."""
        from src.chatbot.estado_conversacion import EstadoConversacion

        try:
            sesion = EstadoConversacion.from_dict(estado) if estado else EstadoConversacion()
        except ValueError:
            LOG.warning("Estado de conversación incompatible: la conversación sigue sin contexto")
            sesion = EstadoConversacion()
        motor = instancia.engine
        if opcion is not None:
            result = _llamar(motor.select_clarification_option, opcion["id_original"], opcion["texto"],
                             on_token=on_token, sesion=sesion)
        else:
            result = _llamar(motor.process, texto, on_token=on_token, sesion=sesion)
        if not isinstance(result, dict):
            raise TypeError(f"el motor devolvió {type(result).__name__}")
        return result, sesion.to_dict()


class SerializadorEstado:
    """JSON (EstadoConversacion.to_dict) firmado con HMAC-SHA256: un estado
    manipulado en Redis se descarta y la conversación sigue sin contexto."""

    def __init__(self, secreto: str | None):
        if not secreto:
            LOG.warning("BACKEND_SECRETO no definido: se usa uno aleatorio de este proceso; "
                        "el contexto de las conversaciones no sobrevive a un reinicio del trabajador")
            secreto = secrets.token_hex(32)
        self._clave = hashlib.sha256(secreto.encode("utf-8")).digest()

    def a_bytes(self, estado: dict | None) -> bytes | None:
        if estado is None:
            return None
        cuerpo = json.dumps(estado, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return hmac.new(self._clave, cuerpo, hashlib.sha256).digest() + cuerpo

    def de_bytes(self, datos: bytes | None) -> dict | None:
        if not datos or len(datos) <= 32:
            return None
        firma, cuerpo = bytes(datos[:32]), bytes(datos[32:])
        if not hmac.compare_digest(firma, hmac.new(self._clave, cuerpo, hashlib.sha256).digest()):
            LOG.warning("Estado de conversación con firma inválida: se descarta")
            return None
        try:
            estado = json.loads(cuerpo.decode("utf-8"))
        except ValueError:
            LOG.warning("Estado de conversación ilegible: se descarta", exc_info=True)
            return None
        return estado if isinstance(estado, dict) else None


# ======================================================================
# Piscina de instancias
# ======================================================================

class PiscinaMotores:
    """N instancias; cada una atiende un turno a la vez."""

    def __init__(self, instancias: list[InstanciaMotor]):
        if not instancias:
            raise ValueError("la piscina necesita al menos una instancia del motor")
        self.instancias = list(instancias)
        self._libres: queue.Queue = queue.Queue()
        for instancia in self.instancias:
            self._libres.put(instancia)

    @property
    def total(self) -> int:
        return len(self.instancias)

    @property
    def libres(self) -> int:
        return self._libres.qsize()

    @property
    def ocupadas(self) -> int:
        return self.total - self.libres

    @contextmanager
    def tomar(self):
        instancia = self._libres.get()
        try:
            yield instancia
        finally:
            self._libres.put(instancia)

    @property
    def principal(self) -> InstanciaMotor:
        return self.instancias[0]


# ======================================================================
# Retriever compartido entre instancias
# ======================================================================

class _ConCandado:
    """Proxy que serializa las llamadas a los métodos del objeto envuelto."""

    def __init__(self, real, candado):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_candado", candado)

    def __getattr__(self, nombre):
        valor = getattr(self._real, nombre)
        if callable(valor) and not isinstance(valor, type):
            candado = self._candado

            def llamada(*args, **kwargs):
                with candado:
                    return valor(*args, **kwargs)

            return llamada
        return valor

    def __setattr__(self, nombre, valor):
        setattr(self._real, nombre, valor)


class RecuperadorConCandado(_ConCandado):
    """HybridRetriever compartido: también su modelo MiniLM (`.model.encode`,
    que usa la similitud del portero)."""

    def __getattr__(self, nombre):
        if nombre == "model":
            modelo = getattr(self._real, "model", None)
            return _ConCandado(modelo, self._candado) if modelo is not None else None
        return super().__getattr__(nombre)


# ======================================================================
# Fábrica real (src/chatbot/fabrica.py, la misma que usa app.py)
# ======================================================================

def construir_instancia_real(raiz: Path, nombre: str = "motor-1", retriever=None) -> InstanciaMotor:
    """Arma el motor real (lento: MiniLM, Qdrant, conexión a Power BI, MedGemma).
    Importa src.* aquí dentro: la API (otro proceso) nunca carga estas piezas."""
    from src.chatbot.fabrica import construir_sistema
    from src.chatbot.response_formatter import ResponseFormatter

    sistema = construir_sistema(Path(raiz), retriever=retriever)
    recuperador = sistema.retriever
    indice = {"status": "ready" if getattr(recuperador, "client", None) is not None else "unavailable",
              "coleccion": getattr(recuperador, "collection_name", None)}
    return InstanciaMotor(
        engine=sistema.engine, conversation_manager=sistema.conversation_manager, formatter=ResponseFormatter(),
        nombre=nombre, estado_medgemma=dict(sistema.medgemma_status or {}),
        estado_powerbi=dict(sistema.powerbi_connection or {}), estado_indice=indice, retriever=recuperador,
    )


def construir_piscina_real(raiz: Path, instancias: int = 1) -> PiscinaMotores:
    """Con una instancia, igual que app.py. Con varias, el retriever (Qdrant +
    MiniLM) se abre una vez y TODAS lo usan a través del mismo candado."""
    if instancias <= 1:
        return PiscinaMotores([construir_instancia_real(raiz, nombre="motor-1")])
    from src.chatbot.fabrica import rutas_por_defecto
    from src.rag.retriever import HybridRetriever

    compartido = RecuperadorConCandado(HybridRetriever(rutas_por_defecto(raiz)["qdrant_path"]), threading.RLock())
    return PiscinaMotores([
        construir_instancia_real(raiz, nombre=f"motor-{numero}", retriever=compartido)
        for numero in range(1, instancias + 1)
    ])

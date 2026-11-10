"""El motor (QueryEngine de src/) dentro del backend.

Hallazgos que dan forma a este módulo (ver specs/006-api-backend/plan.md):

- `QueryEngine` NO es seguro entre hilos: guarda en atributos el estado del
  turno (`_trace`, `progress_listener`, …) y el de la conversación
  (contrapreguntas pendientes, último dato para seguimientos, memoria).
  `ConversationManager` también (`state`, `candidate_dashboards`).
  → Una instancia atiende UN turno a la vez (`PiscinaMotores`) y el estado de
  cada conversación se saca y se restaura alrededor de cada turno
  (`capturar_estado` / `restaurar_estado`).
- Qdrant local admite un solo cliente por carpeta y por proceso; MiniLM pesa.
  → Todas las instancias del proceso comparten UN retriever, protegido por un
  candado (`RecuperadorConCandado`; la búsqueda tarda milisegundos).
- El proveedor de Power BI (ADOMD) tiene conexiones y oyentes por turno.
  → Uno por instancia.

El cableado del motor es `src/chatbot/fabrica.py` (el mismo de app.py).
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import inspect
import logging
import pickle
import queue
import secrets
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

LOG = logging.getLogger(__name__)

# Estado de la CONVERSACIÓN que el motor guarda en atributos (se restaura por turno).
ATRIBUTOS_CONVERSACION = (
    "_pending_master_metric",
    "_pending_query_plan",
    "_pending_dashboard_clarification",
    "_deferred_context_message",
    "_applying_deferred",
    "_last_success",
    "_range_choice",
    "_turn_interpretation",
    "conversation_memory",
)
# Estado del TURNO: se limpia antes de cada turno.
ATRIBUTOS_TURNO = ("_trace", "_intent_llm_turn", "_turn_message", "last_reasoning")
_PENDIENTES = ("_pending_master_metric", "_pending_query_plan", "_pending_dashboard_clarification",
               "_deferred_context_message", "_applying_deferred")


@dataclass
class InstanciaMotor:
    engine: object
    conversation_manager: object
    formatter: object
    nombre: str = "motor-1"
    estado_medgemma: dict = field(default_factory=dict)
    estado_powerbi: dict = field(default_factory=dict)
    estado_indice: dict = field(default_factory=dict)


# ======================================================================
# Estado de conversación: captura, restauración y serialización firmada
# ======================================================================

def capturar_estado(instancia: InstanciaMotor) -> dict:
    motor = instancia.engine
    estado = {nombre: copy.deepcopy(motor.__dict__.get(nombre)) for nombre in ATRIBUTOS_CONVERSACION}
    gestor = instancia.conversation_manager
    if gestor is not None:
        estado["_cm_state"] = copy.deepcopy(getattr(gestor, "state", None))
        estado["_cm_candidatos"] = copy.deepcopy(getattr(gestor, "candidate_dashboards", None))
    return estado


_LIMPIAR_SIEMPRE = ATRIBUTOS_TURNO + ("_range_choice", "_applying_deferred", "_turn_interpretation")
_ESTADO_GESTOR = (("_cm_state", "state"), ("_cm_candidatos", "candidate_dashboards"))


def _reiniciar_todo(instancia: InstanciaMotor) -> None:
    """Como «Nueva conversación»: sin pendientes, sin memoria, sin turno a medias."""
    motor, gestor = instancia.engine, instancia.conversation_manager
    if callable(getattr(gestor, "reset", None)):
        gestor.reset()
    reiniciar = getattr(motor, "reset", None)
    if callable(reiniciar):
        try:
            reiniciar(full=True)
        except TypeError:
            reiniciar()
    for nombre in (n for n in _LIMPIAR_SIEMPRE if n in motor.__dict__):
        setattr(motor, nombre, None)


def restaurar_estado(instancia: InstanciaMotor, estado: dict | None) -> None:
    """Deja la instancia como si siempre hubiera atendido solo esta conversación."""
    _reiniciar_todo(instancia)
    if not estado:
        return
    motor, gestor = instancia.engine, instancia.conversation_manager
    for nombre in (n for n in ATRIBUTOS_CONVERSACION if n in estado):
        if estado[nombre] is not None or nombre in motor.__dict__:
            setattr(motor, nombre, copy.deepcopy(estado[nombre]))
    for clave, atributo in _ESTADO_GESTOR:
        if gestor is not None and estado.get(clave) is not None:
            setattr(gestor, atributo, copy.deepcopy(estado[clave]))


def sin_contexto(estado: dict | None) -> bool:
    """True si la conversación no tiene nada que pueda cambiar la interpretación
    del siguiente mensaje (ni pendientes, ni dato previo, ni memoria)."""
    if not estado:
        return True
    if any(estado.get(nombre) is not None for nombre in _PENDIENTES + ("_last_success", "_range_choice")):
        return False
    memoria = estado.get("conversation_memory")
    try:
        if memoria is not None and len(memoria) > 0:
            return False
    except TypeError:
        return False
    cm_state = estado.get("_cm_state")
    return not bool(getattr(cm_state, "awaiting_clarification", False))


def reiniciar_si_termino(result: dict, instancia: InstanciaMotor) -> None:
    """Puerto de app.py::reset_if_finished: el contexto de contrapregunta solo se
    conserva mientras está pendiente (reset() sin full conserva a propósito el
    último dato numérico para seguimientos)."""
    if result.get("status") == "needs_clarification":
        return
    gestor = instancia.conversation_manager
    if gestor is not None and callable(getattr(gestor, "reset", None)):
        gestor.reset()
    reiniciar = getattr(instancia.engine, "reset", None)
    if callable(reiniciar):
        reiniciar()


def _llamar(funcion, *args, on_token=None):
    """Pasa `on_token` solo si el motor lo acepta (streaming de la redacción:
    agente/ux-espera); así el backend ya queda listo para el evento `token`."""
    if on_token is not None:
        try:
            if "on_token" in inspect.signature(funcion).parameters:
                return funcion(*args, on_token=on_token)
        except (TypeError, ValueError):
            pass
    return funcion(*args)


class SesionPorAtributos:
    """Cómo viaja el estado de la conversación hasta el motor — versión ACTUAL:
    restaurar los atributos de la instancia antes del turno y capturarlos
    después (el motor guarda la conversación en atributos).

    PUNTO DE UNIÓN con agente/memoria-sesion: cuando QueryEngine acepte
    `process(pregunta, sesion=estado)`, otro adaptador con estos mismos tres
    métodos pasará la sesión explícita y devolverá la nueva; el resto del
    backend (almacén, caché, turnos) no cambia."""

    @staticmethod
    def sin_contexto(estado) -> bool:
        return sin_contexto(estado)

    def ejecutar(self, instancia: InstanciaMotor, estado, texto: str, opcion: dict | None = None,
                 on_token=None) -> tuple[dict, dict]:
        """(result, estado nuevo). Si el motor lanza, la excepción sube y el
        estado previo de la conversación queda intacto."""
        restaurar_estado(instancia, estado)
        motor = instancia.engine
        if opcion is not None:
            result = _llamar(motor.select_clarification_option, opcion["id_original"], opcion["texto"],
                             on_token=on_token)
        else:
            result = _llamar(motor.process, texto, on_token=on_token)
        if not isinstance(result, dict):
            raise TypeError(f"el motor devolvió {type(result).__name__}")
        try:
            reiniciar_si_termino(result, instancia)
        except Exception:
            LOG.warning("reset tras el turno falló", exc_info=True)
        return result, capturar_estado(instancia)


class SerializadorEstado:
    """pickle firmado con HMAC-SHA256: un estado manipulado en Redis nunca se
    deserializa (se descarta y la conversación sigue sin contexto)."""

    def __init__(self, secreto: str | None):
        if not secreto:
            LOG.warning("BACKEND_SECRETO no definido: se usa uno aleatorio de este proceso; "
                        "el contexto de las conversaciones no sobrevive a un reinicio del trabajador")
            secreto = secrets.token_hex(32)
        self._clave = hashlib.sha256(secreto.encode("utf-8")).digest()

    def a_bytes(self, estado: dict | None) -> bytes | None:
        if estado is None:
            return None
        cuerpo = pickle.dumps(estado, protocol=pickle.HIGHEST_PROTOCOL)
        return hmac.new(self._clave, cuerpo, hashlib.sha256).digest() + cuerpo

    def de_bytes(self, datos: bytes | None) -> dict | None:
        if not datos or len(datos) <= 32:
            return None
        firma, cuerpo = bytes(datos[:32]), bytes(datos[32:])
        if not hmac.compare_digest(firma, hmac.new(self._clave, cuerpo, hashlib.sha256).digest()):
            LOG.warning("Estado de conversación con firma inválida: se descarta")
            return None
        try:
            estado = pickle.loads(cuerpo)  # noqa: S301 - firmado por este backend
        except Exception:
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
        estado_powerbi=dict(sistema.powerbi_connection or {}), estado_indice=indice,
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

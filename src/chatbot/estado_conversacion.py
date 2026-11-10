"""
Estado de UNA conversación (spec 008, contrato en
specs/008-memoria-por-sesion/contracts/sesion-conversacion.md).

El motor (`QueryEngine`) es un servicio compartido por todas las conversaciones
(catálogos, índices, modelos, cachés de dominio). Lo que depende de la
conversación vive aquí y lo guarda quien conversa: Streamlit en
`st.session_state`, el backend en memoria o Redis (serializado con `to_json`).

- memoria: últimos turnos (ConversationMemory);
- seguimiento: última consulta numérica exitosa («¿y en urología?»);
- pendiente: contrapreguntas y planes abiertos (indicador, plan, tablero) y el
  mensaje de contexto aplazado hasta el botón;
- intencion y tableros_candidatos: estado del ConversationManager.

`sesion_activa()` devuelve la sesión del turno en curso (contextvars: cada hilo
o tarea ve la suya). La fija el motor al empezar un turno con `sesion=`.
"""
import contextvars
import copy
import dataclasses
import json
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime

from src.chatbot.conversation_memory import DEFAULT_MAX_TURNS, ConversationMemory
from src.chatbot.conversation_state import ConversationState

VERSION_ESTADO = 1

_SESION_ACTIVA = contextvars.ContextVar("sesion_conversacion_activa", default=None)

# Campos de la sesión que el motor lee y escribe (clave de `pendiente` en el JSON).
_PENDIENTES = {
    "indicador": "indicador_pendiente",
    "plan": "plan_pendiente",
    "tablero": "tablero_pendiente",
    "mensaje_aplazado": "mensaje_aplazado",
}


def sesion_activa():
    """EstadoConversacion del turno en curso en este contexto, o None (modo legado)."""
    return _SESION_ACTIVA.get()


@contextmanager
def en_sesion(sesion):
    """Fija `sesion` como la activa mientras dure el bloque (None = modo legado)."""
    token = _SESION_ACTIVA.set(sesion)
    try:
        yield sesion
    finally:
        _SESION_ACTIVA.reset(token)


class EstadoConversacion:
    """Estado mutable de una conversación. Un turno a la vez por objeto (`candado`)."""

    def __init__(self, id=None, max_turnos=DEFAULT_MAX_TURNS):
        self.id = str(id) if id else uuid.uuid4().hex
        self.memoria = ConversationMemory(max_turns=max_turnos)
        self.seguimiento = None
        self.indicador_pendiente = None
        self.plan_pendiente = None
        self.tablero_pendiente = None
        self.mensaje_aplazado = None
        self.intencion = ConversationState()
        self.tableros_candidatos = []
        # Transitorios (no se serializan).
        self.ultimo_razonamiento = None
        self.candado = threading.Lock()

    def __repr__(self):
        return f"EstadoConversacion(id={self.id!r}, turnos={len(self.memoria)})"

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def olvidar_contrapreguntas(self):
        """Lo que hacía `QueryEngine.reset()`: contrapreguntas, planes y mensaje aplazado."""
        for campo in _PENDIENTES.values():
            setattr(self, campo, None)

    def cerrar_turno(self, resultado):
        """Lo que hacía `reset_if_finished` de app.py: tras una respuesta final se
        olvidan las contrapreguntas y el estado del analizador de intención; la
        memoria y el seguimiento se conservan."""
        if isinstance(resultado, dict) and resultado.get("status") == "needs_clarification":
            return
        self.olvidar_contrapreguntas()
        self.intencion.clear()
        self.tableros_candidatos = []

    def reiniciar(self):
        """«Nueva conversación»: olvida todo (el id se conserva)."""
        self.olvidar_contrapreguntas()
        self.seguimiento = None
        self.memoria.clear()
        self.intencion.clear()
        self.tableros_candidatos = []
        self.ultimo_razonamiento = None

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self):
        """Dict JSON puro (ver el contrato). Lanza TypeError si algún valor no se puede representar."""
        return {
            "version": VERSION_ESTADO,
            "id": self.id,
            "memoria": {"max_turnos": self.memoria.max_turns, "turnos": _a_json(self.memoria.turns())},
            "seguimiento": _a_json(self.seguimiento),
            "pendiente": {clave: _a_json(getattr(self, campo)) for clave, campo in _PENDIENTES.items()},
            "intencion": _a_json(dataclasses.asdict(self.intencion)),
            "tableros_candidatos": _a_json(list(self.tableros_candidatos or [])),
        }

    @classmethod
    def from_dict(cls, datos):
        version = datos.get("version") if isinstance(datos, dict) else None
        if version != VERSION_ESTADO:
            raise ValueError(f"estado de conversación incompatible (versión {version!r}, se espera {VERSION_ESTADO})")
        try:
            return cls._desde_datos(datos)
        except (TypeError, AttributeError, KeyError) as error:
            raise ValueError(f"estado de conversación corrupto: {error}") from error

    @classmethod
    def _desde_datos(cls, datos):
        memoria = datos.get("memoria") or {}
        estado = cls(id=datos.get("id"), max_turnos=memoria.get("max_turnos") or DEFAULT_MAX_TURNS)
        estado.memoria.load(_de_json(memoria.get("turnos") or []))
        estado.seguimiento = _de_json(datos.get("seguimiento"))
        pendiente = datos.get("pendiente") or {}
        for clave, campo in _PENDIENTES.items():
            setattr(estado, campo, _de_json(pendiente.get(clave)))
        estado.intencion = _intencion_desde(_de_json(datos.get("intencion") or {}))
        estado.tableros_candidatos = list(_de_json(datos.get("tableros_candidatos") or []))
        return estado

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, texto):
        try:
            datos = json.loads(texto)
        except (TypeError, ValueError) as error:
            raise ValueError(f"estado de conversación ilegible: {error}") from error
        return cls.from_dict(datos)

    def copia(self):
        """Copia independiente (mismo id), sin el candado ni el razonamiento."""
        return EstadoConversacion.from_dict(copy.deepcopy(self.to_dict()))


def _intencion_desde(datos):
    campos = {f.name for f in dataclasses.fields(ConversationState)}
    return ConversationState(**{k: v for k, v in datos.items() if k in campos})


# ----------------------------------------------------------------------
# Codificación JSON con tipos (tuplas, conjuntos, fechas, claves no texto)
# ----------------------------------------------------------------------

_ETIQUETAS = frozenset(("__tupla__", "__conjunto__", "__fecha__", "__fecha_hora__", "__dict__"))


def _dict_a_json(valor, ruta):
    if all(isinstance(clave, str) for clave in valor) and not (_ETIQUETAS & set(valor)):
        return {clave: _a_json(v, f"{ruta}.{clave}") for clave, v in valor.items()}
    return {"__dict__": [[_a_json(k, ruta), _a_json(v, f"{ruta}[{k!r}]")] for k, v in valor.items()]}


def _conjunto_a_json(valor, ruta):
    elementos = [_a_json(v, ruta) for v in valor]
    return {"__conjunto__": sorted(elementos, key=lambda v: json.dumps(v, sort_keys=True))}


# Orden importante: datetime es subclase de date.
_CODIFICADORES = (
    (dict, _dict_a_json),
    (list, lambda valor, ruta: [_a_json(v, f"{ruta}[{i}]") for i, v in enumerate(valor)]),
    (tuple, lambda valor, ruta: {"__tupla__": [_a_json(v, f"{ruta}[{i}]") for i, v in enumerate(valor)]}),
    ((set, frozenset), _conjunto_a_json),
    (datetime, lambda valor, ruta: {"__fecha_hora__": valor.isoformat()}),
    (date, lambda valor, ruta: {"__fecha__": valor.isoformat()}),
)

_DECODIFICADORES = {
    "__tupla__": lambda contenido: tuple(_de_json(v) for v in contenido),
    "__conjunto__": lambda contenido: {_de_json(v) for v in contenido},
    "__fecha__": date.fromisoformat,
    "__fecha_hora__": datetime.fromisoformat,
    "__dict__": lambda contenido: {_de_json(k): _de_json(v) for k, v in contenido},
}


def _a_json(valor, ruta="$"):
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor
    for tipo, codificar in _CODIFICADORES:
        if isinstance(valor, tipo):
            return codificar(valor, ruta)
    raise TypeError(f"valor no serializable en {ruta}: {type(valor).__name__}")


def _de_json(valor):
    if isinstance(valor, list):
        return [_de_json(v) for v in valor]
    if not isinstance(valor, dict):
        return valor
    if len(valor) == 1:
        etiqueta, contenido = next(iter(valor.items()))
        decodificar = _DECODIFICADORES.get(etiqueta)
        if decodificar is not None:
            return decodificar(contenido)
    return {clave: _de_json(v) for clave, v in valor.items()}

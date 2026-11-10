"""Progreso del turno para el usuario final: etapas reales, frases humanas y
eventos serializables a JSON (independiente del framework de interfaz).

El motor (QueryEngine) avisa lo que hace con eventos de su traza
(`set_progress_listener`): {"kind": "activity"|"step", "title", "t", "lines"}.
Esos títulos son técnicos («Consultando Power BI (CIRUGIAS)», «Query Plan»,
«MedGemma»...). Este módulo los traduce a eventos para la interfaz, sin
segundos visibles, nombres de modelos, DAX ni pasos internos:

    progreso  {"etapa": str, "frase": str, "t": float}
    espera    {"nivel": int, "frase": str, "t": float}
    token     {"texto": str}
    cola      {"posicion": int, "en_curso": int}     (solo modo diagnóstico)
    aviso     {"motivo": str, "texto": str}

`t` (segundos desde el inicio del turno) es para ordenar y medir; la interfaz
NO lo muestra. El backend (FastAPI) envía cada evento por SSE con
`event: <evento>` y `data: <JSON de datos>`; el contrato completo está en
specs/003-progreso-chat/contracts/eventos.md.

Decisión del usuario (specs/009-experiencia-espera): la espera se siente como
trabajo sobre SU pregunta. Ningún texto habla de colas, filas, turnos,
posiciones, otras consultas, el servidor ni saturación: esperar un hueco del
LLM o el turno de otro NO cambia la etapa visible, y la frase rota despacio
(`ROTACION_S`) para que nunca se vea congelada.

Uso típico en el backend, por turno:

    traductor = TraductorProgreso(recientes=memoria_de_la_sesion)
    enviar(traductor.iniciar())
    engine.set_progress_listener(lambda e: enviar(traductor.traducir(e)))
    with escuchar_tokens(lambda t: enviar(traductor.token(t))):   # src/chatbot/respuesta_en_vivo.py
        ... motor; mientras trabaja, cada ~1 s: enviar(traductor.tic())
    enviar(traductor.finalizar())
    enviar(traductor.aviso(result))   # lista vacía si no hay aviso

Todo es puro (sin E/S salvo la lectura opcional de contadores del LLM) y se
prueba en tests/progreso/.
"""
import random
import time
import unicodedata

from src.chatbot.frases_progreso import (  # noqa: F401  (API pública de este módulo)
    AVISO_EXTRACTIVO,
    ESPERA_POWERBI,
    ETAPA_INICIAL,
    ETAPAS,
    FRASES,
    ROTACION_S,
    SEGUIMIENTO,
    UMBRALES_ESPERA,
)

# ======================================================================
# Etapas reales del turno y sus frases
# ======================================================================

# Prefijo del título de la actividad del motor (normalizado: minúsculas, sin
# tildes) → etapa. Títulos emitidos hoy por src/chatbot/query_engine.py
# (`_activity`) y src/providers/powerbi_provider.py (`_notify_activity`).
# «redactando» es un gancho para un aviso futuro del motor. «LLM en cola…»
# (llm_gate.add_queue_observer) NO cambia la etapa: es solo diagnóstico.
_PREFIJOS = (
    ("redactando", "redactando"),
    ("interpretando", "entendiendo"),
    ("buscando el indicador", "buscando_indicador"),
    ("armando la consulta", "buscando_indicador"),
    ("abriendo conexion", "conectando_powerbi"),
    ("reabriendo conexion", "conectando_powerbi"),
    ("consultando power bi", "consultando_powerbi"),
    ("trayendo la lista", "consultando_powerbi"),
    ("buscando en la documentacion", "revisando_documentacion"),
)

# Frases recientes que se recuerdan por sesión para no repetirlas.
MAX_RECIENTES = 12


def _normalizar(texto):
    base = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in base if not unicodedata.combining(c)).strip()


def etapa_de_evento(evento):
    """Etapa real a la que corresponde un evento del motor, o None (se
    mantiene la etapa actual). Solo las actividades (operaciones que
    empiezan y pueden tardar) cambian la etapa; los pasos no."""
    if not isinstance(evento, dict) or evento.get("kind") != "activity":
        return None
    titulo = _normalizar(evento.get("title"))
    if not titulo:
        return None
    if "describiendo" in titulo and "opciones" in titulo:
        return "preparando_opciones"
    for prefijo, etapa in _PREFIJOS:
        if titulo.startswith(prefijo):
            return etapa
    return None


class SelectorFrases:
    """Elige la variante menos usada recientemente de cada etapa.

    `recientes` es una lista compartida entre turnos de la misma sesión (el
    backend la guarda por conversación, p. ej. en Redis); dentro del turno
    tampoco se repite una frase mientras la etapa tenga otras variantes."""

    def __init__(self, recientes=None, rng=None):
        self.recientes = recientes if recientes is not None else []
        self._usadas = set()
        self._rng = rng or random.Random()

    def _ultimo_uso(self, frase):
        for indice in range(len(self.recientes) - 1, -1, -1):
            if self.recientes[indice] == frase:
                return indice
        return -1

    def elegir(self, etapa):
        variantes = FRASES.get(etapa) or FRASES[ETAPA_INICIAL]
        candidatas = [f for f in variantes if f not in self._usadas] or list(variantes)
        menor = min(self._ultimo_uso(f) for f in candidatas)
        frase = self._rng.choice([f for f in candidatas if self._ultimo_uso(f) == menor])
        self._usadas.add(frase)
        try:
            while frase in self.recientes:
                self.recientes.remove(frase)
            self.recientes.append(frase)
            del self.recientes[:-MAX_RECIENTES]
        except Exception:
            pass  # la memoria es un extra
        return frase


# ======================================================================
# Esperas largas
# ======================================================================

def frase_espera(nivel, etapa):
    """Mensaje del nivel de espera (1..len(UMBRALES_ESPERA)) para la etapa actual."""
    if nivel == 2 and etapa in ("consultando_powerbi", "conectando_powerbi"):
        return ESPERA_POWERBI
    return UMBRALES_ESPERA[nivel - 1][1]


def nivel_espera(transcurrido):
    """Nivel de espera alcanzado (0 si aún no se cruza el primer umbral)."""
    return sum(1 for segundo, _ in UMBRALES_ESPERA if transcurrido >= segundo)


# ======================================================================
# Carga del LLM (punto de enganche con runtime_stats)
# ======================================================================


def _capacidad_llm():
    try:
        from src.llm.llm_gate import max_concurrent

        return int(max_concurrent())
    except Exception:
        return 3


def leer_carga_llm(stats=None, capacidad=None):
    """PUNTO DE ENGANCHE con la carga del LLM (src/chatbot/runtime_stats.py),
    solo para el modo diagnóstico: ningún texto para el usuario depende de él.

    Devuelve {"en_curso", "en_cola", "capacidad", "ocupado"}. Si `stats`
    expone `llm_pressure()` → {"in_flight", "waiting", "capacity",
    "saturated_recent"} se usa eso (los rechazos recientes por saturación
    también cuentan como ocupado); si no, los contadores `stats.llm` de hoy
    (in_flight, waiting) y `llm_gate.max_concurrent()`. Nunca lanza."""
    try:
        if stats is None:
            from src.chatbot.runtime_stats import STATS as stats
        presion = getattr(stats, "llm_pressure", None)
        saturados = 0
        if callable(presion):
            datos = dict(presion() or {})
            capacidad = int(datos.get("capacity") or 0) or capacidad
            saturados = int(datos.get("saturated_recent") or 0)
        else:
            datos = dict(getattr(stats, "llm", None) or {})
        en_curso = int(datos.get("in_flight") or 0)
        en_cola = int(datos.get("waiting") or 0)
        capacidad = int(capacidad or _capacidad_llm())
        ocupado = en_cola > 0 or saturados > 0 or (capacidad > 0 and en_curso >= capacidad)
        return {"en_curso": en_curso, "en_cola": en_cola, "capacidad": capacidad, "ocupado": ocupado}
    except Exception:
        return {"en_curso": 0, "en_cola": 0, "capacidad": int(capacidad or 0), "ocupado": False}


# ======================================================================
# Respuesta degradada
# ======================================================================

def aviso_degradacion(result):
    """{"motivo", "texto"} si la respuesta documental salió como resumen
    extractivo (MedGemma saturado, sin respuesta a tiempo o no disponible),
    o None. `motivo` ("saturado" | "sin_redaccion") es solo diagnóstico."""
    if not isinstance(result, dict):
        return None
    if result.get("status") != "success" or result.get("route") != "rag":
        return None
    if result.get("synthesis_mode") != "extractive":
        return None
    partes = [str(result.get("synthesis_issue") or "")]
    for paso in ((result.get("reasoning") or {}).get("steps") or []):
        partes.append(str(paso.get("title") or ""))
        partes.extend(str(linea) for linea in paso.get("lines") or [])
    motivo = "saturado" if "saturad" in " ".join(partes).lower() else "sin_redaccion"
    return {"motivo": motivo, "texto": AVISO_EXTRACTIVO}


# ======================================================================
# Traductor de eventos del motor → eventos para la interfaz
# ======================================================================


def _evento(nombre, datos):
    """Sobre común: {"evento": nombre SSE, "datos": dict serializable}."""
    return {"evento": nombre, "datos": datos}


def evento_cola(posicion, en_curso):
    """Evento `cola` (SOLO modo diagnóstico): posición del turno en la fila
    (1 = el siguiente) y consultas en curso delante. Valores negativos se
    llevan a 0. El modo normal nunca lo convierte en texto."""
    return _evento("cola", {"posicion": max(0, int(posicion or 0)), "en_curso": max(0, int(en_curso or 0))})


def evento_token(texto):
    """Evento `token`: fragmento de la respuesta que se está redactando (se
    AÑADE al borrador de la burbuja; la respuesta final lo reemplaza)."""
    return _evento("token", {"texto": str(texto or "")})


class TraductorProgreso:
    """Traduce, para UN turno, los eventos del motor a eventos para la
    interfaz. Cada método devuelve una LISTA de sobres
    {"evento": "progreso"|"espera"|"token"|"cola"|"aviso", "datos": {...}}
    (vacía si no hay nada nuevo que mostrar). Nunca lanza.

    - `progreso` cuando la etapa CAMBIA (los pasos internos y las actividades
      repetidas de la misma etapa no generan ruido) y, si la etapa se alarga,
      cada ROTACION_S con la siguiente frase de SEGUIMIENTO (vía `tic()`).
    - `tic()` emite además `espera` al cruzar cada umbral de UMBRALES_ESPERA
      (el backend lo llama periódicamente mientras el motor trabaja).
    - Tras el primer `token`, `tic()` calla: la respuesta visible ya avanza."""

    def __init__(self, recientes=None, reloj=time.monotonic, rng=None):
        self._reloj = reloj
        self.inicio = reloj()
        self._selector = SelectorFrases(recientes, rng=rng)
        self.etapa = None
        self.nivel = 0
        self._frase_desde = self.inicio
        self._rotacion = {}
        self._escribiendo = False

    @property
    def recientes(self):
        return self._selector.recientes

    def _t(self):
        return round(max(0.0, self._reloj() - self.inicio), 1)

    def _progreso(self, frase):
        self._frase_desde = self._reloj()
        return [_evento("progreso", {"etapa": self.etapa, "frase": frase, "t": self._t()})]

    def _cambiar(self, etapa):
        if etapa is None or etapa == self.etapa:
            return []
        self.etapa = etapa
        return self._progreso(self._selector.elegir(etapa))

    def iniciar(self):
        return self._cambiar(ETAPA_INICIAL)

    def traducir(self, evento_motor):
        try:
            return self._cambiar(etapa_de_evento(evento_motor))
        except Exception:
            return []

    def esperando_turno(self, posicion=1, en_curso=1):
        """El turno espera a otro (hoy: candado «un turno a la vez» de
        runtime_stats.turn_slot; mañana: la cola de Redis). La etapa visible
        NO cambia (si el turno no había empezado, se muestra la inicial);
        `cola` se emite en cada llamada solo para el modo diagnóstico."""
        eventos = self._cambiar(ETAPA_INICIAL) if self.etapa is None else []
        eventos.append(evento_cola(posicion, en_curso))
        return eventos

    def _rotar(self):
        seguimiento = SEGUIMIENTO.get(self.etapa)
        if not seguimiento or self._reloj() - self._frase_desde < ROTACION_S:
            return []
        indice = self._rotacion.get(self.etapa, 0)
        self._rotacion[self.etapa] = indice + 1
        return self._progreso(seguimiento[indice % len(seguimiento)])

    def _esperar(self):
        alcanzado = nivel_espera(self._reloj() - self.inicio)
        if alcanzado <= self.nivel:
            return []
        self.nivel = alcanzado
        return [_evento("espera", {
            "nivel": alcanzado, "frase": frase_espera(alcanzado, self.etapa), "t": self._t(),
        })]

    def tic(self):
        """Rotación de la frase de la etapa (cada ROTACION_S) y mensaje de
        espera larga si se cruzó un umbral nuevo. Si se cruzaron varios desde
        el último tic (backend ocupado), solo se emite el más alto: cada
        mensaje reemplaza al anterior en la interfaz."""
        if self._escribiendo:
            return []
        try:
            return self._rotar() + self._esperar()
        except Exception:
            return []

    def token(self, texto):
        """Fragmento de la respuesta en redacción (streaming de MedGemma)."""
        if not texto:
            return []
        self._escribiendo = True
        return [evento_token(texto)]

    def finalizar(self):
        """El motor terminó y la respuesta se está armando para enviarla."""
        return self._cambiar("finalizando")

    def aviso(self, result):
        datos = aviso_degradacion(result)
        return [_evento("aviso", datos)] if datos else []

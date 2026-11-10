"""Progreso del turno para el usuario final: etapas reales, frases humanas y
eventos serializables a JSON (independiente del framework de interfaz).

El motor (QueryEngine) avisa lo que hace con eventos de su traza
(`set_progress_listener`): {"kind": "activity"|"step", "title", "t", "lines"}.
Esos títulos son técnicos («Consultando Power BI (CIRUGIAS)», «Query Plan»,
«MedGemma»...). Este módulo los traduce a eventos para la interfaz, sin
segundos visibles, nombres de modelos, DAX ni pasos internos:

    progreso  {"etapa": str, "frase": str, "t": float}
    espera    {"nivel": int, "frase": str, "t": float}
    cola      {"posicion": int, "en_curso": int}
    aviso     {"motivo": str, "texto": str}

`t` (segundos desde el inicio del turno) es para ordenar y medir; la interfaz
NO lo muestra. El backend (FastAPI) envía cada evento por SSE con
`event: <evento>` y `data: <JSON de datos>`; el contrato completo está en
specs/003-progreso-chat/contracts/eventos.md.

Uso típico en el backend, por turno:

    traductor = TraductorProgreso(recientes=memoria_de_la_sesion)
    enviar(traductor.iniciar())
    engine.set_progress_listener(lambda e: enviar(traductor.traducir(e)))
    ... mientras el motor trabaja, cada ~1 s: enviar(traductor.tic())
    enviar(traductor.finalizar())
    enviar(traductor.aviso(result))   # lista vacía si no hay aviso

Todo es puro (sin E/S salvo la lectura opcional de contadores del LLM) y se
prueba en tests/progreso/.
"""
import random
import time
import unicodedata

# ======================================================================
# Etapas reales del turno y sus frases
# ======================================================================

# Variantes por etapa: todas describen lo que de verdad está pasando, para
# variar sin mentir. Cortas, sin cifras ni términos técnicos.
FRASES = {
    "entendiendo": (
        "Entendiendo tu pregunta",
        "Interpretando lo que necesitas",
        "Revisando qué dato me pides",
        "Leyendo con atención tu pregunta",
    ),
    "buscando_indicador": (
        "Buscando el indicador en los tableros",
        "Ubicando el tablero que tiene ese dato",
        "Buscando el indicador y el periodo que pides",
        "Revisando qué tablero responde mejor",
    ),
    "preparando_opciones": (
        "Preparando las opciones para que elijas",
        "Describiendo las opciones que encontré",
        "Organizando las alternativas encontradas",
    ),
    "conectando_powerbi": (
        "Conectando con Power BI",
        "Abriendo la conexión con los tableros",
        "Estableciendo la conexión con Power BI",
    ),
    "consultando_powerbi": (
        "Consultando los datos en Power BI",
        "Trayendo las cifras del tablero",
        "Consultando el tablero en Power BI",
        "Calculando el dato en Power BI",
    ),
    "revisando_documentacion": (
        "Revisando la documentación de los tableros",
        "Leyendo la documentación para responderte",
        "Buscando en la documentación y preparando la respuesta",
    ),
    "redactando": (
        "Redactando la respuesta",
        "Poniendo en palabras lo que encontré",
        "Preparando la respuesta con lo que encontré",
    ),
    "en_cola": (
        "Hay otras consultas en curso; la tuya sigue enseguida",
        "Tu pregunta está en fila; enseguida la atiendo",
        "Esperando un turno libre para responderte",
    ),
    "finalizando": (
        "Ya casi está",
        "Dando los últimos toques a la respuesta",
        "Terminando de preparar la respuesta",
    ),
}
ETAPAS = tuple(FRASES)
ETAPA_INICIAL = "entendiendo"

# Prefijo del título de la actividad del motor (normalizado: minúsculas, sin
# tildes) → etapa. Títulos emitidos hoy por src/chatbot/query_engine.py
# (`_activity`) y src/providers/powerbi_provider.py (`_notify_activity`).
# «llm en cola» y «redactando» son ganchos para avisos futuros del motor o
# del gestor de carga del LLM (ver contracts/eventos.md).
_PREFIJOS = (
    ("llm en cola", "en_cola"),
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

# (segundos desde el inicio del turno, mensaje). El del nivel 2 depende de la
# etapa y de la carga del LLM (ver frase_espera).
UMBRALES_ESPERA = (
    (10, "Esto está tomando un poco más de lo normal…"),
    (25, "Sigo trabajando en tu respuesta; gracias por la paciencia."),
    (50, "Sigue en marcha: no hace falta volver a enviar la pregunta."),
    (90, "Está tardando más de lo habitual; sigo esperando la respuesta."),
)

ESPERA_POWERBI = "Power BI está tardando en responder; sigo esperando los datos."
ESPERA_FILA = "Hay varias consultas en curso; la tuya está en fila, ya casi…"
ESPERA_TURNO = "Hay otra consulta en curso; la tuya sigue enseguida."

# Etapas en las que el turno espera a MedGemma.
_ETAPAS_LLM = ("entendiendo", "preparando_opciones", "revisando_documentacion", "redactando")


def frase_espera(nivel, etapa, carga=None):
    """Mensaje del nivel de espera (1..len(UMBRALES_ESPERA)) para la etapa
    actual. `carga` es lo que devuelve leer_carga_llm (o None)."""
    texto = UMBRALES_ESPERA[nivel - 1][1]
    if nivel != 2:
        return texto
    if etapa in ("consultando_powerbi", "conectando_powerbi"):
        return ESPERA_POWERBI
    if etapa == "en_cola":
        return ESPERA_TURNO
    if (carga or {}).get("ocupado") and etapa in _ETAPAS_LLM:
        return ESPERA_FILA
    return texto


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
    """PUNTO DE ENGANCHE con la carga del LLM (src/chatbot/runtime_stats.py).

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

AVISO_SATURADO = (
    "Ahora mismo hay muchas consultas a la vez, así que te muestro directamente lo que dice "
    "la documentación, sin redactarlo. Si quieres una explicación más elaborada, vuelve a "
    "preguntar en un momento."
)
AVISO_SIN_REDACCION = (
    "Esta vez no pude redactar la respuesta, así que te muestro directamente lo que dice "
    "la documentación."
)


def aviso_degradacion(result):
    """{"motivo", "texto"} si la respuesta documental salió como resumen
    extractivo (MedGemma saturado, sin respuesta a tiempo o no disponible),
    o None."""
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
    if "saturad" in " ".join(partes).lower():
        return {"motivo": "saturado", "texto": AVISO_SATURADO}
    return {"motivo": "sin_redaccion", "texto": AVISO_SIN_REDACCION}


# ======================================================================
# Traductor de eventos del motor → eventos para la interfaz
# ======================================================================


def _evento(nombre, datos):
    """Sobre común: {"evento": nombre SSE, "datos": dict serializable}."""
    return {"evento": nombre, "datos": datos}


def evento_cola(posicion, en_curso):
    """Evento `cola`: posición del turno en la fila (1 = el siguiente) y
    consultas en curso delante. Valores negativos se llevan a 0."""
    return _evento("cola", {"posicion": max(0, int(posicion or 0)), "en_curso": max(0, int(en_curso or 0))})


class TraductorProgreso:
    """Traduce, para UN turno, los eventos del motor a eventos para la
    interfaz. Cada método devuelve una LISTA de sobres
    {"evento": "progreso"|"espera"|"cola"|"aviso", "datos": {...}} (vacía si
    no hay nada nuevo que mostrar). Nunca lanza.

    - Solo emite `progreso` cuando la etapa CAMBIA (los pasos internos y las
      actividades repetidas de la misma etapa no generan ruido).
    - `tic()` emite `espera` al cruzar cada umbral de UMBRALES_ESPERA (el
      backend lo llama periódicamente mientras el motor trabaja)."""

    def __init__(self, recientes=None, reloj=time.monotonic, rng=None, carga=leer_carga_llm):
        self._reloj = reloj
        self.inicio = reloj()
        self._selector = SelectorFrases(recientes, rng=rng)
        self._carga = carga
        self.etapa = None
        self.nivel = 0
        self._cola_avisada = False

    @property
    def recientes(self):
        return self._selector.recientes

    def _t(self):
        return round(max(0.0, self._reloj() - self.inicio), 1)

    def _leer_carga(self):
        try:
            return self._carga() if callable(self._carga) else None
        except Exception:
            return None

    def _cambiar(self, etapa):
        if etapa is None or etapa == self.etapa:
            return []
        self.etapa = etapa
        return [_evento("progreso", {"etapa": etapa, "frase": self._selector.elegir(etapa), "t": self._t()})]

    def iniciar(self):
        return self._cambiar(ETAPA_INICIAL)

    def traducir(self, evento_motor):
        try:
            return self._cambiar(etapa_de_evento(evento_motor))
        except Exception:
            return []

    def esperando_turno(self, posicion=1, en_curso=1):
        """El turno espera a otro (hoy: candado «un turno a la vez» de
        runtime_stats.turn_slot; mañana: la cola de Redis). La etapa se avisa
        una vez; `cola` se emite en cada llamada para que la interfaz
        actualice la posición si cambia."""
        eventos = self._cambiar("en_cola")
        eventos.append(evento_cola(posicion, en_curso))
        return eventos

    def tic(self):
        """Mensaje de espera larga si se cruzó un umbral nuevo. Si se
        cruzaron varios desde el último tic (backend ocupado), solo se emite
        el más alto: cada mensaje reemplaza al anterior en la interfaz."""
        try:
            alcanzado = nivel_espera(self._reloj() - self.inicio)
            if alcanzado <= self.nivel:
                return []
            self.nivel = alcanzado
            carga = self._leer_carga() if alcanzado == 2 else None
            return [_evento("espera", {
                "nivel": alcanzado, "frase": frase_espera(alcanzado, self.etapa, carga), "t": self._t(),
            })]
        except Exception:
            return []

    def finalizar(self):
        """El motor terminó y la respuesta se está armando para enviarla."""
        return self._cambiar("finalizando")

    def aviso(self, result):
        datos = aviso_degradacion(result)
        return [_evento("aviso", datos)] if datos else []

"""
Estado del servidor en ejecución (diagnóstico de estabilidad).

Contadores de proceso, compartidos por todas las sesiones de Streamlit:

  * turnos atendidos y el candado «un turno a la vez» (`turn_slot`);
  * llamadas a MedGemma: en curso, en cola, completadas, tiempo agotado,
    rechazadas por saturación, errores y latencias recientes (las registra
    `src/llm/llm_gate.py`);
  * Power BI: conexiones abiertas y reabiertas por modelo y consultas en curso
    (las registra `src/providers/powerbi_provider.py`).

La barra lateral («Diagnóstico del servidor»), el razonamiento de cada turno
(«Estado al empezar: …») y la cabecera de la exportación (.md) muestran estos
números: si la app se vuelve lenta tras varias conversaciones, ahí se ve si
hay llamadas acumuladas, reconexiones o hilos vivos de más.
"""
import os
import re
import threading
import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime

# Latencias recientes que se promedian (llamadas al LLM).
RECENT_LATENCIES = 20


def env_float(name, default):
    try:
        value = float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)
    return value if value > 0 else float(default)


def env_int(name, default):
    try:
        value = int(float(os.getenv(name, default)))
    except (TypeError, ValueError):
        return int(default)
    return value if value > 0 else int(default)


class RuntimeStats:
    """Contadores de proceso (seguros entre hilos)."""

    def __init__(self, clock=time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.started_at = self._clock()
            self.turns = {"started": 0, "finished": 0, "errors": 0, "waited": 0, "busy": 0}
            self.turn_holder = None  # {"text", "since"} del turno en curso
            self.llm = {
                "in_flight": 0, "waiting": 0, "completed": 0, "timeouts": 0,
                "saturated": 0, "errors": 0, "abandoned": 0,
            }
            self.llm_by_purpose = {}
            self.llm_latencies = deque(maxlen=RECENT_LATENCIES)
            self.powerbi = {"opened": 0, "reopened": 0, "queries": 0, "query_timeouts": 0,
                            "query_errors": 0, "timeout_kept": 0, "timeout_lost": 0}
            self.powerbi_opened_by_model = {}
            self.powerbi_in_flight = {}

    # ------------------------------------------------------------------
    # turnos
    # ------------------------------------------------------------------

    def _bump(self, group, key, amount=1):
        with self._lock:
            group[key] = group.get(key, 0) + amount

    def turn_started(self):
        self._bump(self.turns, "started")

    def turn_finished(self, error=False):
        self._bump(self.turns, "errors" if error else "finished")

    # ------------------------------------------------------------------
    # LLM (MedGemma)
    # ------------------------------------------------------------------

    def llm_waiting(self, delta):
        self._bump(self.llm, "waiting", delta)

    def llm_begin(self, purpose):
        with self._lock:
            self.llm["in_flight"] += 1
            entry = self.llm_by_purpose.setdefault(purpose or "otro", {"calls": 0, "timeouts": 0})
            entry["calls"] += 1

    def llm_abandoned(self, purpose):
        """Se dejó de esperar una llamada que sigue viva (proveedor sin tiempo
        límite propio): cuenta como tiempo agotado y queda «en curso»."""
        with self._lock:
            self.llm["timeouts"] += 1
            self.llm["abandoned"] += 1
            entry = self.llm_by_purpose.setdefault(purpose or "otro", {"calls": 0, "timeouts": 0})
            entry["timeouts"] += 1

    def llm_end(self, purpose, status, elapsed, abandoned=False):
        with self._lock:
            self.llm["in_flight"] = max(0, self.llm["in_flight"] - 1)
            if abandoned:
                return  # ya contada como tiempo agotado
            if status == "success" or status == "empty_response":
                self.llm["completed"] += 1
            elif status == "llm_timeout":
                self.llm["timeouts"] += 1
                entry = self.llm_by_purpose.setdefault(purpose or "otro", {"calls": 0, "timeouts": 0})
                entry["timeouts"] += 1
            else:
                self.llm["errors"] += 1
            if elapsed is not None:
                self.llm_latencies.append(float(elapsed))

    def llm_saturated(self, purpose):
        with self._lock:
            self.llm["saturated"] += 1
            entry = self.llm_by_purpose.setdefault(purpose or "otro", {"calls": 0, "timeouts": 0})
            entry["saturated"] = entry.get("saturated", 0) + 1

    # ------------------------------------------------------------------
    # Power BI
    # ------------------------------------------------------------------

    def powerbi_connection_opened(self, model, reopened=False):
        with self._lock:
            self.powerbi["reopened" if reopened else "opened"] += 1
            key = str(model or "(espacio de trabajo)")
            self.powerbi_opened_by_model[key] = self.powerbi_opened_by_model.get(key, 0) + 1

    def powerbi_timeout_connection(self, model, kept):
        """Tras cancelar una consulta por CommandTimeout, ¿siguió abierta la
        conexión? (si no, la próxima consulta la reabre)."""
        self._bump(self.powerbi, "timeout_kept" if kept else "timeout_lost")

    def powerbi_query_begin(self, model):
        with self._lock:
            key = str(model or "(espacio de trabajo)")
            self.powerbi["queries"] += 1
            self.powerbi_in_flight[key] = self.powerbi_in_flight.get(key, 0) + 1

    def powerbi_query_end(self, model, status=None, timed_out=False):
        with self._lock:
            key = str(model or "(espacio de trabajo)")
            self.powerbi_in_flight[key] = max(0, self.powerbi_in_flight.get(key, 0) - 1)
            if not self.powerbi_in_flight[key]:
                self.powerbi_in_flight.pop(key, None)
            if timed_out:
                self.powerbi["query_timeouts"] += 1
            elif status not in (None, "success"):
                self.powerbi["query_errors"] += 1

    # ------------------------------------------------------------------
    # instantánea
    # ------------------------------------------------------------------

    def snapshot(self, powerbi_provider=None):
        """Diccionario con todos los números (para la barra lateral, el
        razonamiento y la exportación). `powerbi_provider` (opcional) aporta
        las conexiones abiertas y el tamaño de la caché de dominios."""
        now = self._clock()
        with self._lock:
            latencies = list(self.llm_latencies)
            data = {
                "uptime_s": round(now - self.started_at, 1),
                "started_at": datetime.fromtimestamp(self.started_at).strftime("%Y-%m-%d %H:%M:%S"),
                "turns": dict(self.turns),
                "turn_holder": dict(self.turn_holder) if self.turn_holder else None,
                "llm": dict(self.llm),
                "llm_by_purpose": {k: dict(v) for k, v in self.llm_by_purpose.items()},
                "llm_recent_latency_s": (
                    round(sum(latencies) / len(latencies), 2) if latencies else None
                ),
                "llm_recent_max_s": round(max(latencies), 2) if latencies else None,
                "powerbi": dict(self.powerbi),
                "powerbi_opened_by_model": dict(self.powerbi_opened_by_model),
                "powerbi_in_flight": dict(self.powerbi_in_flight),
            }
        if data["turn_holder"]:
            data["turn_holder"]["for_s"] = round(now - data["turn_holder"]["since"], 1)
        data["powerbi_open"] = open_connections(powerbi_provider)
        cache = getattr(powerbi_provider, "domain_cache", None) if powerbi_provider is not None else None
        try:
            data["domain_cache_size"] = len(cache) if cache is not None else 0
        except Exception:
            data["domain_cache_size"] = None
        threads = threading.enumerate()
        data["threads"] = len(threads)
        # Hilos agrupados por nombre (los números se cambian por N): una
        # acumulación de hilos de un mismo tipo delata llamadas abandonadas.
        names = {}
        for thread in threads:
            base = re.sub(r"\d+", "N", thread.name or "?")
            names[base] = names.get(base, 0) + 1
        data["thread_names"] = dict(sorted(names.items(), key=lambda item: -item[1]))
        return data


def open_connections(provider):
    """Modelos con una conexión ADOMD abierta en el proveedor (lista)."""
    connections = getattr(provider, "_connections", None) if provider is not None else None
    if not connections:
        return []
    checker = getattr(provider, "_is_connection_open", None)
    names = []
    for key, connection in list(connections.items()):
        try:
            is_open = bool(checker(connection)) if callable(checker) else connection is not None
        except Exception:
            is_open = False
        if is_open:
            names.append("espacio de trabajo" if key == "__workspace__" else str(key))
    return names


def _duration(seconds):
    seconds = float(seconds or 0)
    if seconds < 120:
        return f"{seconds:.0f} s"
    if seconds < 7200:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f} h"


def status_line(snapshot):
    """Una línea con el estado del servidor (para el razonamiento)."""
    llm = snapshot["llm"]
    latency = snapshot.get("llm_recent_latency_s")
    pbi = snapshot["powerbi"]
    in_flight = sum(snapshot.get("powerbi_in_flight", {}).values())
    open_models = snapshot.get("powerbi_open") or []
    parts = [
        f"encendido hace {_duration(snapshot['uptime_s'])}",
        f"turnos {snapshot['turns']['finished'] + snapshot['turns']['errors']}",
        f"MedGemma {llm['in_flight']} en curso/{llm['waiting']} en cola/"
        f"{llm['timeouts']} agotadas/{llm['saturated']} saturadas/{llm['errors']} errores"
        + (f", latencia media {latency:.1f} s" if latency is not None else ""),
        f"Power BI {len(open_models)} conexiones"
        + (f" ({', '.join(open_models)})" if open_models else "")
        + f", {in_flight} consultas en curso, {pbi['reopened']} reconexiones",
        f"caché de dominios {snapshot.get('domain_cache_size')}",
        f"hilos {snapshot['threads']}",
    ]
    return " · ".join(parts)


def diagnostics_lines(snapshot, powerbi_provider=None):
    """Líneas Markdown del desplegable «Diagnóstico del servidor»."""
    llm = snapshot["llm"]
    turns = snapshot["turns"]
    pbi = snapshot["powerbi"]
    latency = snapshot.get("llm_recent_latency_s")
    holder = snapshot.get("turn_holder")
    lines = [
        f"- **Encendido:** hace {_duration(snapshot['uptime_s'])} (desde {snapshot['started_at']})",
        f"- **Turnos atendidos:** {turns['finished']} · con error {turns['errors']}"
        f" · tuvieron que esperar a otro {turns['waited']} · rechazados por ocupado {turns['busy']}",
        "- **Turno en curso:** "
        + (f"«{holder['text']}» desde hace {holder.get('for_s', 0):.0f} s" if holder else "ninguno"),
        f"- **MedGemma:** {llm['in_flight']} en curso · {llm['waiting']} en cola · "
        f"{llm['completed']} completadas · {llm['timeouts']} con tiempo agotado"
        f" (abandonadas {llm['abandoned']}) · {llm['saturated']} descartadas por saturación · "
        f"{llm['errors']} con error",
        "- **Latencia reciente de MedGemma:** "
        + (f"media {latency:.1f} s · máxima {snapshot['llm_recent_max_s']:.1f} s"
           if latency is not None else "sin llamadas aún"),
    ]
    by_purpose = snapshot.get("llm_by_purpose") or {}
    if by_purpose:
        lines.append("- **MedGemma por uso:** " + " · ".join(
            f"{name}: {data.get('calls', 0)} llamadas, {data.get('timeouts', 0)} agotadas"
            + (f", {data['saturated']} saturadas" if data.get("saturated") else "")
            for name, data in sorted(by_purpose.items())
        ))
    open_models = snapshot.get("powerbi_open") or []
    in_flight = snapshot.get("powerbi_in_flight") or {}
    lines += [
        f"- **Power BI, conexiones abiertas:** {len(open_models)}"
        + (f" ({', '.join(open_models)})" if open_models else ""),
        "- **Power BI, consultas en curso:** "
        + (", ".join(f"{model}: {count}" for model, count in in_flight.items()) if in_flight else "0"),
        f"- **Power BI, aperturas:** {pbi['opened']} · reconexiones {pbi['reopened']}"
        f" · consultas {pbi['queries']} · cortadas por tiempo límite {pbi['query_timeouts']}"
        f" (conexión conservada {pbi['timeout_kept']}, perdida {pbi['timeout_lost']})"
        f" · con error {pbi['query_errors']}",
    ]
    events = list(getattr(powerbi_provider, "connection_events", None) or [])[-5:]
    for event in events:
        lines.append(
            f"  - {event.get('at')} {event.get('kind')} ({event.get('model')}) en "
            f"{event.get('elapsed_s')} s" + (f" · {event['reason']}" if event.get("reason") else "")
            + ("" if event.get("ok", True) else " · NO quedó abierta")
        )
    lines += [
        f"- **Caché de dominios:** {snapshot.get('domain_cache_size')} columnas",
        f"- **Hilos vivos:** {snapshot['threads']} ("
        + ", ".join(f"{name} ×{count}" for name, count in list(snapshot.get("thread_names", {}).items())[:6])
        + ")",
    ]
    return lines


def degradation_lines(before, after):
    """Qué se degradó durante el turno (diferencia entre dos instantáneas)."""
    lines = []

    def delta(group, key):
        return (after.get(group) or {}).get(key, 0) - (before.get(group) or {}).get(key, 0)

    timeouts = delta("llm", "timeouts")
    saturated = delta("llm", "saturated")
    errors = delta("llm", "errors")
    if timeouts:
        lines.append(f"{timeouts} llamada(s) a MedGemma agotaron su tiempo límite (se cortó la conexión)")
    if saturated:
        lines.append(f"{saturated} llamada(s) a MedGemma no se hicieron: el servidor estaba saturado")
    if errors:
        lines.append(f"{errors} llamada(s) a MedGemma fallaron")
    opened = delta("powerbi", "opened") + delta("powerbi", "reopened")
    if delta("powerbi", "reopened"):
        lines.append(f"se reabrió {delta('powerbi', 'reopened')} conexión(es) con Power BI")
    elif opened:
        lines.append(f"se abrió {opened} conexión(es) nueva(s) con Power BI")
    if delta("powerbi", "query_timeouts"):
        lines.append(f"{delta('powerbi', 'query_timeouts')} consulta(s) a Power BI agotaron su tiempo límite")
    return lines


STATS = RuntimeStats()


# ======================================================================
# Un turno a la vez
# ======================================================================

TURN_LOCK = threading.Lock()


class TurnBusy(Exception):
    """Otro turno siguió en curso más allá del tiempo de espera."""

    def __init__(self, waited_s, holder=None):
        super().__init__(f"otra consulta sigue en curso tras {waited_s:.0f} s de espera")
        self.waited_s = waited_s
        self.holder = holder


def turn_wait_limit():
    return env_float("TURN_WAIT_SECONDS", 120.0)


@contextmanager
def turn_slot(text=None, on_wait=None, max_wait=None, poll_s=0.5, stats=None):
    """Ejecuta el bloque con el candado de proceso «un turno a la vez».

    El motor (QueryEngine) es un único objeto con estado por turno: dos turnos
    a la vez (otra pestaña, o un rerun mientras una llamada sigue bloqueada)
    mezclarían razonamiento, memoria y contrapreguntas. Si otro turno está en
    curso se espera (avisando con `on_wait(segundos_esperados, desde_hace)`)
    hasta `max_wait` segundos; al vencer se lanza TurnBusy. El candado se
    libera siempre (finally), también si Streamlit aborta la ejecución con una
    excepción de control (StopException/RerunException son BaseException).
    """
    stats = stats or STATS
    max_wait = turn_wait_limit() if max_wait is None else float(max_wait)
    started = time.time()
    acquired = TURN_LOCK.acquire(blocking=False)
    if not acquired:
        stats._bump(stats.turns, "waited")
        while not acquired:
            waited = time.time() - started
            if waited >= max_wait:
                stats._bump(stats.turns, "busy")
                raise TurnBusy(waited, stats.turn_holder)
            if on_wait is not None:
                holder = stats.turn_holder or {}
                since = holder.get("since")
                on_wait(waited, (time.time() - since) if since else None)
            acquired = TURN_LOCK.acquire(timeout=min(poll_s, max(0.01, max_wait - waited)))
    try:
        with stats._lock:
            stats.turn_holder = {"text": str(text or "")[:80], "since": time.time()}
        yield time.time() - started
    finally:
        with stats._lock:
            stats.turn_holder = None
        TURN_LOCK.release()


def turn_lock_busy():
    return TURN_LOCK.locked()

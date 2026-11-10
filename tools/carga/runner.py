"""
Rampas de usuarios concurrentes en modo `llm` (solo el LLM, por la puerta
src/llm/llm_gate.py) y `e2e` (a través del motor del simulador, con el turno
compartido de app.py: `turn_slot`).

Los tiempos se reportan en segundos SIMULADOS (con `escala` < 1 todo corre
más rápido y se divide al medir). Con el servidor real, escala = 1.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

from tools.carga import escenarios, metricas
from tools.carga.simulador import ProveedorSimulado, ServidorConfig, ServidorSimulado

SALIDAS = Path(__file__).resolve().parent / "salidas"


class _EnvTemporal:
    def __init__(self, **values):
        self.values = {k: v for k, v in values.items() if v is not None}
        self.saved = {}

    def __enter__(self):
        for key, value in self.values.items():
            self.saved[key] = os.environ.get(key)
            os.environ[key] = str(value)
        return self

    def __exit__(self, *exc):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _esperar_puerta_libre(seconds=30.0):
    from src.llm.llm_gate import queue_state
    deadline = time.time() + seconds
    while time.time() < deadline:
        state = queue_state()
        if not state["in_flight"] and not state["waiting"]:
            return True
        time.sleep(0.02)
    return False


def _arrancar(usuarios, objetivo):
    """Lanza `usuarios` hilos que empiezan a la vez (barrera)."""
    barrier = threading.Barrier(usuarios)
    threads = []
    for index in range(usuarios):
        def run(i=index):
            barrier.wait()
            objetivo(i)
        thread = threading.Thread(target=run, name=f"usuario-{index + 1}", daemon=True)
        threads.append(thread)
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return time.perf_counter() - started


# ======================================================================
# modo llm
# ======================================================================

class _Llamador:
    def __init__(self, provider, escala, espera_cola, espera_ui, sin_puerta):
        self.provider = provider
        self.escala = escala
        self.espera_cola = espera_cola
        self.espera_ui = espera_ui
        self.sin_puerta = sin_puerta
        self.messages = {name: spec["messages"]() for name, spec in escenarios.LLAMADAS.items()}
        self.t_ref = time.perf_counter()

    def llamar(self, name, en_hilo_de_sesion=True):
        from src.llm.llm_gate import call_llm
        spec = escenarios.LLAMADAS[name]
        timeout = spec["timeout"] * self.escala
        if spec["queue_wait"] is not None:
            queue_wait = spec["queue_wait"] * self.escala
        elif self.espera_ui and en_hilo_de_sesion:
            queue_wait = None  # la decide ui_progress (MEDGEMMA_QUEUE_WAIT_UI)
        else:
            queue_wait = self.espera_cola * self.escala
        started = time.perf_counter()
        t0 = (started - self.t_ref) / self.escala
        if self.sin_puerta:
            try:
                result = self.provider.chat(self.messages[name], temperature=spec["temperature"],
                                            max_tokens=spec["max_tokens"], think=False, timeout=timeout)
            except Exception as error:
                result = {"status": "llm_error", "error": f"{type(error).__name__}: {error}"}
        else:
            result = call_llm(self.provider, self.messages[name], purpose=spec["purpose"], timeout=timeout,
                              queue_wait=queue_wait, temperature=spec["temperature"],
                              max_tokens=spec["max_tokens"], think=False)
        latency = (time.perf_counter() - started) / self.escala
        # Espera en fila: latencia - lo que tardó el servidor (si lo informa);
        # si no, lo que dice la puerta (waited_s al saturar, queue_wait_s ≥ 0,5 s).
        duration = result.get("duration_s")
        gate_wait = result.get("waited_s", result.get("queue_wait_s"))
        if duration is not None:
            wait = max(0.0, latency - duration)
        elif gate_wait is not None:
            wait = gate_wait / self.escala
        else:
            wait = None
        ttft = result.get("ttft_s")
        return {
            "purpose": spec["purpose"], "status": result.get("status"), "latency_s": round(latency, 3),
            "wait_s": None if wait is None else round(wait, 3),
            "ttft_s": None if ttft is None else round((wait or 0.0) + ttft, 3),
            "truncated": bool(result.get("truncated")), "done_reason": result.get("done_reason"),
            "context_truncated": bool(result.get("context_truncated")),
            "error": result.get("error"),
            # Intervalo de la llamada desde el inicio del escalón (paralelismo observado).
            "t0_s": round(t0, 3), "t1_s": round(t0 + latency, 3),
            "duration_s": None if duration is None else round(float(duration), 3),
            "ttft_srv_s": None if ttft is None else round(float(ttft), 3),
        }


def _nivel_llm(usuarios, turnos, perfil, llamador, semilla, pausa):
    from src.llm.llm_gate import ui_progress
    calls, turns, lock = [], [], threading.Lock()
    llamador.t_ref = time.perf_counter()

    def usuario(index):
        rng = escenarios.nuevo_rng(semilla, index)
        context = (ui_progress(queue_wait=llamador.espera_ui * llamador.escala)
                   if llamador.espera_ui else nullcontext())
        with context:
            for number in range(turnos):
                kind = escenarios.elegir_turno(perfil, rng)
                started = time.perf_counter()
                records = []
                for step in escenarios.TURNOS[kind]:
                    if len(step) == 1:
                        records.append(llamador.llamar(step[0]))
                    else:
                        # Como OptionDescriber: hilos aparte (sin el contexto de la UI).
                        with ThreadPoolExecutor(max_workers=len(step)) as pool:
                            records.extend(pool.map(lambda n: llamador.llamar(n, en_hilo_de_sesion=False), step))
                total = (time.perf_counter() - started) / llamador.escala
                synth = [r for r in records if r["purpose"] == "síntesis RAG"]
                with lock:
                    calls.extend(records)
                    turns.append({
                        "usuario": index + 1, "turno": number + 1, "tipo": kind, "total_s": round(total, 3),
                        "status": "ok",
                        "degraded": any(r["status"] not in metricas.OK for r in records),
                        "fallback": any(r["status"] not in metricas.OK for r in synth),
                    })
                if pausa:
                    time.sleep(pausa * llamador.escala)

    wall = _arrancar(usuarios, usuario) / llamador.escala
    _esperar_puerta_libre()
    return calls, turns, wall


# ======================================================================
# modo e2e (motor del simulador + turno compartido como app.py)
# ======================================================================

class _Grabadora:
    """Envuelve al proveedor y anota cada llamada que llega al servidor."""

    enforces_timeout = True

    def __init__(self, provider, escala):
        self.provider = provider
        self.escala = escala
        self.model = getattr(provider, "model", "?")
        self.host = getattr(provider, "host", "?")
        self.records = []
        self._lock = threading.Lock()

    def healthcheck(self):
        return self.provider.healthcheck()

    def warmup(self, timeout=None):
        return {"status": "ready"}

    def chat(self, messages, **kwargs):
        started = time.perf_counter()
        result = self.provider.chat(messages, **kwargs)
        latency = (time.perf_counter() - started) / self.escala
        with self._lock:
            self.records.append({
                "purpose": "e2e", "status": result.get("status"), "latency_s": round(latency, 3),
                "ttft_s": result.get("ttft_s"), "truncated": bool(result.get("truncated")),
                "done_reason": result.get("done_reason"), "error": result.get("error"),
            })
        return result


def _motor_e2e(provider, escala):
    """Motor del simulador (Power BI, Qdrant y MiniLM falsos) con el LLM
    cableado al proveedor dado y los tiempos límite escalados."""
    import sys

    from tests.sim import fakes, harness

    # Con --real, medgemma_provider ya se importó con el cliente y el dotenv
    # reales (el proveedor real se construyó antes): mientras se arma el motor
    # simulado se usan los falsos, para que su MedGemmaProvider interno no lea
    # el .env ni salga a la red. Sin --real aún no está importado y el arnés
    # lo importa ya con los falsos.
    mp = sys.modules.get("src.llm.medgemma_provider")
    saved = (mp.Client, mp.ResponseError, mp.load_dotenv) if mp is not None else None
    if mp is not None:
        mp.Client, mp.ResponseError = fakes.FakeOllamaClient, fakes.FakeResponseError
        mp.load_dotenv = lambda *a, **k: False
    try:
        engine, cm, formatter, _status, _pbi, _dax = harness.build_engine()
    finally:
        if mp is not None:
            mp.Client, mp.ResponseError, mp.load_dotenv = saved
    from src.chatbot import contextual_rewriter

    synthesizer = engine.rag_answer_engine.answer_synthesizer
    synthesizer.llm_provider = provider
    synthesizer.timeout_seconds = escenarios.DEFAULT_SYNTHESIS_TIMEOUT * escala
    describer = getattr(engine, "option_describer", None)
    if describer is not None:
        describer.llm_provider = provider
        describer.timeout = 15.0 * escala
    engine.context_llm = provider
    init = contextual_rewriter.LLMContextRewriter.__init__
    original_defaults = init.__defaults__
    defaults = list(original_defaults)
    defaults[0] = 8.0 * escala
    init.__defaults__ = tuple(defaults)

    def restaurar():
        init.__defaults__ = original_defaults

    return harness, engine, cm, formatter, restaurar


def _nivel_e2e(usuarios, turnos, sistema, grabadora, escala, espera_turno, espera_ui, pausa):
    from src.chatbot.runtime_stats import STATS, TurnBusy, turn_slot
    from src.llm.llm_gate import ui_progress
    harness, engine, cm, formatter = sistema
    turns, lock = [], threading.Lock()
    before = STATS.snapshot()["llm"]
    first_record = len(grabadora.records)

    def usuario(index):
        for number in range(turnos):
            text = escenarios.PREGUNTAS_E2E[(index + number) % len(escenarios.PREGUNTAS_E2E)]
            started = time.perf_counter()
            row = {"usuario": index + 1, "turno": number + 1, "pregunta": text}
            try:
                with turn_slot(text, max_wait=espera_turno * escala, poll_s=max(0.01, min(0.5, 0.5 * escala))) as waited:
                    row["wait_turn_s"] = round(waited / escala, 3)
                    context = ui_progress(queue_wait=espera_ui * escala) if espera_ui else nullcontext()
                    with context:
                        result, _ui = harness.ask(engine, cm, formatter, text)
                row["status"] = "error" if result.get("status") == "error" else "ok"
                row["route"] = result.get("route")
                row["synthesis_mode"] = result.get("synthesis_mode")
                row["fallback"] = result.get("synthesis_mode") == "extractive"
            except TurnBusy as busy:
                row.update(status="busy", busy=True, wait_turn_s=round(busy.waited_s / escala, 3))
            row["total_s"] = round((time.perf_counter() - started) / escala, 3)
            with lock:
                turns.append(row)
            if pausa:
                time.sleep(pausa * escala)

    wall = _arrancar(usuarios, usuario) / escala
    _esperar_puerta_libre()
    after = STATS.snapshot()["llm"]
    calls = list(grabadora.records[first_record:])
    # Las saturadas no llegan al servidor: se cuentan con los contadores.
    calls += [{"purpose": "e2e", "status": "llm_saturated"}] * max(0, after["saturated"] - before["saturated"])
    for row in turns:
        row["degraded"] = bool(row.get("fallback"))
    return calls, turns, wall


# ======================================================================
# corrida completa
# ======================================================================

def correr(modo="llm", rampa=(1, 3, 5, 10, 20), turnos=2, perfil="mixto", servidor=None,
           max_concurrent=None, espera_cola=None, espera_ui=None, espera_turno=120.0,
           sin_puerta=False, pausa=0.0, semilla=7, proveedor=None, real=False, log=print,
           parar_si_error=None):
    """Corre la rampa y devuelve el informe (dict). `proveedor` (real) sustituye
    al simulado; con él la escala es 1."""
    servidor = servidor or ServidorConfig()
    escala = 1.0 if proveedor is not None else float(servidor.escala)
    server = None
    if proveedor is None:
        server = ServidorSimulado(servidor)
        proveedor = ProveedorSimulado(server)
    from src.llm.llm_gate import default_queue_wait, max_concurrent as current_max
    espera_cola = float(espera_cola) if espera_cola is not None else default_queue_wait()
    max_concurrent = int(max_concurrent or current_max())
    config = {
        "modo": modo, "rampa": list(rampa), "turnos": turnos, "perfil": perfil if modo == "llm" else "preguntas_e2e",
        "real": bool(real), "escala": escala, "max_concurrent": max_concurrent, "espera_cola_s": espera_cola,
        "espera_ui_s": espera_ui, "espera_turno_s": espera_turno, "sin_puerta": sin_puerta, "pausa_s": pausa,
        "semilla": semilla, "servidor_simulado": None if real else servidor.as_dict(),
        "proveedor": type(proveedor).__name__, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    niveles = []
    env = _EnvTemporal(MEDGEMMA_MAX_CONCURRENT=max_concurrent, MEDGEMMA_QUEUE_WAIT=espera_cola * escala,
                       MEDGEMMA_QUEUE_WAIT_UI=(espera_ui * escala) if espera_ui else None)
    with env:
        sistema = restaurar = grabadora = None
        if modo == "e2e":
            grabadora = _Grabadora(proveedor, escala)
            harness, engine, cm, formatter, restaurar = _motor_e2e(grabadora, escala)
            sistema = (harness, engine, cm, formatter)
        llamador = _Llamador(proveedor, escala, espera_cola, espera_ui, sin_puerta) if modo == "llm" else None
        try:
            for usuarios in rampa:
                snap_before = server.snapshot() if server else None
                if modo == "llm":
                    calls, turns, wall = _nivel_llm(usuarios, turnos, perfil, llamador, semilla, pausa)
                else:
                    calls, turns, wall = _nivel_e2e(usuarios, turnos, sistema, grabadora, escala,
                                                    espera_turno, espera_ui, pausa)
                level = {
                    "usuarios": usuarios, "duracion_s": round(wall, 2),
                    "llamadas": metricas.resumen_llamadas(calls, wall),
                    "turnos": metricas.resumen_turnos(turns, wall),
                    "detalle_turnos": turns, "detalle_llamadas": calls,
                }
                if server is not None:
                    after = server.snapshot()
                    level["servidor"] = {k: after[k] - snap_before.get(k, 0) if k in (
                        "received", "completed", "rejected_503", "cancelled_queued", "cancelled_generating",
                        "truncated", "context_truncated") else after[k] for k in after}
                    server.stats["max_active"] = server.stats["max_queued"] = 0
                level["llamadas"]["paralelismo_observado"] = metricas.paralelismo_observado(calls)
                niveles.append(level)
                if log:
                    log(_fila(level))
                c = level["llamadas"]
                failing = c["tasa_error"] + c["tasa_tiempo_agotado"]
                if parar_si_error is not None and c["n"] and failing > parar_si_error:
                    level["detenido"] = (f"tasa de error + tiempo agotado {failing:.0%} > {parar_si_error:.0%}: "
                                         "se detiene la rampa")
                    if log:
                        log(level["detenido"])
                    break
        finally:
            if restaurar:
                restaurar()
    return {"config": config, "niveles": niveles}


# ======================================================================
# salida
# ======================================================================

COLUMNAS = [
    ("usuarios", 8), ("llamadas", 8), ("ok", 5), ("p50 s", 7), ("p95 s", 7), ("1er tok p95", 11),
    ("saturadas", 9), ("t.agotado", 9), ("error", 6), ("truncadas", 9), ("ok/min", 7),
    ("turno p95 s", 11), ("espera turno p95", 16), ("ocupado", 7), ("respaldo", 8), ("paralelo", 8),
]


def _pct(value):
    return "-" if value is None else f"{value * 100:.0f}%"


def _num(value):
    return "-" if value is None else f"{value:.1f}"


def _fila(level):
    c, t = level["llamadas"], level["turnos"]
    values = [
        str(level["usuarios"]), str(c["n"]), str(c["ok"]), _num(c["latencia_p50_s"]), _num(c["latencia_p95_s"]),
        _num(c["ttft_p95_s"]), _pct(c["tasa_saturadas"]), _pct(c["tasa_tiempo_agotado"]), _pct(c["tasa_error"]),
        _pct(c["tasa_truncadas"]), _num(c["throughput_ok_por_min"]), _num(t["total_p95_s"]),
        _num(t["espera_turno_p95_s"]), _pct(t["tasa_ocupado"]), _pct(t["tasa_respaldo_extractivo"]),
        str((c.get("paralelismo_observado") or {}).get("generando_max") or "-"),
    ]
    return " | ".join(value.rjust(width) for value, (_, width) in zip(values, COLUMNAS))


def tabla(report):
    header = " | ".join(name.rjust(width) for name, width in COLUMNAS)
    lines = [header, "-" * len(header)] + [_fila(level) for level in report["niveles"]]
    cfg = report["config"]
    lines.append(
        f"modo={cfg['modo']} perfil={cfg['perfil']} real={cfg['real']} max_concurrent={cfg['max_concurrent']}"
        f" espera_cola={cfg['espera_cola_s']} s espera_ui={cfg['espera_ui_s']} turnos/usuario={cfg['turnos']}"
        " · tiempos en segundos simulados; p50/p95 de llamadas exitosas; «truncadas» sobre las exitosas"
    )
    return "\n".join(lines)


def guardar(report, carpeta=None, etiqueta=None):
    carpeta = Path(carpeta) if carpeta else SALIDAS
    carpeta.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"carga_{report['config']['modo']}_{etiqueta + '_' if etiqueta else ''}{stamp}.json"
    path = carpeta / name
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path

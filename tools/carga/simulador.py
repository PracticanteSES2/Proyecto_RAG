"""
Servidor Ollama SIMULADO en proceso (sin red) y proveedor con la misma
interfaz que MedGemmaProvider, para medir la carga sin tocar el servidor del
hospital.

Modelo (todos los parámetros son supuestos configurables; calíbralos con una
corrida real de 1 usuario cuando haya permiso):

  * `num_parallel` generaciones a la vez (OLLAMA_NUM_PARALLEL); el resto espera
    en la cola del servidor en orden de llegada;
  * `max_queue` (OLLAMA_MAX_QUEUE): con la cola llena el servidor responde 503
    («server busy») y el proveedor devuelve status="ollama_error";
  * evaluación del prompt a `prompt_tps` tokens/s (≈ caracteres/4) y
    generación a `gen_tps` tokens/s por petición cuando está sola; con k
    peticiones generando a la vez cada una va a gen_tps / (1 + degradacion·(k-1))
    (la GPU se reparte: el total sube menos que linealmente);
  * largo «natural» de la respuesta = U(largo_min, largo_max) · max_tokens; si
    llega a max_tokens se corta (done_reason="length", truncated=True), igual
    que Ollama con num_predict;
  * `num_ctx`: si prompt + max_tokens no cabe, Ollama recorta la ENTRADA en
    silencio; aquí se marca `context_truncated`;
  * el tiempo límite del cliente (`timeout`) se respeta como en
    MedGemmaProvider (se cierra la conexión: el servidor deja de generar y
    libera el hueco) → status="llm_timeout";
  * `escala` multiplica todos los tiempos (0.05 = 20 veces más rápido); los
    resultados se reportan en segundos SIMULADOS (divididos por la escala).

El resultado de `chat` incluye `ttft_s` (primer token desde que empezó la
llamada) y `duration_s`, como si hubiera streaming.
"""
import random
import threading
import time
from dataclasses import asdict, dataclass

STEP_S = 0.01  # paso real de la simulación de la generación


@dataclass
class ServidorConfig:
    num_parallel: int = 3
    max_queue: int = 512
    prompt_tps: float = 1500.0
    gen_tps: float = 20.0
    degradacion: float = 0.5
    largo_min: float = 0.3
    largo_max: float = 1.1
    num_ctx: int = 4096
    escala: float = 1.0
    semilla: int = 7

    def as_dict(self):
        return asdict(self)


def prompt_tokens(messages):
    return max(1, sum(len(str(m.get("content") or "")) for m in messages or []) // 4)


class ServidorSimulado:
    def __init__(self, config=None):
        self.config = config or ServidorConfig()
        self._cond = threading.Condition()
        self._queue = []
        self._generating = 0
        self._rng = random.Random(self.config.semilla)
        self._rng_lock = threading.Lock()
        self.stats = {"received": 0, "completed": 0, "rejected_503": 0, "cancelled_queued": 0,
                      "cancelled_generating": 0, "max_active": 0, "max_queued": 0, "truncated": 0,
                      "context_truncated": 0}

    # ------------------------------------------------------------------
    def snapshot(self):
        with self._cond:
            return dict(self.stats, active=self._generating, queued=len(self._queue))

    def _sleep(self, simulated_s):
        time.sleep(max(0.0, simulated_s) * self.config.escala)

    def _natural_length(self, max_tokens):
        with self._rng_lock:
            factor = self._rng.uniform(self.config.largo_min, self.config.largo_max)
        return max(1, int(round(factor * max_tokens)))

    def generate(self, messages, max_tokens, deadline=None):
        """Atiende una petición. `deadline` es time.monotonic() REAL o None.
        Devuelve dict con status, tokens, done_reason, ttft_s y duration_s
        (segundos simulados)."""
        cfg = self.config
        started = time.monotonic()
        ticket = object()
        with self._cond:
            self.stats["received"] += 1
            if len(self._queue) >= cfg.max_queue:
                self.stats["rejected_503"] += 1
                return {"status": "rejected", "duration_s": 0.0}
            self._queue.append(ticket)
            self.stats["max_queued"] = max(self.stats["max_queued"], len(self._queue))
            while not (self._queue[0] is ticket and self._generating < cfg.num_parallel):
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    self._queue.remove(ticket)
                    self.stats["cancelled_queued"] += 1
                    self._cond.notify_all()
                    return {"status": "timeout", "phase": "cola",
                            "duration_s": (time.monotonic() - started) / cfg.escala}
                self._cond.wait(0.05 if remaining is None else min(0.05, remaining))
            self._queue.pop(0)
            self._generating += 1
            self.stats["max_active"] = max(self.stats["max_active"], self._generating)
            self._cond.notify_all()

        try:
            tokens_in = prompt_tokens(messages)
            context_truncated = tokens_in + max_tokens > cfg.num_ctx
            # Evaluación del prompt.
            prompt_s = tokens_in / max(1.0, cfg.prompt_tps)
            prompt_ends = time.monotonic() + prompt_s * cfg.escala
            while time.monotonic() < prompt_ends:
                if deadline is not None and time.monotonic() >= deadline:
                    return self._cut(started, "prompt")
                time.sleep(min(STEP_S, max(0.0, prompt_ends - time.monotonic())))
            ttft = (time.monotonic() - started) / cfg.escala
            target = self._natural_length(max_tokens)
            limit = min(target, max_tokens)
            produced = 0.0
            last = time.monotonic()
            while produced < limit:
                if deadline is not None and time.monotonic() >= deadline:
                    return self._cut(started, "generación", produced)
                time.sleep(STEP_S)
                now = time.monotonic()
                with self._cond:
                    active = max(1, self._generating)
                speed = cfg.gen_tps / (1.0 + cfg.degradacion * (active - 1))
                produced += speed * (now - last) / cfg.escala
                last = now
            truncated = target >= max_tokens
            with self._cond:
                self.stats["completed"] += 1
                if truncated:
                    self.stats["truncated"] += 1
                if context_truncated:
                    self.stats["context_truncated"] += 1
            return {
                "status": "success",
                "tokens": int(limit),
                "prompt_tokens": tokens_in,
                "done_reason": "length" if truncated else "stop",
                "context_truncated": context_truncated,
                "ttft_s": round(ttft, 3),
                "duration_s": round((time.monotonic() - started) / cfg.escala, 3),
            }
        finally:
            with self._cond:
                self._generating -= 1
                self._cond.notify_all()

    def _cut(self, started, phase, produced=0.0):
        with self._cond:
            self.stats["cancelled_generating"] += 1
        return {"status": "timeout", "phase": phase, "tokens": int(produced),
                "duration_s": (time.monotonic() - started) / self.config.escala}


class ProveedorSimulado:
    """Misma interfaz que MedGemmaProvider (chat/healthcheck/warmup) sobre un
    ServidorSimulado. `timeout` llega en segundos REALES (la puerta ya lo
    escaló) y se respeta como corte de conexión."""

    enforces_timeout = True

    def __init__(self, servidor=None, model="medgemma-simulado", default_timeout=180.0):
        self.servidor = servidor or ServidorSimulado()
        self.model = model
        self.host = "simulado://en-proceso"
        self.default_timeout = default_timeout

    def healthcheck(self):
        return {"status": "ready", "host": self.host, "model": self.model, "installed_models": [self.model]}

    def warmup(self, timeout=None):
        return {"status": "ready", "model": self.model, "host": self.host, "details": {}}

    def chat(self, messages, temperature=0.1, max_tokens=450, think=False, timeout=None, format=None):
        limit = float(timeout) if timeout else self.default_timeout * self.servidor.config.escala
        deadline = time.monotonic() + limit
        outcome = self.servidor.generate(messages, int(max_tokens or 450), deadline=deadline)
        base = {"model": self.model, "host": self.host, "duration_s": outcome.get("duration_s")}
        if outcome["status"] == "rejected":
            return dict(base, status="ollama_error", answer=None, status_code=503,
                        error="server busy, please try again (cola del servidor llena)")
        if outcome["status"] == "timeout":
            return dict(base, status="llm_timeout", answer=None,
                        timeout_seconds=limit / self.servidor.config.escala,
                        error=f"simulado: tiempo agotado en {outcome.get('phase')}")
        words = " ".join(["palabra"] * max(1, outcome["tokens"] // 2))
        return dict(
            base, status="success", answer=f"[simulado] {words}",
            done_reason=outcome["done_reason"], truncated=outcome["done_reason"] == "length",
            eval_count=outcome["tokens"], prompt_eval_count=outcome["prompt_tokens"],
            context_truncated=outcome["context_truncated"], ttft_s=outcome["ttft_s"],
        )

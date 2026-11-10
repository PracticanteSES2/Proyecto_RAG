import os
import threading
import time
from types import SimpleNamespace

from dotenv import load_dotenv
from ollama import Client, ResponseError

try:  # el cliente de Ollama usa httpx; sus timeouts se reconocen por tipo
    from httpx import TimeoutException as _HttpTimeout
except Exception:  # pragma: no cover - httpx siempre viene con ollama
    _HttpTimeout = ()


def _is_timeout(error):
    if _HttpTimeout and isinstance(error, _HttpTimeout):
        return True
    text = f"{type(error).__name__} {error}".lower()
    return "timed out" in text or "timeout" in text


def _auth_headers():
    """Encabezado de autenticación desde el .env (vacío si no hay token).

    MEDGEMMA_API_KEY     token entregado por el administrador del servidor.
    MEDGEMMA_AUTH_HEADER nombre del encabezado (por defecto Authorization).
    MEDGEMMA_AUTH_SCHEME prefijo del valor (por defecto Bearer; vacío = token solo).
    """
    token = os.getenv("MEDGEMMA_API_KEY", "").strip()
    if not token:
        return {}
    header = os.getenv("MEDGEMMA_AUTH_HEADER", "").strip() or "Authorization"
    scheme = os.getenv("MEDGEMMA_AUTH_SCHEME", "Bearer").strip()
    return {header: f"{scheme} {token}" if scheme else token}


def _avisar(on_token, texto):
    """La vista en vivo nunca tumba la llamada."""
    if on_token is None:
        return
    try:
        on_token(texto)
    except Exception:
        pass


def _leer_stream(partes, on_token, plazo_s):
    """Acumula el stream de Ollama avisando cada fragmento a `on_token`.

    Devuelve un objeto con la forma de la respuesta sin streaming
    (message.content, done_reason, eval_count) o None si se pasó el plazo
    total antes del último fragmento. httpx solo limita cada lectura; el plazo
    total se comprueba tras cada fragmento. Cerrar el generador cierra la
    conexión y Ollama deja de generar."""
    limite = time.monotonic() + plazo_s
    textos, ultima = [], None
    try:
        for parte in partes:
            ultima = parte
            texto = getattr(getattr(parte, "message", None), "content", None) or ""
            if texto:
                textos.append(texto)
                _avisar(on_token, texto)
            if not getattr(parte, "done", False) and time.monotonic() > limite:
                return None
    finally:
        cerrar = getattr(partes, "close", None)
        if callable(cerrar):
            cerrar()
    return SimpleNamespace(
        message=SimpleNamespace(content="".join(textos)),
        done_reason=getattr(ultima, "done_reason", None),
        eval_count=getattr(ultima, "eval_count", None),
    )


class MedGemmaProvider:
    """Adaptador remoto para MedGemma servido por Ollama."""

    # chat(timeout=...) corta la llamada a nivel HTTP (ver src/llm/llm_gate.py).
    enforces_timeout = True

    def __init__(
        self,
        host=None,
        model=None,
        timeout=None,
        keep_alive=None,
    ):
        load_dotenv()

        self.host = (
            host
            or os.getenv("MEDGEMMA_BASE_URL", "").strip()
        )

        self.model = (
            model
            or os.getenv(
                "MEDGEMMA_MODEL",
                "medgemma:latest",
            ).strip()
        )

        self.timeout = float(
            timeout
            or os.getenv(
                "MEDGEMMA_TIMEOUT",
                "180",
            )
        )

        self.keep_alive = (
            keep_alive
            or os.getenv(
                "MEDGEMMA_KEEP_ALIVE",
                "10m",
            )
        )

        if not self.host:
            raise ValueError(
                "MEDGEMMA_BASE_URL no está configurado en el .env."
            )

        if not self.host.startswith(("http://", "https://")):
            self.host = "http://" + self.host

        self.host = self.host.rstrip("/")

        # Token del servidor (MEDGEMMA_API_KEY en el .env): viaja en cada
        # petición como encabezado y nunca se escribe en logs ni trazas.
        self.headers = _auth_headers()

        self.client = Client(
            host=self.host,
            timeout=self.timeout,
            headers=self.headers,
        )

        # Un cliente por tiempo límite (se reutilizan: cada uno guarda su
        # conjunto de conexiones). El tiempo límite se aplica a nivel HTTP:
        # al vencer, httpx cierra la conexión y Ollama cancela la generación
        # (con un hilo + join la petición seguía abierta y el servidor seguía
        # generando para nadie).
        self._clients = {}
        self._clients_lock = threading.Lock()

    def _client_for(self, timeout):
        if not timeout or float(timeout) <= 0:
            return self.client
        key = round(float(timeout), 1)
        with self._clients_lock:
            client = self._clients.get(key)
            if client is None:
                client = Client(host=self.host, timeout=key, headers=self.headers)
                self._clients[key] = client
            return client

    def healthcheck(self):
        try:
            # Comprobación corta: no bloquea el arranque si el servidor no responde.
            response = self._client_for(
                float(os.getenv("MEDGEMMA_HEALTH_TIMEOUT", "15") or 15)
            ).list()

            models = getattr(
                response,
                "models",
                [],
            ) or []

            installed = []

            for item in models:
                name = (
                    getattr(item, "model", None)
                    or getattr(item, "name", None)
                )

                if name:
                    installed.append(str(name))

            model_available = any(
                name == self.model
                or name.startswith(f"{self.model}:")
                or self.model.startswith(f"{name}:")
                for name in installed
            )

            return {
                "status": (
                    "ready"
                    if model_available
                    else "model_missing"
                ),
                "host": self.host,
                "model": self.model,
                "installed_models": installed,
            }

        except Exception as exc:
            return {
                "status": "unavailable",
                "host": self.host,
                "model": self.model,
                "error": str(exc),
            }

    def chat(
        self,
        messages,
        temperature=0.1,
        max_tokens=450,
        think=False,
        timeout=None,
        format=None,
        stream=False,
        on_token=None,
    ):
        """`timeout` (s, opcional): tiempo límite de ESTA llamada a nivel HTTP;
        al vencer se cierra la conexión (el servidor deja de generar) y se
        devuelve status="llm_timeout". Sin él rige MEDGEMMA_TIMEOUT.

        `format` (opcional): "json" o un JSON schema (dict) para forzar una
        salida estructurada (Ollama restringe la generación a esa forma).

        `stream=True` + `on_token(texto)` (opcional): la respuesta llega por
        fragmentos (API de streaming de Ollama) y cada uno se avisa a
        `on_token` según llega; el dict devuelto es el MISMO que sin streaming
        (texto completo). Si `on_token` lanza, se ignora. El tiempo límite se
        aplica como plazo total: al vencer a mitad del stream se cierra la
        conexión y se devuelve "llm_timeout"."""
        client = self._client_for(timeout)
        request = {
            "model": self.model,
            "messages": messages,
            "stream": bool(stream),
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if format:
            request["format"] = format

        try:
            try:
                response = client.chat(**request, think=think)
            except TypeError:
                response = client.chat(**request)
            if stream:
                response = _leer_stream(response, on_token, float(timeout or self.timeout))
                if response is None:
                    return self._fallo_por_tiempo(timeout, "plazo total vencido a mitad del stream")
            return self._resultado(response)

        except ResponseError as exc:
            return {
                "status": "ollama_error",
                "answer": None,
                "model": self.model,
                "host": self.host,
                "error": str(exc),
                "status_code": getattr(exc, "status_code", None),
            }

        except Exception as exc:
            if _is_timeout(exc):
                return self._fallo_por_tiempo(timeout, f"{type(exc).__name__}: {exc}")
            return {
                "status": "ollama_error",
                "answer": None,
                "model": self.model,
                "host": self.host,
                "error": str(exc),
            }

    def _resultado(self, response):
        message = getattr(response, "message", None)
        content = getattr(message, "content", None) if message else None
        if not content:
            return {
                "status": "empty_response",
                "answer": None,
                "model": self.model,
                "host": self.host,
            }

        # done_reason="length": se llegó a num_predict (max_tokens) y la
        # respuesta quedó cortada a la mitad (campos añadidos; medición en
        # tools/carga).
        done_reason = getattr(response, "done_reason", None)
        return {
            "status": "success",
            "answer": str(content).strip(),
            "model": self.model,
            "host": self.host,
            "done_reason": done_reason,
            "truncated": done_reason == "length",
            "eval_count": getattr(response, "eval_count", None),
        }

    def _fallo_por_tiempo(self, timeout, error):
        return {
            "status": "llm_timeout",
            "answer": None,
            "model": self.model,
            "host": self.host,
            "timeout_seconds": float(timeout or self.timeout),
            "error": error,
        }

    def warmup(self, timeout=None):
        result = self.chat(
            messages=[
                {
                    "role": "user",
                    "content": "Responde únicamente: OK",
                }
            ],
            temperature=0.0,
            max_tokens=8,
            think=False,
            # Al arrancar no se espera más de MEDGEMMA_WARMUP_TIMEOUT (30 s):
            # un servidor ocupado no debe dejar la app sin cargar minutos.
            timeout=timeout or float(os.getenv("MEDGEMMA_WARMUP_TIMEOUT", "30") or 30),
        )

        return {
            "status": (
                "ready"
                if result.get("status") == "success"
                else result.get("status", "error")
            ),
            "model": self.model,
            "host": self.host,
            "details": result,
        }

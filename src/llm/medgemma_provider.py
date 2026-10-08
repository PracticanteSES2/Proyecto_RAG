import os

from dotenv import load_dotenv
from ollama import Client, ResponseError


class MedGemmaProvider:
    """Adaptador remoto para MedGemma servido por Ollama."""

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

        self.client = Client(
            host=self.host,
            timeout=self.timeout,
        )

    def healthcheck(self):
        try:
            response = self.client.list()

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
    ):
        request = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            try:
                response = self.client.chat(
                    **request,
                    think=think,
                )
            except TypeError:
                response = self.client.chat(**request)

            message = getattr(
                response,
                "message",
                None,
            )

            content = (
                getattr(message, "content", None)
                if message
                else None
            )

            if not content:
                return {
                    "status": "empty_response",
                    "answer": None,
                    "model": self.model,
                    "host": self.host,
                }

            return {
                "status": "success",
                "answer": str(content).strip(),
                "model": self.model,
                "host": self.host,
            }

        except ResponseError as exc:
            return {
                "status": "ollama_error",
                "answer": None,
                "model": self.model,
                "host": self.host,
                "error": str(exc),
                "status_code": getattr(
                    exc,
                    "status_code",
                    None,
                ),
            }

        except Exception as exc:
            return {
                "status": "ollama_error",
                "answer": None,
                "model": self.model,
                "host": self.host,
                "error": str(exc),
            }

    def warmup(self):
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

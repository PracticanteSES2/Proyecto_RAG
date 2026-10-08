import os
import re

from dotenv import load_dotenv
from ollama import Client, ResponseError


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)


def strip_think(text):
    """Quita bloques <think>...</think> (y uno abierto sin cerrar)."""
    if not text:
        return text
    text = _THINK_BLOCK.sub("", text)
    text = _THINK_OPEN.sub("", text)
    return text.strip()


def _with_tag(name):
    name = str(name).strip()
    return name if ":" in name else f"{name}:latest"


class OllamaProvider:

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
            or os.getenv(
                "OLLAMA_HOST",
                "http://localhost:11434",
            )
        )

        self.model = (
            model
            or os.getenv(
                "OLLAMA_MODEL",
                "qwen3:8b",
            )
        )

        self.timeout = float(
            timeout
            or os.getenv(
                "OLLAMA_TIMEOUT",
                "60",
            )
        )

        self.keep_alive = (
            keep_alive
            or os.getenv(
                "OLLAMA_KEEP_ALIVE",
                "30m",
            )
        )

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

            # Comparación exacta; un nombre sin etiqueta equivale a :latest.
            model_available = _with_tag(self.model) in {
                _with_tag(name) for name in installed
            }

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

    def warmup(self):
        try:
            self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": "Responde únicamente: OK",
                    }
                ],
                stream=False,
                think=False,
                keep_alive=self.keep_alive,
                options={
                    "temperature": 0,
                    "num_predict": 5,
                    "num_ctx": 2048,
                },
            )

            return {
                "status": "ready",
                "model": self.model,
            }

        except Exception as exc:
            return {
                "status": "error",
                "model": self.model,
                "error": str(exc),
            }

    def chat(
        self,
        messages,
        temperature=0.1,
        max_tokens=220,
        think=False,
    ):
        try:
            response = self.client.chat(
                model=self.model,
                messages=messages,
                stream=False,
                think=think,
                keep_alive=self.keep_alive,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "num_ctx": 4096,
                },
            )

            content = (
                response.message.content
                if getattr(
                    response,
                    "message",
                    None,
                )
                else None
            )

            content = strip_think(content)

            if not content:
                return {
                    "status": "empty_response",
                    "answer": None,
                    "model": self.model,
                }

            return {
                "status": "success",
                "answer": content,
                "model": self.model,
            }

        except ResponseError as exc:
            return {
                "status": "ollama_error",
                "answer": None,
                "model": self.model,
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
                "error": str(exc),
            }

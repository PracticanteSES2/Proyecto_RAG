"""
Proveedores REALES para `--real` (solo se construyen tras la confirmación).

  * `MedGemmaProvider` tal cual (sin streaming: lo mismo que usa la app).
  * `SondaStreaming`: misma llamada con stream=True para medir el tiempo hasta
    el primer token (lo que vería el usuario si la app hiciera streaming). El
    tiempo límite se aplica al TOTAL (en streaming el de httpx es por lectura):
    al vencer se cierra la respuesta y Ollama deja de generar.

El .env lo lee el propio MedGemmaProvider (load_dotenv) al construirse; esta
herramienta nunca lo abre ni imprime el token.
"""
import time


def crear_proveedor_real(streaming=False):
    from src.llm.medgemma_provider import MedGemmaProvider
    base = MedGemmaProvider()
    return SondaStreaming(base) if streaming else base


class SondaStreaming:
    enforces_timeout = True

    def __init__(self, base):
        self.base = base
        self.model = base.model
        self.host = base.host

    def healthcheck(self):
        return self.base.healthcheck()

    def chat(self, messages, temperature=0.1, max_tokens=450, think=False, timeout=None, format=None):
        from src.llm.medgemma_provider import _is_timeout

        limit = float(timeout or self.base.timeout)
        client = self.base._client_for(limit)
        request = {
            "model": self.base.model, "messages": messages, "stream": True,
            "keep_alive": self.base.keep_alive,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if format:
            request["format"] = format
        started = time.perf_counter()
        ttft = None
        parts = []
        done_reason = None
        eval_count = None
        stream = None
        try:
            stream = client.chat(**request, think=think)
            for chunk in stream:
                message = getattr(chunk, "message", None)
                text = getattr(message, "content", None) if message else None
                if text:
                    if ttft is None:
                        ttft = time.perf_counter() - started
                    parts.append(text)
                if getattr(chunk, "done", False):
                    done_reason = getattr(chunk, "done_reason", None)
                    eval_count = getattr(chunk, "eval_count", None)
                if time.perf_counter() - started > limit:
                    return {"status": "llm_timeout", "answer": None, "model": self.model, "host": self.host,
                            "timeout_seconds": limit, "ttft_s": ttft,
                            "duration_s": time.perf_counter() - started,
                            "error": f"sin terminar en {limit:.1f} s (streaming cortado)"}
        except Exception as exc:
            status = "llm_timeout" if _is_timeout(exc) else "ollama_error"
            return {"status": status, "answer": None, "model": self.model, "host": self.host,
                    "ttft_s": ttft, "duration_s": time.perf_counter() - started,
                    "error": f"{type(exc).__name__}: {exc}",
                    "status_code": getattr(exc, "status_code", None)}
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        answer = "".join(parts).strip()
        if not answer:
            return {"status": "empty_response", "answer": None, "model": self.model, "host": self.host,
                    "ttft_s": ttft, "duration_s": time.perf_counter() - started}
        return {"status": "success", "answer": answer, "model": self.model, "host": self.host,
                "done_reason": done_reason, "truncated": done_reason == "length", "eval_count": eval_count,
                "ttft_s": round(ttft, 3) if ttft is not None else None,
                "duration_s": round(time.perf_counter() - started, 3)}

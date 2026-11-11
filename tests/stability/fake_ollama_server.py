"""
Servidor HTTP local que imita a Ollama (/api/tags y /api/chat, con o sin
streaming NDJSON) para las pruebas de estabilidad y de streaming. Se ejecuta en un hilo y solo escucha en
127.0.0.1 (puerto libre elegido por el sistema).

Modela lo que importa para el problema reportado:

  * capacidad limitada: `parallel` generaciones a la vez (como
    OLLAMA_NUM_PARALLEL); el resto espera en cola;
  * duración variable por petición (`delay_fn(request) -> segundos`);
  * cancelación como Ollama: si el cliente CIERRA la conexión mientras la
    petición espera o se genera, se abandona y libera el hueco. Si el cliente
    deja la conexión abierta (hilo daemon abandonado), sigue generando.
  * streaming ("stream": true): tras la espera inicial envía la respuesta por
    palabras, una línea JSON cada `stream_chunk_s` s, con el hueco ocupado; si
    el cliente cierra a mitad, cuenta "cancelled_streaming".

`stats` cuenta peticiones recibidas, completadas, canceladas (en cola o
generando), máximo de generaciones simultáneas y cola máxima.
"""
import json
import random
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

POLL_S = 0.02


def _client_closed(sock):
    """¿El cliente cerró la conexión? (lectura disponible con 0 bytes)."""
    try:
        readable, _, _ = select.select([sock], [], [], 0)
        if not readable:
            return False
        return sock.recv(1, socket.MSG_PEEK) == b""
    except (OSError, ValueError):
        return True


def default_content(request):
    user = next((m.get("content", "") for m in reversed(request.get("messages") or [])
                 if m.get("role") == "user"), "")
    if "CONTEXTO RECUPERADO" in user:
        return "[FakeHTTP] El tablero muestra los indicadores documentados."
    if "ÚLTIMO MENSAJE" in user:
        return "¿Cuántas cirugías programadas de urología hubo en 2024?"
    if "Indicador:" in user:
        return "1. Cuenta las cirugías registradas en el periodo."
    return "OK"


class FakeOllamaServer:
    def __init__(self, delay_fn=None, parallel=2, content_fn=None):
        self.delay_fn = delay_fn or (lambda request: 0.05)
        self.content_fn = content_fn or default_content
        self.slots = threading.BoundedSemaphore(parallel)
        self.parallel = parallel
        self._lock = threading.Lock()
        self.stats = {
            "received": 0, "completed": 0, "cancelled_queued": 0, "cancelled_generating": 0,
            "active": 0, "queued": 0, "max_active": 0, "max_queued": 0, "cancelled_streaming": 0,
        }
        self.stream_chunk_s = 0.0
        self.events = []  # (instante, tipo, duración pedida)
        self.live = {}  # peticiones en curso (en cola o generando)
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # silencio
                pass

            def _send_json(self, payload, code=200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.startswith("/api/tags"):
                    self._send_json({"models": [{"name": "medgemma:latest", "model": "medgemma:latest"}]})
                else:
                    self._send_json({"error": "no encontrado"}, 404)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                request = json.loads(self.rfile.read(length) or b"{}")
                if not self.path.startswith("/api/chat"):
                    self._send_json({"error": "no encontrado"}, 404)
                    return
                server._chat(self, request)

        class Server(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass  # conexiones cerradas por el cliente: es lo esperado

        self.httpd = Server(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="fake-ollama", daemon=True)

    # ------------------------------------------------------------------
    def _count(self, key, delta=1):
        with self._lock:
            self.stats[key] += delta
            self.stats["max_active"] = max(self.stats["max_active"], self.stats["active"])
            self.stats["max_queued"] = max(self.stats["max_queued"], self.stats["queued"])

    def _chat(self, handler, request):
        sock = handler.connection
        duration = float(self.delay_fn(request))
        key = object()
        with self._lock:
            self.live[key] = {
                "since": time.time(), "duration": round(duration, 2),
                "num_predict": (request.get("options") or {}).get("num_predict"),
            }
        try:
            self._chat_inner(handler, request, sock, duration)
        finally:
            with self._lock:
                self.live.pop(key, None)

    def _chat_inner(self, handler, request, sock, duration):
        self._count("received")
        self._count("queued")
        try:
            while not self.slots.acquire(timeout=POLL_S):
                if _client_closed(sock):
                    self._count("cancelled_queued")
                    self.events.append((time.time(), "cancelled_queued", duration))
                    handler.close_connection = True
                    return
        finally:
            self._count("queued", -1)
        self._count("active")
        try:
            ends = time.time() + duration
            while time.time() < ends:
                if _client_closed(sock):
                    self._count("cancelled_generating")
                    self.events.append((time.time(), "cancelled_generating", duration))
                    handler.close_connection = True
                    return
                time.sleep(POLL_S)
            if request.get("stream"):
                self._finish_stream(handler, request, sock, duration)
                return
            self._count("completed")
            self.events.append((time.time(), "completed", duration))
        finally:
            self._count("active", -1)
            self.slots.release()
        try:
            handler._send_json({
                "model": request.get("model") or "medgemma:latest",
                "created_at": "2026-01-01T00:00:00Z",
                "message": {"role": "assistant", "content": self.content_fn(request)},
                "done": True,
                "done_reason": "stop",
            })
        except OSError:
            handler.close_connection = True

    def _finish_stream(self, handler, request, sock, duration):
        ok = self._stream(handler, request, sock)
        kind = "completed" if ok else "cancelled_streaming"
        self._count(kind)
        self.events.append((time.time(), kind, duration))
        handler.close_connection = True

    def _stream(self, handler, request, sock):
        """Respuesta NDJSON por palabras (transferencia por trozos). False si
        el cliente cerró la conexión a mitad."""
        words = self.content_fn(request).split(" ")
        model = request.get("model") or "medgemma:latest"

        def chunk(payload):
            data = (json.dumps(payload) + "\n").encode("utf-8")
            handler.wfile.write(f"{len(data):X}\r\n".encode("ascii") + data + b"\r\n")
            handler.wfile.flush()

        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "application/x-ndjson")
            handler.send_header("Transfer-Encoding", "chunked")
            handler.end_headers()
            for index, word in enumerate(words):
                if _client_closed(sock):
                    return False
                chunk({"model": model, "created_at": "2026-01-01T00:00:00Z",
                       "message": {"role": "assistant", "content": word if index == 0 else " " + word},
                       "done": False})
                if self.stream_chunk_s:
                    time.sleep(self.stream_chunk_s)
            chunk({"model": model, "created_at": "2026-01-01T00:00:00Z",
                   "message": {"role": "assistant", "content": ""}, "done": True,
                   "done_reason": "stop", "eval_count": len(words)})
            handler.wfile.write(b"0\r\n\r\n")
            handler.wfile.flush()
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    def snapshot(self):
        with self._lock:
            return dict(self.stats)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def variable_delay(seed=7, per_token_s=0.004, base_s=0.3, spike_every=7, spike_factor=4.0):
    """Duración pseudoaleatoria y reproducible: proporcional a num_predict,
    con factor 0.5-2.5 y un pico lento cada `spike_every` peticiones."""
    rng = random.Random(seed)
    counter = {"n": 0}
    lock = threading.Lock()

    def delay(request):
        with lock:
            counter["n"] += 1
            factor = rng.uniform(0.5, 2.5)
            spike = counter["n"] % spike_every == 0
        tokens = float(((request.get("options") or {}).get("num_predict")) or 200)
        seconds = (base_s + tokens * per_token_s) * factor
        return seconds * (spike_factor if spike else 1.0)

    return delay

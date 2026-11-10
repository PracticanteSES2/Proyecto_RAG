"""Apoyo común de las pruebas del backend (sin red, sin Redis real, sin .env).

    python -X utf8 -m unittest discover -s tests/backend -t .
    python -X utf8 -m unittest discover -s tests/api -t .
"""
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
sys.dont_write_bytecode = True
# Las calificaciones de las pruebas nunca van a data/feedback.
os.environ["FEEDBACK_DIR"] = tempfile.mkdtemp(prefix="feedback_backend_")

MODOS = ("memoria", "redis")


def ajustes_prueba(**cambios):
    from backend.app.core.config import Ajustes

    base = {"redis_url": None, "backend_secreto": "secreto-de-prueba", "latido_s": 0.2, "sse_bloqueo_ms": 100,
            "sse_ping_s": 0.5, "cache_ttl_s": 60, "backend_log_nivel": "WARNING", "rag_raiz_datos": RAIZ}
    base.update(cambios)
    return Ajustes(**base)


def almacenes(modo: str):
    """(almacén API, almacén trabajador, servidor fakeredis o None)."""
    from backend.app.services.claves import Claves

    if modo == "memoria":
        from backend.app.services.almacen_memoria import AlmacenMemoria

        almacen = AlmacenMemoria()
        return almacen, almacen, None
    import fakeredis

    from backend.app.services.almacen_redis import AlmacenRedis, AlmacenTrabajadorRedis

    servidor = fakeredis.FakeServer()
    claves = Claves("prueba")
    return (AlmacenRedis(fakeredis.FakeAsyncRedis(server=servidor), claves),
            AlmacenTrabajadorRedis(fakeredis.FakeRedis(server=servidor), claves), servidor)

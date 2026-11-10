"""Apoyo común de las pruebas del backend: HERMÉTICAS.

Dan lo mismo en cualquier checkout (con o sin `.env` y `data/` reales) y nunca
contactan servicios: almacén en memoria o fakeredis, motor doble, una raíz de
datos vacía y temporal (sin catálogos, Qdrant ni docs_tableros reales) y
ajustes que ignoran las variables de entorno del proceso.

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

# Raíz de datos vacía: el normalizador, la huella y las capacidades no leen los
# datos reales del checkout (que cambian y en el principal son grandes).
RAIZ_VACIA = Path(tempfile.mkdtemp(prefix="raiz_backend_"))
(RAIZ_VACIA / "docs_tableros").mkdir()

MODOS = ("memoria", "redis")


def _clase_ajustes():
    from pydantic_settings import BaseSettings

    from backend.app.core.config import Ajustes

    class AjustesPrueba(Ajustes):
        """Solo los valores pasados al construirla: ninguna variable de entorno
        del proceso (REDIS_URL, MOTOR_MODO, LIMITE_*…) cambia las pruebas."""

        @classmethod
        def settings_customise_sources(cls, settings_cls: type[BaseSettings], init_settings, **otras):
            return (init_settings,)

    return AjustesPrueba


def ajustes_prueba(**cambios):
    base = {"redis_url": None, "backend_secreto": "secreto-de-prueba", "latido_s": 0.2, "sse_bloqueo_ms": 100,
            "sse_ping_s": 0.5, "cache_ttl_s": 60, "backend_log_nivel": "WARNING", "rag_raiz_datos": RAIZ_VACIA}
    base.update(cambios)
    return _clase_ajustes()(**base)


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

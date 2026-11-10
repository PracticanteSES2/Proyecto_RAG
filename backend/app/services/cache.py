"""Caché de respuestas: reglas, clave y huella de la versión de datos.

Clave = sha256(huella | fecha local | pregunta normalizada). La pregunta se
normaliza con el MISMO normalizador del motor (`normalize_question`, lenguaje
de chat y tipeos contra el catálogo) y luego sin mayúsculas, tildes ni signos.
La huella cambia si cambia el código (git HEAD) o cualquier archivo de
data/catalog, data/rag, data/model_metadata o data/vector_db (tamaño y fecha),
así una reindexación o un catálogo nuevo invalidan la caché sin borrar nada.
La fecha la invalida cada día (las cifras de Power BI se refrescan a diario) y
el TTL (CACHE_TTL_S, 15 min) acota lo que puede envejecer dentro del día.

Nunca se cachea un turno con contexto (seguimiento, contrapregunta pendiente,
opción elegida, memoria de la conversación) ni una respuesta degradada, con
error, una contrapregunta o una charla del portero.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import threading
import time
from datetime import date
from pathlib import Path

from backend.app.services.motor import sin_contexto

CARPETAS_HUELLA = (("data", "catalog"), ("data", "rag"), ("data", "model_metadata"), ("data", "vector_db"))
_IGNORAR = {".lock"}
_SIGNOS = re.compile(r"[¿?¡!.,;:«»\"'()\[\]]+")


def normalizar_pregunta(texto: str, raiz: Path | None = None) -> str:
    try:
        from src.semantic.question_normalizer import fold, normalize_question, vocabulary_for

        normalizada = normalize_question(texto, vocabulary_for(raiz))
        base = normalizada.text if normalizada is not None and normalizada.text else texto
        base = fold(base)
    except Exception:
        base = str(texto or "").lower()
    return " ".join(_SIGNOS.sub(" ", base).split())


def clave_cache(huella: str, pregunta_normalizada: str, fecha: date | None = None) -> str:
    fecha = fecha or date.today()
    return hashlib.sha256(f"{huella}|{fecha.isoformat()}|{pregunta_normalizada}".encode()).hexdigest()


def puede_leer(turno: dict, estado_previo, habilitada: bool = True, vacio=sin_contexto) -> bool:
    return bool(habilitada) and not turno.get("opcion_id") and vacio(estado_previo)


def puede_guardar(result: dict, respuesta: dict, estado_previo, turno: dict,
                  habilitada: bool = True, vacio=sin_contexto) -> bool:
    if not habilitada or turno.get("opcion_id") or not vacio(estado_previo):
        return False
    if not isinstance(result, dict) or result.get("status") != "success" or result.get("cacheable") is False:
        return False   # cacheable=False: respuesta truncada sin completar (spec 011)
    if result.get("route") not in ("powerbi", "rag"):
        return False
    if result.get("synthesis_mode") == "extractive" or respuesta.get("degradada"):
        return False
    return not respuesta.get("contrapregunta")


def version_codigo(raiz_codigo: Path) -> str:
    try:
        salida = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=raiz_codigo, capture_output=True,
                                text=True, timeout=5)
        return salida.stdout.strip() or "sin-git"
    except Exception:
        return "sin-git"


class Huella:
    """Huella de la versión de datos/catálogo/código, recalculada cada
    `intervalo_s` (solo stat de archivos: barato)."""

    def __init__(self, raiz_datos: Path, raiz_codigo: Path, intervalo_s: float = 60.0, reloj=time.monotonic):
        self.raiz_datos = Path(raiz_datos)
        self.raiz_codigo = Path(raiz_codigo)
        self.intervalo_s = intervalo_s
        self._reloj = reloj
        self._valor = None
        self._calculada = None
        self._candado = threading.Lock()
        self.version = version_codigo(self.raiz_codigo)

    def _calcular(self) -> str:
        resumen = hashlib.sha256(self.version.encode("utf-8"))
        for partes in CARPETAS_HUELLA:
            carpeta = self.raiz_datos.joinpath(*partes)
            if not carpeta.exists():
                resumen.update(f"{'/'.join(partes)}:ausente".encode())
                continue
            for archivo in sorted(p for p in carpeta.rglob("*") if p.is_file() and p.name not in _IGNORAR):
                try:
                    info = archivo.stat()
                except OSError:
                    continue
                relativo = archivo.relative_to(self.raiz_datos).as_posix()
                resumen.update(f"{relativo}|{info.st_size}|{info.st_mtime_ns}\n".encode())
        return resumen.hexdigest()[:24]

    def valor(self) -> str:
        with self._candado:
            ahora = self._reloj()
            if self._valor is None or ahora - self._calculada >= self.intervalo_s:
                self._valor = self._calcular()
                self._calculada = ahora
            return self._valor

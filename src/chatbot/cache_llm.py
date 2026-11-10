"""
Caché de llamadas al LLM dentro del motor (specs/010-rendimiento-llm).

MedGemma da unas pocas respuestas redactadas por minuto en total; una pregunta
documental repetida (misma pregunta normalizada, mismas fuentes, mismo prompt)
o la descripción de una opción ya descrita no necesitan volver a generarse.
Aquí se guarda la respuesta CRUDA del LLM: quien llama aplica siempre su
post-proceso (limpieza, grounding, truncado), también a lo que sale de caché.

Uso (síntesis RAG, descripción de opciones):

    k = cache_llm.clave("síntesis RAG", pregunta, fuentes=contexto, prompt=instrucciones,
                        modelo=proveedor.model, max_tokens=600)
    resultado = cache_llm.llamar_con_cache(k, lambda: call_llm(...), proposito="síntesis RAG")
    resultado.get("cache")  # "hit" | "compartida" | ausente (llamada real)

Clave = sha256(formato | versión de índice/documentación | propósito | pregunta
normalizada con `question_normalizer.clave_pregunta` (la MISMA que usa la caché
de respuestas del API) | huella de las fuentes | huella del prompt | modelo |
max_tokens). Si cambia un chunk, el prompt o el modelo, la clave cambia sola.
`fijar_version(v)` añade una versión explícita (p. ej. la huella de datos del
API) para invalidar todo tras reindexar.

Nunca se guarda una respuesta degradada (saturada, tiempo agotado, error),
vacía o truncada (`truncated` / `done_reason="length"`); quien llama puede
añadir su propio criterio (`es_guardable`, p. ej. «sin evidencia»).

Peticiones idénticas simultáneas: la primera llama al LLM y las demás esperan
su resultado (una sola generación). Si la primera falla, cada una llama por su
cuenta (como sin caché).

Almacén enchufable (`AlmacenCache`): memoria LRU con TTL por defecto (un
proceso). Con varios workers, el API instala el de Redis
(`backend/app/services/cache_llm_redis.py`) con `configurar_almacen(...)`;
`src` no importa `redis` (docs/ARQUITECTURA.md §4). Si el almacén falla, la
llamada sigue sin caché (advertencia en el log «cache_llm»).

Variables: LLM_CACHE (on/off, por defecto on), LLM_CACHE_TTL_S (21600 = 6 h),
LLM_CACHE_MAX (512 entradas en memoria), LLM_CACHE_ESPERA_S (90: espera máxima
por una petición idéntica en curso).
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Callable, Protocol

from src.chatbot.runtime_stats import STATS, env_float, env_int
from src.semantic.question_normalizer import clave_pregunta

LOG = logging.getLogger("cache_llm")

FORMATO = "1"  # súbelo si cambia lo que se guarda
_CAMPOS = ("status", "answer", "model", "done_reason", "truncated", "eval_count", "prompt_eval_count")


class AlmacenCache(Protocol):
    """Interfaz del almacén. `leer` devuelve una copia o None; ambos pueden
    lanzar (almacén caído): `llamar_con_cache` lo absorbe."""

    nombre: str

    def leer(self, clave: str) -> dict | None: ...

    def guardar(self, clave: str, valor: dict, ttl_s: float) -> None: ...


class AlmacenMemoria:
    """LRU con vencimiento, seguro entre hilos (un proceso)."""

    nombre = "memoria"

    def __init__(self, max_entradas: int | None = None, reloj: Callable[[], float] = time.monotonic):
        self.max_entradas = max_entradas or env_int("LLM_CACHE_MAX", 512)
        self.reloj = reloj
        self._datos: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = threading.Lock()

    def leer(self, clave: str) -> dict | None:
        with self._lock:
            item = self._datos.get(clave)
            if item is None:
                return None
            vence, valor = item
            if vence <= self.reloj():
                del self._datos[clave]
                return None
            self._datos.move_to_end(clave)
            return copy.deepcopy(valor)

    def guardar(self, clave: str, valor: dict, ttl_s: float) -> None:
        with self._lock:
            self._datos[clave] = (self.reloj() + float(ttl_s), copy.deepcopy(valor))
            self._datos.move_to_end(clave)
            while len(self._datos) > self.max_entradas:
                self._datos.popitem(last=False)

    def limpiar(self) -> None:
        with self._lock:
            self._datos.clear()

    def __len__(self) -> int:
        return len(self._datos)


_ESTADO: dict = {"almacen": None, "version": ""}
_ESTADO_LOCK = threading.Lock()


def configurar_almacen(almacen: AlmacenCache | None = None) -> None:
    """Instala el almacén (None = memoria nueva). Lo hace el arranque del API
    con Redis; las pruebas, con uno limpio."""
    with _ESTADO_LOCK:
        _ESTADO["almacen"] = almacen


def almacen_actual() -> AlmacenCache:
    with _ESTADO_LOCK:
        if _ESTADO["almacen"] is None:
            _ESTADO["almacen"] = AlmacenMemoria()
        return _ESTADO["almacen"]


def fijar_version(version: str | None) -> None:
    """Versión del índice/documentación que entra en todas las claves."""
    _ESTADO["version"] = str(version or "")


def habilitada() -> bool:
    return str(os.getenv("LLM_CACHE", "on")).strip().lower() not in ("off", "0", "no", "false")


def ttl_s() -> float:
    return env_float("LLM_CACHE_TTL_S", 21600.0)


def huella(*partes) -> str:
    texto = json.dumps(partes, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def clave(proposito: str, pregunta: str = "", fuentes="", prompt="", modelo: str = "",
          max_tokens: int | None = None) -> str:
    """Clave de una llamada (ver el docstring del módulo)."""
    return huella(FORMATO, _ESTADO["version"], proposito, clave_pregunta(pregunta) if pregunta else "",
                  huella(fuentes), huella(prompt), str(modelo or ""), max_tokens)


def modelo_de(proveedor) -> str:
    """Nombre del modelo para la clave. Un proveedor sin `model` (dobles de
    prueba) solo comparte caché consigo mismo."""
    nombre = getattr(proveedor, "model", None)
    return str(nombre) if nombre else f"{type(proveedor).__qualname__}@{id(proveedor)}"


def guardable(resultado) -> bool:
    """Solo respuestas completas: éxito, con texto y sin cortar por num_predict."""
    return (
        isinstance(resultado, dict)
        and resultado.get("status") == "success"
        and bool(str(resultado.get("answer") or "").strip())
        and not resultado.get("truncated")
        and resultado.get("done_reason") != "length"
    )


class _EnCurso:
    __slots__ = ("listo", "resultado")

    def __init__(self):
        self.listo = threading.Event()
        self.resultado = None


_EN_CURSO: dict[str, _EnCurso] = {}
_EN_CURSO_LOCK = threading.Lock()


def _leer(clave_: str):
    try:
        return almacen_actual().leer(clave_)
    except Exception as error:
        STATS.llm_cache_event("errors")
        LOG.warning("cache_llm: no se pudo leer (%s: %s); se llama al LLM", type(error).__name__, error)
        return None


def _guardar(clave_: str, resultado: dict) -> None:
    valor = {campo: resultado[campo] for campo in _CAMPOS if campo in resultado}
    try:
        almacen_actual().guardar(clave_, valor, ttl_s())
        STATS.llm_cache_event("stores")
    except Exception as error:
        STATS.llm_cache_event("errors")
        LOG.warning("cache_llm: no se pudo guardar (%s: %s)", type(error).__name__, error)


def _turno_de(clave_: str):
    """(registro, soy_la_primera) de la petición en curso con esta clave."""
    with _EN_CURSO_LOCK:
        actual = _EN_CURSO.get(clave_)
        if actual is not None:
            return actual, False
        actual = _EnCurso()
        _EN_CURSO[clave_] = actual
        return actual, True


def _llamar_y_guardar(clave_, llamar, es_guardable):
    STATS.llm_cache_event("misses")
    resultado = llamar()
    if guardable(resultado) and es_guardable(resultado):
        _guardar(clave_, resultado)
    else:
        STATS.llm_cache_event("not_stored")
    return resultado


def llamar_con_cache(clave_: str, llamar: Callable[[], dict], proposito: str = "otro",
                     es_guardable: Callable[[dict], bool] = guardable) -> dict:
    """Resultado de la caché o de `llamar()` (que nunca debería lanzar, como
    `call_llm`). Ver el docstring del módulo."""
    if not habilitada():
        return llamar()
    guardado = _leer(clave_)
    if guardado is not None:
        STATS.llm_cache_event("hits")
        STATS.llm_call_avoided(f"caché: {proposito}")
        return dict(guardado, cache="hit")
    registro, primera = _turno_de(clave_)
    if not primera:
        registro.listo.wait(env_float("LLM_CACHE_ESPERA_S", 90.0))
        compartido = registro.resultado
        if guardable(compartido) and es_guardable(compartido):
            STATS.llm_cache_event("shared")
            STATS.llm_call_avoided(f"compartida: {proposito}")
            return dict(compartido, cache="compartida")
        return _llamar_y_guardar(clave_, llamar, es_guardable)
    try:
        registro.resultado = _llamar_y_guardar(clave_, llamar, es_guardable)
        return registro.resultado
    finally:
        registro.listo.set()
        with _EN_CURSO_LOCK:
            _EN_CURSO.pop(clave_, None)

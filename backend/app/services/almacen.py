"""Interfaces del almacén (estado compartido entre la API y el trabajador).

Dos lados:

- `AlmacenAPI` (asíncrono): lo usa FastAPI. Nunca bloquea el ciclo de eventos.
- `AlmacenTrabajador` (síncrono): lo usa el proceso dueño del motor, desde hilos.

Implementaciones: Redis (`almacen_redis.py`, producción, varios procesos) y
memoria (`almacen_memoria.py`, un solo proceso: desarrollo y pruebas).

Formas de los datos (dicts JSON):

- turno: {turno_id, conversacion_id, mensaje, opcion_id, opcion_texto, via,
  diagnostico (bool), cliente, estado ("en_cola"|"procesando"|"terminado"|"error"),
  creado (iso), creado_ms, iniciado_ms, terminado_ms, respuesta (dict|None),
  error (dict|None), snapshot (dict|None), calificacion (dict|None)}
- conversación: {conversacion_id, creada, actualizada, opciones (list),
  frases (list), mensajes (list), turno_activo (str|None)}
- evento: (id, nombre, datos) — el id es el del stream (orden total por turno).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Protocol, runtime_checkable

ESTADOS_FINALES = ("terminado", "error")
CAMPOS_JSON_TURNO = ("respuesta", "error", "snapshot", "calificacion")


def ahora_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def a_json(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)


def turno_a_hash(turno: dict) -> dict[str, str]:
    """dict del turno → campos de texto (HSET)."""
    salida = {}
    for clave, valor in turno.items():
        if clave.startswith("_"):
            continue
        if clave in CAMPOS_JSON_TURNO:
            salida[clave] = a_json(valor) if valor is not None else ""
        elif isinstance(valor, bool):
            salida[clave] = "1" if valor else "0"
        elif valor is None:
            salida[clave] = ""
        else:
            salida[clave] = str(valor)
    return salida


def turno_de_hash(campos: dict) -> dict | None:
    if not campos:
        return None
    turno = {}
    for clave, valor in campos.items():
        clave = clave.decode() if isinstance(clave, bytes) else clave
        valor = valor.decode() if isinstance(valor, bytes) else valor
        if clave in CAMPOS_JSON_TURNO:
            turno[clave] = json.loads(valor) if valor else None
        elif clave == "diagnostico":
            turno[clave] = valor == "1"
        elif clave.endswith("_ms"):
            turno[clave] = int(valor) if valor else None
        else:
            turno[clave] = valor or None
    return turno


@runtime_checkable
class AlmacenAPI(Protocol):
    modo: str

    async def ping(self) -> bool: ...
    async def crear_conversacion(self, conversacion_id: str, ttl_s: int) -> None: ...
    async def conversacion(self, conversacion_id: str) -> dict | None: ...
    async def reservar_turno(self, conversacion_id: str, turno_id: str, ttl_s: int) -> bool: ...
    async def liberar_reserva(self, conversacion_id: str, turno_id: str) -> None: ...
    async def encolar_turno(self, turno: dict, cola_max: int, ttl_s: int) -> bool: ...
    async def turno(self, turno_id: str) -> dict | None: ...
    async def leer_eventos(self, turno_id: str, desde: str, bloqueo_ms: int) -> list[tuple[str, str, dict]]: ...
    async def eventos_existen(self, turno_id: str) -> bool: ...
    async def posicion(self, turno_id: str) -> tuple[int, int]: ...
    async def resumen_cola(self) -> dict: ...
    async def registrar_peticion(self, cliente: str, limite: int, ventana_s: int) -> float | None: ...
    async def marcar_calificacion(self, turno_id: str, calificacion: dict) -> bool: ...
    async def leer_motor(self, nombre: str) -> dict | None: ...
    async def cerrar(self) -> None: ...


@runtime_checkable
class AlmacenTrabajador(Protocol):
    modo: str

    def tomar_turno(self, consumidor: str, bloqueo_ms: int) -> dict | None: ...
    def confirmar(self, turno: dict) -> None: ...
    def recuperar_huerfanos(self, consumidor: str, inactivo_ms: int) -> list[dict]: ...
    def iniciar_turno(self, turno_id: str) -> None: ...
    def publicar_evento(self, turno_id: str, evento: str, datos: dict, ttl_s: int | None = None) -> str: ...
    def terminar_turno(self, turno: dict, campos: dict, eventos_ttl_s: int) -> None: ...
    def meta_conversacion(self, conversacion_id: str) -> dict: ...
    def guardar_conversacion(self, conversacion_id: str, opciones: list, frases: list,
                             mensajes: list, estado_motor: bytes | None, ttl_s: int) -> None: ...
    def cargar_estado_motor(self, conversacion_id: str) -> bytes | None: ...
    def cache_leer(self, clave: str) -> dict | None: ...
    def cache_guardar(self, clave: str, valor: dict, ttl_s: int) -> None: ...
    def publicar_motor(self, nombre: str, datos: dict, ttl_s: int | None) -> None: ...
    def estado_cola(self) -> dict: ...

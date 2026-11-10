"""Almacén en memoria: API y trabajador en el MISMO proceso (modo por defecto sin
REDIS_URL; desarrollo y pruebas). Mismas reglas que Redis (TTL, cola FIFO,
eventos con id ordenado, candado de conversación) para que el comportamiento
no cambie al pasar a Redis.

Seguro entre hilos (un candado + una condición). Los métodos asíncronos no
bloquean: esperan con `asyncio.sleep` corto.
"""
from __future__ import annotations

import asyncio
import copy
import itertools
import threading
import time
from collections import deque

from backend.app.services.almacen import ESTADOS_FINALES, ahora_iso


def _vencido(expira: float | None, ahora: float) -> bool:
    return expira is not None and expira <= ahora


class AlmacenMemoria:
    modo = "memoria"

    def __init__(self, reloj=time.time):
        self._reloj = reloj
        self._candado = threading.RLock()
        self._hay_turno = threading.Condition(self._candado)
        self._conv: dict[str, dict] = {}
        self._activos: dict[str, tuple[str, float]] = {}
        self._turnos: dict[str, dict] = {}
        self._eventos: dict[str, dict] = {}  # turno_id -> {"lista": [...], "expira": t|None}
        self._cola: deque[str] = deque()
        self._espera: dict[str, int] = {}
        self._en_curso: dict[str, int] = {}
        self._cache: dict[str, tuple[dict, float]] = {}
        self._limites: dict[str, list[float]] = {}
        self._motor: dict[str, tuple[dict, float | None]] = {}
        self._secuencia = itertools.count(1)

    # ------------------------------------------------------------ utilidades
    def _ahora(self) -> float:
        return self._reloj()

    def _ms(self) -> int:
        return int(self._ahora() * 1000)

    # Cómo se lee el vencimiento de cada colección (None = no vence).
    _VENCIMIENTOS = (
        ("_conv", lambda valor: valor["expira"]),
        ("_activos", lambda valor: valor[1]),
        ("_turnos", lambda valor: valor["_expira"]),
        ("_eventos", lambda valor: valor["expira"]),
        ("_cache", lambda valor: valor[1]),
        ("_motor", lambda valor: valor[1]),
    )

    def _purgar(self) -> None:
        """Borra lo vencido (equivale al TTL de Redis)."""
        ahora = self._ahora()
        for atributo, vence in self._VENCIMIENTOS:
            coleccion = getattr(self, atributo)
            for clave in [c for c, valor in coleccion.items() if _vencido(vence(valor), ahora)]:
                del coleccion[clave]

    @staticmethod
    def _id_num(evento_id: str) -> int:
        try:
            return int(str(evento_id).split("-")[0])
        except ValueError:
            return 0

    # =================================================================== API
    async def ping(self) -> bool:
        return True

    async def cerrar(self) -> None:
        return None

    async def crear_conversacion(self, conversacion_id: str, ttl_s: int = 24 * 3600) -> None:
        with self._candado:
            ahora = ahora_iso()
            self._conv[conversacion_id] = {
                "creada": ahora, "actualizada": ahora, "opciones": [], "frases": [],
                "mensajes": [], "motor": None, "expira": self._ahora() + ttl_s, "ttl": ttl_s,
            }

    async def conversacion(self, conversacion_id: str) -> dict | None:
        with self._candado:
            self._purgar()
            datos = self._conv.get(conversacion_id)
            if datos is None:
                return None
            activo = self._activos.get(conversacion_id)
            return {
                "conversacion_id": conversacion_id,
                "creada": datos["creada"], "actualizada": datos["actualizada"],
                "opciones": copy.deepcopy(datos["opciones"]), "frases": list(datos["frases"]),
                "mensajes": copy.deepcopy(datos["mensajes"]),
                "turno_activo": activo[0] if activo else None,
            }

    async def reservar_turno(self, conversacion_id: str, turno_id: str, ttl_s: int) -> bool:
        with self._candado:
            self._purgar()
            if conversacion_id in self._activos:
                return False
            self._activos[conversacion_id] = (turno_id, self._ahora() + ttl_s)
            return True

    async def liberar_reserva(self, conversacion_id: str, turno_id: str) -> None:
        with self._candado:
            self._liberar_activo(conversacion_id, turno_id)

    def _liberar_activo(self, conversacion_id, turno_id):
        activo = self._activos.get(conversacion_id)
        if activo and activo[0] == turno_id:
            del self._activos[conversacion_id]

    async def encolar_turno(self, turno: dict, cola_max: int, ttl_s: int) -> bool:
        with self._hay_turno:
            if len(self._espera) >= cola_max:
                return False
            datos = copy.deepcopy(turno)
            datos["_expira"] = self._ahora() + ttl_s
            self._turnos[turno["turno_id"]] = datos
            self._eventos[turno["turno_id"]] = {"lista": [], "expira": self._ahora() + ttl_s}
            self._espera[turno["turno_id"]] = self._ms()
            self._cola.append(turno["turno_id"])
            self._hay_turno.notify_all()
            return True

    def _turno(self, turno_id):
        self._purgar()
        datos = self._turnos.get(turno_id)
        if datos is None:
            return None
        return {k: copy.deepcopy(v) for k, v in datos.items() if not k.startswith("_")}

    async def turno(self, turno_id: str) -> dict | None:
        with self._candado:
            return self._turno(turno_id)

    def _eventos_desde(self, turno_id, desde):
        datos = self._eventos.get(turno_id)
        if not datos:
            return []
        minimo = self._id_num(desde)
        return [(i, n, copy.deepcopy(d)) for i, n, d in datos["lista"] if self._id_num(i) > minimo]

    async def leer_eventos(self, turno_id: str, desde: str, bloqueo_ms: int) -> list[tuple[str, str, dict]]:
        limite = time.monotonic() + max(0, bloqueo_ms) / 1000
        while True:
            with self._candado:
                self._purgar()
                eventos = self._eventos_desde(turno_id, desde)
            if eventos or time.monotonic() >= limite:
                return eventos
            await asyncio.sleep(0.02)

    async def eventos_existen(self, turno_id: str) -> bool:
        with self._candado:
            self._purgar()
            return turno_id in self._eventos

    def _posicion(self, turno_id):
        orden = sorted(self._espera.items(), key=lambda par: (par[1], par[0]))
        ids = [t for t, _ in orden]
        posicion = ids.index(turno_id) + 1 if turno_id in self._espera else 0
        return posicion, len(self._en_curso)

    async def posicion(self, turno_id: str) -> tuple[int, int]:
        with self._candado:
            return self._posicion(turno_id)

    def estado_cola(self) -> dict:
        with self._candado:
            return {"en_espera": len(self._espera), "en_curso": len(self._en_curso)}

    async def resumen_cola(self) -> dict:
        return self.estado_cola()

    async def registrar_peticion(self, cliente: str, limite: int, ventana_s: int) -> float | None:
        with self._candado:
            ahora = self._ahora()
            marcas = [m for m in self._limites.get(cliente, []) if m > ahora - ventana_s]
            if len(marcas) >= limite:
                self._limites[cliente] = marcas
                return max(0.0, marcas[0] + ventana_s - ahora)
            marcas.append(ahora)
            self._limites[cliente] = marcas
            return None

    async def marcar_calificacion(self, turno_id: str, calificacion: dict) -> bool:
        with self._candado:
            datos = self._turnos.get(turno_id)
            if datos is None or datos.get("calificacion") == calificacion:
                return False
            datos["calificacion"] = copy.deepcopy(calificacion)
            return True

    async def leer_motor(self, nombre: str) -> dict | None:
        with self._candado:
            self._purgar()
            valor = self._motor.get(nombre)
            return copy.deepcopy(valor[0]) if valor else None

    # ============================================================ trabajador
    def tomar_turno(self, consumidor: str, bloqueo_ms: int) -> dict | None:
        limite = time.monotonic() + max(0, bloqueo_ms) / 1000
        with self._hay_turno:
            while True:
                while self._cola:
                    turno_id = self._cola.popleft()
                    datos = self._turno(turno_id)
                    if datos is not None:
                        datos["_entrada"] = turno_id
                        return datos
                    self._espera.pop(turno_id, None)
                restante = limite - time.monotonic()
                if restante <= 0:
                    return None
                self._hay_turno.wait(restante)

    def confirmar(self, turno: dict) -> None:
        return None

    def recuperar_huerfanos(self, consumidor: str, inactivo_ms: int) -> list[dict]:
        return []  # un solo proceso: no hay turnos de un trabajador caído

    def iniciar_turno(self, turno_id: str) -> None:
        with self._candado:
            self._espera.pop(turno_id, None)
            self._en_curso[turno_id] = self._ms()
            datos = self._turnos.get(turno_id)
            if datos is not None:
                datos.update(estado="procesando", iniciado_ms=self._ms())

    def publicar_evento(self, turno_id: str, evento: str, datos: dict, ttl_s: int | None = None) -> str:
        with self._candado:
            evento_id = f"{next(self._secuencia)}-0"
            registro = self._eventos.setdefault(turno_id, {"lista": [], "expira": None})
            registro["lista"].append((evento_id, evento, copy.deepcopy(datos)))
            if ttl_s:
                registro["expira"] = self._ahora() + ttl_s
            return evento_id

    def terminar_turno(self, turno: dict, campos: dict, eventos_ttl_s: int) -> None:
        turno_id = turno["turno_id"]
        with self._candado:
            datos = self._turnos.get(turno_id)
            if datos is not None:
                datos.update(copy.deepcopy(campos))
                datos.setdefault("terminado_ms", self._ms())
            self._en_curso.pop(turno_id, None)
            self._espera.pop(turno_id, None)
            if turno_id in self._eventos:
                self._eventos[turno_id]["expira"] = self._ahora() + eventos_ttl_s
            if campos.get("estado") in ESTADOS_FINALES:
                self._liberar_activo(turno["conversacion_id"], turno_id)

    def meta_conversacion(self, conversacion_id: str) -> dict:
        with self._candado:
            datos = self._conv.get(conversacion_id) or {}
            return {"opciones": copy.deepcopy(datos.get("opciones") or []),
                    "frases": list(datos.get("frases") or []),
                    "existe": bool(datos)}

    def guardar_conversacion(self, conversacion_id: str, opciones: list, frases: list,
                             mensajes: list, estado_motor: bytes | None, ttl_s: int) -> None:
        with self._candado:
            datos = self._conv.get(conversacion_id)
            if datos is None:  # expiró durante el turno: se recrea
                ahora = ahora_iso()
                datos = self._conv[conversacion_id] = {"creada": ahora, "mensajes": [], "motor": None}
            datos.update(opciones=copy.deepcopy(opciones), frases=list(frases), motor=estado_motor,
                         actualizada=ahora_iso(), expira=self._ahora() + ttl_s, ttl=ttl_s)
            datos["mensajes"].extend(copy.deepcopy(mensajes))

    def cargar_estado_motor(self, conversacion_id: str) -> bytes | None:
        with self._candado:
            return (self._conv.get(conversacion_id) or {}).get("motor")

    def cache_leer(self, clave: str) -> dict | None:
        with self._candado:
            self._purgar()
            valor = self._cache.get(clave)
            return copy.deepcopy(valor[0]) if valor else None

    def cache_guardar(self, clave: str, valor: dict, ttl_s: int) -> None:
        with self._candado:
            self._cache[clave] = (copy.deepcopy(valor), self._ahora() + ttl_s)

    def publicar_motor(self, nombre: str, datos: dict, ttl_s: int | None) -> None:
        with self._candado:
            self._motor[nombre] = (copy.deepcopy(datos), self._ahora() + ttl_s if ttl_s else None)

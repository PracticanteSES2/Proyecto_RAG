"""El trabajador: consume la cola de turnos y los atiende con la piscina de
motores. Corre como proceso propio (`python -m backend.worker`, con Redis) o
como hilos dentro de la API (modo embebido, sin Redis).

- Solo toma un turno de la cola cuando hay una instancia del motor libre: los
  turnos esperan en la cola compartida (posición FIFO visible por el SSE), no
  en una fila oculta de este proceso.
- Cada turno corre en su hilo (`ThreadPoolExecutor` de tamaño = instancias).
- Latido cada `latido_s`: salud, diagnóstico del servidor y capacidades.
- Al arrancar (y cada minuto) cierra los turnos que un trabajador anterior
  dejó a medias (`error interrumpido`).
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from backend.app.services import capacidades as info
from backend.app.services.almacen import ahora_iso

LOG = logging.getLogger(__name__)
REVISION_HUERFANOS_S = 60.0
REFRESCO_MEDGEMMA_S = 60.0
LIMITE_CHEQUEO_S = 3.0


class Trabajador:
    def __init__(self, almacen, procesador, piscina, ajustes, version: str = "", huella=None,
                 nombre: str | None = None):
        self.almacen = almacen
        self.procesador = procesador
        self.piscina = piscina
        self.ajustes = ajustes
        self.version = version
        self.huella = huella
        self.raiz_datos = ajustes.rag_raiz_datos
        self.nombre = nombre or f"{socket.gethostname()}-{os.getpid()}"
        self.iniciado = ahora_iso()
        self._parar = threading.Event()
        self._huecos = threading.Semaphore(piscina.total)
        self._hilos: list[threading.Thread] = []
        self._ejecutor = ThreadPoolExecutor(max_workers=piscina.total, thread_name_prefix="turno")
        self._capacidades = None
        self.ejemplos_fijos = list(ajustes.capacidades_ejemplos or [])
        # Salud de MedGemma en segundo plano y cacheada: el latido nunca espera un ping lento.
        self._medgemma = info.chequeo_medgemma(piscina, REFRESCO_MEDGEMMA_S, LIMITE_CHEQUEO_S)

    # ------------------------------------------------------------ ciclo de vida
    def iniciar(self) -> None:
        self.cerrar_huerfanos(0)
        self.publicar_estado()
        for objetivo, nombre in ((self._bucle_cola, "cola-turnos"), (self._bucle_latido, "latido-motor")):
            hilo = threading.Thread(target=objetivo, name=nombre, daemon=True)
            hilo.start()
            self._hilos.append(hilo)
        LOG.info("Trabajador %s atendiendo con %d instancia(s) del motor", self.nombre, self.piscina.total)

    def detener(self, espera_s: float = 5.0) -> None:
        self._parar.set()
        for hilo in self._hilos:
            hilo.join(timeout=espera_s)
        self._ejecutor.shutdown(wait=False, cancel_futures=True)

    def esperar(self) -> None:
        """Bloquea hasta `detener()` (proceso trabajador)."""
        while not self._parar.wait(1.0):
            pass

    # ------------------------------------------------------------ cola
    def _bucle_cola(self) -> None:
        while not self._parar.is_set():
            if not self._huecos.acquire(timeout=0.5):
                continue
            try:
                turno = self.almacen.tomar_turno(self.nombre, 1000)
            except Exception:
                LOG.exception("No se pudo leer la cola de turnos; reintento en 2 s")
                self._huecos.release()
                self._parar.wait(2.0)
                continue
            if turno is None:
                self._huecos.release()
                continue
            self._ejecutor.submit(self._atender, turno)

    def _atender(self, turno: dict) -> None:
        try:
            self.procesador.procesar(turno)
        finally:
            try:
                self.almacen.confirmar(turno)
            except Exception:
                LOG.exception("No se pudo confirmar el turno %s", turno.get("turno_id"))
            self._huecos.release()

    def cerrar_huerfanos(self, inactivo_ms: int) -> int:
        try:
            huerfanos = self.almacen.recuperar_huerfanos(self.nombre, inactivo_ms)
        except Exception:
            LOG.exception("No se pudieron revisar los turnos huérfanos")
            return 0
        for turno in huerfanos:
            LOG.warning("Turno %s interrumpido por un reinicio: se cierra con error", turno.get("turno_id"))
            self.procesador.cerrar_huerfano(turno)
            self.almacen.confirmar(turno)
        return len(huerfanos)

    # ------------------------------------------------------------ latido
    def publicar_estado(self) -> None:
        ttl = max(3, int(self.ajustes.latido_s * 3))
        huella = None
        try:
            huella = self.huella.valor() if self.huella is not None else None
        except Exception:
            LOG.debug("Huella no disponible", exc_info=True)
        try:
            self.almacen.publicar_motor(
                "latido", dict(info.latido(self.piscina, self.version, huella, self.iniciado, self.almacen.modo),
                              publicado=ahora_iso()), ttl)
            self.almacen.publicar_motor(
                "diagnostico", dict(info.diagnostico_servidor(self.piscina, self.almacen.estado_cola()),
                                    actualizado=ahora_iso()), ttl * 2)
            if self._capacidades is None:
                self._capacidades = info.capacidades(self.piscina.principal, self.raiz_datos, self.ejemplos_fijos)
            self.almacen.publicar_motor("capacidades", self._capacidades, 24 * 3600)
        except Exception:
            LOG.exception("No se pudo publicar el estado del trabajador")

    def _salud_medgemma(self) -> None:
        if self._medgemma is None:
            return
        self._medgemma.refrescar()
        ultimo = self._medgemma.ultimo()
        if ultimo is not None:
            self.piscina.principal.estado_medgemma = ultimo

    def _bucle_latido(self) -> None:
        ultima_revision = time.monotonic()
        while not self._parar.wait(self.ajustes.latido_s):
            ahora = time.monotonic()
            self._salud_medgemma()
            if ahora - ultima_revision >= REVISION_HUERFANOS_S:
                self.cerrar_huerfanos(int(self.ajustes.turno_max_s * 1000))
                ultima_revision = ahora
            self.publicar_estado()

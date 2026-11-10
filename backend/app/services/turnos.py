"""Un turno de principio a fin, en el proceso dueño del motor.

Orden de publicación (importa para el SSE y para el turno siguiente):
`progreso…` → `respuesta` (o `error`) → se guarda el estado de la conversación
y el turno queda terminado (libera el candado de la conversación) → `fin`.
Así, cuando el navegador ve `fin`, ya puede enviar el siguiente turno y el
contexto ya está guardado.
"""
from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

from backend.app.services import cache as reglas_cache
from backend.app.services import presentacion
from backend.app.services.almacen import ahora_iso
from backend.app.services.motor import PiscinaMotores, SerializadorEstado, SesionPorAtributos
from backend.app.services.progreso import EmisorTurno, Reloj, contexto_cola_llm, nuevo_traductor

LOG = logging.getLogger(__name__)

ERROR_MOTOR = {"mensaje": presentacion.MENSAJE_ERROR, "codigo": "error_motor"}
ERROR_INTERRUMPIDO = {
    "mensaje": "La consulta se interrumpió porque el servicio se reinició. Vuelve a enviarla, por favor.",
    "codigo": "interrumpido",
}
ERROR_OPCION = {
    "mensaje": "Esa opción ya no está disponible. Escribe de nuevo tu pregunta, por favor.",
    "codigo": "opcion_no_vigente",
}


def _snapshot(result, texto, pregunta, via, opciones):
    try:
        from src.feedback.registro import snapshot_turno

        return snapshot_turno(result, texto, pregunta, via, opciones)
    except Exception:
        LOG.warning("No se pudo armar el snapshot del turno", exc_info=True)
        return None


class ProcesadorTurnos:
    def __init__(self, almacen, piscina: PiscinaMotores, serializador: SerializadorEstado, ajustes,
                 huella: reglas_cache.Huella | None = None, raiz_datos: Path | None = None,
                 intervalo_tic_s: float = 1.0, sesiones=None):
        self.almacen = almacen
        self.piscina = piscina
        self.serializador = serializador
        self.ajustes = ajustes
        self.huella = huella
        self.raiz_datos = raiz_datos
        self.intervalo_tic_s = intervalo_tic_s
        # PUNTO DE UNIÓN con agente/memoria-sesion: cómo se pasa el estado de la
        # conversación al motor (hoy, restaurando atributos; mañana, sesion=…).
        self.sesiones = sesiones or SesionPorAtributos()

    # ------------------------------------------------------------------
    def _emisor(self, turno_id, frases):
        def publicar(evento, datos):
            self.almacen.publicar_evento(turno_id, evento, datos)

        return EmisorTurno(publicar, nuevo_traductor(list(frases or [])))

    def _cerrar(self, turno, emisor, campos, mensajes, opciones, estado_bytes, guardar_estado=True):
        cid = turno["conversacion_id"]
        try:
            if guardar_estado:
                self.almacen.guardar_conversacion(cid, opciones, emisor.recientes, mensajes, estado_bytes,
                                                  self.ajustes.conversacion_ttl_s)
            else:
                meta = self.almacen.meta_conversacion(cid)
                self.almacen.guardar_conversacion(cid, meta["opciones"], emisor.recientes, mensajes,
                                                  self.almacen.cargar_estado_motor(cid),
                                                  self.ajustes.conversacion_ttl_s)
        finally:
            self.almacen.terminar_turno(turno, campos, self.ajustes.eventos_ttl_s)
            self.almacen.publicar_evento(turno["turno_id"], "fin", {}, ttl_s=self.ajustes.eventos_ttl_s)

    def _mensaje_usuario(self, turno, texto):
        return {"rol": "usuario", "texto": texto, "via": "opcion" if turno.get("opcion_id") else "texto",
                "turno_id": turno["turno_id"], "fecha": turno.get("creado") or ahora_iso()}

    def _error(self, turno, emisor, error, texto_usuario):
        emisor.evento("error", error)
        mensajes = [self._mensaje_usuario(turno, texto_usuario),
                    {"rol": "asistente", "turno_id": turno["turno_id"], "fecha": ahora_iso(), "error": error}]
        self._cerrar(turno, emisor, {"estado": "error", "error": error}, mensajes, [], None, guardar_estado=False)

    # ------------------------------------------------------------------
    def cerrar_huerfano(self, turno: dict) -> None:
        """Turno que un trabajador anterior dejó a medias."""
        emisor = self._emisor(turno["turno_id"], [])
        try:
            self._error(turno, emisor, ERROR_INTERRUMPIDO, turno.get("mensaje") or turno.get("opcion_texto") or "")
        except Exception:
            LOG.exception("No se pudo cerrar el turno huérfano %s", turno.get("turno_id"))

    def procesar(self, turno: dict) -> None:
        """Nunca lanza: cualquier fallo termina en `error` + `fin`."""
        try:
            self._procesar(turno)
        except Exception:
            LOG.exception("Fallo inesperado procesando el turno %s", turno.get("turno_id"))
            try:
                emisor = self._emisor(turno["turno_id"], [])
                self._error(turno, emisor, ERROR_MOTOR, turno.get("mensaje") or "")
            except Exception:
                LOG.exception("Tampoco se pudo cerrar el turno %s", turno.get("turno_id"))

    def _procesar(self, turno: dict) -> None:
        tid, cid = turno["turno_id"], turno["conversacion_id"]
        recibido = time.time()
        self.almacen.iniciar_turno(tid)
        meta = self.almacen.meta_conversacion(cid)
        emisor = self._emisor(tid, meta.get("frases"))
        emisor.iniciar()

        opcion = None
        if turno.get("opcion_id"):
            opcion = next((o for o in meta.get("opciones") or [] if o.get("id") == turno["opcion_id"]), None)
            if opcion is None:
                self._error(turno, emisor, ERROR_OPCION, turno.get("mensaje") or "")
                return
        texto_usuario = (turno.get("mensaje") or "").strip() or (opcion or {}).get("texto") or ""
        estado_previo = self.serializador.de_bytes(self.almacen.cargar_estado_motor(cid))

        clave, guardado = self._buscar_en_cache(turno, estado_previo, texto_usuario)
        if guardado:
            self._desde_cache(turno, emisor, guardado, texto_usuario, recibido)
            return

        with self.piscina.tomar() as instancia:
            inicio_motor = time.time()
            motor = instancia.engine
            poner_oyente = getattr(motor, "set_progress_listener", None)
            try:
                if callable(poner_oyente):
                    poner_oyente(emisor.traducir)
                with Reloj(emisor, self.intervalo_tic_s), contexto_cola_llm(emisor.cola_llm):
                    result, estado_nuevo = self.sesiones.ejecutar(instancia, estado_previo, texto_usuario, opcion,
                                                                  on_token=emisor.token)
            except Exception:
                LOG.warning("Turno %s: el motor falló", tid, exc_info=True)
                self._error(turno, emisor, ERROR_MOTOR, texto_usuario)
                return
            finally:
                if callable(poner_oyente):
                    try:
                        poner_oyente(None)
                    except Exception:
                        pass
            formatter = instancia.formatter
            fin_motor = time.time()

        try:
            respuesta, pendientes, texto = presentacion.construir_respuesta(result, formatter, tid)
        except Exception:
            LOG.exception("No se pudo presentar la respuesta del turno %s", tid)
            self._error(turno, emisor, ERROR_MOTOR, texto_usuario)
            return
        tiempos = self._tiempos(turno, recibido, inicio_motor, fin_motor)
        razonamiento = presentacion.razonamiento_texto(result, texto)
        if turno.get("diagnostico"):
            respuesta["diagnostico"] = presentacion.diagnostico(result, texto, tiempos, cacheada=False)
        snapshot = _snapshot(result, texto, texto_usuario, "botón" if opcion else "texto",
                             [p["texto"] for p in pendientes])
        estado_bytes = self.serializador.a_bytes(estado_nuevo)

        emisor.finalizar()
        emisor.aviso(result)
        self.almacen.publicar_evento(tid, "respuesta", respuesta)
        mensajes = [self._mensaje_usuario(turno, texto_usuario), self._mensaje_asistente(respuesta, razonamiento)]
        self._cerrar(turno, emisor, {"estado": "terminado", "respuesta": respuesta, "snapshot": snapshot},
                     mensajes, pendientes, estado_bytes)

        if clave and reglas_cache.puede_guardar(result, respuesta, estado_previo, turno,
                                                       self.ajustes.cache_habilitada, self.sesiones.sin_contexto):
            guardable = {k: v for k, v in respuesta.items() if k not in ("turno_id", "diagnostico")}
            self.almacen.cache_guardar(clave, {
                "respuesta": guardable, "snapshot": snapshot, "razonamiento": razonamiento,
                "estado_motor": base64.b64encode(estado_bytes).decode("ascii") if estado_bytes else None,
                "guardada": ahora_iso(),
            }, self.ajustes.cache_ttl_s)

    # ------------------------------------------------------------------
    def _buscar_en_cache(self, turno, estado_previo, texto_usuario):
        """(clave, entrada guardada o None). Clave None si el turno no admite caché."""
        if self.huella is None or not reglas_cache.puede_leer(turno, estado_previo, self.ajustes.cache_habilitada,
                                                              self.sesiones.sin_contexto):
            return None, None
        clave = reglas_cache.clave_cache(
            self.huella.valor(), reglas_cache.normalizar_pregunta(texto_usuario, self.raiz_datos))
        return clave, self.almacen.cache_leer(clave)

    @staticmethod
    def _mensaje_asistente(respuesta, razonamiento):
        return {"rol": "asistente", "turno_id": respuesta["turno_id"], "fecha": ahora_iso(),
                "respuesta": {k: v for k, v in respuesta.items() if k != "diagnostico"},
                "razonamiento": razonamiento}

    @staticmethod
    def _tiempos(turno, recibido, inicio_motor, fin_motor):
        creado = (turno.get("creado_ms") or int(recibido * 1000)) / 1000
        return {"cola_s": round(max(0.0, recibido - creado), 2),
                "motor_s": round(max(0.0, fin_motor - inicio_motor), 2),
                "total_s": round(max(0.0, time.time() - creado), 2)}

    def _desde_cache(self, turno, emisor, guardado, texto_usuario, recibido):
        tid = turno["turno_id"]
        respuesta = dict(guardado.get("respuesta") or {})
        respuesta.update(turno_id=tid, cacheada=True, diagnostico=None)
        if turno.get("diagnostico"):
            ahora = time.time()
            respuesta["diagnostico"] = {
                "razonamiento": guardado.get("razonamiento"), "pasos": [],
                "tiempos": self._tiempos(turno, recibido, ahora, ahora), "cacheada": True,
                "cache_guardada": guardado.get("guardada"),
            }
        estado = guardado.get("estado_motor")
        estado_bytes = base64.b64decode(estado) if estado else None
        if estado_bytes is not None and self.serializador.de_bytes(estado_bytes) is None:
            estado_bytes = None  # firmado con otro secreto: sin contexto, igual que una conversación nueva
        emisor.finalizar()
        self.almacen.publicar_evento(tid, "respuesta", respuesta)
        mensajes = [self._mensaje_usuario(turno, texto_usuario),
                    self._mensaje_asistente(respuesta, guardado.get("razonamiento"))]
        self._cerrar(turno, emisor, {"estado": "terminado", "respuesta": respuesta,
                                     "snapshot": guardado.get("snapshot")}, mensajes, [], estado_bytes)

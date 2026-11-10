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
from dataclasses import dataclass
from pathlib import Path

from backend.app.services import cache as reglas_cache
from backend.app.services import presentacion
from backend.app.services.almacen import ahora_iso
from backend.app.services.motor import PiscinaMotores, SerializadorEstado, SesionExplicita
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


@dataclass
class ContextoTurno:
    turno: dict
    emisor: EmisorTurno
    opcion: dict | None
    texto_usuario: str
    estado_previo: object
    recibido: float


@dataclass
class CorridaMotor:
    result: dict
    estado_nuevo: object
    formatter: object
    inicio: float
    fin: float


def _opcion_elegida(meta: dict, opcion_id: str | None) -> dict | None:
    if not opcion_id:
        return None
    return next((o for o in meta.get("opciones") or [] if o.get("id") == opcion_id), None)


def _quitar_oyente(poner_oyente) -> None:
    try:
        poner_oyente(None)
    except Exception:
        LOG.warning("No se pudo quitar el oyente de progreso del motor", exc_info=True)


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
        self.raiz_datos = raiz_datos if raiz_datos is not None else getattr(ajustes, "rag_raiz_datos", None)
        self.intervalo_tic_s = intervalo_tic_s
        # Cómo se pasa el estado de la conversación al motor: `sesion=` con una
        # EstadoConversacion (spec 008).
        self.sesiones = sesiones or SesionExplicita()

    # ------------------------------------------------------------------
    def _emisor(self, turno_id, frases, diagnostico=False):
        def publicar(evento, datos):
            self.almacen.publicar_evento(turno_id, evento, datos)

        return EmisorTurno(publicar, nuevo_traductor(list(frases or [])), diagnostico=diagnostico)

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
        ctx = self._preparar(turno)
        if ctx is None:
            return
        clave, guardado = self._buscar_en_cache(turno, ctx.estado_previo, ctx.texto_usuario)
        if guardado:
            self._desde_cache(turno, ctx.emisor, guardado, ctx.texto_usuario, ctx.recibido)
            return
        corrida = self._correr_motor(ctx)
        if corrida is None:
            return
        try:
            respuesta, pendientes, texto = presentacion.construir_respuesta(corrida.result, corrida.formatter,
                                                                            turno["turno_id"])
        except Exception:
            LOG.exception("No se pudo presentar la respuesta del turno %s", turno["turno_id"])
            self._error(turno, ctx.emisor, ERROR_MOTOR, ctx.texto_usuario)
            return
        guardable = self._responder(ctx, corrida, respuesta, pendientes, texto)
        if clave and reglas_cache.puede_guardar(corrida.result, respuesta, ctx.estado_previo, turno,
                                                self.ajustes.cache_habilitada, self.sesiones.sin_contexto):
            self.almacen.cache_guardar(clave, guardable, self.ajustes.cache_ttl_s)

    def _preparar(self, turno: dict) -> ContextoTurno | None:
        """Marca el turno en curso, abre el progreso y resuelve la opción elegida."""
        tid, cid = turno["turno_id"], turno["conversacion_id"]
        recibido = time.time()
        self.almacen.iniciar_turno(tid)
        meta = self.almacen.meta_conversacion(cid)
        emisor = self._emisor(tid, meta.get("frases"), bool(turno.get("diagnostico")))
        emisor.iniciar()
        opcion = _opcion_elegida(meta, turno.get("opcion_id"))
        if turno.get("opcion_id") and opcion is None:
            self._error(turno, emisor, ERROR_OPCION, turno.get("mensaje") or "")
            return None
        texto_usuario = (turno.get("mensaje") or "").strip() or (opcion or {}).get("texto") or ""
        estado_previo = self.serializador.de_bytes(self.almacen.cargar_estado_motor(cid))
        return ContextoTurno(turno, emisor, opcion, texto_usuario, estado_previo, recibido)

    def _correr_motor(self, ctx: ContextoTurno) -> CorridaMotor | None:
        """Ejecuta el turno en una instancia libre; None si el motor falló (ya se avisó)."""
        with self.piscina.tomar() as instancia:
            inicio = time.time()
            poner_oyente = getattr(instancia.engine, "set_progress_listener", None)
            oyente = poner_oyente if callable(poner_oyente) else (lambda _oyente: None)
            try:
                oyente(ctx.emisor.traducir)
                with Reloj(ctx.emisor, self.intervalo_tic_s), contexto_cola_llm(ctx.emisor.cola_llm):
                    result, estado_nuevo = self.sesiones.ejecutar(instancia, ctx.estado_previo, ctx.texto_usuario,
                                                                  ctx.opcion, on_token=ctx.emisor.token)
            except Exception:
                LOG.warning("Turno %s: el motor falló", ctx.turno["turno_id"], exc_info=True)
                self._error(ctx.turno, ctx.emisor, ERROR_MOTOR, ctx.texto_usuario)
                return None
            finally:
                _quitar_oyente(oyente)
            return CorridaMotor(result, estado_nuevo, instancia.formatter, inicio, time.time())

    def _responder(self, ctx: ContextoTurno, corrida: CorridaMotor, respuesta: dict, pendientes: list,
                   texto: str) -> dict:
        """Publica la respuesta, guarda la conversación y cierra el turno.
        Devuelve la entrada para la caché (por si se puede guardar)."""
        turno, result = ctx.turno, corrida.result
        tiempos = self._tiempos(turno, ctx.recibido, corrida.inicio, corrida.fin)
        razonamiento = presentacion.razonamiento_texto(result, texto)
        if turno.get("diagnostico"):
            respuesta["diagnostico"] = presentacion.diagnostico(result, texto, tiempos, cacheada=False)
        snapshot = _snapshot(result, texto, ctx.texto_usuario, "botón" if ctx.opcion else "texto",
                             [p["texto"] for p in pendientes])
        estado_bytes = self.serializador.a_bytes(corrida.estado_nuevo)
        ctx.emisor.finalizar()
        ctx.emisor.aviso(result)
        self.almacen.publicar_evento(turno["turno_id"], "respuesta", respuesta)
        mensajes = [self._mensaje_usuario(turno, ctx.texto_usuario), self._mensaje_asistente(respuesta, razonamiento)]
        self._cerrar(turno, ctx.emisor, {"estado": "terminado", "respuesta": respuesta, "snapshot": snapshot},
                     mensajes, pendientes, estado_bytes)
        return {
            "respuesta": {k: v for k, v in respuesta.items() if k not in ("turno_id", "diagnostico")},
            "snapshot": snapshot, "razonamiento": razonamiento,
            "estado_motor": base64.b64encode(estado_bytes).decode("ascii") if estado_bytes else None,
            "guardada": ahora_iso(),
        }

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

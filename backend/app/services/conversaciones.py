"""Casos de uso de la API sobre conversaciones y turnos (lado API, asíncrono).

No toca el motor: encola turnos y lee lo que el trabajador dejó en el almacén.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime

from anyio import to_thread

from backend.app.core import errores
from backend.app.services.almacen import ESTADOS_FINALES, ahora_iso

ID_VALIDO = frozenset("0123456789abcdef")


def id_valido(valor: str) -> bool:
    return isinstance(valor, str) and len(valor) == 32 and set(valor) <= ID_VALIDO


def nuevo_id() -> str:
    return uuid.uuid4().hex


class ServicioConversaciones:
    def __init__(self, almacen, ajustes):
        self.almacen = almacen
        self.ajustes = ajustes

    # ------------------------------------------------------------ conversaciones
    async def crear(self) -> str:
        conversacion_id = nuevo_id()
        await self.almacen.crear_conversacion(conversacion_id, self.ajustes.conversacion_ttl_s)
        return conversacion_id

    async def _conversacion(self, conversacion_id: str) -> dict:
        conversacion = await self.almacen.conversacion(conversacion_id) if id_valido(conversacion_id) else None
        if conversacion is None:
            raise errores.no_encontrada("conversacion")
        return conversacion

    async def historial(self, conversacion_id: str) -> dict:
        conversacion = await self._conversacion(conversacion_id)
        mensajes = [_mensaje_publico(m) for m in conversacion["mensajes"]]
        if conversacion["opciones"] and mensajes and not conversacion["turno_activo"]:
            ultimo = mensajes[-1]
            if ultimo["rol"] == "asistente" and (ultimo.get("respuesta") or {}).get("contrapregunta"):
                ultimo["contrapregunta_vigente"] = True
        return {"conversacion_id": conversacion_id, "creada": conversacion["creada"],
                "actualizada": conversacion["actualizada"], "turno_activo": conversacion["turno_activo"],
                "mensajes": mensajes}

    # ------------------------------------------------------------ turnos
    async def crear_turno(self, conversacion_id: str, mensaje: str, diagnostico: bool, opcion_id: str | None,
                          cliente: str) -> str:
        conversacion = await self._conversacion(conversacion_id)
        opcion = None
        if opcion_id:
            opcion = next((o for o in conversacion["opciones"] if o.get("id") == opcion_id), None)
            if opcion is None:
                raise errores.error(errores.OPCION_NO_VIGENTE)
        turno_id = nuevo_id()
        if not await self.almacen.reservar_turno(conversacion_id, turno_id, self.ajustes.turno_max_s):
            raise errores.error(errores.TURNO_EN_CURSO)
        turno = {
            "turno_id": turno_id, "conversacion_id": conversacion_id,
            "mensaje": mensaje or (opcion or {}).get("texto") or "",
            "opcion_id": opcion_id, "opcion_texto": (opcion or {}).get("texto"),
            "via": "opcion" if opcion else "texto", "diagnostico": bool(diagnostico), "cliente": cliente,
            "estado": "en_cola", "creado": ahora_iso(), "creado_ms": int(time.time() * 1000),
            "respuesta": None, "error": None, "snapshot": None, "calificacion": None,
        }
        try:
            encolado = await self.almacen.encolar_turno(turno, self.ajustes.cola_max, self.ajustes.turno_ttl_s)
        except Exception:
            await self.almacen.liberar_reserva(conversacion_id, turno_id)
            raise
        if not encolado:
            await self.almacen.liberar_reserva(conversacion_id, turno_id)
            raise errores.error(errores.SERVICIO_OCUPADO)
        return turno_id

    async def turno(self, turno_id: str) -> dict:
        turno = await self.almacen.turno(turno_id) if id_valido(turno_id) else None
        if turno is None:
            raise errores.no_encontrada("turno")
        return turno

    # ------------------------------------------------------------ calificación
    async def calificar(self, turno_id: str, valor: str, comentario: str | None) -> bool:
        turno = await self.turno(turno_id)
        if turno.get("estado") != "terminado" or not turno.get("snapshot"):
            raise errores.error(errores.NO_CALIFICABLE)
        calificacion = {"valor": valor, "comentario": comentario or ""}
        if not await self.almacen.marcar_calificacion(turno_id, calificacion):
            return True  # misma calificación: no se duplica la línea
        conversacion = await self.almacen.conversacion(turno["conversacion_id"]) or {"mensajes": []}
        historial, indice = _historial_previo(conversacion["mensajes"], turno_id)
        from src.feedback.registro import construir_registro, guardar

        registro = construir_registro(turno["snapshot"], historial, valor, comentario or "",
                                      turno["conversacion_id"][:12], indice)
        await to_thread.run_sync(guardar, registro)
        return True

    # ------------------------------------------------------------ exportación
    async def exportar(self, conversacion_id: str, formato: str, razonamiento: bool) -> tuple[str, str]:
        if (formato or "md").lower() not in ("md", "markdown"):
            raise errores.error(errores.FORMATO_NO_SOPORTADO)
        conversacion = await self._conversacion(conversacion_id)
        latido = await self.almacen.leer_motor("latido") or {}
        diagnostico = await self.almacen.leer_motor("diagnostico") or {}
        from src.chatbot.conversation_export import export_conversation_markdown, export_file_name

        medgemma = latido.get("medgemma") or {}
        meta = {
            "MedGemma": f"{medgemma.get('estado')} ({medgemma.get('modelo')})" if latido else None,
            "Power BI": (latido.get("powerbi") or {}).get("estado") if latido else None,
            "Versión del código": latido.get("version"),
            "Estado del servidor": diagnostico.get("linea_estado"),
        }
        texto = export_conversation_markdown(_mensajes_streamlit(conversacion["mensajes"]), meta=meta,
                                             include_reasoning=razonamiento, now=datetime.now())
        return texto, export_file_name()


# ----------------------------------------------------------------------
def _mensaje_publico(mensaje: dict) -> dict:
    publico = {k: v for k, v in mensaje.items() if k != "razonamiento"}
    publico.setdefault("contrapregunta_vigente", False)
    return publico


def _historial_previo(mensajes: list[dict], turno_id: str) -> tuple[list[dict], int]:
    """Mensajes anteriores a la respuesta calificada, con las claves de src/feedback."""
    previos = []
    for indice, mensaje in enumerate(mensajes):
        if mensaje.get("rol") == "asistente" and mensaje.get("turno_id") == turno_id:
            return previos, indice
        previos.append({"rol": "assistant" if mensaje.get("rol") == "asistente" else "user",
                        "texto": _texto(mensaje)})
    return previos, len(mensajes)


def _texto(mensaje: dict) -> str:
    if mensaje.get("rol") == "usuario":
        return mensaje.get("texto") or ""
    if mensaje.get("error"):
        return mensaje["error"].get("mensaje") or ""
    return (mensaje.get("respuesta") or {}).get("texto_markdown") or ""


def _con_enlaces(respuesta: dict) -> str:
    texto = respuesta.get("texto_markdown") or ""
    for enlace in respuesta.get("enlaces_powerbi") or []:
        texto += f"\n\n[Abrir en Power BI › {enlace.get('titulo')}]({enlace.get('url')})"
    return texto


def _mensajes_streamlit(mensajes: list[dict]) -> list[dict]:
    """Historial del backend → formato que espera conversation_export (el de
    st.session_state.messages en app.py), con los enlaces de Power BI."""
    salida = []
    for mensaje in mensajes:
        if mensaje.get("rol") == "usuario":
            via = "botón" if mensaje.get("via") == "opcion" else "texto"
            salida.append({"role": "user", "content": mensaje.get("texto") or "", "via": via})
            continue
        if mensaje.get("error"):
            salida.append({"role": "assistant", "content": mensaje["error"].get("mensaje"), "status": "error"})
            continue
        respuesta = mensaje.get("respuesta") or {}
        botones = []
        for opcion in (respuesta.get("contrapregunta") or {}).get("opciones") or []:
            partes = [opcion.get("descripcion")]
            if opcion.get("enlace_powerbi"):
                partes.append(f"[Power BI ›]({opcion['enlace_powerbi'].get('url')})")
            botones.append({"label": opcion.get("texto"), "caption": " · ".join(p for p in partes if p) or None})
        salida.append({"role": "assistant", "content": _con_enlaces(respuesta), "buttons": botones,
                       "reasoning": mensaje.get("razonamiento"), "status": respuesta.get("estado"),
                       "route": respuesta.get("ruta")})
    return salida


def turno_terminado(turno: dict) -> bool:
    return turno.get("estado") in ESTADOS_FINALES

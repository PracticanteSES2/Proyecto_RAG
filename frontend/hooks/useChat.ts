"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { ErrorApi, type ClienteApi } from "@/lib/api/cliente";
import type { ValorCalificacion } from "@/lib/api/tipos";
import { estadoInicialChat, reducirChat, turnoEnCurso, type MensajeAsistente } from "@/lib/chat/reductor";
import type { AccionTurno } from "@/lib/turno/maquina";
import { escribirPreferencia, leerPreferencia } from "./usePreferencia";
import { useTurno } from "./useTurno";

const CLAVE_CONVERSACION = "asistente.conversacion";

let contadorIds = 0;
const nuevoId = (prefijo: string) =>
  `${prefijo}-${typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${++contadorIds}`}`;

interface OpcionesChat {
  cliente: ClienteApi;
  diagnostico: boolean;
  /** Se llama cuando un envío falla por red (para volver a comprobar la salud del servidor). */
  alFallarRed?: () => void;
}

/** Estado y acciones de la conversación: enviar, elegir opción, detener, reintentar, calificar, exportar. */
export function useChat({ cliente, diagnostico, alFallarRed }: OpcionesChat) {
  const [estado, despachar] = useReducer(reducirChat, estadoInicialChat);
  const estadoRef = useRef(estado);
  const ocupado = useRef(false);
  const activo = turnoEnCurso(estado);

  useEffect(() => {
    estadoRef.current = estado;
  }, [estado]);

  useEffect(() => {
    if (!activo) ocupado.current = false;
  }, [activo]);

  const despacharTurno = useCallback(
    (idAsistente: string, accion: AccionTurno) => despachar({ tipo: "turno", idAsistente, accion }),
    [],
  );
  const turnos = useTurno(cliente, despacharTurno, activo?.id);

  // Recupera la conversación guardada al recargar la página.
  useEffect(() => {
    const id = leerPreferencia<string | null>(CLAVE_CONVERSACION, null);
    if (!id) return;
    let vigente = true;
    cliente
      .obtenerConversacion(id)
      .then((conversacion) => {
        if (vigente && estadoRef.current.mensajes.length === 0) despachar({ tipo: "restaurar", conversacion });
      })
      .catch((error: unknown) => {
        if (error instanceof ErrorApi && error.tipo === "no_encontrado")
          escribirPreferencia(CLAVE_CONVERSACION, undefined);
      });
    return () => {
      vigente = false;
    };
  }, [cliente]);

  const enviar = useCallback(
    async (texto: string, opcionId?: string) => {
      const mensaje = texto.trim();
      if (!mensaje || ocupado.current || turnoEnCurso(estadoRef.current)) return;
      ocupado.current = true;
      const idAsistente = nuevoId("a");
      despachar({ tipo: "enviar", idUsuario: nuevoId("u"), idAsistente, texto: mensaje, opcionId, diagnostico });
      let conversacionId = estadoRef.current.conversacionId;
      try {
        if (!conversacionId) {
          conversacionId = (await cliente.crearConversacion()).conversacion_id;
          despachar({ tipo: "conversacion", conversacionId });
          escribirPreferencia(CLAVE_CONVERSACION, conversacionId);
        }
        const { turno_id } = await cliente.enviarTurno(conversacionId, {
          mensaje,
          diagnostico,
          ...(opcionId ? { opcion_id: opcionId } : {}),
        });
        despacharTurno(idAsistente, { tipo: "creado", turnoId: turno_id });
        turnos.escuchar(idAsistente, turno_id);
      } catch (error) {
        if (error instanceof ErrorApi && error.tipo === "saturado") {
          despacharTurno(idAsistente, { tipo: "saturado" });
          return;
        }
        if (error instanceof ErrorApi && error.tipo === "no_encontrado") {
          // La conversación ya no existe en el servidor: la próxima pregunta abre otra.
          despachar({ tipo: "conversacion", conversacionId: undefined });
          escribirPreferencia(CLAVE_CONVERSACION, undefined);
        }
        if (error instanceof ErrorApi && error.tipo === "red") alFallarRed?.();
        despacharTurno(idAsistente, { tipo: "fallo_envio" });
      }
    },
    [cliente, diagnostico, despacharTurno, turnos, alFallarRed],
  );

  const detener = useCallback(() => {
    const enCurso = turnoEnCurso(estadoRef.current);
    if (enCurso) turnos.detener(enCurso.id);
  }, [turnos]);

  const reintentar = useCallback(
    (idAsistente: string) => {
      const mensaje = estadoRef.current.mensajes.find(
        (m): m is MensajeAsistente => m.id === idAsistente && m.rol === "asistente",
      );
      if (!mensaje || turnoEnCurso(estadoRef.current)) return;
      despachar({ tipo: "descartar", idAsistente });
      void enviar(mensaje.solicitud.mensaje, mensaje.solicitud.opcionId);
    },
    [enviar],
  );

  const calificar = useCallback(
    async (idAsistente: string, valor: ValorCalificacion, comentario?: string) => {
      const mensaje = estadoRef.current.mensajes.find(
        (m): m is MensajeAsistente => m.id === idAsistente && m.rol === "asistente",
      );
      const turnoId = mensaje?.turno.turnoId;
      if (!turnoId) return;
      const nota = comentario?.trim() || undefined;
      despachar({ tipo: "calificar", idAsistente, calificacion: { valor, comentario: nota, estado: "guardando" } });
      try {
        await cliente.calificarTurno(turnoId, { valor, ...(nota ? { comentario: nota } : {}) });
        despachar({ tipo: "calificar", idAsistente, calificacion: { valor, comentario: nota, estado: "guardada" } });
      } catch {
        despachar({ tipo: "calificar", idAsistente, calificacion: { valor, comentario: nota, estado: "error" } });
      }
    },
    [cliente],
  );

  const exportar = useCallback(async () => {
    const id = estadoRef.current.conversacionId;
    if (!id) return false;
    try {
      const texto = await cliente.exportarConversacion(id);
      const url = URL.createObjectURL(new Blob([texto], { type: "text/markdown;charset=utf-8" }));
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = `conversacion-asistente-${new Date().toISOString().slice(0, 10)}.md`;
      document.body.append(enlace);
      enlace.click();
      enlace.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      return true;
    } catch {
      return false;
    }
  }, [cliente]);

  const nuevaConversacion = useCallback(() => {
    turnos.cerrarTodo();
    ocupado.current = false;
    escribirPreferencia(CLAVE_CONVERSACION, undefined);
    despachar({ tipo: "reiniciar" });
  }, [turnos]);

  return { estado, activo, enviar, detener, reintentar, calificar, exportar, nuevaConversacion };
}

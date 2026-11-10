/**
 * Reductor de la conversación (puro). Cada pregunta crea un par de mensajes: el del usuario y el del asistente,
 * que contiene la máquina de estados de su turno.
 */
import type {
  ConversacionGuardada,
  OpcionContrapregunta,
  SolicitudCalificacion,
  ValorCalificacion,
} from "@/lib/api/tipos";
import { estadoInicialTurno, reducirTurno, turnoActivo, type AccionTurno, type EstadoTurno } from "@/lib/turno/maquina";

export interface MensajeUsuario {
  id: string;
  rol: "usuario";
  texto: string;
  opcionId?: string;
}

export interface EstadoCalificacion {
  valor: ValorCalificacion;
  comentario?: string;
  estado: "editando" | "guardando" | "guardada" | "error";
}

export interface MensajeAsistente {
  id: string;
  rol: "asistente";
  /** Lo que se envió (para reintentar). */
  solicitud: { mensaje: string; opcionId?: string };
  diagnostico: boolean;
  turno: EstadoTurno;
  calificacion?: EstadoCalificacion;
  /** Id de la opción elegida de su contrapregunta. */
  opcionElegida?: string;
}

export type Mensaje = MensajeUsuario | MensajeAsistente;

export interface EstadoChat {
  conversacionId?: string;
  mensajes: Mensaje[];
}

export type AccionChat =
  | { tipo: "enviar"; idUsuario: string; idAsistente: string; texto: string; opcionId?: string; diagnostico: boolean }
  | { tipo: "conversacion"; conversacionId: string | undefined }
  | { tipo: "turno"; idAsistente: string; accion: AccionTurno }
  | { tipo: "calificar"; idAsistente: string; calificacion: EstadoCalificacion }
  | { tipo: "descartar"; idAsistente: string }
  | { tipo: "reiniciar" }
  | { tipo: "restaurar"; conversacion: ConversacionGuardada };

export const estadoInicialChat: EstadoChat = { mensajes: [] };

const esAsistente = (m: Mensaje): m is MensajeAsistente => m.rol === "asistente";

export function turnoEnCurso(estado: EstadoChat): MensajeAsistente | undefined {
  return estado.mensajes.filter(esAsistente).find((m) => turnoActivo(m.turno));
}

/** La contrapregunta solo admite respuesta si es el último mensaje y no se ha elegido opción. */
export function contrapreguntaActiva(estado: EstadoChat, idAsistente: string): boolean {
  const ultimo = estado.mensajes.at(-1);
  return (
    !!ultimo &&
    esAsistente(ultimo) &&
    ultimo.id === idAsistente &&
    !ultimo.opcionElegida &&
    !!ultimo.turno.respuesta?.contrapregunta
  );
}

function actualizarAsistente(
  estado: EstadoChat,
  id: string,
  cambio: (m: MensajeAsistente) => MensajeAsistente,
): EstadoChat {
  let cambiado = false;
  const mensajes = estado.mensajes.map((m) => {
    if (!esAsistente(m) || m.id !== id) return m;
    const nuevo = cambio(m);
    cambiado ||= nuevo !== m;
    return nuevo;
  });
  return cambiado ? { ...estado, mensajes } : estado;
}

function opcionDe(m: MensajeAsistente, opcionId: string): OpcionContrapregunta | undefined {
  return m.turno.respuesta?.contrapregunta?.opciones.find((o) => o.id === opcionId);
}

export function reducirChat(estado: EstadoChat, accion: AccionChat): EstadoChat {
  switch (accion.tipo) {
    case "enviar": {
      const texto = accion.texto.trim();
      if (!texto || turnoEnCurso(estado)) return estado;
      let base = estado;
      if (accion.opcionId) {
        const ultimo = estado.mensajes.at(-1);
        if (ultimo && esAsistente(ultimo) && opcionDe(ultimo, accion.opcionId)) {
          base = actualizarAsistente(estado, ultimo.id, (m) => ({ ...m, opcionElegida: accion.opcionId }));
        }
      }
      return {
        ...base,
        mensajes: [
          ...base.mensajes,
          { id: accion.idUsuario, rol: "usuario", texto, opcionId: accion.opcionId },
          {
            id: accion.idAsistente,
            rol: "asistente",
            solicitud: { mensaje: texto, opcionId: accion.opcionId },
            diagnostico: accion.diagnostico,
            turno: estadoInicialTurno(),
          },
        ],
      };
    }
    case "conversacion":
      return { ...estado, conversacionId: accion.conversacionId };
    case "turno":
      return actualizarAsistente(estado, accion.idAsistente, (m) => {
        const turno = reducirTurno(m.turno, accion.accion);
        return turno === m.turno ? m : { ...m, turno };
      });
    case "calificar":
      return actualizarAsistente(estado, accion.idAsistente, (m) => ({ ...m, calificacion: accion.calificacion }));
    case "descartar": {
      const i = estado.mensajes.findIndex((m) => m.id === accion.idAsistente);
      if (i < 0) return estado;
      const desde = i > 0 && estado.mensajes[i - 1].rol === "usuario" ? i - 1 : i;
      return { ...estado, mensajes: [...estado.mensajes.slice(0, desde), ...estado.mensajes.slice(i + 1)] };
    }
    case "reiniciar":
      return estadoInicialChat;
    case "restaurar":
      return restaurar(accion.conversacion);
  }
}

/** Reconstruye la conversación desde GET /conversaciones/{id}. */
export function restaurar(conversacion: ConversacionGuardada): EstadoChat {
  const mensajes: Mensaje[] = [];
  conversacion.turnos.forEach((t, i) => {
    mensajes.push({ id: `u-${t.turno_id}`, rol: "usuario", texto: t.mensaje, opcionId: t.opcion_id });
    const turno: EstadoTurno = {
      ...estadoInicialTurno(),
      turnoId: t.turno_id,
      fase: t.respuesta ? "listo" : "desconectado",
      respuesta: t.respuesta,
      avisos: t.avisos ?? [],
    };
    const siguiente = conversacion.turnos[i + 1];
    mensajes.push({
      id: `a-${t.turno_id}`,
      rol: "asistente",
      solicitud: { mensaje: t.mensaje, opcionId: t.opcion_id },
      diagnostico: false,
      turno,
      calificacion: t.calificacion ? calificacionGuardada(t.calificacion) : undefined,
      opcionElegida: siguiente?.opcion_id,
    });
  });
  return { conversacionId: conversacion.conversacion_id, mensajes };
}

function calificacionGuardada(c: SolicitudCalificacion): EstadoCalificacion {
  return { valor: c.valor, comentario: c.comentario, estado: "guardada" };
}

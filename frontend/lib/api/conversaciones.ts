/**
 * GET /conversaciones/{id}: el historial real del backend (`Historial` en backend/app/schemas/conversaciones.py), una
 * lista de mensajes usuario/asistente, adaptado a los turnos con los que el chat restaura la conversación.
 */
import type { ConversacionGuardada, HistorialApi, TurnoGuardado } from "./tipos";

export function conversacionDesdeApi(historial: HistorialApi): ConversacionGuardada {
  const turnos: TurnoGuardado[] = [];
  for (const m of historial.mensajes ?? []) {
    if (m.rol === "usuario" && m.turno_id) {
      turnos.push({ turno_id: m.turno_id, mensaje: m.texto ?? "" });
      continue;
    }
    const turno = turnos.find((t) => t.turno_id === m.turno_id);
    if (m.rol === "asistente" && turno && m.respuesta) turno.respuesta = m.respuesta;
  }
  return { conversacion_id: historial.conversacion_id, turnos };
}

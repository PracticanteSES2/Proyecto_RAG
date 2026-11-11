/**
 * Almacén en memoria del mock (solo con NEXT_PUBLIC_API_MOCK=1). Vive en `globalThis` para sobrevivir a la
 * recarga de módulos de `next dev` y para que todas las rutas compartan el mismo estado.
 */
import type {
  CapacidadesApi,
  ConversacionGuardada,
  HistorialApi,
  EventoAviso,
  EventoRespuesta,
  SolicitudCalificacion,
} from "@/lib/api/tipos";
import { guionPara, type PasoGuion } from "./guiones";

export interface TurnoMock {
  turnoId: string;
  conversacionId: string;
  mensaje: string;
  opcionId?: string;
  inicio: number;
  guion: PasoGuion[];
  calificacion?: SolicitudCalificacion;
}

interface Almacen {
  conversaciones: Map<string, string[]>;
  turnos: Map<string, TurnoMock>;
  caido: boolean;
  contador: number;
}

const global = globalThis as typeof globalThis & { __almacenMock?: Almacen };

export function almacen(): Almacen {
  global.__almacenMock ??= { conversaciones: new Map(), turnos: new Map(), caido: false, contador: 0 };
  return global.__almacenMock;
}

const nuevoId = (prefijo: string) => `${prefijo}-${Date.now().toString(36)}-${(almacen().contador++).toString(36)}`;

export function crearConversacion(): string {
  const id = nuevoId("conv");
  almacen().conversaciones.set(id, []);
  return id;
}

export function crearTurno(
  conversacionId: string,
  mensaje: string,
  diagnostico: boolean,
  opcionId?: string,
): TurnoMock | null {
  const turnos = almacen().conversaciones.get(conversacionId);
  if (!turnos) return null;
  const turnoId = nuevoId("turno");
  const turno: TurnoMock = {
    turnoId,
    conversacionId,
    mensaje,
    opcionId,
    inicio: Date.now(),
    guion: guionPara({ turnoId, mensaje, opcionId, diagnostico }),
  };
  almacen().turnos.set(turnoId, turno);
  turnos.push(turnoId);
  return turno;
}

const respuestaDe = (t: TurnoMock) =>
  t.guion.find((p) => p.evento.tipo === "respuesta")?.evento.datos as EventoRespuesta | undefined;
const avisosDe = (t: TurnoMock) =>
  t.guion.filter((p) => p.evento.tipo === "aviso").map((p) => p.evento.datos as EventoAviso);

export function conversacionGuardada(conversacionId: string): ConversacionGuardada | null {
  const ids = almacen().conversaciones.get(conversacionId);
  if (!ids) return null;
  return {
    conversacion_id: conversacionId,
    turnos: ids
      .map((id) => almacen().turnos.get(id))
      .filter((t): t is TurnoMock => !!t)
      .map((t) => ({
        turno_id: t.turnoId,
        mensaje: t.mensaje,
        opcion_id: t.opcionId,
        respuesta: respuestaDe(t),
        avisos: avisosDe(t),
        calificacion: t.calificacion,
      })),
  };
}

/** GET /conversaciones/{id} con la misma forma que el backend real (mensajes usuario/asistente). */
export function historialMock(conversacionId: string): HistorialApi | null {
  const conversacion = conversacionGuardada(conversacionId);
  if (!conversacion) return null;
  return {
    conversacion_id: conversacionId,
    mensajes: conversacion.turnos.flatMap((t) => [
      {
        rol: "usuario" as const,
        turno_id: t.turno_id,
        texto: t.mensaje,
        via: t.opcion_id ? ("opcion" as const) : ("texto" as const),
      },
      { rol: "asistente" as const, turno_id: t.turno_id, respuesta: t.respuesta ?? null },
    ]),
  };
}

export function exportarMarkdown(conversacionId: string): string | null {
  const conversacion = conversacionGuardada(conversacionId);
  if (!conversacion) return null;
  const partes = [
    "# Conversación con el Asistente de tableros",
    "",
    `_Exportada el ${new Date().toLocaleString("es-CO")}_`,
    "",
  ];
  conversacion.turnos.forEach((t, i) => {
    partes.push(`## ${i + 1}. ${t.mensaje}`, "");
    if (t.respuesta) {
      partes.push(t.respuesta.texto_markdown, "");
      t.respuesta.contrapregunta?.opciones.forEach((o) => partes.push(`- ${o.texto}`));
      t.respuesta.enlaces_powerbi.forEach((e) => partes.push(`[Abrir en Power BI › ${e.titulo}](${e.url})`, ""));
      if (t.respuesta.fuentes.length)
        partes.push(`**Fuentes:** ${t.respuesta.fuentes.map((f) => f.titulo).join(" · ")}`, "");
    }
    t.avisos?.forEach((a) => partes.push(`> ${a.texto}`, ""));
  });
  return partes.join("\n");
}

/** Misma forma que GET /capacidades del backend real (el cliente la adapta en lib/api/capacidades.ts). */
export const CAPACIDADES_MOCK: CapacidadesApi = {
  listo: true,
  tableros_datos: ["Tablero Gestion Camas", "Tablero Lavanderia", "Tablero Tiempos Urgencias"],
  tableros_documentacion: ["Tablero Gestion Camas"],
  ejemplos: [
    "¿Cuántos egresos hubo en marzo de 2026?",
    "Ocupación de camas en octubre",
    "¿Qué es un egreso hospitalario?",
    "Cirugías canceladas por especialidad en 2025",
  ],
};

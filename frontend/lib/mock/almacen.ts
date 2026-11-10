/**
 * Almacén en memoria del mock (solo con NEXT_PUBLIC_API_MOCK=1). Vive en `globalThis` para sobrevivir a la
 * recarga de módulos de `next dev` y para que todas las rutas compartan el mismo estado.
 */
import type {
  Capacidades,
  ConversacionGuardada,
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

export const CAPACIDADES_MOCK: Capacidades = {
  capacidades: [
    {
      titulo: "Cifras de los tableros",
      descripcion: "Egresos, cirugías, camas, urgencias, lavandería y más, con los filtros que necesites.",
    },
    {
      titulo: "Qué significa cada indicador",
      descripcion: "Definiciones y fichas técnicas tomadas de la documentación de los tableros.",
    },
    { titulo: "Ir directo a Power BI", descripcion: "Te dejo el enlace a la página del tablero donde está el dato." },
  ],
  ejemplos: [
    { texto: "¿Cuántos egresos hubo en marzo de 2026?", categoria: "Egresos" },
    { texto: "Ocupación de camas en octubre", categoria: "Capacidad" },
    { texto: "¿Qué es un egreso hospitalario?", categoria: "Documentación" },
    { texto: "Cirugías canceladas por especialidad en 2025", categoria: "Cirugía" },
  ],
};

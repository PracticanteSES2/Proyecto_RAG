import { act } from "@testing-library/react";
import { vi } from "vitest";
import { ErrorApi, type ClienteApi } from "@/lib/api/cliente";
import type { OpcionesEventos } from "@/lib/api/sse";
import type { EventoTurno } from "@/lib/api/tipos";

/** Cliente de la API falso: registra llamadas y deja emitir eventos SSE a mano. */
export function clienteFalso(sobrescribir: Partial<ClienteApi> = {}) {
  const flujos: OpcionesEventos[] = [];
  const cerrar = vi.fn();
  const cliente: ClienteApi = {
    crearConversacion: vi.fn(async () => ({ conversacion_id: "c1" })),
    enviarTurno: vi.fn(async () => ({ turno_id: "t1" })),
    eventosTurno: vi.fn((_id: string, opciones: OpcionesEventos) => {
      flujos.push(opciones);
      return { cerrar };
    }),
    obtenerConversacion: vi.fn(async () => {
      throw new ErrorApi("no_encontrado", "no");
    }),
    exportarConversacion: vi.fn(async () => "# md"),
    calificarTurno: vi.fn(async () => {}),
    capacidades: vi.fn(async () => ({
      capacidades: [{ titulo: "Cifras de los tableros", descripcion: "x" }],
      ejemplos: [{ texto: "¿Cuántos egresos hubo en marzo?" }],
    })),
    salud: vi.fn(async () => ({ estado: "ok" as const })),
    ...sobrescribir,
  };
  const emitir = (evento: EventoTurno) => act(() => flujos.at(-1)!.alEvento(evento));
  return { cliente, emitir, cerrar, flujos };
}

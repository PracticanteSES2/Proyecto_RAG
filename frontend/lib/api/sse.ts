/**
 * Suscripción a los eventos SSE de un turno con `EventSource` nativo.
 *
 * El navegador reconecta solo y envía `Last-Event-ID` (el backend numera cada evento con `id:`). Si la conexión
 * falla varias veces seguidas sin recibir nada, o el servidor la cierra, se informa con `alDesconectar`.
 */
import { TIPOS_EVENTO, type EventoTurno, type TipoEvento } from "./tipos";

export interface OpcionesEventos {
  alEvento: (evento: EventoTurno) => void;
  /** La conexión se perdió sin remedio (antes de `fin`). */
  alDesconectar?: () => void;
  /** Reintentos consecutivos sin eventos antes de rendirse. */
  maxReintentos?: number;
  /** Inyectable en pruebas. */
  crearFuente?: (url: string) => FuenteEventos;
}

/** Subconjunto de `EventSource` que se usa (permite falsearlo en pruebas). */
export interface FuenteEventos {
  readonly readyState: number;
  addEventListener(tipo: string, oyente: (evento: Event | MessageEvent<string>) => void): void;
  onerror: ((evento: Event) => void) | null;
  close(): void;
}

export interface SuscripcionEventos {
  cerrar(): void;
}

const CERRADA = 2;

/** Convierte un mensaje SSE crudo en un evento tipado; `null` si no se puede interpretar. */
export function interpretarEvento(tipo: string, datos: string): EventoTurno | null {
  if (!(TIPOS_EVENTO as readonly string[]).includes(tipo)) return null;
  let valor: unknown;
  try {
    valor = datos ? JSON.parse(datos) : {};
  } catch {
    return null;
  }
  if (typeof valor !== "object" || valor === null) return null;
  return { tipo: tipo as TipoEvento, datos: valor } as EventoTurno;
}

function esMensajeDeServidor(evento: Event | MessageEvent<string>): evento is MessageEvent<string> {
  return typeof (evento as Partial<MessageEvent<unknown>>).data === "string";
}

export function abrirEventosTurno(url: string, opciones: OpcionesEventos): SuscripcionEventos {
  const crear = opciones.crearFuente ?? ((u: string) => new EventSource(u) as unknown as FuenteEventos);
  const maxReintentos = opciones.maxReintentos ?? 5;
  const fuente = crear(url);
  let fallosSeguidos = 0;
  let terminada = false;

  const terminar = (desconectada: boolean) => {
    if (terminada) return;
    terminada = true;
    fuente.close();
    if (desconectada) opciones.alDesconectar?.();
  };

  for (const tipo of TIPOS_EVENTO) {
    fuente.addEventListener(tipo, (mensaje) => {
      // El evento de servidor «error» comparte nombre con el error nativo de conexión (sin `data`).
      if (terminada || !esMensajeDeServidor(mensaje)) return;
      fallosSeguidos = 0;
      const evento = interpretarEvento(tipo, mensaje.data);
      if (!evento) return;
      opciones.alEvento(evento);
      if (evento.tipo === "fin") terminar(false);
    });
  }

  fuente.onerror = (evento) => {
    if (terminada || esMensajeDeServidor(evento)) return;
    fallosSeguidos += 1;
    if (fuente.readyState === CERRADA || fallosSeguidos > maxReintentos) terminar(true);
  };

  return { cerrar: () => terminar(false) };
}

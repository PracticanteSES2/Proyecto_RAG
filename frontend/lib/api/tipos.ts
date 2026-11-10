/**
 * Tipos del contrato API v1 del backend (FastAPI).
 *
 * ÚNICO archivo de tipos de la API: está pensado para reemplazarse por tipos generados desde el OpenAPI del
 * backend (p. ej. `openapi-typescript`). Los supuestos que el contrato v1 no fija están marcados con «Supuesto»
 * y documentados en specs/007-frontend-chat/contracts/api-v1.md.
 */

// ---------------------------------------------------------------- REST

export interface ConversacionCreada {
  conversacion_id: string;
}

export interface SolicitudTurno {
  mensaje: string;
  diagnostico: boolean;
  opcion_id?: string;
}

export interface TurnoCreado {
  turno_id: string;
}

/** Supuesto: valores iguales a los del registro de calificaciones de Streamlit. */
export type ValorCalificacion = "buena" | "mala";

export interface SolicitudCalificacion {
  valor: ValorCalificacion;
  comentario?: string;
}

/** Supuesto: forma de GET /capacidades. */
export interface Capacidad {
  titulo: string;
  descripcion: string;
}

export interface EjemploPregunta {
  texto: string;
  categoria?: string;
}

export interface Capacidades {
  capacidades: Capacidad[];
  ejemplos: EjemploPregunta[];
}

/** Supuesto: forma de GET /salud. Cualquier fallo de red o respuesta no-2xx se trata como «caído». */
export interface Salud {
  estado: "ok" | "degradado";
  detalle?: string;
}

/** Supuesto: turno guardado que devuelve GET /conversaciones/{id} para restaurar el historial. */
export interface TurnoGuardado {
  turno_id: string;
  mensaje: string;
  opcion_id?: string;
  respuesta?: EventoRespuesta;
  avisos?: EventoAviso[];
  calificacion?: SolicitudCalificacion;
}

export interface ConversacionGuardada {
  conversacion_id: string;
  turnos: TurnoGuardado[];
}

// ---------------------------------------------------------------- SSE

export type Etapa =
  | "entendiendo"
  | "buscando_indicador"
  | "preparando_opciones"
  | "conectando_powerbi"
  | "consultando_powerbi"
  | "revisando_documentacion"
  | "redactando"
  | "en_cola"
  | "finalizando";

export interface EventoCola {
  /** 1 = es la siguiente; 0 = desconocida. */
  posicion: number;
  en_curso: number;
}

export interface EventoProgreso {
  etapa: Etapa;
  frase: string;
  /** Segundos desde el inicio del turno. Solo para ordenar/medir: nunca se muestra con diagnóstico apagado. */
  t: number;
}

export interface EventoEspera {
  /** 1..4 (umbrales 10, 25, 50, 90 s). Nunca se muestra como texto. */
  nivel: number;
  frase: string;
  t: number;
}

export interface Fuente {
  titulo: string;
  tablero?: string;
  pagina?: string;
}

export interface EnlacePowerBI {
  titulo: string;
  url: string;
}

export interface OpcionContrapregunta {
  id: string;
  texto: string;
  descripcion?: string;
}

export interface Contrapregunta {
  pregunta: string;
  opciones: OpcionContrapregunta[];
}

/** Supuesto: claves conocidas del objeto libre `diagnostico`; el resto se muestra como JSON. */
export interface Diagnostico {
  dax?: string;
  razonamiento?: string;
  tiempos?: { etapa: string; segundos: number }[];
  [clave: string]: unknown;
}

export interface EventoRespuesta {
  turno_id: string;
  texto_markdown: string;
  ruta: string;
  fuentes: Fuente[];
  enlaces_powerbi: EnlacePowerBI[];
  contrapregunta?: Contrapregunta;
  degradada: boolean;
  aviso?: string;
  diagnostico?: Diagnostico;
}

export type MotivoAviso = "saturado" | "sin_redaccion";

export interface EventoAviso {
  motivo: MotivoAviso;
  texto: string;
}

export interface EventoError {
  mensaje: string;
  codigo: string;
}

export type EventoFin = Record<string, never>;

/** Unión discriminada de todos los eventos SSE de un turno. */
export type EventoTurno =
  | { tipo: "cola"; datos: EventoCola }
  | { tipo: "progreso"; datos: EventoProgreso }
  | { tipo: "espera"; datos: EventoEspera }
  | { tipo: "respuesta"; datos: EventoRespuesta }
  | { tipo: "aviso"; datos: EventoAviso }
  | { tipo: "error"; datos: EventoError }
  | { tipo: "fin"; datos: EventoFin };

export type TipoEvento = EventoTurno["tipo"];

export const TIPOS_EVENTO: readonly TipoEvento[] = [
  "cola",
  "progreso",
  "espera",
  "respuesta",
  "aviso",
  "error",
  "fin",
] as const;

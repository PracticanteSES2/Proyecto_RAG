/** Reindexación del mock: `en_curso` ~2,5 s y luego `lista` (o `error` si se pidió fallar). */
import type { Reindexacion } from "@/lib/api/tiposDocumentacion";
import type { GrupoMock } from "./documentacion";

const DURACION_MS = 2_500;

interface EstadoMock {
  inicio: number;
  falla: boolean;
}

const global = globalThis as typeof globalThis & { __reindexacionesMock?: Map<string, EstadoMock> };
const estados = () => (global.__reindexacionesMock ??= new Map());

export function lanzarReindexacion(g: GrupoMock, falla = false): void {
  const actual = estados().get(g.grupo);
  if (actual && Date.now() - actual.inicio < DURACION_MS) return;
  estados().set(g.grupo, { inicio: Date.now(), falla });
}

export function estadoReindexacion(g: GrupoMock): Reindexacion {
  const base: Reindexacion = {
    grupo: g.grupo,
    estado: "sin_iniciar",
    mensaje: "",
    documentos: null,
    chunks: null,
    segundos: null,
    conexion_compartida: false,
    avisos: [],
    iniciada: null,
    terminada: null,
  };
  const actual = estados().get(g.grupo);
  if (!actual) return base;
  const iniciada = new Date(actual.inicio).toISOString();
  if (Date.now() - actual.inicio < DURACION_MS) {
    return { ...base, estado: "en_curso", mensaje: "Actualizando el buscador del asistente…", iniciada };
  }
  const terminada = new Date(actual.inicio + DURACION_MS).toISOString();
  if (actual.falla) {
    // El reintento manual (POST …/reindexar → lanzarReindexacion sin falla) sí termina bien.
    return {
      ...base,
      estado: "error",
      mensaje: "La reindexación falló: (simulado) no se pudo escribir el índice del tablero.",
      iniciada,
      terminada,
    };
  }
  const documentos = g.docs.length;
  return {
    ...base,
    estado: "lista",
    mensaje: `El asistente ya usa el texto nuevo: se reindexó ${g.tablero} (${documentos} documentos, ${documentos * 4} fragmentos, 2.5 s) con la conexión del chat.`,
    documentos,
    chunks: documentos * 4,
    segundos: 2.5,
    conexion_compartida: true,
    iniciada,
    terminada,
  };
}

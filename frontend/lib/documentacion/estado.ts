/**
 * Utilidades puras de la página de documentación: cuándo sondear una propuesta y el filtro del explorador. No
 * deciden nada del negocio (estados, diff, si se puede aprobar: todo viene del backend).
 */
import type { GrupoDocumentacion, PaginaResumen, Propuesta } from "@/lib/api/tiposDocumentacion";

export const SONDEO_MS = 1_000;
export const SONDEO_ERROR_MS = 3_000;

/** Se sondea mientras MedGemma prepara la propuesta o mientras se reindexa tras aprobarla. */
export function debeSondear(p: Propuesta | null): boolean {
  if (!p) return false;
  return p.estado === "preparando" || p.aprobacion?.reindexacion.estado === "en_curso";
}

/** Minúsculas y sin tildes, para buscar «urgencias» o «lavanderia» sin importar cómo se escriba. */
export function plegar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

/** ¿El texto (ya plegado) contiene la clave? Es búsqueda en un texto, no en una lista. */
const contiene = (texto: string, clave: string) => texto.includes(clave);

export interface GrupoFiltrado {
  grupo: GrupoDocumentacion;
  paginas: PaginaResumen[];
  /** El nombre del tablero coincide: se muestran todas sus páginas. */
  coincideTablero: boolean;
}

/**
 * Tableros y páginas que coinciden con la búsqueda (nombre del tablero o del grupo; página, nombre funcional o
 * archivo). Sin búsqueda, todo.
 */
export function filtrarExplorador(
  grupos: GrupoDocumentacion[],
  paginas: Record<string, PaginaResumen[] | undefined>,
  busqueda: string,
): GrupoFiltrado[] {
  const clave = plegar(busqueda);
  return grupos.flatMap((grupo) => {
    const todas = paginas[grupo.grupo] ?? [];
    if (!clave) return [{ grupo, paginas: todas, coincideTablero: false }];
    const coincideTablero = contiene(plegar(`${grupo.tablero} ${grupo.grupo}`), clave);
    const coinciden = coincideTablero
      ? todas
      : todas.filter((p) => contiene(plegar(`${p.etiqueta} ${p.archivo}`), clave));
    return coincideTablero || coinciden.length ? [{ grupo, paginas: coinciden, coincideTablero }] : [];
  });
}

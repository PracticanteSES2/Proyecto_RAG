/**
 * Revelado de respuestas (puro, sin DOM): la respuesta «aparece» con una escritura rápida y natural.
 *
 * - El texto se parte en unidades: palabras (con su espacio) para la prosa y bloques completos para tablas y
 *   código, que nunca se muestran a medias. `unidades.join("") === texto`.
 * - Respuesta completa (Power BI, portero): se revela en ≤ DURACION_MAX_MS.
 * - Tras el streaming (`token`): si la respuesta final empieza por el borrador, se sigue escribiendo desde donde
 *   iba (sin salto); si la salvaguarda cambió el texto, se muestra completa con un fundido suave.
 *
 * Contrato: specs/003-progreso-chat/contracts/eventos.md («Reglas para el frontend»).
 */

export const DURACION_MAX_MS = 700;
const MS_POR_UNIDAD = 22;
const DURACION_MIN_MS = 120;

const esLineaDeBloque = (linea: string) => /^\s*\|/.test(linea);

/** Unidades de revelado; su concatenación es exactamente el texto. */
export function unidadesRevelado(texto: string): string[] {
  const unidades: string[] = [];
  const lineas = texto.match(/[^\n]*\n|[^\n]+$/g) ?? [];
  let bloque = "";
  let enCodigo = false;
  const cerrarBloque = () => {
    if (bloque) unidades.push(bloque);
    bloque = "";
  };
  for (const linea of lineas) {
    const cerco = /^\s*```/.test(linea);
    if (enCodigo || cerco || esLineaDeBloque(linea)) {
      bloque += linea;
      if (cerco) enCodigo = !enCodigo;
      if (!enCodigo && !esLineaDeBloque(linea) && !cerco) cerrarBloque();
      continue;
    }
    cerrarBloque();
    unidades.push(...(linea.match(/\S+\s*|\s+/g) ?? []));
  }
  cerrarBloque();
  return unidades;
}

const plano = (texto: string) => texto.replace(/\s+/g, " ").trim();

/**
 * Cuántas unidades de la respuesta final ya estaban en el borrador, o -1 si la final no empieza por el
 * borrador (la salvaguarda o el post-proceso cambiaron el texto).
 */
export function unidadesCubiertas(unidades: string[], borrador: string): number {
  const objetivo = plano(borrador);
  if (!objetivo) return 0;
  if (!plano(unidades.join("")).startsWith(objetivo)) return -1;
  let acumulado = "";
  for (let i = 0; i < unidades.length; i += 1) {
    const siguiente = plano(acumulado + unidades[i]);
    if (siguiente.length > objetivo.length) return i;
    acumulado += unidades[i];
  }
  return unidades.length;
}

export function duracionRevelado(pendientes: number): number {
  if (pendientes <= 0) return 0;
  return Math.min(DURACION_MAX_MS, Math.max(DURACION_MIN_MS, pendientes * MS_POR_UNIDAD));
}

/** Unidades visibles tras `transcurridoMs` desde `inicio` (curva suave: arranca rápido y se asienta). */
export function unidadesVisibles(inicio: number, total: number, transcurridoMs: number): number {
  const duracion = duracionRevelado(total - inicio);
  if (duracion === 0 || transcurridoMs >= duracion) return total;
  const avance = 1 - (1 - transcurridoMs / duracion) ** 2;
  return Math.min(total, inicio + Math.ceil((total - inicio) * avance));
}

export interface PlanRevelado {
  unidades: string[];
  /** Unidades visibles al empezar. */
  inicio: number;
  /** La final no coincide con el borrador: se muestra completa con un fundido suave. */
  fundido: boolean;
}

export function planRevelado(texto: string, borrador: string | undefined, animar: boolean): PlanRevelado {
  const unidades = unidadesRevelado(texto);
  if (!animar) return { unidades, inicio: unidades.length, fundido: false };
  if (!borrador?.trim()) return { unidades, inicio: 0, fundido: false };
  const cubiertas = unidadesCubiertas(unidades, borrador);
  if (cubiertas < 0) return { unidades, inicio: unidades.length, fundido: true };
  return { unidades, inicio: cubiertas, fundido: false };
}

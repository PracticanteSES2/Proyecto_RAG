/**
 * Contenido del mock: frases, tabla de ejemplo, diagnóstico simulado y utilidades para armar guiones.
 * Lo consume lib/mock/guiones.ts.
 */
import type { Diagnostico, Etapa, EventoRespuesta, EventoTurno, TipoEvento } from "@/lib/api/tipos";

export interface PasoGuion {
  /** Milisegundos desde la creación del turno. */
  ms: number;
  evento: EventoTurno;
}

export interface EntradaGuion {
  turnoId: string;
  mensaje: string;
  opcionId?: string;
  diagnostico: boolean;
}

export const normalizar = (texto: string) =>
  texto
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

export const FRASES: Record<Etapa, string> = {
  entendiendo: "Entendiendo tu pregunta",
  buscando_indicador: "Buscando el indicador en los tableros",
  preparando_opciones: "Preparando las opciones para que elijas",
  conectando_powerbi: "Conectando con Power BI",
  consultando_powerbi: "Consultando los datos en Power BI",
  revisando_documentacion: "Revisando la documentación de los tableros",
  redactando: "Redactando la respuesta",
  finalizando: "Ya casi está",
};

/** Frases de rotación (las mismas de src/chatbot/frases_progreso.py): la etapa se alarga, la frase avanza. */
export const SEGUIMIENTO: Partial<Record<Etapa, string[]>> = {
  entendiendo: ["Pensando…", "Precisando qué dato necesitas", "Pensando en la mejor forma de responderte"],
  consultando_powerbi: ["Esperando las cifras del tablero", "Revisando las cifras que llegan", "Pensando…"],
  revisando_documentacion: [
    "Revisando los datos que encontré",
    "Organizando la respuesta",
    "Redactando la respuesta",
    "Pensando…",
  ],
};

/** Esperas largas: hablan del trabajo con la pregunta, nunca de otros ni de la carga. */
export const ESPERAS = [
  "Sigo trabajando en tu pregunta…",
  "Estoy armando una respuesta completa; ya casi la tengo…",
  "Sigo con tu pregunta; no hace falta volver a enviarla.",
  "Me está tomando más de lo habitual, pero sigo en ello.",
];

/** Nota neutra de la respuesta extractiva (src/chatbot/frases_progreso.py: AVISO_EXTRACTIVO). */
export const AVISO_EXTRACTIVO = "Te muestro lo que dice la documentación.";

export type Paso = [ms: number, tipo: TipoEvento, datos: unknown];

export const progreso = (ms: number, etapa: Etapa): Paso => [
  ms,
  "progreso",
  { etapa, frase: FRASES[etapa], t: Math.round(ms / 100) / 10 },
];
/** Rotación: misma etapa, la siguiente frase de su seguimiento, cada `cadaMs` a partir de `desdeMs`. */
export const rotaciones = (desdeMs: number, hastaMs: number, etapa: Etapa, cadaMs = 8000): Paso[] => {
  const frases = SEGUIMIENTO[etapa] ?? [];
  const pasos: Paso[] = [];
  for (let ms = desdeMs + cadaMs, i = 0; frases.length && ms < hastaMs; ms += cadaMs, i += 1) {
    pasos.push([ms, "progreso", { etapa, frase: frases[i % frases.length], t: Math.round(ms / 100) / 10 }]);
  }
  return pasos;
};

/** Eventos `token`: el texto en trozos de unas pocas palabras, cada `msPorTrozo`. */
export const tokens = (desdeMs: number, texto: string, msPorTrozo = 70): Paso[] =>
  (texto.match(/\S+\s*\S*\s*|\s+/g) ?? []).map((trozo, i) => [desdeMs + i * msPorTrozo, "token", { texto: trozo }]);

export const espera = (ms: number, nivel: number): Paso => [
  ms,
  "espera",
  { nivel, frase: ESPERAS[nivel - 1], t: ms / 1000 },
];

export const TABLA_EGRESOS = `En **marzo de 2026** se registraron **1.284 egresos** hospitalarios, un **4,2 %** más que en febrero.

| Servicio | Egresos | Estancia promedio (días) |
|---|---:|---:|
| Medicina interna | 412 | 6,1 |
| Cirugía general | 318 | 3,4 |
| Ginecobstetricia | 279 | 2,2 |
| Pediatría | 163 | 4,0 |
| UCI adultos | 112 | 7,8 |

El servicio con más egresos fue **Medicina interna**. Los datos salen del tablero de *Egresos hospitalarios*, página *Resumen mensual*, con el filtro de mes aplicado.`;

export const DEFINICION_EGRESO = `Un **egreso hospitalario** es la salida del paciente del servicio de hospitalización, vivo o por defunción. Se cuenta en el mes en que ocurre la salida.

- Incluye los traslados a otra institución.
- No incluye los traslados internos entre servicios.

En el tablero de *Egresos hospitalarios* lo ves en la página *Resumen mensual*.`;

/** Lo que el modelo «dijo» de más (una cifra sin respaldo): la salvaguarda la quita de la respuesta final. */
export const FRASE_SIN_RESPALDO = " En 2025 los egresos subieron un 12 % frente al año anterior.";

export function diagnosticoDe(entrada: EntradaGuion, ruta: string, tiempos: Paso[]): Diagnostico | undefined {
  if (!entrada.diagnostico) return undefined;
  const etapas = tiempos
    .filter(([, tipo]) => tipo === "progreso")
    .map(([ms, , d]) => ({
      etapa: (d as { etapa: string }).etapa,
      segundos: ms / 1000,
    }));
  return {
    ruta,
    estado: "success",
    razonamiento: `1. Interpreté «${entrada.mensaje}» como consulta de ${ruta === "rag" ? "documentación" : "indicador"}.\n2. Elegí el tablero con mayor coincidencia semántica.\n3. Apliqué los filtros de periodo detectados.`,
    dax:
      ruta === "powerbi"
        ? `EVALUATE\nSUMMARIZECOLUMNS(\n  'Servicio'[Nombre],\n  TREATAS({"2026-03"}, 'Calendario'[AñoMes]),\n  "Egresos", [Total egresos],\n  "Estancia", [Estancia promedio]\n)`
        : undefined,
    tiempos: etapas,
    query_plan: { metrica: "Total egresos", filtros: { AñoMes: "2026-03" }, agrupar_por: ["Servicio"] },
    modelo_semantico: "Egresos hospitalarios",
  };
}

export function armar(pasos: Paso[]): PasoGuion[] {
  return pasos.map(([ms, tipo, datos]) => ({ ms, evento: { tipo, datos } as EventoTurno }));
}

export function respuestaBase(entrada: EntradaGuion, extra: Partial<EventoRespuesta>): EventoRespuesta {
  return {
    turno_id: entrada.turnoId,
    texto_markdown: "",
    ruta: "powerbi",
    fuentes: [],
    enlaces_powerbi: [],
    degradada: false,
    ...extra,
  };
}

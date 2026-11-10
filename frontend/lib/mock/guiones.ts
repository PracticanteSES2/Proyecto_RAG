/**
 * Guiones del mock: qué eventos SSE emite un turno y cuándo. Puro y determinista (se prueba sin servidor).
 *
 * Palabras clave para probar cada caso desde el chat:
 *   «hola», «gracias»          → saludo instantáneo (el indicador nunca llega a verse)
 *   «ocupación», «cuál»        → contrapregunta con opciones
 *   «qué es», «documentación»  → respuesta documental degradada + evento `aviso`
 *   «cola»                     → eventos `cola` antes de empezar
 *   «lento»                    → esperas largas con eventos `espera` del servidor
 *   «respaldo»                 → espera larga SIN eventos `espera` (frases generadas por el cliente)
 *   «error»                    → evento `error`
 *   «429»                      → POST /turnos responde 429 (lo decide la ruta, ver `debeSaturar`)
 *   cualquier otra             → respuesta de Power BI con tabla, fuentes y enlace
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
    .replace(/[̀-ͯ]/g, "");

export function debeSaturar(mensaje: string): boolean {
  return normalizar(mensaje).includes("429");
}

const FRASES: Record<Etapa, string> = {
  entendiendo: "Entendiendo tu pregunta",
  buscando_indicador: "Buscando el indicador en los tableros",
  preparando_opciones: "Preparando las opciones para que elijas",
  conectando_powerbi: "Conectando con Power BI",
  consultando_powerbi: "Consultando los datos en Power BI",
  revisando_documentacion: "Revisando la documentación de los tableros",
  redactando: "Redactando la respuesta",
  en_cola: "Tu pregunta está en fila; enseguida la atiendo",
  finalizando: "Ya casi está",
};

const ESPERAS = [
  "Esto está tomando un poco más de lo normal…",
  "Power BI está tardando en responder; sigo esperando los datos.",
  "Sigue en marcha: no hace falta volver a enviar la pregunta.",
  "Está tardando más de lo habitual; sigo esperando la respuesta.",
];

type Paso = [ms: number, tipo: TipoEvento, datos: unknown];

const progreso = (ms: number, etapa: Etapa): Paso => [ms, "progreso", { etapa, frase: FRASES[etapa], t: Math.round(ms / 100) / 10 }];
const espera = (ms: number, nivel: number): Paso => [ms, "espera", { nivel, frase: ESPERAS[nivel - 1], t: ms / 1000 }];

const TABLA_EGRESOS = `En **marzo de 2026** se registraron **1.284 egresos** hospitalarios, un **4,2 %** más que en febrero.

| Servicio | Egresos | Estancia promedio (días) |
|---|---:|---:|
| Medicina interna | 412 | 6,1 |
| Cirugía general | 318 | 3,4 |
| Ginecobstetricia | 279 | 2,2 |
| Pediatría | 163 | 4,0 |
| UCI adultos | 112 | 7,8 |

El servicio con más egresos fue **Medicina interna**. Los datos salen del tablero de *Egresos hospitalarios*, página *Resumen mensual*, con el filtro de mes aplicado.`;

function diagnosticoDe(entrada: EntradaGuion, ruta: string, tiempos: Paso[]): Diagnostico | undefined {
  if (!entrada.diagnostico) return undefined;
  const etapas = tiempos.filter(([, tipo]) => tipo === "progreso").map(([ms, , d]) => ({
    etapa: (d as { etapa: string }).etapa,
    segundos: ms / 1000,
  }));
  return {
    ruta,
    estado: "success",
    razonamiento: `1. Interpreté «${entrada.mensaje}» como consulta de ${ruta === "rag" ? "documentación" : "indicador"}.\n2. Elegí el tablero con mayor coincidencia semántica.\n3. Apliqué los filtros de periodo detectados.`,
    dax: ruta === "powerbi"
      ? `EVALUATE\nSUMMARIZECOLUMNS(\n  'Servicio'[Nombre],\n  TREATAS({"2026-03"}, 'Calendario'[AñoMes]),\n  "Egresos", [Total egresos],\n  "Estancia", [Estancia promedio]\n)`
      : undefined,
    tiempos: etapas,
    query_plan: { metrica: "Total egresos", filtros: { AñoMes: "2026-03" }, agrupar_por: ["Servicio"] },
    modelo_semantico: "Egresos hospitalarios",
  };
}

function armar(pasos: Paso[]): PasoGuion[] {
  return pasos.map(([ms, tipo, datos]) => ({ ms, evento: { tipo, datos } as EventoTurno }));
}

function respuestaBase(entrada: EntradaGuion, extra: Partial<EventoRespuesta>): EventoRespuesta {
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

export function guionPara(entrada: EntradaGuion): PasoGuion[] {
  const texto = normalizar(entrada.mensaje);
  const tiene = (...palabras: string[]) => palabras.some((p) => texto.includes(p));

  if (!entrada.opcionId && /^(hola|buenas|buenos|gracias|ok|listo)\b/.test(texto)) {
    const pasos: Paso[] = [progreso(40, "entendiendo")];
    return armar([
      ...pasos,
      [280, "respuesta", respuestaBase(entrada, {
        ruta: "conversacion",
        texto_markdown: tiene("gracias")
          ? "¡Con gusto! Si necesitas otra cifra, aquí estoy."
          : "¡Hola! Pregúntame por indicadores, filtros y datos de los tableros institucionales. Por ejemplo: *¿Cuántos egresos hubo en marzo de 2026?*",
        diagnostico: diagnosticoDe(entrada, "conversacion", pasos),
      })],
      [300, "fin", {}],
    ]);
  }

  if (tiene("error")) {
    return armar([
      progreso(50, "entendiendo"),
      progreso(1300, "conectando_powerbi"),
      [2600, "error", { mensaje: "La consulta DAX superó el tiempo máximo (TimeoutError)", codigo: "powerbi_timeout" }],
      [2620, "fin", {}],
    ]);
  }

  if (!entrada.opcionId && tiene("ocupacion", "cual")) {
    const pasos: Paso[] = [progreso(50, "entendiendo"), progreso(1100, "buscando_indicador"), progreso(2100, "preparando_opciones")];
    return armar([
      ...pasos,
      [3400, "respuesta", respuestaBase(entrada, {
        ruta: "aclaracion",
        texto_markdown: "Encontré varios indicadores de **ocupación**. ¿Cuál quieres consultar?",
        contrapregunta: {
          pregunta: "¿Qué ocupación te interesa?",
          opciones: [
            { id: "ocup-uci", texto: "Ocupación de UCI adultos", descripcion: "Camas de cuidado intensivo ocupadas sobre disponibles, por día." },
            { id: "ocup-hosp", texto: "Ocupación de hospitalización general", descripcion: "Porcentaje de camas de hospitalización ocupadas en el mes." },
            { id: "ocup-quir", texto: "Ocupación de salas de cirugía", descripcion: "Horas de quirófano usadas sobre horas programadas." },
          ],
        },
        diagnostico: diagnosticoDe(entrada, "aclaracion", pasos),
      })],
      [3420, "fin", {}],
    ]);
  }

  if (entrada.opcionId) {
    const pasos: Paso[] = [progreso(50, "entendiendo"), progreso(900, "consultando_powerbi"), progreso(2600, "finalizando")];
    return armar([
      ...pasos,
      [3000, "respuesta", respuestaBase(entrada, {
        texto_markdown: `**${entrada.mensaje}** en octubre de 2026: **87,4 %**, 2,1 puntos por encima de septiembre.`,
        fuentes: [{ titulo: "Indicadores de capacidad instalada", tablero: "Capacidad instalada", pagina: "Ocupación" }],
        enlaces_powerbi: [{ titulo: "Capacidad instalada · Ocupación", url: "https://app.powerbi.com/groups/me/reports/demo/ReportSection2" }],
        diagnostico: diagnosticoDe(entrada, "powerbi", pasos),
      })],
      [3020, "fin", {}],
    ]);
  }

  if (tiene("que es", "documentacion", "definicion", "explica")) {
    const pasos: Paso[] = [progreso(50, "entendiendo"), progreso(1000, "revisando_documentacion"), progreso(3800, "finalizando")];
    return armar([
      ...pasos,
      [4200, "respuesta", respuestaBase(entrada, {
        ruta: "rag",
        degradada: true,
        texto_markdown: "Según la documentación del tablero de **Egresos hospitalarios**:\n\n> *Egreso*: salida del paciente del servicio de hospitalización, vivo o por defunción. Se cuenta en el mes en que ocurre la salida.\n\n- Incluye traslados a otra institución.\n- No incluye traslados internos entre servicios.",
        fuentes: [
          { titulo: "Ficha técnica de indicadores", tablero: "Egresos hospitalarios", pagina: "Definiciones" },
          { titulo: "Manual del tablero de egresos" },
        ],
        diagnostico: diagnosticoDe(entrada, "rag", pasos),
      })],
      [4250, "aviso", { motivo: "sin_redaccion", texto: "Hay mucha demanda en este momento: te muestro los fragmentos de la documentación tal como están, sin redactarlos." }],
      [4270, "fin", {}],
    ]);
  }

  let desfase = 0;
  const previos: Paso[] = [];
  if (tiene("cola")) {
    previos.push([30, "cola", { posicion: 3, en_curso: 1 }], [2500, "cola", { posicion: 2, en_curso: 1 }], [5000, "cola", { posicion: 1, en_curso: 1 }]);
    desfase = 7000;
  }
  const lento = tiene("lento");
  const respaldo = tiene("respaldo");
  const escala = lento ? 5.5 : respaldo ? 2.6 : 1;
  const pasos: Paso[] = [
    progreso(desfase + 40, "entendiendo"),
    progreso(desfase + 1200 * escala, "buscando_indicador"),
    progreso(desfase + 2200 * escala, "conectando_powerbi"),
    progreso(desfase + 3000 * escala, "consultando_powerbi"),
    progreso(desfase + 4600 * escala, "redactando"),
    progreso(desfase + 5400 * escala, "finalizando"),
  ];
  const esperas: Paso[] = lento ? [espera(10000, 1), espera(25000, 2)] : [];
  const fin = desfase + 5800 * escala;
  return armar([
    ...previos,
    ...[...pasos, ...esperas].sort((a, b) => a[0] - b[0]),
    [fin, "respuesta", respuestaBase(entrada, {
      texto_markdown: TABLA_EGRESOS,
      fuentes: [{ titulo: "Egresos hospitalarios", tablero: "Egresos hospitalarios", pagina: "Resumen mensual" }],
      enlaces_powerbi: [
        { titulo: "Egresos hospitalarios · Resumen mensual", url: "https://app.powerbi.com/groups/me/reports/demo/ReportSection1" },
      ],
      diagnostico: diagnosticoDe(entrada, "powerbi", pasos),
    })],
    [fin + 20, "fin", {}],
  ]);
}

/** Todos los pasos llevan id 1..n en orden: es el `id:` del SSE (Last-Event-ID). */
export function pasosDesde(guion: PasoGuion[], ultimoId: number): { id: number; paso: PasoGuion }[] {
  return guion.map((paso, i) => ({ id: i + 1, paso })).filter(({ id }) => id > ultimoId);
}

export function formatearSSE(id: number, evento: EventoTurno): string {
  return `id: ${id}\nevent: ${evento.tipo}\ndata: ${JSON.stringify(evento.datos)}\n\n`;
}

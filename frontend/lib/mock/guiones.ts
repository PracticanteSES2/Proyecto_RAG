/**
 * Guiones del mock: qué eventos SSE emite un turno y cuándo. Puro y determinista (se prueba sin servidor).
 *
 * Palabras clave para probar cada caso desde el chat:
 *   «hola», «gracias»          → saludo instantáneo (el indicador nunca llega a verse)
 *   «ocupación», «cuál»        → contrapregunta con opciones
 *   «qué es», «explica»        → respuesta documental que aparece de a poco (eventos `token`)
 *   «salvaguarda»              → streaming cuyo borrador trae una cifra sin respaldo: la final la quita (fundido)
 *   «documentación»            → respuesta documental extractiva + `aviso` con la nota neutra
 *   «cola»                     → espera larga por carga: eventos `cola` (solo diagnóstico) y, a la vista,
 *                                 solo trabajo sobre la pregunta (rotación de frases y espera tranquila)
 *   «lento»                    → esperas largas con eventos `espera` del servidor y rotación de frases
 *   «respaldo»                 → espera larga SIN eventos `espera` (frases generadas por el cliente)
 *   «error»                    → evento `error`
 *   «429»                      → POST /turnos responde 429 (lo decide la ruta, ver `debeSaturar`)
 *   cualquier otra             → respuesta de Power BI con tabla, fuentes y enlace
 */
import type { EventoTurno } from "@/lib/api/tipos";
import {
  armar,
  AVISO_EXTRACTIVO,
  diagnosticoDe,
  espera,
  normalizar,
  progreso,
  respuestaBase,
  rotaciones,
  TABLA_EGRESOS,
  type EntradaGuion,
  type Paso,
  type PasoGuion,
} from "./contenido";
import { guionStreaming } from "./guionStreaming";

export type { EntradaGuion, PasoGuion } from "./contenido";

export function debeSaturar(mensaje: string): boolean {
  return normalizar(mensaje).includes("429");
}

export function guionPara(entrada: EntradaGuion): PasoGuion[] {
  const texto = normalizar(entrada.mensaje);
  const tiene = (...palabras: string[]) => palabras.some((p) => texto.includes(p));

  if (!entrada.opcionId && /^(hola|buenas|buenos|gracias|ok|listo)\b/.test(texto)) {
    const pasos: Paso[] = [progreso(40, "entendiendo")];
    return armar([
      ...pasos,
      [
        280,
        "respuesta",
        respuestaBase(entrada, {
          ruta: "conversacion",
          texto_markdown: tiene("gracias")
            ? "¡Con gusto! Si necesitas otra cifra, aquí estoy."
            : "¡Hola! Pregúntame por indicadores, filtros y datos de los tableros institucionales. Por ejemplo: *¿Cuántos egresos hubo en marzo de 2026?*",
          diagnostico: diagnosticoDe(entrada, "conversacion", pasos),
        }),
      ],
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
    const pasos: Paso[] = [
      progreso(50, "entendiendo"),
      progreso(1100, "buscando_indicador"),
      progreso(2100, "preparando_opciones"),
    ];
    return armar([
      ...pasos,
      [
        3400,
        "respuesta",
        respuestaBase(entrada, {
          ruta: "aclaracion",
          texto_markdown: "Encontré varios indicadores de **ocupación**. ¿Cuál quieres consultar?",
          contrapregunta: {
            pregunta: "¿Qué ocupación te interesa?",
            opciones: [
              {
                id: "ocup-uci",
                texto: "Ocupación de UCI adultos",
                descripcion: "Camas de cuidado intensivo ocupadas sobre disponibles, por día.",
              },
              {
                id: "ocup-hosp",
                texto: "Ocupación de hospitalización general",
                descripcion: "Porcentaje de camas de hospitalización ocupadas en el mes.",
              },
              {
                id: "ocup-quir",
                texto: "Ocupación de salas de cirugía",
                descripcion: "Horas de quirófano usadas sobre horas programadas.",
              },
            ],
          },
          diagnostico: diagnosticoDe(entrada, "aclaracion", pasos),
        }),
      ],
      [3420, "fin", {}],
    ]);
  }

  if (entrada.opcionId) {
    const pasos: Paso[] = [
      progreso(50, "entendiendo"),
      progreso(900, "consultando_powerbi"),
      progreso(2600, "finalizando"),
    ];
    return armar([
      ...pasos,
      [
        3000,
        "respuesta",
        respuestaBase(entrada, {
          texto_markdown: `**${entrada.mensaje}** en octubre de 2026: **87,4 %**, 2,1 puntos por encima de septiembre.`,
          fuentes: [
            { titulo: "Indicadores de capacidad instalada", tablero: "Capacidad instalada", pagina: "Ocupación" },
          ],
          enlaces_powerbi: [
            {
              titulo: "Capacidad instalada · Ocupación",
              url: "https://app.powerbi.com/groups/me/reports/demo/ReportSection2",
            },
          ],
          diagnostico: diagnosticoDe(entrada, "powerbi", pasos),
        }),
      ],
      [3020, "fin", {}],
    ]);
  }

  if (!tiene("documentacion") && tiene("que es", "definicion", "explica", "salvaguarda")) {
    return guionStreaming(entrada, tiene("salvaguarda"));
  }

  if (tiene("documentacion")) {
    const pasos: Paso[] = [
      progreso(50, "entendiendo"),
      progreso(1000, "revisando_documentacion"),
      progreso(3800, "finalizando"),
    ];
    return armar([
      ...pasos,
      [
        4200,
        "respuesta",
        respuestaBase(entrada, {
          ruta: "rag",
          degradada: true,
          texto_markdown:
            "Según la documentación del tablero de **Egresos hospitalarios**:\n\n> *Egreso*: salida del paciente del servicio de hospitalización, vivo o por defunción. Se cuenta en el mes en que ocurre la salida.\n\n- Incluye traslados a otra institución.\n- No incluye traslados internos entre servicios.",
          fuentes: [
            { titulo: "Ficha técnica de indicadores", tablero: "Egresos hospitalarios", pagina: "Definiciones" },
            { titulo: "Manual del tablero de egresos" },
          ],
          diagnostico: diagnosticoDe(entrada, "rag", pasos),
        }),
      ],
      [4250, "aviso", { motivo: "saturado", texto: AVISO_EXTRACTIVO }],
      [4270, "fin", {}],
    ]);
  }

  let desfase = 0;
  const previos: Paso[] = [];
  if (tiene("cola")) {
    // Espera por carga. Como el backend: `cola` solo llega con diagnóstico; a la vista, trabajo sobre la pregunta.
    desfase = 12000;
    const colas: Paso[] = entrada.diagnostico
      ? [
          [30, "cola", { posicion: 3, en_curso: 3 }],
          [4000, "cola", { posicion: 2, en_curso: 3 }],
          [8000, "cola", { posicion: 1, en_curso: 3 }],
        ]
      : [];
    previos.push(progreso(20, "entendiendo"), ...colas, ...rotaciones(20, desfase, "entendiendo"), espera(10000, 1));
  }
  const lento = tiene("lento");
  const respaldo = tiene("respaldo");
  const escala = lento ? 5.5 : respaldo ? 2.6 : 1;
  const pasos: Paso[] = [
    ...(desfase ? [] : [progreso(40, "entendiendo")]),
    progreso(desfase + 1200 * escala, "buscando_indicador"),
    progreso(desfase + 2200 * escala, "conectando_powerbi"),
    progreso(desfase + 3000 * escala, "consultando_powerbi"),
    progreso(desfase + 4600 * escala, "redactando"),
    progreso(desfase + 5400 * escala, "finalizando"),
  ];
  const esperas: Paso[] = lento
    ? [espera(10000, 1), espera(25000, 2), ...rotaciones(3000 * escala, 4600 * escala, "consultando_powerbi")]
    : [];
  const fin = desfase + 5800 * escala;
  return armar([
    ...previos,
    ...[...pasos, ...esperas].sort((a, b) => a[0] - b[0]),
    [
      fin,
      "respuesta",
      respuestaBase(entrada, {
        texto_markdown: TABLA_EGRESOS,
        fuentes: [{ titulo: "Egresos hospitalarios", tablero: "Egresos hospitalarios", pagina: "Resumen mensual" }],
        enlaces_powerbi: [
          {
            titulo: "Egresos hospitalarios · Resumen mensual",
            url: "https://app.powerbi.com/groups/me/reports/demo/ReportSection1",
          },
        ],
        diagnostico: diagnosticoDe(entrada, "powerbi", pasos),
      }),
    ],
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

/**
 * Documentación de ejemplo del mock (solo con NEXT_PUBLIC_API_MOCK=1): dos tableros pequeños con la forma real de
 * `docs_tableros/<grupo>/md/*.md`. Vive en `globalThis` para sobrevivir a la recarga de módulos de `next dev`
 * (las aprobaciones del mock cambian el documento y su historial).
 */
import type {
  DocumentoPagina,
  EntradaDocumento,
  GrupoDocumentacion,
  ListaPaginas,
  SeccionDocumento,
} from "@/lib/api/tiposDocumentacion";

export interface DocMock {
  archivo: string;
  pagina: string;
  nombre_funcional: string;
  bloque: string;
  tablas: string[];
  version: number;
  actualizado: string;
  proposito: string;
  secciones: SeccionDocumento[];
  /** Del más antiguo al más reciente (como en el .md). */
  historial: EntradaDocumento[];
}

export interface GrupoMock {
  grupo: string;
  tablero: string;
  docs: DocMock[];
}

const inicial = (): GrupoMock[] => [
  {
    grupo: "tablero_tiempos_urgencias",
    tablero: "TABLERO TIEMPOS URGENCIAS",
    docs: [
      {
        archivo: "_general.md",
        pagina: "TABLERO TIEMPOS URGENCIAS",
        nombre_funcional: "Oportunidad de la atención en urgencias",
        bloque: "General",
        tablas: [],
        version: 1,
        actualizado: "2026-10-20",
        proposito:
          "Muestra los tiempos de la atención de urgencias: del triage a la consulta, a la hospitalización y al egreso.",
        secciones: [
          {
            titulo: "Navegación",
            entradas: [{ nombre: "Inicio", texto: "La página RESUMEN_D lleva a las páginas del día." }],
          },
        ],
        historial: [{ nombre: "2026-10-20 · v1", texto: "Documentación inicial." }],
      },
      {
        archivo: "consultas_dia.md",
        pagina: "CONSULTAS DIA",
        nombre_funcional: "Oportunidad en la atención de consultas del día (triage II y III)",
        bloque: "Día",
        tablas: ["CONSULTAS_DIA", "EN_ESPERA_CONSULTA"],
        version: 1,
        actualizado: "2026-10-20",
        proposito:
          "Muestra en tiempo real la oportunidad de la consulta médica de urgencias, separada en triage II y triage III, con semáforo.",
        secciones: [
          {
            titulo: "Indicadores",
            entradas: [
              {
                nombre: "Tiempo de espera para consulta",
                texto: "Minutos entre la admisión y el primer folio de historia clínica.",
              },
            ],
          },
          {
            titulo: "Reglas de negocio",
            entradas: [
              {
                nombre: "Semáforo triage II",
                texto: "Verde de 0 a 15 minutos, amarillo de 16 a 30 y rojo de 31 o más.",
              },
              {
                nombre: "Semáforo triage III",
                texto: "Verde de 0 a 60 minutos, amarillo de 61 a 90 y rojo de 91 o más.",
              },
            ],
          },
          {
            titulo: "Observaciones",
            entradas: [
              {
                nombre: "Huecos en el semáforo",
                texto:
                  "En las tablas de atendidos de triage II los valores exactos de 16 y 31 minutos quedan sin color.",
              },
            ],
          },
        ],
        historial: [{ nombre: "2026-10-20 · v1", texto: "Documentación inicial generada a partir del PBIP." }],
      },
      {
        archivo: "resumen.md",
        pagina: "RESUMEN",
        nombre_funcional: "Datos históricos: resumen",
        bloque: "Histórico",
        tablas: ["OPORTUNIDAD_TRIAGE"],
        version: 1,
        actualizado: "2026-10-20",
        proposito: "Resume los tiempos históricos de urgencias por mes.",
        secciones: [],
        historial: [{ nombre: "2026-10-20 · v1", texto: "Documentación inicial." }],
      },
    ],
  },
  {
    grupo: "tablero_lavanderia",
    tablero: "TABLERO LAVANDERÍA",
    docs: [
      {
        archivo: "inicio.md",
        pagina: "INICIO",
        nombre_funcional: "Kilos de ropa procesados por turno",
        bloque: "Histórico",
        tablas: ["LAVANDERIA"],
        version: 3,
        actualizado: "2026-11-02",
        proposito: "Kilos de ropa lavada por **turno** y por servicio.",
        secciones: [
          {
            titulo: "Indicadores",
            entradas: [{ nombre: "Turno ok", texto: "Turnos con más de 300 kg procesados." }],
          },
        ],
        historial: [
          { nombre: "2026-10-01 · v1", texto: "Documentación inicial." },
          { nombre: "2026-10-15 · v2", texto: "Se corrigió el nombre del indicador." },
          { nombre: "2026-11-02 · v3", texto: "Se agregó la meta de kilos. Autor: Ana." },
        ],
      },
    ],
  },
];

const global = globalThis as typeof globalThis & { __documentacionMock?: GrupoMock[] };

export function gruposMock(): GrupoMock[] {
  global.__documentacionMock ??= inicial();
  return global.__documentacionMock;
}

export const grupoMock = (grupo: string) => gruposMock().find((g) => g.grupo === grupo);

export const docMock = (grupo: string, pagina: string) =>
  grupoMock(grupo)?.docs.find((d) => d.pagina === pagina || d.archivo === pagina);

export function listaGrupos(): GrupoDocumentacion[] {
  return gruposMock().map((g) => ({ grupo: g.grupo, tablero: g.tablero, paginas: g.docs.length }));
}

export function etiqueta(d: DocMock): string {
  const nombre = d.archivo === "_general.md" ? "General del tablero" : d.pagina;
  const base = d.nombre_funcional ? `${nombre} — ${d.nombre_funcional}` : nombre;
  return d.bloque && d.bloque !== "General" ? `${base} · ${d.bloque}` : base;
}

export function listaPaginas(g: GrupoMock): ListaPaginas {
  return {
    grupo: g.grupo,
    tablero: g.tablero,
    paginas: g.docs.map((d) => ({
      archivo: d.archivo,
      pagina: d.pagina,
      nombre_funcional: d.nombre_funcional,
      bloque: d.bloque,
      valido: true,
      general: d.archivo === "_general.md",
      etiqueta: etiqueta(d),
    })),
  };
}

export function aMarkdown(g: GrupoMock, d: DocMock): string {
  const entradas = (lista: EntradaDocumento[]) => lista.map((e) => `- **${e.nombre}**: ${e.texto}`);
  return [
    "---",
    `tablero: ${g.tablero}`,
    `pagina: ${d.pagina}`,
    `nombre_funcional: ${d.nombre_funcional}`,
    `bloque: ${d.bloque}`,
    `tablas: [${d.tablas.join(", ")}]`,
    `actualizado: ${d.actualizado}`,
    `version: ${d.version}`,
    "---",
    "",
    `# ${d.pagina}`,
    "",
    "## Propósito",
    d.proposito,
    ...d.secciones.flatMap((s) => ["", `## ${s.titulo}`, ...entradas(s.entradas)]),
    "",
    "## Historial de cambios",
    ...entradas(d.historial),
    "",
  ].join("\n");
}

export function documentoMock(g: GrupoMock, d: DocMock): DocumentoPagina {
  const valor = (v: string) => v || "—";
  return {
    grupo: g.grupo,
    tablero: g.tablero,
    archivo: d.archivo,
    ruta: `${g.grupo}/md/${d.archivo}`,
    pagina: d.pagina,
    interpretable: true,
    valido: true,
    errores_formato: [],
    ficha: [
      { dato: "Tablero", valor: g.tablero },
      { dato: "Página", valor: d.pagina },
      { dato: "Nombre funcional", valor: valor(d.nombre_funcional) },
      { dato: "Bloque", valor: valor(d.bloque) },
      { dato: "Tablas", valor: valor(d.tablas.join(", ")) },
      { dato: "Versión", valor: String(d.version) },
      { dato: "Última actualización", valor: d.actualizado },
    ],
    cuerpo: { proposito: d.proposito, secciones: d.secciones },
    historial: [...d.historial].reverse(),
    texto: aMarkdown(g, d),
  };
}

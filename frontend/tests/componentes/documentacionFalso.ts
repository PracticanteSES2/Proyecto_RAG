import { createElement } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { Documentacion } from "@/components/documentacion/Documentacion";
import type { ClienteDocumentacion } from "@/lib/api/documentacion";
import type { DocumentoPagina, Propuesta } from "@/lib/api/tiposDocumentacion";

export const GRUPO = "tablero_tiempos_urgencias";

export const documento = (extra: Partial<DocumentoPagina> = {}): DocumentoPagina => ({
  grupo: GRUPO,
  tablero: "TABLERO TIEMPOS URGENCIAS",
  archivo: "consultas_dia.md",
  ruta: `${GRUPO}/md/consultas_dia.md`,
  pagina: "CONSULTAS DIA",
  interpretable: true,
  valido: true,
  errores_formato: [],
  ficha: [
    { dato: "Página", valor: "CONSULTAS DIA" },
    { dato: "Versión", valor: "1" },
  ],
  cuerpo: {
    proposito: "Muestra la oportunidad de la consulta.",
    secciones: [
      {
        titulo: "Reglas de negocio",
        entradas: [{ nombre: "Semáforo triage II", texto: "Verde de 0 a 15 minutos." }],
      },
    ],
  },
  historial: [{ nombre: "2026-10-20 · v1", texto: "Documentación inicial." }],
  texto: "---\npagina: CONSULTAS DIA\n---\n# CONSULTAS DIA",
  ...extra,
});

export const propuesta = (extra: Partial<Propuesta> = {}): Propuesta => ({
  propuesta_id: "p1",
  grupo: GRUPO,
  tablero: "TABLERO TIEMPOS URGENCIAS",
  estado: "lista",
  nota: "subí el verde a 20",
  pagina: "CONSULTAS DIA",
  nombre_funcional: "Oportunidad de consultas",
  autor: "",
  cambios_pbip: [],
  progreso: null,
  como_se_eligio: "la nota la nombra o usa palabras que solo están en esa página",
  resumen: "Se amplió el verde.",
  dudas: [],
  avisos: ["«Huecos en el semáforo» también menciona el 16."],
  errores: [],
  operaciones: [
    {
      indice: 0,
      accion: "modificar",
      seccion: "Reglas de negocio",
      entrada: "Semáforo triage II",
      descripcion: "Cambiar la entrada **«Semáforo triage II»** de **Reglas de negocio**",
      texto: "Verde de 0 a 20 minutos.",
      texto_actual: "Verde de 0 a 15 minutos.",
      editable: true,
    },
  ],
  diff: {
    agregadas: 1,
    eliminadas: 1,
    unificado: "--- antes\n+++ despues",
    bloques: [
      {
        lineas: [
          { tipo: "igual", texto: "## Reglas de negocio" },
          { tipo: "sale", texto: "- **Semáforo triage II**: Verde de 0 a 15 minutos." },
          { tipo: "entra", texto: "- **Semáforo triage II**: Verde de 0 a 20 minutos." },
        ],
      },
    ],
  },
  vista_previa: null,
  formato_valido: true,
  errores_formato: [],
  candidatas: [],
  tiempos: "preparada en 4.5 s · 1 llamada a MedGemma (3.2 s)",
  detalle_tecnico: null,
  puede_aprobar: true,
  aprobacion: null,
  creada: "2026-11-11T09:00:00",
  actualizada: "2026-11-11T09:00:05",
  ...extra,
});

/** Cliente de documentación falso: un tablero con dos páginas; las propuestas se configuran por prueba. */
export function clienteDocFalso(sobrescribir: Partial<ClienteDocumentacion> = {}): ClienteDocumentacion {
  return {
    grupos: vi.fn(async () => ({
      grupos: [
        { grupo: GRUPO, tablero: "TABLERO TIEMPOS URGENCIAS", paginas: 2 },
        { grupo: "tablero_lavanderia", tablero: "TABLERO LAVANDERÍA", paginas: 1 },
      ],
    })),
    paginas: vi.fn(async (grupo: string) => ({
      grupo,
      tablero: grupo,
      paginas:
        grupo === GRUPO
          ? [
              {
                archivo: "consultas_dia.md",
                pagina: "CONSULTAS DIA",
                nombre_funcional: "Oportunidad de consultas",
                bloque: "Día",
                valido: true,
                general: false,
                etiqueta: "CONSULTAS DIA — Oportunidad de consultas · Día",
              },
              {
                archivo: "resumen.md",
                pagina: "RESUMEN",
                nombre_funcional: "Datos históricos",
                bloque: "Histórico",
                valido: true,
                general: false,
                etiqueta: "RESUMEN — Datos históricos · Histórico",
              },
            ]
          : [
              {
                archivo: "inicio.md",
                pagina: "INICIO",
                nombre_funcional: "Kilos por turno",
                bloque: "Histórico",
                valido: true,
                general: false,
                etiqueta: "INICIO — Kilos por turno · Histórico",
              },
            ],
    })),
    documento: vi.fn(async () => documento()),
    proponer: vi.fn(async () =>
      propuesta({ estado: "preparando", progreso: { etapa: "leyendo_nota", frase: "Leyendo tu nota", espera: null } }),
    ),
    propuesta: vi.fn(async () => propuesta()),
    corregir: vi.fn(async () => propuesta()),
    aclarar: vi.fn(async () => propuesta({ estado: "preparando" })),
    descartar: vi.fn(async () => propuesta({ estado: "descartada" })),
    aprobar: vi.fn(async () => propuesta()),
    reindexar: vi.fn(),
    reindexacion: vi.fn(),
    ...sobrescribir,
  };
}

export const ESPERA = { timeout: 4000 };

export async function abrirPagina(cliente: ClienteDocumentacion) {
  const usuario = userEvent.setup();
  render(createElement(Documentacion, { cliente }));
  const tableros = await screen.findByRole("complementary", { name: "Tableros" });
  await usuario.click(await within(tableros).findByRole("button", { name: /TABLERO TIEMPOS URGENCIAS/ }));
  await usuario.click(within(tableros).getByRole("button", { name: /CONSULTAS DIA/ }));
  await screen.findByRole("heading", { level: 2, name: "CONSULTAS DIA" });
  return usuario;
}

export async function proponer(cliente: ClienteDocumentacion, nota = "subí el verde del semáforo a 20") {
  const usuario = await abrirPagina(cliente);
  await usuario.click(screen.getByRole("button", { name: "Proponer un cambio en esta página" }));
  await usuario.type(screen.getByLabelText("¿Qué cambió?"), nota);
  await usuario.click(screen.getByRole("button", { name: "Generar propuesta" }));
  return usuario;
}

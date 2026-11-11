/**
 * Propuestas de cambio del mock (solo con NEXT_PUBLIC_API_MOCK=1). Imitan al backend: la propuesta pasa unos segundos
 * en `preparando` con las etapas y frases reales, y luego queda según la nota:
 * - «falla»               → error del modelo (con detalle técnico)
 * - «ambigua» sin página  → requiere aclaración (candidatas = páginas del tablero)
 * - «semáforo»            → cambia «Semáforo triage II» de CONSULTAS DIA
 * - «lento»               → tarda 14 s (para ver las frases de espera)
 * - cualquier otra        → agrega «Nota del equipo» en Observaciones
 * Al aprobar se guarda en el documento del mock y la reindexación tarda ~2,5 s («reindexación falla» la hace fallar).
 */
import type { EstadoPropuesta, Propuesta, SolicitudPropuesta } from "@/lib/api/tiposDocumentacion";
import { aMarkdown, docMock, etiqueta, grupoMock, type DocMock, type GrupoMock } from "./documentacion";
import { bloquesDiff, contarCambios, unificado } from "./diff";
import { aplicarOps, propuestaVacia, type OpMock } from "./operacionesMock";
import { estadoReindexacion, lanzarReindexacion } from "./reindexacionMock";

interface Resultado {
  estado: Exclude<EstadoPropuesta, "preparando" | "aprobada" | "descartada">;
  pagina: string;
  ops: OpMock[];
  resumen: string;
  como: string;
  dudas: string[];
  errores: string[];
  avisos: string[];
  detalle: string | null;
  /** Copia del documento al proponer (el diff no cambia aunque luego se apruebe). */
  docAntes: DocMock | null;
}

export interface RegistroMock {
  id: string;
  grupo: string;
  nota: string;
  pagina: string | null;
  cambios: string[];
  autor: string;
  inicio: number;
  creada: string;
  resultado?: Resultado;
  final?: "descartada" | "aprobada";
  aprobacion?: { autor: string; version: number; fecha: string };
}

const global = globalThis as typeof globalThis & { __propuestasMock?: Map<string, RegistroMock> };
const registros = () => (global.__propuestasMock ??= new Map());

const plano = (texto: string) =>
  texto
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
const duracionMs = (nota: string) => (plano(nota).includes("lento") ? 14_000 : 4_500);

function resolver(r: RegistroMock, g: GrupoMock): Resultado {
  const nota = plano(r.nota);
  const base = {
    pagina: r.pagina ?? "",
    ops: [],
    resumen: "",
    como: "",
    dudas: [],
    errores: [],
    avisos: [],
    detalle: null,
    docAntes: null,
  };
  if (nota.includes("falla") && !nota.includes("reindexacion")) {
    const errores = ["MedGemma devolvió una respuesta incompleta (simulado)."];
    return { ...base, estado: "error", errores, detalle: '{"operaciones": [' };
  }
  if (!r.pagina && nota.includes("ambigua")) {
    return { ...base, estado: "requiere_aclaracion", dudas: ["¿A qué página del tablero se refiere el cambio?"] };
  }
  const semaforo = nota.includes("semaforo");
  const doc = (r.pagina && docMock(g.grupo, r.pagina)) || (semaforo && docMock(g.grupo, "CONSULTAS DIA")) || g.docs[1];
  const pagina = doc?.pagina ?? g.docs[0]!.pagina;
  const tieneSemaforo = doc?.secciones.some((s) => s.entradas.some((e) => e.nombre === "Semáforo triage II"));
  const ops: OpMock[] =
    semaforo && tieneSemaforo
      ? [
          {
            accion: "modificar",
            seccion: "Reglas de negocio",
            entrada: "Semáforo triage II",
            texto: "Verde de 0 a 20 minutos, amarillo de 21 a 30 y rojo de 31 o más.",
          },
        ]
      : [{ accion: "agregar", seccion: "Observaciones", entrada: "Nota del equipo", texto: r.nota }];
  const resumen = semaforo ? "Se amplió el verde del semáforo de triage II a 20 minutos." : "Se agregó una nota.";
  const como = r.pagina
    ? "la elegiste tú en el formulario"
    : "la nota la nombra o usa palabras que solo están en esa página";
  const avisos = semaforo ? ["«Huecos en el semáforo» también menciona el 16; revisa si también cambia."] : [];
  const docAntes = doc ? structuredClone(doc) : null;
  return { ...base, estado: "lista", pagina, ops, resumen, como, avisos, docAntes };
}

export function crearPropuesta(s: SolicitudPropuesta): RegistroMock | null {
  if (!grupoMock(s.grupo)) return null;
  const r: RegistroMock = {
    id: crypto.randomUUID().replaceAll("-", ""),
    grupo: s.grupo,
    nota: s.nota.trim(),
    pagina: s.pagina || null,
    cambios: s.cambios_pbip ?? [],
    autor: s.autor ?? "",
    inicio: Date.now(),
    creada: new Date().toISOString(),
  };
  registros().set(r.id, r);
  return r;
}

export const registroMock = (id: string) => registros().get(id);

function progreso(r: RegistroMock, transcurrido: number) {
  if (transcurrido < 1_200) return { etapa: "leyendo_nota", frase: "Leyendo tu nota" };
  if (!r.pagina && transcurrido < 2_600)
    return { etapa: "eligiendo_pagina", frase: "Ubicando la página que corresponde" };
  if (transcurrido < duracionMs(r.nota) - 800)
    return { etapa: "redactando", frase: "Redactando el cambio en la documentación" };
  return { etapa: "revisando", frase: "Revisando el cambio propuesto" };
}

function resultadoDe(r: RegistroMock, g: GrupoMock): Resultado | null {
  if (!r.resultado && Date.now() - r.inicio >= duracionMs(r.nota)) r.resultado = resolver(r, g);
  return r.resultado ?? null;
}

function conResultado(p: Propuesta, r: RegistroMock, g: GrupoMock, res: Resultado): Propuesta {
  const doc = res.docAntes;
  const salida: Propuesta = { ...p, estado: r.final ?? res.estado, pagina: res.pagina, como_se_eligio: res.como };
  Object.assign(salida, { resumen: res.resumen, dudas: res.dudas, errores: res.errores, avisos: res.avisos });
  salida.detalle_tecnico = res.detalle;
  salida.tiempos = `preparada en ${(duracionMs(r.nota) / 1000).toFixed(1)} s · 1 llamada a MedGemma (3.2 s)`;
  if (res.estado === "requiere_aclaracion") {
    salida.candidatas = g.docs.map((d) => ({ pagina: d.pagina, etiqueta: etiqueta(d) }));
  }
  if (!doc || res.ops.length === 0) return salida;
  salida.nombre_funcional = doc.nombre_funcional;
  const despuesDoc = aplicarOps(doc, res.ops, res.resumen);
  const textoAntes = aMarkdown(g, doc);
  const textoDespues = aMarkdown(g, despuesDoc);
  const [agregadas, eliminadas] = contarCambios(textoAntes, textoDespues);
  salida.operaciones = res.ops.map((op, indice) => ({
    indice,
    accion: op.accion,
    seccion: op.seccion,
    entrada: op.entrada,
    descripcion: `${op.accion === "agregar" ? "Agregar" : "Cambiar"} la entrada **«${op.entrada}»** ${op.accion === "agregar" ? "en" : "de"} **${op.seccion}**`,
    texto: op.texto,
    texto_actual:
      doc.secciones.find((s) => s.titulo === op.seccion)?.entradas.find((e) => e.nombre === op.entrada)?.texto ?? null,
    editable: true,
  }));
  salida.diff = {
    agregadas,
    eliminadas,
    unificado: unificado(textoAntes, textoDespues),
    bloques: bloquesDiff(textoAntes, textoDespues),
  };
  salida.vista_previa = {
    cuerpo: { proposito: despuesDoc.proposito, secciones: despuesDoc.secciones },
    historial: [...despuesDoc.historial].reverse(),
  };
  salida.formato_valido = true;
  salida.puede_aprobar = salida.estado === "lista";
  return salida;
}

export function vistaPropuesta(r: RegistroMock): Propuesta | null {
  const g = grupoMock(r.grupo);
  if (!g) return null;
  const p = propuestaVacia(r, g.tablero);
  const res = r.final === "aprobada" ? r.resultado : resultadoDe(r, g);
  if (!res) {
    if (r.final === "descartada") return { ...p, estado: "descartada" };
    return { ...p, progreso: { ...progreso(r, Date.now() - r.inicio), espera: espera(Date.now() - r.inicio) } };
  }
  const salida = conResultado(p, r, g, res);
  if (r.aprobacion) {
    salida.aprobacion = { ...r.aprobacion, reindexacion: estadoReindexacion(g) };
    salida.puede_aprobar = false;
  }
  return salida;
}

const espera = (ms: number) => (ms >= 10_000 ? "Sigo trabajando en tu nota…" : null);

/** «Actualizar vista previa»: cambia el texto de las operaciones. */
export function corregirMock(r: RegistroMock, textos: { indice: number; texto: string }[]): string | null {
  const ops = r.resultado?.ops;
  if (!ops || r.final || r.resultado?.estado !== "lista")
    return "Solo se pueden corregir propuestas listas para aprobar.";
  for (const { indice, texto } of textos) {
    const op = ops[indice];
    if (!op || !texto.trim()) return "No se pudo aplicar tu corrección: el texto no puede quedar vacío.";
    op.texto = texto.trim();
  }
  return null;
}

export function aclararMock(r: RegistroMock, nota: string, pagina: string | null) {
  Object.assign(r, { nota: nota.trim(), pagina, inicio: Date.now(), resultado: undefined, final: undefined });
}

export function aprobarMock(r: RegistroMock, autor: string): string | null {
  const g = grupoMock(r.grupo);
  const res = r.resultado;
  if (!g || !res || r.final || res.estado !== "lista") return "Esta propuesta no se puede aprobar.";
  const doc = docMock(g.grupo, res.pagina);
  if (!doc) return "La página ya no existe.";
  const nuevo = aplicarOps(doc, res.ops, res.resumen, autor);
  g.docs[g.docs.indexOf(doc)] = nuevo;
  r.final = "aprobada";
  r.aprobacion = { autor, version: nuevo.version, fecha: new Date().toISOString() };
  lanzarReindexacion(g, plano(r.nota).includes("reindexacion falla"));
  return null;
}

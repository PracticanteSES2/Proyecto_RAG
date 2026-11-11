/** Piezas del mock de propuestas: operaciones sobre un documento y la propuesta «vacía» (en preparación). */
import type { Propuesta } from "@/lib/api/tiposDocumentacion";
import type { DocMock } from "./documentacion";
import type { RegistroMock } from "./propuestas";

export interface OpMock {
  accion: "agregar" | "modificar";
  seccion: string;
  entrada: string;
  texto: string;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function aplicarOps(d: DocMock, ops: OpMock[], resumen: string, autor = ""): DocMock {
  const nuevo: DocMock = structuredClone(d);
  for (const op of ops) {
    let seccion = nuevo.secciones.find((s) => s.titulo === op.seccion);
    if (!seccion) {
      seccion = { titulo: op.seccion, entradas: [] };
      nuevo.secciones.push(seccion);
    }
    const existente = seccion.entradas.find((e) => e.nombre === op.entrada);
    if (existente) existente.texto = op.texto;
    else seccion.entradas.push({ nombre: op.entrada, texto: op.texto });
  }
  nuevo.version += 1;
  nuevo.actualizado = hoy();
  nuevo.historial.push({ nombre: `${hoy()} · v${nuevo.version}`, texto: resumen + (autor ? ` Autor: ${autor}.` : "") });
  return nuevo;
}

export function propuestaVacia(r: RegistroMock, tablero: string): Propuesta {
  return {
    propuesta_id: r.id,
    grupo: r.grupo,
    tablero,
    estado: "preparando",
    nota: r.nota,
    pagina: r.pagina ?? "",
    nombre_funcional: "",
    autor: r.autor,
    cambios_pbip: r.cambios,
    progreso: null,
    como_se_eligio: "",
    resumen: "",
    dudas: [],
    avisos: [],
    errores: [],
    operaciones: [],
    diff: null,
    vista_previa: null,
    formato_valido: false,
    errores_formato: [],
    candidatas: [],
    tiempos: "",
    detalle_tecnico: null,
    puede_aprobar: false,
    aprobacion: null,
    creada: r.creada,
    actualizada: new Date().toISOString(),
  };
}

/**
 * Tipos del contrato de la documentación viva (`/api/v1/documentacion/**`).
 * Fuente: specs/013-documentacion-web/contracts/api-documentacion.md y los esquemas pydantic de
 * backend/app/schemas/documentacion.py. Como `tipos.ts`, pensado para reemplazarse por tipos generados del OpenAPI.
 */

export interface GrupoDocumentacion {
  grupo: string;
  tablero: string;
  paginas: number;
}

export interface ListaGrupos {
  grupos: GrupoDocumentacion[];
}

export interface PaginaResumen {
  archivo: string;
  pagina: string;
  nombre_funcional: string;
  bloque: string;
  valido: boolean;
  general: boolean;
  etiqueta: string;
}

export interface ListaPaginas {
  grupo: string;
  tablero: string;
  paginas: PaginaResumen[];
}

export interface FilaFicha {
  dato: string;
  valor: string;
}

export interface EntradaDocumento {
  nombre: string;
  texto: string;
}

export interface SeccionDocumento {
  titulo: string;
  entradas: EntradaDocumento[];
}

export interface CuerpoDocumento {
  proposito: string;
  secciones: SeccionDocumento[];
}

export interface DocumentoPagina {
  grupo: string;
  tablero: string;
  archivo: string;
  ruta: string;
  pagina: string;
  interpretable: boolean;
  valido: boolean;
  errores_formato: string[];
  ficha: FilaFicha[];
  cuerpo: CuerpoDocumento;
  historial: EntradaDocumento[];
  texto: string;
}

export type EstadoPropuesta = "preparando" | "lista" | "requiere_aclaracion" | "error" | "aprobada" | "descartada";
export type EstadoReindexacion = "sin_iniciar" | "en_curso" | "lista" | "error" | "no_disponible";

export interface SolicitudPropuesta {
  nota: string;
  grupo: string;
  pagina: string | null;
  cambios_pbip: string[];
  autor: string;
}

export interface ProgresoPropuesta {
  etapa: string;
  frase: string;
  espera: string | null;
}

export interface OperacionPropuesta {
  indice: number;
  accion: string;
  seccion: string;
  entrada: string;
  descripcion: string;
  texto: string;
  texto_actual: string | null;
  editable: boolean;
}

export interface LineaDiff {
  tipo: "igual" | "sale" | "entra";
  texto: string;
}

export interface DiffPropuesta {
  agregadas: number;
  eliminadas: number;
  unificado: string;
  bloques: { lineas: LineaDiff[] }[];
}

export interface Reindexacion {
  grupo: string;
  estado: EstadoReindexacion;
  mensaje: string;
  documentos: number | null;
  chunks: number | null;
  segundos: number | null;
  conexion_compartida: boolean;
  avisos: string[];
  iniciada: string | null;
  terminada: string | null;
}

export interface Aprobacion {
  autor: string;
  version: number | null;
  fecha: string;
  reindexacion: Reindexacion;
}

export interface Propuesta {
  propuesta_id: string;
  grupo: string;
  tablero: string;
  estado: EstadoPropuesta;
  nota: string;
  pagina: string;
  nombre_funcional: string;
  autor: string;
  cambios_pbip: string[];
  progreso: ProgresoPropuesta | null;
  como_se_eligio: string;
  resumen: string;
  dudas: string[];
  avisos: string[];
  errores: string[];
  operaciones: OperacionPropuesta[];
  diff: DiffPropuesta | null;
  vista_previa: { cuerpo: CuerpoDocumento; historial: EntradaDocumento[] } | null;
  formato_valido: boolean;
  errores_formato: string[];
  candidatas: { pagina: string; etiqueta: string }[];
  tiempos: string;
  detalle_tecnico: string | null;
  puede_aprobar: boolean;
  aprobacion: Aprobacion | null;
  creada: string;
  actualizada: string;
}

export interface SolicitudAclaracion {
  nota: string;
  pagina: string | null;
}

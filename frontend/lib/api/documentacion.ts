/**
 * Cliente tipado de la documentación viva (`/api/v1/documentacion/**`). Comparte el transporte (URL base, errores
 * clasificados con el `{mensaje, codigo}` del backend) con el cliente del chat.
 */
import { ErrorApi, crearTransporte, type Fetch } from "./cliente";
import { urlBaseApi } from "./config";
import type {
  DocumentoPagina,
  ListaGrupos,
  ListaPaginas,
  Propuesta,
  Reindexacion,
  SolicitudAclaracion,
  SolicitudPropuesta,
} from "./tiposDocumentacion";

export interface ClienteDocumentacion {
  grupos(): Promise<ListaGrupos>;
  paginas(grupo: string): Promise<ListaPaginas>;
  documento(grupo: string, archivo: string): Promise<DocumentoPagina>;
  proponer(solicitud: SolicitudPropuesta): Promise<Propuesta>;
  propuesta(id: string): Promise<Propuesta>;
  corregir(id: string, textos: { indice: number; texto: string }[]): Promise<Propuesta>;
  aclarar(id: string, solicitud: SolicitudAclaracion): Promise<Propuesta>;
  descartar(id: string): Promise<Propuesta>;
  aprobar(id: string, autor: string): Promise<Propuesta>;
  reindexar(grupo: string): Promise<Reindexacion>;
  reindexacion(grupo: string): Promise<Reindexacion>;
}

export function crearClienteDocumentacion(
  base: string = urlBaseApi(),
  fetchFn: Fetch = (...a) => fetch(...a),
): ClienteDocumentacion {
  const { json, post } = crearTransporte(base, fetchFn);
  const id = encodeURIComponent;
  const raiz = "/documentacion";
  return {
    grupos: () => json<ListaGrupos>(`${raiz}/grupos`),
    paginas: (grupo) => json<ListaPaginas>(`${raiz}/grupos/${id(grupo)}/paginas`),
    documento: (grupo, archivo) => json<DocumentoPagina>(`${raiz}/grupos/${id(grupo)}/paginas/${id(archivo)}`),
    proponer: (solicitud) => json<Propuesta>(`${raiz}/propuestas`, post(solicitud)),
    propuesta: (pid) => json<Propuesta>(`${raiz}/propuestas/${id(pid)}`),
    corregir: (pid, textos) => json<Propuesta>(`${raiz}/propuestas/${id(pid)}/operaciones`, post({ textos })),
    aclarar: (pid, solicitud) => json<Propuesta>(`${raiz}/propuestas/${id(pid)}/aclaracion`, post(solicitud)),
    descartar: (pid) => json<Propuesta>(`${raiz}/propuestas/${id(pid)}/descartar`, post()),
    aprobar: (pid, autor) => json<Propuesta>(`${raiz}/propuestas/${id(pid)}/aprobar`, post({ autor })),
    reindexar: (grupo) => json<Reindexacion>(`${raiz}/grupos/${id(grupo)}/reindexar`, post()),
    reindexacion: (grupo) => json<Reindexacion>(`${raiz}/grupos/${id(grupo)}/reindexacion`),
  };
}

/** Mensaje amable para la persona: el del backend si vino; si no, uno genérico según el tipo de fallo. */
export function mensajeDeError(error: unknown, que: string): string {
  if (error instanceof ErrorApi) {
    if (error.mensajeServidor) return error.mensajeServidor;
    if (error.tipo === "red") return `${que}: no logré comunicarme con el asistente. Revisa tu conexión.`;
    if (error.tipo === "no_encontrado") return `${que}: ya no está disponible.`;
  }
  return `${que}. Intenta de nuevo en un momento.`;
}

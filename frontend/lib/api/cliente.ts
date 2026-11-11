/**
 * Cliente tipado de la API v1. Es el único punto del frontend que habla HTTP con el backend.
 */
import { PREFIJO_API, urlBaseApi } from "./config";
import { abrirEventosTurno, type OpcionesEventos, type SuscripcionEventos } from "./sse";
import type {
  Capacidades,
  ConversacionCreada,
  ConversacionGuardada,
  Salud,
  SolicitudCalificacion,
  SolicitudTurno,
  TurnoCreado,
} from "./tipos";

export type TipoErrorApi = "saturado" | "no_encontrado" | "red" | "http";

/** Error de la API con una clasificación pensada para decidir el mensaje amable al usuario. */
export class ErrorApi extends Error {
  readonly tipo: TipoErrorApi;
  readonly estado?: number;
  /** Segundos sugeridos por `Retry-After` en un 429 (no se muestran al usuario). */
  readonly reintentarEn?: number;
  /** `codigo` estable del cuerpo de error del backend (`{mensaje, codigo}`), si vino. */
  readonly codigo?: string;
  /** `mensaje` amable del backend (en español, sin detalles internos), si vino. */
  readonly mensajeServidor?: string;

  constructor(
    tipo: TipoErrorApi,
    mensaje: string,
    estado?: number,
    reintentarEn?: number,
    cuerpo: { codigo?: string; mensajeServidor?: string } = {},
  ) {
    super(mensaje);
    this.name = "ErrorApi";
    this.tipo = tipo;
    this.estado = estado;
    this.reintentarEn = reintentarEn;
    this.codigo = cuerpo.codigo;
    this.mensajeServidor = cuerpo.mensajeServidor;
  }
}

/** `{mensaje, codigo}` del cuerpo de un error del backend (vacío si no es JSON con esa forma). */
async function cuerpoError(respuesta: Response): Promise<{ codigo?: string; mensajeServidor?: string }> {
  const datos = (await respuesta.json().catch(() => null)) as { mensaje?: unknown; codigo?: unknown } | null;
  return {
    codigo: typeof datos?.codigo === "string" ? datos.codigo : undefined,
    mensajeServidor: typeof datos?.mensaje === "string" ? datos.mensaje : undefined,
  };
}

export interface ClienteApi {
  crearConversacion(): Promise<ConversacionCreada>;
  enviarTurno(conversacionId: string, solicitud: SolicitudTurno): Promise<TurnoCreado>;
  eventosTurno(turnoId: string, opciones: OpcionesEventos): SuscripcionEventos;
  obtenerConversacion(conversacionId: string): Promise<ConversacionGuardada>;
  exportarConversacion(conversacionId: string): Promise<string>;
  calificarTurno(turnoId: string, calificacion: SolicitudCalificacion): Promise<void>;
  capacidades(): Promise<Capacidades>;
  salud(): Promise<Salud>;
}

export type Fetch = typeof fetch;

/** Transporte HTTP común de los clientes de la API: URL, errores clasificados y JSON. */
export function crearTransporte(base: string, fetchFn: Fetch) {
  const url = (ruta: string) => `${base}${PREFIJO_API}${ruta}`;

  async function pedir(ruta: string, init?: RequestInit): Promise<Response> {
    let respuesta: Response;
    try {
      respuesta = await fetchFn(url(ruta), {
        ...init,
        headers: {
          Accept: "application/json",
          ...(init?.body ? { "Content-Type": "application/json" } : {}),
          ...init?.headers,
        },
      });
    } catch (causa) {
      throw new ErrorApi("red", causa instanceof Error ? causa.message : "Fallo de red");
    }
    if (respuesta.ok) return respuesta;
    const cuerpo = await cuerpoError(respuesta);
    if (respuesta.status === 429) {
      const cabecera = Number(respuesta.headers.get("Retry-After"));
      throw new ErrorApi(
        "saturado",
        "Demasiadas consultas",
        429,
        Number.isFinite(cabecera) && cabecera > 0 ? cabecera : undefined,
        cuerpo,
      );
    }
    if (respuesta.status === 404) throw new ErrorApi("no_encontrado", "No encontrado", 404, undefined, cuerpo);
    throw new ErrorApi("http", `HTTP ${respuesta.status}`, respuesta.status, undefined, cuerpo);
  }

  const json = async <T>(ruta: string, init?: RequestInit): Promise<T> =>
    (await pedir(ruta, init)).json() as Promise<T>;
  const post = (cuerpo?: unknown): RequestInit => ({
    method: "POST",
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });
  return { url, pedir, json, post };
}

export function crearClienteApi(base: string = urlBaseApi(), fetchFn: Fetch = (...a) => fetch(...a)): ClienteApi {
  const { url, pedir, json, post } = crearTransporte(base, fetchFn);
  const id = encodeURIComponent;

  return {
    crearConversacion: () => json<ConversacionCreada>("/conversaciones", post()),
    enviarTurno: (conversacionId, solicitud) =>
      json<TurnoCreado>(`/conversaciones/${id(conversacionId)}/turnos`, post(solicitud)),
    eventosTurno: (turnoId, opciones) => abrirEventosTurno(url(`/turnos/${id(turnoId)}/eventos`), opciones),
    obtenerConversacion: (conversacionId) => json<ConversacionGuardada>(`/conversaciones/${id(conversacionId)}`),
    exportarConversacion: async (conversacionId) =>
      (
        await pedir(`/conversaciones/${id(conversacionId)}/exportar?formato=md`, {
          headers: { Accept: "text/markdown" },
        })
      ).text(),
    calificarTurno: async (turnoId, calificacion) => {
      await pedir(`/turnos/${id(turnoId)}/calificacion`, post(calificacion));
    },
    capacidades: () => json<Capacidades>("/capacidades"),
    salud: () => json<Salud>("/salud"),
  };
}

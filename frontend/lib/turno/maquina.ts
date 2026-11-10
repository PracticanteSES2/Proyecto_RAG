/**
 * Máquina de estados de un turno (pura, sin DOM ni red).
 *
 * Recibe las acciones del cliente (turno creado, tic del reloj, detener…) y los eventos SSE del contrato
 * (`cola`, `progreso`, `espera`, `respuesta`, `aviso`, `error`, `fin`) y produce lo que la interfaz necesita:
 * la frase principal, el renglón secundario de espera, la respuesta y los avisos.
 *
 * Reglas (specs/003-progreso-chat/contracts/eventos.md): `progreso` reemplaza la frase; `espera` reemplaza el
 * renglón secundario; nunca se muestran `t`, `nivel` ni `etapa` como texto.
 */
import type {
  Etapa,
  EventoAviso,
  EventoCola,
  EventoError,
  EventoRespuesta,
  EventoTurno,
} from "@/lib/api/tipos";

export type FaseTurno =
  | "enviando" // POST /turnos en vuelo
  | "en_curso" // escuchando eventos
  | "listo" // llegó la respuesta
  | "error" // evento `error`
  | "saturado" // 429 al crear el turno
  | "fallo_envio" // no se pudo crear el turno (red / servidor)
  | "desconectado" // el flujo de eventos se cortó sin respuesta
  | "detenido"; // el usuario detuvo la consulta

export interface EtapaRegistrada {
  etapa: Etapa;
  frase: string;
  t: number;
}

export interface EstadoTurno {
  fase: FaseTurno;
  turnoId?: string;
  /** Frase principal del indicador. */
  frase: string;
  /** Renglón secundario (eventos `espera` o respaldo del cliente). */
  fraseEspera?: string;
  esperaDelServidor: boolean;
  /** Segundos transcurridos según el reloj del cliente (solo modo diagnóstico). */
  segundos: number;
  etapas: EtapaRegistrada[];
  cola?: EventoCola;
  respuesta?: EventoRespuesta;
  avisos: EventoAviso[];
  error?: EventoError;
}

export type AccionTurno =
  | { tipo: "creado"; turnoId: string }
  | { tipo: "evento"; evento: EventoTurno }
  | { tipo: "tic"; segundos: number }
  | { tipo: "saturado" }
  | { tipo: "fallo_envio" }
  | { tipo: "desconectado" }
  | { tipo: "detenido" };

export const FRASE_INICIAL = "Entendiendo tu pregunta…";

export const FRASES_ETAPA: Record<Etapa, string> = {
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

/** Respaldo del cliente si el servidor no envía `espera` (mismos umbrales y tono que el backend). */
const ESCALONES_ESPERA: readonly [number, string][] = [
  [90, "Está tardando más de lo habitual; sigo esperando la respuesta."],
  [50, "Sigue en marcha: no hace falta volver a enviar la pregunta."],
  [25, "Sigo trabajando en tu respuesta; gracias por la paciencia."],
  [10, "Esto está tomando un poco más de lo normal…"],
];

export const AVISO_DEGRADADA =
  "Esta respuesta se armó directamente con la documentación, sin la redacción habitual del asistente.";

const NUMEROS = ["cero", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez"];

export function estadoInicialTurno(): EstadoTurno {
  return { fase: "enviando", frase: FRASE_INICIAL, esperaDelServidor: false, segundos: 0, etapas: [], avisos: [] };
}

export function turnoActivo(estado: EstadoTurno): boolean {
  return estado.fase === "enviando" || estado.fase === "en_curso";
}

export function conPuntosSuspensivos(frase: string): string {
  const limpia = frase.trim();
  return /[….!?;:]$/.test(limpia) ? limpia : `${limpia}…`;
}

export function fraseCola({ posicion, en_curso }: EventoCola): string {
  if (posicion <= 1) return "Tu pregunta es la siguiente; enseguida la atiendo…";
  const antes = posicion - 1 + Math.max(0, en_curso);
  if (antes === 1) return "Hay una consulta antes que la tuya, ya casi…";
  const cantidad = antes < NUMEROS.length ? NUMEROS[antes] : String(antes);
  return `Hay ${cantidad} consultas antes que la tuya, ya casi…`;
}

export function fraseEsperaCliente(segundos: number): string | undefined {
  return ESCALONES_ESPERA.find(([umbral]) => segundos >= umbral)?.[1];
}

function aplicarEvento(estado: EstadoTurno, evento: EventoTurno): EstadoTurno {
  // Tras la respuesta solo interesan los avisos; tras otros finales, nada.
  if (!turnoActivo(estado)) {
    if (estado.fase === "listo" && evento.tipo === "aviso") {
      return { ...estado, avisos: [...estado.avisos, evento.datos] };
    }
    return estado;
  }
  switch (evento.tipo) {
    case "cola":
      return { ...estado, fase: "en_curso", cola: evento.datos, frase: fraseCola(evento.datos) };
    case "progreso": {
      const { etapa, frase, t } = evento.datos;
      const texto = frase?.trim() ? frase : FRASES_ETAPA[etapa] ?? FRASE_INICIAL;
      return {
        ...estado,
        fase: "en_curso",
        cola: etapa === "en_cola" ? estado.cola : undefined,
        frase: conPuntosSuspensivos(texto),
        etapas: [...estado.etapas, { etapa, frase: texto, t }],
      };
    }
    case "espera":
      return { ...estado, fraseEspera: evento.datos.frase, esperaDelServidor: true };
    case "respuesta":
      return { ...estado, fase: "listo", respuesta: evento.datos };
    case "aviso":
      return { ...estado, avisos: [...estado.avisos, evento.datos] };
    case "error":
      return { ...estado, fase: "error", error: evento.datos };
    case "fin":
      return { ...estado, fase: "desconectado" };
  }
}

export function reducirTurno(estado: EstadoTurno, accion: AccionTurno): EstadoTurno {
  switch (accion.tipo) {
    case "evento":
      return aplicarEvento(estado, accion.evento);
    case "creado":
      return estado.fase === "enviando" ? { ...estado, fase: "en_curso", turnoId: accion.turnoId } : estado;
    case "tic": {
      if (!turnoActivo(estado)) return estado;
      const fraseEspera = estado.esperaDelServidor
        ? estado.fraseEspera
        : fraseEsperaCliente(accion.segundos) ?? estado.fraseEspera;
      return { ...estado, segundos: accion.segundos, fraseEspera };
    }
    case "saturado":
    case "fallo_envio":
    case "desconectado":
    case "detenido":
      return turnoActivo(estado) ? { ...estado, fase: accion.tipo } : estado;
  }
}

/** Notas amables bajo la respuesta (degradada y eventos `aviso`), sin repetir textos. */
export function avisosVisibles(estado: EstadoTurno): string[] {
  const textos: string[] = [];
  const r = estado.respuesta;
  if (r?.aviso?.trim()) textos.push(r.aviso.trim());
  for (const aviso of estado.avisos) {
    const texto = aviso.texto?.trim();
    if (texto && !textos.includes(texto)) textos.push(texto);
  }
  // Nota genérica solo si la respuesta vino degradada y nadie explicó por qué.
  if (r?.degradada && textos.length === 0) textos.push(AVISO_DEGRADADA);
  return textos;
}

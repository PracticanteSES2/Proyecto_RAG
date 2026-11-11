/**
 * Máquina de estados de un turno (pura, sin DOM ni red).
 *
 * Recibe las acciones del cliente (turno creado, tic del reloj, detener…) y los eventos SSE del contrato
 * (`cola`, `progreso`, `espera`, `token`, `respuesta`, `aviso`, `error`, `fin`) y produce lo que la interfaz
 * necesita: la frase principal, el renglón secundario de espera, el borrador en vivo, la respuesta y los avisos.
 *
 * Reglas (specs/003-progreso-chat/contracts/eventos.md): `progreso` reemplaza la frase; `espera` reemplaza el
 * renglón secundario; `token` se añade al borrador y `respuesta` lo reemplaza; nunca se muestran `t`, `nivel`
 * ni `etapa` como texto. Decisión del usuario (specs/009-experiencia-espera): `cola` es solo diagnóstico; la
 * espera nunca habla de filas, colas ni otras consultas.
 */
import type { Etapa, EventoAviso, EventoCola, EventoError, EventoRespuesta, EventoTurno } from "@/lib/api/tipos";

export type FaseTurno =
  | "enviando" // POST /turnos en vuelo
  | "en_curso" // escuchando eventos
  | "listo" // llegó la respuesta
  | "error" // evento `error`
  | "saturado" // 429 al crear el turno
  | "fallo_envio" // no se pudo crear el turno (red / servidor)
  | "desconectado" // el flujo de eventos se cortó sin respuesta
  | "detenido"; // el usuario detuvo la consulta

/** Fases finales sin respuesta: la interfaz muestra un aviso amable (components/chat/AvisoTurno.tsx). */
export type FaseProblema = Extract<FaseTurno, "error" | "saturado" | "fallo_envio" | "desconectado" | "detenido">;
const FASES_PROBLEMA: ReadonlySet<FaseTurno> = new Set([
  "error",
  "saturado",
  "fallo_envio",
  "desconectado",
  "detenido",
]);

export function esFaseProblema(fase: FaseTurno): fase is FaseProblema {
  return FASES_PROBLEMA.has(fase);
}

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
  /** Solo modo diagnóstico. */
  cola?: EventoCola;
  /** Texto que llegó por `token` (borrador en vivo de la redacción). */
  borrador?: string;
  respuesta?: EventoRespuesta;
  /** La respuesta llegó en vivo (no del historial): la interfaz la revela con escritura rápida. */
  revelar?: boolean;
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
  finalizando: "Ya casi está",
};

/** Respaldo del cliente si el servidor no envía `espera` (mismos umbrales y textos que src/chatbot/frases_progreso.py). */
const ESCALONES_ESPERA: readonly [number, string][] = [
  [90, "Me está tomando más de lo habitual, pero sigo en ello."],
  [50, "Sigo con tu pregunta; no hace falta volver a enviarla."],
  [25, "Estoy armando una respuesta completa; ya casi la tengo…"],
  [10, "Sigo trabajando en tu pregunta…"],
];

/** Nota neutra para la respuesta extractiva: nunca culpa a la carga ni a otras consultas. */
export const AVISO_DEGRADADA = "Te muestro lo que dice la documentación.";

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
      // Solo diagnóstico: la frase visible sigue siendo la de trabajo sobre la pregunta.
      return { ...estado, fase: "en_curso", cola: evento.datos };
    case "progreso": {
      const { etapa, frase, t } = evento.datos;
      const texto = frase?.trim() ? frase : (FRASES_ETAPA[etapa] ?? FRASE_INICIAL);
      return {
        ...estado,
        fase: "en_curso",
        frase: conPuntosSuspensivos(texto),
        etapas: [...estado.etapas, { etapa, frase: texto, t }],
      };
    }
    case "espera":
      return { ...estado, fraseEspera: evento.datos.frase, esperaDelServidor: true };
    case "token":
      return { ...estado, fase: "en_curso", borrador: (estado.borrador ?? "") + (evento.datos.texto ?? "") };
    case "respuesta":
      return { ...estado, fase: "listo", respuesta: evento.datos, revelar: true };
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
        : (fraseEsperaCliente(accion.segundos) ?? estado.fraseEspera);
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
  const r = estado.respuesta;
  const textos = new Set<string>();
  for (const texto of [r?.aviso, ...estado.avisos.map((a) => a.texto)]) {
    if (texto?.trim()) textos.add(texto.trim());
  }
  // Nota genérica solo si la respuesta vino degradada y nadie explicó por qué.
  if (r?.degradada && textos.size === 0) textos.add(AVISO_DEGRADADA);
  return [...textos];
}

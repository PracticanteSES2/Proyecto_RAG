import { describe, expect, it } from "vitest";
import {
  contrapreguntaActiva,
  estadoInicialChat,
  reducirChat,
  turnoEnCurso,
  type AccionChat,
  type EstadoChat,
  type MensajeAsistente,
} from "@/lib/chat/reductor";
import type { EventoRespuesta } from "@/lib/api/tipos";

const aplicar = (acciones: AccionChat[], inicial: EstadoChat = estadoInicialChat) => acciones.reduce(reducirChat, inicial);
const enviar = (n: number, texto = `pregunta ${n}`, opcionId?: string): AccionChat => ({
  tipo: "enviar",
  idUsuario: `u${n}`,
  idAsistente: `a${n}`,
  texto,
  opcionId,
  diagnostico: false,
});
const responder = (n: number, extra: Partial<EventoRespuesta> = {}): AccionChat => ({
  tipo: "turno",
  idAsistente: `a${n}`,
  accion: {
    tipo: "evento",
    evento: {
      tipo: "respuesta",
      datos: { turno_id: `t${n}`, texto_markdown: "ok", ruta: "powerbi", fuentes: [], enlaces_powerbi: [], degradada: false, ...extra },
    },
  },
});
const contrapregunta = {
  pregunta: "¿Qué ocupación?",
  opciones: [
    { id: "op-uci", texto: "UCI adultos" },
    { id: "op-hosp", texto: "Hospitalización general" },
  ],
};
const asistente = (e: EstadoChat, id: string) => e.mensajes.find((m) => m.id === id) as MensajeAsistente;

describe("reductor del chat", () => {
  it("enviar agrega el mensaje del usuario y el turno del asistente", () => {
    const e = aplicar([enviar(1, "  ¿Cuántos egresos?  ")]);
    expect(e.mensajes.map((m) => m.rol)).toEqual(["usuario", "asistente"]);
    expect(e.mensajes[0]).toMatchObject({ texto: "¿Cuántos egresos?" });
    expect(asistente(e, "a1").turno.fase).toBe("enviando");
    expect(turnoEnCurso(e)?.id).toBe("a1");
  });

  it("no envía mensajes vacíos", () => {
    expect(aplicar([enviar(1, "   ")]).mensajes).toHaveLength(0);
  });

  it("no envía otra pregunta mientras hay un turno en curso", () => {
    const e = aplicar([enviar(1), enviar(2)]);
    expect(e.mensajes).toHaveLength(2);
  });

  it("permite enviar cuando el turno anterior terminó", () => {
    const e = aplicar([enviar(1), responder(1), enviar(2)]);
    expect(e.mensajes).toHaveLength(4);
    expect(turnoEnCurso(e)?.id).toBe("a2");
  });

  it("delegar eventos del turno al mensaje del asistente correcto", () => {
    const e = aplicar([enviar(1), { tipo: "turno", idAsistente: "a1", accion: { tipo: "creado", turnoId: "t1" } }]);
    expect(asistente(e, "a1").turno).toMatchObject({ fase: "en_curso", turnoId: "t1" });
  });

  it("elegir una opción la marca en la contrapregunta y envía opcion_id", () => {
    const e = aplicar([enviar(1), responder(1, { contrapregunta }), enviar(2, "UCI adultos", "op-uci")]);
    expect(asistente(e, "a1").opcionElegida).toBe("op-uci");
    expect(asistente(e, "a2").solicitud).toEqual({ mensaje: "UCI adultos", opcionId: "op-uci" });
    expect(e.mensajes[2]).toMatchObject({ rol: "usuario", opcionId: "op-uci" });
  });

  it("la contrapregunta solo está activa si es el último mensaje y sin elección", () => {
    const conPregunta = aplicar([enviar(1), responder(1, { contrapregunta })]);
    expect(contrapreguntaActiva(conPregunta, "a1")).toBe(true);
    const elegida = reducirChat(conPregunta, enviar(2, "UCI adultos", "op-uci"));
    expect(contrapreguntaActiva(elegida, "a1")).toBe(false);
    const escrita = reducirChat(conPregunta, enviar(2, "otra cosa"));
    expect(contrapreguntaActiva(escrita, "a1")).toBe(false);
  });

  it("calificar guarda el estado de la calificación", () => {
    const e = aplicar([
      enviar(1),
      responder(1),
      { tipo: "calificar", idAsistente: "a1", calificacion: { valor: "mala", comentario: "faltó el año", estado: "guardada" } },
    ]);
    expect(asistente(e, "a1").calificacion).toEqual({ valor: "mala", comentario: "faltó el año", estado: "guardada" });
  });

  it("descartar quita el turno fallido y su pregunta (para reintentar)", () => {
    const e = aplicar([
      enviar(1),
      responder(1),
      enviar(2),
      { tipo: "turno", idAsistente: "a2", accion: { tipo: "saturado" } },
      { tipo: "descartar", idAsistente: "a2" },
    ]);
    expect(e.mensajes.map((m) => m.id)).toEqual(["u1", "a1"]);
  });

  it("reiniciar vacía la conversación y olvida su id", () => {
    const e = aplicar([{ tipo: "conversacion", conversacionId: "c1" }, enviar(1), { tipo: "reiniciar" }]);
    expect(e).toEqual(estadoInicialChat);
  });

  it("restaurar reconstruye pares de mensajes, avisos, calificación y opciones elegidas", () => {
    const e = aplicar([
      {
        tipo: "restaurar",
        conversacion: {
          conversacion_id: "c9",
          turnos: [
            {
              turno_id: "t1",
              mensaje: "¿Ocupación?",
              respuesta: { turno_id: "t1", texto_markdown: "¿Cuál?", ruta: "aclaracion", fuentes: [], enlaces_powerbi: [], degradada: false, contrapregunta },
            },
            {
              turno_id: "t2",
              mensaje: "UCI adultos",
              opcion_id: "op-uci",
              respuesta: { turno_id: "t2", texto_markdown: "87 %", ruta: "powerbi", fuentes: [], enlaces_powerbi: [], degradada: false },
              avisos: [{ motivo: "saturado", texto: "nota" }],
              calificacion: { valor: "buena" },
            },
          ],
        },
      },
    ]);
    expect(e.conversacionId).toBe("c9");
    expect(e.mensajes).toHaveLength(4);
    expect(asistente(e, "a-t1").opcionElegida).toBe("op-uci");
    expect(asistente(e, "a-t2").turno.fase).toBe("listo");
    expect(asistente(e, "a-t2").turno.avisos).toHaveLength(1);
    expect(asistente(e, "a-t2").calificacion).toEqual({ valor: "buena", comentario: undefined, estado: "guardada" });
  });
});

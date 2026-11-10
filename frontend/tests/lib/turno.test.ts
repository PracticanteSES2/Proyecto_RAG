import { describe, expect, it } from "vitest";
import {
  avisosVisibles,
  estadoInicialTurno,
  fraseCola,
  fraseEsperaCliente,
  reducirTurno,
  turnoActivo,
  type AccionTurno,
  type EstadoTurno,
} from "@/lib/turno/maquina";
import type { EventoRespuesta, EventoTurno } from "@/lib/api/tipos";

const ev = (evento: EventoTurno): AccionTurno => ({ tipo: "evento", evento });
const aplicar = (acciones: AccionTurno[], inicial: EstadoTurno = estadoInicialTurno()) =>
  acciones.reduce(reducirTurno, inicial);

const respuesta = (extra: Partial<EventoRespuesta> = {}): EventoRespuesta => ({
  turno_id: "t1",
  texto_markdown: "Hubo **1.234** egresos.",
  ruta: "powerbi",
  fuentes: [],
  enlaces_powerbi: [],
  degradada: false,
  ...extra,
});

describe("máquina de estados del turno", () => {
  it("empieza enviando, con la frase inicial y sin espera", () => {
    const e = estadoInicialTurno();
    expect(e.fase).toBe("enviando");
    expect(e.frase).toBe("Entendiendo tu pregunta…");
    expect(e.fraseEspera).toBeUndefined();
    expect(turnoActivo(e)).toBe(true);
  });

  it("pasa a en curso al crearse el turno", () => {
    const e = aplicar([{ tipo: "creado", turnoId: "t1" }]);
    expect(e.fase).toBe("en_curso");
    expect(e.turnoId).toBe("t1");
  });

  it("progreso reemplaza la frase, añade puntos suspensivos y registra la etapa", () => {
    const e = aplicar([
      { tipo: "creado", turnoId: "t1" },
      ev({
        tipo: "progreso",
        datos: { etapa: "consultando_powerbi", frase: "Consultando los datos en Power BI", t: 3.1 },
      }),
    ]);
    expect(e.frase).toBe("Consultando los datos en Power BI…");
    expect(e.etapas).toEqual([{ etapa: "consultando_powerbi", frase: "Consultando los datos en Power BI", t: 3.1 }]);
  });

  it("usa una frase humana por etapa si el servidor no trae frase", () => {
    const e = aplicar([ev({ tipo: "progreso", datos: { etapa: "redactando", frase: "", t: 1 } })]);
    expect(e.frase).toBe("Redactando la respuesta…");
  });

  it("no duplica puntuación final de la frase del servidor", () => {
    const e = aplicar([ev({ tipo: "progreso", datos: { etapa: "finalizando", frase: "Ya casi está…", t: 1 } })]);
    expect(e.frase).toBe("Ya casi está…");
  });

  it("cola: con posición > 1 dice cuántas consultas van antes", () => {
    const e = aplicar([ev({ tipo: "cola", datos: { posicion: 2, en_curso: 1 } })]);
    expect(e.frase).toBe("Hay dos consultas antes que la tuya, ya casi…");
    expect(e.cola).toEqual({ posicion: 2, en_curso: 1 });
  });

  it("cola: con posición 1 o desconocida no da números", () => {
    expect(fraseCola({ posicion: 1, en_curso: 1 })).toBe("Tu pregunta es la siguiente; enseguida la atiendo…");
    expect(fraseCola({ posicion: 0, en_curso: 0 })).toBe("Tu pregunta es la siguiente; enseguida la atiendo…");
    expect(fraseCola({ posicion: 2, en_curso: 0 })).toBe("Hay una consulta antes que la tuya, ya casi…");
    expect(fraseCola({ posicion: 14, en_curso: 1 })).toBe("Hay 14 consultas antes que la tuya, ya casi…");
  });

  it("un progreso posterior a la cola la retira", () => {
    const e = aplicar([
      ev({ tipo: "cola", datos: { posicion: 3, en_curso: 1 } }),
      ev({ tipo: "progreso", datos: { etapa: "entendiendo", frase: "Entendiendo tu pregunta", t: 4 } }),
    ]);
    expect(e.cola).toBeUndefined();
    expect(e.frase).toBe("Entendiendo tu pregunta…");
  });

  it("espera del servidor ocupa el renglón secundario y desactiva el respaldo del cliente", () => {
    const e = aplicar([
      ev({
        tipo: "espera",
        datos: { nivel: 2, frase: "Power BI está tardando en responder; sigo esperando los datos.", t: 25 },
      }),
      { tipo: "tic", segundos: 95 },
    ]);
    expect(e.fraseEspera).toBe("Power BI está tardando en responder; sigo esperando los datos.");
    expect(e.esperaDelServidor).toBe(true);
  });

  it("sin espera del servidor, el cliente escalona frases por tiempo", () => {
    expect(aplicar([{ tipo: "tic", segundos: 5 }]).fraseEspera).toBeUndefined();
    expect(aplicar([{ tipo: "tic", segundos: 12 }]).fraseEspera).toBe(fraseEsperaCliente(12));
    expect(fraseEsperaCliente(9)).toBeUndefined();
    expect(fraseEsperaCliente(10)).toBe("Esto está tomando un poco más de lo normal…");
    expect(fraseEsperaCliente(30)).toBe("Sigo trabajando en tu respuesta; gracias por la paciencia.");
    expect(fraseEsperaCliente(55)).toBe("Sigue en marcha: no hace falta volver a enviar la pregunta.");
    expect(fraseEsperaCliente(200)).toBe("Está tardando más de lo habitual; sigo esperando la respuesta.");
  });

  it("tic guarda los segundos transcurridos (solo para el modo diagnóstico)", () => {
    expect(aplicar([{ tipo: "tic", segundos: 7.5 }]).segundos).toBe(7.5);
  });

  it("respuesta termina el turno y conserva el contenido", () => {
    const e = aplicar([{ tipo: "creado", turnoId: "t1" }, ev({ tipo: "respuesta", datos: respuesta() })]);
    expect(e.fase).toBe("listo");
    expect(e.respuesta?.texto_markdown).toContain("1.234");
    expect(turnoActivo(e)).toBe(false);
  });

  it("ignora progreso y espera tardíos, pero acepta avisos tras la respuesta", () => {
    const e = aplicar([
      ev({ tipo: "respuesta", datos: respuesta() }),
      ev({ tipo: "progreso", datos: { etapa: "finalizando", frase: "Ya casi está", t: 9 } }),
      ev({ tipo: "espera", datos: { nivel: 1, frase: "x", t: 10 } }),
      ev({ tipo: "aviso", datos: { motivo: "saturado", texto: "Respuesta armada directamente con los documentos." } }),
      ev({ tipo: "fin", datos: {} }),
    ]);
    expect(e.fase).toBe("listo");
    expect(e.etapas).toHaveLength(0);
    expect(e.avisos).toEqual([{ motivo: "saturado", texto: "Respuesta armada directamente con los documentos." }]);
  });

  it("error deja el turno en error con los datos técnicos guardados", () => {
    const e = aplicar([ev({ tipo: "error", datos: { mensaje: "Timeout DAX", codigo: "powerbi_timeout" } })]);
    expect(e.fase).toBe("error");
    expect(e.error).toEqual({ mensaje: "Timeout DAX", codigo: "powerbi_timeout" });
  });

  it("fin sin respuesta ni error se trata como desconexión", () => {
    const e = aplicar([{ tipo: "creado", turnoId: "t1" }, ev({ tipo: "fin", datos: {} })]);
    expect(e.fase).toBe("desconectado");
  });

  it("desconexión, saturación, fallo de envío y detención son estados finales", () => {
    expect(aplicar([{ tipo: "desconectado" }]).fase).toBe("desconectado");
    expect(aplicar([{ tipo: "saturado" }]).fase).toBe("saturado");
    expect(aplicar([{ tipo: "fallo_envio" }]).fase).toBe("fallo_envio");
    const detenido = aplicar([{ tipo: "detenido" }, ev({ tipo: "respuesta", datos: respuesta() })]);
    expect(detenido.fase).toBe("detenido");
    expect(detenido.respuesta).toBeUndefined();
  });

  it("una desconexión después de la respuesta no la borra", () => {
    const e = aplicar([ev({ tipo: "respuesta", datos: respuesta() }), { tipo: "desconectado" }]);
    expect(e.fase).toBe("listo");
  });
});

describe("avisos visibles", () => {
  it("respuesta degradada sin texto usa un aviso amable genérico", () => {
    const e = aplicar([ev({ tipo: "respuesta", datos: respuesta({ degradada: true }) })]);
    expect(avisosVisibles(e)).toEqual([
      "Esta respuesta se armó directamente con la documentación, sin la redacción habitual del asistente.",
    ]);
  });

  it("usa el aviso de la respuesta y los eventos aviso sin repetir textos", () => {
    const e = aplicar([
      ev({ tipo: "respuesta", datos: respuesta({ degradada: true, aviso: "Hubo mucha demanda." }) }),
      ev({ tipo: "aviso", datos: { motivo: "saturado", texto: "Hubo mucha demanda." } }),
      ev({ tipo: "aviso", datos: { motivo: "sin_redaccion", texto: "Otra nota." } }),
    ]);
    expect(avisosVisibles(e)).toEqual(["Hubo mucha demanda.", "Otra nota."]);
  });

  it("sin degradación ni avisos no hay notas", () => {
    expect(avisosVisibles(aplicar([ev({ tipo: "respuesta", datos: respuesta() })]))).toEqual([]);
  });
});

describe("avisos visibles (prioridad)", () => {
  it("un evento aviso reemplaza la nota genérica de respuesta degradada", () => {
    const e = aplicar([
      ev({ tipo: "respuesta", datos: respuesta({ degradada: true }) }),
      ev({ tipo: "aviso", datos: { motivo: "sin_redaccion", texto: "Te muestro los fragmentos tal como están." } }),
    ]);
    expect(avisosVisibles(e)).toEqual(["Te muestro los fragmentos tal como están."]);
  });
});

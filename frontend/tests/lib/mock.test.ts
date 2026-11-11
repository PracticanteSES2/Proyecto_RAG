import { describe, expect, it } from "vitest";
import { debeSaturar, formatearSSE, guionPara, pasosDesde } from "@/lib/mock/guiones";
import { estadoInicialTurno, reducirTurno } from "@/lib/turno/maquina";

const entrada = (mensaje: string, extra: { opcionId?: string; diagnostico?: boolean } = {}) => ({
  turnoId: "t1",
  mensaje,
  diagnostico: false,
  ...extra,
});
const tipos = (mensaje: string, extra?: { opcionId?: string; diagnostico?: boolean }) =>
  guionPara(entrada(mensaje, extra)).map((p) => p.evento.tipo);

/** Ejecuta un guion completo contra la máquina de estados del turno. */
const ejecutar = (mensaje: string, extra?: { opcionId?: string; diagnostico?: boolean }) =>
  guionPara(entrada(mensaje, extra)).reduce(
    (estado, paso) => reducirTurno(estado, { tipo: "evento", evento: paso.evento }),
    reducirTurno(estadoInicialTurno(), { tipo: "creado", turnoId: "t1" }),
  );

const ESCENARIOS = [
  "hola",
  "egresos",
  "ocupación",
  "qué es un egreso",
  "salvaguarda",
  "documentación de egresos",
  "cola",
  "lento",
  "respaldo",
  "error",
];

/** Lo que la persona puede leer de un guion (frases de progreso y espera, avisos, borrador y respuesta). */
const textosVisibles = (mensaje: string) =>
  guionPara(entrada(mensaje)).flatMap(({ evento }) => {
    if (evento.tipo === "progreso" || evento.tipo === "espera") return [evento.datos.frase];
    if (evento.tipo === "aviso") return [evento.datos.texto];
    if (evento.tipo === "token") return [evento.datos.texto];
    return [];
  });

describe("guiones del mock", () => {
  it("los pasos van en orden cronológico y terminan en fin", () => {
    for (const m of ESCENARIOS) {
      const guion = guionPara(entrada(m));
      expect(guion.map((p) => p.ms)).toEqual([...guion.map((p) => p.ms)].sort((a, b) => a - b));
      expect(guion.at(-1)?.evento.tipo).toBe("fin");
    }
  });

  it("el saludo responde antes de 600 ms (el indicador nunca se ve)", () => {
    const respuesta = guionPara(entrada("Hola")).find((p) => p.evento.tipo === "respuesta");
    expect(respuesta!.ms).toBeLessThan(600);
  });

  it("la pregunta por defecto trae tabla, fuentes y enlace de Power BI", () => {
    const e = ejecutar("¿Cuántos egresos hubo en marzo de 2026?");
    expect(e.fase).toBe("listo");
    expect(e.respuesta?.texto_markdown).toContain("| Servicio |");
    expect(e.respuesta?.enlaces_powerbi).toHaveLength(1);
    expect(e.respuesta?.diagnostico).toBeUndefined();
  });

  it("con diagnóstico incluye DAX y tiempos", () => {
    const e = ejecutar("egresos", { diagnostico: true });
    expect(e.respuesta?.diagnostico?.dax).toContain("EVALUATE");
    expect(e.respuesta?.diagnostico?.tiempos?.length).toBeGreaterThan(3);
  });

  it("ocupación devuelve contrapregunta; con opción, la cifra", () => {
    expect(ejecutar("¿Cuál es la ocupación?").respuesta?.contrapregunta?.opciones).toHaveLength(3);
    const elegida = ejecutar("Ocupación de UCI adultos", { opcionId: "ocup-uci" });
    expect(elegida.respuesta?.contrapregunta).toBeUndefined();
    expect(elegida.respuesta?.texto_markdown).toContain("87,4 %");
  });

  it("documentación extractiva llega con la nota neutra (el motivo queda para diagnóstico)", () => {
    const e = ejecutar("Busca en la documentación qué es un egreso");
    expect(e.respuesta?.degradada).toBe(true);
    expect(e.avisos[0]).toEqual({ motivo: "saturado", texto: "Te muestro lo que dice la documentación." });
  });

  it("la pregunta documental aparece de a poco: tokens antes de la respuesta y borrador igual a la final", () => {
    const guion = guionPara(entrada("¿Qué es un egreso?"));
    const nombres = guion.map((p) => p.evento.tipo);
    expect(nombres.filter((t) => t === "token").length).toBeGreaterThan(10);
    expect(nombres.indexOf("token")).toBeLessThan(nombres.indexOf("respuesta"));
    const e = ejecutar("¿Qué es un egreso?");
    expect(e.borrador).toBe(e.respuesta?.texto_markdown);
    expect(e.revelar).toBe(true);
  });

  it("salvaguarda: el borrador trae una cifra que la respuesta final ya no trae", () => {
    const e = ejecutar("salvaguarda");
    expect(e.borrador).toContain("12 %");
    expect(e.respuesta?.texto_markdown).not.toContain("12 %");
  });

  it("ningún escenario habla de filas, colas, otras consultas ni saturación", () => {
    for (const m of ESCENARIOS) {
      for (const texto of textosVisibles(m)) {
        expect(texto).not.toMatch(/(fila|cola|turno|posici[oó]n|en curso|ocupad|saturad|demanda|antes que la tuya)/i);
        expect(texto).not.toMatch(/otras? consultas?|varias consultas|muchas consultas/i);
      }
    }
  });

  it("cola larga sin mencionarla: `cola` solo con diagnóstico y, a la vista, rotación de frases", () => {
    expect(tipos("cola por favor", { diagnostico: true }).filter((t) => t === "cola")).toHaveLength(3);
    const normal = tipos("cola por favor");
    expect(normal).not.toContain("cola");
    expect(normal[0]).toBe("progreso");
    const frases = textosVisibles("cola por favor");
    expect(frases).toContain("Pensando…");
    expect(frases).toContain("Sigo trabajando en tu pregunta…");
  });

  it("lento, respaldo y error emiten sus eventos", () => {
    expect(tipos("algo lento").filter((t) => t === "espera")).toHaveLength(2);
    expect(tipos("respaldo")).not.toContain("espera");
    expect(ejecutar("provoca un error").fase).toBe("error");
    expect(debeSaturar("prueba 429")).toBe(true);
    expect(debeSaturar("egresos")).toBe(false);
  });

  it("reanuda después de Last-Event-ID y formatea SSE", () => {
    const guion = guionPara(entrada("egresos"));
    expect(pasosDesde(guion, 2)[0].id).toBe(3);
    expect(pasosDesde(guion, guion.length)).toHaveLength(0);
    expect(formatearSSE(4, { tipo: "fin", datos: {} })).toBe("id: 4\nevent: fin\ndata: {}\n\n");
  });
});

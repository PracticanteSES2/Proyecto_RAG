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

describe("guiones del mock", () => {
  it("los pasos van en orden cronológico y terminan en fin", () => {
    for (const m of ["hola", "egresos", "ocupación", "qué es un egreso", "cola", "lento", "respaldo", "error"]) {
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

  it("documentación llega degradada y con aviso", () => {
    const e = ejecutar("¿Qué es un egreso?");
    expect(e.respuesta?.degradada).toBe(true);
    expect(e.avisos[0]?.motivo).toBe("sin_redaccion");
  });

  it("cola, lento, respaldo y error emiten sus eventos", () => {
    expect(tipos("cola por favor").filter((t) => t === "cola")).toHaveLength(3);
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

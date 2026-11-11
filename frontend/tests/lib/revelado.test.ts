import { describe, expect, it } from "vitest";
import {
  DURACION_MAX_MS,
  duracionRevelado,
  planRevelado,
  unidadesCubiertas,
  unidadesRevelado,
  unidadesVisibles,
} from "@/lib/turno/revelado";

const TABLA = "Hubo **1.284** egresos.\n\n| Servicio | Egresos |\n|---|---:|\n| UCI | 112 |\n\nFin del dato.";

describe("revelado de respuestas", () => {
  it("las unidades reconstruyen el texto exacto", () => {
    for (const texto of [TABLA, "Una línea", "  con espacios  \n\n- lista\n- otra\n", "```\ncodigo\n```\ntexto"]) {
      expect(unidadesRevelado(texto).join("")).toBe(texto);
    }
  });

  it("las tablas y el código son una sola unidad (nunca se ven a medias)", () => {
    const unidades = unidadesRevelado(TABLA);
    expect(unidades).toContain("| Servicio | Egresos |\n|---|---:|\n| UCI | 112 |\n");
    expect(unidades.filter((u) => u.includes("|"))).toHaveLength(1);
    expect(unidadesRevelado("```\na\nb\n```\n")).toEqual(["```\na\nb\n```\n"]);
  });

  it("si la final empieza por el borrador se continúa desde ahí", () => {
    const unidades = unidadesRevelado("Un egreso es la salida del paciente.");
    expect(unidadesCubiertas(unidades, "Un egreso es")).toBe(3);
    expect(unidadesCubiertas(unidades, "Un  egreso\nes la")).toBe(4); // espacios normalizados
    expect(unidadesCubiertas(unidades, "")).toBe(0);
    expect(unidadesCubiertas(unidades, "Un egreso fue")).toBe(-1);
  });

  it("plan: historial completo; en vivo desde cero; borrador que coincide continúa; si no, fundido", () => {
    const texto = "Un egreso es la salida del paciente.";
    expect(planRevelado(texto, undefined, false).inicio).toBe(unidadesRevelado(texto).length);
    expect(planRevelado(texto, undefined, true)).toMatchObject({ inicio: 0, fundido: false });
    expect(planRevelado(texto, "Un egreso", true)).toMatchObject({ inicio: 2, fundido: false });
    const cambiado = planRevelado(texto, "Un egreso subió un 12 %", true);
    expect(cambiado.fundido).toBe(true);
    expect(cambiado.inicio).toBe(cambiado.unidades.length);
  });

  it("rápido y acotado: nunca más de 700 ms, y termina mostrando todo", () => {
    expect(duracionRevelado(0)).toBe(0);
    expect(duracionRevelado(5)).toBeGreaterThan(0);
    expect(duracionRevelado(10_000)).toBe(DURACION_MAX_MS);
    expect(unidadesVisibles(0, 100, 0)).toBe(0);
    const mitad = unidadesVisibles(0, 100, DURACION_MAX_MS / 2);
    expect(mitad).toBeGreaterThan(50); // arranca rápido y se asienta
    expect(mitad).toBeLessThan(100);
    expect(unidadesVisibles(0, 100, DURACION_MAX_MS)).toBe(100);
    expect(unidadesVisibles(40, 50, 0)).toBe(40);
  });
});

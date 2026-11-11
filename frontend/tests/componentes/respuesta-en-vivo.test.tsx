import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MensajeAsistente } from "@/components/chat/MensajeAsistente";
import type { EventoTurno } from "@/lib/api/tipos";
import type { AccionTurno } from "@/lib/turno/maquina";
import { mensaje, props, respuesta } from "./ayudas";

/** Respuesta que aparece de a poco: borrador con tokens, revelado y reemplazo por la final (specs/009). */
describe("MensajeAsistente: respuesta en vivo", () => {
  const ev = (evento: EventoTurno): AccionTurno => ({ tipo: "evento", evento });
  const token = (texto: string) => ev({ tipo: "token", datos: { texto } });
  const creado: AccionTurno = { tipo: "creado", turnoId: "t1" };

  /** Animación activa (sin «movimiento reducido») y cuadros de animación que la prueba avanza a mano. */
  function conAnimacion() {
    const cuadros: FrameRequestCallback[] = [];
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query }));
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => cuadros.push(cb));
    vi.stubGlobal("cancelAnimationFrame", () => {});
    return (ms: number) =>
      act(() => {
        for (const cb of cuadros.splice(0)) cb(ms);
      });
  }

  afterEach(() => vi.unstubAllGlobals());

  it("con tokens muestra el borrador en una burbuja con cursor, sin el indicador", () => {
    render(<MensajeAsistente {...props} mensaje={mensaje([creado, token("Un egreso "), token("es la salida")])} />);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText("Un egreso es la salida")).toBeInTheDocument();
    expect(document.querySelector(".prosa--escribiendo")).not.toBeNull();
    expect(document.querySelector("[aria-busy=true]")).not.toBeNull();
  });

  it("del borrador a la final sin desmontar la burbuja y sin cursor al terminar", () => {
    const acciones = [creado, token("Hubo **1.284** egresos.")];
    const { rerender } = render(<MensajeAsistente {...props} mensaje={mensaje(acciones)} />);
    const burbuja = document.querySelector("[aria-busy]");
    rerender(<MensajeAsistente {...props} mensaje={mensaje([...acciones, respuesta()])} />);
    expect(document.querySelector("[aria-busy]")).toBe(burbuja);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(document.querySelector(".prosa--escribiendo")).toBeNull();
  });

  it("respuesta completa en vivo: escritura rápida y los extras aparecen al terminar", () => {
    const avanzar = conAnimacion();
    render(<MensajeAsistente {...props} mensaje={mensaje([creado, respuesta()])} />);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("link", { name: /Abrir en Power BI/ })).toBeNull();
    avanzar(0);
    avanzar(100);
    expect(screen.getByText(/Hubo/)).toBeInTheDocument();
    avanzar(800);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Abrir en Power BI/ })).toBeInTheDocument();
    expect(document.querySelector(".prosa--escribiendo")).toBeNull();
  });

  it("si la salvaguarda cambió el texto, la final reemplaza al borrador con un fundido", () => {
    conAnimacion();
    const acciones = [creado, token("Un egreso subió un 12 % en 2025.")];
    render(
      <MensajeAsistente
        {...props}
        mensaje={mensaje([...acciones, respuesta({ texto_markdown: "Un egreso es la salida del paciente." })])}
      />,
    );
    expect(screen.getByText("Un egreso es la salida del paciente.")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("12 %");
    expect(document.querySelector(".respuesta--fundido")).not.toBeNull();
  });

  it("la respuesta del historial (sin revelar) aparece completa aunque haya animación", () => {
    conAnimacion();
    const m = mensaje([]);
    m.turno = { ...m.turno, fase: "listo", respuesta: { ...respuestaDatos(), texto_markdown: "Hubo 5 egresos." } };
    render(<MensajeAsistente {...props} mensaje={m} />);
    expect(screen.getByText("Hubo 5 egresos.")).toBeInTheDocument();
  });
});

function respuestaDatos() {
  const accion = respuesta();
  if (accion.tipo !== "evento" || accion.evento.tipo !== "respuesta") throw new Error("respuesta de prueba");
  return accion.evento.datos;
}

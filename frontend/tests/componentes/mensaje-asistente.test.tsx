import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MensajeAsistente } from "@/components/chat/MensajeAsistente";
import type { AccionTurno } from "@/lib/turno/maquina";
import { mensaje, props, respuesta } from "./ayudas";

describe("MensajeAsistente", () => {
  it("mientras piensa muestra el indicador", () => {
    render(<MensajeAsistente {...props} mensaje={mensaje([{ tipo: "creado", turnoId: "t1" }])} />);
    expect(screen.getByRole("status")).toHaveTextContent("Entendiendo tu pregunta…");
  });

  it("muestra Markdown saneado con tabla, enlace a Power BI y fuentes", () => {
    render(<MensajeAsistente {...props} mensaje={mensaje([{ tipo: "creado", turnoId: "t1" }, respuesta()])} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "112" })).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText("malo").closest("a")?.getAttribute("href") ?? "").not.toContain("javascript");
    const enlace = screen.getByRole("link", { name: /Abrir en Power BI ›/ });
    expect(enlace).toHaveAttribute("href", "https://app.powerbi.com/x");
    expect(enlace).toHaveAttribute("target", "_blank");
    expect(screen.getByText(/Egresos hospitalarios · Resumen/)).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("muestra el aviso de respuesta degradada como nota discreta", () => {
    render(
      <MensajeAsistente {...props} mensaje={mensaje([respuesta({ degradada: true, aviso: "Hubo mucha demanda." })])} />,
    );
    expect(screen.getByText("Hubo mucha demanda.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("las opciones de la contrapregunta envían su id", async () => {
    const alElegirOpcion = vi.fn();
    const contrapregunta = {
      pregunta: "¿Cuál ocupación?",
      opciones: [{ id: "op-uci", texto: "UCI adultos", descripcion: "Camas UCI" }],
    };
    render(
      <MensajeAsistente
        {...props}
        contrapreguntaActiva
        alElegirOpcion={alElegirOpcion}
        mensaje={mensaje([respuesta({ contrapregunta })])}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /UCI adultos/ }));
    expect(alElegirOpcion).toHaveBeenCalledWith("op-uci", "UCI adultos");
  });

  it("opciones de una contrapregunta ya respondida quedan desactivadas", () => {
    const contrapregunta = {
      pregunta: "¿Cuál?",
      opciones: [
        { id: "a", texto: "A" },
        { id: "b", texto: "B" },
      ],
    };
    render(<MensajeAsistente {...props} mensaje={mensaje([respuesta({ contrapregunta })], { opcionElegida: "a" })} />);
    expect(screen.getByRole("button", { name: "A" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "A" })).toHaveAttribute("aria-pressed", "true");
  });

  it("429: aviso amable con Reintentar y sin jerga", async () => {
    const alReintentar = vi.fn();
    render(<MensajeAsistente {...props} alReintentar={alReintentar} mensaje={mensaje([{ tipo: "saturado" }])} />);
    expect(screen.getByText(/Hay muchas consultas en este momento/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Reintentar/ }));
    expect(alReintentar).toHaveBeenCalled();
  });

  it("error: el detalle técnico solo aparece con diagnóstico", () => {
    const acciones: AccionTurno[] = [
      { tipo: "evento", evento: { tipo: "error", datos: { mensaje: "TimeoutError DAX", codigo: "powerbi_timeout" } } },
    ];
    const { rerender } = render(<MensajeAsistente {...props} mensaje={mensaje(acciones)} />);
    expect(screen.getByText(/No pude completar esta consulta/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("powerbi_timeout");
    rerender(<MensajeAsistente {...props} diagnostico mensaje={mensaje(acciones)} />);
    expect(document.body.textContent).toContain("powerbi_timeout");
  });

  it("modo diagnóstico muestra el panel con DAX", () => {
    const m = mensaje([respuesta({ diagnostico: { dax: 'EVALUATE ROW("x", 1)' } })]);
    render(<MensajeAsistente {...props} diagnostico mensaje={m} />);
    expect(screen.getByText(/Detalles técnicos/)).toBeInTheDocument();
    expect(screen.getByText(/EVALUATE ROW/)).toBeInTheDocument();
  });
});

import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Calificacion } from "@/components/chat/Calificacion";
import { Compositor } from "@/components/chat/Compositor";

describe("Compositor", () => {
  it("Enter envía y limpia; Shift+Enter hace salto de línea", async () => {
    const alEnviar = vi.fn();
    render(<Compositor ocupado={false} alEnviar={alEnviar} alDetener={vi.fn()} />);
    const campo = screen.getByLabelText("Escribe tu pregunta");
    await userEvent.type(campo, "Primera línea{Shift>}{Enter}{/Shift}segunda");
    expect(alEnviar).not.toHaveBeenCalled();
    expect(campo).toHaveValue("Primera línea\nsegunda");
    await userEvent.type(campo, "{Enter}");
    expect(alEnviar).toHaveBeenCalledWith("Primera línea\nsegunda");
    expect(campo).toHaveValue("");
  });

  it("no envía vacío y el botón está desactivado", async () => {
    const alEnviar = vi.fn();
    render(<Compositor ocupado={false} alEnviar={alEnviar} alDetener={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Enviar pregunta" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Escribe tu pregunta"), "   {Enter}");
    expect(alEnviar).not.toHaveBeenCalled();
  });

  it("con un turno en curso Enter no envía y el botón es «Detener»", async () => {
    const alEnviar = vi.fn();
    const alDetener = vi.fn();
    render(<Compositor ocupado alEnviar={alEnviar} alDetener={alDetener} />);
    await userEvent.type(screen.getByLabelText("Escribe tu pregunta"), "otra{Enter}");
    expect(alEnviar).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Detener la consulta" }));
    expect(alDetener).toHaveBeenCalled();
  });
});

describe("Calificacion", () => {
  it("pulgar arriba califica al instante", async () => {
    const alCalificar = vi.fn();
    render(<Calificacion alCalificar={alCalificar} />);
    await userEvent.click(screen.getByRole("button", { name: "Me sirvió" }));
    expect(alCalificar).toHaveBeenCalledWith("buena");
  });

  it("pulgar abajo pide un comentario opcional antes de enviar", async () => {
    const alCalificar = vi.fn();
    render(<Calificacion alCalificar={alCalificar} />);
    await userEvent.click(screen.getByRole("button", { name: "No me sirvió" }));
    expect(alCalificar).not.toHaveBeenCalled();
    const cuadro = screen.getByLabelText(/Qué esperabas/);
    fireEvent.change(cuadro, { target: { value: "Faltó el año" } });
    await userEvent.click(within(cuadro.parentElement!).getByRole("button", { name: "Enviar" }));
    expect(alCalificar).toHaveBeenCalledWith("mala", "Faltó el año");
  });

  it("muestra la confirmación cuando se guardó", () => {
    render(<Calificacion alCalificar={vi.fn()} calificacion={{ valor: "buena", estado: "guardada" }} />);
    expect(screen.getByText("Gracias por tu opinión.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Me sirvió" })).toHaveAttribute("aria-pressed", "true");
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IndicadorPensando } from "@/components/chat/IndicadorPensando";

describe("IndicadorPensando", () => {
  it("es una región de estado con la frase y sin números ni etapas técnicas", () => {
    render(
      <IndicadorPensando
        frase="Consultando los datos en Power BI…"
        fraseEspera="Esto está tomando un poco más de lo normal…"
        etapas={[{ etapa: "consultando_powerbi", frase: "Consultando", t: 3.1 }]}
        segundos={12.4}
      />,
    );
    const estado = screen.getByRole("status");
    expect(estado).toHaveAttribute("aria-live", "polite");
    expect(estado).toHaveTextContent("Consultando los datos en Power BI…");
    expect(estado).toHaveTextContent("Esto está tomando un poco más de lo normal…");
    expect(document.body.textContent).not.toMatch(/\d/);
    expect(document.body.textContent).not.toContain("consultando_powerbi");
  });

  it("con diagnóstico muestra la línea de tiempo con segundos", () => {
    render(
      <IndicadorPensando
        frase="Consultando…"
        diagnostico
        etapas={[{ etapa: "consultando_powerbi", frase: "Consultando", t: 3.1 }]}
        segundos={12.4}
      />,
    );
    const linea = screen.getByLabelText("Línea de tiempo del turno");
    expect(linea).toHaveTextContent("consultando_powerbi");
    expect(linea).toHaveTextContent("3,1 s");
  });

  it("al cambiar de frase mantiene la anterior oculta para el fundido", () => {
    const { rerender } = render(<IndicadorPensando frase="Entendiendo tu pregunta…" />);
    rerender(<IndicadorPensando frase="Buscando el indicador…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Buscando el indicador…");
    expect(screen.getByText("Entendiendo tu pregunta…")).toHaveAttribute("aria-hidden", "true");
  });
});

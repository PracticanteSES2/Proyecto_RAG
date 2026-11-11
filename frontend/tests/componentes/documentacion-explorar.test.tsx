import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Documentacion } from "@/components/documentacion/Documentacion";
import { NavegacionPrincipal } from "@/components/ui/NavegacionPrincipal";
import { GRUPO, abrirPagina, clienteDocFalso } from "./documentacionFalso";

describe("Documentación: explorar", () => {
  it("busca sin importar tildes y abre el documento con ficha e historial", async () => {
    const cliente = clienteDocFalso();
    const usuario = userEvent.setup();
    render(<Documentacion cliente={cliente} />);
    const tableros = await screen.findByRole("complementary", { name: "Tableros" });
    await within(tableros).findByRole("button", { name: /TABLERO LAVANDERÍA/ });
    await usuario.type(within(tableros).getByRole("searchbox"), "lavanderia");
    expect(within(tableros).queryByRole("button", { name: /TIEMPOS URGENCIAS/ })).toBeNull();
    expect(within(tableros).getByRole("button", { name: /INICIO/ })).toBeInTheDocument();

    await usuario.clear(within(tableros).getByRole("searchbox"));
    await usuario.type(within(tableros).getByRole("searchbox"), "historicos");
    expect(within(tableros).getByRole("button", { name: /RESUMEN/ })).toBeInTheDocument();
    expect(within(tableros).queryByRole("button", { name: /CONSULTAS DIA/ })).toBeNull();
  });

  it("muestra el documento: formato, ficha, cuerpo, historial y el .md guardado", async () => {
    const cliente = clienteDocFalso();
    await abrirPagina(cliente);
    expect(cliente.documento).toHaveBeenCalledWith(GRUPO, "consultas_dia.md");
    expect(screen.getByText("Formato válido")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ficha de la página" })).toBeInTheDocument();
    expect(screen.getByText("Semáforo triage II")).toBeInTheDocument();
    expect(screen.getByText("2026-10-20 · v1")).toBeInTheDocument();
    expect(screen.getByText("Ver el archivo .md tal como está guardado")).toBeInTheDocument();
  });

  it("marca la sección actual en la navegación", () => {
    render(<NavegacionPrincipal actual="documentacion" />);
    const actual = screen.getAllByRole("link", { name: "Documentación" })[0]!;
    expect(actual).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link", { name: /Chat/ })[0]).toHaveAttribute("href", "/");
  });
});

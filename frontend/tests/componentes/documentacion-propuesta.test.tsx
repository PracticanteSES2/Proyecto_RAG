import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ESPERA, GRUPO, abrirPagina, clienteDocFalso, proponer, propuesta } from "./documentacionFalso";

describe("Documentación: proponer y revisar", () => {
  it("envía la nota con la página elegida y espera con frases de trabajo", async () => {
    const preparando = propuesta({
      estado: "preparando",
      progreso: { etapa: "redactando", frase: "Redactando el cambio en la documentación", espera: null },
    });
    const cliente = clienteDocFalso({ propuesta: vi.fn(async () => preparando) });
    await proponer(cliente);
    expect(cliente.proponer).toHaveBeenCalledWith({
      nota: "subí el verde del semáforo a 20",
      grupo: GRUPO,
      pagina: "CONSULTAS DIA",
      cambios_pbip: [],
      autor: "",
    });
    expect(await screen.findByText("Redactando el cambio en la documentación", {}, ESPERA)).toBeInTheDocument();
    expect(screen.queryByText(/cola|fila|saturad/i)).toBeNull();
  });

  it("pide la nota antes de enviar", async () => {
    const cliente = clienteDocFalso();
    const usuario = await abrirPagina(cliente);
    await usuario.click(screen.getByRole("button", { name: "Proponer un cambio en esta página" }));
    await usuario.click(screen.getByRole("button", { name: "Generar propuesta" }));
    expect(screen.getByText("Para generar la propuesta, escribe qué cambió.")).toBeInTheDocument();
    expect(cliente.proponer).not.toHaveBeenCalled();
  });

  it("muestra la revisión con un diff legible sin color", async () => {
    const cliente = clienteDocFalso();
    await proponer(cliente);
    await screen.findByRole("heading", { name: "Revisión de la propuesta" }, ESPERA);
    expect(screen.getByText("Revisa esto antes de aprobar (1)")).toBeInTheDocument();
    expect(screen.getByText(/Cómo se eligió la página: la nota la nombra/)).toBeInTheDocument();
    const sale = document.querySelector("del");
    const entra = document.querySelector("ins");
    expect(sale).toHaveTextContent("Sale: - **Semáforo triage II**: Verde de 0 a 15 minutos.");
    expect(entra).toHaveTextContent("Entra: - **Semáforo triage II**: Verde de 0 a 20 minutos.");
    expect(screen.getByText("El resultado cumple el formato")).toBeInTheDocument();
  });

  it("no deja aprobar con correcciones pendientes ni sin autor", async () => {
    const cliente = clienteDocFalso({
      corregir: vi.fn(async () => propuesta({ actualizada: "otra" })),
    });
    const usuario = await proponer(cliente);
    const texto = await screen.findByLabelText(/Texto nuevo/, {}, ESPERA);
    await usuario.clear(texto);
    await usuario.type(texto, "Verde de 0 a 25 minutos.");
    expect(screen.getByRole("button", { name: "Aprobar y guardar" })).toBeDisabled();
    await usuario.click(screen.getByRole("button", { name: "Actualizar vista previa" }));
    expect(cliente.corregir).toHaveBeenCalledWith("p1", [{ indice: 0, texto: "Verde de 0 a 25 minutos." }]);

    const aprobar = await screen.findByRole("button", { name: "Aprobar y guardar" });
    expect(aprobar).toBeEnabled();
    await usuario.click(aprobar);
    expect(screen.getByText("Escribe quién aprueba el cambio.")).toBeInTheDocument();
    expect(cliente.aprobar).not.toHaveBeenCalled();
    await usuario.type(screen.getByLabelText("Aprueba"), "Ana");
    await usuario.click(aprobar);
    expect(cliente.aprobar).toHaveBeenCalledWith("p1", "Ana");
  });

  it("tras aprobar muestra la versión y permite reintentar la reindexación", async () => {
    const aprobada = propuesta({
      estado: "aprobada",
      puede_aprobar: false,
      aprobacion: {
        autor: "Ana",
        version: 2,
        fecha: "2026-11-11",
        reindexacion: {
          grupo: GRUPO,
          estado: "error",
          mensaje: "La reindexación falló: sin índice.",
          documentos: null,
          chunks: null,
          segundos: null,
          conexion_compartida: false,
          avisos: [],
          iniciada: null,
          terminada: null,
        },
      },
    });
    const cliente = clienteDocFalso({
      aprobar: vi.fn(async () => aprobada),
      propuesta: vi.fn(async () => propuesta()),
    });
    const usuario = await proponer(cliente);
    await usuario.type(await screen.findByLabelText("Aprueba", {}, ESPERA), "Ana");
    await usuario.click(screen.getByRole("button", { name: "Aprobar y guardar" }));
    expect(await screen.findByText("Cambio aprobado")).toBeInTheDocument();
    expect(screen.getByText("la versión 2")).toBeInTheDocument();
    expect(screen.getByText(/todavía no lo conoce/)).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Reintentar la reindexación" }));
    expect(cliente.reindexar).toHaveBeenCalledWith(GRUPO);
  });

  it("pide aclaración con las páginas candidatas y reintenta con la elegida", async () => {
    const cliente = clienteDocFalso({
      propuesta: vi.fn(async () =>
        propuesta({
          estado: "requiere_aclaracion",
          nota: "nota ambigua",
          operaciones: [],
          diff: null,
          puede_aprobar: false,
          dudas: ["¿A qué página del tablero se refiere el cambio?"],
          candidatas: [{ pagina: "RESUMEN", etiqueta: "RESUMEN — Datos históricos · Histórico" }],
        }),
      ),
    });
    const usuario = await proponer(cliente, "nota ambigua");
    expect(await screen.findByText(/Hace falta una aclaración/, {}, ESPERA)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "RESUMEN — Datos históricos · Histórico" })).toBeChecked();
    await usuario.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(cliente.aclarar).toHaveBeenCalledWith("p1", { nota: "nota ambigua", pagina: "RESUMEN" });
  });

  it("explica un error del modelo con el detalle técnico plegado", async () => {
    const cliente = clienteDocFalso({
      propuesta: vi.fn(async () =>
        propuesta({
          estado: "error",
          operaciones: [],
          diff: null,
          puede_aprobar: false,
          errores: ["MedGemma devolvió una respuesta incompleta."],
          detalle_tecnico: '{"operaciones": [',
        }),
      ),
    });
    await proponer(cliente, "esto falla");
    expect(await screen.findByText("No se pudo preparar la propuesta.", {}, ESPERA)).toBeInTheDocument();
    expect(screen.getByText("MedGemma devolvió una respuesta incompleta.")).toBeInTheDocument();
    expect(screen.getByText("Detalle técnico")).toBeInTheDocument();
  });
});

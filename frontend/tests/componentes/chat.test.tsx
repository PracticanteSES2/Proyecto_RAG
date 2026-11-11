import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Chat } from "@/components/chat/Chat";
import { ErrorApi, type ClienteApi } from "@/lib/api/cliente";
import { ProveedorApi } from "@/lib/api/contexto";
import { clienteFalso } from "./clienteFalso";

const montar = (cliente: ClienteApi) =>
  render(
    <ProveedorApi cliente={cliente}>
      <Chat />
    </ProveedorApi>,
  );

describe("Chat (flujo completo contra un cliente falso)", () => {
  beforeEach(() => window.localStorage.clear());

  it("estado vacío con capacidades y ejemplos que se envían al pulsarlos", async () => {
    const { cliente } = clienteFalso();
    montar(cliente);
    expect(await screen.findByText("Cifras de los tableros")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "¿Cuántos egresos hubo en marzo?" }));
    await waitFor(() =>
      expect(cliente.enviarTurno).toHaveBeenCalledWith("c1", {
        mensaje: "¿Cuántos egresos hubo en marzo?",
        diagnostico: false,
      }),
    );
  });

  it("pregunta → progreso → respuesta, y el botón Detener mientras piensa", async () => {
    const { cliente, emitir } = clienteFalso();
    montar(cliente);
    await userEvent.type(screen.getByLabelText("Escribe tu pregunta"), "¿Egresos de marzo?{Enter}");
    await waitFor(() => expect(cliente.eventosTurno).toHaveBeenCalledWith("t1", expect.anything()));
    expect(screen.getByRole("button", { name: "Detener la consulta" })).toBeInTheDocument();

    emitir({
      tipo: "progreso",
      datos: { etapa: "consultando_powerbi", frase: "Consultando los datos en Power BI", t: 2 },
    });
    expect(screen.getByRole("status")).toHaveTextContent("Consultando los datos en Power BI…");

    emitir({
      tipo: "respuesta",
      datos: {
        turno_id: "t1",
        texto_markdown: "Hubo **1.284** egresos.",
        ruta: "powerbi",
        fuentes: [],
        enlaces_powerbi: [],
        degradada: false,
      },
    });
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText("1.284")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enviar pregunta" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Me sirvió" }));
    expect(cliente.calificarTurno).toHaveBeenCalledWith("t1", { valor: "buena" });
    expect(await screen.findByText("Gracias por tu opinión.")).toBeInTheDocument();
  });

  it("detener cierra el flujo y deja un aviso tranquilo", async () => {
    const { cliente, cerrar } = clienteFalso();
    montar(cliente);
    await userEvent.type(screen.getByLabelText("Escribe tu pregunta"), "egresos{Enter}");
    await waitFor(() => expect(cliente.eventosTurno).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("button", { name: "Detener la consulta" }));
    expect(cerrar).toHaveBeenCalled();
    expect(screen.getByText("Detuviste esta consulta.")).toBeInTheDocument();
  });

  it("429 muestra el aviso amable y Reintentar vuelve a enviar", async () => {
    let intentos = 0;
    const { cliente } = clienteFalso({
      enviarTurno: vi.fn(async () => {
        intentos += 1;
        if (intentos === 1) throw new ErrorApi("saturado", "429", 429);
        return { turno_id: "t2" };
      }),
    });
    montar(cliente);
    await userEvent.type(screen.getByLabelText("Escribe tu pregunta"), "egresos{Enter}");
    expect(await screen.findByText(/No pude recibir tu pregunta en este momento/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Reintentar/ }));
    await waitFor(() => expect(cliente.eventosTurno).toHaveBeenCalledWith("t2", expect.anything()));
    expect(screen.queryByText(/No pude recibir tu pregunta/)).toBeNull();
    expect(screen.getAllByText("egresos")).toHaveLength(1);
  });

  it("si /salud falla aparece el aviso de servidor", async () => {
    const { cliente } = clienteFalso({
      salud: vi.fn(async () => {
        throw new ErrorApi("red", "caído");
      }),
    });
    montar(cliente);
    expect(await screen.findByRole("alert")).toHaveTextContent("No logramos comunicarnos con el asistente.");
  });

  it("la contrapregunta envía opcion_id al elegir", async () => {
    const { cliente, emitir } = clienteFalso();
    montar(cliente);
    await userEvent.type(screen.getByLabelText("Escribe tu pregunta"), "ocupación{Enter}");
    await waitFor(() => expect(cliente.eventosTurno).toHaveBeenCalled());
    emitir({
      tipo: "respuesta",
      datos: {
        turno_id: "t1",
        texto_markdown: "¿Cuál?",
        ruta: "aclaracion",
        fuentes: [],
        enlaces_powerbi: [],
        degradada: false,
        contrapregunta: { pregunta: "Elige", opciones: [{ id: "op-uci", texto: "UCI adultos" }] },
      },
    });
    emitir({ tipo: "fin", datos: {} });
    await userEvent.click(screen.getByRole("button", { name: "UCI adultos" }));
    await waitFor(() =>
      expect(cliente.enviarTurno).toHaveBeenLastCalledWith("c1", {
        mensaje: "UCI adultos",
        diagnostico: false,
        opcion_id: "op-uci",
      }),
    );
  });
});

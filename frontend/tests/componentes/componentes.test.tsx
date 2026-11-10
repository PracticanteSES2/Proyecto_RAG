import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Calificacion } from "@/components/chat/Calificacion";
import { Compositor } from "@/components/chat/Compositor";
import { IndicadorPensando } from "@/components/chat/IndicadorPensando";
import { MensajeAsistente } from "@/components/chat/MensajeAsistente";
import type { EventoRespuesta } from "@/lib/api/tipos";
import type { MensajeAsistente as TipoMensajeAsistente } from "@/lib/chat/reductor";
import { estadoInicialTurno, reducirTurno, type AccionTurno } from "@/lib/turno/maquina";

const mensaje = (acciones: AccionTurno[], extra: Partial<TipoMensajeAsistente> = {}): TipoMensajeAsistente => ({
  id: "a1",
  rol: "asistente",
  solicitud: { mensaje: "¿Egresos?" },
  diagnostico: false,
  turno: acciones.reduce(reducirTurno, estadoInicialTurno()),
  ...extra,
});

const respuesta = (extra: Partial<EventoRespuesta> = {}): AccionTurno => ({
  tipo: "evento",
  evento: {
    tipo: "respuesta",
    datos: {
      turno_id: "t1",
      texto_markdown: "Hubo **1.284** egresos.\n\n| Servicio | Egresos |\n|---|---:|\n| UCI | 112 |\n\n<script>alert(1)</script>\n\n[malo](javascript:alert(1))",
      ruta: "powerbi",
      fuentes: [{ titulo: "Egresos hospitalarios", pagina: "Resumen" }],
      enlaces_powerbi: [{ titulo: "Egresos · Resumen", url: "https://app.powerbi.com/x" }],
      degradada: false,
      ...extra,
    },
  },
});

const props = {
  diagnostico: false,
  contrapreguntaActiva: false,
  ocupado: false,
  alElegirOpcion: vi.fn(),
  alReintentar: vi.fn(),
  alCalificar: vi.fn(),
};

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
      <IndicadorPensando frase="Consultando…" diagnostico etapas={[{ etapa: "consultando_powerbi", frase: "Consultando", t: 3.1 }]} segundos={12.4} />,
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
    render(<MensajeAsistente {...props} mensaje={mensaje([respuesta({ degradada: true, aviso: "Hubo mucha demanda." })])} />);
    expect(screen.getByText("Hubo mucha demanda.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("las opciones de la contrapregunta envían su id", async () => {
    const alElegirOpcion = vi.fn();
    const contrapregunta = { pregunta: "¿Cuál ocupación?", opciones: [{ id: "op-uci", texto: "UCI adultos", descripcion: "Camas UCI" }] };
    render(
      <MensajeAsistente {...props} contrapreguntaActiva alElegirOpcion={alElegirOpcion} mensaje={mensaje([respuesta({ contrapregunta })])} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /UCI adultos/ }));
    expect(alElegirOpcion).toHaveBeenCalledWith("op-uci", "UCI adultos");
  });

  it("opciones de una contrapregunta ya respondida quedan desactivadas", () => {
    const contrapregunta = { pregunta: "¿Cuál?", opciones: [{ id: "a", texto: "A" }, { id: "b", texto: "B" }] };
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
    const acciones: AccionTurno[] = [{ tipo: "evento", evento: { tipo: "error", datos: { mensaje: "TimeoutError DAX", codigo: "powerbi_timeout" } } }];
    const { rerender } = render(<MensajeAsistente {...props} mensaje={mensaje(acciones)} />);
    expect(screen.getByText(/No pude completar esta consulta/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("powerbi_timeout");
    rerender(<MensajeAsistente {...props} diagnostico mensaje={mensaje(acciones)} />);
    expect(document.body.textContent).toContain("powerbi_timeout");
  });

  it("modo diagnóstico muestra el panel con DAX", () => {
    const m = mensaje([respuesta({ diagnostico: { dax: "EVALUATE ROW(\"x\", 1)" } })]);
    render(<MensajeAsistente {...props} diagnostico mensaje={m} />);
    expect(screen.getByText(/Detalles técnicos/)).toBeInTheDocument();
    expect(screen.getByText(/EVALUATE ROW/)).toBeInTheDocument();
  });
});

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

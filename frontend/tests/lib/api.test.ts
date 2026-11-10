import { describe, expect, it, vi } from "vitest";
import { ErrorApi, crearClienteApi } from "@/lib/api/cliente";
import { mockActivo, urlBaseApi } from "@/lib/api/config";
import { abrirEventosTurno, interpretarEvento, type FuenteEventos } from "@/lib/api/sse";
import type { EventoTurno } from "@/lib/api/tipos";

describe("configuración", () => {
  it("usa localhost:8000 por defecto y quita la barra final", () => {
    expect(urlBaseApi(undefined, false)).toBe("http://localhost:8000");
    expect(urlBaseApi("https://asistente.hospital/ ", false)).toBe("https://asistente.hospital");
  });

  it("con mock usa el mismo origen", () => {
    expect(urlBaseApi("http://x", true)).toBe("");
    expect(mockActivo("1")).toBe(true);
    expect(mockActivo("0", "development")).toBe(false);
    expect(mockActivo(undefined, "production")).toBe(false);
    expect(mockActivo(undefined, "development")).toBe(true);
  });
});

describe("cliente", () => {
  const respuestaJson = (cuerpo: unknown, status = 200, headers: Record<string, string> = {}) =>
    new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json", ...headers } });

  it("envía el turno con el cuerpo del contrato", async () => {
    const fetchFn = vi.fn(async () => respuestaJson({ turno_id: "t1" }, 202));
    const cliente = crearClienteApi("http://api", fetchFn);
    await expect(cliente.enviarTurno("c 1", { mensaje: "hola", diagnostico: false, opcion_id: "op" })).resolves.toEqual(
      { turno_id: "t1" },
    );
    const [url, init] = fetchFn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/api/v1/conversaciones/c%201/turnos");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ mensaje: "hola", diagnostico: false, opcion_id: "op" });
  });

  it("clasifica 429 como saturado con Retry-After", async () => {
    const cliente = crearClienteApi("", async () => respuestaJson({}, 429, { "Retry-After": "5" }));
    const error = await cliente.enviarTurno("c", { mensaje: "x", diagnostico: false }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ErrorApi);
    expect(error).toMatchObject({ tipo: "saturado", estado: 429, reintentarEn: 5 });
  });

  it("clasifica fallos de red y 404", async () => {
    const caido = crearClienteApi("", async () => {
      throw new TypeError("Failed to fetch");
    });
    await expect(caido.salud()).rejects.toMatchObject({ tipo: "red" });
    const vacio = crearClienteApi("", async () => respuestaJson({}, 404));
    await expect(vacio.obtenerConversacion("c")).rejects.toMatchObject({ tipo: "no_encontrado" });
  });

  it("exporta como texto Markdown", async () => {
    const fetchFn = vi.fn(async () => new Response("# Conversación", { status: 200 }));
    await expect(crearClienteApi("", fetchFn).exportarConversacion("c1")).resolves.toBe("# Conversación");
    expect((fetchFn.mock.calls[0] as unknown as [string])[0]).toBe("/api/v1/conversaciones/c1/exportar?formato=md");
  });
});

class FuenteFalsa implements FuenteEventos {
  readyState = 1;
  onerror: ((evento: Event) => void) | null = null;
  cerrada = false;
  private oyentes = new Map<string, ((e: Event | MessageEvent<string>) => void)[]>();
  addEventListener(tipo: string, oyente: (e: Event | MessageEvent<string>) => void) {
    this.oyentes.set(tipo, [...(this.oyentes.get(tipo) ?? []), oyente]);
  }
  close() {
    this.cerrada = true;
    this.readyState = 2;
  }
  emitir(tipo: string, datos: unknown) {
    const mensaje = new MessageEvent(tipo, { data: JSON.stringify(datos) });
    this.oyentes.get(tipo)?.forEach((o) => o(mensaje));
    if (tipo === "error") this.onerror?.(mensaje);
  }
  fallarConexion(estado = 0) {
    this.readyState = estado;
    const nativo = new Event("error");
    this.oyentes.get("error")?.forEach((o) => o(nativo));
    this.onerror?.(nativo);
  }
}

describe("eventos SSE", () => {
  const abrir = (maxReintentos?: number) => {
    const fuente = new FuenteFalsa();
    const eventos: EventoTurno[] = [];
    const alDesconectar = vi.fn();
    const sub = abrirEventosTurno("/x", {
      alEvento: (e) => eventos.push(e),
      alDesconectar,
      crearFuente: () => fuente,
      maxReintentos,
    });
    return { fuente, eventos, alDesconectar, sub };
  };

  it("interpreta eventos conocidos y descarta basura", () => {
    expect(interpretarEvento("progreso", '{"etapa":"entendiendo","frase":"a","t":0}')).toEqual({
      tipo: "progreso",
      datos: { etapa: "entendiendo", frase: "a", t: 0 },
    });
    expect(interpretarEvento("desconocido", "{}")).toBeNull();
    expect(interpretarEvento("progreso", "{no json")).toBeNull();
  });

  it("entrega los eventos en orden y se cierra con fin", () => {
    const { fuente, eventos, alDesconectar } = abrir();
    fuente.emitir("progreso", { etapa: "entendiendo", frase: "Entendiendo", t: 0 });
    fuente.emitir("respuesta", { turno_id: "t" });
    fuente.emitir("fin", {});
    fuente.emitir("aviso", { motivo: "saturado", texto: "tarde" });
    expect(eventos.map((e) => e.tipo)).toEqual(["progreso", "respuesta", "fin"]);
    expect(fuente.cerrada).toBe(true);
    expect(alDesconectar).not.toHaveBeenCalled();
  });

  it("el evento de servidor «error» no se confunde con un fallo de conexión", () => {
    const { fuente, eventos, alDesconectar } = abrir(0);
    fuente.emitir("error", { mensaje: "falló", codigo: "x" });
    expect(eventos).toEqual([{ tipo: "error", datos: { mensaje: "falló", codigo: "x" } }]);
    expect(alDesconectar).not.toHaveBeenCalled();
  });

  it("tolera reconexiones del navegador y se rinde tras demasiados fallos", () => {
    const { fuente, alDesconectar } = abrir(2);
    fuente.fallarConexion();
    fuente.fallarConexion();
    expect(alDesconectar).not.toHaveBeenCalled();
    fuente.fallarConexion();
    expect(alDesconectar).toHaveBeenCalledOnce();
    expect(fuente.cerrada).toBe(true);
  });

  it("avisa si el servidor cierra la conexión", () => {
    const { fuente, alDesconectar } = abrir();
    fuente.fallarConexion(2);
    expect(alDesconectar).toHaveBeenCalledOnce();
  });

  it("cerrar a mano no cuenta como desconexión", () => {
    const { fuente, alDesconectar, sub } = abrir();
    sub.cerrar();
    expect(fuente.cerrada).toBe(true);
    expect(alDesconectar).not.toHaveBeenCalled();
  });
});

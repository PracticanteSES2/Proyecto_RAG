import { afterEach, describe, expect, it, vi } from "vitest";
import { crearClienteDocumentacion, mensajeDeError } from "@/lib/api/documentacion";
import { ErrorApi } from "@/lib/api/cliente";
import type { Propuesta } from "@/lib/api/tiposDocumentacion";
import { debeSondear, filtrarExplorador, plegar } from "@/lib/documentacion/estado";
import { bloquesDiff, contarCambios } from "@/lib/mock/diff";
import { responderDocumentacion } from "@/lib/mock/rutasDocumentacion";

const json = (cuerpo: unknown, status = 200) =>
  new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json" } });

describe("cliente de documentación", () => {
  it("usa las rutas y cuerpos del contrato", async () => {
    const fetchFn = vi.fn(async () => json({}));
    const cliente = crearClienteDocumentacion("http://api", fetchFn);
    await cliente.documento("tablero x", "consultas_dia.md");
    await cliente.proponer({ nota: "n", grupo: "g", pagina: null, cambios_pbip: [], autor: "" });
    await cliente.corregir("p1", [{ indice: 0, texto: "t" }]);
    await cliente.aprobar("p1", "Ana");
    await cliente.reindexar("g");
    const llamadas = fetchFn.mock.calls as unknown as [string, RequestInit][];
    expect(llamadas.map(([url]) => url)).toEqual([
      "http://api/api/v1/documentacion/grupos/tablero%20x/paginas/consultas_dia.md",
      "http://api/api/v1/documentacion/propuestas",
      "http://api/api/v1/documentacion/propuestas/p1/operaciones",
      "http://api/api/v1/documentacion/propuestas/p1/aprobar",
      "http://api/api/v1/documentacion/grupos/g/reindexar",
    ]);
    expect(JSON.parse(llamadas[2]![1].body as string)).toEqual({ textos: [{ indice: 0, texto: "t" }] });
    expect(JSON.parse(llamadas[3]![1].body as string)).toEqual({ autor: "Ana" });
  });

  it("conserva el mensaje amable y el código del backend", async () => {
    const cliente = crearClienteDocumentacion("", async () =>
      json({ mensaje: "La documentación de X cambió.", codigo: "documento_modificado" }, 409),
    );
    const error = await cliente.aprobar("p1", "Ana").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ErrorApi);
    expect(error).toMatchObject({ codigo: "documento_modificado", estado: 409 });
    expect(mensajeDeError(error, "No se guardó")).toBe("La documentación de X cambió.");
    expect(mensajeDeError(new ErrorApi("red", "x"), "No se guardó")).toMatch(/Revisa tu conexión/);
  });
});

describe("estado de la página", () => {
  const base = { estado: "lista", aprobacion: null } as unknown as Propuesta;

  it("sondea mientras prepara o reindexa", () => {
    expect(debeSondear(null)).toBe(false);
    expect(debeSondear({ ...base, estado: "preparando" })).toBe(true);
    expect(debeSondear(base)).toBe(false);
    const reindexando = { ...base, estado: "aprobada", aprobacion: { reindexacion: { estado: "en_curso" } } };
    expect(debeSondear(reindexando as unknown as Propuesta)).toBe(true);
  });

  it("filtra tableros y páginas sin tildes", () => {
    expect(plegar("  Lavandería ")).toBe("lavanderia");
    const grupos = [
      { grupo: "a", tablero: "Urgencias", paginas: 2 },
      { grupo: "b", tablero: "Lavandería", paginas: 1 },
    ];
    const pagina = (archivo: string, etiqueta: string) => ({
      archivo,
      etiqueta,
      pagina: etiqueta,
      nombre_funcional: "",
      bloque: "",
      valido: true,
      general: false,
    });
    const paginas = { a: [pagina("c.md", "CONSULTAS DÍA"), pagina("r.md", "RESUMEN")], b: [pagina("i.md", "INICIO")] };
    expect(filtrarExplorador(grupos, paginas, "").map((g) => g.paginas.length)).toEqual([2, 1]);
    const porPagina = filtrarExplorador(grupos, paginas, "consultas dia");
    expect(porPagina).toHaveLength(1);
    expect(porPagina[0]!.paginas.map((p) => p.archivo)).toEqual(["c.md"]);
    expect(filtrarExplorador(grupos, paginas, "LAVANDERIA")[0]).toMatchObject({ coincideTablero: true });
    expect(filtrarExplorador(grupos, paginas, "nada")).toEqual([]);
  });
});

describe("mock de documentación", () => {
  afterEach(() => vi.useRealTimers());

  const post = async (ruta: string[], cuerpo: Record<string, unknown> | null) =>
    (await responderDocumentacion("POST", ruta, cuerpo).json()) as Propuesta;
  const get = async (ruta: string[]) => (await responderDocumentacion("GET", ruta, null).json()) as Propuesta;

  it("diff por tramos con una línea de contexto", () => {
    const antes = ["a", "b", "c", "d", "e", "f"].join("\n");
    const despues = ["a", "B", "c", "d", "e", "f", "g"].join("\n");
    expect(bloquesDiff(antes, despues)).toEqual([
      {
        lineas: [
          { tipo: "igual", texto: "a" },
          { tipo: "sale", texto: "b" },
          { tipo: "entra", texto: "B" },
          { tipo: "igual", texto: "c" },
        ],
      },
      {
        lineas: [
          { tipo: "igual", texto: "f" },
          { tipo: "entra", texto: "g" },
        ],
      },
    ]);
    expect(contarCambios(antes, despues)).toEqual([2, 1]);
  });

  it("recorre el flujo: preparando → lista → corregir → aprobar → reindexar", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-11T10:00:00"));
    const creada = await post(["propuestas"], {
      nota: "subí el semáforo a 20",
      grupo: "tablero_tiempos_urgencias",
      pagina: null,
      cambios_pbip: [],
      autor: "",
    });
    expect(creada).toMatchObject({ estado: "preparando", progreso: { frase: "Leyendo tu nota" } });
    const id = creada.propuesta_id;

    vi.setSystemTime(new Date("2026-11-11T10:00:05"));
    const lista = await get(["propuestas", id]);
    expect(lista.estado).toBe("lista");
    expect(lista.pagina).toBe("CONSULTAS DIA");
    expect(lista.operaciones[0]?.texto_actual).toMatch(/Verde de 0 a 15/);
    expect(lista.diff?.bloques.length).toBeGreaterThan(0);

    const corregida = await post(["propuestas", id, "operaciones"], { textos: [{ indice: 0, texto: "Verde a 25." }] });
    expect(corregida.operaciones[0]?.texto).toBe("Verde a 25.");

    const aprobada = await post(["propuestas", id, "aprobar"], { autor: "Ana" });
    expect(aprobada.estado).toBe("aprobada");
    expect(aprobada.aprobacion?.reindexacion.estado).toBe("en_curso");
    vi.setSystemTime(new Date("2026-11-11T10:00:09"));
    expect((await get(["propuestas", id])).aprobacion?.reindexacion.estado).toBe("lista");
  });

  it("valida la nota y explica los casos de error y aclaración", async () => {
    const vacia = responderDocumentacion("POST", ["propuestas"], { nota: " ", grupo: "tablero_lavanderia" });
    expect(vacia.status).toBe(422);
    expect(await vacia.json()).toEqual({ codigo: "peticion_invalida", mensaje: "Escribe qué cambió en el tablero." });
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-11T11:00:00"));
    const ambigua = await post(["propuestas"], { nota: "nota ambigua", grupo: "tablero_tiempos_urgencias" });
    const falla = await post(["propuestas"], { nota: "esto falla", grupo: "tablero_tiempos_urgencias" });
    vi.setSystemTime(new Date("2026-11-11T11:00:06"));
    const aclarar = await get(["propuestas", ambigua.propuesta_id]);
    expect(aclarar.estado).toBe("requiere_aclaracion");
    expect(aclarar.candidatas.length).toBeGreaterThan(0);
    const error = await get(["propuestas", falla.propuesta_id]);
    expect(error).toMatchObject({ estado: "error", detalle_tecnico: '{"operaciones": [' });
  });
});

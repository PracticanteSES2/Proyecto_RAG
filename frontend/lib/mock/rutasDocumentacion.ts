/** Enrutador del mock de `/api/v1/documentacion/**` (lo usa `app/api/v1/documentacion/[...ruta]/route.ts`). */
import type { SolicitudPropuesta } from "@/lib/api/tiposDocumentacion";
import { docMock, documentoMock, grupoMock, listaGrupos, listaPaginas } from "./documentacion";
import { aclararMock, aprobarMock, corregirMock, crearPropuesta, registroMock, vistaPropuesta } from "./propuestas";
import { estadoReindexacion, lanzarReindexacion } from "./reindexacionMock";

type Cuerpo = Record<string, unknown> | null;

const error = (estado: number, codigo: string, mensaje: string) =>
  Response.json({ mensaje, codigo }, { status: estado });
const sinGrupo = () => error(404, "grupo_no_encontrado", "No encontré la documentación de ese tablero.");
const sinPropuesta = () =>
  error(
    404,
    "propuesta_no_encontrada",
    "No encontré esa propuesta; puede haber expirado. Vuelve a proponer el cambio.",
  );
const texto = (valor: unknown) => (typeof valor === "string" ? valor.trim() : "");

function grupos(metodo: string, [grupo, recurso, archivo]: string[]): Response {
  const g = grupo ? grupoMock(grupo) : undefined;
  if (!grupo) return Response.json({ grupos: listaGrupos() });
  if (!g) return sinGrupo();
  if (recurso === "paginas" && !archivo) return Response.json(listaPaginas(g));
  if (recurso === "paginas" && archivo) {
    const d = docMock(g.grupo, archivo);
    return d
      ? Response.json(documentoMock(g, d))
      : error(404, "pagina_no_encontrada", "No encontré esa página en la documentación del tablero.");
  }
  if (recurso === "reindexar" && metodo === "POST") {
    lanzarReindexacion(g);
    return Response.json(estadoReindexacion(g), { status: 202 });
  }
  if (recurso === "reindexacion") return Response.json(estadoReindexacion(g));
  return error(404, "no_encontrado", "No encontrado");
}

function nuevaPropuesta(cuerpo: Cuerpo): Response {
  const nota = texto(cuerpo?.nota);
  if (!nota) return error(422, "peticion_invalida", "Escribe qué cambió en el tablero.");
  const registro = crearPropuesta({ ...(cuerpo as unknown as SolicitudPropuesta), nota });
  return registro ? Response.json(vistaPropuesta(registro), { status: 202 }) : sinGrupo();
}

function accion(id: string, verbo: string | undefined, cuerpo: Cuerpo): Response {
  const registro = registroMock(id);
  if (!registro) return sinPropuesta();
  const vista = () => Response.json(vistaPropuesta(registro), { status: verbo === "aclaracion" ? 202 : 200 });
  if (verbo === "operaciones") {
    const fallo = corregirMock(registro, (cuerpo?.textos as { indice: number; texto: string }[]) ?? []);
    return fallo ? error(422, "correccion_invalida", fallo) : vista();
  }
  if (verbo === "aclaracion") {
    const nota = texto(cuerpo?.nota);
    if (!nota) return error(422, "peticion_invalida", "La nota no puede quedar vacía.");
    aclararMock(registro, nota, texto(cuerpo?.pagina) || null);
    return vista();
  }
  if (verbo === "descartar") {
    registro.final ??= "descartada";
    return vista();
  }
  if (verbo === "aprobar") {
    const autor = texto(cuerpo?.autor);
    if (!autor) return error(422, "peticion_invalida", "Escribe quién aprueba el cambio.");
    const fallo = aprobarMock(registro, autor);
    return fallo ? error(409, "propuesta_no_aprobable", fallo) : vista();
  }
  return vista();
}

export function responderDocumentacion(metodo: "GET" | "POST", ruta: string[], cuerpo: Cuerpo): Response {
  const [recurso, ...resto] = ruta;
  if (recurso === "grupos") return grupos(metodo, resto);
  if (recurso === "propuestas" && resto.length === 0 && metodo === "POST") return nuevaPropuesta(cuerpo);
  if (recurso === "propuestas" && resto[0]) return accion(resto[0], resto[1], cuerpo);
  return error(404, "no_encontrado", "No encontrado");
}

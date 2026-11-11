/**
 * GET /capacidades: el contrato real del backend (`backend/app/schemas/sistema.py`) y su adaptación a lo que muestra
 * la bienvenida del chat. Las tarjetas son textos de interfaz; los datos (tableros y ejemplos) vienen del backend.
 */
import type { Capacidades, CapacidadesApi } from "./tipos";

const TARJETA_CIFRAS = {
  titulo: "Cifras de los tableros",
  descripcion: "Indicadores de los tableros de Power BI institucionales, con los filtros que necesites.",
};
const TARJETAS_FIJAS = [
  { titulo: "Qué significa cada indicador", descripcion: "Definiciones tomadas de la documentación de los tableros." },
  { titulo: "Ir directo a Power BI", descripcion: "Un enlace a la página del tablero donde está el dato." },
];

/** Contenido de respaldo si GET /capacidades no responde o el motor aún no está listo. */
export const CAPACIDADES_RESPALDO: Capacidades = {
  capacidades: [TARJETA_CIFRAS, ...TARJETAS_FIJAS],
  ejemplos: [
    { texto: "¿Cuántos egresos hubo el mes pasado?" },
    { texto: "¿Qué indicadores tiene el tablero quirúrgico?" },
  ],
};

const textos = (valor: unknown): string[] =>
  Array.isArray(valor) ? valor.filter((t): t is string => typeof t === "string" && t.trim() !== "") : [];

export function capacidadesDesdeApi(respuesta: Partial<CapacidadesApi> | null | undefined): Capacidades {
  const tableros = textos(respuesta?.tableros_datos);
  const ejemplos = textos(respuesta?.ejemplos).map((texto) => ({ texto }));
  const cifras = tableros.length
    ? {
        ...TARJETA_CIFRAS,
        descripcion: `Indicadores de ${tableros.length} tableros de Power BI institucionales, con los filtros que necesites.`,
      }
    : TARJETA_CIFRAS;
  return {
    capacidades: [cifras, ...TARJETAS_FIJAS],
    ejemplos: ejemplos.length ? ejemplos : CAPACIDADES_RESPALDO.ejemplos,
  };
}

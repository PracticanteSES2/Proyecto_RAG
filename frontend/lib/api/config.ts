/**
 * Configuración de acceso a la API.
 *
 * - `NEXT_PUBLIC_API_URL`: URL base del backend FastAPI (por defecto http://localhost:8000).
 * - `NEXT_PUBLIC_API_MOCK=1`: usa el mock que vive en las rutas de Next (`app/api/v1/**`) del mismo origen.
 *
 * Next sustituye `process.env.NEXT_PUBLIC_*` en el build: deben leerse con el nombre literal.
 */

export const URL_API_POR_DEFECTO = "http://localhost:8000";

export function mockActivo(valor: string | undefined = process.env.NEXT_PUBLIC_API_MOCK): boolean {
  return valor === "1" || valor === "true";
}

export function urlBaseApi(
  url: string | undefined = process.env.NEXT_PUBLIC_API_URL,
  mock: boolean = mockActivo(),
): string {
  if (mock) return "";
  return (url && url.trim() ? url.trim() : URL_API_POR_DEFECTO).replace(/\/+$/, "");
}

export const PREFIJO_API = "/api/v1";

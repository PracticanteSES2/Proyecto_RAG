/** Utilidades de las rutas del mock (app/api/v1/**). */
import { mockActivo } from "@/lib/api/config";

/** Las rutas del mock solo responden con NEXT_PUBLIC_API_MOCK=1; si no, 404 (el backend real es otro origen). */
export function mockApagado(): Response | null {
  return mockActivo() ? null : Response.json({ detail: "Mock desactivado" }, { status: 404 });
}

export const noEncontrado = () => Response.json({ detail: "No encontrado" }, { status: 404 });

export const esperar = (ms: number, senal: AbortSignal) =>
  new Promise<void>((resolver) => {
    if (ms <= 0 || senal.aborted) return resolver();
    const temporizador = setTimeout(resolver, ms);
    senal.addEventListener("abort", () => {
      clearTimeout(temporizador);
      resolver();
    }, { once: true });
  });

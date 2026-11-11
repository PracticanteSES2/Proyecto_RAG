import { mockApagado } from "@/lib/mock/http";
import { responderDocumentacion } from "@/lib/mock/rutasDocumentacion";

type Contexto = { params: Promise<{ ruta: string[] }> };

/** Mock de `/api/v1/documentacion/**` (solo con NEXT_PUBLIC_API_MOCK=1). */
export async function GET(_peticion: Request, { params }: Contexto) {
  return mockApagado() ?? responderDocumentacion("GET", (await params).ruta, null);
}

export async function POST(peticion: Request, { params }: Contexto) {
  const apagado = mockApagado();
  if (apagado) return apagado;
  const cuerpo = (await peticion.json().catch(() => null)) as Record<string, unknown> | null;
  return responderDocumentacion("POST", (await params).ruta, cuerpo);
}

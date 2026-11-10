import type { SolicitudCalificacion } from "@/lib/api/tipos";
import { almacen } from "@/lib/mock/almacen";
import { mockApagado, noEncontrado } from "@/lib/mock/http";

export async function POST(peticion: Request, { params }: { params: Promise<{ turnoId: string }> }) {
  const apagado = mockApagado();
  if (apagado) return apagado;
  const turno = almacen().turnos.get((await params).turnoId);
  if (!turno) return noEncontrado();
  const cuerpo = (await peticion.json().catch(() => null)) as SolicitudCalificacion | null;
  if (!cuerpo || (cuerpo.valor !== "buena" && cuerpo.valor !== "mala")) {
    return Response.json({ detail: "valor inválido" }, { status: 422 });
  }
  turno.calificacion = { valor: cuerpo.valor, comentario: cuerpo.comentario?.trim() || undefined };
  return new Response(null, { status: 204 });
}

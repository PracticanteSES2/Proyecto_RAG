import type { SolicitudTurno } from "@/lib/api/tipos";
import { crearTurno } from "@/lib/mock/almacen";
import { debeSaturar } from "@/lib/mock/guiones";
import { mockApagado, noEncontrado } from "@/lib/mock/http";

export async function POST(peticion: Request, { params }: { params: Promise<{ id: string }> }) {
  const apagado = mockApagado();
  if (apagado) return apagado;
  const cuerpo = (await peticion.json().catch(() => null)) as SolicitudTurno | null;
  if (!cuerpo || typeof cuerpo.mensaje !== "string" || !cuerpo.mensaje.trim()) {
    return Response.json({ detail: "mensaje requerido" }, { status: 422 });
  }
  if (debeSaturar(cuerpo.mensaje)) {
    return Response.json({ detail: "Demasiadas consultas" }, { status: 429, headers: { "Retry-After": "5" } });
  }
  const turno = crearTurno((await params).id, cuerpo.mensaje.trim(), !!cuerpo.diagnostico, cuerpo.opcion_id);
  return turno ? Response.json({ turno_id: turno.turnoId }, { status: 202 }) : noEncontrado();
}

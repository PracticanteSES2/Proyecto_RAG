import { almacen } from "@/lib/mock/almacen";
import { mockApagado } from "@/lib/mock/http";

export function GET() {
  const apagado = mockApagado();
  if (apagado) return apagado;
  return almacen().caido
    ? Response.json({ detail: "Servicio no disponible" }, { status: 503 })
    : Response.json({ estado: "ok" });
}

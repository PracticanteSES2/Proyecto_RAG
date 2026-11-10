import { almacen } from "@/lib/mock/almacen";
import { mockApagado } from "@/lib/mock/http";

/** Solo mock: `POST /api/v1/mock/caida?activa=1|0` simula que el backend está caído (para ver el aviso). */
export function POST(peticion: Request) {
  const apagado = mockApagado();
  if (apagado) return apagado;
  almacen().caido = new URL(peticion.url).searchParams.get("activa") !== "0";
  return Response.json({ caido: almacen().caido });
}

import { crearConversacion } from "@/lib/mock/almacen";
import { mockApagado } from "@/lib/mock/http";

export function POST() {
  return mockApagado() ?? Response.json({ conversacion_id: crearConversacion() }, { status: 201 });
}

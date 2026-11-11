import { historialMock } from "@/lib/mock/almacen";
import { mockApagado, noEncontrado } from "@/lib/mock/http";

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const apagado = mockApagado();
  if (apagado) return apagado;
  const conversacion = historialMock((await params).id);
  return conversacion ? Response.json(conversacion) : noEncontrado();
}

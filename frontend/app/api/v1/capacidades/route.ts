import { CAPACIDADES_MOCK } from "@/lib/mock/almacen";
import { mockApagado } from "@/lib/mock/http";

export function GET() {
  return mockApagado() ?? Response.json(CAPACIDADES_MOCK);
}

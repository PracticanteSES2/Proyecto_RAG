import { exportarMarkdown } from "@/lib/mock/almacen";
import { mockApagado, noEncontrado } from "@/lib/mock/http";

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const apagado = mockApagado();
  if (apagado) return apagado;
  const id = (await params).id;
  const texto = exportarMarkdown(id);
  if (texto === null) return noEncontrado();
  return new Response(texto, {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Content-Disposition": `attachment; filename="conversacion-${id}.md"`,
    },
  });
}

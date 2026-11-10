import { almacen } from "@/lib/mock/almacen";
import { formatearSSE, pasosDesde } from "@/lib/mock/guiones";
import { esperar, mockApagado, noEncontrado } from "@/lib/mock/http";

/** SSE del turno: emite cada paso del guion a su hora, reanudando tras `Last-Event-ID`. */
export async function GET(peticion: Request, { params }: { params: Promise<{ turnoId: string }> }) {
  const apagado = mockApagado();
  if (apagado) return apagado;
  const turno = almacen().turnos.get((await params).turnoId);
  if (!turno) return noEncontrado();
  const ultimoId = Number(peticion.headers.get("Last-Event-ID") ?? 0) || 0;
  const senal = peticion.signal;
  const codificador = new TextEncoder();

  const flujo = new ReadableStream<Uint8Array>({
    async start(controlador) {
      controlador.enqueue(codificador.encode("retry: 1500\n\n"));
      for (const { id, paso } of pasosDesde(turno.guion, ultimoId)) {
        await esperar(turno.inicio + paso.ms - Date.now(), senal);
        if (senal.aborted) break;
        controlador.enqueue(codificador.encode(formatearSSE(id, paso.evento)));
      }
      controlador.close();
    },
  });

  return new Response(flujo, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

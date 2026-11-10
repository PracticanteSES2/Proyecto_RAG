import { vi } from "vitest";
import type { EventoRespuesta } from "@/lib/api/tipos";
import type { MensajeAsistente as TipoMensajeAsistente } from "@/lib/chat/reductor";
import { estadoInicialTurno, reducirTurno, type AccionTurno } from "@/lib/turno/maquina";

export const mensaje = (acciones: AccionTurno[], extra: Partial<TipoMensajeAsistente> = {}): TipoMensajeAsistente => ({
  id: "a1",
  rol: "asistente",
  solicitud: { mensaje: "¿Egresos?" },
  diagnostico: false,
  turno: acciones.reduce(reducirTurno, estadoInicialTurno()),
  ...extra,
});

export const respuesta = (extra: Partial<EventoRespuesta> = {}): AccionTurno => ({
  tipo: "evento",
  evento: {
    tipo: "respuesta",
    datos: {
      turno_id: "t1",
      texto_markdown:
        "Hubo **1.284** egresos.\n\n| Servicio | Egresos |\n|---|---:|\n| UCI | 112 |\n\n<script>alert(1)</script>\n\n[malo](javascript:alert(1))",
      ruta: "powerbi",
      fuentes: [{ titulo: "Egresos hospitalarios", pagina: "Resumen" }],
      enlaces_powerbi: [{ titulo: "Egresos · Resumen", url: "https://app.powerbi.com/x" }],
      degradada: false,
      ...extra,
    },
  },
});

export const props = {
  diagnostico: false,
  contrapreguntaActiva: false,
  ocupado: false,
  alElegirOpcion: vi.fn(),
  alReintentar: vi.fn(),
  alCalificar: vi.fn(),
};

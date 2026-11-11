import type { ProgresoPropuesta } from "@/lib/api/tiposDocumentacion";
import { IndicadorPensando } from "@/components/chat/IndicadorPensando";
import { Mascota } from "@/components/ui/Mascota";

/**
 * Mientras MedGemma prepara la propuesta: el mismo indicador del chat, con la frase de la etapa real y, si tarda,
 * la frase de espera. Nunca se habla de colas, otras personas ni saturación (lo garantiza el backend).
 */
export function EsperaPropuesta({ nota, progreso }: { nota: string; progreso: ProgresoPropuesta | null }) {
  return (
    <section
      aria-label="Preparando la propuesta"
      className="entrada flex items-start gap-4 rounded-lg bg-surface-2 p-4"
    >
      <Mascota variante="pensando" alto={64} />
      <div className="min-w-0 flex-1">
        <p className="mb-2 truncate text-sm text-fg-muted">Tu nota: «{nota}»</p>
        <IndicadorPensando frase={progreso?.frase ?? "Leyendo tu nota"} fraseEspera={progreso?.espera ?? undefined} />
      </div>
    </section>
  );
}

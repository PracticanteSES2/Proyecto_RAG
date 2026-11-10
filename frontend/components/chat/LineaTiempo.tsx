import type { EtapaRegistrada } from "@/lib/turno/maquina";

interface Props {
  etapas: EtapaRegistrada[];
  /** Segundos totales (reloj del cliente). */
  segundos: number;
  enCurso?: boolean;
}

const formatear = (s: number) => `${s.toLocaleString("es-CO", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;

/** Línea de tiempo de etapas con segundos. SOLO para el modo diagnóstico. */
export function LineaTiempo({ etapas, segundos, enCurso = false }: Props) {
  return (
    <div className="mt-2 rounded-md border-l-[3px] border-diag-border bg-diag-bg px-3 py-2 text-xs text-fg" aria-label="Línea de tiempo del turno">
      <ol className="space-y-0.5 font-mono">
        {etapas.map((e, i) => {
          const fin = etapas[i + 1]?.t ?? (enCurso ? undefined : segundos);
          return (
            <li key={`${e.etapa}-${e.t}`} className="flex gap-3">
              <span className="w-14 shrink-0 text-right tabular-nums text-diag">{formatear(e.t)}</span>
              <span className="min-w-0 flex-1 truncate">
                {e.etapa}
                <span className="text-fg-muted"> · {e.frase}</span>
              </span>
              {fin !== undefined && <span className="shrink-0 tabular-nums text-fg-muted">+{formatear(Math.max(0, fin - e.t))}</span>}
            </li>
          );
        })}
      </ol>
      <p className="mt-1 font-mono tabular-nums text-diag">
        {enCurso ? "Transcurrido" : "Total"}: {formatear(segundos)}
      </p>
    </div>
  );
}

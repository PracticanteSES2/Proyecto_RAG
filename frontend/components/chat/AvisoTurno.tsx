import type { FaseTurno } from "@/lib/turno/maquina";
import { IconoReintentar } from "@/components/ui/Iconos";
import { Mascota } from "@/components/ui/Mascota";

type FaseProblema = Extract<FaseTurno, "error" | "saturado" | "fallo_envio" | "desconectado" | "detenido">;

export const TEXTOS_PROBLEMA: Record<FaseProblema, string> = {
  saturado: "Hay muchas consultas en este momento. Intenta de nuevo en unos segundos.",
  error: "No pude completar esta consulta. Puedes intentarlo de nuevo en un momento.",
  fallo_envio: "No logré comunicarme con el asistente. Revisa tu conexión e intenta de nuevo.",
  desconectado: "Se interrumpió la conexión mientras preparaba tu respuesta.",
  detenido: "Detuviste esta consulta.",
};

export function esFaseProblema(fase: FaseTurno): fase is FaseProblema {
  return fase in TEXTOS_PROBLEMA;
}

interface Props {
  fase: FaseProblema;
  alReintentar?: () => void;
  puedeReintentar: boolean;
}

/** Aviso amable (sin jerga técnica) cuando un turno no termina en respuesta. */
export function AvisoTurno({ fase, alReintentar, puedeReintentar }: Props) {
  const detenido = fase === "detenido";
  const tono = detenido
    ? "text-fg-muted"
    : fase === "error"
      ? "border-l-[3px] border-danger-border bg-danger-bg text-fg"
      : "border-l-[3px] border-warning-border bg-warning-bg text-fg";
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md px-4 py-3 ${tono}`}>
      <p className="flex min-w-0 flex-1 items-center gap-3">
        {!detenido && <Mascota variante={fase === "saturado" ? "pensando" : "sin_resultados"} alto={52} />}
        <span>{TEXTOS_PROBLEMA[fase]}</span>
      </p>
      {alReintentar && (
        <button
          type="button"
          onClick={alReintentar}
          disabled={!puedeReintentar}
          className="inline-flex items-center gap-1.5 rounded-pill border border-border-strong bg-surface px-3 py-1.5 text-sm font-semibold text-fg transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <IconoReintentar tamano={14} />
          {detenido ? "Volver a preguntar" : "Reintentar"}
        </button>
      )}
    </div>
  );
}

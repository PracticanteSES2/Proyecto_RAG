import { IconoReintentar } from "@/components/ui/Iconos";
import { Mascota } from "@/components/ui/Mascota";

/** Aviso amable cuando GET /salud falla. Se reintenta solo; el botón permite comprobar ya. */
export function AvisoServidor({ alReintentar }: { alReintentar: () => void }) {
  return (
    <div role="alert" className="entrada border-b border-warning-border bg-warning-bg">
      <div className="mx-auto flex max-w-[var(--chat-max-width)] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 text-sm text-warning">
        <Mascota variante="pensando" alto={40} />
        <p className="min-w-0 flex-1">
          <strong className="font-semibold">No logramos comunicarnos con el asistente.</strong> Puede estar
          reiniciándose; lo intentaremos de nuevo en unos segundos.
        </p>
        <button
          type="button"
          onClick={alReintentar}
          className="inline-flex items-center gap-1.5 rounded-pill border border-warning-border bg-surface px-3 py-1 font-semibold text-fg hover:bg-surface-2"
        >
          <IconoReintentar tamano={14} />
          Comprobar ahora
        </button>
      </div>
    </div>
  );
}

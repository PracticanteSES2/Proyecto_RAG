import type { Contrapregunta as TipoContrapregunta } from "@/lib/api/tipos";
import { IconoCheck, IconoChevron } from "@/components/ui/Iconos";

interface Props {
  contrapregunta: TipoContrapregunta;
  /** Solo la última contrapregunta sin responder admite elección. */
  activa: boolean;
  elegida?: string;
  alElegir: (id: string, texto: string) => void;
}

/** Opciones de una contrapregunta como tarjetas pulsables (envían `opcion_id`). */
export function Contrapregunta({ contrapregunta, activa, elegida, alElegir }: Props) {
  return (
    <fieldset className="mt-3">
      <legend className="mb-2 text-sm font-semibold text-fg-heading">{contrapregunta.pregunta}</legend>
      <ul className="grid gap-2 sm:grid-cols-2">
        {contrapregunta.opciones.map((opcion) => {
          const esElegida = elegida === opcion.id;
          const estilo = esElegida
            ? "border-primary bg-surface-3 ring-1 ring-primary"
            : activa
              ? "border-info-border bg-surface hover:border-primary hover:bg-surface-3 hover:shadow-md"
              : "border-border bg-surface opacity-60";
          return (
            <li key={opcion.id}>
              <button
                type="button"
                disabled={!activa}
                aria-pressed={esElegida}
                onClick={() => alElegir(opcion.id, opcion.texto)}
                className={`group flex h-full w-full items-start gap-3 rounded-md border px-4 py-3 text-left transition-[background-color,border-color,box-shadow] duration-200 disabled:cursor-default ${estilo}`}
              >
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold text-link">{opcion.texto}</span>
                  {opcion.descripcion && (
                    <span className="mt-0.5 block text-sm text-fg-muted">{opcion.descripcion}</span>
                  )}
                </span>
                <span className="mt-0.5 shrink-0 text-link" aria-hidden="true">
                  {esElegida ? (
                    <IconoCheck tamano={18} />
                  ) : activa ? (
                    <IconoChevron
                      tamano={18}
                      className="transition-transform duration-200 group-hover:translate-x-0.5"
                    />
                  ) : null}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}

import type { OperacionPropuesta } from "@/lib/api/tiposDocumentacion";
import { Markdown } from "@/components/chat/Markdown";

interface Props {
  operaciones: OperacionPropuesta[];
  ediciones: Record<number, string>;
  alEditar: (indice: number, texto: string) => void;
  deshabilitado: boolean;
}

/** «Cambios propuestos»: qué hace cada operación, el texto actual y el texto nuevo (corregible salvo al quitar). */
export function OperacionesPropuesta({ operaciones, ediciones, alEditar, deshabilitado }: Props) {
  return (
    <section aria-labelledby="titulo-operaciones" className="space-y-3">
      <h3 id="titulo-operaciones" className="text-base font-semibold">
        Cambios propuestos
      </h3>
      <ol className="space-y-3">
        {operaciones.map((op) => (
          <li key={op.indice} className="rounded-md border border-border bg-surface p-3">
            <div className="flex gap-2 text-sm">
              <span className="font-semibold text-fg-muted">{op.indice + 1}.</span>
              <Markdown texto={op.descripcion} />
            </div>
            {op.texto_actual && op.accion !== "agregar" && (
              <div className="mt-2">
                <p className="text-xs font-semibold text-fg-muted">Texto actual</p>
                <blockquote className="mt-1 border-l-2 border-border-strong pl-3 text-sm text-fg">
                  {op.texto_actual}
                </blockquote>
              </div>
            )}
            {op.editable && (
              <label className="mt-3 block">
                <span className="text-xs font-semibold text-fg-muted">
                  Texto nuevo (puedes corregirlo antes de aprobar)
                </span>
                <textarea
                  value={ediciones[op.indice] ?? op.texto}
                  onChange={(e) => alEditar(op.indice, e.target.value)}
                  disabled={deshabilitado}
                  rows={op.seccion.toLowerCase().startsWith("prop") ? 5 : 3}
                  className="mt-1 w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-fg"
                />
              </label>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

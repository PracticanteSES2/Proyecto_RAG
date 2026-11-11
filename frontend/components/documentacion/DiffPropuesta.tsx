import { Fragment } from "react";
import type { LineaDiff, Propuesta } from "@/lib/api/tiposDocumentacion";
import { CuerpoDocumento, Historial } from "./CuerpoDocumento";

/** Una línea del diff: `<del>`/`<ins>` con signo y texto para lectores de pantalla (legible sin color). */
function Linea({ linea }: { linea: LineaDiff }) {
  const contenido = linea.texto || " ";
  if (linea.tipo === "sale") {
    return (
      <del className="block border-l-4 border-danger-border bg-danger-bg px-2 py-px text-fg no-underline">
        <span aria-hidden="true">− </span>
        <span className="sr-only">Sale: </span>
        {contenido}
      </del>
    );
  }
  if (linea.tipo === "entra") {
    return (
      <ins className="block border-l-4 border-success-border bg-success-bg px-2 py-px text-fg no-underline">
        <span aria-hidden="true">+ </span>
        <span className="sr-only">Entra: </span>
        {contenido}
      </ins>
    );
  }
  return (
    <div className="border-l-4 border-transparent px-2 py-px text-fg-muted">
      <span aria-hidden="true">{"  "}</span>
      {contenido}
    </div>
  );
}

/** «Antes y después»: solo los tramos cambiados (calculados en el backend), vista previa y diff técnico. */
export function DiffPropuesta({ propuesta }: { propuesta: Propuesta }) {
  const { diff, vista_previa: vistaPrevia } = propuesta;
  if (!diff) return null;
  return (
    <section aria-labelledby="titulo-diff" className="space-y-3">
      <h3 id="titulo-diff" className="text-base font-semibold">
        Antes y después
      </h3>
      <p className="text-xs text-fg-muted">
        <span className="font-semibold text-danger">− líneas que salen ({diff.eliminadas})</span> ·{" "}
        <span className="font-semibold text-success">+ líneas que entran ({diff.agregadas})</span>. La versión y el
        historial los actualiza el sistema.
      </p>
      {diff.bloques.length === 0 ? (
        <p className="text-sm text-fg-muted">No hay diferencias.</p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-border bg-surface py-1 font-mono text-xs whitespace-pre-wrap">
          {diff.bloques.map((bloque, b) => (
            <Fragment key={`bloque-${b}`}>
              {b > 0 && (
                <div className="py-1 text-center text-fg-muted" aria-hidden="true">
                  ⋯
                </div>
              )}
              <div role="group" aria-label={`Tramo ${b + 1}`}>
                {bloque.lineas.map((linea, n) => (
                  <Linea key={`${b}-${n}`} linea={linea} />
                ))}
              </div>
            </Fragment>
          ))}
        </div>
      )}
      {vistaPrevia && (
        <details className="rounded-md border border-border px-4 py-2">
          <summary className="cursor-pointer text-sm font-semibold text-fg">Ver la página como quedaría</summary>
          <div className="mt-3 space-y-4">
            <CuerpoDocumento cuerpo={vistaPrevia.cuerpo} />
            <h3 className="text-base font-semibold">Historial de cambios</h3>
            <Historial entradas={vistaPrevia.historial} />
          </div>
        </details>
      )}
      <details className="rounded-md border border-border px-4 py-2">
        <summary className="cursor-pointer text-sm font-semibold text-fg">Diff unificado (técnico)</summary>
        <pre className="mt-2 max-h-80 overflow-auto rounded-sm bg-surface-code p-3 font-mono text-xs text-fg">
          {diff.unificado}
        </pre>
      </details>
    </section>
  );
}

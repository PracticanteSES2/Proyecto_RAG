import type { DocumentoPagina } from "@/lib/api/tiposDocumentacion";
import { Aviso } from "@/components/ui/Aviso";
import { Boton } from "@/components/ui/Boton";
import { IconoCheck } from "@/components/ui/Iconos";
import { IconoHistorial, IconoLapiz } from "@/components/ui/IconosDocumentacion";
import { CuerpoDocumento, Historial } from "./CuerpoDocumento";

interface Props {
  documento: DocumentoPagina;
  alProponer: () => void;
}

/** Documento de una página: estado del formato, ficha, cuerpo, historial y el .md tal como está guardado. */
export function VistaDocumento({ documento, alProponer }: Props) {
  return (
    <article aria-labelledby="titulo-documento" className="space-y-5">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-[14rem] flex-1">
          <p className="text-xs font-semibold tracking-wide text-fg-muted uppercase">{documento.tablero}</p>
          <h2 id="titulo-documento" className="text-xl font-semibold sm:text-2xl">
            {documento.pagina}
          </h2>
        </div>
        <Boton variante="primario" onClick={alProponer}>
          <IconoLapiz tamano={16} />
          Proponer un cambio en esta página
        </Boton>
      </div>

      {documento.valido ? (
        <p className="inline-flex items-center gap-1.5 rounded-pill bg-success-bg px-3 py-1 text-xs font-semibold text-success">
          <IconoCheck tamano={14} />
          Formato válido
        </p>
      ) : (
        <Aviso
          tono="aviso"
          titulo={
            documento.interpretable
              ? "Formato con problemas. La página se muestra, pero conviene corregirla:"
              : "Formato con problemas. No se pudo interpretar la página."
          }
        >
          <ul className="list-disc pl-5">
            {documento.errores_formato.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </Aviso>
      )}

      {documento.interpretable && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <CuerpoDocumento cuerpo={documento.cuerpo} />
          <aside aria-labelledby="titulo-ficha" className="space-y-6 lg:order-none">
            <section className="rounded-lg border border-border bg-surface p-4">
              <h3 id="titulo-ficha" className="mb-3 text-base font-semibold">
                Ficha de la página
              </h3>
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
                {documento.ficha.map((f) => (
                  <div key={f.dato} className="contents">
                    <dt className="text-fg-muted">{f.dato}</dt>
                    <dd className="font-semibold break-words text-fg">{f.valor}</dd>
                  </div>
                ))}
              </dl>
            </section>
            <section aria-labelledby="titulo-historial">
              <h3 id="titulo-historial" className="mb-3 flex items-center gap-2 text-base font-semibold">
                <IconoHistorial tamano={16} />
                Historial de cambios
              </h3>
              <Historial entradas={documento.historial} />
            </section>
          </aside>
        </div>
      )}

      <details className="rounded-md border border-border bg-surface-2 px-4 py-2" open={!documento.interpretable}>
        <summary className="cursor-pointer text-sm font-semibold text-fg">
          Ver el archivo .md tal como está guardado
        </summary>
        <p className="mt-2 text-xs text-fg-muted">{documento.ruta}</p>
        <pre className="mt-2 max-h-96 overflow-auto rounded-sm bg-surface-code p-3 font-mono text-xs whitespace-pre-wrap text-fg">
          {documento.texto}
        </pre>
      </details>
    </article>
  );
}

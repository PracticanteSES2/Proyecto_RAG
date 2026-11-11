import type { CuerpoDocumento as Cuerpo, EntradaDocumento } from "@/lib/api/tiposDocumentacion";
import { Markdown } from "@/components/chat/Markdown";

/** Entradas «**nombre**: texto» de una sección (el texto es Markdown saneado). */
export function ListaEntradas({ entradas }: { entradas: EntradaDocumento[] }) {
  return (
    <ul className="space-y-2">
      {entradas.map((e) => (
        <li key={e.nombre} className="rounded-md bg-surface-2 px-3 py-2">
          <p className="text-sm font-semibold text-fg-heading">{e.nombre}</p>
          <Markdown texto={e.texto} />
        </li>
      ))}
    </ul>
  );
}

/** Propósito y secciones de una página (sin metadatos ni historial). */
export function CuerpoDocumento({ cuerpo }: { cuerpo: Cuerpo }) {
  return (
    <div className="space-y-5">
      <section aria-label="Propósito">
        <h3 className="mb-2 text-base font-semibold">Propósito</h3>
        {cuerpo.proposito ? <Markdown texto={cuerpo.proposito} /> : <p className="text-fg-muted">(vacío)</p>}
      </section>
      {cuerpo.secciones.map((s) => (
        <section key={s.titulo} aria-label={s.titulo}>
          <h3 className="mb-2 text-base font-semibold">{s.titulo}</h3>
          <ListaEntradas entradas={s.entradas} />
        </section>
      ))}
    </div>
  );
}

/** Historial de cambios, el más reciente primero (como lo entrega el backend). */
export function Historial({ entradas }: { entradas: EntradaDocumento[] }) {
  if (entradas.length === 0) return <p className="text-sm text-fg-muted">Sin cambios registrados.</p>;
  return (
    <ol className="space-y-2 border-l-2 border-border pl-4">
      {entradas.map((e) => (
        <li key={e.nombre} className="text-sm">
          <p className="font-semibold text-fg">{e.nombre}</p>
          <p className="text-fg-muted">{e.texto}</p>
        </li>
      ))}
    </ol>
  );
}

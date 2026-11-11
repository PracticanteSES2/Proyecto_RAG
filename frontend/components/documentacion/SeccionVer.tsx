"use client";

import type { ClienteDocumentacion } from "@/lib/api/documentacion";
import type { PaginaResumen } from "@/lib/api/tiposDocumentacion";
import { useDocumento } from "@/hooks/useDocumento";
import { Aviso } from "@/components/ui/Aviso";
import { Mascota } from "@/components/ui/Mascota";
import { VistaDocumento } from "./VistaDocumento";

interface Props {
  cliente: ClienteDocumentacion;
  grupo: string;
  archivo: string | null;
  paginas: PaginaResumen[];
  revision: number;
  alElegir: (archivo: string) => void;
  alProponer: (pagina: string) => void;
}

/** Pestaña «Ver documentación»: el documento elegido o, sin página, la lista de páginas del tablero. */
export function SeccionVer({ cliente, grupo, archivo, paginas, revision, alElegir, alProponer }: Props) {
  const { documento, error, cargando } = useDocumento(cliente, grupo, archivo, revision);

  if (!archivo) {
    if (paginas.length === 0) {
      return (
        <div className="flex items-center gap-4 text-fg-muted">
          <Mascota variante="sin_resultados" alto={72} />
          <p>Este tablero todavía no tiene páginas documentadas.</p>
        </div>
      );
    }
    return (
      <section aria-label="Páginas del tablero" className="space-y-3">
        <p className="text-sm text-fg-muted">Elige una página para ver su documentación.</p>
        <ul className="grid gap-2 sm:grid-cols-2">
          {paginas.map((p) => (
            <li key={p.archivo}>
              <button
                type="button"
                onClick={() => alElegir(p.archivo)}
                className="h-full w-full rounded-md border border-border bg-surface px-3 py-2 text-left transition-colors hover:border-primary hover:bg-surface-2"
              >
                <span className="block text-sm font-semibold text-fg-heading">
                  {p.general ? "General del tablero" : p.pagina}
                </span>
                {p.nombre_funcional && <span className="block text-xs text-fg-muted">{p.nombre_funcional}</span>}
              </button>
            </li>
          ))}
        </ul>
      </section>
    );
  }
  if (error) return <Aviso tono="error" titulo={error} />;
  if (cargando || !documento) {
    return (
      <p role="status" className="text-sm text-fg-muted">
        Abriendo la página…
      </p>
    );
  }
  return <VistaDocumento documento={documento} alProponer={() => alProponer(documento.pagina)} />;
}

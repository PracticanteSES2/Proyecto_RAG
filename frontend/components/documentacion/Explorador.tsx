"use client";

import { useId, useState } from "react";
import type { GrupoDocumentacion, PaginaResumen } from "@/lib/api/tiposDocumentacion";
import { filtrarExplorador } from "@/lib/documentacion/estado";
import { IconoTablero } from "@/components/ui/Iconos";
import { IconoBuscar } from "@/components/ui/IconosDocumentacion";

interface Props {
  grupos: GrupoDocumentacion[];
  paginas: Record<string, PaginaResumen[]>;
  seleccion: { grupo: string; archivo: string | null } | null;
  alElegir: (grupo: string, archivo: string | null) => void;
}

/** Tableros y sus páginas con búsqueda (nombre, nombre funcional o archivo; sin importar tildes). */
export function Explorador({ grupos, paginas, seleccion, alElegir }: Props) {
  const [busqueda, setBusqueda] = useState("");
  const idBusqueda = useId();
  const resultados = filtrarExplorador(grupos, paginas, busqueda);
  const buscando = busqueda.trim().length > 0;

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <label htmlFor={idBusqueda} className="sr-only">
        Buscar tablero o página
      </label>
      <div className="relative">
        <IconoBuscar
          tamano={16}
          className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-fg-muted"
        />
        <input
          id={idBusqueda}
          type="search"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          placeholder="Buscar tablero o página"
          className="h-10 w-full rounded-pill border border-border-strong bg-surface pr-3 pl-9 text-sm text-fg placeholder:text-fg-muted"
        />
      </div>
      <p className="sr-only" aria-live="polite">
        {buscando ? `${resultados.length} tableros coinciden` : ""}
      </p>
      {resultados.length === 0 && <p className="px-1 text-sm text-fg-muted">Ningún tablero ni página coincide.</p>}
      <ul className="min-h-0 space-y-1 overflow-y-auto pr-1">
        {resultados.map(({ grupo, paginas: lista }) => {
          const abierto = buscando || seleccion?.grupo === grupo.grupo;
          return (
            <li key={grupo.grupo}>
              <button
                type="button"
                onClick={() => alElegir(grupo.grupo, null)}
                aria-expanded={abierto}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm font-semibold transition-colors hover:bg-surface-2 ${
                  seleccion?.grupo === grupo.grupo ? "text-fg-heading" : "text-fg"
                }`}
              >
                <IconoTablero tamano={16} className="shrink-0 text-primary" />
                <span className="min-w-0 flex-1 truncate">{grupo.tablero}</span>
                <span className="shrink-0 text-xs font-normal text-fg-muted">{grupo.paginas}</span>
              </button>
              {abierto && (
                <ul className="mt-1 mb-2 ml-4 space-y-0.5 border-l border-border pl-2">
                  {lista.map((p) => {
                    const actual = seleccion?.grupo === grupo.grupo && seleccion.archivo === p.archivo;
                    return (
                      <li key={p.archivo}>
                        <button
                          type="button"
                          onClick={() => alElegir(grupo.grupo, p.archivo)}
                          aria-current={actual ? "page" : undefined}
                          title={p.etiqueta}
                          className={`w-full rounded-sm px-2 py-1.5 text-left text-sm transition-colors ${
                            actual ? "bg-surface-3 font-semibold text-fg-heading" : "text-fg hover:bg-surface-2"
                          }`}
                        >
                          <span className="block truncate">
                            {p.general ? "General del tablero" : p.pagina}
                            {!p.valido && <span className="ml-1 text-warning">(formato con problemas)</span>}
                          </span>
                          {p.nombre_funcional && (
                            <span className="block truncate text-xs text-fg-muted">{p.nombre_funcional}</span>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

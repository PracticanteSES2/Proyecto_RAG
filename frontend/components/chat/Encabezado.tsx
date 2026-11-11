import Image from "next/image";
import type { ReactNode } from "react";
import { IconoNueva } from "@/components/ui/IconosAjustes";
import { NavegacionPrincipal } from "@/components/ui/NavegacionPrincipal";

interface Props {
  diagnostico: boolean;
  puedeReiniciar: boolean;
  alNuevaConversacion: () => void;
  ajustes: ReactNode;
}

/** Filete de marca (cuatro colores del isotipo), identidad y acciones globales. */
export function Encabezado({ diagnostico, puedeReiniciar, alNuevaConversacion, ajustes }: Props) {
  return (
    <header className="shrink-0 bg-bg">
      <div className="h-1" style={{ background: "var(--gradient-marca)" }} aria-hidden="true" />
      <div className="border-b border-border">
        <div className="mx-auto flex h-16 max-w-5xl items-center gap-3 px-4">
          <Image
            src="/marca/isotipo_ses.svg"
            alt=""
            width={36}
            height={36}
            unoptimized
            priority
            className="size-9 shrink-0"
          />
          <div className="min-w-0 flex-1 leading-tight">
            <p className="flex items-center gap-2 font-heading text-base font-semibold text-fg-heading sm:text-lg">
              <span className="truncate">Asistente de tableros</span>
              {diagnostico && (
                <span className="shrink-0 rounded-pill border border-diag-border bg-diag-bg px-2 py-0.5 font-body text-xs font-bold text-diag">
                  Diagnóstico
                </span>
              )}
            </p>
            <p className="truncate text-xs text-fg-muted">
              S.E.S. Hospital Universitario de Caldas{" "}
              <span className="hidden sm:inline">· Queremos devolver sonrisas</span>
            </p>
          </div>
          <NavegacionPrincipal actual="chat" />
          <button
            type="button"
            onClick={alNuevaConversacion}
            disabled={!puedeReiniciar}
            className="inline-flex h-10 items-center gap-2 rounded-pill border border-border-strong px-3 text-sm font-semibold text-fg transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40 sm:px-4"
          >
            <IconoNueva tamano={16} />
            <span className="sr-only sm:not-sr-only">Nueva conversación</span>
          </button>
          {ajustes}
        </div>
      </div>
      {diagnostico && <div className="h-[3px] bg-diag-border" aria-hidden="true" />}
    </header>
  );
}

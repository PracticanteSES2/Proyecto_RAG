import Image from "next/image";
import { NavegacionPrincipal } from "@/components/ui/NavegacionPrincipal";

/** Encabezado de la documentación: el mismo filete de marca e identidad del chat, con la navegación. */
export function EncabezadoDocumentacion() {
  return (
    <header className="shrink-0 bg-bg">
      <div className="h-1" style={{ background: "var(--gradient-marca)" }} aria-hidden="true" />
      <div className="border-b border-border">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4">
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
            <h1 className="truncate font-heading text-base font-semibold text-fg-heading sm:text-lg">
              Documentación de tableros
            </h1>
            <p className="truncate text-xs text-fg-muted">
              Consulta cada página y propone cambios en lenguaje sencillo
              <span className="hidden sm:inline">; un cambio solo se guarda cuando lo apruebas</span>
            </p>
          </div>
          <NavegacionPrincipal actual="documentacion" />
        </div>
      </div>
    </header>
  );
}

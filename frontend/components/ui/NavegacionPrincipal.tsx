import Link from "next/link";
import { IconoDocumento } from "./Iconos";
import { IconoChat } from "./IconosDocumentacion";

type Seccion = "chat" | "documentacion";

const ENLACES = [
  { seccion: "chat", href: "/", texto: "Chat", Icono: IconoChat },
  { seccion: "documentacion", href: "/documentacion", texto: "Documentación", Icono: IconoDocumento },
] as const;

/**
 * «Chat · Documentación»: navegación entre las dos pantallas, con la actual marcada (`aria-current="page"`). En el
 * móvil queda solo el acceso a la otra pantalla, como botón con icono, para no robarle espacio al título.
 */
export function NavegacionPrincipal({ actual }: { actual: Seccion }) {
  const otra = ENLACES.find((e) => e.seccion !== actual)!;
  return (
    <nav aria-label="Secciones" className="shrink-0">
      <ul className="hidden items-center gap-1 rounded-pill bg-surface-2 p-1 text-sm md:flex">
        {ENLACES.map(({ seccion, href, texto }) => (
          <li key={seccion}>
            <Link
              href={href}
              aria-current={seccion === actual ? "page" : undefined}
              className={`inline-flex h-8 items-center rounded-pill px-3 font-semibold transition-colors ${
                seccion === actual ? "bg-surface text-fg-heading shadow-sm" : "text-fg-muted hover:text-fg"
              }`}
            >
              {texto}
            </Link>
          </li>
        ))}
      </ul>
      <Link
        href={otra.href}
        aria-label={`Ir a ${otra.texto}`}
        className="inline-flex size-10 items-center justify-center rounded-pill text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg md:hidden"
      >
        <otra.Icono tamano={20} />
      </Link>
    </nav>
  );
}

import type { GrupoDocumentacion, PaginaResumen } from "@/lib/api/tiposDocumentacion";
import { Aviso } from "@/components/ui/Aviso";
import { Boton } from "@/components/ui/Boton";
import { Explorador } from "./Explorador";

interface Props {
  grupos: GrupoDocumentacion[] | null;
  paginas: Record<string, PaginaResumen[]>;
  error: string | null;
  alReintentar: () => void;
  seleccion: { grupo: string; archivo: string | null } | null;
  alElegir: (grupo: string, archivo: string | null) => void;
}

/** Columna de tableros: cargando, error con reintento, vacío o el explorador. */
export function PanelTableros({ grupos, paginas, error, alReintentar, seleccion, alElegir }: Props) {
  let contenido;
  if (error) {
    contenido = (
      <Aviso tono="error" titulo={error}>
        <Boton className="mt-2" onClick={alReintentar}>
          Reintentar
        </Boton>
      </Aviso>
    );
  } else if (grupos === null) {
    contenido = (
      <p role="status" className="text-sm text-fg-muted">
        Cargando los tableros…
      </p>
    );
  } else if (grupos.length === 0) {
    contenido = (
      <p className="text-sm text-fg-muted">
        Todavía no hay tableros con documentación. Cada tablero guarda sus páginas en docs_tableros/&lt;grupo&gt;/md/.
      </p>
    );
  } else {
    contenido = <Explorador grupos={grupos} paginas={paginas} seleccion={seleccion} alElegir={alElegir} />;
  }
  return (
    <aside
      aria-label="Tableros"
      className="max-h-80 overflow-y-auto md:sticky md:top-4 md:max-h-[calc(100dvh-7rem)] md:self-start"
    >
      {contenido}
    </aside>
  );
}

import type { GrupoDocumentacion, PaginaResumen } from "@/lib/api/tiposDocumentacion";
import type { usePropuesta } from "@/hooks/usePropuesta";
import { Aviso } from "@/components/ui/Aviso";
import { FormularioPropuesta } from "./FormularioPropuesta";
import { PanelPropuesta } from "./PanelPropuesta";

interface Props {
  grupo: GrupoDocumentacion;
  paginas: PaginaResumen[];
  paginaInicial: string;
  autor: string;
  alCambiarAutor: (autor: string) => void;
  propuestas: ReturnType<typeof usePropuesta>;
}

/** Pestaña «Proponer un cambio»: formulario y, debajo, la propuesta del tablero en su estado actual. */
export function SeccionProponer({ grupo, paginas, paginaInicial, autor, alCambiarAutor, propuestas }: Props) {
  const { propuesta } = propuestas;
  return (
    <div className="space-y-5">
      <FormularioPropuesta
        key={`${grupo.grupo}|${paginaInicial}`}
        grupo={grupo.grupo}
        tablero={grupo.tablero}
        paginas={paginas}
        paginaInicial={paginaInicial}
        autor={autor}
        alCambiarAutor={alCambiarAutor}
        ocupado={propuestas.enviando || propuesta?.estado === "preparando"}
        alEnviar={(s) => void propuestas.proponer(s)}
      />
      {propuestas.error && <Aviso tono="error" titulo={propuestas.error} />}
      {propuesta && propuesta.grupo === grupo.grupo && (
        <PanelPropuesta
          propuesta={propuesta}
          autor={autor}
          alCambiarAutor={alCambiarAutor}
          ocupado={propuestas.enviando}
          acciones={propuestas}
        />
      )}
    </div>
  );
}

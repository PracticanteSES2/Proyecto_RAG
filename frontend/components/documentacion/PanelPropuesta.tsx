import type { Propuesta, SolicitudAclaracion } from "@/lib/api/tiposDocumentacion";
import { Aviso } from "@/components/ui/Aviso";
import { Boton } from "@/components/ui/Boton";
import { Mascota } from "@/components/ui/Mascota";
import { AclaracionPropuesta } from "./AclaracionPropuesta";
import { EsperaPropuesta } from "./EsperaPropuesta";
import { EstadoAprobacion } from "./EstadoAprobacion";
import { ListaTextos } from "./ListaTextos";
import { RevisionPropuesta } from "./RevisionPropuesta";

export interface AccionesPropuesta {
  corregir: (textos: { indice: number; texto: string }[]) => void;
  aclarar: (solicitud: SolicitudAclaracion) => void;
  descartar: () => void;
  aprobar: (autor: string) => void;
  reintentarReindexacion: () => void;
  cerrar: () => void;
}

interface Props {
  propuesta: Propuesta;
  autor: string;
  alCambiarAutor: (autor: string) => void;
  ocupado: boolean;
  acciones: AccionesPropuesta;
}

/** Lo que corresponde mostrar según el estado de la propuesta (lo decide el backend). */
export function PanelPropuesta({ propuesta, autor, alCambiarAutor, ocupado, acciones }: Props) {
  switch (propuesta.estado) {
    case "preparando":
      return <EsperaPropuesta nota={propuesta.nota} progreso={propuesta.progreso} />;
    case "lista":
      return (
        <RevisionPropuesta
          key={propuesta.actualizada}
          propuesta={propuesta}
          autor={autor}
          alCambiarAutor={alCambiarAutor}
          ocupado={ocupado}
          alCorregir={acciones.corregir}
          alAprobar={acciones.aprobar}
          alRechazar={acciones.descartar}
        />
      );
    case "requiere_aclaracion":
      return (
        <AclaracionPropuesta
          key={propuesta.actualizada}
          propuesta={propuesta}
          ocupado={ocupado}
          alReintentar={acciones.aclarar}
          alDescartar={acciones.descartar}
        />
      );
    case "aprobada":
      return (
        <EstadoAprobacion
          propuesta={propuesta}
          ocupado={ocupado}
          alReintentar={acciones.reintentarReindexacion}
          alOtroCambio={acciones.cerrar}
        />
      );
    case "descartada":
      return (
        <div className="entrada space-y-3">
          <Aviso tono="info" titulo="Propuesta descartada. La documentación no cambió." />
          <Boton variante="discreto" onClick={acciones.cerrar}>
            Proponer otro cambio
          </Boton>
        </div>
      );
    default:
      return (
        <section aria-label="La propuesta no se pudo preparar" className="entrada space-y-3">
          <div className="flex items-start gap-3">
            <Mascota variante="sin_resultados" alto={56} />
            <Aviso tono="error" titulo="No se pudo preparar la propuesta." className="flex-1">
              <ListaTextos
                textos={propuesta.errores.length ? propuesta.errores : ["No se obtuvo una propuesta válida."]}
              />
              <p className="mt-2">
                Puedes ajustar la nota (o elegir la página) en el formulario y volver a intentarlo.
              </p>
            </Aviso>
          </div>
          {propuesta.detalle_tecnico && (
            <details className="rounded-md border border-border px-4 py-2">
              <summary className="cursor-pointer text-sm font-semibold text-fg">Detalle técnico</summary>
              {propuesta.pagina && <p className="mt-2 text-xs text-fg-muted">Página: {propuesta.pagina}</p>}
              <pre className="mt-2 overflow-auto rounded-sm bg-surface-code p-3 font-mono text-xs text-fg">
                {propuesta.detalle_tecnico}
              </pre>
            </details>
          )}
        </section>
      );
  }
}

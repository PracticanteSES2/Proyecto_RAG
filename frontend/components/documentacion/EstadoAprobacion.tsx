import type { Propuesta } from "@/lib/api/tiposDocumentacion";
import { Aviso } from "@/components/ui/Aviso";
import { Boton } from "@/components/ui/Boton";
import { IconoReintentar } from "@/components/ui/Iconos";
import { ListaTextos } from "./ListaTextos";

interface Props {
  propuesta: Propuesta;
  ocupado: boolean;
  alReintentar: () => void;
  alOtroCambio: () => void;
}

/** Cambio aprobado y estado de la reindexación (el chat usa la versión nueva cuando termina). */
export function EstadoAprobacion({ propuesta, ocupado, alReintentar, alOtroCambio }: Props) {
  const aprobacion = propuesta.aprobacion;
  if (!aprobacion) return null;
  const { reindexacion } = aprobacion;
  const version = aprobacion.version !== null ? `la versión ${aprobacion.version}` : "una versión nueva";
  const fallo = reindexacion.estado === "error" || reindexacion.estado === "no_disponible";

  return (
    <section aria-label="Cambio aprobado" className="entrada space-y-3">
      <Aviso tono="exito" titulo="Cambio aprobado">
        La página <strong>{propuesta.pagina}</strong> quedó guardada en <strong>{version}</strong>.
      </Aviso>
      {(reindexacion.estado === "en_curso" || reindexacion.estado === "sin_iniciar") && (
        <p role="status" className="flex items-center gap-2 text-sm text-fg-muted">
          <span className="pensando__punto" style={{ background: "var(--ses-azul)" }} aria-hidden="true" />
          Actualizando el buscador del asistente (reindexación del tablero)…
        </p>
      )}
      {reindexacion.estado === "lista" && (
        <Aviso tono="info" titulo="Buscador del asistente actualizado">
          {reindexacion.mensaje}
          {reindexacion.avisos.length > 0 && <ListaTextos textos={reindexacion.avisos} />}
        </Aviso>
      )}
      {fallo && (
        <Aviso tono="aviso" titulo="El cambio sí quedó guardado, pero el asistente del chat todavía no lo conoce.">
          <p>{reindexacion.mensaje}</p>
          <Boton className="mt-2" onClick={alReintentar} disabled={ocupado}>
            <IconoReintentar tamano={14} />
            Reintentar la reindexación
          </Boton>
        </Aviso>
      )}
      <Boton variante="discreto" onClick={alOtroCambio}>
        Proponer otro cambio
      </Boton>
    </section>
  );
}

"use client";

import type { ValorCalificacion } from "@/lib/api/tipos";
import type { MensajeAsistente as TipoMensajeAsistente } from "@/lib/chat/reductor";
import { avisosVisibles, turnoActivo } from "@/lib/turno/maquina";
import { AvatarAsistente } from "@/components/ui/Mascota";
import { IconoInfo } from "@/components/ui/Iconos";
import { AvisoTurno, esFaseProblema } from "./AvisoTurno";
import { Calificacion } from "./Calificacion";
import { IndicadorPensando } from "./IndicadorPensando";
import { PanelDiagnostico } from "./PanelDiagnostico";
import { RespuestaTurno } from "./RespuestaTurno";

interface Props {
  mensaje: TipoMensajeAsistente;
  diagnostico: boolean;
  contrapreguntaActiva: boolean;
  /** Hay un turno en curso (no se puede reintentar ni elegir). */
  ocupado: boolean;
  alElegirOpcion: (id: string, texto: string) => void;
  alReintentar: () => void;
  alCalificar: (valor: ValorCalificacion, comentario?: string) => void;
}

function Avisos({ textos }: { textos: string[] }) {
  if (!textos.length) return null;
  return (
    <div className="mt-2 space-y-1">
      {textos.map((texto) => (
        <p key={texto} className="flex items-start gap-1.5 text-sm text-fg-muted">
          <IconoInfo tamano={16} className="mt-0.5 shrink-0 text-info" />
          <span>{texto}</span>
        </p>
      ))}
    </div>
  );
}

/**
 * Mensaje del asistente: indicador de «pensando»; en cuanto llegan tokens, la burbuja con el borrador en vivo,
 * que se convierte en la respuesta validada (misma burbuja, sin saltos); o un aviso amable si algo falló.
 */
export function MensajeAsistente({
  mensaje,
  diagnostico,
  contrapreguntaActiva,
  ocupado,
  alElegirOpcion,
  alReintentar,
  alCalificar,
}: Props) {
  const { turno } = mensaje;
  const activo = turnoActivo(turno);
  const escribiendo = activo && !!turno.borrador;

  if (activo && !escribiendo) {
    return (
      <article aria-label="Asistente" className="pensando flex gap-3">
        <AvatarAsistente pensando />
        <IndicadorPensando
          frase={turno.frase}
          fraseEspera={turno.fraseEspera}
          diagnostico={diagnostico}
          etapas={turno.etapas}
          segundos={turno.segundos}
        />
      </article>
    );
  }

  const respuesta = turno.respuesta;
  return (
    <article aria-label="Asistente" className="entrada flex gap-3">
      <AvatarAsistente pensando={escribiendo} />
      <div className="min-w-0 flex-1">
        {respuesta || escribiendo ? (
          <RespuestaTurno
            mensaje={mensaje}
            contrapreguntaActiva={contrapreguntaActiva}
            ocupado={ocupado}
            alElegirOpcion={alElegirOpcion}
            pie={
              <>
                <Avisos textos={avisosVisibles(turno)} />
                {turno.turnoId && !respuesta?.contrapregunta && (
                  <Calificacion calificacion={mensaje.calificacion} alCalificar={alCalificar} />
                )}
              </>
            }
          />
        ) : (
          esFaseProblema(turno.fase) && (
            <AvisoTurno fase={turno.fase} alReintentar={alReintentar} puedeReintentar={!ocupado} />
          )
        )}
        {diagnostico && <PanelDiagnostico turno={turno} />}
      </div>
    </article>
  );
}

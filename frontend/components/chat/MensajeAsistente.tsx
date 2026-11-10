"use client";

import type { EnlacePowerBI, Fuente, ValorCalificacion } from "@/lib/api/tipos";
import type { MensajeAsistente as TipoMensajeAsistente } from "@/lib/chat/reductor";
import { avisosVisibles, turnoActivo } from "@/lib/turno/maquina";
import { AvatarAsistente } from "@/components/ui/Mascota";
import { IconoDocumento, IconoExterno, IconoInfo, IconoTablero } from "@/components/ui/Iconos";
import { AvisoTurno, esFaseProblema } from "./AvisoTurno";
import { Calificacion } from "./Calificacion";
import { Contrapregunta } from "./Contrapregunta";
import { IndicadorPensando } from "./IndicadorPensando";
import { Markdown } from "./Markdown";
import { PanelDiagnostico } from "./PanelDiagnostico";

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

function EnlacesPowerBI({ enlaces }: { enlaces: EnlacePowerBI[] }) {
  if (!enlaces.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {enlaces.map((enlace) => (
        <a
          key={enlace.url}
          href={enlace.url}
          target="_blank"
          rel="noopener noreferrer"
          title={enlace.titulo}
          className="group inline-flex max-w-full items-center gap-2 rounded-pill border border-primary bg-surface py-1.5 pr-4 pl-3 text-sm font-semibold text-link no-underline transition-colors hover:bg-primary hover:text-on-primary"
        >
          <IconoTablero tamano={16} className="shrink-0" />
          <span className="truncate">
            Abrir en Power BI ›<span className="sr-only"> (se abre en otra pestaña)</span>
            <span className="ml-1.5 font-normal opacity-80">{enlace.titulo}</span>
          </span>
          <IconoExterno tamano={14} className="shrink-0 opacity-70" />
        </a>
      ))}
    </div>
  );
}

function Fuentes({ fuentes }: { fuentes: Fuente[] }) {
  if (!fuentes.length) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-fg-muted">
      <span className="font-semibold">Fuentes:</span>
      {fuentes.map((f, i) => (
        <span
          key={`${f.titulo}-${i}`}
          className="inline-flex max-w-full items-center gap-1 rounded-pill bg-surface-2 px-2.5 py-1"
        >
          <IconoDocumento tamano={12} className="shrink-0" />
          <span className="truncate">
            {[f.tablero && f.tablero !== f.titulo ? f.tablero : null, f.titulo, f.pagina].filter(Boolean).join(" · ")}
          </span>
        </span>
      ))}
    </div>
  );
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

/** Mensaje del asistente: indicador de «pensando», respuesta completa o aviso amable. */
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

  if (turnoActivo(turno)) {
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
      <AvatarAsistente />
      <div className="min-w-0 flex-1">
        {respuesta ? (
          <>
            <div className="rounded-bubble rounded-tl-[var(--radius-bubble-tail)] border border-border bg-surface px-4 py-3 shadow-sm">
              <Markdown texto={respuesta.texto_markdown} />
              {respuesta.contrapregunta && (
                <Contrapregunta
                  contrapregunta={respuesta.contrapregunta}
                  activa={contrapreguntaActiva && !ocupado}
                  elegida={mensaje.opcionElegida}
                  alElegir={alElegirOpcion}
                />
              )}
              <EnlacesPowerBI enlaces={respuesta.enlaces_powerbi} />
              <Fuentes fuentes={respuesta.fuentes} />
            </div>
            <Avisos textos={avisosVisibles(turno)} />
            {turno.turnoId && !respuesta.contrapregunta && (
              <Calificacion calificacion={mensaje.calificacion} alCalificar={alCalificar} />
            )}
          </>
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

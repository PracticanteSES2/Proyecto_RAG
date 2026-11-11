"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";
import type { EnlacePowerBI, Fuente } from "@/lib/api/tipos";
import type { MensajeAsistente } from "@/lib/chat/reductor";
import { IconoDocumento, IconoExterno, IconoTablero } from "@/components/ui/Iconos";
import { useRevelado } from "@/hooks/useRevelado";
import { Contrapregunta } from "./Contrapregunta";
import { Markdown } from "./Markdown";

/** Tras un fundido (la final no coincidía con el borrador), la burbuja conserva su alto este tiempo. */
const RETENER_ALTO_MS = 450;

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
  // Una etiqueta por fuente distinta (también sirve de clave estable).
  const etiquetas = [
    ...new Set(
      fuentes.map((f) =>
        [f.tablero && f.tablero !== f.titulo ? f.tablero : null, f.titulo, f.pagina].filter(Boolean).join(" · "),
      ),
    ),
  ];
  if (!etiquetas.length) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-fg-muted">
      <span className="font-semibold">Fuentes:</span>
      {etiquetas.map((etiqueta) => (
        <span
          key={etiqueta}
          className="inline-flex max-w-full items-center gap-1 rounded-pill bg-surface-2 px-2.5 py-1"
        >
          <IconoDocumento tamano={12} className="shrink-0" />
          <span className="truncate">{etiqueta}</span>
        </span>
      ))}
    </div>
  );
}

interface Props {
  mensaje: MensajeAsistente;
  contrapreguntaActiva: boolean;
  ocupado: boolean;
  alElegirOpcion: (id: string, texto: string) => void;
  /** Lo que va bajo la burbuja (avisos, calificación); aparece cuando la respuesta terminó de revelarse. */
  pie?: ReactNode;
}

/**
 * Burbuja de la respuesta. Una sola instancia vive desde el primer `token` hasta la respuesta final, así el
 * borrador en vivo se convierte en la respuesta validada sin desmontar nada (contracts/eventos.md):
 * borrador con cursor → si la final empieza por él, se sigue escribiendo; si no, fundido suave conservando el alto.
 * Sin borrador, la respuesta en vivo se revela con escritura rápida; la del historial aparece completa.
 */
export function RespuestaTurno({ mensaje, contrapreguntaActiva, ocupado, alElegirOpcion, pie }: Props) {
  const { turno } = mensaje;
  const respuesta = turno.respuesta;
  const revelado = useRevelado(respuesta?.texto_markdown ?? "", turno.borrador, !!respuesta && !!turno.revelar);
  const caja = useRef<HTMLDivElement>(null);
  const altoBorrador = useRef(0);
  const escribiendo = !respuesta;

  useLayoutEffect(() => {
    const nodo = caja.current;
    if (!nodo) return;
    if (escribiendo) {
      altoBorrador.current = nodo.offsetHeight;
      return;
    }
    if (!revelado.fundido || !altoBorrador.current) return;
    nodo.style.minHeight = `${altoBorrador.current}px`;
    const id = window.setTimeout(() => (nodo.style.minHeight = ""), RETENER_ALTO_MS);
    return () => window.clearTimeout(id);
  }, [escribiendo, revelado.fundido, turno.borrador]);

  const texto = escribiendo ? (turno.borrador ?? "") : revelado.visible;
  const conCursor = escribiendo || !revelado.completo;
  const final = revelado.completo ? respuesta : undefined;

  return (
    <>
      <div
        ref={caja}
        aria-busy={conCursor}
        className="rounded-bubble rounded-tl-[var(--radius-bubble-tail)] border border-border bg-surface px-4 py-3 shadow-sm"
      >
        <div
          key={revelado.fundido ? "final" : "texto"}
          className={`${conCursor ? "prosa--escribiendo" : ""} ${revelado.fundido ? "respuesta--fundido" : ""}`}
        >
          <Markdown texto={texto} />
        </div>
        {final?.contrapregunta && (
          <Contrapregunta
            contrapregunta={final.contrapregunta}
            activa={contrapreguntaActiva && !ocupado}
            elegida={mensaje.opcionElegida}
            alElegir={alElegirOpcion}
          />
        )}
        {final && (
          <div className="respuesta__extras">
            <EnlacesPowerBI enlaces={final.enlaces_powerbi} />
            <Fuentes fuentes={final.fuentes} />
          </div>
        )}
      </div>
      {final && pie}
    </>
  );
}

"use client";

import { useId, useState } from "react";
import type { ValorCalificacion } from "@/lib/api/tipos";
import type { EstadoCalificacion } from "@/lib/chat/reductor";
import { IconoPulgarAbajo, IconoPulgarArriba } from "@/components/ui/Iconos";

interface Props {
  calificacion?: EstadoCalificacion;
  alCalificar: (valor: ValorCalificacion, comentario?: string) => void;
}

/** 👍 guarda al instante; 👎 abre un comentario opcional antes de enviar. */
export function Calificacion({ calificacion, alCalificar }: Props) {
  const [editando, setEditando] = useState(false);
  const [comentario, setComentario] = useState(calificacion?.comentario ?? "");
  const id = useId();
  const valor = calificacion?.valor;

  const botonClase = (activo: boolean) =>
    `inline-flex size-8 items-center justify-center rounded-pill transition-colors ${
      activo ? "bg-surface-3 text-primary" : "text-fg-muted hover:bg-surface-2 hover:text-fg"
    }`;

  const enviarNegativa = () => {
    alCalificar("mala", comentario);
    setEditando(false);
  };

  return (
    <div className="mt-2">
      <div className="flex items-center gap-1">
        <span className="mr-1 text-xs text-fg-muted">¿Te sirvió?</span>
        <button
          type="button"
          aria-label="Me sirvió"
          aria-pressed={valor === "buena"}
          className={botonClase(valor === "buena")}
          onClick={() => {
            setEditando(false);
            alCalificar("buena");
          }}
        >
          <IconoPulgarArriba tamano={16} />
        </button>
        <button
          type="button"
          aria-label="No me sirvió"
          aria-pressed={valor === "mala" || editando}
          aria-expanded={editando}
          aria-controls={`${id}-comentario`}
          className={botonClase(valor === "mala" || editando)}
          onClick={() => setEditando((v) => !v)}
        >
          <IconoPulgarAbajo tamano={16} />
        </button>
        <span className="ml-2 text-xs text-fg-muted" aria-live="polite">
          {calificacion?.estado === "guardando" && "Guardando…"}
          {calificacion?.estado === "guardada" && "Gracias por tu opinión."}
          {calificacion?.estado === "error" && "No se pudo guardar; intenta de nuevo."}
        </span>
      </div>
      {editando && (
        <div id={`${id}-comentario`} className="entrada mt-2 max-w-xl rounded-md border border-border bg-surface-2 p-3">
          <label htmlFor={`${id}-texto`} className="text-sm font-semibold text-fg">
            ¿Qué esperabas que respondiera? <span className="font-normal text-fg-muted">(opcional)</span>
          </label>
          <p className="text-xs text-fg-muted">No incluyas datos de pacientes.</p>
          <textarea
            id={`${id}-texto`}
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
            rows={3}
            className="mt-2 w-full resize-y rounded-sm border border-border-strong bg-surface px-3 py-2 text-sm text-fg"
          />
          <div className="mt-2 flex justify-end gap-2">
            <button type="button" onClick={() => setEditando(false)} className="rounded-pill px-3 py-1.5 text-sm font-semibold text-fg-muted hover:bg-surface-3">
              Cancelar
            </button>
            <button
              type="button"
              onClick={enviarNegativa}
              className="rounded-pill bg-primary px-4 py-1.5 text-sm font-semibold text-on-primary hover:bg-primary-hover active:bg-primary-active"
            >
              Enviar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

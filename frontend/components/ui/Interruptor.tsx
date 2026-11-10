"use client";

import { useId } from "react";

interface Props {
  etiqueta: string;
  ayuda?: string;
  activo: boolean;
  alCambiar: (activo: boolean) => void;
  /** Tono del interruptor activo: primario o morado de diagnóstico. */
  tono?: "primario" | "diag";
}

/** Interruptor accesible (role="switch"). */
export function Interruptor({ etiqueta, ayuda, activo, alCambiar, tono = "primario" }: Props) {
  const id = useId();
  const fondo = activo
    ? tono === "diag"
      ? "bg-diag border-diag"
      : "bg-primary border-primary"
    : "bg-surface-2 border-border-strong";
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <label htmlFor={id} className="block text-sm font-semibold text-fg">
          {etiqueta}
        </label>
        {ayuda && (
          <p id={`${id}-ayuda`} className="mt-0.5 text-xs text-fg-muted">
            {ayuda}
          </p>
        )}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={activo}
        aria-describedby={ayuda ? `${id}-ayuda` : undefined}
        onClick={() => alCambiar(!activo)}
        className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-pill border transition-colors duration-200 ${fondo}`}
      >
        <span
          className={`inline-block size-4 rounded-full bg-surface shadow-sm transition-transform duration-200 ${activo ? "translate-x-6" : "translate-x-1"}`}
        />
      </button>
    </div>
  );
}

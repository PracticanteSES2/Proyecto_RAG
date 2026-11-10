"use client";

import { useState } from "react";
import type { EtapaRegistrada } from "@/lib/turno/maquina";
import { LineaTiempo } from "./LineaTiempo";

/** Puntos con los cuatro colores del isotipo (los mismos del filete superior). */
const PUNTOS = ["var(--ses-azul)", "var(--ses-morado)", "var(--ses-coral)", "var(--ses-verde)"];

interface Props {
  frase: string;
  fraseEspera?: string;
  diagnostico?: boolean;
  etapas?: EtapaRegistrada[];
  segundos?: number;
}

/**
 * Indicador de «pensando». Contenedor de alto fijo: la frase principal (una línea, elipsis, brillo suave) y un
 * renglón reservado para las frases de espera, para que nada salte al cambiar. La frase anterior se desvanece
 * mientras entra la nueva (~200 ms). Con diagnóstico, además la línea de tiempo con segundos.
 */
export function IndicadorPensando({ frase, fraseEspera, diagnostico = false, etapas = [], segundos = 0 }: Props) {
  const [frases, setFrases] = useState({ actual: frase, anterior: null as string | null, clave: 0 });
  if (frases.actual !== frase) {
    setFrases({ actual: frase, anterior: frases.actual, clave: frases.clave + 1 });
  }

  return (
    <div className="min-w-0 flex-1 pt-1">
      <div role="status" aria-live="polite" aria-atomic="true">
      <div className="flex items-center gap-3">
        <span className="flex shrink-0 items-center gap-1.5" aria-hidden="true">
          {PUNTOS.map((color, i) => (
            <span key={color} className="pensando__punto" style={{ background: color, animationDelay: `${i * 0.18}s` }} />
          ))}
        </span>
        <span className="relative block h-6 min-w-0 flex-1 overflow-hidden">
          {frases.anterior && (
            <span key={`a${frases.clave}`} aria-hidden="true" className="pensando__saliente absolute inset-0 truncate text-base font-semibold text-fg-heading">
              {frases.anterior}
            </span>
          )}
          <span key={`b${frases.clave}`} className="pensando__frase absolute inset-0 truncate text-base font-semibold">
            {frase}
          </span>
        </span>
      </div>
      <p className="mt-1 h-5 truncate pl-[calc(4*0.45rem+3*0.375rem+0.75rem)] text-[0.82rem] text-fg-muted opacity-80">
        {fraseEspera && (
          <span key={fraseEspera} className="pensando__espera">
            {fraseEspera}
          </span>
        )}
      </p>
      </div>
      {diagnostico && <LineaTiempo etapas={etapas} segundos={segundos} enCurso />}
    </div>
  );
}

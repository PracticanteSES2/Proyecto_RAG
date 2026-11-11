"use client";

import { useEffect, useMemo, useState } from "react";
import { planRevelado, unidadesVisibles } from "@/lib/turno/revelado";

function sinAnimacion(): boolean {
  if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") return true;
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export interface Revelado {
  visible: string;
  completo: boolean;
  fundido: boolean;
}

/**
 * Revela `texto` con escritura rápida (lib/turno/revelado.ts). `animar` = la respuesta llegó en vivo; si venía
 * de un borrador en streaming, se continúa desde él. Sin animación (historial, `prefers-reduced-motion`, sin
 * requestAnimationFrame) el texto aparece completo.
 */
export function useRevelado(texto: string, borrador: string | undefined, animar: boolean): Revelado {
  const plan = useMemo(() => planRevelado(texto, borrador, animar && !sinAnimacion()), [texto, borrador, animar]);
  const total = plan.unidades.length;
  const [mostradas, setMostradas] = useState(plan.inicio);

  useEffect(() => {
    if (plan.inicio >= total) return;
    let marco = 0;
    let inicioMs: number | undefined;
    const paso = (ahora: number) => {
      inicioMs ??= ahora;
      const n = unidadesVisibles(plan.inicio, total, ahora - inicioMs);
      setMostradas(n);
      if (n < total) marco = window.requestAnimationFrame(paso);
    };
    marco = window.requestAnimationFrame(paso);
    return () => window.cancelAnimationFrame(marco);
  }, [plan, total]);

  const n = Math.max(mostradas, plan.inicio);
  return {
    visible: n >= total ? texto : plan.unidades.slice(0, n).join(""),
    completo: n >= total,
    fundido: plan.fundido,
  };
}

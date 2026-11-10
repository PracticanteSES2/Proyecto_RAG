"use client";

import { useEffect } from "react";
import { usePreferencia } from "./usePreferencia";

export type Tema = "sistema" | "claro" | "oscuro";

/** Tema de la interfaz: «sistema» sigue a prefers-color-scheme; los otros fuerzan <html data-theme>. */
export function useTema() {
  const [tema, cambiarTema] = usePreferencia<Tema>("asistente.tema", "sistema");
  useEffect(() => {
    const raiz = document.documentElement;
    if (tema === "claro") raiz.dataset.theme = "light";
    else if (tema === "oscuro") raiz.dataset.theme = "dark";
    else delete raiz.dataset.theme;
  }, [tema]);
  return [tema, cambiarTema] as const;
}

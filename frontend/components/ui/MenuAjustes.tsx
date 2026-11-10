"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { Tema } from "@/hooks/useTema";
import { IconoAjustes, IconoExportar, IconoLuna, IconoMonitor, IconoSol } from "./IconosAjustes";
import { Interruptor } from "./Interruptor";

interface Props {
  tema: Tema;
  alCambiarTema: (tema: Tema) => void;
  diagnostico: boolean;
  alCambiarDiagnostico: (activo: boolean) => void;
  puedeExportar: boolean;
  alExportar: () => Promise<boolean>;
}

const TEMAS: { valor: Tema; etiqueta: string; Icono: typeof IconoSol }[] = [
  { valor: "sistema", etiqueta: "Sistema", Icono: IconoMonitor },
  { valor: "claro", etiqueta: "Claro", Icono: IconoSol },
  { valor: "oscuro", etiqueta: "Oscuro", Icono: IconoLuna },
];

/** Menú discreto de ajustes: tema, modo diagnóstico y exportar la conversación. */
export function MenuAjustes({
  tema,
  alCambiarTema,
  diagnostico,
  alCambiarDiagnostico,
  puedeExportar,
  alExportar,
}: Props) {
  const [abierto, setAbierto] = useState(false);
  const [mensajeExportar, setMensajeExportar] = useState<string | null>(null);
  const contenedor = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const idPanel = useId();

  useEffect(() => {
    if (!abierto) return;
    const alPulsarFuera = (e: PointerEvent) => {
      if (!contenedor.current?.contains(e.target as Node)) setAbierto(false);
    };
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setAbierto(false);
        boton.current?.focus();
      }
    };
    document.addEventListener("pointerdown", alPulsarFuera);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("pointerdown", alPulsarFuera);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [abierto]);

  const exportar = async () => {
    setMensajeExportar(null);
    const ok = await alExportar();
    setMensajeExportar(ok ? "Listo: revisa tus descargas." : "No se pudo exportar. Intenta de nuevo.");
  };

  return (
    <div ref={contenedor} className="relative">
      <button
        ref={boton}
        type="button"
        aria-label="Ajustes"
        aria-expanded={abierto}
        aria-controls={idPanel}
        onClick={() => setAbierto((v) => !v)}
        className="inline-flex size-10 items-center justify-center rounded-pill text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg"
      >
        <IconoAjustes tamano={20} />
      </button>
      {abierto && (
        <div
          id={idPanel}
          role="dialog"
          aria-label="Ajustes"
          className="entrada absolute top-12 right-0 z-30 w-[min(20rem,calc(100vw-2rem))] rounded-lg border border-border bg-surface p-4 shadow-lg"
        >
          <fieldset>
            <legend className="text-sm font-semibold text-fg">Apariencia</legend>
            <div className="mt-2 grid grid-cols-3 gap-1 rounded-md bg-surface-2 p-1">
              {TEMAS.map(({ valor, etiqueta, Icono }) => (
                <label
                  key={valor}
                  className={`flex cursor-pointer flex-col items-center gap-1 rounded-sm px-2 py-1.5 text-xs transition-colors has-[:focus-visible]:shadow-[var(--focus-ring)] ${
                    tema === valor ? "bg-surface font-semibold text-fg shadow-sm" : "text-fg-muted hover:text-fg"
                  }`}
                >
                  <input
                    type="radio"
                    name="tema"
                    value={valor}
                    checked={tema === valor}
                    onChange={() => alCambiarTema(valor)}
                    className="sr-only"
                  />
                  <Icono tamano={16} />
                  {etiqueta}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="my-4 h-px bg-border" />

          <Interruptor
            etiqueta="Modo diagnóstico"
            ayuda="Muestra tiempos, etapas, DAX y trazas bajo cada respuesta. Pensado para el equipo técnico."
            activo={diagnostico}
            alCambiar={alCambiarDiagnostico}
            tono="diag"
          />

          <div className="my-4 h-px bg-border" />

          <button
            type="button"
            onClick={exportar}
            disabled={!puedeExportar}
            className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm font-semibold text-fg transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <IconoExportar tamano={16} />
            Exportar conversación (.md)
          </button>
          <p className="px-2 text-xs text-fg-muted" aria-live="polite">
            {mensajeExportar ??
              (puedeExportar ? "Preguntas, respuestas y enlaces, para compartir." : "Aún no hay nada que exportar.")}
          </p>
        </div>
      )}
    </div>
  );
}

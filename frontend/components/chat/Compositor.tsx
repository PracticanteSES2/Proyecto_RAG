"use client";

import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { IconoDetener, IconoEnviar } from "@/components/ui/Iconos";

export interface ManejadorCompositor {
  enfocar(): void;
}

interface Props {
  /** Hay un turno en curso: Enter no envía y el botón pasa a «Detener». */
  ocupado: boolean;
  alEnviar: (texto: string) => void;
  alDetener: () => void;
}

const MAX_ALTO_PX = 6 * 24 + 20; // ~6 líneas

/** Campo de pregunta: Enter envía, Shift+Enter hace salto de línea; crece hasta ~6 líneas. */
export const Compositor = forwardRef<ManejadorCompositor, Props>(function Compositor(
  { ocupado, alEnviar, alDetener },
  ref,
) {
  const [texto, setTexto] = useState("");
  const campo = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({ enfocar: () => campo.current?.focus() }), []);

  useLayoutEffect(() => {
    const el = campo.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_ALTO_PX)}px`;
  }, [texto]);

  const vacio = !texto.trim();

  const enviar = () => {
    if (ocupado || vacio) return;
    alEnviar(texto);
    setTexto("");
  };

  const alTeclear = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      enviar();
    }
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        enviar();
      }}
      className="flex items-end gap-2 rounded-lg border border-border-strong bg-surface p-2 pl-4 shadow-md transition-shadow focus-within:shadow-[var(--focus-ring)]"
    >
      <label htmlFor="pregunta" className="sr-only">
        Escribe tu pregunta
      </label>
      <textarea
        id="pregunta"
        ref={campo}
        rows={1}
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={alTeclear}
        placeholder="Escribe tu pregunta…"
        enterKeyHint="send"
        autoComplete="off"
        className="max-h-40 min-h-10 flex-1 resize-none bg-transparent py-2 text-base text-fg placeholder:text-fg-muted focus:outline-none focus-visible:shadow-none"
      />
      {ocupado ? (
        <button
          type="button"
          onClick={alDetener}
          aria-label="Detener la consulta"
          title="Detener"
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-pill border border-border-strong bg-surface-2 text-fg transition-colors hover:bg-surface-3"
        >
          <IconoDetener tamano={18} />
        </button>
      ) : (
        <button
          type="submit"
          disabled={vacio}
          aria-label="Enviar pregunta"
          title="Enviar (Enter)"
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-pill bg-primary text-on-primary transition-[background-color,opacity] hover:bg-primary-hover active:bg-primary-active disabled:cursor-not-allowed disabled:opacity-40"
        >
          <IconoEnviar tamano={20} />
        </button>
      )}
    </form>
  );
});

export type Modo = "ver" | "proponer";

const MODOS: { modo: Modo; texto: string }[] = [
  { modo: "ver", texto: "Ver documentación" },
  { modo: "proponer", texto: "Proponer un cambio" },
];

/** «Ver documentación · Proponer un cambio» (botones con `aria-pressed`). */
export function SelectorModo({ modo, alCambiar }: { modo: Modo; alCambiar: (modo: Modo) => void }) {
  return (
    <div className="flex gap-1 rounded-pill bg-surface-2 p-1" role="group" aria-label="¿Qué quieres hacer?">
      {MODOS.map(({ modo: valor, texto }) => (
        <button
          key={valor}
          type="button"
          aria-pressed={modo === valor}
          onClick={() => alCambiar(valor)}
          className={`h-8 rounded-pill px-3 text-sm font-semibold transition-colors ${
            modo === valor ? "bg-surface text-fg-heading shadow-sm" : "text-fg-muted hover:text-fg"
          }`}
        >
          {texto}
        </button>
      ))}
    </div>
  );
}

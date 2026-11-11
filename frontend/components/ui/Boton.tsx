import type { ButtonHTMLAttributes } from "react";

type Variante = "primario" | "secundario" | "discreto";

const CLASES: Record<Variante, string> = {
  primario: "bg-primary text-on-primary hover:bg-primary-hover active:bg-primary-active",
  secundario: "border border-border-strong bg-surface text-fg hover:bg-surface-2",
  discreto: "text-fg-muted hover:bg-surface-2 hover:text-fg",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: Variante;
}

/** Botón píldora con las variantes del sistema visual (tokens de styles/tokens.css). */
export function Boton({ variante = "secundario", className = "", type = "button", ...resto }: Props) {
  return (
    <button
      type={type}
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-pill px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${CLASES[variante]} ${className}`}
      {...resto}
    />
  );
}

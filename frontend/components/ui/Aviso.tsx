import type { ReactNode } from "react";

type Tono = "info" | "exito" | "aviso" | "error";

const CLASES: Record<Tono, string> = {
  info: "border-info-border bg-info-bg",
  exito: "border-success-border bg-success-bg",
  aviso: "border-warning-border bg-warning-bg",
  error: "border-danger-border bg-danger-bg",
};

interface Props {
  tono?: Tono;
  titulo?: string;
  children?: ReactNode;
  className?: string;
}

/**
 * Recuadro de aviso con borde de color y título en texto (el tono nunca es la única señal). Los errores se anuncian
 * a los lectores de pantalla (`role="alert"`); el resto, como estado (`role="status"`).
 */
export function Aviso({ tono = "info", titulo, children, className = "" }: Props) {
  return (
    <div
      role={tono === "error" ? "alert" : "status"}
      className={`rounded-md border-l-[3px] px-4 py-3 text-sm text-fg ${CLASES[tono]} ${className}`}
    >
      {titulo && <p className="font-semibold">{titulo}</p>}
      {children && <div className={titulo ? "mt-1" : ""}>{children}</div>}
    </div>
  );
}

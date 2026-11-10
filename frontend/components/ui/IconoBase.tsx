/** Base de los iconos de trazo (24×24, 2px, currentColor). Decorativos: el texto o aria-label dice qué hacen. */
import type { SVGProps } from "react";

export type PropsIcono = SVGProps<SVGSVGElement> & { tamano?: number };

export function IconoBase({ tamano = 18, children, ...resto }: PropsIcono) {
  return (
    <svg
      width={tamano}
      height={tamano}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...resto}
    >
      {children}
    </svg>
  );
}

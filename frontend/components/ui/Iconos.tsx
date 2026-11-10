/** Iconos del chat (24×24, trazo 2px, currentColor; pulgares de Lucide, licencia ISC). Decorativos. */
import { IconoBase as Base, type PropsIcono as Props } from "./IconoBase";

export const IconoEnviar = (p: Props) => (
  <Base {...p}>
    <path d="M12 19V5" />
    <path d="m5 12 7-7 7 7" />
  </Base>
);

export const IconoDetener = (p: Props) => (
  <Base {...p}>
    <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none" />
  </Base>
);

export const IconoPulgarArriba = (p: Props) => (
  <Base {...p}>
    <path d="M7 10v12" />
    <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z" />
  </Base>
);

export const IconoPulgarAbajo = (p: Props) => (
  <Base {...p}>
    <path d="M17 14V2" />
    <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z" />
  </Base>
);

export const IconoInfo = (p: Props) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 16v-4" />
    <path d="M12 8h.01" />
  </Base>
);

export const IconoExterno = (p: Props) => (
  <Base {...p}>
    <path d="M14 4h6v6" />
    <path d="M20 4 10 14" />
    <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </Base>
);

export const IconoReintentar = (p: Props) => (
  <Base {...p}>
    <path d="M3 12a9 9 0 0 1 15.5-6.2L21 8" />
    <path d="M21 3v5h-5" />
    <path d="M21 12a9 9 0 0 1-15.5 6.2L3 16" />
    <path d="M3 21v-5h5" />
  </Base>
);

export const IconoDocumento = (p: Props) => (
  <Base {...p}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
    <path d="M14 3v5h5" />
    <path d="M9 13h6" />
    <path d="M9 17h4" />
  </Base>
);

export const IconoTablero = (p: Props) => (
  <Base {...p}>
    <path d="M4 20V10" />
    <path d="M10 20V4" />
    <path d="M16 20v-7" />
    <path d="M22 20H2" />
  </Base>
);

export const IconoCheck = (p: Props) => (
  <Base {...p}>
    <path d="m5 12 5 5L20 7" />
  </Base>
);

export const IconoChevron = (p: Props) => (
  <Base {...p}>
    <path d="m9 6 6 6-6 6" />
  </Base>
);

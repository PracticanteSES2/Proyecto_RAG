/**
 * Mascota del hospital: el BARRANQUERO (el ave de la estatua de la torre del hospital).
 *
 * Mientras el agente de estética entrega los SVG oficiales en `public/marca/mascota/`, se dibuja un marcador
 * provisional en línea. Para usar los oficiales basta con copiar los archivos y poner
 * `MASCOTA_OFICIAL_DISPONIBLE = true`: los componentes que usan <Mascota>/<AvatarAsistente> no cambian.
 *
 * Variantes: «color» (franjas con los colores del isotipo), «natural» (colores del ave), «mono» (currentColor).
 */
import { useId, type CSSProperties } from "react";

export type VarianteMascota = "color" | "natural" | "mono";

export const MASCOTA_OFICIAL_DISPONIBLE = false;

export const ARCHIVOS_MASCOTA: Record<VarianteMascota | "avatar", string> = {
  color: "/marca/mascota/barranquero_color.svg",
  natural: "/marca/mascota/barranquero_natural.svg",
  mono: "/marca/mascota/barranquero_mono.svg",
  avatar: "/marca/mascota/avatar_barranquero.svg",
};

interface PropsMascota {
  variante?: VarianteMascota;
  /** Lado en px (cuadrado). */
  tamano?: number;
  /** Texto alternativo; vacío = decorativa. */
  etiqueta?: string;
  className?: string;
}

export function Mascota({ variante = "color", tamano = 96, etiqueta = "", className }: PropsMascota) {
  const accesible = etiqueta ? { role: "img" as const, "aria-label": etiqueta } : { "aria-hidden": true as const };
  if (MASCOTA_OFICIAL_DISPONIBLE) {
    if (variante === "mono") {
      const estilo: CSSProperties = {
        width: tamano,
        height: tamano,
        backgroundColor: "currentColor",
        mask: `url(${ARCHIVOS_MASCOTA.mono}) center / contain no-repeat`,
        WebkitMask: `url(${ARCHIVOS_MASCOTA.mono}) center / contain no-repeat`,
      };
      return <span className={`inline-block ${className ?? ""}`} style={estilo} {...accesible} />;
    }
    return (
      // eslint-disable-next-line @next/next/no-img-element -- SVG estático; next/image no aporta nada aquí
      <img src={ARCHIVOS_MASCOTA[variante]} width={tamano} height={tamano} alt={etiqueta} className={className} />
    );
  }
  return <BarranqueroProvisional variante={variante} tamano={tamano} className={className} {...accesible} />;
}

interface PropsAvatar {
  tamano?: number;
  /** Anillo que respira mientras el asistente trabaja. */
  pensando?: boolean;
  className?: string;
}

/** Avatar del asistente en el chat (decorativo: el rol lo anuncia el mensaje). */
export function AvatarAsistente({ tamano = 32, pensando = false, className = "" }: PropsAvatar) {
  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center rounded-full bg-primary text-on-primary shadow-sm ${className}`}
      style={{ width: tamano, height: tamano }}
      aria-hidden="true"
    >
      {pensando && <span className="avatar__anillo absolute -inset-1 rounded-full border-2 border-ses-azul-cielo" />}
      {MASCOTA_OFICIAL_DISPONIBLE ? (
        // eslint-disable-next-line @next/next/no-img-element -- SVG estático
        <img src={ARCHIVOS_MASCOTA.avatar} width={tamano} height={tamano} alt="" className="rounded-full" />
      ) : (
        <BarranqueroProvisional variante="mono" tamano={Math.round(tamano * 0.78)} colorOjo="var(--color-primary)" />
      )}
    </span>
  );
}

const COLORES: Record<Exclude<VarianteMascota, "color">, Record<"cuerpo" | "ala" | "corona" | "antifaz" | "ojo" | "pico" | "cola", string>> = {
  natural: {
    cuerpo: "var(--ses-verde)",
    ala: "var(--ses-verde-fuerte)",
    corona: "var(--ses-azul-cielo)",
    antifaz: "var(--ses-tinta)",
    ojo: "var(--ses-coral-fuerte)",
    pico: "var(--ses-tinta)",
    cola: "var(--ses-azul)",
  },
  mono: {
    cuerpo: "currentColor",
    ala: "currentColor",
    corona: "currentColor",
    antifaz: "currentColor",
    ojo: "transparent",
    pico: "currentColor",
    cola: "currentColor",
  },
};

/** Marcador provisional: barranquero posado de perfil, con su cola larga terminada en «raqueta». */
function BarranqueroProvisional({
  variante,
  tamano,
  className,
  colorOjo,
  ...accesible
}: { variante: VarianteMascota; tamano: number; className?: string; colorOjo?: string; role?: "img"; "aria-label"?: string; "aria-hidden"?: true }) {
  const id = useId().replace(/:/g, "");
  const c = variante === "color" ? COLORES.natural : COLORES[variante];
  const cuerpo = variante === "color" ? `url(#franjas-${id})` : c.cuerpo;
  return (
    <svg width={tamano} height={tamano} viewBox="0 0 64 64" className={className} {...accesible} focusable="false">
      {variante === "color" && (
        <defs>
          <linearGradient id={`franjas-${id}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="var(--ses-azul)" />
            <stop offset="0.25" stopColor="var(--ses-azul)" />
            <stop offset="0.25" stopColor="var(--ses-morado)" />
            <stop offset="0.5" stopColor="var(--ses-morado)" />
            <stop offset="0.5" stopColor="var(--ses-coral)" />
            <stop offset="0.75" stopColor="var(--ses-coral)" />
            <stop offset="0.75" stopColor="var(--ses-verde)" />
            <stop offset="1" stopColor="var(--ses-verde)" />
          </linearGradient>
        </defs>
      )}
      <path d="M38 41 49.5 57" stroke={c.cola} strokeWidth="2.6" strokeLinecap="round" fill="none" />
      <ellipse cx="51" cy="59" rx="3" ry="4.4" transform="rotate(-35 51 59)" fill={c.cola} />
      <path d="M19 31c0-8 8-12.5 16.5-9 8.5 3.6 10.8 13.6 4.6 20-6 6.2-19 3.4-21-5Z" fill={cuerpo} />
      <circle cx="22" cy="22" r="9" fill={cuerpo} />
      <path d="M14.2 18.5a9 9 0 0 1 15.4-.8" stroke={c.corona} strokeWidth="3.2" strokeLinecap="round" fill="none" />
      {variante !== "mono" && <path d="M28.5 28.5c5.5-.4 10.5 3.6 11.2 9.4-5.4.4-10-3.2-11.2-9.4Z" fill={c.ala} />}
      {variante !== "mono" && <path d="M13.5 22.5 27.5 20.8v4.3l-13.2 1.2Z" fill={c.antifaz} />}
      <path d="M13.6 21.6 4 25.2l9.8 1.1Z" fill={c.pico} />
      {variante !== "mono" && <circle cx="21.5" cy="23" r="1.7" fill={c.ojo} />}
      {variante === "mono" && colorOjo && <circle cx="21.5" cy="22.6" r="1.8" fill={colorOjo} />}
    </svg>
  );
}

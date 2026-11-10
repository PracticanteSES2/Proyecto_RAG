/**
 * Mascota del hospital: el BARRANQUERO (el ave de la estatua de la torre del hospital).
 * SVG oficiales en `public/marca/mascota/` (origen y proceso: docs/diseno/identidad_visual.md §7).
 *
 * Se sirven como archivos estáticos (next/image sin optimizar), así que sus ids internos nunca chocan entre instancias. La variante
 * «mono» se pinta con una máscara CSS sobre `currentColor`: hereda el color del texto como si fuera en línea.
 */
import Image from "next/image";
import type { CSSProperties } from "react";

export type VarianteMascota = "natural" | "color" | "color_rama" | "mono" | "pensando" | "sin_resultados";

/** Ruta y proporción (ancho / alto del viewBox) de cada archivo. */
export const ARCHIVOS_MASCOTA: Record<VarianteMascota, { src: string; proporcion: number }> = {
  natural: { src: "/marca/mascota/barranquero_natural.svg", proporcion: 528 / 854 },
  color: { src: "/marca/mascota/barranquero_color.svg", proporcion: 528 / 854 },
  color_rama: { src: "/marca/mascota/barranquero_color_rama.svg", proporcion: 1293 / 941 },
  mono: { src: "/marca/mascota/barranquero_mono.svg", proporcion: 528 / 854 },
  pensando: { src: "/marca/mascota/barranquero_pensando.svg", proporcion: 528 / 886 },
  sin_resultados: { src: "/marca/mascota/barranquero_sin_resultados.svg", proporcion: 528 / 854 },
};

export const ARCHIVO_AVATAR = "/marca/mascota/avatar_barranquero.svg";

interface PropsMascota {
  variante?: VarianteMascota;
  /** Alto en px; el ancho sale de la proporción del dibujo. */
  alto?: number;
  /** Texto alternativo; vacío = decorativa. */
  etiqueta?: string;
  className?: string;
}

export function Mascota({ variante = "natural", alto = 96, etiqueta = "", className = "" }: PropsMascota) {
  const { src, proporcion } = ARCHIVOS_MASCOTA[variante];
  const ancho = Math.round(alto * proporcion);
  if (variante === "mono") {
    const estilo: CSSProperties = {
      width: ancho,
      height: alto,
      backgroundColor: "currentColor",
      mask: `url(${src}) center / contain no-repeat`,
      WebkitMask: `url(${src}) center / contain no-repeat`,
    };
    const accesible = etiqueta ? { role: "img" as const, "aria-label": etiqueta } : { "aria-hidden": true as const };
    return <span className={`inline-block shrink-0 ${className}`} style={estilo} {...accesible} />;
  }
  return (
    <Image
      unoptimized
      src={src}
      width={ancho}
      height={alto}
      alt={etiqueta}
      className={`shrink-0 select-none ${className}`}
      draggable={false}
    />
  );
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
      className={`relative inline-flex shrink-0 rounded-full shadow-sm ${className}`}
      style={{ width: tamano, height: tamano }}
      aria-hidden="true"
    >
      {pensando && <span className="avatar__anillo absolute -inset-1 rounded-full border-2 border-ses-azul-cielo" />}
      <Image
        unoptimized
        src={ARCHIVO_AVATAR}
        width={tamano}
        height={tamano}
        alt=""
        className="rounded-full"
        draggable={false}
      />
    </span>
  );
}

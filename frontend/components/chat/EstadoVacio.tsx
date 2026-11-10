"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import type { ClienteApi } from "@/lib/api/cliente";
import type { Capacidades } from "@/lib/api/tipos";
import { Mascota } from "@/components/ui/Mascota";

/** Contenido de respaldo si GET /capacidades no responde: el estado vacío nunca queda vacío. */
export const CAPACIDADES_RESPALDO: Capacidades = {
  capacidades: [
    {
      titulo: "Cifras de los tableros",
      descripcion: "Indicadores de los tableros de Power BI institucionales, con los filtros que necesites.",
    },
    {
      titulo: "Qué significa cada indicador",
      descripcion: "Definiciones tomadas de la documentación de los tableros.",
    },
    { titulo: "Ir directo a Power BI", descripcion: "Un enlace a la página del tablero donde está el dato." },
  ],
  ejemplos: [
    { texto: "¿Cuántos egresos hubo el mes pasado?" },
    { texto: "¿Qué indicadores tiene el tablero quirúrgico?" },
  ],
};

interface Props {
  cliente: ClienteApi;
  alPreguntar: (texto: string) => void;
  deshabilitado?: boolean;
}

/** Bienvenida: mascota, qué puede hacer el asistente y ejemplos de preguntas que se envían al pulsarlos. */
export function EstadoVacio({ cliente, alPreguntar, deshabilitado = false }: Props) {
  const [datos, setDatos] = useState<Capacidades | null>(null);

  useEffect(() => {
    let vigente = true;
    cliente
      .capacidades()
      .then((c) => vigente && setDatos(c))
      .catch(() => vigente && setDatos(CAPACIDADES_RESPALDO));
    return () => {
      vigente = false;
    };
  }, [cliente]);

  const contenido = datos ?? CAPACIDADES_RESPALDO;

  return (
    <section
      aria-labelledby="bienvenida"
      className="entrada relative mx-auto flex max-w-2xl flex-col items-center py-6 text-center sm:py-10"
    >
      <Image
        src="/marca/isotipo_ses.svg"
        alt=""
        width={420}
        height={420}
        unoptimized
        priority
        className="pointer-events-none absolute top-0 left-1/2 -z-10 size-[26rem] -translate-x-1/2 opacity-[0.06]"
      />
      <Mascota variante="natural" alto={220} />
      <h1 id="bienvenida" className="mt-4 text-2xl font-bold sm:text-3xl">
        Hola, ¿qué quieres consultar hoy?
      </h1>
      <p className="mt-2 max-w-lg text-fg-muted">
        Soy el asistente de tableros del S.E.S. Hospital Universitario de Caldas. Pregúntame por cifras e indicadores
        sin tener que entrar a Power BI.
      </p>

      <h2 className="mt-7 font-body text-xs font-bold tracking-wide text-fg-muted uppercase">Prueba con</h2>
      <ul className="mt-3 flex flex-wrap justify-center gap-2">
        {contenido.ejemplos.map((e) => (
          <li key={e.texto}>
            <button
              type="button"
              disabled={deshabilitado}
              onClick={() => alPreguntar(e.texto)}
              className="min-h-11 rounded-pill border border-info-border bg-surface-3 px-4 py-2 text-sm font-semibold text-link transition-colors hover:border-primary hover:bg-primary hover:text-on-primary disabled:cursor-not-allowed disabled:opacity-50"
            >
              {e.texto}
            </button>
          </li>
        ))}
      </ul>
      <ul
        className={`mt-10 grid w-full gap-3 text-left sm:grid-cols-3 ${datos ? "" : "opacity-0"} transition-opacity duration-300`}
      >
        {contenido.capacidades.map((c) => (
          <li key={c.titulo} className="rounded-lg border border-border bg-surface p-4 shadow-sm">
            <h2 className="text-sm font-semibold">{c.titulo}</h2>
            <p className="mt-1 text-sm text-fg-muted">{c.descripcion}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

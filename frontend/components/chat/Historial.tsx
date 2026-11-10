"use client";

import { useEffect, useRef } from "react";
import type { ValorCalificacion } from "@/lib/api/tipos";
import { contrapreguntaActiva, type EstadoChat } from "@/lib/chat/reductor";
import { MensajeAsistente } from "./MensajeAsistente";
import { MensajeUsuario } from "./MensajeUsuario";

interface Props {
  estado: EstadoChat;
  diagnostico: boolean;
  ocupado: boolean;
  alElegirOpcion: (id: string, texto: string) => void;
  alReintentar: (idAsistente: string) => void;
  alCalificar: (idAsistente: string, valor: ValorCalificacion, comentario?: string) => void;
}

/** Historial de la conversación (role="log": los mensajes nuevos se anuncian a lectores de pantalla). */
export function Historial({ estado, diagnostico, ocupado, alElegirOpcion, alReintentar, alCalificar }: Props) {
  const fin = useRef<HTMLDivElement>(null);
  const ultimo = estado.mensajes.at(-1);
  const huella = `${estado.mensajes.length}-${ultimo?.rol === "asistente" ? ultimo.turno.fase : ""}`;

  useEffect(() => {
    const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    fin.current?.scrollIntoView({ behavior: reducido ? "auto" : "smooth", block: "end" });
  }, [huella]);

  return (
    <div
      role="log"
      aria-live="polite"
      aria-relevant="additions"
      aria-label="Conversación"
      className="flex flex-col gap-6"
    >
      {estado.mensajes.map((m) =>
        m.rol === "usuario" ? (
          <MensajeUsuario key={m.id} mensaje={m} />
        ) : (
          <MensajeAsistente
            key={m.id}
            mensaje={m}
            diagnostico={diagnostico}
            ocupado={ocupado}
            contrapreguntaActiva={contrapreguntaActiva(estado, m.id)}
            alElegirOpcion={alElegirOpcion}
            alReintentar={() => alReintentar(m.id)}
            alCalificar={(valor, comentario) => alCalificar(m.id, valor, comentario)}
          />
        ),
      )}
      <div ref={fin} className="h-px" />
    </div>
  );
}

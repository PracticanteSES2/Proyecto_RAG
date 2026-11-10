import type { MensajeUsuario as TipoMensajeUsuario } from "@/lib/chat/reductor";

export function MensajeUsuario({ mensaje }: { mensaje: TipoMensajeUsuario }) {
  return (
    <article aria-label="Tú" className="entrada flex justify-end">
      <p className="max-w-[85%] rounded-bubble rounded-tr-[var(--radius-bubble-tail)] bg-surface-3 px-4 py-2.5 whitespace-pre-wrap text-fg sm:max-w-[80%]">
        {mensaje.texto}
      </p>
    </article>
  );
}

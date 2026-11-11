"use client";

import { useId, useState } from "react";
import type { Propuesta, SolicitudAclaracion } from "@/lib/api/tiposDocumentacion";
import { Aviso } from "@/components/ui/Aviso";
import { Boton } from "@/components/ui/Boton";
import { ListaTextos } from "./ListaTextos";

interface Props {
  propuesta: Propuesta;
  ocupado: boolean;
  alReintentar: (solicitud: SolicitudAclaracion) => void;
  alDescartar: () => void;
}

/** «Hace falta una aclaración»: dudas de MedGemma, página candidata (o detectar) y nota precisada. */
export function AclaracionPropuesta({ propuesta, ocupado, alReintentar, alDescartar }: Props) {
  const conCandidatas = propuesta.candidatas.length > 0;
  // Solo lo que la persona cambió; mientras tanto, lo que propone el backend.
  const [paginaElegida, setPagina] = useState<string | null>(null);
  const [notaEditada, setNota] = useState<string | null>(null);
  const pagina = paginaElegida ?? propuesta.candidatas[0]?.pagina ?? "";
  const nota = notaEditada ?? propuesta.nota;
  const [vacia, setVacia] = useState(false);
  const id = useId();
  const opciones = [{ pagina: "", etiqueta: "Que MedGemma la detecte" }, ...propuesta.candidatas];

  const reintentar = () => {
    setVacia(!nota.trim());
    if (nota.trim()) alReintentar({ nota: nota.trim(), pagina: pagina || null });
  };

  return (
    <section aria-label="Aclaración de la propuesta" className="entrada space-y-4">
      <Aviso tono="aviso" titulo="Hace falta una aclaración. MedGemma no quiso adivinar:">
        <ListaTextos textos={propuesta.dudas.length ? propuesta.dudas : ["La nota es ambigua."]} />
      </Aviso>
      {propuesta.avisos.length > 0 && (
        <Aviso tono="info" titulo="Además:">
          <ListaTextos textos={propuesta.avisos} />
        </Aviso>
      )}
      <fieldset className="space-y-1">
        <legend className="mb-2 text-sm font-semibold text-fg">
          {conCandidatas ? "¿En qué página va el cambio?" : "Elige la página (opcional)"}
        </legend>
        {opciones.map((o) => (
          <label
            key={o.pagina || "detectar"}
            className="flex cursor-pointer items-start gap-2 rounded-sm px-2 py-1 text-sm hover:bg-surface-2"
          >
            <input
              type="radio"
              name={`${id}-pagina`}
              value={o.pagina}
              checked={pagina === o.pagina}
              onChange={() => setPagina(o.pagina)}
              className="mt-1 accent-primary"
            />
            <span>{o.etiqueta}</span>
          </label>
        ))}
      </fieldset>
      <div>
        <label htmlFor={`${id}-nota`} className="mb-1 block text-sm font-semibold text-fg">
          Puedes precisar la nota
        </label>
        <textarea
          id={`${id}-nota`}
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          rows={3}
          aria-invalid={vacia}
          className="w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-fg"
        />
        {vacia && <p className="mt-1 text-sm text-danger">La nota no puede quedar vacía.</p>}
      </div>
      <div className="flex flex-wrap gap-2">
        <Boton variante="primario" onClick={reintentar} disabled={ocupado}>
          Reintentar
        </Boton>
        <Boton onClick={alDescartar} disabled={ocupado}>
          Descartar
        </Boton>
      </div>
    </section>
  );
}

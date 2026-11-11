"use client";

import { useId, useState } from "react";
import type { Propuesta } from "@/lib/api/tiposDocumentacion";
import { Aviso } from "@/components/ui/Aviso";
import { Boton } from "@/components/ui/Boton";
import { IconoReintentar } from "@/components/ui/Iconos";
import { DiffPropuesta } from "./DiffPropuesta";
import { ListaTextos } from "./ListaTextos";
import { OperacionesPropuesta } from "./OperacionesPropuesta";

interface Props {
  propuesta: Propuesta;
  autor: string;
  alCambiarAutor: (autor: string) => void;
  ocupado: boolean;
  alCorregir: (textos: { indice: number; texto: string }[]) => void;
  alAprobar: (autor: string) => void;
  alRechazar: () => void;
}

/** Revisión de una propuesta lista: operaciones (corregibles), avisos, diff, formato y aprobar con autor. */
export function RevisionPropuesta(props: Props) {
  const { propuesta, autor, alCambiarAutor, ocupado, alCorregir, alAprobar, alRechazar } = props;
  const [ediciones, setEdiciones] = useState<Record<number, string>>({});
  const [sinAutor, setSinAutor] = useState(false);
  const id = useId();
  const cambiadas = propuesta.operaciones.flatMap((op) => {
    const texto = ediciones[op.indice];
    return texto !== undefined && texto.trim() !== op.texto.trim() ? [{ indice: op.indice, texto }] : [];
  });
  const pendientes = cambiadas.length > 0;

  const aprobar = () => {
    setSinAutor(!autor.trim());
    if (autor.trim()) alAprobar(autor.trim());
  };

  return (
    <section aria-labelledby={`${id}-titulo`} className="entrada space-y-5">
      <header className="space-y-1">
        <h2 id={`${id}-titulo`} className="text-lg font-semibold">
          Revisión de la propuesta
        </h2>
        <p className="text-xs text-fg-muted">
          Nota: «{propuesta.nota}»{propuesta.tiempos && ` · ${propuesta.tiempos}`}
        </p>
        <p className="text-sm">
          <strong>Página:</strong> {propuesta.pagina}
          {propuesta.nombre_funcional && ` — ${propuesta.nombre_funcional}`}
        </p>
        {propuesta.como_se_eligio && (
          <p className="text-xs text-fg-muted">Cómo se eligió la página: {propuesta.como_se_eligio}.</p>
        )}
        {propuesta.resumen && (
          <p className="text-sm">
            <strong>Resumen:</strong> {propuesta.resumen}
          </p>
        )}
      </header>

      {propuesta.dudas.length > 0 && (
        <Aviso tono="aviso" titulo="MedGemma dejó estas dudas; revísalas antes de aprobar">
          <ListaTextos textos={propuesta.dudas} />
        </Aviso>
      )}

      <OperacionesPropuesta
        operaciones={propuesta.operaciones}
        ediciones={ediciones}
        alEditar={(indice, texto) => setEdiciones((actual) => ({ ...actual, [indice]: texto }))}
        deshabilitado={ocupado}
      />
      {pendientes && (
        <Aviso tono="info" titulo="Corregiste el texto de una operación.">
          <p>Pulsa «Actualizar vista previa» para ver el resultado; solo entonces se puede aprobar.</p>
          <Boton className="mt-2" disabled={ocupado} onClick={() => alCorregir(cambiadas)}>
            <IconoReintentar tamano={14} />
            Actualizar vista previa
          </Boton>
        </Aviso>
      )}

      {propuesta.avisos.length > 0 && (
        <Aviso tono="aviso" titulo={`Revisa esto antes de aprobar (${propuesta.avisos.length})`}>
          <ListaTextos textos={propuesta.avisos} />
        </Aviso>
      )}

      <DiffPropuesta propuesta={propuesta} />

      {propuesta.formato_valido ? (
        <Aviso tono="exito" titulo="El resultado cumple el formato" />
      ) : (
        <Aviso tono="error" titulo="El resultado no cumple el formato:">
          <ListaTextos textos={propuesta.errores_formato} />
        </Aviso>
      )}

      <div className="space-y-3 rounded-lg border border-border bg-surface-2 p-4">
        <label htmlFor={`${id}-autor`} className="block text-sm font-semibold text-fg">
          Aprueba
        </label>
        <input
          id={`${id}-autor`}
          value={autor}
          onChange={(e) => alCambiarAutor(e.target.value)}
          maxLength={120}
          aria-invalid={sinAutor}
          placeholder="Tu nombre"
          className="w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-fg sm:max-w-sm"
        />
        {sinAutor && <p className="text-sm text-danger">Escribe quién aprueba el cambio.</p>}
        <div className="flex flex-wrap gap-2">
          <Boton variante="primario" onClick={aprobar} disabled={ocupado || pendientes || !propuesta.puede_aprobar}>
            Aprobar y guardar
          </Boton>
          <Boton onClick={alRechazar} disabled={ocupado}>
            Rechazar
          </Boton>
        </div>
      </div>
    </section>
  );
}

"use client";

import { useId, useState, type FormEvent } from "react";
import type { PaginaResumen, SolicitudPropuesta } from "@/lib/api/tiposDocumentacion";
import { Boton } from "@/components/ui/Boton";

interface Props {
  grupo: string;
  tablero: string;
  paginas: PaginaResumen[];
  /** Página elegida al llegar desde «Proponer un cambio en esta página» ("" = detectar). */
  paginaInicial: string;
  autor: string;
  alCambiarAutor: (autor: string) => void;
  ocupado: boolean;
  alEnviar: (solicitud: SolicitudPropuesta) => void;
}

const CAMPO =
  "w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-fg placeholder:text-fg-muted";

/** «¿Qué cambió?»: nota libre, página (o detectar), autor y cambios del PBIP. Nada se guarda hasta aprobar. */
export function FormularioPropuesta(props: Props) {
  const { grupo, tablero, paginas, paginaInicial, autor, alCambiarAutor, ocupado, alEnviar } = props;
  const [nota, setNota] = useState("");
  const [pagina, setPagina] = useState(paginaInicial);
  const [pbip, setPbip] = useState("");
  const [falta, setFalta] = useState(false);
  const id = useId();

  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (!nota.trim()) {
      setFalta(true);
      return;
    }
    setFalta(false);
    const cambios = pbip
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    alEnviar({ nota: nota.trim(), grupo, pagina: pagina || null, cambios_pbip: cambios, autor: autor.trim() });
  };

  return (
    <form onSubmit={enviar} className="space-y-4 rounded-lg border border-border bg-surface p-4 sm:p-5" noValidate>
      <p className="text-sm text-fg-muted">
        Escribe con tus palabras qué cambió en <strong className="text-fg">{tablero}</strong>. MedGemma propone el
        cambio exacto en la documentación y <strong className="text-fg">nada se guarda hasta que lo apruebes</strong>.
      </p>
      <div>
        <label htmlFor={`${id}-nota`} className="mb-1 block text-sm font-semibold text-fg">
          ¿Qué cambió?
        </label>
        <textarea
          id={`${id}-nota`}
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          rows={4}
          maxLength={4000}
          aria-invalid={falta}
          aria-describedby={falta ? `${id}-falta` : undefined}
          placeholder="Ej.: le subí el verde del semáforo de triage II a 20 minutos"
          className={CAMPO}
        />
        {falta && (
          <p id={`${id}-falta`} className="mt-1 text-sm text-danger">
            Para generar la propuesta, escribe qué cambió.
          </p>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-autor`} className="mb-1 block text-sm font-semibold text-fg">
            Tu nombre <span className="font-normal text-fg-muted">(opcional; se pide al aprobar)</span>
          </label>
          <input
            id={`${id}-autor`}
            value={autor}
            onChange={(e) => alCambiarAutor(e.target.value)}
            maxLength={120}
            placeholder="Quién hizo el cambio"
            className={CAMPO}
          />
        </div>
        <div>
          <label htmlFor={`${id}-pagina`} className="mb-1 block text-sm font-semibold text-fg">
            Página
          </label>
          <select id={`${id}-pagina`} value={pagina} onChange={(e) => setPagina(e.target.value)} className={CAMPO}>
            <option value="">Detectar automáticamente</option>
            {paginas.map((p) => (
              <option key={p.archivo} value={p.pagina}>
                {p.etiqueta}
              </option>
            ))}
          </select>
        </div>
      </div>
      <details className="rounded-md bg-surface-2 px-3 py-2">
        <summary className="cursor-pointer text-sm font-semibold text-fg">
          Cambios detectados en el PBIP (opcional)
        </summary>
        <label htmlFor={`${id}-pbip`} className="mt-2 mb-1 block text-xs text-fg-muted">
          Un cambio por línea
        </label>
        <textarea
          id={`${id}-pbip`}
          value={pbip}
          onChange={(e) => setPbip(e.target.value)}
          rows={3}
          placeholder="Página CONSULTAS DIA: se cambió el semáforo de la tabla de atendidos de triage II."
          className={CAMPO}
        />
      </details>
      <Boton type="submit" variante="primario" disabled={ocupado}>
        Generar propuesta
      </Boton>
    </form>
  );
}

import type { Diagnostico, EventoError } from "@/lib/api/tipos";
import type { EstadoTurno } from "@/lib/turno/maquina";
import { LineaTiempo } from "./LineaTiempo";

interface Props {
  turno: EstadoTurno;
}

const CLAVES_PROPIAS = new Set(["dax", "razonamiento", "tiempos"]);

function Bloque({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="mt-3">
      <h4 className="mb-1 font-body text-xs font-bold tracking-wide text-diag uppercase">{titulo}</h4>
      {children}
    </section>
  );
}

function Codigo({ texto }: { texto: string }) {
  return (
    <pre className="max-h-80 overflow-auto rounded-sm bg-surface-code px-3 py-2 font-mono text-xs leading-relaxed text-fg">
      <code>{texto}</code>
    </pre>
  );
}

/** Panel plegable «Detalles técnicos» (solo modo diagnóstico): ruta, tiempos, DAX, razonamiento y el resto. */
export function PanelDiagnostico({ turno }: Props) {
  const diag: Diagnostico = turno.respuesta?.diagnostico ?? {};
  const error: EventoError | undefined = turno.error;
  const resto = Object.fromEntries(Object.entries(diag).filter(([clave]) => !CLAVES_PROPIAS.has(clave)));
  const resumen = [turno.respuesta?.ruta ?? turno.fase, `${turno.segundos.toLocaleString("es-CO")} s`].join(" · ");

  return (
    <details className="group mt-3 rounded-md border-l-[3px] border-diag-border bg-diag-bg px-3 py-2 text-sm">
      <summary className="cursor-pointer font-semibold text-diag select-none">
        Detalles técnicos <span className="font-normal">· {resumen}</span>
      </summary>
      {turno.etapas.length > 0 && <LineaTiempo etapas={turno.etapas} segundos={turno.segundos} />}
      {error && (
        <Bloque titulo="Error">
          <Codigo texto={`${error.codigo}: ${error.mensaje}`} />
        </Bloque>
      )}
      {turno.cola && (
        <Bloque titulo="Cola">
          <Codigo texto={JSON.stringify(turno.cola)} />
        </Bloque>
      )}
      {diag.tiempos && diag.tiempos.length > 0 && (
        <Bloque titulo="Tiempos del servidor">
          <Codigo texto={diag.tiempos.map((t) => `${t.segundos.toFixed(1).padStart(6)} s  ${t.etapa}`).join("\n")} />
        </Bloque>
      )}
      {diag.razonamiento && (
        <Bloque titulo="Razonamiento">
          <Codigo texto={diag.razonamiento} />
        </Bloque>
      )}
      {diag.dax && (
        <Bloque titulo="DAX">
          <Codigo texto={diag.dax} />
        </Bloque>
      )}
      {Object.keys(resto).length > 0 && (
        <Bloque titulo="Más datos">
          <Codigo texto={JSON.stringify(resto, null, 2)} />
        </Bloque>
      )}
      {turno.avisos.length > 0 && (
        <Bloque titulo="Avisos">
          <Codigo texto={JSON.stringify(turno.avisos, null, 2)} />
        </Bloque>
      )}
    </details>
  );
}

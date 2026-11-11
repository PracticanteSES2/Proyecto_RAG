"use client";

import { useEffect, useState } from "react";
import { crearClienteDocumentacion, type ClienteDocumentacion } from "@/lib/api/documentacion";
import { useExplorador } from "@/hooks/useExplorador";
import { usePropuesta } from "@/hooks/usePropuesta";
import { Mascota } from "@/components/ui/Mascota";
import { EncabezadoDocumentacion } from "./EncabezadoDocumentacion";
import { PanelTableros } from "./PanelTableros";
import { SeccionProponer } from "./SeccionProponer";
import { SeccionVer } from "./SeccionVer";
import { SelectorModo, type Modo } from "./SelectorModo";

function Bienvenida() {
  return (
    <section className="entrada mx-auto flex max-w-xl flex-col items-center py-10 text-center">
      <Mascota variante="color_rama" alto={120} />
      <h2 className="mt-4 text-2xl font-semibold">Documentación viva de los tableros</h2>
      <p className="mt-2 text-fg-muted">
        Elige un tablero y una página para ver su ficha, su contenido y el historial de cambios, o propone un cambio
        escribiendo con tus palabras qué cambió. El chat usa la versión nueva en cuanto la apruebas.
      </p>
    </section>
  );
}

/** Página de documentación viva: explorador, documento y el flujo proponer → revisar → aprobar → reindexar. */
export function Documentacion({ cliente: inyectado }: { cliente?: ClienteDocumentacion }) {
  const [cliente] = useState(() => inyectado ?? crearClienteDocumentacion());
  const explorador = useExplorador(cliente);
  const propuestas = usePropuesta(cliente);
  const [seleccion, setSeleccion] = useState<{ grupo: string; archivo: string | null } | null>(null);
  const [modo, setModo] = useState<Modo>("ver");
  const [paginaPropuesta, setPaginaPropuesta] = useState("");
  const [autor, setAutor] = useState("");
  const aprobacion = propuestas.propuesta?.aprobacion;
  const revision = aprobacion?.version ?? 0;
  const grupoAprobado = aprobacion ? propuestas.propuesta?.grupo : undefined;
  const { recargar } = explorador;

  // Tras aprobar, la versión y la validez de las páginas del tablero cambian.
  useEffect(() => {
    if (grupoAprobado) void recargar(grupoAprobado);
  }, [grupoAprobado, revision, recargar]);

  const grupo = explorador.grupos?.find((g) => g.grupo === seleccion?.grupo);
  const paginas = (grupo && explorador.paginas[grupo.grupo]) || [];
  const elegir = (g: string, archivo: string | null) => {
    setSeleccion({ grupo: g, archivo });
    setModo("ver");
  };

  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <EncabezadoDocumentacion />
      <div className="mx-auto grid w-full max-w-7xl flex-1 gap-6 px-4 py-6 md:grid-cols-[18rem_minmax(0,1fr)]">
        <PanelTableros
          grupos={explorador.grupos}
          paginas={explorador.paginas}
          error={explorador.error}
          alReintentar={explorador.reintentar}
          seleccion={seleccion}
          alElegir={elegir}
        />
        <main className="min-w-0">
          {!grupo ? (
            <Bienvenida />
          ) : (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-3">
                <p className="min-w-[14rem] flex-1 font-heading text-sm font-semibold text-fg-muted">
                  {grupo.tablero} · {grupo.paginas} páginas
                </p>
                <SelectorModo modo={modo} alCambiar={setModo} />
              </div>
              {modo === "ver" ? (
                <SeccionVer
                  cliente={cliente}
                  grupo={grupo.grupo}
                  archivo={seleccion?.archivo ?? null}
                  paginas={paginas}
                  revision={revision}
                  alElegir={(archivo) => elegir(grupo.grupo, archivo)}
                  alProponer={(pagina) => {
                    setPaginaPropuesta(pagina);
                    setModo("proponer");
                  }}
                />
              ) : (
                <SeccionProponer
                  grupo={grupo}
                  paginas={paginas}
                  paginaInicial={paginaPropuesta}
                  autor={autor}
                  alCambiarAutor={setAutor}
                  propuestas={propuestas}
                />
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

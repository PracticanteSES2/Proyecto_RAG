"use client";

import { useCallback, useEffect, useState } from "react";
import { mensajeDeError, type ClienteDocumentacion } from "@/lib/api/documentacion";
import type { GrupoDocumentacion, ListaPaginas, PaginaResumen } from "@/lib/api/tiposDocumentacion";

/**
 * Tableros con documentación y sus páginas. Las páginas de todos los tableros se piden en paralelo al cargar, así
 * la búsqueda del explorador encuentra cualquier página. `recargar(grupo)` vuelve a pedir las de un tablero (tras
 * aprobar un cambio cambian versión y validez).
 */
export function useExplorador(cliente: ClienteDocumentacion) {
  const [grupos, setGrupos] = useState<GrupoDocumentacion[] | null>(null);
  const [paginas, setPaginas] = useState<Record<string, PaginaResumen[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let vigente = true;
    const guardarPaginas = (respuestas: PromiseSettledResult<ListaPaginas>[]) => {
      const porGrupo: Record<string, PaginaResumen[]> = {};
      respuestas.forEach((r) => {
        if (r.status === "fulfilled") porGrupo[r.value.grupo] = r.value.paginas;
      });
      if (vigente) setPaginas(porGrupo);
    };
    cliente
      .grupos()
      .then(({ grupos: lista }) => {
        if (!vigente) return;
        setGrupos(lista);
        setError(null);
        return Promise.allSettled(lista.map((g) => cliente.paginas(g.grupo))).then(guardarPaginas);
      })
      .catch((causa: unknown) => {
        if (vigente) setError(mensajeDeError(causa, "No pude cargar la documentación de los tableros"));
      });
    return () => {
      vigente = false;
    };
  }, [cliente, intento]);

  const reintentar = useCallback(() => setIntento((n) => n + 1), []);

  const recargar = useCallback(
    async (grupo: string) => {
      try {
        const lista = await cliente.paginas(grupo);
        setPaginas((actual) => ({ ...actual, [grupo]: lista.paginas }));
      } catch {
        // Se conserva la lista anterior: la página sigue siendo navegable.
      }
    },
    [cliente],
  );

  return { grupos, paginas, error, reintentar, recargar };
}

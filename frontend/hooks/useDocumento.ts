"use client";

import { useEffect, useState } from "react";
import { mensajeDeError, type ClienteDocumentacion } from "@/lib/api/documentacion";
import type { DocumentoPagina } from "@/lib/api/tiposDocumentacion";

interface Estado {
  clave: string;
  documento: DocumentoPagina | null;
  error: string | null;
}

/** Documento de una página. `revision` obliga a volver a pedirlo (p. ej. tras aprobar un cambio). */
export function useDocumento(
  cliente: ClienteDocumentacion,
  grupo: string | null,
  archivo: string | null,
  revision = 0,
) {
  const clave = grupo && archivo ? `${grupo}/${archivo}#${revision}` : "";
  const [estado, setEstado] = useState<Estado>({ clave: "", documento: null, error: null });

  useEffect(() => {
    if (!grupo || !archivo) return;
    let vigente = true;
    cliente
      .documento(grupo, archivo)
      .then((documento) => vigente && setEstado({ clave, documento, error: null }))
      .catch(
        (causa: unknown) =>
          vigente && setEstado({ clave, documento: null, error: mensajeDeError(causa, "No pude abrir esta página") }),
      );
    return () => {
      vigente = false;
    };
  }, [cliente, grupo, archivo, clave]);

  const vigente = estado.clave === clave;
  return {
    documento: vigente ? estado.documento : null,
    error: vigente ? estado.error : null,
    cargando: !!clave && !vigente,
  };
}

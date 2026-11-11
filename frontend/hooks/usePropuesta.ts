"use client";

import { useCallback, useEffect, useState } from "react";
import { mensajeDeError, type ClienteDocumentacion } from "@/lib/api/documentacion";
import type { Propuesta, SolicitudAclaracion, SolicitudPropuesta } from "@/lib/api/tiposDocumentacion";
import { SONDEO_ERROR_MS, SONDEO_MS, debeSondear } from "@/lib/documentacion/estado";
import { iniciarSondeo } from "@/lib/sondeo";

/**
 * Propuesta de cambio en curso: la crea (202), la sondea mientras MedGemma la prepara o mientras se reindexa y expone
 * las acciones de la revisión. Los errores llegan con el mensaje amable del backend.
 */
export function usePropuesta(cliente: ClienteDocumentacion) {
  const [propuesta, setPropuesta] = useState<Propuesta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const id = propuesta?.propuesta_id;
  const sondear = debeSondear(propuesta);

  useEffect(() => {
    if (!sondear || !id) return;
    let vigente = true;
    const cancelar = iniciarSondeo(async () => {
      try {
        const nueva = await cliente.propuesta(id);
        if (vigente) setPropuesta(nueva);
        return SONDEO_MS;
      } catch (causa) {
        if (vigente) setError(mensajeDeError(causa, "No pude consultar la propuesta"));
        return SONDEO_ERROR_MS;
      }
    });
    return () => {
      vigente = false;
      cancelar();
    };
  }, [cliente, id, sondear]);

  const ejecutar = useCallback(async (que: string, accion: () => Promise<Propuesta>) => {
    setEnviando(true);
    setError(null);
    try {
      setPropuesta(await accion());
      return true;
    } catch (causa) {
      setError(mensajeDeError(causa, que));
      return false;
    } finally {
      setEnviando(false);
    }
  }, []);

  const conId = useCallback(
    (que: string, accion: (pid: string) => Promise<Propuesta>) =>
      id ? ejecutar(que, () => accion(id)) : Promise.resolve(false),
    [ejecutar, id],
  );

  return {
    propuesta,
    error,
    enviando,
    proponer: (s: SolicitudPropuesta) => ejecutar("No se pudo enviar la nota", () => cliente.proponer(s)),
    corregir: (textos: { indice: number; texto: string }[]) =>
      conId("No se pudo aplicar tu corrección", (pid) => cliente.corregir(pid, textos)),
    aclarar: (s: SolicitudAclaracion) => conId("No se pudo reintentar", (pid) => cliente.aclarar(pid, s)),
    descartar: () => conId("No se pudo descartar", (pid) => cliente.descartar(pid)),
    aprobar: (autor: string) => conId("No se guardó el cambio", (pid) => cliente.aprobar(pid, autor)),
    reintentarReindexacion: () =>
      conId("No se pudo reintentar la reindexación", async (pid) => {
        if (propuesta) await cliente.reindexar(propuesta.grupo);
        return cliente.propuesta(pid);
      }),
    cerrar: () => {
      setPropuesta(null);
      setError(null);
    },
  };
}

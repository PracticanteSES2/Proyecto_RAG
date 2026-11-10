"use client";

import { useCallback, useEffect, useState } from "react";
import type { ClienteApi } from "@/lib/api/cliente";

export type EstadoSalud = "desconocido" | "ok" | "caido";

const CADA_MS_OK = 60_000;
const CADA_MS_CAIDO = 10_000;

/**
 * Consulta GET /salud al iniciar y periódicamente (más seguido mientras el servidor está caído).
 * `verificar()` reinicia el ciclo y comprueba de inmediato.
 */
export function useSalud(cliente: ClienteApi) {
  const [estado, setEstado] = useState<EstadoSalud>("desconocido");
  const [ciclo, setCiclo] = useState(0);

  useEffect(() => {
    let vigente = true;
    let temporizador: ReturnType<typeof setTimeout>;
    const comprobar = async () => {
      let nuevo: EstadoSalud;
      try {
        await cliente.salud();
        nuevo = "ok";
      } catch {
        nuevo = "caido";
      }
      if (!vigente) return;
      setEstado(nuevo);
      temporizador = setTimeout(comprobar, nuevo === "ok" ? CADA_MS_OK : CADA_MS_CAIDO);
    };
    temporizador = setTimeout(comprobar, 0);
    return () => {
      vigente = false;
      clearTimeout(temporizador);
    };
  }, [cliente, ciclo]);

  const verificar = useCallback(() => setCiclo((n) => n + 1), []);

  return { estado, verificar };
}

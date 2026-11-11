"use client";

import { useCallback, useEffect, useState } from "react";
import type { ClienteApi } from "@/lib/api/cliente";
import { iniciarSondeo } from "@/lib/sondeo";

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

  // El ciclo vive en lib/sondeo.ts: el efecto devuelve su `cancelar`, que limpia el temporizador pendiente y
  // descarta la respuesta en vuelo al desmontar o al reiniciar con `verificar()`.
  useEffect(() => {
    let vigente = true;
    const cancelar = iniciarSondeo(async () => {
      let nuevo: EstadoSalud;
      try {
        await cliente.salud();
        nuevo = "ok";
      } catch {
        nuevo = "caido";
      }
      if (vigente) setEstado(nuevo);
      return nuevo === "ok" ? CADA_MS_OK : CADA_MS_CAIDO;
    });
    return () => {
      vigente = false;
      cancelar();
    };
  }, [cliente, ciclo]);

  const verificar = useCallback(() => setCiclo((n) => n + 1), []);

  return { estado, verificar };
}

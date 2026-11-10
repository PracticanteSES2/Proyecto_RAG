"use client";

import { useCallback, useEffect, useRef } from "react";
import type { ClienteApi } from "@/lib/api/cliente";
import type { SuscripcionEventos } from "@/lib/api/sse";
import type { AccionTurno } from "@/lib/turno/maquina";

export type DespacharTurno = (idAsistente: string, accion: AccionTurno) => void;

/**
 * Conecta la máquina de estados del turno (lib/turno/maquina.ts) con el mundo: abre el flujo SSE de cada turno,
 * reenvía sus eventos, lleva el reloj (tic cada segundo mientras el turno está activo) y permite detenerlo.
 *
 * El flujo sigue abierto después de `respuesta` hasta `fin`, porque `aviso` puede llegar tarde.
 */
export function useTurno(cliente: ClienteApi, despachar: DespacharTurno, idActivo?: string) {
  const suscripciones = useRef(new Map<string, SuscripcionEventos>());
  const detenidos = useRef(new Set<string>());
  const despacharRef = useRef(despachar);

  useEffect(() => {
    despacharRef.current = despachar;
  }, [despachar]);

  // Reloj del turno activo (respaldo de frases de espera y tiempos del modo diagnóstico).
  useEffect(() => {
    if (!idActivo) return;
    const inicio = performance.now();
    const intervalo = setInterval(() => {
      const segundos = Math.round((performance.now() - inicio) / 100) / 10;
      despacharRef.current(idActivo, { tipo: "tic", segundos });
    }, 1000);
    return () => clearInterval(intervalo);
  }, [idActivo]);

  useEffect(() => {
    const abiertas = suscripciones.current;
    return () => {
      abiertas.forEach((s) => s.cerrar());
      abiertas.clear();
    };
  }, []);

  const escuchar = useCallback(
    (idAsistente: string, turnoId: string) => {
      if (detenidos.current.has(idAsistente)) return;
      const suscripcion = cliente.eventosTurno(turnoId, {
        alEvento: (evento) => {
          despacharRef.current(idAsistente, { tipo: "evento", evento });
          if (evento.tipo === "fin") suscripciones.current.delete(idAsistente);
        },
        alDesconectar: () => {
          suscripciones.current.delete(idAsistente);
          despacharRef.current(idAsistente, { tipo: "desconectado" });
        },
      });
      suscripciones.current.set(idAsistente, suscripcion);
    },
    [cliente],
  );

  const detener = useCallback((idAsistente: string) => {
    detenidos.current.add(idAsistente);
    suscripciones.current.get(idAsistente)?.cerrar();
    suscripciones.current.delete(idAsistente);
    despacharRef.current(idAsistente, { tipo: "detenido" });
  }, []);

  const cerrarTodo = useCallback(() => {
    suscripciones.current.forEach((s, id) => {
      detenidos.current.add(id);
      s.cerrar();
    });
    suscripciones.current.clear();
  }, []);

  return { escuchar, detener, cerrarTodo };
}

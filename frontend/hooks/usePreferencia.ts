"use client";

import { useCallback, useSyncExternalStore } from "react";

const EVENTO = "asistente:preferencia";

function leer<T>(clave: string, porDefecto: T): T {
  try {
    const crudo = window.localStorage.getItem(clave);
    return crudo === null ? porDefecto : (JSON.parse(crudo) as T);
  } catch {
    return porDefecto;
  }
}

/** Escribe (o borra con `undefined`) una preferencia y avisa a los suscriptores de la misma pestaña. */
export function escribirPreferencia<T>(clave: string, valor: T | undefined): void {
  try {
    if (valor === undefined) window.localStorage.removeItem(clave);
    else window.localStorage.setItem(clave, JSON.stringify(valor));
  } catch {
    // Almacenamiento bloqueado: la preferencia vive solo en esta sesión.
  }
  window.dispatchEvent(new CustomEvent(EVENTO, { detail: clave }));
}

export function leerPreferencia<T>(clave: string, porDefecto: T): T {
  return typeof window === "undefined" ? porDefecto : leer(clave, porDefecto);
}

function suscribir(aviso: () => void) {
  window.addEventListener("storage", aviso);
  window.addEventListener(EVENTO, aviso);
  return () => {
    window.removeEventListener("storage", aviso);
    window.removeEventListener(EVENTO, aviso);
  };
}

/** Preferencia en localStorage, sincronizada entre componentes y pestañas (valores primitivos). */
export function usePreferencia<T extends string | number | boolean>(clave: string, porDefecto: T) {
  const valor = useSyncExternalStore(
    suscribir,
    () => leer(clave, porDefecto),
    () => porDefecto,
  );
  const cambiar = useCallback((nuevo: T) => escribirPreferencia(clave, nuevo), [clave]);
  return [valor, cambiar] as const;
}

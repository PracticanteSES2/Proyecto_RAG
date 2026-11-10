"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { crearClienteApi, type ClienteApi } from "./cliente";

const ContextoApi = createContext<ClienteApi | null>(null);

/** Provee el cliente de la API a los componentes (en pruebas se inyecta uno falso). */
export function ProveedorApi({ cliente, children }: { cliente?: ClienteApi; children: ReactNode }) {
  const [valor] = useState<ClienteApi>(() => cliente ?? crearClienteApi());
  return <ContextoApi.Provider value={valor}>{children}</ContextoApi.Provider>;
}

export function useApi(): ClienteApi {
  const cliente = useContext(ContextoApi);
  if (!cliente) throw new Error("useApi debe usarse dentro de <ProveedorApi>");
  return cliente;
}

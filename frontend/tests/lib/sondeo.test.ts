import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSalud } from "@/hooks/useSalud";
import type { ClienteApi } from "@/lib/api/cliente";
import { iniciarSondeo } from "@/lib/sondeo";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("iniciarSondeo", () => {
  it("ejecuta enseguida y reprograma con la espera que devuelve la tarea", async () => {
    const tarea = vi.fn(async () => 1000);
    const cancelar = iniciarSondeo(tarea);
    await vi.advanceTimersByTimeAsync(0);
    expect(tarea).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(tarea).toHaveBeenCalledTimes(2);
    cancelar();
  });

  it("cancelar limpia el temporizador pendiente: no hay más ejecuciones", async () => {
    const tarea = vi.fn(async () => 1000);
    const cancelar = iniciarSondeo(tarea);
    await vi.advanceTimersByTimeAsync(0);
    cancelar();
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(tarea).toHaveBeenCalledTimes(1);
  });

  it("si se cancela con la tarea en vuelo, no se reprograma", async () => {
    let terminar: (ms: number) => void = () => {};
    const tarea = vi.fn(() => new Promise<number>((resolver) => (terminar = resolver)));
    const cancelar = iniciarSondeo(tarea);
    await vi.advanceTimersByTimeAsync(0);
    cancelar();
    terminar(1000);
    await vi.advanceTimersByTimeAsync(5000);
    expect(tarea).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("useSalud", () => {
  const cliente = (salud: () => Promise<unknown>) => ({ salud }) as unknown as ClienteApi;

  it("al desmontar no deja temporizadores ni vuelve a consultar", async () => {
    const salud = vi.fn(async () => ({}));
    const api = cliente(salud); // estable, como el del contexto de la app
    const { result, unmount } = renderHook(() => useSalud(api));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(result.current.estado).toBe("ok");
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(salud).toHaveBeenCalledTimes(1);
  });

  it("si el servidor falla, vuelve a consultar más seguido", async () => {
    const salud = vi.fn(async () => {
      throw new Error("caído");
    });
    const api = cliente(salud); // estable, como el del contexto de la app
    const { result, unmount } = renderHook(() => useSalud(api));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(result.current.estado).toBe("caido");
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(salud).toHaveBeenCalledTimes(2);
    unmount();
  });
});

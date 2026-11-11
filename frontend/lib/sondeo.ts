/**
 * Sondeo periódico cancelable: ejecuta `tarea` ya mismo y, al terminar, la vuelve a programar tras los
 * milisegundos que ella devuelva. `cancelar()` detiene el ciclo y limpia el temporizador pendiente (también si la
 * tarea estaba en vuelo: su resultado se ignora). Lo usa hooks/useSalud.ts.
 */
export function iniciarSondeo(tarea: () => Promise<number>): () => void {
  let vigente = true;
  let temporizador: ReturnType<typeof setTimeout> | undefined;

  const ejecutar = async () => {
    const esperaMs = await tarea();
    if (!vigente) return;
    temporizador = setTimeout(() => void ejecutar(), esperaMs);
  };

  temporizador = setTimeout(() => void ejecutar(), 0);
  return () => {
    vigente = false;
    if (temporizador !== undefined) clearTimeout(temporizador);
  };
}

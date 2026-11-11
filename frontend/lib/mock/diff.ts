/**
 * Diff por líneas del mock (en el backend lo hace difflib): tramos cambiados con una línea de contexto, como
 * `diff.bloques` del contrato. LCS simple: los documentos del mock tienen pocas decenas de líneas.
 */
import type { LineaDiff } from "@/lib/api/tiposDocumentacion";

function lineasDiff(antes: string, despues: string): LineaDiff[] {
  const a = antes.split("\n");
  const b = despues.split("\n");
  const largo = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  const en = (i: number, j: number) => largo[i]?.[j] ?? 0;
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      largo[i]![j] = a[i] === b[j] ? en(i + 1, j + 1) + 1 : Math.max(en(i + 1, j), en(i, j + 1));
    }
  }
  const salida: LineaDiff[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      salida.push({ tipo: "igual", texto: a[i++]! });
      j++;
    } else if (i < a.length && (j >= b.length || en(i + 1, j) >= en(i, j + 1))) {
      salida.push({ tipo: "sale", texto: a[i++]! });
    } else {
      salida.push({ tipo: "entra", texto: b[j++]! });
    }
  }
  return salida;
}

export function bloquesDiff(antes: string, despues: string, contexto = 1): { lineas: LineaDiff[] }[] {
  const lineas = lineasDiff(antes, despues);
  const cambiadas = lineas.map((l, n) => (l.tipo === "igual" ? -1 : n)).filter((n) => n >= 0);
  const visibles = new Set(
    cambiadas.flatMap((n) => Array.from({ length: 2 * contexto + 1 }, (_, k) => n - contexto + k)),
  );
  const bloques: { lineas: LineaDiff[] }[] = [];
  let anterior = -2;
  lineas.forEach((linea, n) => {
    if (!visibles.has(n)) return;
    if (n !== anterior + 1 || bloques.length === 0) bloques.push({ lineas: [] });
    bloques.at(-1)!.lineas.push(linea);
    anterior = n;
  });
  return bloques;
}

/** [agregadas, eliminadas]. */
export function contarCambios(antes: string, despues: string): [number, number] {
  const lineas = lineasDiff(antes, despues);
  return [lineas.filter((l) => l.tipo === "entra").length, lineas.filter((l) => l.tipo === "sale").length];
}

export function unificado(antes: string, despues: string): string {
  const cuerpo = lineasDiff(antes, despues)
    .filter((l) => l.tipo !== "igual")
    .map((l) => `${l.tipo === "entra" ? "+" : "-"}${l.texto}`);
  return ["--- antes/documento.md", "+++ despues/documento.md", ...cuerpo].join("\n");
}

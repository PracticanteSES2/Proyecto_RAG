/**
 * Guion del mock para la respuesta documental redactada en vivo (eventos `token`): primero el borrador por
 * trozos y luego la respuesta validada que lo reemplaza. Con `conCifraSinRespaldo`, el borrador trae una cifra
 * que la salvaguarda quita de la respuesta final (la interfaz la reemplaza con un fundido).
 * Contrato: specs/003-progreso-chat/contracts/eventos.md (evento `token`).
 */
import {
  armar,
  DEFINICION_EGRESO,
  diagnosticoDe,
  FRASE_SIN_RESPALDO,
  progreso,
  respuestaBase,
  tokens,
  type EntradaGuion,
  type Paso,
  type PasoGuion,
} from "./contenido";

export function guionStreaming(entrada: EntradaGuion, conCifraSinRespaldo: boolean): PasoGuion[] {
  const pasos: Paso[] = [progreso(50, "entendiendo"), progreso(900, "revisando_documentacion")];
  const [primero, ...resto] = DEFINICION_EGRESO.split("\n\n");
  const borrador = conCifraSinRespaldo ? [`${primero}${FRASE_SIN_RESPALDO}`, ...resto].join("\n\n") : DEFINICION_EGRESO;
  const trozos = tokens(2600, borrador);
  const fin = (trozos.at(-1)?.[0] ?? 2600) + 250;
  return armar([
    ...pasos,
    ...trozos,
    progreso(fin - 100, "finalizando"),
    [
      fin,
      "respuesta",
      respuestaBase(entrada, {
        ruta: "rag",
        texto_markdown: DEFINICION_EGRESO,
        fuentes: [{ titulo: "Ficha técnica de indicadores", tablero: "Egresos hospitalarios", pagina: "Definiciones" }],
        diagnostico: diagnosticoDe(entrada, "rag", pasos),
      }),
    ],
    [fin + 20, "fin", {}],
  ]);
}

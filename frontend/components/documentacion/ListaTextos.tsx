/** Lista con viñetas de textos del backend (dudas, avisos, errores). */
export function ListaTextos({ textos }: { textos: string[] }) {
  return (
    <ul className="list-disc pl-5">
      {textos.map((texto) => (
        <li key={texto}>{texto}</li>
      ))}
    </ul>
  );
}

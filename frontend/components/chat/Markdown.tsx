import ReactMarkdown, { type Components } from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

/**
 * Markdown de las respuestas (GFM: tablas, listas, negritas). Sin HTML crudo (react-markdown lo ignora) y además
 * saneado con rehype-sanitize; los enlaces abren en otra pestaña.
 */
const componentes: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="prosa__tabla" role="region" aria-label="Tabla de datos" tabIndex={0}>
      <table>{children}</table>
    </div>
  ),
};

export function Markdown({ texto }: { texto: string }) {
  return (
    <div className="prosa">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]} components={componentes}>
        {texto}
      </ReactMarkdown>
    </div>
  );
}

import type { Metadata } from "next";
import { Documentacion } from "@/components/documentacion/Documentacion";

export const metadata: Metadata = {
  title: "Documentación de tableros · Asistente de tableros",
  description: "Consulta la documentación viva de cada tablero y propone cambios en lenguaje sencillo.",
};

export default function PaginaDocumentacion() {
  return <Documentacion />;
}

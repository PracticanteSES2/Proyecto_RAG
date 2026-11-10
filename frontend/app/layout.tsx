import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Montserrat, Mulish } from "next/font/google";
import "./globals.css";

// next/font descarga las fuentes al compilar y las sirve desde el propio servidor (sin peticiones a Google
// desde el navegador). tokens.css las consume con var(--font-montserrat) / var(--font-mulish) / var(--font-jetbrains).
const montserrat = Montserrat({ subsets: ["latin"], weight: ["600", "700"], variable: "--font-montserrat", display: "swap" });
const mulish = Mulish({ subsets: ["latin"], weight: ["400", "600", "700"], variable: "--font-mulish", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: "Asistente de tableros · S.E.S. Hospital Universitario de Caldas",
  description: "Consulta cifras y documentación de los tableros de Power BI institucionales.",
  icons: { icon: "/marca/isotipo_ses.svg" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "white" },
    { media: "(prefers-color-scheme: dark)", color: "black" },
  ],
};

/** Aplica el tema guardado antes del primer pintado (evita el destello de tema equivocado). */
const SCRIPT_TEMA = `try{var t=JSON.parse(localStorage.getItem("asistente.tema"));if(t==="claro")document.documentElement.dataset.theme="light";else if(t==="oscuro")document.documentElement.dataset.theme="dark";}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es-CO" className={`${montserrat.variable} ${mulish.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: SCRIPT_TEMA }} />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  );
}

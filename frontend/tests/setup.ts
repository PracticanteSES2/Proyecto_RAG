import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());

// jsdom no implementa scrollIntoView ni matchMedia. Las pruebas corren con «movimiento reducido»: las respuestas
// aparecen completas al instante (el revelado con escritura se prueba aparte, en mensaje-asistente.test.tsx).
Element.prototype.scrollIntoView ??= function scrollIntoView() {};
window.matchMedia ??= ((query: string) => ({
  matches: query.includes("prefers-reduced-motion"),
  media: query,
  onchange: null,
  addListener() {},
  removeListener() {},
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;

import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat";

/** Prohíbe colores hexadecimales sueltos: los colores salen de styles/tokens.css. */
const sinHex = {
  selector: "Literal[value=/#[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]/]",
  message: "Usa un token de color (var(--color-…)) de styles/tokens.css, no un hexadecimal.",
};
const sinHexPlantilla = {
  selector: "TemplateElement[value.raw=/#[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]/]",
  message: sinHex.message,
};

const config = [
  ...nextVitals,
  ...nextTs,
  prettier,
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts", "coverage/**"] },
  {
    files: ["components/**/*.{ts,tsx}", "hooks/**/*.{ts,tsx}", "app/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}"],
    rules: { "no-restricted-syntax": ["error", sinHex, sinHexPlantilla] },
  },
];

export default config;

# Tokens de diseño y propuesta de UI (frontend Next.js)

Fuente de verdad de los valores: [`tokens.css`](tokens.css), listo para copiar a `frontend/`. De dónde sale cada color
y cada tipografía: [`identidad_visual.md`](identidad_visual.md). Los contrastes se comprueban con
`python docs/diseno/verificar_contraste.py docs/diseno/tokens.css`, que lee los valores reales del CSS y hoy reporta
**0 fallas**.

**Decisiones clave:**
1. **Primario `#096CB5`** (el azul medio oficial del logotipo) en lugar del `#2B7FB0` actual, que con texto blanco
   da **4.41:1** y **no cumple AA**. El azul de marca `#3A96D3` (3.24:1) queda para ilustraciones, gráficos y
   detalles grandes, nunca como fondo de texto.
2. Texto largo en **neutro oscuro `#1E2A36`** y títulos en **azul profundo `#024573`**, que es el de la barra del
   sitio web. El texto actual de la app (`#185888`) es legible (7.53:1), pero un cuerpo entero en azul cansa en
   respuestas largas.
3. Los cuatro colores del isotipo entran como **acentos** (filete, puntos del indicador "pensando", gráficos). El
   **morado** identifica el **modo diagnóstico**.
4. **Modo oscuro** incluido, que sigue al sistema y se puede forzar con `<html data-theme>`.
5. **Montserrat** (títulos) y **Mulish** (cuerpo) vía `next/font`, ambas presentes en el informe oficial 2025. La
   fuente web oficial, Arlon, es de pago.

## 1. Primitivos de marca

| Token | Hex | Origen |
|---|---|---|
| `--ses-azul` | `#3A96D3` | "S.E.S." del logotipo (web `#3894D1`) |
| `--ses-azul-medio` | `#096CB5` | Puntos fuertes y "Hospital Universitario" (web `#096CB4`) |
| `--ses-azul-profundo` | `#024573` | Encabezado del sitio web |
| `--ses-azul-cielo` | `#7DCCF3` | Puntos claros del logotipo |
| `--ses-morado` / `-fuerte` / `-claro` | `#8D77B1` / `#6D509B` / `#AE92C4` | Isotipo |
| `--ses-coral` / `-fuerte` / `-claro` | `#F08480` / `#E56558` / `#F4B8B3` | Isotipo |
| `--ses-verde` / `-fuerte` / `-claro` | `#8BC160` / `#44AB43` / `#AED289` | Isotipo |
| `--ses-tinta` | `#1E2A36` | Neutro propuesto para el texto |

## 2. Tokens semánticos

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--color-bg` | `#FFFFFF` | `#0E1B26` | Fondo de la página |
| `--color-surface` | `#FFFFFF` | `#122231` | Burbuja del asistente, tarjetas |
| `--color-surface-2` | `#F1F7FC` | `#16293A` | Barra lateral, zonas hundidas |
| `--color-surface-3` | `#EAF4FB` | `#1B3A55` | Burbuja del usuario, chips de ejemplo |
| `--color-surface-code` | `#F4F6F9` | `#1A2633` | DAX, JSON, razonamiento |
| `--color-fg` | `#1E2A36` | `#E6EEF5` | Texto |
| `--color-fg-muted` | `#4A5866` | `#A9BACB` | Texto secundario, metadatos |
| `--color-fg-heading` | `#024573` | `#CFE6F7` | Títulos |
| `--color-primary` | `#096CB5` | `#7DCCF3` | Botón principal, enviar, selección |
| `--color-primary-hover` | `#075A97` | `#A5DCF7` | Hover |
| `--color-primary-active` | `#024573` | `#CFE6F7` | Presionado |
| `--color-on-primary` | `#FFFFFF` | `#0E1B26` | Texto sobre el primario |
| `--color-link` | `#096CB5` | `#7DCCF3` | Enlaces ("Abrir en Power BI") |
| `--color-border` | `#D3E3F0` | `#2A4257` | Separadores decorativos |
| `--color-border-strong` | `#71889D` | `#7F98AE` | Borde de inputs y controles (3:1) |
| `--color-focus` | `#096CB5` | `#7DCCF3` | Anillo de foco |
| `--color-success` / `-bg` / `-border` | `#2F7A2E` / `#EDF6E6` / `#8BC160` | `#8FD18E` / `#16301F` / `#3A8A39` | "Power BI: conectado" |
| `--color-warning` / `-bg` / `-border` | `#8A5300` / `#FFF4DB` / `#EF9B00` | `#F5C26B` / `#33270F` / `#8A5300` | "No conectado", avisos |
| `--color-danger` / `-bg` / `-border` | `#B3362C` / `#FDECEA` / `#F08480` | `#F59A92` / `#3A1D1C` / `#B3362C` | Errores |
| `--color-info` / `-bg` / `-border` | `#096CB5` / `#EAF4FB` / `#7DCCF3` | `#7DCCF3` / `#16293A` / `#3A96D3` | Notas, alcance |
| `--color-diag` / `-bg` / `-border` | `#6D509B` / `#F3EFF8` / `#AE92C4` | `#C3B1DB` / `#251E35` / `#6D509B` | **Modo diagnóstico** |
| `--color-chart-1…6` | `#096CB5 #3A8A39 #6D509B #D9564B #3A96D3 #024573` | `#7DCCF3 #8BC160 #AE92C4 #F08480 #3A96D3 #CFE6F7` | Series de gráficos |

El verde (`#8BC160`) y el coral (`#F08480`) del isotipo no llegan a 3:1 sobre blanco (2.12 y 2.52). En gráficos
claros se usan sus versiones oscurecidas `#3A8A39` y `#D9564B`. En modo oscuro sí funcionan los originales.

## 3. Contrastes WCAG 2.2 AA (calculados)

Fórmula de luminancia relativa de WCAG. Mínimos: 4.5:1 para texto normal, 3:1 para componentes de interfaz, foco y
gráficos (criterios 1.4.3 y 1.4.11). Tabla generada por `verificar_contraste.py` sobre `tokens.css`:

| Par (texto / fondo) | Claro | Oscuro | Mínimo |
|---|---|---|---|
| `fg` / `bg` | 14.59:1 | 14.88:1 | 4.5:1 |
| `fg` / `surface` | 14.59:1 | 13.79:1 | 4.5:1 |
| `fg` / `surface-2` | 13.51:1 | 12.68:1 | 4.5:1 |
| `fg` / `surface-3` | 13.08:1 | 10.05:1 | 4.5:1 |
| `fg` / `surface-code` | 13.47:1 | 13.08:1 | 4.5:1 |
| `fg-muted` / `bg` | 7.29:1 | 8.79:1 | 4.5:1 |
| `fg-muted` / `surface` | 7.29:1 | 8.14:1 | 4.5:1 |
| `fg-muted` / `surface-2` | 6.76:1 | 7.49:1 | 4.5:1 |
| `fg-muted` / `surface-3` | 6.54:1 | 5.93:1 | 4.5:1 |
| `fg-heading` / `bg` | 9.99:1 | 13.56:1 | 4.5:1 |
| `fg-heading` / `surface-2` | 9.26:1 | 11.55:1 | 4.5:1 |
| `on-primary` / `primary` | 5.49:1 | 9.81:1 | 4.5:1 |
| `on-primary` / `primary-hover` | 7.20:1 | 11.78:1 | 4.5:1 |
| `on-primary` / `primary-active` | 9.99:1 | 13.56:1 | 4.5:1 |
| `link` / `bg` | 5.49:1 | 9.81:1 | 4.5:1 |
| `link` / `surface` | 5.49:1 | 9.09:1 | 4.5:1 |
| `link` / `surface-2` | 5.09:1 | 8.36:1 | 4.5:1 |
| `link` / `surface-3` | 4.92:1 | 6.62:1 | 4.5:1 |
| `border-strong` / `bg` | 3.68:1 | 5.82:1 | 3:1 |
| `border-strong` / `surface` | 3.68:1 | 5.39:1 | 3:1 |
| `border-strong` / `surface-2` | 3.41:1 | 4.96:1 | 3:1 |
| `border-strong` / `surface-3` | 3.30:1 | 3.93:1 | 3:1 |
| `focus` / `bg` | 5.49:1 | 9.81:1 | 3:1 |
| `focus` / `surface` | 5.49:1 | 9.09:1 | 3:1 |
| `focus` / `surface-2` | 5.09:1 | 8.36:1 | 3:1 |
| `success` / `success-bg` | 4.80:1 | 7.91:1 | 4.5:1 |
| `warning` / `warning-bg` | 5.79:1 | 8.91:1 | 4.5:1 |
| `danger` / `danger-bg` | 5.28:1 | 7.23:1 | 4.5:1 |
| `info` / `info-bg` | 4.92:1 | 8.36:1 | 4.5:1 |
| `diag` / `diag-bg` | 5.66:1 | 8.08:1 | 4.5:1 |
| `fg` / `diag-bg` | 12.86:1 | 13.61:1 | 4.5:1 |
| `fg` / `info-bg` | 13.08:1 | 12.68:1 | 4.5:1 |
| `chart-1` / `bg` | 5.49:1 | 9.81:1 | 3:1 |
| `chart-2` / `bg` | 4.31:1 | 8.22:1 | 3:1 |
| `chart-3` / `bg` | 6.42:1 | 6.41:1 | 3:1 |
| `chart-4` / `bg` | 3.90:1 | 6.91:1 | 3:1 |
| `chart-5` / `bg` | 3.24:1 | 5.39:1 | 3:1 |
| `chart-6` / `bg` | 9.99:1 | 13.56:1 | 3:1 |

Referencia de lo que **no** pasa (para no reintroducirlo): blanco sobre `#2B7FB0` da 4.41, blanco sobre `#3A96D3`
da 3.24, blanco sobre `#3C8FCD` da 3.50, `#44AB43` sobre blanco da 2.94, `#F08480` sobre blanco da 2.52 y `#8BC160`
sobre blanco da 2.12.

## 4. Tipografía

| Rol | Familia | Pesos | Token |
|---|---|---|---|
| Títulos, nombre del asistente, cifras destacadas | **Montserrat** | 600, 700 | `--font-heading` |
| Cuerpo, burbujas, controles | **Mulish** | 400, 600, 700 | `--font-body` |
| DAX, JSON, razonamiento | **JetBrains Mono** (o Cascadia Mono / Consolas del sistema) | 400 | `--font-mono` |

Escala 1.200 sobre 16px: `xs 12`, `sm 14`, `base 16`, `lg 19.2`, `xl 23`, `2xl 27.6`, `3xl 33.2`. Interlineado
1.55 en el cuerpo y 1.2 en los títulos. El cuerpo del chat va siempre a 16px como mínimo.

### `next/font` (Google Fonts, autoalojadas en el build)

`next/font/google` descarga las fuentes **al compilar** y las sirve desde el propio servidor. El navegador del
funcionario no hace peticiones a Google, lo que conviene en una plataforma cerrada.

```tsx
// frontend/app/layout.tsx
import { Montserrat, Mulish, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const montserrat = Montserrat({ subsets: ["latin"], weight: ["600", "700"], variable: "--font-montserrat", display: "swap" });
const mulish = Mulish({ subsets: ["latin"], weight: ["400", "600", "700"], variable: "--font-mulish", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400"], variable: "--font-jetbrains", display: "swap" });

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-CO" className={`${montserrat.variable} ${mulish.variable} ${mono.variable}`} suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
```

`tokens.css` ya consume `var(--font-montserrat)`, `var(--font-mulish)` y `var(--font-jetbrains)`.

### Alternativa local (si la máquina de build no tiene internet, o para Arlon)

```tsx
import localFont from "next/font/local";
// Archivos .woff2 en frontend/app/fonts/ (Montserrat y Mulish: OFL, desde Google Fonts o @fontsource)
const montserrat = localFont({ src: [{ path: "./fonts/Montserrat-SemiBold.woff2", weight: "600" }, { path: "./fonts/Montserrat-Bold.woff2", weight: "700" }], variable: "--font-montserrat", display: "swap" });
const mulish = localFont({ src: "./fonts/Mulish-Variable.woff2", weight: "200 1000", variable: "--font-mulish", display: "swap" });
// Arlon (Marc Lohner) es DE PAGO: solo con la licencia web del hospital, pedida a Comunicaciones.
// const arlon = localFont({ src: "./fonts/Arlon-Regular.woff2", variable: "--font-mulish" });
```

## 5. Radios, espaciado, sombras, movimiento

| Token | Valor | Origen / uso |
|---|---|---|
| `--radius-xs` / `sm` / `md` / `lg` | 4 / 8 / 12 / 18px | Las tarjetas del sitio usan 18px |
| `--radius-pill` | 999px | Botones píldora del sitio (33px); chips y botón de enviar |
| `--radius-bubble` / `--radius-bubble-tail` | 18px / 6px | Burbujas con una esquina "cola" |
| `--space-1…14` | 4, 8, 12, 16, 20, 24, 32, 40, 48, 56px | Base 4 (coincide con la escala por defecto de Tailwind) |
| `--chat-max-width` | 760px | Ancho de lectura cómodo (unos 75 caracteres) |
| `--sidebar-width` | 280px | |
| `--shadow-sm` / `md` / `lg` | Tinte `#024573` al 6–14 % | Elevación suave. En oscuro, negro más denso |
| `--focus-ring` | `0 0 0 2px bg, 0 0 0 4px focus` | Foco visible doble, que funciona sobre cualquier superficie |
| `--motion-fast` / `base` / `slow` | 120 / 200 / 1400ms | `prefers-reduced-motion` las anula |

## 6. Tailwind CSS v4 (`@theme`)

En `globals.css` van los dos `@import` al principio (CSS exige que precedan a cualquier otra regla): primero
`tailwindcss` y después `tokens.css`. Luego viene el bloque `@theme`, que genera las utilidades `bg-surface`,
`text-fg-muted`, `rounded-bubble`, `font-heading`, `shadow-md`, etc. con los valores del modo claro. Los bloques
oscuros de `tokens.css` redefinen esas mismas variables fuera de capas, así que ganan sobre `@layer theme`. Las
utilidades de Tailwind v4 leen `var(--color-…)` en tiempo de ejecución, de modo que el modo oscuro funciona sin el
prefijo `dark:`. Que el `:root` de `tokens.css` repita los valores de `@theme` no hace daño, porque son idénticos. La
base de `tokens.css` está en `@layer base`, así que las utilidades la sobrescriben.

```css
/* frontend/app/globals.css (copiar docs/diseno/tokens.css a frontend/app/tokens.css) */
@import "tailwindcss";
@import "./tokens.css";

@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));

@theme {
  --color-*: initial;                 /* solo la paleta del hospital */
  --color-white: #ffffff;
  --color-transparent: transparent;
  --color-current: currentColor;

  --color-ses-azul: #3a96d3;
  --color-ses-azul-medio: #096cb5;
  --color-ses-azul-profundo: #024573;
  --color-ses-azul-cielo: #7dccf3;
  --color-ses-morado: #8d77b1;
  --color-ses-coral: #f08480;
  --color-ses-verde: #8bc160;

  --color-bg: #ffffff;
  --color-surface: #ffffff;
  --color-surface-2: #f1f7fc;
  --color-surface-3: #eaf4fb;
  --color-surface-code: #f4f6f9;
  --color-fg: #1e2a36;
  --color-fg-muted: #4a5866;
  --color-fg-heading: #024573;
  --color-primary: #096cb5;
  --color-primary-hover: #075a97;
  --color-primary-active: #024573;
  --color-on-primary: #ffffff;
  --color-link: #096cb5;
  --color-border: #d3e3f0;
  --color-border-strong: #71889d;
  --color-focus: #096cb5;
  --color-success: #2f7a2e;  --color-success-bg: #edf6e6;  --color-success-border: #8bc160;
  --color-warning: #8a5300;  --color-warning-bg: #fff4db;  --color-warning-border: #ef9b00;
  --color-danger: #b3362c;   --color-danger-bg: #fdecea;   --color-danger-border: #f08480;
  --color-info: #096cb5;     --color-info-bg: #eaf4fb;     --color-info-border: #7dccf3;
  --color-diag: #6d509b;     --color-diag-bg: #f3eff8;     --color-diag-border: #ae92c4;
  --color-chart-1: #096cb5; --color-chart-2: #3a8a39; --color-chart-3: #6d509b;
  --color-chart-4: #d9564b; --color-chart-5: #3a96d3; --color-chart-6: #024573;

  --font-heading: var(--font-montserrat), "Segoe UI", system-ui, sans-serif;
  --font-body: var(--font-mulish), "Segoe UI", system-ui, sans-serif;
  --font-mono: var(--font-jetbrains), ui-monospace, "Cascadia Mono", Consolas, monospace;
  --font-sans: var(--font-body);

  --text-xs: 0.75rem;   --text-xs--line-height: 1.4;
  --text-sm: 0.875rem;  --text-sm--line-height: 1.45;
  --text-base: 1rem;    --text-base--line-height: 1.55;
  --text-lg: 1.2rem;    --text-lg--line-height: 1.4;
  --text-xl: 1.44rem;   --text-xl--line-height: 1.3;
  --text-2xl: 1.728rem; --text-2xl--line-height: 1.2;
  --text-3xl: 2.074rem; --text-3xl--line-height: 1.15;

  --radius-xs: 4px; --radius-sm: 8px; --radius-md: 12px; --radius-lg: 18px;
  --radius-pill: 999px; --radius-bubble: 18px;

  --spacing: 4px;

  --shadow-sm: 0 1px 2px rgb(2 69 115 / 0.08);
  --shadow-md: 0 1px 2px rgb(2 69 115 / 0.06), 0 4px 12px rgb(2 69 115 / 0.10);
  --shadow-lg: 0 2px 4px rgb(2 69 115 / 0.06), 0 12px 32px rgb(2 69 115 / 0.14);

  --animate-pensando: pensando 1.4s ease-in-out infinite;
  --animate-shimmer: shimmer 1.6s linear infinite;
  @keyframes pensando { 0%, 80%, 100% { transform: translateY(0); opacity: .45 } 40% { transform: translateY(-4px); opacity: 1 } }
  @keyframes shimmer { from { background-position: 200% 0 } to { background-position: -200% 0 } }
}
```

Si se prefiere conservar la paleta por defecto de Tailwind (grises, `red-500`…), basta con quitar la línea
`--color-*: initial;`.

## 7. Propuesta de UI del chat (Next.js)

Equivalencias con la app Streamlit actual (`app.py`): mensajes con contrapreguntas y botones de opción, enlace
"Abrir en Power BI", expander "Razonamiento del asistente", progreso en vivo (`LiveProgress`), "Detalles de la
consulta", modo diagnóstico (estado, etapa, query plan, DAX, calificación 👍/👎), barra lateral con el estado de
MedGemma y Power BI, "Nueva conversación", exportar y "Diagnóstico del servidor".

### 7.1 Layout

```
┌───────────── filete de marca 4px (gradient-marca) ─────────────────────────────┐
│ [logo horizontal]  Asistente de tableros           ● Power BI  ● MedGemma  [☾] │  ← encabezado 64px, bg, borde inferior
├──────────────┬─────────────────────────────────────────────────────────────────┤
│ Barra lateral│                columna de chat (máx. 760px, centrada)            │
│ surface-2    │  (avatar) ┌ burbuja asistente ┐                                  │
│ 280px        │           └───────────────────┘          ┌ burbuja usuario ┐     │
│ · Nueva conv.│                                          └─────────────────┘     │
│ · Historial  │                                                                  │
│ · Modo diag. │                                                                  │
│ · Exportar   │  ┌ compositor fijo abajo: textarea + botón enviar (píldora) ┐   │
│ · Diag. serv.│  └──────────────────────────────────────────────────────────┘   │
└──────────────┴─────────────────────────────────────────────────────────────────┘
```

- **Encabezado:** `logo_ses_horizontal_oficial.png` a 32-36px de alto (en oscuro, la versión en blanco o el
  isotipo monocromo más el texto), título "Asistente de tableros" en Montserrat 600 `text-lg text-fg-heading`, y a la
  derecha **pastillas de estado** (punto de color más texto, nunca solo color): "Power BI conectado"
  (`success`) o "Power BI sin conexión" (`warning`). El conmutador de tema va al final.
- **Filete de marca:** `height: 4px; background: var(--gradient-marca)` arriba del todo, con los cuatro colores del
  isotipo. Sustituye el filete tricolor de `estilo.py`, que dejaba fuera el morado.
- **Barra lateral** en `surface-2`, que se colapsa en un cajón por debajo de 1024px. "Nueva conversación" es un botón
  secundario (borde `border-strong`, radio píldora). El modo diagnóstico es un *switch* con etiqueta y una nota de
  ayuda.
- **Compositor:** `textarea` que crece hasta 6 líneas, borde `border-strong`, `radius-lg`, foco con `--focus-ring`,
  y botón enviar circular `bg-primary text-on-primary` con icono de flecha (Lucide `ArrowUp`, trazo de 2px).
  `Enter` envía y `Shift+Enter` hace salto de línea. Debajo, en `text-xs text-fg-muted`: *"Respondo solo con
  información de los tableros y documentos institucionales."*

### 7.2 Burbujas

| | Asistente | Usuario |
|---|---|---|
| Alineación | Izquierda, con avatar de 32px | Derecha, sin avatar |
| Fondo / borde | `surface` + `1px border` + `shadow-sm` | `surface-3`, sin borde |
| Radio | `18px` con la esquina superior izquierda en `6px` | `18px` con la esquina superior derecha en `6px` |
| Ancho máximo | 100 % de la columna (tablas y listas) | 80 % |
| Tipografía | Mulish 16/1.55, `fg`. Cifras clave en `font-semibold` | Igual |
| Pie | Enlace "Abrir en Power BI ›" (`link`, subrayado al hover) y botón "Razonamiento" | Hora en `text-xs fg-muted` |

```css
.burbuja { padding: var(--space-3) var(--space-4); border-radius: var(--radius-bubble); max-width: 100%; }
.burbuja--asistente { background: var(--color-surface); border: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm); border-top-left-radius: var(--radius-bubble-tail); }
.burbuja--usuario { background: var(--color-surface-3); margin-left: auto; max-width: 80%;
  border-top-right-radius: var(--radius-bubble-tail); }
.burbuja table { border-collapse: collapse; font-variant-numeric: tabular-nums; }
.burbuja th { color: var(--color-fg-heading); text-align: left; border-bottom: 2px solid var(--color-border); }
.burbuja td { border-bottom: 1px solid var(--color-border); padding: var(--space-1) var(--space-3); }
```

- **Contrapreguntas:** las opciones van como **chips** píldora (`surface-3`, borde `info-border`, texto `link`,
  hover `primary` con `on-primary`), con su descripción corta en `text-sm fg-muted` debajo. Una vez respondida, las
  opciones quedan como lista atenuada y sin interacción (como `render_past_options`).
- **Errores** dentro de la burbuja: banda `danger-bg` con borde izquierdo de 3px `danger-border`, icono y texto en
  lenguaje llano ("No pude completar la consulta…"). El detalle técnico solo aparece en modo diagnóstico.
- **Fuera de alcance:** nota `info` con la sonrisa en `currentColor`.

### 7.3 Avatar del asistente

- Archivo `assets/marca/propuestas/avatar_asistente.svg`: sonrisa blanca sobre círculo `#096CB5`. Se probó a 24, 32
  y 64px y es legible en los tres tamaños. En el chat va a **32px**, alineado con la primera línea de la burbuja y
  con `alt=""` (es decorativo: el rol ya lo anuncia el `aria-label` del mensaje, "Asistente").
- Como componente React, copiar el contenido del SVG a `AvatarAsistente.tsx`. No tiene `id` ni `<style>`, así que se
  pueden repetir instancias sin conflicto. En modo oscuro se mantiene igual (el azul sobre `#0E1B26` se distingue).
- Mientras el asistente piensa, el avatar puede llevar un anillo `ses-azul-cielo` que respira (`opacity`
  0.4 → 1, 1.4s). Con `prefers-reduced-motion` queda fijo.

### 7.4 Estado vacío (conversación nueva)

```
            [isotipo_ses.svg 96px]
     Hola, soy el asistente de tableros del
       S.E.S. Hospital Universitario de Caldas        ← Montserrat 700 text-2xl fg-heading
  Pregúntame por indicadores, filtros y datos de      ← Mulish text-base fg-muted
  los tableros de Power BI institucionales.

  ┌ ¿Cuántas cirugías se cancelaron por especialidad en 2025? ┐  ┌ Cirugías programadas y realizadas en 2024 ┐
  ┌ Camas por estado ┐  ┌ ¿Cuántos registros y cuánto peso hubo en lavandería en enero de 2026? ┐
  ┌ ¿Qué indicadores tiene el tablero quirúrgico? ┐
```

- Los ejemplos son **botones** (chips `surface-3`, `radius-pill`, `text-sm`) que envían la pregunta al pulsarse.
  Salen de consultas reales del conjunto de pruebas (`tests/`). Lo ideal es que el *backend* entregue la lista según
  los tableros cargados.
- El patrón decorativo del isotipo (como `fondo-logo-pattern.jpg` del sitio) puede ir de fondo, recortado en una
  esquina al 8-10 % de opacidad y solo en el estado vacío.
- **Sin resultados** (la consulta no encontró datos): ilustración `estado_sin_resultados.svg` a 120px dentro de la
  burbuja, más sugerencias de reformulación como chips.

### 7.5 Indicador "pensando"

El backend reporta pasos en vivo (`LiveProgress`: etapa y segundos transcurridos). La propuesta:

1. **Burbuja provisional** del asistente con **cuatro puntos** en azul, morado, coral y verde (los "ojos" del
   isotipo) que saltan en secuencia, y al lado el **paso actual** en `text-sm fg-muted` ("Buscando la métrica en el
   catálogo…", "Consultando Power BI…") con el cronómetro (`12 s`). Así se distingue lentitud de bloqueo, igual que
   hoy.
2. Debajo, **dos líneas *skeleton*** con *shimmer* (degradado `surface-2` → `surface-3` → `surface-2`) donde aparecerá
   la respuesta.
3. Más de 20 s: nota adicional "Esto está tardando más de lo normal". Más de 60 s: botón "Cancelar".
4. `aria-live="polite"` en el texto del paso (no en los puntos). Con `prefers-reduced-motion`, los puntos quedan
   fijos y el *shimmer* se apaga.

```tsx
const PUNTOS = ["var(--ses-azul)", "var(--ses-morado)", "var(--ses-coral)", "var(--ses-verde)"];
export function Pensando({ paso, segundos }: { paso: string; segundos: number }) {
  return (
    <div className="burbuja burbuja--asistente flex items-center gap-3" role="status">
      <span className="flex gap-1" aria-hidden="true">
        {PUNTOS.map((c, i) => (
          <span key={i} className="size-2 rounded-full animate-pensando" style={{ background: c, animationDelay: `${i * 0.15}s` }} />
        ))}
      </span>
      <span className="text-sm text-fg-muted" aria-live="polite">{paso} · {segundos} s</span>
    </div>
  );
}
// Skeleton: <div className="h-3 rounded-sm animate-shimmer"
//   style={{ background: "linear-gradient(90deg, var(--color-surface-2) 25%, var(--color-surface-3) 50%, var(--color-surface-2) 75%)", backgroundSize: "400% 100%" }} />
```

Ilustración grande opcional (por ejemplo, para la primera carga del modelo): `estado_pensando.svg`.

### 7.6 Modo diagnóstico

Pensado para el desarrollador, no para el funcionario. Se activa en la barra lateral, se recuerda en `localStorage` y
se identifica en **morado** (`--color-diag*`), un color que no aparece en ninguna otra parte de la UI:

- **Señal global:** con el modo activo, una franja de 3px `diag-border` bajo el encabezado y una pastilla
  "Diagnóstico" (`diag-bg` / `diag`) junto al título. Así nunca se confunde con la vista normal en una captura.
- **Por mensaje:** bajo cada respuesta, un panel plegable `<details>` con fondo `diag-bg`, borde izquierdo de 3px
  `diag-border` y título "Diagnóstico · {estado} · {etapa} · {ms}". Dentro, en pestañas o secciones: Estado, Etapa,
  Ruta, Query plan (JSON con resaltado), Dimensiones, Filtros de negocio y filtros del tablero, **DAX** (bloque
  `surface-code`, `font-mono text-sm`, botón copiar) y Contexto multi-modelo. Los errores técnicos (`type: mensaje`)
  van aquí en `danger`.
- **Pasos con tiempos:** la lista completa de `LiveProgress` con la duración de cada paso queda visible y desplegada
  al terminar. Fuera del modo diagnóstico se colapsa en "Listo en 4.2 s".
- **Calificación 👍/👎:** solo en modo diagnóstico, como hoy (`mostrar_calificacion`). Botones fantasma de 32px; el 👎
  abre un campo "¿Qué esperabas?".
- **Razonamiento del asistente:** disponible siempre como botón discreto ("Cómo llegué a esta respuesta"). En modo
  diagnóstico se abre por defecto.
- **Diagnóstico del servidor:** sección de la barra lateral, visible solo con el modo activo.

### 7.7 Accesibilidad mínima

- Lista de mensajes con `role="log"` y `aria-live="polite"`. Cada mensaje con `aria-label` "Asistente" o "Tú".
- Foco visible en todo lo interactivo (`--focus-ring`). Objetivos táctiles de 44px como mínimo en chips y botones.
- El estado nunca se comunica solo con color: punto, texto e icono.
- Idioma `es-CO`. Cifras con `font-variant-numeric: tabular-nums` en tablas.

## 8. Pendiente de validar con Comunicaciones del hospital

1. La recreación vectorial del isotipo (`isotipo_ses.svg`, `isotipo_ses_monocromo.svg`), o mejor, que entreguen el
   vector oficial.
2. Usar una "sonrisa" del isotipo como avatar y sus variaciones de expresión (`propuestas/`).
3. El barranquero como posible mascota (opción B) y el boceto `barranquero_concepto.svg`.
4. La licencia web de Arlon, o la aprobación de Montserrat y Mulish como sustitutas.
5. Confirmar si existe una mascota usada solo en Facebook o Instagram (no se pudo revisar sin sesión).

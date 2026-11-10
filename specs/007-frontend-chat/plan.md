# Plan de implementación: Frontend web del chat

**Rama**: `agente/frontend-web` | **Fecha**: 2026-11-10 | **Spec**: [spec.md](spec.md)

## Resumen

Chat en Next.js (App Router) que consume la API v1 del backend FastAPI por HTTP + SSE. Todo el acceso a la API
vive en `frontend/lib/api/`; un mock en rutas de Next (`app/api/v1/**`, activo solo con
`NEXT_PUBLIC_API_MOCK=1`) reproduce el flujo completo con eventos temporizados. La lógica (reductor del turno
SSE, reductor del chat, frases de espera) es pura y se prueba con Vitest; los componentes se prueban con
Testing Library.

## Contexto técnico

**Lenguaje/versión**: TypeScript 6.0.3 (estricto) sobre Node 24 LTS.

**Dependencias**: Next.js 16.4.6, React 19.3.1, Tailwind CSS 4.3.5, react-markdown 10.1.0 + remark-gfm 4.0.1 +
rehype-sanitize 6.0.0. Versiones exactas (sin `^`/`~`).

**Pruebas**: Vitest 5.1.0 + jsdom 31 + Testing Library 16.

**Plataforma**: navegadores modernos (Edge/Chrome del hospital), móvil y escritorio.

**Restricciones**: red cerrada → sin fuentes de Google en build (`next/font/google` descartado; pila de fuentes
del sistema en tokens hasta que llegue la tipografía oficial). Sin dependencias de iconos (SVG propios).

## Decisiones

| Decisión | Motivo | Alternativa descartada |
|---|---|---|
| TypeScript 6.0.3 y no 7.x | typescript-eslint 8 admite `<6.1`; TS 7 (nativo) aún no lo soporta | TS 7 |
| ESLint 9.39 y no 10 | eslint-plugin-react / import / jsx-a11y declaran hasta ^9 | ESLint 10 |
| Mock como rutas de Next en las mismas rutas `/api/v1/**` | ejercita el SSE real (EventSource, `Last-Event-ID`) sin cambiar el cliente: solo cambia la URL base | MSW (no intercepta EventSource sin polyfill) |
| EventSource nativo | reconexión y `Last-Event-ID` gratis | fetch + parser propio |
| Reductor del turno puro (`lib/turno/`) | la máquina de estados del SSE se prueba sin DOM ni red | estado disperso en el hook |
| Indicador visible con `animation-delay: 600ms` en CSS | sin temporizadores en JS; si la respuesta llega antes, nunca se pinta | `setTimeout` |
| Tokens en `app/tokens.css` (primitivas de marca → semánticos claro/oscuro → `@theme inline`) | reemplazar la marca sin tocar componentes | colores en componentes |
| Regla ESLint que prohíbe hex en `components/`, `hooks/` y `lib/` | garantiza el punto anterior | revisión manual |

## Estructura

```text
frontend/
├── app/                 # layout, página, tokens.css, globals.css, api/v1/** (mock)
├── components/chat/     # Chat, Historial, MensajeUsuario, MensajeAsistente, IndicadorPensando, Compositor,
│                        # Contrapregunta, Calificacion, PanelDiagnostico, EstadoVacio, AvisoServidor, ...
├── components/ui/       # Boton, Iconos, Mascota, Marca, MenuAjustes, Interruptor
├── hooks/               # useChat, useTurno, useSalud, useTema
├── lib/api/             # tipos.ts, config.ts, cliente.ts, sse.ts
├── lib/turno/           # reductor del turno + frases (puro)
├── lib/chat/            # reductor del chat (puro)
├── lib/mock/            # guiones del mock + almacén en memoria
└── tests/               # Vitest
```

## Revisión de constitución

`.specify/memory/constitution.md` sigue siendo la plantilla: no hay puertas formales. Se aplican las reglas del
proyecto (TDD, verificación antes de cerrar, graphify actualizado).

---
description: "Tareas del frontend web del chat"
---

# Tareas: Frontend web del chat (Next.js)

**Entrada**: `specs/007-frontend-chat/` (spec.md, plan.md, contracts/api-v1.md)

**Pruebas**: obligatorias (TDD) para la lógica pura y los componentes clave.

## Fase 1: Preparación

- [x] T001 Crear `frontend/` con package.json de versiones exactas y `.gitignore`
- [x] T002 [P] Configurar TypeScript estricto (`tsconfig.json`), ESLint (`eslint.config.mjs`, regla sin hex), Vitest (`vitest.config.mts`, `tests/setup.ts`)
- [x] T003 [P] Tailwind v4 + tokens: copiar `docs/diseno/tokens.css` a `styles/tokens.css` y exponerlos con `@theme inline` en `styles/globals.css`
- [x] T004 [P] Marca en `public/marca/` (isotipo, oficial/, mascota/)

## Fase 2: Base (bloqueante)

- [x] T005 Tipos del contrato en `lib/api/tipos.ts` (incluye `espera` y `aviso`)
- [x] T006 Pruebas de configuración, cliente y SSE en `tests/lib/api.test.ts` (rojo)
- [x] T007 `lib/api/config.ts`, `lib/api/cliente.ts` (ErrorApi: saturado/no_encontrado/red/http), `lib/api/sse.ts` (EventSource, colisión del evento «error», reintentos)
- [x] T008 Pruebas de la máquina del turno en `tests/lib/turno.test.ts` (rojo)
- [x] T009 `lib/turno/maquina.ts`: frases, cola, espera de servidor y respaldo del cliente, avisos, estados finales
- [x] T010 Pruebas del reductor del chat en `tests/lib/chat.test.ts` (rojo)
- [x] T011 `lib/chat/reductor.ts`: enviar, opción elegida, calificar, descartar, reiniciar, restaurar

## Fase 3: Historia 1 y 3 — preguntar, pensar y responder (P1)

- [x] T012 [P] Guiones del mock + pruebas (`lib/mock/guiones.ts`, `tests/lib/mock.test.ts`)
- [x] T013 Almacén y rutas del mock en `app/api/v1/**` (SSE con `Last-Event-ID`, 429, caída simulada)
- [x] T014 Hooks `useTurno` (SSE + reloj + detener) y `useChat`
- [x] T015 `IndicadorPensando` (600 ms, fundidos, puntos de marca, renglón de espera, reduced-motion) y `LineaTiempo`
- [x] T016 `MensajeAsistente`, `Markdown` saneado, enlaces Power BI, fuentes, avisos, `AvisoTurno`
- [x] T017 `Compositor` (Enter / Shift+Enter, «Detener»), `Historial` (role=log), `Chat`

## Fase 4: Historia 2 — contrapreguntas (P1)

- [x] T018 `Contrapregunta` (tarjetas, elegida, desactivadas)

## Fase 5: Historias 4 y 5 — calificar, exportar, nueva, estado vacío, salud (P2)

- [x] T019 `Calificacion` (👍 inmediato, 👎 con comentario opcional)
- [x] T020 `MenuAjustes` (tema, diagnóstico, exportar), `Encabezado` (filete, nueva conversación)
- [x] T021 `EstadoVacio` (GET /capacidades con respaldo) y `AvisoServidor` + `useSalud`

## Fase 6: Historia 6 — diagnóstico (P3)

- [x] T022 `PanelDiagnostico` (tiempos, error técnico, DAX, razonamiento, resto en JSON) y franja/píldora morada

## Fase 7: Cierre

- [x] T023 Pruebas de componentes y flujo completo (`tests/componentes/*.test.tsx`)
- [x] T024 lint, typecheck, test y build en verde; capturas con el mock (claro, oscuro, móvil)
- [x] T025 Barranquero oficial (`public/marca/mascota/`): avatar, estado vacío, avisos; marca movida de `assets/marca/` a `frontend/public/marca/`
- [x] T028 Prettier 3.9.10 (`npm run format`, exigido en `npm run lint`) y línea base del doctor para el perfil frontend
- [ ] T026 Integrar con el backend real: tipos generados desde OpenAPI, confirmar supuestos de `contracts/api-v1.md`, CORS
- [ ] T027 Endpoint de cancelación de turno en el backend (hoy «Detener» solo cierra el flujo en el cliente)

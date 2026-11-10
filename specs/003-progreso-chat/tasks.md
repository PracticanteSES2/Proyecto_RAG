---
description: "Tareas del progreso del chat («pensando» amable), independiente de framework"
---

# Tasks: Progreso del chat

**Input**: `specs/003-progreso-chat/` (spec, plan, contracts/eventos.md)

**Tests**: obligatorios (TDD). **Comando**: `.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests/progreso -t .`

## Phase 1: Setup

- [x] T001 Crear `specs/003-progreso-chat/` (spec, plan, tasks, contracts/eventos.md) y `tests/progreso/__init__.py`
- [x] T002 Revertir el trabajo previo sobre Streamlit (`app.py`, `src/ui/progreso.py`, pruebas de AppTest) por el cambio de stack

## Phase 2: Lógica pura (US1)

- [x] T003 Pruebas que fallan: `etapa_de_evento` para todos los títulos de actividad del motor y los ganchos («LLM en cola», «Redactando»); pasos/eventos raros → `None`; catálogo de etapas; ≥3 variantes; textos sin dígitos ni tecnicismos
- [x] T004 Implementar `FRASES`, `ETAPAS`, `etapa_de_evento` en `src/chatbot/progreso.py`
- [x] T005 Pruebas que fallan e implementación de `SelectorFrases` (sin repetir entre turnos ni en el turno, memoria acotada)

## Phase 3: Esperas y carga (US2)

- [x] T006 Pruebas que fallan: `nivel_espera`, `frase_espera` (Power BI, en cola, MedGemma ocupado, no reenviar), `leer_carga_llm` (contadores, `llm_pressure`, fallo)
- [x] T007 Implementar `UMBRALES_ESPERA`, `nivel_espera`, `frase_espera`, `leer_carga_llm`

## Phase 4: Degradación (US3)

- [x] T008 Pruebas que fallan e implementación de `aviso_degradacion` (saturado, sin redacción, sin aviso)

## Phase 5: Traductor y contrato

- [x] T009 Pruebas que fallan de `TraductorProgreso`: `iniciar`, solo al cambiar de etapa, sin DAX ni modelo, frase distinta al volver, `esperando_turno` + `cola`, `tic` por umbral y atrasado, nivel 2 con carga, `finalizar`, `aviso`, JSON, robustez, integración con `ReasoningTrace`
- [x] T010 Implementar `TraductorProgreso` y `evento_cola`
- [x] T011 Correr `tests/progreso` → PASS; commit

## Pendiente (otros agentes)

- [ ] T012 Backend FastAPI: endpoint SSE que use `TraductorProgreso` (ver plan.md, «Integración esperada»)
- [ ] T013 Frontend Next.js: indicador según contracts/eventos.md («Reglas para el frontend»)
- [ ] T014 Carga: `STATS.llm_pressure()` y actividad «LLM en cola»

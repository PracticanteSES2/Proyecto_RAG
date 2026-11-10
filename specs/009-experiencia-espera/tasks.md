---
description: "Tareas de la experiencia de espera: textos sin colas y respuesta en streaming"
---

# Tasks: Experiencia de espera

**Input**: `specs/009-experiencia-espera/` (spec, plan) y `specs/003-progreso-chat/contracts/eventos.md`

**Tests**: obligatorios (TDD). **Comandos**:
`.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests/progreso -t .` ·
`.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests/streaming -t .`

## Phase 1: Setup

- [x] T001 Crear `specs/009-experiencia-espera/` (spec, plan, tasks) y `tests/streaming/__init__.py`

## Phase 2: Textos sin colas (US1, US2, US4)

- [x] T002 Pruebas que fallan en `tests/progreso/test_progreso.py`: vocabulario de cola prohibido en todo el
  catálogo; sin etapa `en_cola`; «LLM en cola» y `esperando_turno` no cambian la etapa; rotación por `tic()`;
  esperas sin carga; aviso neutro; tras el primer token `tic()` calla; evento `token`
- [x] T003 Implementar en `src/chatbot/progreso.py`
- [x] T004 Actualizar `specs/003-progreso-chat/contracts/eventos.md`

## Phase 3: Streaming (US3)

- [x] T005 Pruebas que fallan del proveedor (`tests/streaming/test_proveedor_stream.py`): tokens en orden,
  mismo dict, vacío, plazo total a mitad del stream, callback que lanza, sin `stream` igual que antes
- [x] T006 `MedGemmaProvider.chat(stream=False, on_token=None)`
- [x] T007 Pruebas que fallan de `call_llm(on_token=...)`: pasa al proveedor, protege el callback, proveedor
  sin `on_token`, sin reenvío tras abandono, saturado sin tokens
- [x] T008 `llm_gate.call_llm`
- [x] T009 Pruebas que fallan (`tests/streaming/test_sintesis_stream.py`): `FiltroBorrador`, `escuchar_tokens`,
  `synthesize_rag(on_token)` y `RAGAnswerEngine.answer` (resultado idéntico, tokens, sin evidencia retenida)
- [x] T010 `src/chatbot/respuesta_en_vivo.py`, parámetro `on_token` en la síntesis y el RAG

## Phase 4: Streamlit legado (US5)

- [x] T011 Textos de espera y `TurnBusy` en `app.py`; actualizar `tests/stability/test_stability.py`
- [x] T012 Texto de saturación de `src/docs_md/actualizador.py`; docstrings de `llm_gate`/`runtime_stats`
  («hay N consultas antes que la tuya» → solo diagnóstico)

## Phase 5: Cierre del motor

- [x] T013 Suites del área, doctor (`--verificar`), `graphify update .`, merge de `desarrollo`, commits

## Phase 6: Frontend (cuando `frontend/` esté en `desarrollo`)

- [ ] T014 Quitar textos de cola de la máquina de estados y del indicador
- [ ] T015 Pintar `token` en la burbuja con cursor sutil, sin saltos; reemplazo por la final (plan.md)
- [ ] T016 Revelado rápido de respuestas completas (Power BI)
- [ ] T017 Mock: cola larga sin mencionarla, streaming, degradada; Vitest
- [ ] T018 `lint`, `typecheck`, `test`, `build` en verde; capturas de la espera y del streaming

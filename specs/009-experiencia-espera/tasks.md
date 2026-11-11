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

- [x] T010b `@con_tokens` (respuesta_en_vivo): `QueryEngine.process` y `select_clarification_option` aceptan
  `on_token` (el backend lo detecta por la firma) sin re-indentar el motor (+3 líneas en `query_engine.py`)
- [x] T010c Backend: `EmisorTurno.token` pasa por `TraductorProgreso.token` (silencia `tic`); 503
  `servicio_ocupado` sin «muchas consultas»; descripción SSE con `token` y `cola` solo diagnóstico
- [x] T010d Catálogo de textos a `src/chatbot/frases_progreso.py` (`progreso.py` < 400 líneas)

## Phase 4: Streamlit legado (US5)

- [x] T011 Textos de espera y `TurnBusy` en `app.py`; actualizar `tests/stability/test_stability.py`
- [x] T012 Texto de saturación de `src/docs_md/actualizador.py`; docstrings de `llm_gate`/`runtime_stats`
  («hay N consultas antes que la tuya» → solo diagnóstico)

## Phase 5: Cierre del motor

- [x] T013 Suites del área, doctor (`--verificar`), `graphify update .`, merge de `desarrollo`, commits

## Phase 6: Frontend (cuando `frontend/` esté en `desarrollo`)

- [x] T014 Quitar textos de cola de la máquina de estados (`fraseCola`, etapa `en_cola`), del aviso 429 y del mock;
  `cola` solo se guarda para el panel de diagnóstico
- [x] T015 Pintar `token` en la burbuja con cursor sutil, sin saltos (`RespuestaTurno`: una sola burbuja del borrador
  a la final; si la final empieza por el borrador sigue escribiendo, si no, fundido conservando el alto)
- [x] T016 Revelado rápido de respuestas completas (`lib/turno/revelado.ts`, `hooks/useRevelado.ts`: ≤ 700 ms, por
  palabras, tablas y código enteros, nada con `prefers-reduced-motion` ni en el historial)
- [x] T017 Mock: «cola» (rotación y espera tranquila; `cola` solo con diagnóstico, como el backend), «qué es»
  (streaming), «salvaguarda» (fundido), «documentación» (extractiva con nota neutra); Vitest
- [x] T018 `lint`, `typecheck`, `test`, `build` en verde; capturas de la espera, el streaming y el estado vacío
- [x] T019 Estado vacío compacto en alturas ≤ 940 px y sin tarjetas en el móvil: nada queda bajo la barra de entrada
  en 1280×900, 1280×800, 1366×768 ni 390×844

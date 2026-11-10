# Tasks: Respuestas completas

**Input**: `specs/011-respuestas-truncadas/` (spec.md, plan.md)

**Tests**: TDD — cada bloque empieza por sus pruebas en rojo.

## Phase 1: Inventario

- [x] T001 Inventario de llamadas al LLM con `num_predict`/`num_ctx`/propósito y comportamiento al truncarse (plan.md).

## Phase 2: Presupuesto de tokens (US3)

- [x] T002 Pruebas rojas `tests/rag/test_presupuesto_tokens.py`: `num_predict` por entorno, estimación,
  `ajustar_a_contexto` quita fuentes del final y luego recorta caracteres.
- [x] T003 `src/comun/entorno.py` (reexport en `runtime_stats`) y `src/llm/presupuesto_tokens.py`.

## Phase 3: Corte seguro y continuación (US1, US2)

- [x] T004 Pruebas rojas `tests/rag/test_respuesta_completa.py`: frases, tablas, listas, Markdown anidado,
  decimales, abreviaturas, cierre de bloques, unión de continuación, decisión por presión y tiempo.
- [x] T005 `src/chatbot/respuesta_completa.py`.

## Phase 4: Integración (US1-US4)

- [x] T006 Pruebas rojas de integración: síntesis con doble `done_reason="length"` (corte + aviso, continuación,
  fila → sin continuación, recorte de entrada, diagnóstico en la traza, `cacheable`).
- [x] T007 `answer_synthesizer`, `rag_answer_engine`, línea en `query_engine`, `prompt_eval_count`.
- [x] T008 Reescritura truncada rechazada; descripción de opción truncada cortada o descartada; `num_predict`
  configurable en opciones, reescritura e intención.

## Phase 5: Verificación

- [x] T009 Suites `tests.rag`, `tests.redaccion`, `tests.sim`, `tests.perf`, `tests.context`, `tests.stability`.
- [x] T010 Doctor `--verificar`, `graphify update .`, merge de `desarrollo`.

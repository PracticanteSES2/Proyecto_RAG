# Tasks: Concurrencia con MedGemma

**Input**: `specs/004-concurrencia-llm/` (spec.md, plan.md)

**Tests**: TDD — cada bloque de implementación empieza por sus pruebas en rojo.

## Phase 1: Diagnóstico (US1)

- [x] T001 [US1] Leer puerta, proveedor, sintetizador, reescritor, descriptor, intención LLM, `app.py`
  (motor cacheado, `turn_slot`) y contadores; anotar archivo:línea.
- [x] T002 [US1] Línea base: correr `tests.stability.test_stability` antes de tocar nada.

## Phase 2: Fila justa y API para la UI (US3)

- [x] T003 [US3] Pruebas rojas `tests/perf/test_cola_justa.py`: FIFO de la puerta, posición/`ahead`,
  rendición sale de la fila, contrato (`llm_saturated`, `llm_timeout`, `llm_error`, nunca lanza),
  `ui_progress` (espera larga, callback, presupuesto completo), campos nuevos de `STATS.snapshot()`,
  `turn_slot` FIFO + `queue_snapshot()` + `TURN_LOCK` externo.
- [x] T004 [US3] `FifoLine`, `TURN_LINE`, `queue_snapshot()`, `set_queue_source()` en `src/chatbot/runtime_stats.py`.
- [x] T005 [US3] Fila FIFO, `queue_state()` y `ui_progress()` en `src/llm/llm_gate.py` (docstring = API).
- [x] T006 [US3] `done_reason` en `MedGemmaProvider.chat` (prueba con cliente falso).
- [x] T007 [US3] Verde: `tests.perf.test_cola_justa` y `tests.stability.test_stability`.

## Phase 3: Herramienta de medición (US2)

- [x] T008 [US2] Pruebas rojas `tests/perf/test_carga.py` (simulador: capacidad, cola máxima, timeout,
  truncado, TTFT; métricas p50/p95; CLI con JSON; `--real` sin confirmación no llama; e2e corto).
- [x] T009 [US2] `tools/carga/simulador.py`, `metricas.py`, `escenarios.py`, `runner.py`, `__main__.py`.
- [x] T010 [US2] Línea `/tools/carga/salidas/` al final de `.gitignore`.
- [x] T011 [US2] Verde y corrida simulada de la rampa 1,3,5,10,20 (llm y e2e) para el documento.

## Phase 4: Documento (US1)

- [x] T012 [US1] `docs/arquitectura/concurrencia.md`: diagnóstico, temores con evidencia, resultados,
  opciones por costo/beneficio, Redis sí/no, decisiones del usuario, comando real.

## Phase 4b: Cambio de rumbo (API FastAPI + workers + Redis)

- [x] T015 Pruebas rojas `tests/perf/test_gate_redis.py` (fakeredis): capacidad global entre procesos,
  FIFO entre procesos, préstamo vencido, ticket huérfano, rendición, caída a memoria, SSE.
- [x] T016 `src/llm/gate_backends.py` (MemoriaBackend, RedisBackend) y selección por
  `LLM_GATE_BACKEND`/`REDIS_URL` en `llm_gate.py`; `evento_cola()`, `add_queue_observer()`.
- [x] T017 `STATS.llm_pressure()`; `redis` en requirements.txt, `fakeredis` en requirements-dev.txt.
- [x] T018 Perfil `sonda`, paralelismo observado y parada por errores en `tools/carga`.
- [ ] T019 Medición real (bloqueada por el control de permisos; comando en el documento, sección 4).

## Phase 5: Cierre

- [x] T013 Verificación final (todas las pruebas tocadas) y commits en `agente/carga`.
- [ ] T014 `graphify update .` (CLI no instalado aquí: pendiente para el usuario).

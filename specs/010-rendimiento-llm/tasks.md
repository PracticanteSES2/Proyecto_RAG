# Tasks: Rendimiento con MedGemma

- [x] T001 Pruebas rojas de contadores de costo (`tests/perf/test_costo_llm.py`) → `runtime_stats` + `llm_gate`.
- [x] T002 Pruebas rojas de la caché (`tests/perf/test_cache_llm.py`: LRU, TTL, clave, no guardar
      degradadas/truncadas, agrupar idénticas, almacén caído, Redis con fakeredis) → `src/chatbot/cache_llm.py`,
      `backend/app/services/cache_llm_redis.py`.
- [x] T003 `question_normalizer.clave_pregunta`; `backend/app/services/cache.normalizar_pregunta` la usa.
- [x] T004 Síntesis RAG por la caché (post-proceso intacto; «sin evidencia» no se guarda).
- [x] T005 Pruebas rojas de opciones (`tests/clarification/test_opciones_sin_llm.py`) → caché por opción y
      descripción de catálogo suficiente (`OPTION_DESCRIBER_CATALOGO`).
- [x] T006 Extracto directo opcional (`tests/rag/test_extracto_directo.py`, `RAG_EXTRACTO_DIRECTO`).
- [x] T007 Redis fuera de `src`: `puerta_llm_redis.py` + `llm_gate.registrar_backend`; pruebas de la puerta
      actualizadas (`tests/perf/test_gate_redis.py`).
- [x] T008 `MedGemmaProvider`: `prompt_eval_count`, `MEDGEMMA_NUM_CTX` opcional, `keep_alive` 30m.
- [x] T009 `tools/carga`: modo `componentes`, `--sin-palancas`, costo por turno, salidas en `var/out/carga`,
      motor e2e inyectado desde `tools/manual/carga_e2e.py`; `.gitignore` sin `tools/carga/salidas`.
- [x] T010 Medición antes/después (5/10/20 usuarios) y `docs/arquitectura/concurrencia.md`.
- [x] T011 Suites tocadas, doctor, `graphify update .`, merge de `desarrollo`.

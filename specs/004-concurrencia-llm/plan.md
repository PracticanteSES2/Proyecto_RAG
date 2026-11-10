# Implementation Plan: Concurrencia con MedGemma

**Branch**: `agente/carga` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-concurrencia-llm/spec.md`

## Summary

1. Diagnóstico leído del código (no supuesto) → `docs/arquitectura/concurrencia.md`.
2. Fila justa reutilizable (`FifoLine`, en `runtime_stats.py`) usada por `turn_slot` (capacidad 1, sobre
   `TURN_LOCK`) y por `llm_gate` (capacidad `MEDGEMMA_MAX_CONCURRENT`), con posición consultable
   (`queue_snapshot()`) y campos nuevos en `STATS.snapshot()` (`turn_queue`, `llm_queue`).
3. Modo con progreso en la puerta: `llm_gate.ui_progress(on_queue, queue_wait)` (ContextVar) → espera
   `MEDGEMMA_QUEUE_WAIT_UI` (30 s) y callback con la posición; la espera no resta presupuesto a la llamada.
4. `MedGemmaProvider` devuelve `done_reason` (aditivo) → detectar truncado por `num_predict`.
6. Cambio de rumbo (API FastAPI + workers + Redis): backend enchufable de la puerta
   (`src/llm/gate_backends.py`: `memoria` | `redis`, semáforo distribuido justo con préstamos TTL),
   `evento_cola()` para SSE, `STATS.llm_pressure()`, `add_queue_observer()`.
5. `tools/carga/` (CLI `python -m tools.carga`): simulador de servidor Ollama en proceso, modos `llm` y
   `e2e`, rampas, métricas, tabla + JSON en `tools/carga/salidas/` (ignorada).

## Technical Context

**Language/Version**: Python 3.14 (`.venv`)

**Primary Dependencies**: `ollama` 0.6.3 (httpx), Streamlit; ninguna nueva.

**Storage**: N/A (salidas JSON en carpeta ignorada).

**Testing**: unittest (`.venv\Scripts\python.exe -X utf8 -m unittest tests.perf.test_cola_justa tests.perf.test_carga`)
y el runner propio de `tests.stability.test_stability`.

**Target Platform**: Windows 11, un proceso Streamlit; MedGemma remoto (Ollama) compartido.

**Project Type**: aplicación Streamlit de un solo proyecto.

**Performance Goals**: la fila no añade más de ~1 ms por llamada sin espera.

**Constraints**: contrato de `call_llm` intacto; solo AÑADIR campos a `runtime_stats`; no tocar `app.py`,
`src/ui/`, portero, doctor, raíz salvo una línea en `.gitignore`; nada contra el MedGemma real ni Power BI.

**Scale/Scope**: rampas 1-20 usuarios; 2-3 llamadas al LLM por turno como máximo.

## Constitution Check

| Compuerta | Estado |
|---|---|
| Power BI / BD solo lectura; la herramienta e2e usa el Power BI simulado | ✅ |
| `.env` intocado (las pruebas usan `dotenv` falso; `--real` lo carga el propio proveedor al correrlo el usuario) | ✅ |
| Prueba de carga real solo con permiso explícito (`--real` + confirmación escrita) | ✅ |
| TDD (pruebas antes de la implementación) | ✅ |
| `graphify update .` | ⚠️ CLI no instalado en este entorno; queda para el usuario |

## Project Structure

```text
specs/004-concurrencia-llm/{spec.md, plan.md, tasks.md}
docs/arquitectura/concurrencia.md        # diagnóstico, resultados, opciones, decisiones
src/chatbot/runtime_stats.py             # FifoLine, TURN_LINE, queue_snapshot(), campos nuevos
src/llm/llm_gate.py                      # fila FIFO, queue_state(), ui_progress()
src/llm/medgemma_provider.py             # done_reason (aditivo)
tools/carga/{__init__,__main__,simulador,escenarios,metricas,runner}.py
tests/perf/test_cola_justa.py            # fila justa, contrato, snapshot, turn_slot
tests/perf/test_carga.py                 # simulador, métricas, CLI, confirmación --real, e2e corto
```

**Structure Decision**: la fila vive en `runtime_stats.py` (ya contiene `turn_slot` y lo importa la puerta;
así no hay importación circular). La herramienta va en `tools/carga/` (mantenimiento/medición), sin
dependencias de `app.py` salvo a través del arnés `tests/sim` en modo e2e.

## Complexity Tracking

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| `turn_slot` FIFO además de la puerta | La espera real con N usuarios ocurre en el turno (motor compartido), no en la puerta | Solo la puerta: la UI mostraría posición 0 casi siempre |
| e2e con el motor simulado aun con `--real` | No cargar Power BI real | `app.build_system()` real: tocaría Power BI |

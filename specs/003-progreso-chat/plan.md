# Implementation Plan: Progreso del chat («pensando» amable)

**Branch**: `agente/ui-progreso` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md) | **Contrato**: [contracts/eventos.md](contracts/eventos.md)

## Summary

Módulo Python puro `src/chatbot/progreso.py`, sin dependencias de interfaz:

- `FRASES`/`ETAPAS`: catálogo de etapas reales con variantes de frase.
- `etapa_de_evento`: título de la actividad del motor → etapa (prefijos normalizados).
- `SelectorFrases`: variante menos usada recientemente (memoria por sesión + turno).
- `UMBRALES_ESPERA`, `nivel_espera`, `frase_espera`: mensajes escalonados según etapa y carga.
- `leer_carga_llm`: punto de enganche con `runtime_stats` (no se editan archivos del agente de carga).
- `aviso_degradacion`: nota amable para respuestas documentales extractivas.
- `TraductorProgreso`: por turno, `iniciar`/`traducir`/`esperando_turno`/`tic`/`finalizar`/`aviso` →
  listas de sobres `{"evento", "datos"}` listos para SSE.

Streamlit queda congelado: `app.py` no se toca (el trabajo inicial sobre Streamlit se revirtió por decisión
del usuario). La animación la implementa el frontend Next.js siguiendo el contrato.

## Decisiones

| Tema | Decisión | Por qué |
|---|---|---|
| Ubicación | `src/chatbot/` | Lo consume el backend junto al motor; no depende de la interfaz |
| Granularidad | `progreso` solo al cambiar de etapa | El motor emite muchas actividades seguidas (varias consultas a Power BI); el usuario solo necesita la etapa |
| Esperas | servidor con `tic()` periódico, solo el nivel más alto | El backend no queda bloqueado (motor en hilo); el frontend solo pinta |
| Tiempo | `t` en los datos pero nunca visible | Ordenar y medir sin mostrar segundos |
| Variación | LRU por sesión (12 frases) + sin repetir en el turno | Variedad sin mentir: todas las variantes describen la misma etapa |
| Carga | `llm_pressure()` si existe, si no `STATS.llm` | Desacoplado del agente de carga |
| Errores | ningún método lanza | La vista en vivo nunca tumba el turno |

## Integración esperada en el backend (FastAPI)

```python
traductor = TraductorProgreso(recientes=frases_de_la_sesion)   # lista guardada en Redis por conversación
cola = queue.Queue()
emitir = lambda sobres: [cola.put(s) for s in sobres]
emitir(traductor.iniciar())
engine.set_progress_listener(lambda e: emitir(traductor.traducir(e)))
# hilo del motor: result = engine.process(texto); luego cola.put(FIN)
# generador SSE: get(timeout=1) → yield; en cada timeout: emitir(traductor.tic())
emitir(traductor.finalizar()); emitir(traductor.aviso(result))
```

## Technical Context

**Language/Version**: Python 3.14 (`.venv`) · **Dependencies**: ninguna nueva · **Testing**: unittest
(`python -m unittest discover -s tests/progreso -t .`) · **Constraints**: sin `.env`, sin MedGemma ni Power BI
reales; no tocar `src/llm`, `runtime_stats.py`, `src/chatbot/portero*`, `app.py`.

## Constitution Check

| Compuerta | Estado |
|---|---|
| Power BI / BD solo lectura; el módulo no consulta nada | ✅ |
| Sin datos de pacientes (frases fijas; títulos y DAX del motor nunca salen) | ✅ |
| `.env` intocado | ✅ |
| spec-kit + TDD | ✅ |
| Archivos de otros agentes intocados | ✅ |

## Project Structure

```text
specs/003-progreso-chat/   spec.md · plan.md · tasks.md · contracts/eventos.md
src/chatbot/progreso.py     NUEVO
tests/progreso/             NUEVO: __init__.py, test_progreso.py
```

## Complexity Tracking

Sin violaciones que justificar.

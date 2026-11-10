# Implementation Plan: Portero conversacional

**Branch**: `desarrollo` (sin rama propia) | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-portero-conversacional/spec.md`

**Plan detallado por tareas (TDD)**: [docs/superpowers/plans/2026-11-09-portero-conversacional.md](../../docs/superpowers/plans/2026-11-09-portero-conversacional.md) · **Diseño aprobado**: [docs/superpowers/specs/2026-11-09-portero-conversacional-design.md](../../docs/superpowers/specs/2026-11-09-portero-conversacional-design.md)

## Summary

Antes de buscar, el motor pasa el mensaje normalizado por un clasificador puro: reglas de
frase completa → guardas (número, periodo, vocabulario del catálogo, longitud) → similitud con
el MiniLM ya cargado (umbral + margen frente a preguntas de dominio). Si reconoce charla,
identidad o capacidades, responde con texto fijo (capacidades desde el catálogo en dos grupos)
por la ruta `conversacion`, sin tocar la memoria de seguimiento. Ante duda o fallo, flujo actual.

## Technical Context

**Language/Version**: Python 3.14.7 (`.venv`)

**Primary Dependencies**: sentence-transformers 6.0.1 (MiniLM ya cargado por `HybridRetriever`), Streamlit 1.64.0. Ninguna nueva.

**Storage**: N/A (banco de pruebas en JSON dentro de `tests/portero/`; registro de calificaciones existente)

**Testing**: unittest (`.venv\Scripts\python.exe -X utf8 -m unittest`), simulador `tests.sim.harness`, bancos `tests/real/`

**Target Platform**: Windows 11, app Streamlit local; Power BI remoto solo lectura

**Project Type**: aplicación web Streamlit de un solo proyecto (`src/`, `tests/`, `app.py`)

**Performance Goals**: respuesta conversacional < 1 s; clasificación < 50 ms por mensaje con MiniLM en CPU (vectores de ejemplos precalculados)

**Constraints**: 0 falsos positivos; sin LLM ni servidor compartido; el portero nunca tumba el turno

**Scale/Scope**: ~6 subtipos, 20–30 ejemplos por subtipo; catálogo de 43 modelos + tableros documentados; bancos: 71 + 50 + 50 + 26 conversaciones

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` aún es la plantilla sin rellenar; se aplican como compuertas
las reglas del proyecto (CLAUDE.md) y las restricciones permanentes del usuario:

| Compuerta | Estado |
|---|---|
| Power BI / BD de producción solo lectura; el portero no consulta nada | ✅ |
| Sin datos de pacientes en salidas, logs o commits (textos fijos y nombres de catálogo) | ✅ |
| `.env` intocado; los subagentes no lo cargan | ✅ |
| spec-kit + superpowers (diseño, plan, TDD, revisión) | ✅ en curso |
| Subagentes por rol (investigador, seguridad/integridad, probador adversarial, implementador) | ✅ previsto en implementación |
| `graphify update .` tras editar código | ✅ en cada tarea |
| Sin rama nueva (todo en `desarrollo`) | ✅ |

Re-evaluación tras Fase 1: sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/001-portero-conversacional/
├── plan.md              # Este archivo
├── research.md          # Fase 0
├── data-model.md        # Fase 1
├── quickstart.md        # Fase 1
├── contracts/
│   └── portero.md       # Contrato del módulo y de la ruta `conversacion`
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/chatbot/
├── portero.py           # NUEVO: clasificación, guardas, similitud, catálogo, respuestas
└── query_engine.py      # process(): conexión del portero
src/feedback/registro.py # ruta `conversacion` sin modo estricto
app.py                   # mostrar ruta `conversacion`
tests/portero/
├── __init__.py
├── banco_portero.json   # ~60 conversacionales + ~60 reales cortas
├── test_portero.py      # unitarias + banco + barrido ciego (solo reglas)
├── test_portero_minilm.py  # medición con MiniLM real (skip si no está)
└── test_motor_portero.py   # integración con el motor (simulador)
```

**Structure Decision**: proyecto único existente; el portero es un módulo puro en
`src/chatbot/` (junto al motor que lo consume) para no engordar `query_engine.py`.

## Complexity Tracking

Sin violaciones que justificar.

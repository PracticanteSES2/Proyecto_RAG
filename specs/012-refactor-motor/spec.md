# Feature Specification: Refactor del motor (fases 0, 1, 3 y 4 de docs/ARQUITECTURA.md)

**Feature Branch**: `agente/refactor-motor`

**Created**: 2026-11-10

**Status**: En curso

**Input**: «Reducir el desorden medido por el agente de estructura y el doctor (backend 65,8: tamaño 17,5,
higiene 45, duplicación 66, capas 66) sin cambiar el comportamiento del motor. Ejecutar las fases 0, 1 (sin
`src/fabrica.py`), 3 y 4; dejar la fase 2 (partir `query_engine.py`) lista como guion.»

## Contexto

Otros agentes editan en paralelo `query_engine.py`, `conversation_*.py`, `contextual_rewriter.py`,
`portero*.py`, `progreso.py`, `answer_synthesizer.py`, `rag_answer_engine.py`, `option_describer.py`,
`src/llm/*`, `src/rag/grounding.py`, `app.py`, `backend/`, `frontend/` y `tools/carga`: esta ronda **no los
toca**. Todo lo que ellos importan sigue existiendo en su ruta actual (reexportes de compatibilidad).

## Historias de usuario

### H1 — Andamiaje del repositorio (P1)

Quien llega al repo encuentra un `README.md` (qué es, cómo correr cada parte, enlaces), un `pyproject.toml`
con la configuración de ruff (sin reformatear nada) y una constitución de spec-kit con los principios reales.

**Prueba independiente**: `ruff check src/comun` lee la configuración; el doctor no reporta entradas de raíz
nuevas.

### H2 — Capas en orden (P1)

`src.providers` deja de importar `src.chatbot`: el estado de ejecución (`runtime_stats`) vive en
`src/comun/estadisticas.py` y `src/chatbot/runtime_stats.py` lo reexporta. Los módulos permitidos usan
`src.comun.rutas.RAIZ_PROYECTO` en vez de recalcular la raíz. Los ciclos `ingestion ↔ docs_md`,
`semantic ↔ docs_md` y `semantic ↔ dax` desaparecen.

**Prueba independiente**: un script de grafo de imports (módulo a módulo y paquete a paquete) no encuentra
esos ciclos; el doctor baja sus hallazgos de capas y de «raíz del proyecto».

### H3 — Utilidades canónicas (P2)

`src/comun/texto.py`, `src/comun/json_io.py`, `src/comun/registro.py` (y `src/comun/entorno.py`) concentran
las utilidades duplicadas. Cada sustitución está respaldada por una prueba de equivalencia (vieja vs nueva)
sobre el vocabulario real del catálogo; las variantes que no son equivalentes se quedan, con un comentario
que dice en qué difieren. La librería registra con `logging` en vez de `print`, y los `except Exception: pass`
registran o justifican por qué callan.

**Prueba independiente**: `tests/comun/` (equivalencias y utilidades) en verde; golden master idéntico.

### H4 — Fase 2 lista para ejecutar (P2)

`specs/012-refactor-motor/fase2.md` trae el guion paso a paso para partir `query_engine.py` en mixins, con
rangos de líneas actualizados, orden, pruebas de cada paso y uso del golden master.

## Requisitos

- **RF-001**: Ningún cambio de comportamiento: golden master (`tests.resolution.test_golden`) idéntico a una
  foto tomada el mismo día sobre `desarrollo`.
- **RF-002**: `python -X utf8 -m tools.doctor --verificar` pasa (salvo retrocesos ajenos ya presentes en la
  rama base, que se documentan) y el puntaje backend sube.
- **RF-003**: Ninguna ruta importable desaparece: lo que se mueve deja reexporte.
- **RF-004**: No se tocan los archivos de otros agentes listados en «Contexto».
- **RF-005**: Ni `.env`, ni MedGemma, ni Power BI reales.

## Criterios de éxito

- Capa invertida `providers → chatbot` eliminada; los 3 ciclos rotos.
- Menos hallazgos de `utilidad_repetida`, `print_depuracion`, `except_silencioso` y `mojibake`.
- Fase 2 con guion verificable.

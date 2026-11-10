# Proyecto_RAG — asistente RAG + Power BI del SES Hospital Universitario de Caldas

Asistente administrativo en español que responde preguntas sobre los tableros de Power BI del
hospital: entiende la pregunta, elige el indicador, los filtros y el periodo, consulta el modelo
semántico **en solo lectura** y, cuando la pregunta es documental, responde con la documentación
de los tableros (RAG híbrido sobre Qdrant). El LLM es MedGemma, local.

> Reglas que no cambian: Power BI y bases de datos de producción **solo lectura**; **nada de datos
> de pacientes** en salidas, logs ni commits; el `.env` lo edita solo el usuario.

## Partes del repositorio

| Parte | Qué es | Estado |
| --- | --- | --- |
| `src/` | Motor en Python 3.14: `chatbot` (turno), `semantic` (pregunta → plan), `dax`, `rag`, `providers` (Power BI), `llm`, `docs_md`, `ingestion`, `feedback`, `comun` | Activo |
| `backend/` | API FastAPI + Redis que expone el motor a todo el hospital | En construcción |
| `frontend/` | Next.js (App Router) + TypeScript estricto | En construcción |
| `app.py` · `pages/` · `src/ui/` | Interfaz Streamlit | **Legado congelado** (se retira con la paridad) |
| `tools/` | CLIs de mantenimiento: actualizar el RAG, sincronizar Power BI, doctor de salud | Activo |
| `tests/` | Pruebas por área, arneses (`sim`, `realistic`), bancos reales y golden master | Activo |
| `docs_tableros/` | Documentación de negocio de cada tablero (la lee el RAG) | Activo |

Dónde va cada cosa, capas permitidas y plan de reorganización: [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).
Resumen de reglas: [`CLAUDE.md`](CLAUDE.md) («Estructura y reglas de creación»).

## Preparar el entorno

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt        # producción
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt    # pruebas, ruff, vulture
```

El `.env` (endpoint de Power BI, MedGemma, Qdrant) lo crea y edita el usuario. El propietario de los
tableros actualiza todo con `powershell -ExecutionPolicy Bypass -File .\actualizar_proyecto.ps1`
(pull, dependencias, revisión del `.env` sin mostrar valores, login de Power BI y RAG).

## Cómo correr cada parte

| Qué | Comando |
| --- | --- |
| Regenerar catálogos y RAG (`data/`) | `.venv\Scripts\python.exe tools\update_rag.py "<carpeta de documentación>"` (`--help` para opciones) |
| Login de Power BI por código de dispositivo | `.venv\Scripts\python.exe -m src.providers.powerbi_token login` |
| App Streamlit (legado) | `.venv\Scripts\python.exe -m streamlit run app.py` |
| Backend FastAPI (cuando exista) | `.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload` |
| Frontend Next.js (cuando exista) | `cd frontend; npm ci; npm run dev` |
| Doctor de salud | `.venv\Scripts\python.exe -X utf8 -m tools.doctor --verificar` ([`docs/calidad/doctor.md`](docs/calidad/doctor.md)) |

## Pruebas

```powershell
.venv\Scripts\python.exe -X utf8 -m unittest tests.<área>.test_<tema>     # una suite
.venv\Scripts\python.exe -X utf8 -m tests.<área>.test_<tema>              # suites escritas como script
.venv\Scripts\python.exe -X utf8 -m tests.eval.test_eval                  # banco del simulador
.venv\Scripts\python.exe -X utf8 -m tests.resolution.test_golden          # golden master (~1 h)
```

Los refactors del motor exigen golden master idéntico; las corridas contra Power BI real se lanzan
solo desde el checkout principal (ver [`docs/HANDOFF.md`](docs/HANDOFF.md)).

## Documentación

- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) — estructura, capas, convenciones y plan por fases.
- [`docs/HANDOFF.md`](docs/HANDOFF.md) — estado del trabajo y mediciones de los bancos.
- [`src/semantic/README_motor.md`](src/semantic/README_motor.md) — mapa del motor de resolución por etapas.
- [`src/docs_md/README.md`](src/docs_md/README.md) — documentación viva en Markdown de los tableros.
- [`docs/calidad/doctor.md`](docs/calidad/doctor.md) — doctor de salud y trinquete.
- [`docs/diseno/identidad_visual.md`](docs/diseno/identidad_visual.md) — identidad visual y tokens.
- [`.specify/memory/constitution.md`](.specify/memory/constitution.md) — principios del proyecto (spec-kit); specs en `specs/`.

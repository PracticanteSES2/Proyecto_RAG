## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.

## Reglas del proyecto (definidas por el usuario)

1. **Graphify siempre al día.** Cada vez que haya una actualización del proyecto (código, documentación, merge, pull,
   cambio de rama), actualizar también el grafo: `graphify update .` (y `/graphify . --update` si cambian docs).
   El hook de git (`graphify hook install`) lo hace en commit y checkout, pero no sustituye correrlo tras editar.
2. **Desarrollo con spec-kit + superpowers.** Al desarrollar cualquier funcionalidad o cambio:
   - spec-kit: `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`
     (`/speckit-analyze` antes de implementar).
   - superpowers (`.claude/skills/`): `brainstorming` y `writing-plans` antes de codificar, `test-driven-development`
     al implementar, `systematic-debugging` ante fallos, `verification-before-completion` antes de dar algo por
     terminado y `requesting-code-review` al cerrar. Empezar leyendo `using-superpowers`.

## Trabajo en curso por equipo (leer al abrir la sesión)

- **Equipo con Docker/WSL (propietario)** — si `docker version` responde: tu trabajo es
  `specs/014-infra-docker-wsl/` (Redis real, modo trabajador + API, carga, contenedores, cliente OpenAPI,
  Playwright de paridad). Empieza por `plan.md` §0 y sigue la primera tarea sin `[x]` de `tasks.md`. La sesión
  orquesta e integra; **todo el desarrollo lo hacen agentes** en worktrees `agente/<tema>`.
- **Equipo de desarrollo (sin Docker)**: clasificación de mensajes que no son consultas (saludos, charla,
  preguntas ajenas a los tableros) sin gastar MedGemma, Qdrant ni Power BI. Reservado: `src/chatbot/portero*.py`,
  `src/chatbot/charla*.py`, `tests/portero/`, `specs/015-*`. La otra sesión no los toca.
- Estado y decisiones recientes: `docs/HANDOFF.md` (la entrada de arriba es la más nueva).

## Estructura y reglas de creación

Normativo para personas y agentes. Detalle, tablas y plan por fases: `docs/ARQUITECTURA.md`.

1. **Monorepo.** `backend/` (FastAPI: `app/` = `core/`, `api/v1/`, `schemas/`, `services/` con Redis; `motor/` = destino de `src/`),
   `frontend/` (Next.js App Router + TS estricto), `infra/` (Redis, scripts, servicios), `src/` (motor actual),
   `tools/`, `tests/`, `docs/`, `docs_tableros/` (negocio), `specs/`. **Streamlit** (`app.py`, `pages/`,
   `.streamlit/`, `src/ui/`, `assets/`) está **congelado**: solo arreglos críticos; se borra al alcanzar la
   paridad de `docs/ARQUITECTURA.md` §9.
2. **Dónde crear.** Antes de crear un archivo, ubicarlo en la tabla «Quiero crear X → va en Y» (§5). Prohibido
   dejar archivos sueltos en la raíz: solo se permite la lista blanca de §12. Nada de `utils.py`, `helpers.py`,
   `*_v2.py`, `final*.py`, `nuevo*.py`.
3. **Capas.** Se importa solo hacia abajo: `backend/app → src.chatbot → dominio (semantic, rag, dax, docs_md,
   feedback, ingestion) → providers/llm → src.comun`. `src` nunca importa `backend`, `tools`, `tests`, `app`,
   `pages`, `fastapi`, `redis` ni (fuera del legado) `streamlit`. Los routers de `backend/app/api` llaman a
   `services/`, no al motor directamente.
4. **Frontend.** Sin lógica de negocio (cifras, periodos, filtros y permisos los decide el backend). Llamadas al
   backend solo con el cliente tipado **generado desde OpenAPI** en `frontend/lib/api/` (lo generado no se edita).
   Estructura `app/`, `components/` (`ui/` + una carpeta por funcionalidad), `hooks/`, `lib/`, `styles/`; colores,
   tipografía y espacios solo con tokens de `styles/tokens.css`.
5. **Lo efímero.** Salidas en `var/out/<suite>/`, logs en `var/logs/`, temporales en `var/tmp/` (rutas con
   `src.comun.rutas`; `var/` está ignorada). Sondeos y pruebas de un solo uso: en el scratchpad del agente; si deben
   quedar, en `tools/manual/`. Nunca en `tests/` ni en la raíz.
6. **Reutilizar antes de crear.** Antes de escribir una utilidad (normalizar texto, leer/escribir JSON, rutas,
   logging, entorno, slug) buscarla con Grep en `src/comun/` y en la tabla de §11; si existe una variante, usarla o
   moverla a `src/comun/`. Prohibido recalcular la raíz con `Path(__file__).parents[...]` en código nuevo.
7. **Tamaño.** Archivo Python ≤ 800 líneas (aviso a 400), función ≤ 80 (aviso a 50); TS/TSX ≤ 400, componente
   ≤ 250. Ningún cambio hace crecer un archivo que ya pasa el máximo (p. ej. `query_engine.py`) sin extraer más de
   lo que añade.
8. **Pruebas con cada cambio.** `tests/<área>/test_<tema>.py` nombrado por comportamiento (no `test_r10.py`);
   frontend con Vitest/Playwright. Refactor del motor = golden master idéntico (`tests.resolution.test_golden`).
   Estilo: ruff (Python), ESLint + `tsc --noEmit` (frontend).
9. **Limpieza al terminar.** Borrar temporales, salidas sueltas y `__pycache__` creados fuera de `var/`; `git status`
   limpio salvo lo que se va a commitear; actualizar las referencias (Grep) de lo que se mueva.
10. **Doctor antes de terminar.** Correr el doctor de salud (`tools/doctor/`) antes de dar algo por terminado: ningún
    desarrollo nuevo puede bajar su puntaje (backend ni frontend). Si baja, se corrige o se justifica en el commit.

# Arquitectura del repositorio

Documento **normativo**: dice dónde vive cada cosa, quién puede importar a quién, cómo se nombran los
archivos y en qué orden se reorganiza el código heredado. Lo siguen las personas y todos los agentes.
El resumen corto está en `CLAUDE.md` («Estructura y reglas de creación»); el doctor de salud
(`tools/doctor/`) verifica las reglas de la sección 12.

Estado: 2026-11-10. Decisión vigente: el producto pasa a **backend FastAPI + frontend Next.js + Redis**
para todo el hospital. Streamlit queda **congelado como legado** (sección 9).

---

## 1. Diagnóstico de partida (2026-11-10, commit d7522c8)

| Medida | Valor |
| --- | --- |
| Archivos versionados | 674 (docs_tableros 251, tests 242, src 101, tools 37, .specify 20, specs 8, docs 6, raíz 7) |
| Líneas Python | src 60.305 · tests 45.930 · tools 9.984 · app.py 929 · pages 22 |
| `src/chatbot/query_engine.py` | 7.568 líneas, 334 KB, **una clase con 175 métodos**; `_process` solo mide 736 líneas |
| Archivos de `src` con más de 800 líneas | 28 |
| Funciones de más de 80 líneas / de más de 150 | 146 / 42 (la mayor: `_process`, 736; `build_global_master_metrics`, 701) |
| Funciones que normalizan texto definidas en `src` | **33** (`normalize_text` ×8, `_plain` ×7, `_normalize` ×5, `_fold` ×4, `fold` ×3, …); `unicodedata.normalize` en 41 archivos |
| Lectores de JSON propios en `src` | 11 (`load_json`, `_load_json`, `_leer_json`) |
| Módulos que recalculan la raíz con `Path(__file__).parents[...]` | 15 en `src`/`pages` (más ~60 en `tests` y 10 en `tools`) |
| Módulos de `src` con `if __name__ == "__main__"` y `print()` | 11 módulos, 142 `print()` (scripts de construcción dentro de la librería) |
| Logging | solo 3 módulos de `src` usan `logging`; ninguno lo configura |

Problemas de capas detectados (ver sección 4):

- `src/providers/powerbi_provider.py` y `src/llm/llm_gate.py` importan `src.chatbot.runtime_stats` (capa baja → capa alta).
- Ciclos: `ingestion ↔ docs_md`, `semantic ↔ docs_md`, `semantic ↔ dax` (`dax_validator` → `detail_list`; `multi_model_components` → `dax_validator`).
- `src/semantic` mezcla dos responsabilidades: la **resolución en tiempo de consulta** y la **construcción offline de catálogos**
  (`model_catalog_builder`, `visual_catalog_builder`, `powerbi_catalog_manager`, `global_master_metric_builder`,
  `document_normalizer`, `semantic_merge`).
- Los arneses de prueba (`tests/sim`, `tests/realistic`, `tests/real`, golden master) extraen `build_system()` de
  **`app.py` por AST**: el motor no tiene una fábrica propia, y retirar Streamlit rompería el golden master.
- Interfaz dentro del motor: `src/docs_md/interfaz.py`, `src/feedback/panel.py` y `src/ui/estilo.py` importan `streamlit`.

Código sin uso en producción (no es basura, pero se anota): `src/llm/ollama_provider.py` (solo `tools/manual`),
`src/feedback/lector.py` (solo pruebas; lector para diagnóstico), `src/semantic/powerbi_catalog_manager.py`
(solo herramientas de construcción). Docstring con mojibake en `src/semantic/resolucion/__init__.py`.

---

## 2. Estructura objetivo (monorepo)

```
Proyecto_RAG/
├── backend/                  FastAPI (Python 3.14)
│   ├── app/                  capa HTTP: lo único que conoce FastAPI y Redis
│   │   ├── main.py           crea la app, monta routers, middlewares y lifespan (precalentado del motor)
│   │   ├── core/             config.py (Settings de pydantic-settings; ningún os.environ suelto),
│   │   │                     dependencias.py (Depends: settings, Redis, fachada del motor), registro.py
│   │   ├── api/v1/           routers delgados: chat, conversaciones, documentacion, calificaciones, salud
│   │   ├── schemas/          modelos pydantic de entrada/salida = contrato OpenAPI
│   │   └── services/         cola, cache, limites, conversaciones (Redis) y motor.py (fachada al motor)
│   └── motor/                (FASE 5) el motor que hoy vive en src/: chatbot, semantic, rag, dax, providers,
│                             llm, ingestion, docs_md, feedback, comun
├── frontend/                 Next.js (App Router) + TypeScript estricto
│   ├── app/                  rutas, layouts y páginas (servidor por defecto)
│   ├── components/           ui/ (primitivas) y una carpeta por funcionalidad (chat/, documentacion/, …)
│   ├── hooks/                hooks de cliente (useChat, useProgreso, …)
│   ├── lib/                  api/ (cliente GENERADO desde OpenAPI + envoltorio fetch), utilidades puras
│   ├── styles/               tokens.css (colores, tipografía, espacios) y globals.css
│   ├── public/               logo y marca (destino de assets/)
│   └── tests/ · e2e/         Vitest + Testing Library · Playwright
├── infra/                    redis/ (redis.conf), scripts/ (arranque backend/frontend/Redis), servicios/
│                             (servicio de Windows), docker/ (futuro docker-compose)
├── src/                      motor ACTUAL (hasta la fase 5); backend/app lo importa tal cual
│   └── comun/                utilidades transversales canónicas (rutas hoy; texto, json, registro, entorno después)
├── tools/                    CLI de mantenimiento (update_rag, sync_*, por_confirmar, local_data/, doctor/)
│   └── manual/               sondeos y pruebas manuales de un uso contra servicios reales (no se corren en CI)
├── tests/                    pruebas Python por área (una carpeta por área; ver sección 7)
├── docs/                     ARQUITECTURA.md, HANDOFF.md, superpowers/{specs,plans}, diseno/, adr/ (decisiones)
├── docs_tableros/            documentación de NEGOCIO viva de los tableros (la lee el RAG; no es doc técnica)
├── specs/                    spec-kit (NNN-nombre/spec.md, plan.md, tasks.md…)
├── app.py · pages/ · .streamlit/ · src/ui/     LEGADO Streamlit congelado (sección 9)
├── assets/                   LEGADO: marca usada por Streamlit; se mueve a frontend/public/ al retirar Streamlit
├── var/                      EFÍMERO e ignorado: out/, logs/, tmp/ (sección 6)
├── data/ · tableros/         estado local ignorado (catálogos, Qdrant, metadata, caché del token; PBIP)
├── CLAUDE.md · README.md · requirements.txt · actualizar_proyecto.ps1 · .gitignore
└── .specify/ · .claude/      herramientas (spec-kit versionado; .claude local e ignorado)
```

`assets/` **no sobrevive**: es la marca de Streamlit (`src/ui/estilo.py`, `pages/`). El frontend usa
`frontend/public/`; mientras exista Streamlit se duplica el logo (no se enlaza `public/` desde Python).

---

## 3. Responsabilidad de cada paquete

### Backend y motor (Python)

| Paquete | Responsabilidad | No hace |
| --- | --- | --- |
| `backend/app/api/v1` | Validar la petición (esquema), llamar a UN servicio, devolver el esquema de salida | Lógica de negocio, Redis directo, importar módulos internos del motor |
| `backend/app/core` | Configuración (`config.py`), dependencias e infraestructura transversal de la app | Lógica de negocio |
| `backend/app/schemas` | Contrato público (pydantic). Fuente del OpenAPI que genera el cliente del frontend | Lógica |
| `backend/app/services` | Cola de trabajos, caché, límite de peticiones, estado de conversación (Redis) y la fachada `motor.py` | Resolver preguntas (eso es del motor) |
| `src/chatbot` (→ `motor/chatbot`) | Orquestar un turno: portero, contrapreguntas, seguimientos, ejecución del plan, formato de la respuesta | HTTP, Redis, Streamlit |
| `src/semantic` | Resolución en tiempo de consulta: pregunta → plan (indicador, filtros, periodo, agrupación). `resolucion/` = etapas (mixins) | Construir catálogos (fase 4 los saca a `catalogo/`) |
| `src/rag` | Recuperación híbrida, ranking, extractos, anclaje de cifras | Llamar a Power BI |
| `src/dax` | Generar y validar DAX desde un plan | Elegir indicadores |
| `src/providers` | Power BI (ADOMD, token, enlaces, caché de dominios). Solo lectura | Lógica de conversación |
| `src/llm` | Clientes de LLM (MedGemma/Ollama) y la compuerta de concurrencia | Prompts de negocio (viven en quien los usa) |
| `src/ingestion` · `src/docs_md` | Ingesta de documentos y documentación viva en Markdown (formato, diccionario, PBIP, actualizador, indexación) | UI (la parte Streamlit de `docs_md/interfaz.py` es legado) |
| `src/feedback` | Registro y lectura de calificaciones (JSONL) | UI (`panel.py` es legado) |
| `src/comun` | Utilidades puras y transversales: `rutas` (raíz, data/, var/). Destino de texto, JSON, logging y entorno | Importar cualquier otro paquete del proyecto |
| `tools/` | Scripts de mantenimiento y construcción (catálogos, sincronización, RAG, doctor) | Ser importado por `src` o `backend` |
| `tools/manual/` | Sondeos y pruebas manuales de un uso contra servicios reales | Correr en la batería automática |
| `tests/` | Pruebas automáticas, arneses (`sim`, `realistic`), bancos (`real`, `eval`) y golden master | Ser importado por `src`, `backend` o `tools` (salvo `tools/manual`) |

### Frontend (TypeScript)

| Carpeta | Responsabilidad | Prohibido |
| --- | --- | --- |
| `app/` | Rutas, layouts, carga de datos en Server Components, metadatos | Lógica de negocio, `fetch` a mano fuera de `lib/api` |
| `components/ui/` | Primitivas visuales sin estado de negocio (Botón, Tarjeta, Burbuja…) | Llamar a la API |
| `components/<funcionalidad>/` | Composición de una funcionalidad (chat, documentación, calificaciones) | Reglas del dominio (decidir indicadores, filtros, permisos) |
| `hooks/` | Estado de cliente y suscripciones (progreso, streaming) | Duplicar estado que ya da el backend |
| `lib/api/` | Cliente **generado** desde `/openapi.json` (`lib/api/generado/`, no se edita a mano) + envoltorio de errores | Tipos de la API escritos a mano |
| `lib/` | Utilidades puras (formato de fechas/números es-CO) | Acceso al DOM |
| `styles/` | Tokens CSS (`--color-*`, `--espacio-*`, `--fuente-*`) y estilos globales | Colores o tamaños literales en componentes |

Regla de oro del frontend: **toda decisión de negocio vive en el backend**. El frontend pinta lo que el backend
devuelve (respuesta, botones de contrapregunta, enlaces, progreso) y no recalcula cifras, periodos ni filtros.

---

## 4. Capas y dirección de dependencias

Se importa solo **hacia abajo**. Mismo nivel: permitido solo si no forma un ciclo.

```
  frontend ──HTTP (cliente generado de OpenAPI)──▶ backend/app
  app.py · pages/ (legado)  ·  tools/  ·  tests/          (entradas; nadie las importa)
          │
  backend/app  (api → services → schemas · core)           (única capa con fastapi y redis)
          │
  src.chatbot · src.feedback                                (aplicación: orquestación del turno, calificaciones)
          │
  src.semantic · src.dax · src.docs_md · src.ingestion · src.catalogo   (dominio)
          │
  src.providers · src.llm · src.rag                         (infraestructura: Power BI, LLM, índices)
          │
  src.comun                                                 (base: utilidades puras; no importa nada del proyecto)
```

Prohibido:

1. `src.*` importa `backend`, `tools`, `tests`, `app` o `pages`.
2. `src.*` importa `fastapi`, `redis` o `streamlit` (excepción congelada: `src/ui`, `src/docs_md/interfaz.py`, `src/feedback/panel.py`).
3. `backend/app/api` importa `src.*` directamente (pasa por `backend/app/services/motor.py`).
4. `tools/` importa `tests/` (excepción prevista: `tools/manual/`, que usa los arneses de `tests.real`/`tests.realistic`;
   requiere la extensión `excepto` del doctor, §12).
5. Capas bajas importan altas: `providers`/`llm` → `chatbot` (deuda actual: `runtime_stats`, fase 1).
6. Frontend: `components/ui/` importa `lib/api/`, o hay `fetch` fuera de `lib/api/`, o se edita a mano `lib/api/generado/`.

Ciclos actuales a romper (fases 1 y 4): `ingestion ↔ docs_md`, `semantic ↔ docs_md`, `semantic ↔ dax`.

---

## 5. Dónde va cada cosa

| Quiero crear… | Va en… |
| --- | --- |
| Un endpoint HTTP | `backend/app/api/v1/<recurso>.py` + esquemas en `backend/app/schemas/<recurso>.py` + prueba en `tests/api/` |
| Lógica que usa Redis (cola, caché, límite, conversación) | `backend/app/services/<nombre>.py` |
| Una regla de resolución (indicador, filtro, periodo, agrupación) | la etapa correspondiente de `src/semantic/resolucion/` (ver `src/semantic/README_motor.md`) |
| Comportamiento de un turno de chat | el mixin del motor de chat que corresponda (`src/chatbot/`; tras la fase 2, `src/chatbot/consulta/`) |
| Generación/validación DAX | `src/dax/` |
| Acceso a Power BI o a un LLM | `src/providers/` · `src/llm/` |
| Construcción offline de catálogos/índices | hoy `src/semantic/*_builder.py`; desde la fase 4 `src/catalogo/` |
| Una utilidad genérica (texto, JSON, rutas, logging, entorno) | **primero buscarla** en `src/comun/` y en la tabla de la sección 11; si no existe, en `src/comun/<tema>.py` |
| Un script de mantenimiento reutilizable | `tools/<verbo>_<objeto>.py` (con `--help` y docstring de uso) |
| Un sondeo o prueba manual de un solo uso | el scratchpad del agente; si debe quedar, `tools/manual/` |
| Una prueba automática | `tests/<área>/test_<tema>.py` (sección 7) |
| Un banco de preguntas o fixture | `tests/<área>/fixtures/` · bancos reales en `tests/real/banco_*.json` |
| Salidas de una corrida, informes, logs | `var/out/<suite>/` · `var/logs/` (con `src.comun.rutas`) — nunca en la raíz ni junto al código |
| Temporales | `var/tmp/` o el scratchpad del agente |
| Datos locales regenerables (catálogos, Qdrant, caché) | `data/` (ignorada) |
| Documentación técnica o de diseño | `docs/` (`docs/adr/NNNN-titulo.md` para decisiones; `docs/diseno/` para diseño visual) |
| Spec de una funcionalidad | `specs/NNN-nombre/` (spec-kit) · diseño/plan de superpowers en `docs/superpowers/{specs,plans}/` |
| README de un paquete | dentro del paquete (`src/semantic/README_motor.md`, `src/docs_md/README.md`) |
| Documentación de negocio de un tablero | `docs_tableros/tablero_<nombre>/md/` (formato de `src/docs_md/formato.py`) |
| Una página o componente web | `frontend/app/<ruta>/page.tsx` · `frontend/components/<funcionalidad>/` |
| Un color, tamaño o tipografía | token en `frontend/styles/tokens.css` (y en `.streamlit/config.toml` solo si es un arreglo crítico del legado) |
| Configuración de Redis o arranque de servicios | `infra/redis/` · `infra/scripts/` · `infra/servicios/` |

---

## 6. Lugares para lo efímero

| Carpeta | Qué guarda | Se puede borrar | Cómo se obtiene la ruta |
| --- | --- | --- | --- |
| `var/out/<suite>/` | Informes y resultados de evaluadores, bancos y regresiones (`eval`, `real/desarrollo`, `real/<banco>`, `real/multiturno`, `real/manual`, `regresion`, `docs_md`, `sondeo_intencion`) | Sí, siempre | `src.comun.rutas.ruta_salida(...)` |
| `var/logs/` | Logs de procesos y tareas programadas (`regresion_real.log`) | Sí | `ruta_log(...)` |
| `var/tmp/` | Temporales y copias de trabajo (`qdrant_copia` de `tests/real/run_real.py`) | Sí | `ruta_tmp(...)` |
| `data/` | Estado local que la app necesita (catálogos, Qdrant, metadata, `feedback/`, caché del token) | No sin regenerar (`tools/update_rag.py`) | `src.comun.rutas.DATOS` |
| scratchpad del agente | Sondeos, scripts de análisis y notas de una sesión | Sí, al terminar | fuera del repo |

`PROYECTO_VAR_DIR` cambia la base de `var/`. Las funciones de `rutas` no crean carpetas: quien escribe hace
`mkdir(parents=True, exist_ok=True)`. Las carpetas heredadas `tests/eval/out/`, `tests/docs_md/out/` y
`tests/real/out*/` siguen ignoradas hasta que se vacíen (sección 13).

---

## 7. Convenciones

**Idioma.** Código nuevo, carpetas, documentación y mensajes en **español** sin tildes en identificadores
(`resolucion`, `calificaciones`). Excepción: las carpetas que impone o recomienda el framework conservan su
nombre convencional en inglés (FastAPI: `core/`, `api/`, `schemas/`, `services/`; Next.js: `app/`,
`components/`, `hooks/`, `lib/`, `public/`, `styles/`); los módulos dentro de ellas van en español
(`services/cola.py`). Los nombres en inglés existentes del motor se respetan hasta que una fase los mueva.

**Python.** Módulos y funciones `snake_case`; clases `PascalCase`; constantes `MAYUSCULAS`. Un módulo = una
responsabilidad nombrada por su sustantivo (`periodo.py`, no `utils2.py`). Prohibidos los nombres genéricos
`utils.py`, `helpers.py`, `misc.py`, `nuevo.py`, `final.py`, `_v2.py`, `test_final.py`. Tipado en firmas
públicas. `logging.getLogger(__name__)` en la librería; `print` solo en CLIs (`tools/`, `tests/*/run*.py`).
Estilo verificado con **ruff** (configuración en `pyproject.toml` de la raíz, fase 0): `F` (errores),
`E`/`W` (estilo), `I` (orden de imports), `B` (bugbear), `UP`, `T201` (print) en `src`; largo de línea 120.

**Pruebas Python.** `tests/<área>/test_<tema>.py`, con `unittest` (se corren como
`python -X utf8 -m unittest tests.<área>.test_<tema>` o `python -m tests.<área>.test_<tema>`). Nombres por
comportamiento, no por ronda: `test_r7.py` está prohibido para pruebas nuevas (las existentes se renombran en la
fase 6). Arneses y fakes en `tests/common/` o en el área. Toda prueba que escriba algo usa `tempfile` o `var/`.

**TypeScript.** `strict: true` y `noUncheckedIndexedAccess`; componentes `PascalCase.tsx`; hooks
`useAlgo.ts`; utilidades `camelCase.ts`; rutas de `app/` en `kebab-case`. ESLint + Prettier sin
advertencias. Nada de `any` explícito. Textos de interfaz en español.

**Ramas y commits.** `agente/<tema>` para agentes; commits en español, en imperativo o descriptivos, con el
porqué en el cuerpo.

**Límites de tamaño** (para código nuevo o tocado; lo heredado se reduce por fases):

| Elemento | Aviso | Máximo |
| --- | --- | --- |
| Archivo Python | 400 líneas | 800 líneas |
| Función/método Python | 50 líneas | 80 líneas |
| Complejidad ciclomática | 10 | 15 |
| Parámetros | 6 | 8 |
| Archivo TS/TSX | 250 líneas | 400 líneas |
| Componente React | 150 líneas | 250 líneas |

Ningún cambio puede **aumentar** el tamaño de un archivo que ya pasa el máximo (`query_engine.py` y los 27
restantes) salvo que el mismo cambio extraiga más de lo que añade.

---

## 8. Pruebas y verificación

- Cada cambio de comportamiento trae su prueba en el mismo commit (TDD: roja → verde).
- Refactors sin cambio de comportamiento del motor: **golden master idéntico**
  (`python -X utf8 -m tests.resolution.test_golden`, ~1 h; `GOLDEN_BANCOS=eval` para una pasada rápida).
  La foto se toma y se compara el mismo día; regenerarla solo con justificación en el commit.
- Antes de dar algo por terminado: las suites del área tocada, `python -m tests.eval.test_eval`, y el
  **doctor** (`tools/doctor/`): el puntaje no puede bajar respecto de la rama base (backend y frontend).
- Frontend: `tsc --noEmit`, ESLint, Vitest; Playwright para los flujos de paridad (sección 9).

---

## 9. Streamlit congelado (legado)

`app.py`, `pages/`, `.streamlit/`, `src/ui/`, `src/docs_md/interfaz.py`, `src/feedback/panel.py` y `assets/`:

- Solo se aceptan **arreglos críticos** (la app no arranca, respuesta incorrecta, fuga de datos). Nada de
  funcionalidades ni rediseños nuevos: van al frontend.
- Toda lógica que hoy viva en `app.py` y sea del motor se **extrae** al motor (fase 1: `build_system`,
  `get_display_answer`, `reset_if_finished`) antes de poder borrar `app.py`.
- Se elimina cuando el frontend tenga **paridad**, es decir, cuando haya prueba Playwright verde contra el
  backend real de cada uno de estos flujos:
  1. Pregunta numérica con respuesta de Power BI y botón «Abrir en Power BI».
  2. Contrapregunta con botones (incluida «ninguna de las anteriores») y continuación del plan.
  3. Seguimiento contextual («¿y el mes pasado?») en la misma conversación.
  4. Respuesta documental (RAG) con fuentes.
  5. Progreso por etapas y aviso de espera/cola.
  6. Razonamiento/traza visible y exportación de la conversación.
  7. Calificación de un turno (registro en `data/feedback/`).
  8. Página de documentación: ver un tablero y proponer un cambio.
  9. Estado de servicios (MedGemma, Power BI) y tema institucional.
  10. Arneses (`tests/sim`, `tests/realistic`, `tests/real`) y golden master corriendo **sin** `app.py`.
- Al alcanzar la paridad: commit único que borra el legado, mueve `assets/` a `frontend/public/` y quita
  `streamlit` de `requirements.txt`.

---

## 10. Plan por fases

Cada fase es una rama `agente/estructura-fN`, sin cambios de comportamiento salvo que se diga, y se cierra con:
suites del área + `tests.eval.test_eval` + golden master idéntico + doctor sin bajar. Las fases que tocan
`src/` se coordinan: **no** se ejecutan mientras otro agente edita los mismos archivos.

**Fase 0 — Andamiaje (hecha en parte, 2026-11-10).** `var/` + `.gitignore` ordenado, `src/comun/rutas.py`,
salidas redirigidas, reglas en `CLAUDE.md`. Pendiente: `pyproject.toml` en la raíz con ruff (sin cambiar código),
`README.md` de la raíz (cómo arrancar backend, frontend y legado), llenar `.specify/memory/constitution.md`
(hoy es la plantilla vacía) remitiendo a este documento.

**Fase 1 — Fábrica del motor y deudas de capa (riesgo medio).**
1. `src/fabrica.py`: mover `build_system`, `get_display_answer` y `reset_if_finished` de `app.py`; `app.py` los
   importa; los arneses (`tests/realistic/harness.py`, `tests/sim/harness.py`) dejan de leer `app.py` por AST.
   Riesgo: el arnés ejecuta además el bloque `load_dotenv` de `app.py` — conservarlo en la fábrica con el mismo
   `env_root`. Verificar: golden master idéntico. Coordinar con el agente de UI (`app.py`) y con backend
   (que usará la fábrica).
2. `runtime_stats` → `src/comun/estadisticas.py` (o `src/observabilidad/`), con reexport en
   `src/chatbot/runtime_stats.py`. Rompe `providers/llm → chatbot`. Coordinar con el agente de carga.
3. Las 15 raíces propias de `src`/`pages` pasan a `from src.comun.rutas import RAIZ_PROYECTO` (requisito de la
   fase 5: después solo cambia `rutas.py`).

**Fase 2 — Partir `query_engine.py` (riesgo alto; el patrón ya probado en `src/semantic/resolucion/`).**
`QueryEngine` pasa a ser una clase compuesta por mixins en `src/chatbot/consulta/`; los métodos se **mueven sin
cambios** (las pruebas usan ~30 privados como `engine._query_plan_failure`, que siguen existiendo). Orden, de lo
más aislado a lo más acoplado, un commit y un golden master por paso:

| Paso | Módulo (`src/chatbot/consulta/`) | Líneas hoy | Métodos |
| --- | --- | --- | --- |
| 1 | `trazas.py` | 222–575 | `_think`, `_activity`, `_traced`, `_trace_plan`, `_trace_dax`, líneas de candidato/filtro |
| 2 | `ejecucion_dax.py` | 576–750 | `_model_schema`, `_execute_dax`, columnas desconocidas, `_dimension_listing` |
| 3 | `agrupado.py` | 1809–2054 | filas agrupadas, grupos en blanco, ranking, «sin datos» con fecha de corte |
| 4 | `metrica_legada.py` | 1591–1808 | `_execute_legacy_metric` |
| 5 | `maestra.py` (contrapregunta y ejecución) | 752–1590 | métricas maestras (partir en dos si pasa de 800) |
| 6 | `plan.py` | 2055–2489 | `_execute_query_plan`, listados y detalle |
| 7 | `opciones.py` | 2490–3223 | describir, colapsar y depurar opciones |
| 8 | `contrapregunta.py` | 3224–4180 | respuesta, selección, continuación, mensajes de fallo |
| 9 | `compuestas.py` | 4180–4739 | participación, tablas compuestas |
| 10 | `intencion.py` | 4740–5094 | `_intent_llm_plan`, páginas con la misma medida, recordar éxito |
| 11 | `seguimientos.py` | 5095–5770 | periodo anterior, cambios de calificativo, `_followup_plan` |
| 12 | `contexto.py` | 5771–6569 | tema, comparación, reescritura con LLM |
| 13 | portero (6726–6823) | — | solo cuando el agente del portero cierre |
| 14 | `_process` (736 líneas) | 6824–7559 | **último**: partir en etapas (pendientes → seguimiento → contexto → tipo → plan → ejecución), cada una < 80 líneas |

Riesgos: (a) atributos de módulo que las pruebas parchean — buscar `patch("src.chatbot.query_engine.` antes de
cada paso y reexportar; (b) orden de resolución de métodos con mixins (ningún nombre repetido entre mixins:
verificarlo con un script); (c) imports circulares entre mixins (cada mixin importa solo lo que usa; nada de
`from ..query_engine import`). Meta: `query_engine.py` < 400 líneas (constructor, `process`, `close`).

**Fase 3 — Utilidades canónicas (riesgo medio).** `src/comun/texto.py` (`sin_tildes`, `plegar`, `llave`,
`tokens`), `src/comun/json_io.py` (`leer_json`, `escribir_json_atomico`), `src/comun/registro.py`
(configuración de logging) y `src/comun/entorno.py` (`env_int`, `env_float`, `env_bool`). Las 33 variantes
de normalización **no son idénticas** (regex `[^a-z0-9\s]` vs `[^a-z0-9]+`, `%` conservado en
`business_terms`, `casefold` vs `lower`, NFD vs NFKD, caché `lru_cache` en `resolucion/texto.py`): cada
reemplazo lleva prueba de equivalencia sobre el vocabulario real del catálogo y golden master idéntico. Las que
difieren a propósito se quedan y se documentan.

**Fase 4 — Separar construcción de consulta (riesgo medio).** `src/catalogo/` recibe los constructores
(`model_catalog_builder`, `visual_catalog_builder`, `powerbi_catalog_manager`, `global_master_metric_builder`,
`document_normalizer`, `semantic_merge`) y `src/ingestion/`; sus bloques `__main__` y `print` pasan a
`tools/` (CLIs) y a `logging`. Rompe los ciclos `ingestion ↔ docs_md` y `semantic ↔ docs_md`. Mover
`detail_list.validate_detail_dax` a `src/dax/` rompe `semantic ↔ dax`.

**Fase 5 — `src/` → `backend/motor/` (riesgo alto, mecánico).** Requiere fases 1 y 3 (una sola raíz).
`git mv src backend/motor`; reescritura mecánica `src.` → `motor.` en imports y rutas de `mock.patch` (script
con revisión del diff); `backend/` como raíz de paquete (`pyproject.toml` con `packages`) y los arneses con la
nueva ruta; `rutas.RAIZ_PROYECTO` pasa a `parents[3]`. Un solo commit, en una ventana sin otros agentes en
`src/`. Verificar: todas las suites + golden master + arranque de backend y del legado.

**Fase 6 — Pruebas ordenadas (riesgo bajo).** Renombrar `tests/resolution/test_r2…test_r9.py` y
`test_indicador2.py` por comportamiento; separar bancos y evaluadores (`tests/real`, `tests/eval`) de las
pruebas unitarias en `tests/bancos/` si crecen; `tools/manual/test_*.py` → `tools/manual/sondeo_*.py` para que
nadie los confunda con pruebas; `tests/real/sondeo_intencion.py` (sondeo de un uso) → `tools/manual/` en cuanto el
doctor admita la excepción `tools.manual → tests` (hoy sumaría 2 hallazgos altos de capas).

**Fase 7 — Retiro de Streamlit.** Cuando se cumpla la paridad (sección 9).

---

## 11. Reutilizar antes de crear

Antes de escribir una función utilitaria: `Grep` por el verbo (`normaliz`, `fold`, `plain`, `slug`, `json`,
`raiz`, `root`) en `src/comun/` y en esta tabla. Si existe una variante, usarla o moverla a `src/comun/`.

| Necesidad | Usar hoy | Variantes duplicadas encontradas (a consolidar en la fase 3) |
| --- | --- | --- |
| Raíz del proyecto, `data/`, `var/` | `src.comun.rutas` (`RAIZ_PROYECTO`, `DATOS`, `ruta_salida`, `ruta_log`, `ruta_tmp`) | `PROJECT_ROOT`/`RAIZ` en 15 módulos de `src`/`pages` |
| Normalizar texto para comparar (minúsculas, sin tildes, solo alfanumérico) | `src.semantic.resolucion.texto.normalize_text` (con caché) | `normalize_text` en `rag/ranking`, `semantic/source_model_router`, `master_metric_resolver`, `powerbi_catalog_manager`, `global_master_metric_builder`, `query_semantic_planner`, `chatbot/intent_parser`; `_normalize_text` en `query_engine`, `metric_resolver` |
| Quitar tildes y minúsculas sin tocar signos | `src.semantic.question_normalizer.fold` | `fold` en `business_terms` (conserva `%`), `request_phrases`; `_fold` en `dax/column_guard`, `rag/grounding`, `semantic/detail_list`, `chatbot/detail_formatter` |
| Texto plano en mayúsculas para rótulos | `src.rag.source_labels._plain` | `_plain` en `option_describer`, `response_formatter`, `document_parser`, `domain_cache`, `extractive`, `table_titles` |
| Tokens canónicos | `src.semantic.resolucion.texto.canonical_token(s)` | versión distinta en `query_semantic_planner` |
| Leer JSON | `json.loads(Path.read_text(encoding="utf-8"))` | `load_json` ×5 (`filter_resolver` y `semantic_merge` idénticas), `_load_json` ×4, `_leer_json` ×2 |
| Escribir JSON atómico | `src.docs_md.repositorio` (escritura con `os.replace`) | `catalog_utils`, `chunk_builder`, `semantic_merge`, `document_normalizer`, `visual_catalog_builder`, `tools/sync_*` |
| Slug de nombre | `src.docs_md.repositorio.slug` | `slugify` en `document_parser`, `powerbi_catalog_manager`, `tools/import_documentation_batch`, `tools/local_data/metadata_format`, `tools/sync_powerbi_metadata` |
| Clave canónica de fila de catálogo | — | `_canonical_key` idéntica en `global_master_metric_builder` y `visual_catalog_builder` |
| Variables de entorno numéricas | `src.chatbot.runtime_stats.env_int/env_float` | (destino `src/comun/entorno.py`) |
| Logging | `logging.getLogger(__name__)` | 142 `print()` en 11 módulos de `src` |

---

## 12. Reglas verificables por el doctor

Valores exactos para `tools/doctor/reglas.toml`, escritos con el **mismo esquema** que ese archivo
(`[[capas.orden]]` de abajo arriba, `[[capas.prohibidas]]` con prefijos de módulo). El orquestador reemplaza
las secciones homónimas; lo que no aparece aquí queda como está en `reglas.toml`. Extensiones que el doctor
aún no lee (marcadas `# EXTENSIÓN`): conviene implementarlas; mientras tanto se ignoran sin error.

```toml
[general]
exclusiones = [
  "/.venv", "/venv", ".git", "/.claude", "/graphify-out", "/data", "/tableros", "/__data", "/var",
  "fixtures", "__pycache__", "node_modules", "/.superpowers", "/Documentacion", "/frontend",
]
codigo = ["src", "backend", "tools", "pages", "app.py"]
pruebas = ["tests", "backend/tests"]
paquete = "src"

[legado]
rutas = ["app.py", "pages", ".streamlit", "src/ui", "src/docs_md/interfaz.py", "src/feedback/panel.py", "assets"]

[estructura]
# Entradas permitidas en la raíz. Todo lo demás (zips, logs, scripts, .md sueltos) es un hallazgo.
raiz_permitida = [
  "backend", "frontend", "infra", "src", "tools", "tests", "docs", "docs_tableros", "specs",
  ".specify", ".gitignore", ".gitattributes", ".editorconfig", "pyproject.toml", "requirements*.txt",
  ".env.example", "CLAUDE.md", "README.md", "actualizar_proyecto.ps1",
  # Legado Streamlit (congelado; se borra con la paridad):
  "app.py", "pages", ".streamlit", "assets",
  # Locales: tolerados SOLO si git los ignora.
  ".claude", ".env", ".venv", "var", "data", "tableros", "graphify-out", ".superpowers",
]
# EXTENSIÓN: deben estar ignoradas por git (git check-ignore) si existen.
carpetas_ignoradas = ["var", "data", "tableros", ".venv", ".claude", "graphify-out", ".superpowers", ".env",
                      "__pycache__", "node_modules", ".next"]
max_archivo_kb = 1024
binario_permitido = ["assets/**", "docs/**", "frontend/public/**", "tests/**/fixtures/**"]

[estructura.subcarpetas]
tools = ["local_data", "manual", "doctor", "carga"]
docs = ["superpowers", "diseno", "adr", "calidad"]
infra = ["redis", "scripts", "servicios", "docker"]
backend = ["app", "motor", "tests"]
"backend/app" = ["core", "api", "schemas", "services", "models"]

[tamano]
aplica_a = ["src", "backend", "tools", "pages", "app.py"]
archivo_media = 400       # aviso
archivo_alta = 800        # máximo para código nuevo o tocado
funcion_media = 50
funcion_alta = 80
complejidad_media = 10
complejidad_alta = 15
parametros_max = 8

[[duplicacion.utilidades]]
nombre = "normalizar texto / quitar tildes"
llamadas = ["unicodedata.normalize"]
aplica_a = ["src", "backend", "pages", "app.py"]
canonico = ""   # "src/comun/texto.py" cuando exista (fase 3)
sugerencia = "Reutilizar la normalización existente (docs/ARQUITECTURA.md §11) o moverla a src/comun/texto.py."

[[duplicacion.utilidades]]
nombre = "raíz del proyecto"
patron = "raiz_proyecto"
aplica_a = ["src", "backend", "pages", "app.py"]
canonico = "src/comun/rutas.py"
sugerencia = "from src.comun.rutas import RAIZ_PROYECTO, DATOS, ruta_salida, ruta_log, ruta_tmp"

# Capas de abajo arriba: una capa solo importa de su nivel o de niveles inferiores.
[[capas.orden]]
nombre = "base"
modulos = ["src.comun"]

[[capas.orden]]
nombre = "infraestructura"
modulos = ["src.providers", "src.llm", "src.rag"]

[[capas.orden]]
nombre = "dominio"
modulos = ["src.semantic", "src.dax", "src.docs_md", "src.ingestion", "src.catalogo"]

[[capas.orden]]
nombre = "aplicacion"
modulos = ["src.chatbot", "src.feedback"]

[[capas.orden]]
nombre = "presentacion_legado"
modulos = ["src.ui"]

[[capas.orden]]
nombre = "backend_base"
modulos = ["backend.app.core", "backend.app.schemas", "backend.app.models"]

[[capas.orden]]
nombre = "backend_servicios"
modulos = ["backend.app.services"]

[[capas.orden]]
nombre = "backend_api"
modulos = ["backend.app.api", "backend.app.main", "backend"]

[[capas.prohibidas]]
desde = "src"
hacia = ["backend", "tools", "tests", "app", "pages", "fastapi", "starlette", "redis"]

[[capas.prohibidas]]
desde = "backend.app.api"
hacia = ["src"]            # el motor se usa a través de backend.app.services.motor

[[capas.prohibidas]]
desde = "backend"
hacia = ["src.ui", "streamlit", "tools", "tests", "app", "pages"]

[[capas.prohibidas]]
desde = "tools"
hacia = ["tests", "app", "pages", "backend"]
excepto = ["tools.manual"]   # EXTENSIÓN: los sondeos manuales usan los arneses de tests.real/tests.realistic

[[capas.prohibidas]]
desde = "app"
hacia = ["tools", "tests", "pages", "backend"]

[[capas.prohibidas]]
desde = "pages"
hacia = ["tools", "tests", "backend"]

[pruebas]
aplica_a = ["src", "backend"]

[higiene]
print_en = ["src", "backend"]
sys_path_en = ["src", "backend"]
# EXTENSIÓN: nombres de archivo prohibidos en código.
nombres_prohibidos = ["utils.py", "helpers.py", "misc.py", "nuevo*.py", "final*.py", "*_v2.py", "*_old.py", "copia*"]

[fastapi]
aplica_a = ["backend"]
carpeta_routers = ["backend/app/api/v1"]
modulos_settings = ["backend/app/core/config.py"]
motor_prohibido_en_routers = ["src"]

[frontend]
carpeta = "frontend"
carpetas_api = ["frontend/lib/api"]
tokens = ["frontend/styles/tokens.*", "frontend/app/globals.css"]
componente_media = 150
componente_alta = 250
# EXTENSIÓN (arquitectura del frontend):
archivo_ts_media = 250
archivo_ts_alta = 400
generado_no_editable = ["frontend/lib/api/generado"]
fetch_solo_en = ["frontend/lib/api"]
prohibidas = [
  { desde = "frontend/components/ui", hacia = ["frontend/lib/api", "frontend/app"] },
  { desde = "frontend/components", hacia = ["frontend/app"] },
  { desde = "frontend/lib", hacia = ["frontend/app", "frontend/components", "frontend/hooks"] },
]
```

Deuda de capas conocida (hallazgos ya presentes en la línea base, se eliminan en las fases 1 y 4):
`src/providers/powerbi_provider.py` y `src/llm/llm_gate.py` → `src.chatbot.runtime_stats`;
`tools/manual/regresion_real.py` → `tests.real`; ciclos `ingestion ↔ docs_md`, `semantic ↔ docs_md`, `semantic ↔ dax`.

Comprobado el 2026-11-10 con el doctor en desarrollo (`agente/doctor`, perfil backend, `--sin-externas`) y estas
reglas: base d7522c8 = 67,4 (hallazgo alto: `HANDOFF.md` suelto en la raíz) → rama `agente/estructura` = 69,9, sin
hallazgos nuevos en Duplicación ni Capas. Con los umbrales de tamaño de esta sección el puntaje absoluto de
«Tamaño» baja (≈ 30 → ≈ 18) porque el código heredado los supera; el trinquete del doctor compara contra la
línea base, así que solo penaliza lo que crezca.

---

## 13. Pendientes del checkout principal (no versionados)

Propuestas para el usuario (los agentes no borran nada fuera de su worktree):

| Entrada | Tamaño | Propuesta |
| --- | --- | --- |
| `OneDrive_1_9-10-2026.zip` | 101 MB | Fuera del repo (`Documents/Proyecto_RAG_fuentes/`) o borrar si ya se extrajo |
| `Documentacion.zip` | 79 MB | Igual: es el comprimido de `Documentacion/` |
| `Documentacion/` | 79 MB | Fuera del repo; las fuentes vivas ya están en `docs_tableros/` |
| `__data/semantic_documents_Error.txt` | 1 KB | Borrar (respuesta de error de una descarga fallida del 2026-10-09) |
| `__pycache__/` (raíz) | 76 KB | Borrar (bytecode de scripts que ya viven en `tools/`) |
| `tests/eval/out/` | 14 MB | Mover a `var/out/eval/` (incluye `rag_probe.py`, un sondeo suelto) |
| `tests/real/out`, `out_holdout`, `out_holdout2`, `out_multiturno`, `out_sondeo` | 39 + 2,8 + 1,2 + 1,2 + 1,4 MB | Mover a `var/out/real/{desarrollo,holdout,holdout2,multiturno}/` y `var/out/sondeo_intencion/` |
| `.claude/worktrees/` | 563 MB (76 worktrees al medir; durante la sesión quedaron 8) | `git worktree prune` y borrar los de ramas ya integradas al cerrar cada ronda |

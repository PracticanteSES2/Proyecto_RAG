# Plan 014 — Infraestructura con Docker y WSL

**Spec**: `spec.md` · **Tareas**: `tasks.md` · **Para**: la sesión de Claude Code del propietario, tras `git pull`.

## 0. Si eres la sesión que acaba de hacer `pull`: empieza aquí

1. Lee `CLAUDE.md` (reglas normativas), `docs/ARQUITECTURA.md` (§2, §4, §5, §9, §12), `docs/backend.md` y este plan.
2. Abre `tasks.md` y continúa por la **primera tarea sin `[x]`**. Si todas las de una fase están marcadas, pasa a
   la siguiente. Al cerrar cada tarea, márcala y haz commit (así la siguiente sesión retoma donde quedó).
3. Antes de la primera tarea de código haz la **fase A** (arranque): sin ella no hay línea base con qué comparar.
4. Al terminar cada fase, escribe una entrada corta al principio de `docs/HANDOFF.md` (qué se integró, qué sigue,
   qué decide el usuario).

## 1. Modo de trabajo: la sesión orquesta, los agentes ejecutan

**Todo el desarrollo lo hacen agentes**; la sesión principal no escribe código de producción. Su trabajo es
repartir, revisar, integrar y verificar.

- **Un agente por tarea o grupo de tareas independiente**, cada uno en su propio worktree
  (`isolation: "worktree"`) y en su propia rama `agente/<tema>` creada desde `desarrollo`. Agentes en paralelo solo
  si no tocan los mismos archivos (la columna «Archivos» de `tasks.md` dice cuáles toca cada tarea).
- **Instrucciones de cada agente** (copiarlas en su prompt, que es todo el contexto que tendrá):
  - el objetivo, la tarea de `tasks.md`, los archivos que puede tocar y los que no;
  - la regla de graphify: «si existe `graphify-out/graph.json`, corre `graphify query "<pregunta>"` antes de buscar
    o leer código; usa `graphify path`/`graphify explain` para relaciones»;
  - TDD (superpowers `test-driven-development`): prueba en rojo primero, luego el código;
  - reglas de `CLAUDE.md` (dónde crear, capas, tamaños, `var/`, reutilizar `src/comun/`, nada en la raíz);
  - no cargar ni editar `.env`; Power BI y bases de datos **solo lectura**; nada de datos de pacientes en
    salidas, logs ni commits;
  - al terminar: suites del área + doctor del área (`python -X utf8 -m tools.doctor backend|frontend`) y un
    informe con lo hecho, lo que no y cómo se verificó (`verification-before-completion`).
- **Integración (la hace la sesión)**, por cada rama de agente:
  1. agente `revisor-estructura` sobre el diff → debe decir APROBAR;
  2. `git merge --no-ff agente/<tema>` en `desarrollo` con mensaje «Integra agente/<tema>: …»;
  3. suites afectadas + `python -X utf8 -m tools.doctor --verificar` (ningún perfil baja; si sube,
     `--actualizar-linea-base` en un commit «Doctor: línea base tras integrar …»);
  4. `graphify update .` (y `/graphify . --update` si cambiaron documentos);
  5. superpowers `requesting-code-review` al cerrar cada fase;
  6. limpiar: `git worktree remove` del agente, borrar la rama integrada, `git status` limpio.
- **Diagnóstico**: agentes `doctor-backend` y `doctor-frontend` (solo leen) antes de planear una fase grande y
  después de integrarla.
- **Fallos**: superpowers `systematic-debugging`; nunca `--no-verify` ni saltar hooks.

### Proceso por funcionalidad (CLAUDE.md, regla 2)

spec-kit: esta spec ya está escrita; correr `/speckit-clarify` (preguntas al propietario) y `/speckit-analyze`
antes de implementar. Para piezas grandes nuevas (p. ej. la cola de tareas de reindexación) se puede abrir una
sub-spec `specs/016-…` con `/speckit-specify`. superpowers: leer `using-superpowers`; `brainstorming` y
`writing-plans` antes de codificar cada fase (planes en `docs/superpowers/plans/`).

### Coordinación con la otra sesión (equipo de desarrollo)

Trabaja en paralelo sobre `desarrollo` en la clasificación de mensajes que no son consultas. **No tocar**:
`src/chatbot/portero*.py`, `src/chatbot/charla*.py`, `tests/portero/`, `specs/015-*`. Antes de integrar: `git pull
origin desarrollo`; si hay conflicto en `tools/doctor/linea_base.json`, regenerarla con `--actualizar-linea-base`
tras el merge (no resolver el JSON a mano). Push a `origin/desarrollo` solo con todo en verde y con el visto bueno
del propietario; `main` no se toca.

## 2. Arquitectura de despliegue objetivo

```
Windows (anfitrión)                           Docker Desktop (backend WSL2)
┌──────────────────────────────────┐          ┌─────────────────────────────────────┐
│ python -m backend.worker  (UNO)  │◀──Redis──▶│ redis:7.4  (AOF, requirepass,       │
│  Qdrant local (data/), MiniLM,   │  :6379   │            maxmemory 512mb)          │
│  ADOMD/pythonnet → Power BI,     │          │ api  (uvicorn --workers N,           │
│  MedGemma (HTTP)                 │          │       MOTOR_MODO=externo)  :8000     │
└──────────────────────────────────┘          │ web  (next start, standalone) :3000 │
                                              └─────────────────────────────────────┘
```

- **El trabajador va en Windows, fuera de Docker**: ADOMD (Power BI) necesita Windows y Qdrant local admite un
  solo proceso por carpeta. Nunca dos trabajadores sobre el mismo `data/`.
- **La API en contenedor** no carga el motor (`MOTOR_MODO=externo`): verificar con un agente que la imagen no
  arrastra `torch`/`sentence-transformers`. Si los arrastra, separar un `requirements-api.txt` mínimo (sin tocar el
  de producción) o dejar la API en Windows y solo Redis + web en Docker (decisión del propietario en
  `/speckit-clarify`).
- **Rutas**: todo lo efímero en `var/`; los datos en `data/`. Archivos nuevos según §5:
  `infra/docker/` (compose, Dockerfiles), `infra/redis/` (configuración), `infra/scripts/` (arranque en
  PowerShell), pruebas de integración en `tests/backend/` y `tests/api/`, e2e en `frontend/tests/e2e/`.
- **Secretos**: `REDIS_URL`, `BACKEND_SECRETO`, contraseña de Redis: variables de entorno o un
  `infra/docker/.env` **ignorado por git** con un `infra/docker/.env.example` versionado. El `.env` de la raíz lo
  edita solo el usuario.

## 3. Fases

| Fase | Qué | Agentes (paralelo si no comparten archivos) | Verificación |
| --- | --- | --- | --- |
| A | Arranque: herramientas, línea base, servicios actuales | sesión (sin agentes) | suites + doctor + chat en modo memoria |
| B | Redis en Docker + suites contra Redis real | 1 infra · 1 pruebas | CA-01, CA-02 |
| C | Modo Redis de punta a punta + carga | 1 integración · luego 1 carga | CA-03, CA-04 |
| D | Reindexación por cola en el trabajador | 1 backend (TDD) | CA-05 |
| E | Contenedores API + web, compose real | 1 api-imagen · 1 web-imagen · luego 1 compose | CA-06 |
| F | Cliente OpenAPI + prueba de contrato | 1 frontend | CA-07 |
| G | Playwright de paridad (§9) | 1-2 e2e (repartir flujos) | CA-08 |
| H | Cierre: doctor, graphify, HANDOFF, revisión | sesión + `revisor-estructura` | CA-09 |

B, D y F pueden ir en paralelo (archivos distintos). C necesita B. E necesita B. G necesita C y F.

## 4. Riesgos

- **WSL2/Docker y antivirus**: el disco es lento; montar `data/` en contenedores es lento y no hace falta (el
  trabajador queda en Windows). No montar el repo entero en la imagen de la API: copiar solo `backend/` y `src/`.
- **CORS**: la API solo admite `http://localhost:3000`; en compose ajustar `CORS_ORIGENES`.
- **`host.docker.internal`**: la API en contenedor no habla con el trabajador directamente (todo va por Redis);
  solo Redis debe ser alcanzable desde ambos lados.
- **Pruebas intermitentes con Redis real** (`test_cola_fifo_posicion_y_eventos`, `test_turno_en_curso_cola_y_limite`
  ya fueron intermitentes con fakeredis): prefijo de claves único por prueba (`redis_prefijo`) y `FLUSHDB` solo
  sobre una base de datos dedicada a pruebas (`/15`), nunca la de la app.
- **Power BI**: la carga real consulta Power BI de producción en solo lectura: pocas consultas, ramp corto, con
  permiso explícito del propietario antes de correrla.

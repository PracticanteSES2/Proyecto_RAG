---
description: "Tareas de la infraestructura con Docker y WSL (equipo del propietario)"
---

# Tareas: Infraestructura con Docker y WSL

**Entrada**: `specs/014-infra-docker-wsl/` (spec.md, plan.md). **Retome**: continuar por la primera tarea sin `[x]`.
**Ejecución**: cada tarea la hace un **agente** en su worktree (`agente/<tema>`); la sesión orquesta e integra
(`plan.md` §1). **Pruebas**: TDD, primero en rojo. `[P]` = puede ir en paralelo con las otras `[P]` de su fase.

## Fase A: Arranque (la sesión, sin agentes)

- [ ] A01 Comprobar herramientas: `docker version`, `docker compose version`, `wsl --status` (WSL2), Node ≥ 20,
  `.venv` con `pip install -r requirements-dev.txt`, `cd frontend; npm ci`. Si falta algo, pedírselo al propietario.
- [ ] A02 Skills del proceso (CLAUDE.md regla 2). Si `/speckit-specify` no aparece: `uvx --from
  git+https://github.com/github/spec-kit.git specify init --here --ai claude --script ps` y luego `git checkout --
  .specify` y `git status` limpio (no debe pisar la constitución versionada). Si superpowers no aparece, pedir al
  propietario que lo instale como plugin de Claude Code (`/plugin`, buscar «superpowers») y reiniciar la sesión.
  Graphify: `pip install graphifyy` en la `.venv` y `graphify hook install`.
- [ ] A03 `graphify update .` (el grafo no se versiona entero al día) y `graphify query "backend redis worker
  almacen"` para ubicarse.
- [ ] A04 Línea base: `python -X utf8 -m unittest discover -s tests/backend -t .`, igual con `tests/api`;
  frontend `npm run typecheck`, `npm run lint`, `npx vitest run` (en Windows, abrir la terminal en `C:\…` con la C
  mayúscula: con `c:\` Vitest carga dos veces y falla «failed to find the current suite»);
  `python -X utf8 -m tools.doctor --verificar`. Anotar en `docs/HANDOFF.md` lo que no esté en verde **antes** de
  tocar nada.
- [ ] A05 Levantar el modo actual (memoria) y probar a mano chat y documentación: backend
  `.\infra\scripts\iniciar_backend.ps1 -ArchivoEntorno .env`, frontend con `NEXT_PUBLIC_API_MOCK=0` y
  `npx next dev --port 3000`. Login de Power BI por código de dispositivo si lo pide (`POWERBI_AUTH=device_code`).
- [ ] A06 `/speckit-clarify` sobre esta spec (decisiones del propietario: ¿API en contenedor o en Windows?, puertos,
  contraseña de Redis, ¿cuántos procesos de API?) y `/speckit-analyze`.

## Fase B: Redis en Docker

- [ ] B01 [P] Agente infra: `infra/redis/redis.conf` (AOF, `maxmemory 512mb`, `volatile-lru`, `protected-mode`),
  `infra/docker/docker-compose.yml` con el servicio `redis` (healthcheck `redis-cli ping`, volumen, contraseña por
  variable), `infra/docker/.env.example` (versionado; el `.env` de esa carpeta ignorado en `.gitignore`) e
  `infra/scripts/iniciar_redis.ps1` (sube, espera el healthcheck, imprime la `REDIS_URL` sin la contraseña).
  Borrar `docker-compose.referencia.yml` y actualizar sus referencias (Grep en `docs/` y `specs/`). — CA-01
- [ ] B02 [P] Agente pruebas: que `tests/backend` y `tests/api` usen Redis real si existe `REDIS_URL_PRUEBAS`
  (base `/15`, prefijo único por prueba, limpieza solo de su prefijo) y `fakeredis` si no; el helper va en
  `tests/backend/apoyo.py`. Sin la variable el resultado debe ser idéntico al de A04. — CA-02
- [ ] B03 Integrar B01+B02, correr ambas suites con `REDIS_URL_PRUEBAS` contra el Redis de B01 y arreglar lo que
  falle (`systematic-debugging`); vigilar las dos pruebas intermitentes de `plan.md` §4.

## Fase C: Modo Redis de punta a punta

- [ ] C01 Agente integración: `iniciar_backend.ps1 -RedisUrl … -Procesos 2` + trabajador; verificar `GET /salud`
  (`modo: "redis"`), conversación real desde el frontend, turnos de una misma conversación servidos por procesos
  distintos, trabajador muerto a mitad de turno → `error interrumpido` al volver. Documentar en `docs/backend.md`
  «Despliegue con Redis» lo que cambie. — CA-03 · cierra `specs/006-api-backend/tasks.md` T020
- [ ] C02 Puerta de MedGemma en Redis (`LLM_GATE_BACKEND=redis`): log sin «Redis no disponible»,
  `llm_gate.backend_name() == "redis"`, `STATS.snapshot()["llm_queue"]` suma ambos procesos.
- [ ] C03 **Con permiso explícito del propietario** (consulta Power BI de producción, solo lectura): `tools/carga`
  con rampas 1, 3, 5, 10, 20; informe en `var/out/carga/`; tabla y P recomendado en
  `docs/arquitectura/concurrencia.md` §4.1; propuesta de `MEDGEMMA_MAX_CONCURRENT` y `MOTOR_INSTANCIAS`. — CA-04 ·
  cierra `specs/004-concurrencia-llm/tasks.md` T019

## Fase D: Reindexación en modo externo

- [ ] D01 `/speckit-specify` corto (sub-spec `specs/016-reindexacion-trabajador/`) o `brainstorming` +
  `writing-plans`: tarea `reindexar(grupo)` encolada en Redis, ejecutada por el trabajador (dueño de Qdrant), estado
  `sin_iniciar | en_curso | lista | error` leído por la API. Contrato sin cambios
  (`specs/013-documentacion-web/contracts/api-documentacion.md`).
- [ ] D02 [P] Agente backend (TDD con fakeredis, luego Redis real): `backend/app/services/` (cola de tareas del
  trabajador) + `tests/backend/test_documentacion_servicio.py` (motor externo ya no da `no_disponible`). — CA-05
- [ ] D03 Quitar «hoy responde `no_disponible`» de `docs/ARQUITECTURA.md` §9.8 y `docs/backend.md`.

## Fase E: Contenedores de la API y del frontend

- [ ] E01 [P] Agente api-imagen: `infra/docker/api.Dockerfile` (python 3.12-slim o la versión de la `.venv`, solo
  `backend/` + `src/` + requirements, usuario no root, `MOTOR_MODO=externo`). Medir si la imagen importa
  `torch`/`sentence-transformers`; si sí, aplicar la decisión de A06 (plan §2).
- [ ] E02 [P] Agente web-imagen: `infra/docker/web.Dockerfile` (Next `output: "standalone"` en
  `frontend/next.config.ts`, multi-etapa, `NEXT_PUBLIC_API_URL` en build), sin romper `next dev`.
- [ ] E03 Agente compose: servicios `api` y `web` en `infra/docker/docker-compose.yml`, `CORS_ORIGENES`,
  `infra/scripts/iniciar_todo.ps1` (Redis + API + web en Docker; trabajador en Windows). README de la raíz: sección
  «Arranque con Docker». — CA-06

## Fase F: Cliente OpenAPI y contrato

- [ ] F01 [P] Agente frontend: exportar el esquema (`python -m backend` o `app.openapi()` →
  `frontend/lib/api/openapi.json` por script en `tools/`), generar tipos en `frontend/lib/api/generado/` (p. ej.
  `openapi-typescript`, script `npm run api:tipos`), y que `tipos.ts`, `capacidades.ts` y `conversaciones.ts` usen
  los tipos generados en vez de los «Supuesto:». Los adaptadores de `capacidades.ts`/`conversaciones.ts` se quedan
  (traducen contrato → vista). — CA-07 · cierra `specs/007-frontend-chat/tasks.md` T026
- [ ] F02 Prueba de contrato: falla si `openapi.json` no coincide con el backend actual (Python, en `tests/api/`) y
  `tsc` falla si cambia sin regenerar. Revisar también `Salud` (el backend devuelve `estado: "caido"` y `listo`).

## Fase G: Playwright de paridad (§9 de `docs/ARQUITECTURA.md`)

- [ ] G01 Agente e2e: Playwright en `frontend/tests/e2e/` (config aparte de Vitest; `npm run e2e`) contra el backend
  real, flujos 1-5 de §9.
- [ ] G02 Agente e2e: flujos 6-10 (incluida la documentación viva, flujo 8). Saltar con motivo lo que dependa de
  datos ausentes y anotarlo aquí. — CA-08
- [ ] G03 Actualizar §9 con lo cubierto. **No** borrar Streamlit: lo decide el usuario.

## Fase H: Cierre

- [ ] H01 `python -X utf8 -m tools.doctor --verificar` (ningún perfil baja) y `--actualizar-linea-base` si sube.
- [ ] H02 `graphify update .` y `/graphify . --update` (cambiaron docs).
- [ ] H03 `revisor-estructura` sobre todo el diff de la spec y `requesting-code-review`.
- [ ] H04 Entrada en `docs/HANDOFF.md`, `git status` limpio, worktrees de agentes eliminados; push a
  `origin/desarrollo` con el visto bueno del propietario.

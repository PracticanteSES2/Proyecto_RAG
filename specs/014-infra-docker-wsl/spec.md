# Spec 014 — Infraestructura con Docker y WSL (equipo del propietario)

**Estado**: lista para `/speckit-clarify` → `/speckit-analyze` → `/speckit-implement` en el equipo del propietario.
**Creada**: 2026-11-11 desde el equipo de desarrollo (sin Docker, WSL ni Redis; sin permisos de administrador).
**Plan**: `plan.md` · **Tareas**: `tasks.md` (marcar `[x]` al cerrar cada una; es el punto de retome entre sesiones).

## Por qué

El backend (FastAPI), el frontend (Next.js) y la capa Redis están terminados y probados **solo** con memoria y
`fakeredis`: en el equipo de desarrollo no se puede instalar Docker, WSL ni Redis. Todo lo que exige un Redis real,
varios procesos o contenedores quedó marcado como «no probado» o «pendiente para el propietario»:

| Pendiente | Dónde quedó anotado |
| --- | --- |
| Probar con Redis real y medir con `tools/carga` antes de subir `MOTOR_INSTANCIAS` | `specs/006-api-backend/tasks.md` T020 |
| Medición real de concurrencia de MedGemma (capacidad P) con la puerta en Redis | `specs/004-concurrencia-llm/tasks.md` T019, `docs/arquitectura/concurrencia.md` §4 y §6.1 |
| `docker-compose` de referencia sin probar | `infra/docker/docker-compose.referencia.yml` |
| Reindexar la documentación cuando el motor corre en el trabajador (hoy responde `no_disponible`) | `docs/ARQUITECTURA.md` §9.8, `specs/013-documentacion-web/plan.md` |
| Pruebas Playwright de paridad contra el backend real (requisito para retirar Streamlit) | `docs/ARQUITECTURA.md` §9 |
| Cliente del frontend generado desde OpenAPI (hoy los tipos son «supuestos» escritos a mano) | `specs/007-frontend-chat/tasks.md` T026 |

El 2026-11-11 el «supuesto» de `GET /capacidades` no coincidía con el backend real y la bienvenida del chat se
caía al entrar (`Cannot read properties of undefined (reading 'map')`). Se corrigió a mano en
`frontend/lib/api/capacidades.ts`; el cliente generado desde OpenAPI y las pruebas de contrato evitan que se repita.

## Qué debe quedar

1. **Redis real en Docker (WSL2)** con contraseña, persistencia AOF y `maxmemory`, arrancable con un solo comando
   desde PowerShell, y las suites de `tests/backend` y `tests/api` pasando **también** contra ese Redis.
2. **Modo Redis de punta a punta**: un trabajador (`python -m backend.worker`, en Windows: Power BI usa
   ADOMD/pythonnet) + API con varios procesos + puerta de MedGemma en Redis (`LLM_GATE_BACKEND=redis`), con
   `GET /api/v1/salud` → `modo: "redis"` y una conversación real completa desde el frontend.
3. **Medición de carga** (1, 3, 5, 10 y 20 usuarios) con `tools/carga` y el valor de `MEDGEMMA_MAX_CONCURRENT` y
   `MOTOR_INSTANCIAS` recomendado, documentado en `docs/arquitectura/concurrencia.md`.
4. **Reindexación en modo externo**: la API encarga la reindexación al trabajador por Redis (cola de tareas) en vez
   de responder `no_disponible`.
5. **Contenedores de la API y del frontend** (Dockerfile + `docker-compose.yml` real, ya no «referencia») con el
   trabajador en el anfitrión Windows (`host.docker.internal`), y un script que levanta todo.
6. **Cliente tipado generado desde OpenAPI** en `frontend/lib/api/` (lo generado no se edita) + una prueba de
   contrato que falle si el backend y el frontend se separan.
7. **Pruebas Playwright de paridad** (§9 de `docs/ARQUITECTURA.md`, flujos 1-10) contra el backend real, en verde.

## Fuera de alcance (lo hace la sesión del equipo de desarrollo, no tocar)

- Clasificación de mensajes que no son consultas («hola», «gracias», «¿raíz cuadrada de 5?»): respuesta sin
  MedGemma, sin Qdrant y sin Power BI. Archivos reservados: `src/chatbot/portero*.py`, `src/chatbot/charla*.py`,
  `tests/portero/`, `specs/015-*`.
- Fase 2 del refactor del motor (`specs/012-refactor-motor/fase2.md`): no se ejecuta mientras haya otra sesión en
  `src/chatbot/`.
- Retirar Streamlit: solo cuando §9 esté completo **y** el usuario lo apruebe.

## Criterios de aceptación

- **CA-01** `infra/scripts/iniciar_redis.ps1` levanta Redis en Docker; `docker compose ... ps` lo muestra sano
  (healthcheck) y sobrevive a un reinicio del contenedor sin perder la cola (AOF).
- **CA-02** `REDIS_URL_PRUEBAS=redis://... python -X utf8 -m unittest discover -s tests/backend -t .` y lo mismo con
  `tests/api` pasan contra el Redis real; sin la variable siguen pasando con `fakeredis` (herméticas).
- **CA-03** Con Redis: `GET /api/v1/salud` → `modo: "redis"`, componentes `ok`; dos procesos de API atienden turnos
  de la misma conversación; matar el trabajador a mitad de un turno lo cierra como `error interrumpido` al volver.
- **CA-04** Informe de carga en `var/out/carga/` y tabla resumida en `docs/arquitectura/concurrencia.md` §4.1.
- **CA-05** `POST .../reindexar` con motor externo termina en `lista` (o `error` con mensaje amable), nunca
  `no_disponible`.
- **CA-06** `docker compose -f infra/docker/docker-compose.yml up` + trabajador en Windows sirven el chat en
  `http://localhost:3000` contra el backend real.
- **CA-07** `frontend/lib/api/` usa tipos generados; `npm run typecheck` falla si cambia el esquema del backend sin
  regenerar.
- **CA-08** Playwright: los 10 flujos de §9 en verde contra el backend real (se pueden saltar con motivo los que
  dependan de datos que no existan, anotándolo en `tasks.md`).
- **CA-09** Doctor: ningún perfil baja (`python -X utf8 -m tools.doctor --verificar`); `graphify update .` corrido
  tras cada integración.

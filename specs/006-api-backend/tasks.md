# Tasks: API del asistente (FastAPI + Redis)

**Input**: [spec.md](spec.md) · [plan.md](plan.md) · [contracts/api-v1.md](contracts/api-v1.md)
**Pruebas**: `python -X utf8 -m unittest discover -s tests/backend -t .` y `… -s tests/api -t .` (TDD: cada tarea
de código entra con su prueba).

## Fase 1 — Andamiaje

- [x] T001 Spec, plan y contrato v1 (`specs/006-api-backend/`)
- [x] T002 `backend/app/{core,api/v1,schemas,services}` según `docs/ARQUITECTURA.md`; dependencias en
      `requirements.txt` / `requirements-dev.txt`
- [x] T003 `core/config.py` (pydantic-settings, solo variables de entorno), `core/errores.py`, `core/registro.py`,
      `core/dependencias.py`

## Fase 2 — Fundamentos (bloquean las historias)

- [x] T004 Almacén: interfaces (`services/almacen.py`), memoria (`almacen_memoria.py`) y Redis
      (`almacen_redis.py`: Streams + grupo, ZSET de cola y límites, hashes, XAUTOCLAIM) — `tests/backend/test_almacen.py`
      corre el MISMO contrato en ambos
- [x] T005 Fábrica única del motor `src/chatbot/fabrica.py`; `app.py::build_system` la usa (arneses por AST intactos;
      golden master: 0 diferencias frente al código anterior; `tests/sim`: 57 PASS)
- [x] T006 Motor en el backend (`services/motor.py`): piscina, retriever compartido con candado, estado por
      conversación (captura/restauración) firmado con HMAC, adaptador `SesionPorAtributos` (punto de unión con
      agente/memoria-sesion) — `tests/backend/test_motor_estado.py`
- [x] T007 Presentación (`services/presentacion.py`): puerto de `get_display_answer`, contrapregunta con ids
      originales, fuentes, enlaces, detalles, diagnóstico — `tests/backend/test_presentacion.py`

## Fase 3 — US1: preguntar y ver la respuesta en vivo (P1)

- [x] T008 `ProcesadorTurnos` (`services/turnos.py`): progreso/espera/aviso con `src/chatbot/progreso.py`,
      `llm_gate.ui_progress`, `token`, orden respuesta → guardar → fin — `tests/backend/test_turnos.py`
- [x] T009 SSE (`services/eventos.py`): Last-Event-ID, `cola`, ping, reconstrucción del estado final
- [x] T010 Routers `conversaciones`, `turnos` — `tests/api/test_api.py`

## Fase 4 — US2: muchas personas a la vez (P1)

- [x] T011 `Trabajador` (`services/trabajador.py`): toma de la cola solo con instancia libre, hilos, latido,
      huérfanos; `backend/worker.py`
- [x] T012 Candado de conversación (409), cola llena (503), límite por navegador e IP (429)
- [x] T013 Prueba con el motor REAL simulado: conversaciones intercaladas no se mezclan
      (`tests/backend/test_motor_simulado.py`)

## Fase 5 — US3: caché (P2)

- [x] T014 `services/cache.py`: normalizador del motor, huella de datos/catálogo/código, fecha, reglas de qué se
      guarda — `tests/backend/test_cache.py`; estado posterior guardado para que los seguimientos funcionen

## Fase 6 — US4: historial, exportación, calificación, capacidades, salud, diagnóstico (P2)

- [x] T015 Historial con `contrapregunta_vigente`; exportación Markdown con `conversation_export`
- [x] T016 Calificación con `src/feedback/registro.py` (idempotente)
- [x] T017 Capacidades, salud (vida/preparación) y diagnóstico del servidor publicados por el trabajador

## Fase 7 — Cierre

- [x] T018 `infra/scripts/iniciar_backend.ps1`, `infra/docker/docker-compose.referencia.yml` (no probado),
      `docs/backend.md` (incluye «Despliegue con Redis»)
- [ ] T019 Adaptador `SesionExplicita` cuando agente/memoria-sesion entregue `process(pregunta, sesion=…)`
- [ ] T020 Probar con Redis real en el servidor y medir con `tools/carga` antes de subir `MOTOR_INSTANCIAS`
- [ ] T021 Retirar la duplicación restante con app.py (`get_display_answer`) cuando Streamlit se apague

# Tasks: Memoria de conversación por sesión

**Input**: `specs/008-memoria-por-sesion/` (spec.md, plan.md, research.md, contracts/)

**Tests**: TDD — pruebas de aislamiento, serialización y concurrencia en `tests/sesion/`.

## Phase 1: Inventario y contrato

- [x] T001 Inventario archivo:línea del estado mutable (motor, gestor, memoria, reescritor, colaboradores,
  singletons de módulo) → `research.md`.
- [x] T002 Contrato `contracts/sesion-conversacion.md` (commit primero, para `agente/backend-api`).
- [x] T003 Línea base del golden master con `desarrollo` intacto (copia aparte, misma fecha).

## Phase 2: Pruebas (rojo)

- [x] T004 `tests/sesion/test_sesion_conversacion.py`: serialización (tipos, versión, corrupto, ruta del valor
  no serializable), cierre y reinicio; seguimientos intercalados; contrapregunta ajena; reiniciar A no toca B;
  JSON (seguimiento y contrapregunta abierta); ida y vuelta por JSON en cada turno; el motor no guarda estado;
  `reset_if_finished` con sesión; hilos con turnos en serie; dos turnos a la vez dentro del motor.

## Phase 3: Implementación (verde)

- [x] T005 `src/chatbot/estado_conversacion.py` (+ `ConversationMemory.max_turns`/`load`).
- [x] T006 `src/chatbot/sesion_motor.py` y cambios localizados en `query_engine.py`.
- [x] T007 `ConversationManager.state`/`candidate_dashboards` sobre la sesión activa.
- [x] T008 `app.py`: estado por pestaña, `sesion=`, «Nueva conversación» solo la propia.

- [x] T012 Backend: `SesionExplicita` reemplaza `SesionPorAtributos` (misma forma), `SerializadorEstado` JSON
  firmado; motor doble con el andamiaje de sesión; `tests/backend` y `tests/api`.

## Phase 4: Verificación

- [x] T009 Suites: sesion, context (conversation, context), clarification, routing, portero, stability,
  multiturno `--sim`.
- [x] T010 Golden master comparado con la línea base del mismo día.
- [x] T011 Doctor `--verificar`; merge de `desarrollo`; `graphify update .`.

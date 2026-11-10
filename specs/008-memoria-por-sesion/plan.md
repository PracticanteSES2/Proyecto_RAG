# Implementation Plan: Memoria de conversación por sesión

**Branch**: `agente/memoria-sesion` | **Date**: 2026-11-10 | **Spec**: `specs/008-memoria-por-sesion/spec.md`

## Summary

Sacar del `QueryEngine` y del `ConversationManager` compartidos todo el estado de conversación y llevarlo a un
`EstadoConversacion` serializable que guarda quien conversa; el estado del turno en curso pasa a un ContextVar.
El motor queda como servicio compartido sin estado de conversación. Contrato:
`contracts/sesion-conversacion.md`. Inventario y decisión: `research.md`.

## Technical Context

**Language/Version**: Python 3.14 (venv del proyecto) · **Dependencias nuevas**: ninguna (`contextvars`,
`dataclasses`, `json`, `threading`) · **Testing**: unittest + scripts (`tests/sesion`, `tests/context`,
`tests/clarification`, `tests/routing`, `tests/portero`, `tests/stability`, golden master)
**Restricciones**: `query_engine.py` pasa del máximo de 800 líneas: el cambio no puede hacerlo crecer (baja
62 líneas). Streamlit congelado: cambio mínimo en `app.py`. Capas: `src.chatbot` no importa
`streamlit`/`backend`.

## Diseño

1. `src/chatbot/estado_conversacion.py`: `EstadoConversacion` (memoria, seguimiento, pendientes, intención,
   tableros candidatos; `cerrar_turno`, `reiniciar`, `olvidar_contrapreguntas`; `to_dict`/`from_dict`/
   `to_json`/`from_json` con etiquetas para tuplas, conjuntos y fechas; `candado` por conversación) y el
   ContextVar `sesion_activa()` / `en_sesion()`.
2. `src/chatbot/sesion_motor.py`: `SesionMotorMixin` con descriptores para los atributos históricos
   (`_pending_query_plan`, `_last_success`, `conversation_memory`, `_trace`…), `_turno()` (abre el turno o se
   une al anidado; fija la sesión activa y toma su candado), decorador `con_sesion` (`sesion=`, `progreso=`,
   cierre automático del turno), `reset`/`conversation_history` con `sesion=`, escucha de progreso por
   contexto y despachadores fijos para el proveedor de Power BI.
3. `QueryEngine(SesionMotorMixin)`: `@con_sesion` en `process` y `select_clarification_option`; `__init__` sin
   estado; `_range_choice` por `getattr` (antes `__dict__`).
4. `ConversationManager.state` / `candidate_dashboards`: propiedades sobre la sesión activa (o la propia del
   gestor en modo legado).
5. `ConversationMemory.max_turns` y `load()` para restaurar.
6. `app.py`: `conversacion()` en `st.session_state`; `process(..., sesion=conversacion())`;
   `reset_if_finished(..., sesion=)`; «Nueva conversación» crea un estado nuevo (sin `turn_slot`);
   razonamiento del error desde la sesión.

## Compatibilidad

Sin `sesion=` el motor usa su sesión propia y el gestor la suya, exactamente como antes (los arneses
`tests/sim` y `tests/realistic` siguen llamando `conversation_manager.reset()` y `engine.reset()`). El golden
master (`tests.resolution.test_golden`) usa ese modo y debe quedar idéntico.

## Riesgos

- Colaboradores con temporales del turno (`research.md` §5): por eso se mantiene `turn_slot`.
- Valores no JSON en un pendiente futuro: `to_dict` falla con la ruta (prueba de ida y vuelta en cada turno).

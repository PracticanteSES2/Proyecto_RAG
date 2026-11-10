# Research: inventario del estado mutable del motor (spec 008)

Medido sobre `desarrollo` en `df16e53` (2026-11-10). Líneas de ese commit.

## 1. Cómo se comparte

- `app.py:99` `@st.cache_resource def build_system()`: un solo `QueryEngine` y un solo `ConversationManager`
  para todas las sesiones de Streamlit (`app.py:382`).
- `app.py:362-371` `reset_if_finished` y `app.py:813-831` «Nueva conversación» llamaban
  `conversation_manager.reset()` y `engine.reset(full=True)` sobre los objetos compartidos: borraban el
  contexto de todos.
- `app.py:615-634` `turn_slot`: un turno a la vez en todo el servidor (evitaba turnos simultáneos, NO la
  mezcla entre turnos de personas distintas).

## 2. Estado por conversación (debe ir en la sesión) — ahora en `EstadoConversacion`

| Atributo (antes) | Dónde | Qué guarda | Riesgo | Ahora |
|---|---|---|---|---|
| `QueryEngine._pending_master_metric` | `query_engine.py:126`, 1076, 1360, 6836, 7496 | contrapregunta del resolvedor maestro (intención, opciones, resultado) | B responde la contrapregunta de A | `indicador_pendiente` |
| `QueryEngine._pending_query_plan` | `query_engine.py:127`, 3299, 3334, 3344, 3397, 3419, 3672, 3693, 3853, 3866, 3880, 4668, 6682, 7001, 7197, 7207 | contrapregunta del Query Plan (pregunta, opciones, excluidas, compuesta) | B elige opción de A; «1» de B aplica a A | `plan_pendiente` |
| `QueryEngine._pending_dashboard_clarification` | `query_engine.py:128`, 3496, 6683, 6805, 7049, 7057 | «¿a qué tablero te refieres?» | ídem | `tablero_pendiente` |
| `QueryEngine._last_success` | `query_engine.py:135`, 5041, 5063 | última consulta numérica (indicador, filtros, periodo, agrupación) | «¿y en urología?» se completa con la consulta de otro | `seguimiento` |
| `QueryEngine.conversation_memory` | `query_engine.py:141`; `conversation_memory.py:168` | últimos 12 turnos (texto, interpretación, resumen, datos) | reescritura contextual y RAG con el historial de otro (fuga de lo que preguntó) | `memoria` |
| `QueryEngine._deferred_context_message` | `query_engine.py:149`, 3448, 3807, 6709, 6775 | mensaje de contexto aplazado hasta el botón | se aplica a la elección de otra persona | `mensaje_aplazado` |
| `QueryEngine.last_reasoning` | `query_engine.py:122`, 285, 292; leído en `app.py:631` | razonamiento del último turno (incluye la pregunta) | el error de A muestra el razonamiento de B | `ultimo_razonamiento` (transitorio, no se serializa) |
| `ConversationManager.state` | `conversation_manager.py:23`; `conversation_state.py` | intención, tablero, año/mes, campos faltantes, `awaiting_clarification`, pregunta original | la aclaración de tablero de A captura el mensaje de B | `intencion` |
| `ConversationManager.candidate_dashboards` | `conversation_manager.py:25`, 126, 264, 312, 323, 352 | tableros ofrecidos | ídem | `tableros_candidatos` |

## 3. Estado del turno en curso (no debe compartirse entre turnos simultáneos) — ahora en `_Turno` (ContextVar)

| Atributo | Dónde | Ahora |
|---|---|---|
| `_trace` | `query_engine.py:120`, 251, 297 (y `top_level = self._trace is None`) | `_Turno.trace` |
| `_turn_interpretation` | `query_engine.py:146`, 3446, 5778, 6707, 6775 | `_Turno.turn_interpretation` |
| `_turn_message` | `query_engine.py:6582-6586` | `_Turno.turn_message` |
| `_range_choice` | `query_engine.py:3103`, 3263, 3293 (`__dict__`) | `_Turno.range_choice` |
| `_intent_llm_turn` | `query_engine.py:4775` | `_Turno.intent_llm_turn` |
| `_applying_deferred` | `query_engine.py:150`, 3460-3464 | `_Turno.applying_deferred` |
| `progress_listener` | `query_engine.py:121`, 231-241 | ContextVar `_ESCUCHA` (por hilo/tarea) o `progreso=` |
| `PowerBIProvider.query_listener` / `activity_listener` | `powerbi_provider.py:98-102`, fijados por `query_engine.py:237-241` | despachadores fijos del motor que avisan solo al turno del hilo que consulta |

## 4. Compartible sin riesgo (cachés de dominio puras: dependen del catálogo/modelo, no del usuario)

`QueryEngine._portero_recursos` (6747), `_single_word_tables` (2699); `GuardedQueryPlanDAXGenerator._schemas`;
cachés `*_cache`, `_vocabulary`, `_token_weights`, `_metric_models`… de `src/semantic/resolucion/*`;
`BusinessFilterResolver.value_cache`, `ValoresMixin.value_cache`; `MultiModel*._cache`;
`HybridRetriever._corpus` y sus índices; `SourceModelRouter` (índices); `MedGemmaProvider._clients`;
`PowerBIProvider._connections`; `IndiceSemantico` (intención LLM); `DomainCache._entries/_cards` (valores de
columnas: datos del modelo, sin permisos por usuario en este despliegue); `STATS` (contadores globales a
propósito); `plan_budget` (ya es `threading.local`); `llm_gate._PROGRESS` (ya es ContextVar).
`contextual_rewriter.py` no tiene estado (expresiones regulares y `LLMContextRewriter` sin memoria).

## 5. Pendiente para turnos en paralelo (fuera de esta tarea: no son estado de conversación)

Colaboradores compartidos que guardan temporales de UNA llamada en atributos de instancia. Con `turn_slot`
(un turno a la vez) son correctos; con turnos en paralelo se mezclarían:

| Atributo | Dónde | Efecto si dos turnos se cruzan |
|---|---|---|
| `QueryPlanBuilder._date_metric` | `periodo.py:751-756` | puede elegir la columna de fecha del indicador de OTRO turno (dato equivocado) |
| `QueryPlanBuilder._resolution_notes` | `query_plan_builder.py:207-245`; `contrapregunta.py:288-295`; `homonimos.py:68-75`; `tipo_pregunta.py:453-460`; `intencion_llm.py:1006-1024` | notas de razonamiento de un turno en el plan de otro |
| `QueryPlanBuilder._sibling_exempt` | `query_plan_builder.py:903-915` | exención de hermanos aplicada al turno equivocado |
| `IntentParser.last_dashboard_reason` | `intent_parser.py:203`, 381-395, leído en 720 | motivo del tablero de otro turno (solo razonamiento) |
| `RAGAnswerEngine.last_synthesis_issue` | `rag_answer_engine.py:157-172`, leído en 215 | motivo de redacción de otro turno (solo diagnóstico) |
| `ValoresMixin.domain_errors` | `valores.py:54` | errores de exploración mezclados |
| `DomainCache` turno (`_turn_id`, `_in_turn`, `_failed_turn`, `_avoided_turn`, `_turn_has_code`) | `domain_cache.py:481-498` | presupuesto y reintentos de exploración compartidos entre turnos |

Arreglo sugerido (agente del refactor del motor): pasar esos temporales a variables locales o a un
`threading.local`/ContextVar como `plan_budget`. Cuando estén, `turn_slot` puede pasar a un candado por
conversación (que ya trae `EstadoConversacion.candado`).

## Decisión de API

Se eligió `engine.process(texto, sesion=estado)` (y `select_clarification_option(..., sesion=estado)`) en vez
de `engine.sesion(id)`: no cambia la firma posicional, el estado lo guarda quien conversa (Streamlit o el
backend) y el motor no necesita un registro de sesiones ni su vencimiento. Los atributos históricos del motor
quedan como descriptores (`src/chatbot/sesion_motor.py`), así el código del motor y las pruebas existentes no
cambian: el cambio en `query_engine.py` es localizado (decoradores `@con_sesion`, `__init__` sin estado y
`reset`/`conversation_history`/escucha de progreso movidos al mixin; el archivo baja 62 líneas).

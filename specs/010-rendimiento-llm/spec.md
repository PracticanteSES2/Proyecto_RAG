# Feature Specification: Rendimiento con MedGemma (menos trabajo por turno)

**Feature Branch**: `agente/rendimiento-llm`

**Created**: 2026-11-10

**Status**: Implementada (pendiente de la medición real que corre el usuario)

**Input**: "Según la simulación el servidor rinde 4-8 respuestas redactadas por minuto y ninguna cola cambia
ese techo; con 10 usuarios y turnos en paralelo ~60 % de las síntesis caerían al resumen de respaldo. No se
puede añadir GPU. Subir el techo efectivo reduciendo el trabajo que se le pide a MedGemma por turno, sin
perder calidad. Cerrar los hallazgos del doctor de la herramienta de carga y de Redis en `src`."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Saber dónde se gasta MedGemma (Priority: P1)

El propietario quiere ver, por tipo de turno, cuántas llamadas al LLM se hacen y cuántos tokens de entrada
(prompt) y de salida (`num_predict`) pide cada una, con evidencia archivo:línea y contadores en vivo.

**Independent Test**: `STATS.snapshot()` trae `llm_cost_by_purpose`, `llm_avoided` y `llm_cache`;
`python -m tools.carga --modo componentes` informa llamadas/turno y tokens/turno.

**Acceptance Scenarios**:

1. **Given** una llamada por `call_llm`, **When** termina, **Then** quedan sumados por propósito los
   caracteres del prompt, los tokens estimados, el `num_predict` pedido y, si el proveedor los informa,
   `prompt_eval_count`/`eval_count`.
2. **Given** una llamada evitada (caché, catálogo), **Then** se cuenta en `llm_avoided` con su motivo.

### User Story 2 - Más respuestas redactadas por minuto con la misma GPU (Priority: P1)

Las preguntas documentales repetidas (misma pregunta normalizada, mismas fuentes, mismo prompt) no vuelven a
llamar a MedGemma; las descripciones de opciones ya pedidas tampoco; las peticiones idénticas simultáneas se
agrupan en una sola llamada.

**Independent Test**: con el simulador, `--modo componentes` antes (`--sin-palancas`) y después: menos
llamadas/turno, más respuestas redactadas por minuto y menos respaldo extractivo con 5/10/20 usuarios.

**Acceptance Scenarios**:

1. **Given** una síntesis exitosa y completa, **When** se repite la pregunta (con otra forma: tildes,
   mayúsculas, signos) con las mismas fuentes, **Then** no hay llamada al LLM y la respuesta es la misma.
2. **Given** una síntesis saturada, con tiempo agotado, vacía, «sin evidencia» o truncada
   (`done_reason=length`), **Then** no se guarda.
3. **Given** cambian las fuentes (otro chunk, otro texto) o el prompt (versión), **Then** la clave cambia.
4. **Given** dos turnos simultáneos con la misma clave, **Then** una sola llamada llega al LLM.
5. **Given** `LLM_CACHE=off`, **Then** el comportamiento es el de antes.

### User Story 3 - Capas limpias para Redis (Priority: P2)

`src` no importa `redis`: el semáforo distribuido y el almacén Redis de la caché viven en
`backend/app/services/` y se inyectan en la puerta/caché, que solo conocen un `Protocol`.

**Acceptance Scenarios**:

1. **Given** el doctor, **Then** no hay hallazgo `src → redis` ni `tools → tests`.
2. **Given** `LLM_GATE_BACKEND=redis` sin adaptador instalado o con Redis caído, **Then** la puerta usa
   memoria con advertencia (como antes).

### User Story 4 - La herramienta de carga escribe en `var/out/carga/` (Priority: P3)

## Requirements *(mandatory)*

- **FR-001**: contadores nuevos en `runtime_stats` solo AÑADIDOS (no se cambia ningún campo existente).
- **FR-002**: caché de llamadas al LLM en el motor (`src/chatbot/cache_llm.py`) con almacén enchufable:
  memoria LRU con TTL por defecto; Redis detrás de la misma interfaz (probado con fakeredis).
- **FR-003**: clave = versión del formato + propósito + pregunta normalizada (normalizador existente
  `question_normalizer`) + huella de las fuentes usadas + huella del prompt + modelo + `max_tokens` +
  versión opcional de índice/documentación.
- **FR-004**: nunca se guardan respuestas degradadas, truncadas, vacías ni «sin evidencia».
- **FR-005**: el post-proceso (grounding, limpieza, truncado) se aplica SIEMPRE a la respuesta cruda,
  también si viene de la caché.
- **FR-006**: no se toca `num_predict` ni el manejo de truncadas (rama `agente/truncado`).
- **FR-007**: `tools/carga` sin importar `tests` (el motor del simulador e2e se inyecta desde
  `tools/manual/carga_e2e.py`, carpeta exenta) y con salidas en `var/out/carga/`.

## Success Criteria *(mandatory)*

- **SC-001**: llamadas al LLM por turno y respaldo extractivo con 10 usuarios bajan en la simulación
  `componentes` frente a `--sin-palancas`.
- **SC-002**: todas las pruebas existentes pasan (calidad protegida) y el doctor no baja.

## Assumptions

- La tasa de aciertos de la caché depende de cuánto se repiten las preguntas; el simulador usa un supuesto
  explícito (popularidad Zipf sobre un banco de preguntas) que se debe calibrar con el registro real.

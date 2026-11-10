# Feature Specification: Progreso del chat («pensando» amable)

**Feature Branch**: `agente/ui-progreso`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Para el usuario final mostrar segundos, pasos técnicos y razonamiento hace que
parezca que el bot está lento o colgado, sobre todo cuando MedGemma está saturado. Frases cortas y humanas
que reflejen la etapa real, mensajes tranquilizadores escalonados en esperas largas, aviso amable si la
respuesta se degrada, charla al instante." Ajuste del orquestador (2026-11-10): se abandona Streamlit; el
nuevo stack es FastAPI + Next.js + Redis. Este trabajo entrega la parte independiente de framework: un
módulo Python puro que traduce los eventos del motor a eventos `progreso`/`espera`/`cola`/`aviso`
serializables a JSON (el backend los envía por SSE y el frontend los pinta).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver que el asistente trabaja, sin tecnicismos (Priority: P1)

Una persona del hospital pregunta «¿cuántas cirugías hubo en octubre?». Mientras espera recibe una frase
corta que cambia con la etapa real: «Entendiendo tu pregunta» → «Buscando el indicador en los tableros» →
«Consultando los datos en Power BI». Nunca ve segundos, contadores, nombres de modelos, DAX ni pasos internos.

**Why this priority**: es lo que ve el usuario en cada pregunta; la lista de pasos con segundos da sensación
de lentitud o de bloqueo.

**Independent Test**: alimentar `TraductorProgreso` con los eventos reales de `ReasoningTrace`; sale un
evento `progreso` por cambio de etapa, con frase sin dígitos ni términos técnicos.

**Acceptance Scenarios**:

1. **Given** el motor avisa «Consultando Power BI (MODELO)» con el DAX, **When** se traduce, **Then** sale `progreso` con etapa `consultando_powerbi` y una frase de esa etapa, sin el modelo ni el DAX.
2. **Given** varias actividades seguidas de la misma etapa (p. ej. tres consultas a Power BI), **Then** solo se emite el primer `progreso`.
3. **Given** dos turnos de la misma sesión pasan por la misma etapa, **Then** la frase no se repite respecto del turno anterior.
4. **Given** el turno vuelve a una etapa ya vista, **Then** la frase cambia por otra variante.

---

### User Story 2 - Esperas largas tranquilizadoras (Priority: P1)

Si la respuesta tarda, el backend emite eventos `espera` escalonados (≈10, 25, 50, 90 s) que reemplazan al
anterior: «Esto está tomando un poco más de lo normal…», luego uno según la etapa («Power BI está tardando
en responder; sigo esperando los datos.» o «Hay varias consultas en curso; la tuya está en fila, ya casi…»),
luego «Sigue en marcha: no hace falta volver a enviar la pregunta.».

**Independent Test**: reloj falso; `tic()` emite `espera` solo al cruzar cada umbral y, si se atrasó, solo el
nivel más alto.

**Acceptance Scenarios**:

1. **Given** 10 s sin respuesta, **When** el backend llama `tic()`, **Then** sale `espera` nivel 1; un segundo `tic()` en el mismo nivel no emite nada.
2. **Given** la carga del LLM está ocupada y la etapa usa MedGemma, **Then** el nivel 2 habla de consultas en fila.
3. **Given** el turno espera a otro (candado de turno hoy, cola de Redis mañana), **Then** sale `progreso` con etapa `en_cola` una vez y `cola` {posicion, en_curso} en cada actualización.

---

### User Story 3 - Respuesta degradada explicada con amabilidad (Priority: P2)

Si la respuesta documental sale como resumen extractivo (MedGemma saturado o sin respuesta), se emite
`aviso` con un texto breve y no técnico.

**Acceptance Scenarios**:

1. **Given** ruta `rag`, `synthesis_mode = "extractive"` y «saturado» en el razonamiento, **Then** `aviso` motivo `saturado`.
2. **Given** ruta `rag` extractiva por otro motivo, **Then** `aviso` motivo `sin_redaccion`.
3. **Given** cualquier otra respuesta, **Then** no hay `aviso`.

---

### User Story 4 - Charla al instante (Priority: P2)

«hola», «gracias» (portero, ruta `conversacion`, < 1 s) no deben mostrar el indicador: el contrato pide al
frontend no pintarlo antes de 600 ms (ver contracts/eventos.md).

### Edge Cases

- Evento sin título, de tipo desconocido o que no es un dict: no se emite nada, sin error.
- Lectura de la carga del LLM que falla: se asume sin carga (mensajes genéricos).
- `tic()` llamado tarde (backend ocupado): solo el nivel de espera más alto alcanzado.
- Posición o en curso negativos o nulos en `cola`: se llevan a 0.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El módulo MUST ser Python puro, sin dependencias de interfaz (`src/chatbot/progreso.py`).
- **FR-002**: Las etapas MUST ser: `entendiendo`, `buscando_indicador`, `preparando_opciones`, `conectando_powerbi`, `consultando_powerbi`, `revisando_documentacion`, `redactando`, `en_cola`, `finalizando`.
- **FR-003**: Cada actividad que emite hoy el motor MUST traducirse a su etapa; los pasos y lo desconocido no cambian la etapa. «LLM en cola» y «Redactando…» quedan reservados como ganchos.
- **FR-004**: Cada etapa MUST tener ≥3 variantes; la elección evita repetir dentro del turno y respecto de la memoria de la sesión (máx. 12 frases).
- **FR-005**: Los textos visibles MUST NOT incluir dígitos ni términos técnicos (MedGemma, DAX, Query Plan, LLM, RAG, modelo semántico).
- **FR-006**: Los eventos MUST ser serializables a JSON con la forma del contrato (`progreso`, `espera`, `cola`, `aviso`), envueltos en `{"evento", "datos"}`.
- **FR-007**: `progreso` MUST emitirse solo cuando cambia la etapa.
- **FR-008**: `espera` MUST emitirse al cruzar cada umbral (10, 25, 50, 90 s desde el inicio del turno); el nivel 2 depende de la etapa y de la carga del LLM.
- **FR-009**: La carga del LLM MUST leerse por un único punto de enganche (`leer_carga_llm`): hoy `STATS.llm` + `llm_gate.max_concurrent()`; si existe `STATS.llm_pressure()`, eso.
- **FR-010**: `aviso` MUST emitirse solo para respuestas documentales extractivas.
- **FR-011**: Ningún método del traductor MUST lanzar.

### Key Entities

- **Etapa**: fase real del turno con variantes de frase.
- **Evento**: sobre `{"evento": nombre SSE, "datos": dict}`.
- **Carga del LLM**: en curso, en cola, capacidad, ocupado.

## Success Criteria *(mandatory)*

- **SC-001**: 0 dígitos y 0 términos técnicos en todas las frases, esperas y avisos (prueba sobre el catálogo completo).
- **SC-002**: el 100 % de los títulos de actividad del motor tienen etapa (prueba sobre la lista).
- **SC-003**: 10 turnos seguidos por la misma etapa sin dos frases iguales consecutivas.
- **SC-004**: `tests/progreso` en verde sin interfaz ni servicios externos.

## Assumptions

- El motor sigue emitiendo `{"kind", "title", "t", "lines"}` por `set_progress_listener`.
- El backend FastAPI ejecuta el motor en un hilo y puede llamar `tic()` mientras espera.
- Streamlit (`app.py`) queda congelado como legado; no se modifica.
- La parte visual (animación, brillo, transiciones) la hace el frontend Next.js.

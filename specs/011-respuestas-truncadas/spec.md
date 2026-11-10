# Feature Specification: Respuestas completas (truncado por `num_predict` y por `num_ctx`)

**Feature Branch**: `agente/truncado`

**Created**: 2026-11-10

**Status**: Implementada

**Input**: «Las respuestas del LLM pueden quedar cortadas por `num_predict` (600 tokens en la síntesis) y a veces
terminan a mitad de frase, de tabla o de lista. `MedGemmaProvider.chat` ya devuelve `done_reason`, `truncated` y
`eval_count`, pero nadie actúa sobre eso. Si el prompt supera el `num_ctx` del servidor, Ollama recorta la
ENTRADA sin avisar.»

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Nunca ver una respuesta cortada a la mitad (Priority: P1)

Quien pregunta por la documentación recibe siempre una respuesta que termina en una frase, fila de tabla o
ítem de lista completos, con el Markdown bien cerrado. Si no se pudo completar, una línea discreta dice
«La respuesta completa está en el tablero» (con el enlace de Power BI si existe); nunca un texto técnico.

**Independent Test**: `python -X utf8 -m unittest tests.rag.test_respuesta_completa` (dobles que devuelven
`done_reason="length"`).

**Acceptance Scenarios**:

1. **Given** una síntesis con `truncated=True` que termina en «…el indicador se calcula divid», **When** se
   repara, **Then** la respuesta termina en la última frase completa y lleva la línea del tablero.
2. **Given** una tabla Markdown cuya última fila quedó a medias, **Then** se quita esa fila y se conservan las
   completas; si no queda ninguna fila de datos, se quita la tabla.
3. **Given** «Dr.», «p. ej.» o un decimal («3.5») al final, **Then** no se toman como fin de frase.
4. **Given** un bloque de código o negrita abiertos, **Then** se cierran.
5. **Given** que tras cortar no queda contenido, **Then** se usa el resumen extractivo (como cuando el LLM
   falla) y el razonamiento lo explica.

### User Story 2 - Completar cuando hay tiempo y el servidor está libre (Priority: P2)

Si la respuesta quedó truncada, el presupuesto de tiempo de la síntesis alcanza (según la velocidad medida
de la propia llamada) y MedGemma no tiene fila ni saturación reciente (`STATS.llm_pressure()`), se hace UNA
llamada de continuación y se une sin repetir. Si hay fila, no se continúa.

**Acceptance Scenarios**:

1. **Given** presión 0 y tiempo de sobra, **Then** una sola llamada extra y respuesta unida sin línea de aviso.
2. **Given** `waiting > 0`, `in_flight >= capacity` o saturación reciente, **Then** no se llama y se corta.
3. **Given** que la continuación también se trunca, **Then** se corta el conjunto y va la línea de aviso.

### User Story 3 - Que la entrada nunca supere `num_ctx` (Priority: P1)

Antes de llamar se estiman los tokens de entrada. Si superarían `num_ctx - num_predict - margen`, se quitan
las fuentes menos relevantes (las últimas) y, si con una sola no cabe, se recorta su texto; queda en la traza.

### User Story 4 - Diagnóstico (Priority: P2)

La traza del turno (razonamiento) muestra `truncada: sí/no`, tokens de entrada (reales o estimados) y de
salida, `num_predict`/`num_ctx`, si se recortó la entrada y qué reparación se aplicó.

### Edge Cases

- La respuesta truncada y reparada (corte + aviso) se marca `cacheable=False`: ningún caché debe guardarla.
- Streaming (`agente/ux-espera`): el borrador que llega por `on_token` es provisional; la respuesta FINAL
  (reparada, anclada y con aviso) reemplaza al borrador completo al terminar.
- Proveedores/dobles sin `truncated`: se comportan como hoy.

## Requirements *(mandatory)*

- **FR-001**: `num_predict` por propósito configurable por entorno (`LLM_NUM_PREDICT_<PROPOSITO>`).
- **FR-002**: La TAREA de la síntesis pide una extensión objetivo derivada de `num_predict`.
- **FR-003**: Estimación de tokens de entrada y recorte controlado contra `MEDGEMMA_NUM_CTX`.
- **FR-004**: Corte en límite seguro + cierre de Markdown cuando `truncated`.
- **FR-005**: Una continuación opcional sujeta a tiempo y presión; `RAG_CONTINUAR_TRUNCADA=0` la apaga.
- **FR-006**: Línea discreta de aviso con enlace de Power BI cuando existe.
- **FR-007**: Diagnóstico en la traza; `cacheable=False` en lo truncado no completado.
- **FR-008**: Reescritura truncada se rechaza; descripción de opción truncada se corta o se descarta.

## Success Criteria

- **SC-001**: Ninguna respuesta con `truncated=True` sale del motor sin pasar por la reparación.
- **SC-002**: Suites `tests.rag`, `tests.redaccion`, `tests.sim` y `tests.perf` en verde.

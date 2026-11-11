# Feature Specification: Experiencia de espera (trabajando en TU pregunta + respuesta que aparece de a poco)

**Feature Branch**: `agente/ux-espera`

**Created**: 2026-11-10

**Status**: Implementado (motor, contrato y Streamlit); frontend pendiente de integrar

**Input**: Decisión del usuario: mostrar la saturación con frases como «Hay dos consultas antes que la tuya, ya
casi…», «Hay varias consultas en curso; la tuya está en fila», «Hay otra consulta en curso…» o «Tu pregunta está
en fila» es HORRIBLE. Al usuario no le importa si hay otras consultas: eso daña la percepción de que la
herramienta funciona. La espera debe sentirse como que el asistente está TRABAJANDO en SU pregunta y tarda un
poco («pensando…», etapas de trabajo), o la respuesta debe ir apareciendo de a poco. Nunca se menciona a otros
usuarios, filas, colas, saturación ni posiciones.

Reemplaza las historias 2 (nivel 2 «en fila») y 3 (aviso «muchas consultas a la vez») de
`specs/003-progreso-chat/spec.md` y la etapa `en_cola`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - La espera se siente como trabajo sobre mi pregunta (Priority: P1)

Una persona del hospital pregunta por un procedimiento documentado mientras MedGemma atiende a otras. Ve
«Revisando la documentación de los tableros» → (8 s después) «Revisando los datos que encontré» →
«Organizando la respuesta» → «Redactando la respuesta». Nunca lee «fila», «cola», «otra consulta», «en curso»,
«ocupado», «saturado» ni una posición.

**Why this priority**: es lo que ve cada persona cuando el servidor está cargado; hablar de otros da la
impresión de que la herramienta no funciona.

**Independent Test**: `TraductorProgreso` con reloj falso: la actividad «LLM en cola…» y `esperando_turno()` no
cambian la etapa visible; `tic()` rota la frase de la etapa cada `ROTACION_S` s; ningún texto visible del
catálogo contiene vocabulario de cola.

**Acceptance Scenarios**:

1. **Given** el motor avisa «LLM en cola: posición 2, 3 en curso», **When** se traduce, **Then** no sale ningún
   `progreso` nuevo (se mantiene la etapa de trabajo actual).
2. **Given** el turno espera a otro turno (candado o cola de Redis), **When** el backend llama
   `esperando_turno(posicion, en_curso)`, **Then** solo sale `cola` (para el modo diagnóstico); la etapa visible
   sigue siendo de trabajo («Entendiendo tu pregunta»).
3. **Given** una etapa dura más de `ROTACION_S` (8 s), **When** el backend llama `tic()`, **Then** sale
   `progreso` con la MISMA etapa y otra frase de su secuencia de seguimiento; no se repite la frase anterior.
4. **Given** todo el catálogo (frases, seguimientos, esperas, avisos), **Then** ningún texto menciona colas,
   filas, turnos, posiciones, otras consultas, usuarios, servidor, ocupación ni saturación, ni lleva dígitos.

---

### User Story 2 - Esperas largas que tranquilizan sin hablar de otros (Priority: P1)

Si tarda, el renglón secundario dice «Sigo trabajando en tu pregunta…», luego «Estoy armando una respuesta
completa; ya casi la tengo…» (o, si espera a Power BI, «Las cifras de Power BI están tardando un poco; sigo
pendiente.»), luego «Sigo con tu pregunta; no hace falta volver a enviarla.».

**Independent Test**: `frase_espera(nivel, etapa)` y `tic()` con reloj falso.

**Acceptance Scenarios**:

1. **Given** 10 s sin respuesta, **Then** `espera` nivel 1 «Sigo trabajando en tu pregunta…».
2. **Given** nivel 2 en una etapa de Power BI, **Then** habla de Power BI; en el resto, de la respuesta propia;
   nunca de la carga del servidor (ya no se consulta la carga para el texto).
3. **Given** ya empezaron a llegar tokens de la respuesta, **Then** `tic()` no emite más rotaciones ni esperas.

---

### User Story 3 - La respuesta aparece de a poco (Priority: P1)

En una pregunta documental la respuesta se va escribiendo en la burbuja mientras MedGemma la genera. Al
terminar, la respuesta validada (salvaguarda de cifras, limpieza, truncado) reemplaza el borrador sin salto
visual si coincide, o con un fundido suave si cambió.

**Independent Test**: proveedor con cliente Ollama falso en streaming; `call_llm(on_token=...)`;
`AnswerSynthesizer.synthesize_rag(on_token=...)` y `RAGAnswerEngine.answer` con
`escuchar_tokens(...)`: los tokens llegan en orden, el resultado final es idéntico al de la llamada sin
streaming y sin `on_token` nada cambia.

**Acceptance Scenarios**:

1. **Given** `MedGemmaProvider.chat(stream=True, on_token=cb)`, **Then** `cb` recibe cada fragmento y el dict
   devuelto es el mismo que sin streaming (`status`, `answer` completo, `done_reason`, `truncated`, `eval_count`).
2. **Given** el tiempo límite de la llamada vence a mitad del stream, **Then** se cierra la conexión y vuelve
   `llm_timeout` (como sin streaming).
3. **Given** `cb` lanza, **Then** la llamada sigue y su resultado no cambia.
4. **Given** `call_llm(..., on_token=cb)` con un proveedor que no admite `on_token`, **Then** se comporta como
   antes (sin tokens) y con los mismos `status`; tras abandonar una llamada por tiempo, ya no se reenvían tokens.
5. **Given** la respuesta empieza por la frase de «sin evidencia» o por una muletilla («Claro, …»), **Then**
   esa parte no se transmite (el borrador nunca muestra lo que el post-proceso quitará al inicio).
6. **Given** una respuesta numérica de Power BI (sin LLM), **Then** no hay tokens; el frontend la revela con un
   efecto de escritura rápido (≤ ~700 ms) y sin efecto si el usuario pidió menos movimiento.

---

### User Story 4 - Degradación sin culpar a la carga (Priority: P2)

Si la respuesta documental sale como resumen extractivo, se presenta como respuesta normal con, como mucho, la
nota neutra «Te muestro lo que dice la documentación.». El motivo (`saturado` / `sin_redaccion`) queda solo para
el modo diagnóstico.

**Acceptance Scenarios**:

1. **Given** síntesis extractiva por saturación o por tiempo, **Then** `aviso` lleva el mismo texto neutro.

---

### User Story 5 - Streamlit legado sin textos de cola (Priority: P3)

En `app.py` el aviso «Esperando a que termine otra consulta en curso…» pasa a «Pensando en tu pregunta…» y el
mensaje de `TurnBusy` deja de mencionar otras consultas. Sin streaming.

### Edge Cases

- El RAG no halla evidencia y el motor cae al Query Plan: el borrador (si hubo) se reemplaza por la respuesta
  final; la frase de «sin evidencia» nunca se transmitió.
- La salvaguarda (`src/rag/grounding.py`) quita una frase con una cifra no respaldada: el reemplazo final es un
  fundido suave, no un salto.
- El stream termina mientras se retenía el inicio (respuesta muy corta): no hay tokens; llega la final.
- Turno del portero o respuesta de Power BI: sin tokens.

## Requirements *(mandatory)*

- **FR-001**: Ningún texto visible del progreso, la espera, el aviso ni el legado menciona colas, filas,
  turnos, posiciones, otras consultas, otros usuarios, el servidor, ocupación ni saturación.
- **FR-002**: Se elimina la etapa `en_cola`; las esperas de hueco y de turno mantienen la etapa de trabajo.
- **FR-003**: Rotación lenta (`ROTACION_S` = 8 s) de frases dentro de la etapa, en orden de progreso.
- **FR-004**: El evento `cola` se mantiene solo para el modo diagnóstico.
- **FR-005**: Nuevo evento SSE `token {texto}` (fragmento a añadir al borrador).
- **FR-006**: `MedGemmaProvider.chat(stream=True, on_token=cb)`; `call_llm` deja pasar `on_token` sin romper su
  contrato; `AnswerSynthesizer.synthesize_rag` y `RAGAnswerEngine.answer` aceptan `on_token` opcional; sin él, el
  comportamiento es idéntico.
- **FR-007**: El post-proceso completo (limpieza, salvaguarda de cifras, truncado) sigue aplicándose a la
  respuesta final, que reemplaza al borrador.
- **FR-008**: `escuchar_tokens(on_token)` permite al backend recibir los tokens sin tocar `query_engine`.

## Success Criteria *(mandatory)*

- **SC-001**: 0 textos visibles con vocabulario de cola (prueba automática sobre todo el catálogo).
- **SC-002**: En una pregunta documental el primer texto de la respuesta aparece con el primer fragmento útil
  del modelo, no al final de la generación.
- **SC-003**: Resultados de `call_llm` y de la síntesis idénticos con y sin `on_token` (pruebas).

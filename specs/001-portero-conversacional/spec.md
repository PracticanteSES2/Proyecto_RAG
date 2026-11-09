# Feature Specification: Portero conversacional

**Feature Branch**: `desarrollo` (sin rama propia, por decisión del usuario)

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "Portero conversacional: responder saludo, agradecimiento, despedida, «¿cómo estás?», «¿quién eres?» y «¿qué puedes hacer?» sin buscar en la documentación ni en Power BI, sin interceptar nunca una pregunta real del dominio. Fuente aprobada: docs/superpowers/specs/2026-11-09-portero-conversacional-design.md y docs/superpowers/plans/2026-11-09-portero-conversacional.md."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Saludar y recibir una respuesta natural (Priority: P1)

Un funcionario del hospital abre el asistente y escribe «hola», «¿cómo estás hoy?», «gracias» o
«chao». Hoy recibe «No encontré información relacionada con esa pregunta en la
documentación…», lo que hace parecer roto al asistente. Debe recibir una respuesta breve y
cordial, al instante, que lo invite a preguntar por los indicadores.

**Why this priority**: es lo primero que hace un usuario nuevo y fue el fallo observado con
un usuario real de prueba.

**Independent Test**: escribir las cuatro frases en una conversación nueva; cada una recibe
la respuesta conversacional correspondiente sin consultar documentación ni datos.

**Acceptance Scenarios**:

1. **Given** una conversación nueva, **When** el usuario escribe «¿Cómo estás hoy?», **Then** recibe un saludo breve con un ejemplo de pregunta y no se consulta documentación ni datos.
2. **Given** una respuesta de datos ya entregada, **When** el usuario escribe «gracias», **Then** recibe «Con gusto…» sin consultas.
3. **Given** cualquier momento sin contrapregunta abierta, **When** el usuario escribe «chao», **Then** recibe una despedida breve.

---

### User Story 2 - Saber qué puede hacer el asistente (Priority: P1)

El usuario escribe «¿qué puedes hacer?» o «ayuda» y recibe la lista de tableros que el
sistema conoce, separada en **Datos** (cifras consultables) y **Documentación** (explicación
de qué muestra y cómo se calcula), con un ejemplo de pregunta. «¿Quién eres?» explica qué es el
asistente y que no da recomendaciones clínicas.

**Why this priority**: orienta al usuario nuevo y fija expectativas correctas (qué responde
con cifras y qué no).

**Independent Test**: preguntar «¿qué puedes hacer?» y comprobar que los tableros listados
coinciden con el catálogo vigente, en dos grupos sin duplicados.

**Acceptance Scenarios**:

1. **Given** un catálogo con tableros consultables y otros solo documentados, **When** el usuario pregunta «¿qué puedes hacer?», **Then** ve dos grupos; un tablero que está en ambos aparece solo en «Datos».
2. **Given** un catálogo no disponible, **When** pregunta «¿qué puedes hacer?», **Then** recibe un texto genérico con un ejemplo, sin error.
3. **Given** cualquier momento sin contrapregunta abierta, **When** pregunta «¿quién eres?», **Then** se identifica como asistente de los tableros del Hospital Universitario de Caldas y aclara que no da recomendaciones clínicas.

---

### User Story 3 - Las preguntas reales nunca se desvían (Priority: P1)

Quien hace una pregunta de datos o documentación, aunque sea corta o empiece con un saludo,
sigue recibiendo exactamente la misma respuesta que hoy. Los seguimientos y las respuestas a
contrapreguntas no se confunden con charla.

**Why this priority**: es el anti-objetivo principal; desviar una pregunta real es peor que
el problema que se resuelve.

**Independent Test**: pasar todas las preguntas de los bancos de evaluación existentes y del
banco nuevo de preguntas cortas/ambiguas; ninguna recibe respuesta conversacional.

**Acceptance Scenarios**:

1. **Given** una conversación nueva, **When** el usuario escribe «hola, ¿cuántas cirugías hubo en octubre?», **Then** recibe la respuesta de datos, no un saludo.
2. **Given** el asistente acaba de preguntar «¿A qué indicador te refieres?», **When** el usuario responde «ninguna» o «gracias», **Then** se trata como respuesta a la contrapregunta.
3. **Given** una pregunta de datos respondida, **When** el usuario escribe «gracias» y luego «¿y en octubre?», **Then** el tercer turno es un seguimiento de la pregunta de datos original.

### Edge Cases

- Mensajes con tipeos o jerga de chat («holaa», «q tal», «grax», «buenas»).
- Saludo seguido de una palabra del dominio («buenas, ocupación»): va al flujo normal.
- Seguimientos cortos sin palabras del dominio («¿y en octubre?», «el anterior», «la 2»).
- Mensajes largos que empiezan con saludo y luego cuentan un caso: van al flujo normal.
- El componente de similitud no está disponible o falla: solo reglas, sin error visible.
- El catálogo está vacío o no carga: texto genérico de capacidades.
- El mismo mensaje conversacional se repite: misma respuesta, sin efectos en la memoria.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST reconocer y responder sin consultar documentación ni datos los mensajes de tipo saludo, agradecimiento, despedida, estado («¿cómo estás?»), identidad («¿quién eres?») y capacidades («¿qué puedes hacer?», «ayuda»).
- **FR-002**: El sistema MUST NOT dar respuesta conversacional cuando hay una contrapregunta abierta o se está aplicando la elección de una opción.
- **FR-003**: El sistema MUST NOT dar respuesta conversacional si el mensaje contiene números, referencias a periodos, palabras del catálogo de tableros/indicadores o más de 8 palabras tras quitar el saludo. «hoy» por sí solo no cuenta como periodo («¿cómo estás hoy?» sí es charla), salvo que el mensaje sea entero una o dos frases de regla sin ediciones (p. ej. «buenos días a todos», «hasta mañana»); la guarda de número, la lista de bloqueo y el estado pendiente siempre aplican.
- **FR-004**: Ante cualquier duda o fallo interno, el mensaje MUST seguir el flujo actual sin cambios.
- **FR-005**: La respuesta de capacidades MUST construirse desde el catálogo vigente en dos grupos: «Datos» (tableros consultables) y «Documentación» (solo documentados), sin duplicados; un grupo vacío no se muestra; sin catálogo, texto genérico.
- **FR-006**: La respuesta de identidad MUST indicar que el asistente no da recomendaciones clínicas.
- **FR-007**: Las respuestas MUST ser textos fijos (sin generación por modelo de lenguaje).
- **FR-008**: Un turno conversacional MUST NOT alterar el contexto de seguimiento de la conversación; sí aparece en la conversación visible y exportada.
- **FR-009**: El razonamiento visible MUST indicar que el mensaje se respondió como conversacional y por qué (regla o similitud).
- **FR-010**: El registro de calificaciones MUST guardar el turno conversacional con su ruta propia y su texto completo.
- **FR-011**: El reconocimiento MUST tolerar variantes y tipeos comunes mediante comparación por similitud con frases de ejemplo, con un umbral conservador.

### Key Entities

- **Clasificación conversacional**: tipo (charla, identidad, capacidades), subtipo (saludo, agradecimiento, despedida, estado, identidad, capacidades), confianza y motivo (regla o similitud).
- **Banco del portero**: mensajes etiquetados como conversacionales (con su tipo) o como preguntas reales que deben pasar al flujo normal.
- **Catálogo de tableros**: tableros consultables y tableros documentados, con sus nombres legibles.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 preguntas reales interceptadas en todos los bancos de evaluación existentes (desarrollo, holdout 1, holdout 2, multi-turno) y en las ~60 preguntas reales del banco del portero.
- **SC-002**: ≥75 % de los mensajes conversacionales del banco reconocidos solo con reglas; ≥90 % con la comparación por similitud.
- **SC-003**: Las 5 frases del caso real («¿Cómo estás hoy?», «hola», «gracias», «¿quién eres?», «¿qué puedes hacer?») se responden sin ninguna consulta de datos ni documentación.
- **SC-004**: Los porcentajes de acierto de los bancos (desarrollo 96 %, holdout 1 80 %, holdout 2 22 %, multi-turno) no bajan.
- **SC-005**: La respuesta conversacional aparece en menos de 1 segundo.

## Assumptions

- Calibración solo con el banco del portero y el banco de desarrollo; holdouts y multi-turno solo como prueba ciega.
- La similitud reutiliza el modelo de embeddings ya cargado por el buscador de documentación; no se instalan modelos nuevos ni se usa el servidor compartido.
- Rechazo de consejo clínico, «no sé» diferenciado y preguntas fuera del hospital quedan para una segunda entrega.
- Power BI y bases de datos: solo lectura; nada de datos de pacientes en salidas, logs o commits.

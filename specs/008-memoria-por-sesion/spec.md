# Feature Specification: Memoria de conversación por sesión

**Feature Branch**: `agente/memoria-sesion`

**Created**: 2026-11-10

**Status**: Implementada (pendiente de revisión)

**Input**: "La memoria de conversación es COMPARTIDA entre todos los usuarios: `app.py` crea un único motor con
`@st.cache_resource` y el `QueryEngine` guarda en atributos de instancia el contexto conversacional. El
seguimiento de una persona («¿y en urología?») puede completarse con la pregunta de otra; una contrapregunta o
un plan pendiente de un usuario puede aplicarse a otro; «Nueva conversación» borra el contexto de todos. Es una
fuga de información entre usuarios y un error de exactitud."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cada persona conversa con su propio contexto (Priority: P1)

Dos personas usan el asistente a la vez. Ana pregunta «cirugías programadas de abril de 2025» y Beto
«atenciones de marzo de 2024»; luego los dos escriben «¿y en urología?». Cada uno recibe el seguimiento de SU
pregunta.

**Why this priority**: hoy el seguimiento puede responder con el indicador, el periodo o los filtros de otra
persona (dato equivocado y fuga de lo que preguntó otro).

**Independent Test**: `tests/sesion/test_sesion_conversacion.py::AislamientoTest::test_seguimientos_intercalados_no_se_contaminan`.

**Acceptance Scenarios**:

1. **Given** dos conversaciones intercaladas, **When** cada una pide «¿y en urología?», **Then** A obtiene
   CIRUGÍAS PROGRAMADAS de abril 2025 y B TOTAL ATENCIONES de marzo 2024, ambas con ESPECIALIDAD = UROLOGIA, y
   la memoria de cada una solo tiene sus turnos.

---

### User Story 2 - Una contrapregunta es de quien la recibió (Priority: P1)

Si Ana tiene abierta «¿cuál indicador de cirugías realizadas?», un «1» o un botón de Beto no la responde.

**Independent Test**: `test_contrapregunta_pendiente_de_a_no_la_responde_b`.

**Acceptance Scenarios**:

1. **Given** A con contrapregunta abierta, **When** B elige la opción de A o escribe «1», **Then** B recibe
   «No hay una aclaración pendiente» o una respuesta propia, y A conserva su contrapregunta y la resuelve.

---

### User Story 3 - «Nueva conversación» solo reinicia la propia (Priority: P1)

**Independent Test**: `test_reiniciar_a_no_afecta_b`.

**Acceptance Scenarios**:

1. **Given** A y B con contexto, **When** A pulsa «Nueva conversación», **Then** B sigue con su seguimiento.

---

### User Story 4 - El backend guarda y restaura la conversación (Priority: P1)

El backend FastAPI guardará el estado en memoria o Redis con TTL entre peticiones.

**Independent Test**: `test_estado_sobrevive_serializar_y_restaurar` y
`test_cada_turno_serializa_y_restaura_igual` (ida y vuelta por JSON en cada turno = mismas respuestas).

**Acceptance Scenarios**:

1. **Given** una conversación con seguimiento o con una contrapregunta abierta, **When** se serializa a JSON y
   se restaura, **Then** el siguiente turno responde igual que sin serializar.

---

### User Story 5 - Turnos simultáneos sin pisarse (Priority: P2)

**Independent Test**: `ConcurrenciaTest` (hilos con turnos en serie como Streamlit, y dos turnos a la vez
dentro del motor con el cuerpo del turno falso).

### Edge Cases

- Sin `sesion=` (pruebas, scripts, arneses): modo legado de un solo usuario, comportamiento idéntico al de antes.
- Turno que lanza excepción con `sesion=`: se cierra como error (igual que `reset_if_finished` con el error).
- Dos turnos a la vez de la MISMA conversación: se ejecutan en serie (candado de la sesión).
- Estado de otra versión o corrupto: `from_dict`/`from_json` lanzan `ValueError` (empezar conversación nueva).
- Un valor interno no representable en JSON: `to_dict` lanza `TypeError` con la ruta del valor.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El estado mutable por conversación (memoria, seguimiento, contrapreguntas/planes pendientes,
  mensaje aplazado, estado del analizador de intención) DEBE vivir en un `EstadoConversacion` explícito.
- **FR-002**: `QueryEngine.process` y `select_clarification_option` DEBEN aceptar `sesion=` y, con ella, leer y
  escribir solo esa conversación y cerrar el turno solos.
- **FR-003**: `EstadoConversacion` DEBE serializarse a JSON puro y restaurarse sin pérdida (versión explícita).
- **FR-004**: Los datos del turno en curso (razonamiento, interpretación, mensaje, escucha de progreso) DEBEN ser
  por turno (contextvars), no atributos compartidos.
- **FR-005**: `app.py` DEBE guardar la conversación de cada pestaña en `st.session_state` y pasarla al motor;
  «Nueva conversación» solo reinicia la suya.
- **FR-006**: Sin `sesion=` el comportamiento DEBE ser idéntico al anterior (golden master sin diferencias).
- **FR-007**: `turn_slot` se mantiene (colaboradores compartidos con temporales del turno, ver `research.md`).

### Key Entities

- **EstadoConversacion** (`src/chatbot/estado_conversacion.py`): id, memoria, seguimiento, pendientes,
  intención, tableros candidatos; transitorios `ultimo_razonamiento` y `candado`.
- **_Turno** (`src/chatbot/sesion_motor.py`): datos del turno en curso, en un ContextVar.

## Success Criteria *(mandatory)*

- **SC-001**: Las 5 situaciones del pedido (seguimientos intercalados, contrapregunta ajena, reinicio, JSON,
  hilos) tienen prueba y pasan.
- **SC-002**: Suites de contexto, conversación, aclaración, enrutamiento, portero y estabilidad, y el golden
  master, sin cambios de comportamiento.
- **SC-003**: Doctor `--verificar` sin bajar el puntaje.

# Feature Specification: API del asistente (FastAPI + Redis)

**Feature Branch**: `agente/backend-api` (carpeta `specs/006-api-backend`)

**Created**: 2026-11-10

**Status**: Implementada (v1)

**Input**: «Abandonar Streamlit y construir con FastAPI (backend) + Next.js (frontend) + Redis, porque lo usará todo
el hospital (varias dependencias, todo el día, muchas peticiones simultáneas). `app.py` es la especificación
funcional: todo lo que hace debe quedar disponible por la API.»

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preguntar y ver la respuesta en vivo (Priority: P1)

Una persona del hospital abre el chat (Next.js), escribe una pregunta sobre un tablero y ve en vivo en qué va el
asistente (etapas con frases amables, su posición si hay fila) hasta que llega la respuesta en Markdown, con las
fuentes, el botón «Abrir en Power BI» y, si aplica, una contrapregunta con opciones.

**Why this priority**: es el uso principal; sin esto no hay producto.

**Independent Test**: `POST /conversaciones` → `POST /conversaciones/{id}/turnos` → `GET /turnos/{id}/eventos`
(SSE) con el motor simulado; llegan `progreso`… `respuesta` y `fin`.

**Acceptance Scenarios**:

1. **Given** una conversación nueva, **When** envío «hola», **Then** recibo `202 {turno_id}` y por SSE
   `progreso` (entendiendo), `respuesta` (ruta `conversacion`) y `fin`.
2. **Given** una pregunta ambigua, **When** el motor pide aclarar, **Then** la `respuesta` trae
   `contrapregunta {pregunta, opciones[{id, texto, descripcion?}]}`; **When** envío un turno con `opcion_id`,
   **Then** el motor aplica esa opción (como el botón de Streamlit).
3. **Given** que el SSE se corta, **When** reconecto con `Last-Event-ID`, **Then** recibo solo los eventos
   posteriores; **Given** que el turno ya terminó y sus eventos expiraron, **Then** recibo `respuesta` y `fin`
   reconstruidos del estado final.
4. **Given** que el motor falla, **Then** recibo `error {mensaje amable, codigo}` y `fin`, sin detalles internos.

### User Story 2 - Muchas personas a la vez sin romper el motor (Priority: P1)

Decenas de personas preguntan al mismo tiempo. Las peticiones HTTP no se bloquean; los turnos esperan en una fila
justa (FIFO) y cada uno ve su posición; el motor (Qdrant local, MiniLM, ADOMD, MedGemma) vive en un único proceso
que lo protege.

**Independent Test**: varias conversaciones encoladas contra un trabajador con una sola instancia del motor: cada
turno recibe `cola {posicion, en_curso}` mientras espera y todos terminan; el estado de una conversación nunca se
mezcla con el de otra.

**Acceptance Scenarios**:

1. **Given** dos conversaciones A y B, **When** A deja una contrapregunta pendiente y B pregunta otra cosa,
   **Then** la siguiente respuesta de A aplica su opción y B no ve el contexto de A.
2. **Given** un turno en curso en una conversación, **When** envío otro en la misma, **Then** `409 turno_en_curso`.
3. **Given** que un cliente envía demasiados turnos en un minuto, **Then** `429` con mensaje amable y `Retry-After`.
4. **Given** la fila llena, **Then** `503 servicio_ocupado` amable.

### User Story 3 - Respuestas repetidas al instante (Priority: P2)

Si alguien pregunta lo mismo que otra persona hace poco (misma pregunta normalizada, mismos datos/catálogo, mismo
día), la respuesta sale de la caché sin tocar Power BI ni MedGemma.

**Acceptance Scenarios**:

1. **Given** una respuesta exitosa a una pregunta autónoma, **When** otra conversación nueva hace la misma pregunta
   (con otras mayúsculas, tildes o abreviaturas de chat), **Then** responde desde caché (`diagnostico.cacheada`).
2. **Given** un seguimiento («¿y en 2025?»), una opción de contrapregunta, una respuesta degradada (resumen
   extractivo) o un error, **Then** nunca se guarda ni se lee de la caché.
3. **Given** que cambia el catálogo, el índice o el código, o cambia el día, **Then** la caché anterior no se usa.

### User Story 4 - Historial, exportación, calificación, capacidades, salud y diagnóstico (Priority: P2)

Todo lo demás de `app.py`: ver el historial de la conversación, exportarlo a Markdown (con o sin razonamiento),
calificar una respuesta (buena/mala con qué se esperaba, mismo registro `src/feedback`), mostrar en el estado vacío
qué tableros se pueden consultar y ejemplos, ver la salud (Redis, motor, MedGemma, Power BI, índice) y el panel de
diagnóstico del servidor.

### Edge Cases

- Sin `REDIS_URL` (o Redis caído al arrancar): modo memoria de un solo proceso con advertencia en el log.
- Opción de contrapregunta que ya no está vigente: `409 opcion_no_vigente`.
- Mensaje vacío sin opción, o demasiado largo: `422` amable.
- Trabajador caído a mitad de turno: al reiniciar, los turnos huérfanos se cierran con `error interrumpido`.
- Turno inexistente o expirado: `404`.
- Estado de conversación manipulado en Redis: la firma HMAC falla y la conversación sigue sin contexto.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: La API expone el contrato v1 de `contracts/api-v1.md` (OpenAPI en `/api/v1/openapi.json`).
- **FR-002**: Los turnos se encolan y se procesan fuera del ciclo de eventos, en el proceso dueño del motor.
- **FR-003**: Los eventos de cada turno viajan por Redis (Streams) y el SSE los lee aunque la API tenga varios
  procesos; admite `Last-Event-ID` y reenvío del estado final.
- **FR-004**: El estado de conversación del motor (contrapreguntas pendientes, último dato para seguimientos,
  memoria) se guarda por conversación (Redis con TTL o memoria) y se restaura antes de cada turno.
- **FR-005**: Caché de respuestas por pregunta normalizada + huella de datos/catálogo/código + fecha, con TTL; nunca
  para turnos con contexto, opciones, respuestas degradadas o con error.
- **FR-006**: Límite de peticiones por cliente (identificador de sesión del navegador o IP), ventana deslizante, 429.
- **FR-007**: Errores siempre como `{mensaje, codigo}` en español amable; nunca trazas ni detalles internos.
- **FR-008**: `diagnostico` (trazas, tiempos, DAX, plan, caché) solo cuando el turno lo pide.
- **FR-009**: Sin Redis: todo funciona en un proceso, en memoria, con advertencia.
- **FR-010**: Reutiliza `src/feedback`, `conversation_export`, `powerbi_links`, `progreso`, `runtime_stats` y la
  puerta del LLM sin reimplementarlos.
- **FR-011**: CORS para el frontend en desarrollo (`http://localhost:3000`).
- **FR-012**: No lee `.env` por su cuenta (solo variables de entorno); no expone secretos.

### Key Entities

- **Conversación**: id, creada/actualizada, mensajes, turno activo, opciones pendientes, frases recientes,
  estado del motor (firmado).
- **Turno**: id, conversación, mensaje u opción, diagnóstico, estado (`en_cola`, `procesando`, `terminado`,
  `error`), tiempos, respuesta final, snapshot saneado para calificar.
- **Evento**: `cola`, `progreso`, `espera`, `aviso`, `respuesta`, `error`, `fin`.

## Success Criteria *(mandatory)*

- **SC-001**: Las pruebas de `tests/backend` pasan con `fakeredis` y con memoria (SSE incluido), sin red.
- **SC-002**: Un «hola» repetido o una pregunta cacheada responde en < 1 s una vez en el trabajador.
- **SC-003**: Ningún endpoint bloquea el ciclo de eventos con trabajo del motor.
- **SC-004**: El frontend puede construirse solo con `contracts/api-v1.md`.

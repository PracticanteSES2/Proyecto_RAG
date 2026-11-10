# Feature Specification: Concurrencia con MedGemma (diagnóstico, medición y cola justa)

**Feature Branch**: `agente/carga`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Con más de 3 respuestas simultáneas el servidor de MedGemma se satura. Temo que
con 10 personas a la vez el bot falle, responda peor, solo dé el resumen de respaldo, MedGemma ni lo intente o
corte respuestas a la mitad. Quiero un diagnóstico con evidencia, una herramienta para medir la carga (simulada
y, con permiso, real), una cola justa con posición consultable para que la UI muestre «hay N consultas antes
que la tuya» y un documento con las opciones y la decisión que me toca."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Saber qué pasa hoy con N usuarios simultáneos (Priority: P1)

El propietario quiere saber, con evidencia del código (archivo:línea), qué ocurre cuando 10 personas
preguntan a la vez: cuántas llamadas al LLM hace un turno, dónde se espera, qué se degrada y qué puede
cortarse.

**Why this priority**: sin diagnóstico cualquier cambio (Redis, más GPU, ajustes de Ollama) es a ciegas.

**Independent Test**: `docs/arquitectura/concurrencia.md` responde cada temor con «¿puede pasar?» y
«¿ya está contemplado?» citando el código.

**Acceptance Scenarios**:

1. **Given** el código de `desarrollo`, **When** se lee el documento, **Then** cada temor (falla, peor
   respuesta, solo respaldo, MedGemma no lo intenta, corte a la mitad) tiene respuesta y evidencia.

---

### User Story 2 - Medir la carga con una herramienta repetible (Priority: P1)

El propietario corre `python -m tools.carga` con rampas 1, 3, 5, 10 y 20 usuarios, en modo solo-LLM y
extremo a extremo, y obtiene p50/p95, tiempo al primer token, tasas de saturación/tiempo agotado/error,
respuestas truncadas y throughput, en tabla y JSON. Sin `--real` usa un servidor simulado configurable;
con `--real` avisa y pide confirmación antes de tocar el servidor del hospital.

**Why this priority**: es la única forma de convertir el temor en números y de comparar opciones.

**Independent Test**: `python -m unittest tests.perf.test_carga` corre la herramienta con el proveedor
falso y comprueba métricas y archivos de salida.

**Acceptance Scenarios**:

1. **Given** el proveedor falso con capacidad 3, **When** se corre la rampa 1,3,5,10,20, **Then** la tabla
   muestra latencias crecientes y saturación solo por encima de la capacidad.
2. **Given** `--real` sin confirmación escrita, **When** se ejecuta, **Then** no se hace ninguna llamada.

---

### User Story 3 - Cola justa con posición consultable (Priority: P2)

Cuando hay espera (por el turno o por un hueco de MedGemma), quien llega primero entra primero y la UI
puede preguntar en qué posición está la consulta actual para mostrar «hay N consultas antes que la tuya».

**Why this priority**: la espera ya existe (un turno a la vez); hoy no es FIFO ni se ve cuánto falta.

**Independent Test**: pruebas de `tests/perf/test_cola_justa.py` (orden FIFO, posición, espera larga
con progreso, contrato de `call_llm`).

**Acceptance Scenarios**:

1. **Given** 3 llamadas en curso y 2 en espera, **When** se libera un hueco, **Then** entra la primera en
   llegar y la otra pasa a la posición 1.
2. **Given** la UI envuelve el turno con `ui_progress(...)`, **When** la síntesis espera hueco, **Then**
   espera hasta `MEDGEMMA_QUEUE_WAIT_UI` s, recibe la posición en un callback y la espera no le resta
   presupuesto a la generación.
3. **Given** cualquier caso, **When** se llama a `call_llm`, **Then** nunca lanza y devuelve los mismos
   status que antes.

### Edge Cases

- Una llamada en espera se rinde (tiempo de espera agotado): sale de la fila y las de detrás avanzan.
- Una llamada abandonada (proveedor sin tiempo límite propio) sigue ocupando su hueco hasta terminar.
- Alguien toma `TURN_LOCK` directamente (pruebas antiguas): la fila de turnos lo respeta (sondeo).
- El callback de progreso lanza: se ignora y la llamada sigue.
- `MEDGEMMA_MAX_CONCURRENT` cambia en caliente: la capacidad se lee en cada llamada.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `call_llm` MUST atender las esperas en orden de llegada (FIFO) y conservar su contrato
  (nunca lanza; status `success`/`empty_response`/`llm_timeout`/`llm_saturated`/`llm_error`/los del proveedor).
- **FR-002**: El sistema MUST exponer, sin renombrar campos existentes, una instantánea con llamadas en
  curso, en espera, capacidad y la posición en fila de la llamada (o turno) del hilo actual.
- **FR-003**: `turn_slot` MUST ser FIFO y conservar su firma, `on_wait(waited, since)`, `TurnBusy` y la
  liberación en `finally`.
- **FR-004**: Debe existir un modo «con progreso» (`ui_progress`) con espera configurable
  (`MEDGEMMA_QUEUE_WAIT_UI`, 30 s) que solo afecta a las llamadas sin `queue_wait` explícito.
- **FR-005**: `tools/carga` MUST simular N usuarios (rampas) en modo `llm` y `e2e`, con proveedor falso
  configurable (capacidad, cola máxima, latencia, degradación por concurrencia, truncado) y modo `--real`
  que avisa y exige escribir la confirmación.
- **FR-006**: La herramienta MUST reportar p50/p95, primer token, tasas de `llm_saturated`, tiempo agotado,
  error, truncadas y throughput, en tabla y JSON en una carpeta ignorada por git.
- **FR-007**: `MedGemmaProvider` MUST informar `done_reason` (additivo) para detectar respuestas cortadas
  por `num_predict`.

- **FR-008** (cambio de rumbo 2026-11-10: API FastAPI + workers + Redis): la puerta MUST tener backend
  enchufable `memoria` | `redis` (`LLM_GATE_BACKEND`, `REDIS_URL`): semáforo justo entre procesos con
  tickets FIFO, préstamos con TTL y posición consultable; sin Redis, cae a memoria con advertencia.
- **FR-009**: MUST exponer `evento_cola()` (SSE `cola` {posicion, en_curso}) y `STATS.llm_pressure()`.

### Key Entities

- **Fila justa (FifoLine)**: tickets en orden de llegada con hilo y dueño; posición 1 = la siguiente.
- **Instantánea de cola**: `{capacity, in_flight, waiting, position, ahead}` para turnos y para MedGemma.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Con el proveedor falso, el orden de entrada de 6 llamadas en espera coincide con el de llegada.
- **SC-002**: Todas las pruebas existentes de la puerta (`tests/stability`) y las nuevas de `tests/perf` pasan.
- **SC-003**: La herramienta corre la rampa completa simulada en menos de 1 minuto con `--escala` pequeña.
- **SC-004**: El documento ordena las opciones por costo/beneficio y deja explícitas las decisiones del usuario.

## Assumptions

- La app sigue siendo un único proceso Streamlit; no se ejecuta nada contra el MedGemma real ni Power BI
  real sin permiso explícito del usuario.
- La UI (otro agente) consume la API; `app.py` y `src/ui/` no se tocan aquí.
- El modo e2e usa el motor del simulador (`tests/sim`: Power BI y Qdrant de fixtures) incluso con `--real`
  (solo el LLM es real), para no cargar Power BI.

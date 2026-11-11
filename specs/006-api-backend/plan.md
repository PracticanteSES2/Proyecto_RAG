# Implementation Plan: API del asistente (FastAPI + Redis)

**Branch**: `agente/backend-api` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md) |
**Contrato**: [contracts/api-v1.md](contracts/api-v1.md)

## Summary

`backend/` con FastAPI (API asíncrona, sin estado) + un **proceso trabajador** dueño del motor
(`python -m backend.worker`), coordinados por Redis (Streams, hashes, ZSET). Sin `REDIS_URL`, todo corre en un solo
proceso en memoria (el trabajador va en un hilo de la API). El motor se importa de `src/` tal cual.

## Hallazgos de concurrencia del motor (verificados en el código)

| Recurso | Hallazgo | Consecuencia |
|---|---|---|
| Qdrant local (`HybridRetriever`, `QdrantClient(path=…)`) | candado de archivo: un solo proceso (y un solo cliente por carpeta) puede abrirlo | el índice vive en **un** proceso: el trabajador |
| MiniLM (`SentenceTransformer`) | en memoria, ~cientos de MB, carga lenta | se carga una vez, en el trabajador; compartido entre instancias |
| ADOMD (pythonnet, `PowerBIProvider`) | CLR por proceso; conexiones con estado; `query_listener`/`activity_listener` son atributos del proveedor que el motor cambia por turno | un proveedor por instancia del motor, nunca compartido entre turnos simultáneos |
| `QueryEngine` | **no es seguro entre hilos**: guarda estado por turno y por conversación en atributos (`_trace`, `progress_listener`, `_pending_query_plan`, `_pending_master_metric`, `_pending_dashboard_clarification`, `_deferred_context_message`, `_applying_deferred`, `_last_success`, `_range_choice`, `_turn_interpretation`, `_intent_llm_turn`, `_turn_message`, `conversation_memory`) y `ConversationManager` (`state`, `candidate_dashboards`) | una instancia atiende **un turno a la vez**; el estado de conversación se **saca y se restaura** por turno |
| `runtime_stats.STATS`, `llm_gate` | globales del proceso, con candados | se comparten sin problema; la puerta del LLM limita MedGemma en todo el proceso (o en Redis con `LLM_GATE_BACKEND=redis`, agente/carga) |
| `turn_slot` (candado «un turno a la vez») | global del proceso, pensado para Streamlit | el backend no lo usa: lo reemplaza la piscina de instancias |

## Arquitectura

```text
Navegador (Next.js) ──HTTP/SSE──► API FastAPI (uvicorn, 1..N procesos, async, sin estado)
                                   │  POST turno: límite (ZSET) → candado de conversación (SET NX)
                                   │             → XADD rag:cola:turnos + ZADD rag:cola:espera + HSET rag:turno:{id}
                                   │  GET eventos (SSE): XREAD BLOCK rag:turno:{id}:eventos (+ `cola` calculada)
                                   ▼
                                 Redis
                                   ▲
                                   │  XREADGROUP (grupo «motores») solo cuando hay una instancia libre
Trabajador (1 proceso: python -m backend.worker)
   Piscina de MOTOR_INSTANCIAS motores (por defecto 1), cada uno en su hilo:
     caché → restaurar estado de la conversación → engine.process / select_clarification_option
     → eventos (progreso/espera/cola/aviso vía src/chatbot/progreso.py) → XADD → respuesta/fin
     → guardar estado firmado + historial + snapshot → XACK
   Latido (cada 5 s): salud, diagnóstico del servidor (STATS), capacidades, huella de datos.
```

**Por qué un proceso trabajador y no hilos dentro de la API**: Qdrant local no admite dos procesos, así que con
uvicorn `--workers N` cada proceso intentaría abrirlo; además la CLR/ADOMD y MiniLM son pesados y deben cargarse una
vez. Separar el trabajador deja a la API escalar libremente (y reiniciarse sin recargar el motor), y la cola en
Redis da posición justa (FIFO) y supervivencia a reinicios (turnos huérfanos → `error interrumpido`).

**Por qué no varios trabajadores**: el mismo candado de Qdrant. Para escalar más allá de una máquina/proceso hay que
pasar Qdrant a modo servidor (fase posterior). Dentro del proceso, `MOTOR_INSTANCIAS>1` crea motores completos que
comparten el retriever (protegido con un candado: la búsqueda tarda milisegundos) y tienen cada uno su proveedor de
Power BI y su estado; queda desactivado por defecto hasta validarlo con `tools/carga` (agente/carga).

## Redis: claves y estructuras (prefijo `REDIS_PREFIJO`, por defecto `rag`)

| Clave | Tipo | Contenido | TTL |
|---|---|---|---|
| `rag:cola:turnos` | Stream + grupo `motores` | `{turno_id}` | recortado (MAXLEN ~10000) |
| `rag:cola:espera` | ZSET | turno_id → número de llegada (`INCR rag:cola:llegadas`; posición = ZRANK+1) | — (se limpia al tomar) |
| `rag:cola:en_curso` | ZSET | turno_id → ms de inicio | — (se limpia al terminar; huérfanos > `TURNO_MAX_S`) |
| `rag:turno:{id}` | HASH | conversación, mensaje/opción, diagnóstico, estado, tiempos, respuesta (JSON), snapshot (JSON), calificación | `TURNO_TTL_S` (24 h) |
| `rag:turno:{id}:eventos` | Stream | `{evento, datos}`; el id del stream es el `id:` del SSE | `EVENTOS_TTL_S` (1 h tras `fin`) |
| `rag:conv:{id}` | HASH | creada, actualizada, opciones pendientes, frases recientes | `CONVERSACION_TTL_S` (24 h, se renueva) |
| `rag:conv:{id}:mensajes` | LIST | mensajes JSON (usuario/asistente) | ídem |
| `rag:conv:{id}:motor` | STRING | estado del motor: pickle **firmado con HMAC-SHA256** (`BACKEND_SECRETO`) | ídem |
| `rag:conv:{id}:activo` | STRING (SET NX) | turno en curso de la conversación | `TURNO_MAX_S` |
| `rag:cache:{sha256}` | STRING | respuesta + snapshot + estado del motor posterior | `CACHE_TTL_S` (15 min) |
| `rag:limite:{cliente}` | ZSET | marcas de tiempo (ventana deslizante) | ventana |
| `rag:motor:latido` / `:diagnostico` / `:capacidades` | STRING JSON | salud del trabajador, STATS, tableros y ejemplos | 15 s / 30 s / 1 día |

Clave de caché = sha256(huella | fecha local | pregunta normalizada con `normalize_question` + `fold`). Huella =
sha256 de la versión del código (git HEAD) y de tamaño+mtime de `data/catalog`, `data/rag`, `data/model_metadata` y
`data/vector_db` (se recalcula cada 60 s). Solo se lee y se guarda cuando la conversación no tiene contexto (sin
memoria, sin pendiente, sin opción) y la respuesta es `success` de `powerbi` o `rag` no extractiva.

## Technical Context

**Language/Version**: Python 3.14 (`.venv`) · **Dependencies**: fastapi, uvicorn[standard], pydantic-settings,
redis (+ fakeredis, pytest, httpx en desarrollo) · **Storage**: Redis 6.2+ (Streams, XAUTOCLAIM) o memoria ·
**Testing**: pytest (`tests/backend`), fakeredis, TestClient/httpx (SSE) · **Constraints**: sin `.env` propio, sin
MedGemma ni Power BI reales en pruebas, no tocar `app.py`, `src/llm`, `runtime_stats.py`, `src/chatbot/portero*`,
`frontend/`.

## Constitution Check

| Compuerta | Estado |
|---|---|
| Power BI / BD solo lectura | ✅ el backend no consulta nada por su cuenta; el motor sigue igual |
| Sin datos de pacientes en logs | ✅ calificación con el snapshot saneado de `src/feedback`; errores sin detalles |
| `.env` intocado | ✅ `config.py` solo lee variables de entorno |
| spec-kit + TDD | ✅ |
| Archivos de otros agentes intocados | ✅ (`progreso.py` llega por cherry-pick de agente/ui-progreso) |

## Project Structure

```text
backend/
  worker.py                       python -m backend.worker (proceso dueño del motor, con Redis)
  app/main.py                     create_app(): routers, CORS, errores, ciclo de vida (motor embebido sin Redis)
  app/core/                       config.py (pydantic-settings, solo entorno) · errores.py · registro.py · dependencias.py
  app/api/v1/                     conversaciones.py · turnos.py · sistema.py (routers delgados, sin src.*)
  app/schemas/                    comunes.py · conversaciones.py · turnos.py · sistema.py (contrato OpenAPI)
  app/services/
    almacen.py                    interfaces AlmacenAPI (async) / AlmacenTrabajador (sync)
    almacen_memoria.py            ambos lados en un proceso (modo por defecto sin Redis)
    almacen_redis.py              AlmacenRedis (redis.asyncio) + AlmacenTrabajadorRedis (redis)
    claves.py                     nombres de claves Redis
    motor.py                      fachada del motor: piscina, candado del retriever, SesionPorAtributos, firma HMAC
    presentacion.py               result → payload `respuesta` (puerto de get_display_answer)
    cache.py                      clave, huella, reglas
    progreso.py                   TraductorProgreso + llm_gate.ui_progress + `token`
    turnos.py                     ProcesadorTurnos
    trabajador.py                 Trabajador (cola, hilos, latido, huérfanos)
    capacidades.py                capacidades, latido, diagnóstico del servidor
    conversaciones.py · eventos.py · estado.py · limites.py · sistema.py   (lado API y arranque)
src/chatbot/fabrica.py            cableado ÚNICO del motor (lo usan app.py y el backend)
infra/scripts/iniciar_backend.ps1 · infra/docker/docker-compose.referencia.yml (no probado)
docs/backend.md
tests/backend/ (servicios, trabajador, motor real simulado) · tests/api/ (HTTP + SSE)
```

## Puntos de unión con otros agentes

- **agente/memoria-sesion**: el estado por conversación pasa por `SesionPorAtributos` (`services/motor.py`):
  `ejecutar(instancia, estado, texto, opcion, on_token)` → `(result, estado_nuevo)` y `sin_contexto(estado)`.
  Cuando el motor acepte `process(pregunta, sesion=…)`, un adaptador con la misma forma lo reemplaza; almacén,
  caché y turnos no cambian (el estado se guarda firmado; si su objeto no es pickle-able, cambia solo el
  serializador).
- **agente/ux-espera**: `token` {texto} se publica desde el hilo del motor directamente en el almacén (seguro entre
  hilos; el SSE lo reenvía como cualquier evento, sin `call_soon_threadsafe` porque el motor no corre en el ciclo
  de eventos de la API); `on_token` se pasa al motor solo si su firma lo acepta. `cola` queda para diagnóstico.
- **agente/carga**: `llm_gate.ui_progress(on_queue=…)` alrededor de cada turno; `STATS.llm_pressure()` en el
  diagnóstico.
- **agente/rendimiento-llm**: el código Redis del backend vive en `backend/app/services`, nunca en `src/`.

## Complexity Tracking

| Decisión | Por qué no algo más simple |
|---|---|
| Proceso trabajador aparte | Qdrant local + CLR impiden varios procesos con motor; la API debe escalar |
| Estado del motor serializado (pickle firmado) | el motor guarda objetos (`ConversationMemory`, `ConversationState`) no JSON; la firma evita ejecutar un pickle manipulado |
| Dos implementaciones de almacén | Redis para producción; memoria para desarrollo/pruebas sin servicios |

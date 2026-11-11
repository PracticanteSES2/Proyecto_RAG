# Implementation Plan: Rendimiento con MedGemma

**Branch**: `agente/rendimiento-llm` · **Spec**: `spec.md`

## Resumen técnico

La generación domina el costo (≈ 20 tokens/s por petición sola; la evaluación del prompt es ~50-100 veces
más rápida por token). Por eso lo que sube el techo de respuestas redactadas por minuto es **no generar**:
caché de la respuesta cruda del LLM, peticiones idénticas agrupadas, opciones descritas sin LLM cuando el
catálogo basta y, opcional, el extracto como respuesta. Recortar el prompt casi no mueve el techo (se mide
y se deja como está para no arriesgar la calidad). `num_predict` es de `agente/truncado`.

## Diseño

| Pieza | Dónde | Capa |
|---|---|---|
| Contadores de costo (`llm_payload`, `llm_usage`, `llm_call_avoided`, `llm_cache_event`) | `src/chatbot/runtime_stats.py` + `src/llm/llm_gate.py` | aplicación (deuda conocida: la puerta importa runtime_stats) |
| Caché de llamadas (`AlmacenCache` Protocol, `AlmacenMemoria` LRU+TTL, `clave`, `llamar_con_cache`) | `src/chatbot/cache_llm.py` | aplicación (usa `question_normalizer`) |
| Clave de pregunta compartida motor/API | `src/semantic/question_normalizer.clave_pregunta` | dominio |
| Síntesis RAG con caché | `answer_synthesizer.synthesize_rag` (un solo bloque) | aplicación |
| Opciones: caché por opción + catálogo suficiente | `option_describer` | aplicación |
| Extracto directo (opcional, `RAG_EXTRACTO_DIRECTO=on`) | `rag_answer_engine._direct_extract` | aplicación |
| Almacén Redis de la caché | `backend/app/services/cache_llm_redis.py` | backend_servicios |
| Semáforo Redis de la puerta (movido) | `backend/app/services/puerta_llm_redis.py` + `llm_gate.registrar_backend` | backend_servicios |
| Cableado al arrancar | `backend/app/services/sistema.py` (`_instalar_redis_del_motor`, `fijar_version`) | backend_servicios |
| Medición | `tools/carga/componentes.py`, `metricas.resumen_costo`, columnas nuevas | tools |
| Motor e2e del simulador | `tools/manual/carga_e2e.py` (exento), inyectado con `fabrica_motor` | tools/manual |

## Riesgos y mitigación

- **Respuesta equivocada servida de caché**: la clave incluye la huella exacta del contexto, del prompt
  (sistema, tarea, conversación), del modelo y `max_tokens`; el post-proceso corre siempre. Proveedores sin
  `model` (dobles de prueba) solo comparten caché consigo mismos.
- **Respuestas degradadas pegadas**: nunca se guardan (saturadas, tiempo agotado, vacías, truncadas, «sin
  evidencia», descripciones rechazadas).
- **Coordinación con otros agentes**: cambios localizados (un bloque en `synthesize_rag`, dos líneas y un
  campo en `MedGemmaProvider`); `num_predict` intacto.

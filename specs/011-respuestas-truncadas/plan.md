# Implementation Plan: Respuestas completas

**Branch**: `agente/truncado` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

## Inventario de llamadas al LLM (antes del cambio)

Ningún cliente envía `num_ctx` (`src/llm/medgemma_provider.py:189-192`): rige el del servidor y, si el prompt
no cabe, Ollama recorta la entrada en silencio (`docs/arquitectura/concurrencia.md:62`).

| Propósito | Dónde | `num_predict` | Qué pasaba al truncarse |
| --- | --- | --- | --- |
| Síntesis RAG | `src/chatbot/answer_synthesizer.py:249` (default), `:485` | 600 | Se ignoraba `truncated` (`:489-527`): la respuesta cortada a mitad de frase/tabla/lista llegaba al usuario como éxito |
| Síntesis Power BI | `answer_synthesizer.py:744` | 350 | Ruta no conectada («segunda fase», `:698`) |
| Descripción de opciones | `src/chatbot/option_describer.py:242` | 60 | `parse` toma la primera frase (`:214`); un fragmento sin punto se mostraba como descripción |
| Reescritura contextual | `src/chatbot/contextual_rewriter.py:308` | 80 | `clean` toma la primera línea (`:316`); una pregunta a medias podía pasar `validate` |
| Intención LLM | `src/semantic/intencion_llm.py:84`, `:883` | 160 (JSON) | JSON cortado → «invalid» → un reintento (`:900`) → reglas |
| Documentación viva | `src/docs_md/actualizador.py:87,90,606` | 1500 / 40 (JSON) | JSON cortado → problemas → reintento con corrección (`:1299`); offline, fuera del chat |
| Calentamiento | `medgemma_provider.py:281` | 8 | Irrelevante («OK») |
| `OllamaProvider` | `src/llm/ollama_provider.py:131-134`, `:164-167` | 5 / 220 (`num_ctx` 2048/4096) | Sin uso en producción (solo `tools/manual`) |

## Valores elegidos (configurables por entorno)

Supuesto de la simulación de carga: ~20 tokens/s por petición sola (`concurrencia.md:101`); la síntesis tiene
40 s (`RAG_SYNTHESIS_TIMEOUT`). Español con el tokenizador de Gemma ≈ 1,5 tokens/palabra + ~15 % de Markdown.

| Variable | Valor | Justificación |
| --- | --- | --- |
| `LLM_NUM_PREDICT_SINTESIS` | 600 | 600 tok ≈ 30 s a 20 tok/s: subirlo rompe los 40 s con carga. Se pide ≤ 250 palabras (≈ 430 tok) → ~170 tok de holgura |
| `LLM_NUM_PREDICT_CONTINUACION` | 200 | ≈ 10 s; basta para cerrar 1-3 frases o ítems (≤ 80 palabras) |
| `LLM_NUM_PREDICT_OPCIONES` | 60 | La frase pedida es ≤ 15 palabras (≈ 25 tok): margen ×2 |
| `LLM_NUM_PREDICT_REESCRITURA` | 80 | Una pregunta ≤ 30 palabras (≈ 45 tok) |
| `LLM_NUM_PREDICT_INTENCION` | 160 | JSON compacto del esquema de intención (README del motor) |
| `LLM_NUM_PREDICT_POWERBI` | 350 | Sin cambios (ruta no conectada) |
| `MEDGEMMA_NUM_CTX` | 4096 | Contexto del servidor (no se envía: cambiarlo por petición recarga el modelo). Poner el real |
| `LLM_CARACTERES_POR_TOKEN` | 3.3 | Conservador: la síntesis medida da ~3,6 caracteres/token (2.400-2.800 tok para ~9.500 caracteres) |
| `RAG_CONTINUAR_TRUNCADA` | 1 | 0 desactiva la continuación |

Margen fijo de 64 tokens (plantilla de chat). Entrada máxima = `num_ctx - num_predict - 64`.

## Diseño

- `src/comun/entorno.py`: `env_int`/`env_float` (destino de fase 3; `runtime_stats` los reexporta) para que
  `src/llm` no importe `src.chatbot`.
- `src/llm/presupuesto_tokens.py`: `num_predict(proposito)`, `num_ctx()`, `estimar_tokens`, `tokens_mensajes`,
  `entrada_maxima`, `palabras_objetivo`, `ajustar_a_contexto(construir, n_fuentes, salida)`.
- `src/chatbot/respuesta_completa.py`: `cortar_en_limite_seguro`, `unir_continuacion`, `decidir_continuacion`
  (tiempo + `STATS.llm_pressure()`), `completar(...)` (orquesta corte/continuación), `linea_aviso(enlace)`,
  `describir(diagnostico)`.
- `AnswerSynthesizer.synthesize_rag`: TAREA con extensión objetivo; `ajustar_a_contexto`; `completar` antes de
  limpiar/anclar; devuelve `diagnostico`, `incompleta`, `cacheable`. Si no queda contenido → `llm_truncated`
  (resumen extractivo).
- `RAGAnswerEngine`: añade la línea de aviso (con `enlace_para_resultado`) DESPUÉS del anclaje de cifras (la URL
  no pasa por `ground_answer`), y `synthesis_detail` + `respuesta_llm` en el resultado; `query_engine` muestra
  `synthesis_detail` en el paso «Búsqueda en la documentación (RAG)» (misma línea, sin crecer).
- `MedGemmaProvider.chat`: añade `prompt_eval_count` (aditivo) para calibrar la estimación.

## Coordinación

- `agente/ux-espera` (streaming `on_token`): el borrador es provisional; la final reparada lo reemplaza.
- `agente/rendimiento-llm` (prompts, contexto, caché): no guardar en caché si `cacheable` es False; el recorte
  de contexto de esa rama sigue mandando, aquí solo se garantiza no pasar de `num_ctx`.
- `agente/memoria-sesion`: sin cambios en el estado de conversación; en `query_engine` solo una línea.

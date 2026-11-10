# Implementation Plan: Experiencia de espera

**Branch**: `agente/ux-espera` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md) |
**Contrato**: [../003-progreso-chat/contracts/eventos.md](../003-progreso-chat/contracts/eventos.md)

## Summary

1. **Textos** (`src/chatbot/progreso.py`): sin etapa `en_cola`; «LLM en cola» y `esperando_turno()` mantienen la
   etapa de trabajo; `SEGUIMIENTO` por etapa + `tic()` que rota la frase cada `ROTACION_S` (8 s); esperas largas
   sin carga ni otros; aviso de degradación neutro; `evento_token`/`TraductorProgreso.token()`.
2. **Streaming de la síntesis** de punta a punta:
   `MedGemmaProvider.chat(stream=True, on_token=cb)` → `llm_gate.call_llm(..., on_token=cb)` →
   `AnswerSynthesizer.synthesize_rag(..., on_token=cb)` → `RAGAnswerEngine.answer(..., on_token=cb)`, con
   `src/chatbot/respuesta_en_vivo.py` (`escuchar_tokens`, `oyente_tokens`, `FiltroBorrador`).
3. **Streamlit**: solo textos de espera y de `TurnBusy`.
4. **Frontend**: cuando `frontend/` llegue a `desarrollo` (ver tasks.md, fase 6).

## Decisiones

| Tema | Decisión | Por qué |
|---|---|---|
| Espera de hueco/turno | No cambia la etapa visible; solo `cola` (diagnóstico) | El usuario ve trabajo sobre SU pregunta, nunca a otros |
| Rotación | `progreso` con la misma etapa y la siguiente frase de `SEGUIMIENTO[etapa]` cada 8 s; en orden de avance, cíclico sin repetir la actual | Nunca se ve congelado; lenta para no parecer un carrusel |
| Esperas largas | Umbrales 10/25/50/90 s iguales; textos sin carga | Mismo ritmo, mensaje distinto |
| Carga del LLM | `leer_carga_llm` se conserva (gancho/diagnóstico) pero ya no decide textos; `TraductorProgreso` deja de recibir `carga` | El texto no depende de otros |
| Degradación | `aviso` con texto neutro único; `motivo` solo para diagnóstico | Honesto sin culpar a la carga |
| Paso de `on_token` al motor | `escuchar_tokens(cb)` (ContextVar, como `llm_gate.ui_progress`) leído por `RAGAnswerEngine` | No toca `query_engine` (lo edita `agente/memoria-sesion`); explícito por parámetro en las capas de síntesis |
| Streaming en el proveedor | `client.chat(stream=True)` de Ollama; se acumula el texto y se devuelve el MISMO dict que sin streaming | El contrato de `call_llm` no cambia |
| Tiempo límite en streaming | Plazo total comprobado tras cada fragmento (cierra el generador → cierra la conexión → Ollama deja de generar) + el tiempo límite HTTP por lectura del cliente | httpx solo limita cada lectura; el plazo total sigue siendo real |
| Callback que lanza | Se ignora (proveedor y puerta) | La vista en vivo nunca tumba la llamada |
| Llamada abandonada (proveedor sin tiempo límite propio) | La puerta deja de reenviar tokens al vencer | Nada llega después del `llm_timeout` |
| Post-proceso | Se aplica igual al texto completo; la respuesta final validada (`respuesta`) REEMPLAZA al borrador | Salvaguarda de cifras, limpieza y truncado siguen siendo la única verdad |
| Lo que el post-proceso quita al inicio | `FiltroBorrador` retiene el comienzo mientras pueda ser la frase de «sin evidencia» o una muletilla («Claro, …») y la quita antes de transmitir | El borrador no muestra algo que luego desaparece arriba (el salto más visible) |
| Reemplazo en el frontend | Si la final empieza por el borrador (espacios normalizados): se sigue escribiendo desde ahí, sin salto. Si no: fundido cruzado ~150 ms con alto mínimo fijado | Sin saltos de layout; cambios de la salvaguarda se ven suaves |
| Power BI | Sin LLM: llega completa; el frontend la revela con escritura rápida (≤ ~700 ms, por palabras; nada con `prefers-reduced-motion`) | Que también «aparezca» sin ralentizar |
| Tokens y esperas | Tras el primer token, `tic()` no emite más | La respuesta visible ya es la señal de avance |

## Integración en el backend (FastAPI, `agente/backend-api`)

```python
from src.chatbot.respuesta_en_vivo import escuchar_tokens

traductor = TraductorProgreso(recientes=frases_de_la_sesion)
emitir(traductor.iniciar())
engine.set_progress_listener(lambda e: emitir(traductor.traducir(e)))
# EN EL HILO DEL MOTOR (ContextVar por hilo):
with escuchar_tokens(lambda texto: emitir(traductor.token(texto))):
    result = engine.process(texto)
# generador SSE: cada ~1 s → emitir(traductor.tic())
emitir(traductor.finalizar()); enviar respuesta; emitir(traductor.aviso(result))
```

`emitir` desde el hilo del motor al bucle async: `loop.call_soon_threadsafe(cola.put_nowait, sobre)`.

## Technical Context

**Language/Version**: Python 3.14 · **Dependencies**: ninguna nueva (cliente `ollama` existente) ·
**Testing**: unittest (`tests/progreso`, `tests/streaming`, `tests/stability`) · **Constraints**: sin `.env`,
sin MedGemma ni Power BI reales; cambios en la síntesis mínimos (un parámetro `on_token`) por los agentes de
rendimiento, truncado y memoria.

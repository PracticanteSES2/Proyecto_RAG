# Plan de implementación: Documentación viva en la web

**Rama**: `agente/documentacion-web` | **Fecha**: 2026-11-11 | **Spec**: [spec.md](spec.md) ·
**Contrato**: [contracts/api-documentacion.md](contracts/api-documentacion.md)

## Resumen

La página de Streamlit `pages/1_Documentación.py` → `src/docs_md/interfaz.py` se reparte así:

| Streamlit (`interfaz.py`) | Nuevo stack |
|---|---|
| `repositorio.listar_tableros/listar_paginas`, lectura del `.md` | `GET /documentacion/grupos[/…/paginas[/archivo]]` |
| `ficha_markdown`, `cuerpo_markdown`, `historial_markdown`, `etiqueta_pagina` | `services/documentacion_vista.py` (estructuras, no Markdown armado) |
| `_formulario` + `_proponer` (spinner) | `POST /propuestas` (202) + sondeo `GET /propuestas/{id}` con `progreso` |
| `_revisar_lista`, `describir_operacion`, `texto_actual`, `reaplicar`, `diff_html`, `lineas_cambiadas` | vista de la propuesta (`operaciones`, `diff.bloques`) + `POST …/operaciones` |
| `_aclarar` | `candidatas` + `POST …/aclaracion` |
| `_aprobar` + `_reindexar_aprobado` + `reindexar` (cliente del chat) | `POST …/aprobar` + `CoordinadorIndice` (piscina del motor embebido) |
| `_mostrar_aprobado`, `mensaje_error`, `metodo_pagina_texto`, `tiempos_texto` | campos `aprobacion`, `errores`, `como_se_eligio`, `tiempos` |

`interfaz.py` importa `streamlit` y es legado: el backend no puede importarlo. Su lógica pura de presentación se
reescribe en `documentacion_vista.py` (morirá con Streamlit; ver ARQUITECTURA §9). `src/docs_md` no se toca.

## Decisiones

| Decisión | Motivo | Alternativa descartada |
|---|---|---|
| Asincronía por **202 + sondeo** (1 s) | la propuesta es un trabajo único de 5–60 s con un solo resultado; el sondeo es trivial de reanudar (recargar la página, otra pestaña) y no ocupa una conexión SSE | SSE: mismo valor para un único resultado, más piezas (almacén de eventos por propuesta) |
| Progreso **calculado al leer** (etapa real + rotación cada 8 s + umbrales de espera 10/25/50/90 s con `nivel_espera` de `src.chatbot.progreso`) | sin hilo reloj; cualquier lectura ve el mismo estado; mismas reglas que el chat (frases de trabajo, sin colas) | traductor con `tic()` por propuesta |
| Etapa real con un **proveedor observado** (`ProveedorObservado` envuelve a `MedGemmaProvider` y avisa cada llamada; la de `max_tokens == MAX_TOKENS_PAGINA` es elegir página) | `proponer_cambio` no emite eventos y no se refactoriza `src/docs_md`; la llamada sigue pasando por `call_llm` | frases por tiempo (podrían mentir sobre lo que pasa) |
| Propuestas en **memoria del proceso de la API** (24 h, máx. 200) | un solo proceso uvicorn en este equipo (sin Redis) | Redis: queda pendiente para varios procesos |
| Reindexación en un **hilo dedicado** que **retiene todas las instancias** de la piscina del motor embebido, pasa a `reindexar_grupo` el retriever del motor (cliente Qdrant + MiniLM) y luego invalida la huella de la caché de respuestas | Qdrant local admite un solo cliente por carpeta; `refresh_metadata` reemplaza el corpus en memoria que usan los turnos; un turno nunca ve un índice a medias; la caché no sirve la versión vieja | reindexar en paralelo con los turnos (carrera con `refresh_metadata`), abrir otro cliente (Qdrant lo rechaza) |
| Motor externo (Redis + trabajador): `no_disponible` | la API no es dueña de Qdrant; hace falta una cola de tareas en el trabajador (pendiente) | abrir Qdrant desde la API (choca con el trabajador) |
| `InstanciaMotor.retriever` (nuevo campo) | la piscina no guardaba el retriever; `construir_instancia_real` lo tiene a mano | buscarlo con `active_retriever()` (ambiguo con varias carpetas) |
| Diff estructurado en el backend (`difflib`, tramos con 1 línea de contexto) | el frontend no calcula nada; se pinta con tokens `success`/`danger`, signo «+/−» y texto para lectores de pantalla | HTML armado en el backend (como Streamlit) |
| Una sola ruta `/documentacion` con la selección en estado local | página estática, sin `useSearchParams`/Suspense; compartir el enlace a una página queda pendiente | `app/documentacion/[grupo]/[archivo]` |
| Cliente propio `lib/api/documentacion.ts` sobre el transporte común (`crearTransporte`), y `ErrorApi` con `codigo`/`mensajeServidor` | los 409 de negocio («la documentación cambió…») se muestran con el texto amable del backend; el chat no cambia | ampliar `ClienteApi` (obligaría a tocar todos los dobles del chat) |
| Mock en rutas de Next (`app/api/v1/documentacion/**`) con propuesta temporizada | mismo patrón del chat: el cliente no cambia, solo la URL base | MSW |

## Estructura

```text
backend/app/api/v1/documentacion.py        # router delgado
backend/app/schemas/documentacion.py       # contrato pydantic
backend/app/services/documentacion.py      # ServicioDocumentacion: lectura, propuestas (hilos), aprobación
backend/app/services/documentacion_vista.py# ficha/cuerpo/historial/operaciones/diff (puro)
backend/app/services/documentacion_indice.py # CoordinadorIndice + ProveedorObservado + frases de trabajo
tests/backend/test_documentacion_vista.py
tests/backend/test_documentacion_servicio.py
tests/backend/test_documentacion_api.py
tests/backend/documentacion_doble.py       # actualizador e indexación dobles
frontend/app/documentacion/page.tsx
frontend/app/api/v1/documentacion/**       # mock
frontend/components/documentacion/*        # Explorador, VistaDocumento, FormularioPropuesta, RevisionPropuesta, Diff, …
frontend/hooks/useDocumentacion.ts, usePropuesta.ts
frontend/lib/api/{cliente,tipos}.ts        # métodos y tipos de documentación
frontend/lib/mock/documentacion*.ts
frontend/tests/{lib,componentes}/documentacion*.test.ts(x)
```

## Riesgos

- Una reindexación espera a que terminen los turnos en curso (hasta minutos si uno es lento); mientras tanto los
  turnos nuevos esperan en la cola. Aceptable: es una acción de mantenimiento y suele tardar segundos
  (embeddings incrementales).
- Las cachés del `QueryPlanBuilder` (índice de páginas, documentos semánticos) no se recargan al reindexar
  (Streamlit tampoco): el RAG (lo que responde el chat documental) sí usa el texto nuevo al instante; el índice de
  páginas del planificador se refresca al reiniciar el motor.

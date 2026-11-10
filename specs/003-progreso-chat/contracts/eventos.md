# Contrato: eventos de progreso del turno

Productor: `src/chatbot/progreso.py` (`TraductorProgreso`) y `src/chatbot/respuesta_en_vivo.py` (tokens).
Transporte: SSE desde el backend FastAPI. Consumidor: frontend Next.js.

**Revisión 2026-11-10 (specs/009-experiencia-espera)** — decisión del usuario: la espera se siente como trabajo
sobre la pregunta de la persona. **Ningún texto visible menciona colas, filas, turnos, posiciones, otras consultas,
otros usuarios, el servidor, ocupación ni saturación.** Cambios: se elimina la etapa `en_cola`; rotación lenta de
frases; nuevas frases de `espera`; aviso de degradación neutro; nuevo evento `token`; `cola` solo para diagnóstico.

## Sobre

Cada método del traductor devuelve una **lista** (posiblemente vacía) de sobres:

```json
{"evento": "progreso", "datos": {"etapa": "consultando_powerbi", "frase": "Trayendo las cifras del tablero", "t": 4.0}}
```

El backend lo envía como:

```
event: progreso
data: {"etapa": "consultando_powerbi", "frase": "Trayendo las cifras del tablero", "t": 4.0}
```

Todos los textos van en UTF-8, en español, sin dígitos ni términos técnicos. `t` = segundos (1 decimal)
desde el inicio del turno: **solo para ordenar y medir; la interfaz no lo muestra**.

## Eventos

### `progreso` — etapa de trabajo del turno

| Campo | Tipo | Notas |
|---|---|---|
| `etapa` | str | una de las etapas de abajo |
| `frase` | str | frase lista para mostrar (≤ ~55 caracteres) |
| `t` | float | segundos desde el inicio |

Se emite cuando la etapa cambia y, si la etapa se alarga, **cada `ROTACION_S` = 8 s** (vía `tic()`) con la MISMA
etapa y la siguiente frase de `SEGUIMIENTO[etapa]` (en orden de avance, cíclica, sin repetir la anterior).
Reemplaza la frase anterior (con un fundido suave).

| Etapa | Cuándo | Frase inicial (ej.) | Seguimiento (rotación) |
|---|---|---|---|
| `entendiendo` | inicio del turno; interpretación; espera de turno | «Entendiendo tu pregunta» | «Pensando…» · «Precisando qué dato necesitas» · «Pensando en la mejor forma de responderte» |
| `buscando_indicador` | Query Plan / armado de la consulta | «Buscando el indicador en los tableros» | «Comparando los indicadores que podrían servir» · «Revisando el periodo y los filtros» · «Pensando…» |
| `preparando_opciones` | MedGemma describe las opciones | «Preparando las opciones para que elijas» | «Revisando cada opción» · «Describiendo cada opción con claridad» · «Pensando…» |
| `conectando_powerbi` | apertura o reapertura de la conexión | «Conectando con Power BI» | «Esperando la conexión con los tableros» · «Preparando la consulta del dato» |
| `consultando_powerbi` | consulta DAX, lista de valores o de detalle | «Consultando los datos en Power BI» | «Esperando las cifras del tablero» · «Revisando las cifras que llegan» · «Pensando…» |
| `revisando_documentacion` | búsqueda en la documentación + redacción RAG | «Revisando la documentación de los tableros» | «Revisando los datos que encontré» · «Organizando la respuesta» · «Redactando la respuesta» · «Pensando…» |
| `redactando` | reservada: actividad «Redactando…» | «Redactando la respuesta» | «Organizando la respuesta» · «Pensando…» · «Puliendo la redacción» |
| `finalizando` | el backend llama `finalizar()` al volver el motor | «Ya casi está» | «Dando los últimos toques» · «Revisando que todo cuadre» |

**Ya no existe `en_cola`.** Esperar un hueco de MedGemma (actividad «LLM en cola…») o el turno de otra consulta
(`esperando_turno()`) **no cambia la etapa**: la persona sigue viendo la etapa de trabajo y su rotación.

### `espera` — la respuesta tarda (renglón secundario)

| Campo | Tipo | Notas |
|---|---|---|
| `nivel` | int | 1..4 (umbrales 10, 25, 50, 90 s desde el inicio) |
| `frase` | str | mensaje tranquilizador |
| `t` | float | segundos desde el inicio |

Lo produce `tic()`, que el backend llama periódicamente (recomendado cada 1 s) mientras el motor trabaja.
Cada `espera` reemplaza a la anterior; si se cruzaron varios umbrales entre dos `tic`, solo llega el más alto.
No depende de la carga del servidor.

| Nivel | Frase |
|---|---|
| 1 | «Sigo trabajando en tu pregunta…» |
| 2 | Power BI: «Las cifras de Power BI están tardando un poco; sigo pendiente.» · resto: «Estoy armando una respuesta completa; ya casi la tengo…» |
| 3 | «Sigo con tu pregunta; no hace falta volver a enviarla.» |
| 4 | «Me está tomando más de lo habitual, pero sigo en ello.» |

### `token` — la respuesta aparece de a poco (nuevo)

| Campo | Tipo | Notas |
|---|---|---|
| `texto` | str | fragmento a **añadir** al borrador de la burbuja (no vacío) |

Solo en respuestas documentales redactadas por MedGemma (streaming de Ollama). Las respuestas de Power BI, del
portero y de la caché no traen tokens: llegan completas en `respuesta`. Tras el primer `token`, `tic()` deja de
emitir rotaciones y esperas.

Productor: `MedGemmaProvider.chat(stream=True, on_token=cb)` → `llm_gate.call_llm(..., on_token=cb)` →
`AnswerSynthesizer.synthesize_rag(..., on_token=cb)` → `RAGAnswerEngine.answer(..., on_token=cb)` →
`QueryEngine.process(texto, on_token=cb)` / `select_clarification_option(..., on_token=cb)` (decorador
`con_tokens`, que activa `escuchar_tokens(cb)` durante el turno). `TraductorProgreso.token(texto)` arma el sobre.
`cb` se llama en el hilo del motor; si lanza, se ignora; nunca llega un token después de un `llm_timeout`.

**Borrador y validación.** Lo transmitido es un **borrador**. El post-proceso (limpieza de muletillas, quitar
escalas no documentadas, salvaguarda de cifras de `src/rag/grounding.py`, truncado) se aplica igual al texto
completo y la respuesta final llega en `respuesta`, que **reemplaza** al borrador. Para evitar el salto más visible,
`FiltroBorrador` retiene el comienzo hasta decidir: nunca transmite la frase de «sin evidencia» ni la muletilla
inicial («Claro, …»). Si el RAG no halla evidencia y el motor responde por otra ruta, la `respuesta` también
reemplaza al borrador.

### `cola` — solo modo diagnóstico

| Campo | Tipo | Notas |
|---|---|---|
| `posicion` | int ≥ 0 | 1 = es el siguiente; 0 = desconocida |
| `en_curso` | int ≥ 0 | consultas atendiéndose delante |

Lo produce `esperando_turno(posicion, en_curso)` (y el backend desde la fila de Redis / `llm_gate`). **El modo
normal nunca lo convierte en texto** (ni «hay N consultas antes que la tuya» ni «en fila»); el modo diagnóstico
puede mostrarlo con segundos y posición.

### `aviso` — respuesta extractiva

| Campo | Tipo | Notas |
|---|---|---|
| `motivo` | str | `saturado` \| `sin_redaccion` — **solo diagnóstico, no se muestra** |
| `texto` | str | siempre la nota neutra «Te muestro lo que dice la documentación.» |

Lo produce `aviso(result)` tras el turno; solo para respuestas documentales (`route = "rag"`) con
`synthesis_mode = "extractive"`. Se presenta como una respuesta normal con esa nota discreta debajo. Debe
persistirse con el mensaje para que se vea al recargar el historial.

## Secuencias típicas

Pregunta de datos:

```
progreso {etapa: entendiendo}            t=0.0
progreso {etapa: buscando_indicador}     t=1.8
progreso {etapa: consultando_powerbi}    t=3.1
progreso {etapa: consultando_powerbi, frase: «Esperando las cifras del tablero»}   t=11.1   (rotación)
espera   {nivel: 1}                      t=10.0
progreso {etapa: finalizando}            t=12.4
(event: respuesta ... — fuera de este contrato; el frontend la revela con escritura rápida)
```

Pregunta documental con MedGemma cargado:

```
progreso {etapa: entendiendo}                 t=0.0
progreso {etapa: revisando_documentacion}     t=1.2
(cola {posicion: 2, en_curso: 3}              solo diagnóstico)
progreso {…, frase: «Revisando los datos que encontré»}   t=9.2
espera   {nivel: 1, «Sigo trabajando en tu pregunta…»}    t=10.0
progreso {…, frase: «Organizando la respuesta»}           t=17.2
token {texto: "El indicador "} · token {texto: "mide la ocupación"} · …
progreso {etapa: finalizando}
respuesta {…}   ← reemplaza al borrador
```

Turno del portero («hola»): `progreso entendiendo` y la respuesta llegan en < 1 s.

## Reglas para el frontend

- No pintar el indicador hasta 600 ms después de enviar la pregunta (la charla no debe mostrarlo).
- Un solo contenedor: `progreso` reemplaza la frase (fundido suave, también en la rotación); `espera` reemplaza
  el renglón secundario; el indicador desaparece al llegar el primer `token` o la respuesta.
- Nunca mostrar `t`, `nivel`, `etapa`, `motivo` ni `cola` como texto en modo normal.
- `token`: añadir el texto a la burbuja del asistente con un cursor sutil al final; la burbuja crece hacia abajo
  sin mover lo anterior (sin saltos de layout).
- `respuesta` tras tokens: si el texto final (espacios normalizados) **empieza por el borrador**, se sigue
  escribiendo desde ahí sin salto; si no (la salvaguarda cambió algo), fundido cruzado de ~150 ms fijando el alto
  mínimo de la burbuja durante el cambio.
- `respuesta` sin tokens (Power BI, portero, caché): revelado con escritura rápida y natural, por palabras, en
  ≤ ~700 ms en total (las tablas y botones aparecen al terminar); sin efecto con `prefers-reduced-motion`.
- `aviso`: la nota neutra en texto secundario bajo la respuesta.

## Ganchos para otros agentes

- **Backend**: pasar `on_token` a `engine.process` (la firma lo anuncia) y publicar `traductor.token(texto)`;
  `cola` solo para el modo diagnóstico.
- **Carga (src/llm, runtime_stats)**: `STATS.llm_pressure()` y `leer_carga_llm` quedan para el diagnóstico; ningún
  texto para el usuario depende de ellos.
- **Motor**: una actividad «Redactando la respuesta» antes de la síntesis con MedGemma activa `redactando`.

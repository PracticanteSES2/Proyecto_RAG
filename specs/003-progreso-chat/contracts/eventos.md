# Contrato: eventos de progreso del turno

Productor: `src/chatbot/progreso.py` (`TraductorProgreso`). Transporte: SSE desde el backend FastAPI.
Consumidor: frontend Next.js.

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

### `progreso` — cambió la etapa real del turno

| Campo | Tipo | Notas |
|---|---|---|
| `etapa` | str | una de las etapas de abajo |
| `frase` | str | frase lista para mostrar (≤ ~55 caracteres) |
| `t` | float | segundos desde el inicio |

Se emite solo cuando la etapa cambia. Reemplaza la frase anterior.

| Etapa | Cuándo | Ejemplo de frase |
|---|---|---|
| `entendiendo` | inicio del turno; interpretación (reglas o MedGemma) | «Entendiendo tu pregunta» |
| `buscando_indicador` | Query Plan / armado de la consulta | «Buscando el indicador en los tableros» |
| `preparando_opciones` | MedGemma describe las opciones de una contrapregunta | «Preparando las opciones para que elijas» |
| `conectando_powerbi` | apertura o reapertura de la conexión | «Conectando con Power BI» |
| `consultando_powerbi` | consulta DAX, lista de valores o de detalle | «Consultando los datos en Power BI» |
| `revisando_documentacion` | búsqueda en la documentación + redacción RAG | «Revisando la documentación de los tableros» |
| `redactando` | reservada: actividad «Redactando…» (aún no la emite el motor) | «Redactando la respuesta» |
| `en_cola` | el turno espera a otro (candado de turno / cola Redis) o actividad «LLM en cola» | «Tu pregunta está en fila; enseguida la atiendo» |
| `finalizando` | el backend llama `finalizar()` al volver el motor | «Ya casi está» |

### `espera` — la respuesta tarda

| Campo | Tipo | Notas |
|---|---|---|
| `nivel` | int | 1..4 (umbrales 10, 25, 50, 90 s desde el inicio) |
| `frase` | str | mensaje tranquilizador |
| `t` | float | segundos desde el inicio |

Lo produce `tic()`, que el backend llama periódicamente (recomendado cada 1 s) mientras el motor trabaja.
Cada `espera` reemplaza a la anterior; si se cruzaron varios umbrales entre dos `tic`, solo llega el más alto.

| Nivel | Frase |
|---|---|
| 1 | «Esto está tomando un poco más de lo normal…» |
| 2 | Power BI: «Power BI está tardando en responder; sigo esperando los datos.» · en cola: «Hay otra consulta en curso; la tuya sigue enseguida.» · MedGemma ocupado: «Hay varias consultas en curso; la tuya está en fila, ya casi…» · resto: «Sigo trabajando en tu respuesta; gracias por la paciencia.» |
| 3 | «Sigue en marcha: no hace falta volver a enviar la pregunta.» |
| 4 | «Está tardando más de lo habitual; sigo esperando la respuesta.» |

### `cola` — posición en la fila

| Campo | Tipo | Notas |
|---|---|---|
| `posicion` | int ≥ 0 | 1 = es el siguiente; 0 = desconocida |
| `en_curso` | int ≥ 0 | consultas atendiéndose delante |

Lo produce `esperando_turno(posicion, en_curso)`; puede repetirse para actualizar la posición. Con el candado
actual («un turno a la vez») el backend usa `posicion=1, en_curso=1`; con Redis, la posición real.

### `aviso` — respuesta degradada

| Campo | Tipo | Notas |
|---|---|---|
| `motivo` | str | `saturado` \| `sin_redaccion` |
| `texto` | str | nota amable para mostrar bajo la respuesta |

Lo produce `aviso(result)` tras el turno; solo para respuestas documentales (`route = "rag"`) con
`synthesis_mode = "extractive"`. Debe persistirse con el mensaje para que se vea al recargar el historial.

## Secuencia típica

```
progreso {etapa: entendiendo}            t=0.0
progreso {etapa: buscando_indicador}     t=1.8
progreso {etapa: consultando_powerbi}    t=3.1
espera   {nivel: 1}                      t=10.0
progreso {etapa: finalizando}            t=12.4
(event: respuesta ... — fuera de este contrato)
aviso    {motivo: ...}                   (opcional)
```

Turno del portero («hola»): `progreso entendiendo` y la respuesta llegan en < 1 s.

## Reglas para el frontend

- No pintar el indicador hasta 600 ms después de enviar la pregunta (la charla no debe mostrarlo).
- Un solo contenedor: `progreso` reemplaza la frase; `espera` reemplaza el renglón secundario; desaparece al
  llegar la respuesta.
- Nunca mostrar `t`, `nivel` ni `etapa` como texto.

## Ganchos para otros agentes

- **Carga (src/llm, runtime_stats)**: exponer `STATS.llm_pressure()` →
  `{"in_flight", "waiting", "capacity", "saturated_recent"}` (rechazos por saturación del último minuto).
  `leer_carga_llm` ya lo usa si existe. Para avisar en vivo que una llamada quedó en cola, emitir una
  actividad con título que empiece por «LLM en cola» (se traduce a `en_cola`).
- **Motor**: una actividad «Redactando la respuesta» antes de la síntesis con MedGemma activa `redactando`.

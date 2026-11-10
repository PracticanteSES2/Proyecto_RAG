# Contrato API v1 — Asistente de Gestión Clínica

Base: `/api/v1`. JSON UTF-8. OpenAPI: `/api/v1/openapi.json` (Swagger en `/api/v1/docs`).
Sin usuarios ni login. Identificador opcional del navegador: cabecera `X-Cliente-Id` (8–64 caracteres
`[A-Za-z0-9_-]`, p. ej. un UUID guardado en `localStorage`); se usa para el límite de peticiones (si falta, la IP).

## Errores (todas las rutas)

```json
{"mensaje": "Texto amable en español, sin detalles internos.", "codigo": "turno_en_curso"}
```

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `conversacion_no_encontrada` · `turno_no_encontrado` | id inexistente o expirado |
| 409 | `turno_en_curso` | ya hay un turno sin terminar en esa conversación |
| 409 | `opcion_no_vigente` | `opcion_id` no es de la contrapregunta pendiente |
| 409 | `turno_no_calificable` | el turno aún no termina o no tiene respuesta que calificar |
| 400 | `formato_no_soportado` | exportación con un formato distinto de `md` |
| 422 | `peticion_invalida` | cuerpo inválido (mensaje vacío sin opción, demasiado largo, valor desconocido…) |
| 429 | `demasiadas_peticiones` | límite por cliente; cabecera `Retry-After` (s) y campo `reintentar_en_s` |
| 503 | `servicio_ocupado` | la fila de turnos está llena |
| 500 | `error_interno` | inesperado |

## Conversaciones

### `POST /conversaciones` → `201`
```json
{"conversacion_id": "3f2a…(32 hex)"}
```

### `GET /conversaciones/{id}` → `200`
```json
{
  "conversacion_id": "…", "creada": "2026-11-10T11:40:32-05:00", "actualizada": "…",
  "turno_activo": null,
  "mensajes": [
    {"rol": "usuario", "texto": "¿Cuántas cirugías hubo en 2024?", "via": "texto", "turno_id": "…", "fecha": "…"},
    {"rol": "asistente", "turno_id": "…", "fecha": "…", "respuesta": { /* payload `respuesta` sin `diagnostico` */ },
     "contrapregunta_vigente": true}
  ]
}
```
`via`: `texto` | `opcion`. `contrapregunta_vigente` solo es `true` en la última contrapregunta aún sin responder
(pintar sus botones activos; las anteriores como referencia). Un error queda como
`{"rol": "asistente", "error": {"mensaje", "codigo"}}`.

### `GET /conversaciones/{id}/exportar?formato=md&razonamiento=true` → `200 text/markdown`
Descarga (`Content-Disposition: attachment; filename="conversacion_AAAAMMDD_HHMMSS.md"`) generada por
`src/chatbot/conversation_export.py`, igual que «Descargar conversación (.md)» de Streamlit (enlaces de Power BI
incluidos; `razonamiento=false` lo omite). Único formato hoy: `md`.

## Turnos

### `POST /conversaciones/{id}/turnos` → `202`
Cuerpo:
```json
{"mensaje": "¿Cuántas cirugías hubo en 2024?", "diagnostico": false, "opcion_id": null}
```
- `mensaje`: 1–2000 caracteres (obligatorio salvo con `opcion_id`; con opción puede ir el texto del botón, que es
  lo que se guarda en el historial; si va vacío se usa la etiqueta de la opción).
- `opcion_id`: respuesta a la contrapregunta pendiente (un `opciones[].id`).
- `diagnostico`: si `true`, la respuesta incluye `diagnostico`.

Respuesta:
```json
{"turno_id": "…", "conversacion_id": "…", "eventos_url": "/api/v1/turnos/…/eventos"}
```

### `GET /turnos/{turno_id}/eventos` → `200 text/event-stream`
Formato SSE estándar: `id:` (solo en eventos guardados; usar `Last-Event-ID` o `?desde=<id>` al reconectar),
`event:` y `data:` (JSON). Comentarios `: ping` cada 15 s. `retry: 3000` al inicio. El flujo termina tras `fin`.

| Evento | `data` | Notas |
|---|---|---|
| `cola` | `{"posicion": 2, "en_curso": 1}` | mientras el turno espera en la fila (1 = el siguiente; sin `id:`) o una llamada a MedGemma espera hueco. **Mostrar solo en modo diagnóstico**: la interfaz nunca habla de filas, otras consultas ni saturación |
| `progreso` | `{"etapa": "consultando_powerbi", "frase": "Trayendo las cifras del tablero", "t": 4.0}` | contrato de `specs/003-progreso-chat/contracts/eventos.md` (etapas, reglas: no mostrar `t`) |
| `espera` | `{"nivel": 1, "frase": "Esto está tomando un poco más de lo normal…", "t": 10.0}` | niveles 1..4 (10/25/50/90 s) |
| `token` | `{"texto": "El tablero muestra"}` | trozo de la redacción en streaming (cuando el motor lo emita; agente/ux-espera). Concatenar en orden; `respuesta` trae el texto final completo y lo reemplaza |
| `aviso` | `{"motivo": "saturado" \| "sin_redaccion", "texto": "…"}` | respuesta documental degradada (también va en `respuesta.aviso`) |
| `respuesta` | ver abajo | una por turno |
| `error` | `{"mensaje": "Ocurrió un error al procesar la consulta. Intenta nuevamente.", "codigo": "error_motor"}` | `codigo`: `error_motor` · `interrumpido` · `expirado` |
| `fin` | `{}` | último evento |

Reconexión: con `Last-Event-ID` se reenvía todo lo posterior. Si el turno ya terminó y sus eventos expiraron, se
reenvían `respuesta` (o `error`) y `fin` reconstruidos del estado final.

#### Payload `respuesta`
```json
{
  "turno_id": "…",
  "texto_markdown": "En 2024 hubo **1.234** cirugías realizadas…",
  "ruta": "datos",
  "estado": "success",
  "fuentes": [{"titulo": "Tablero Quirúrgico › Cirugías", "tablero": "Tablero Quirúrgico", "pagina": "Cirugías"}],
  "enlaces_powerbi": [{"titulo": "Tablero Quirúrgico › Cirugías · con los filtros de la consulta", "url": "https://app.powerbi.com/…"}],
  "contrapregunta": null,
  "detalles": {"informe": "…", "tablero": "…", "modelo_semantico": "…", "metrica": "…", "filtros_tablero": ["…"], "sintesis": null},
  "degradada": false,
  "aviso": null,
  "cacheada": false,
  "diagnostico": null
}
```
- `ruta`: `conversacion` (portero: saludo, identidad, capacidades) · `datos` (Power BI) · `documentacion` (RAG) ·
  `contrapregunta` · `fuera_de_alcance` · `otra`.
- `estado`: estado del motor (`success`, `needs_clarification`, `not_found`, `empty_result`, `metric_not_resolved`,
  `unsupported_filter`, `powerbi_error`, …). Informativo: el texto ya explica el caso.
- `contrapregunta` (si el asistente pide aclarar):
  `{"pregunta": "¿A cuál te refieres?", "opciones": [{"id": "b_cx_realizadas", "texto": "Cirugías realizadas (Tablero Quirúrgico)", "descripcion": "…", "enlace_powerbi": {"titulo", "url"}}]}`.
  Responder con un turno `{opcion_id}`. Puede incluir «Ninguna de las anteriores».
- `detalles`: lo de «Detalles de la consulta» de Streamlit (solo respuestas exitosas que no son charla).
- `degradada`/`aviso`: respuesta documental sin redacción (MedGemma saturado o caído) o Power BI no disponible.
- `cacheada`: la respuesta salió de la caché.
- `diagnostico` (solo con `diagnostico: true`):
  `{"razonamiento": "texto", "pasos": [{"titulo", "lineas", "t"}], "tiempos": {"cola_s", "motor_s", "total_s"},
  "estado", "etapa", "detalles", "error", "dax", "plan_consulta", "contexto_fuentes", "agrupaciones",
  "filtros_negocio", "pregunta_normalizada", "cacheada", "estado_servidor"}`.

### `POST /turnos/{turno_id}/calificacion` → `200`
```json
{"valor": "buena" | "mala", "comentario": "qué se esperaba (obligatorio si es mala; sin datos de pacientes)"}
```
Respuesta `{"guardada": true}`. Escribe en `data/feedback/calificaciones.jsonl` con `src/feedback/registro.py`
(snapshot saneado por lista blanca). Repetir la misma calificación no duplica la línea.

## Sistema

### `GET /capacidades` → `200`
```json
{"listo": true, "tableros_datos": ["Lavandería", "…"], "tableros_documentacion": ["Triage", "…"],
 "ejemplos": ["¿Cuál fue el total de atenciones el mes pasado?", "…"]}
```
`listo=false` (listas vacías) mientras el trabajador arranca.

### `GET /salud` → `200` (vida) · `GET /salud/listo` → `200` | `503` (preparación)
```json
{"estado": "ok" | "degradado" | "caido", "listo": true, "modo": "redis" | "memoria",
 "componentes": {
   "redis": {"estado": "ok" | "caido" | "no_configurado"},
   "motor": {"estado": "ok" | "iniciando" | "caido", "instancias": 1, "ocupadas": 0, "latido_hace_s": 1.2},
   "medgemma": {"estado": "ok" | "caido" | "desconocido", "modelo": "medgemma:…"},
   "powerbi": {"estado": "ok" | "caido" | "desconocido"},
   "indice": {"estado": "ok" | "caido" | "desconocido"}},
 "cola": {"en_espera": 0, "en_curso": 0}, "version": "abc1234"}
```
Sin URLs, credenciales ni rutas.

### `GET /diagnostico/servidor` → `200`
```json
{"disponible": true, "actualizado": "…", "lineas_markdown": ["- **Encendido:** hace 3 min …"],
 "linea_estado": "encendido hace 3 min · turnos 4 · …", "instantanea": { /* STATS.snapshot() */ },
 "cola": {"en_espera": 0, "en_curso": 0}, "motor": {"instancias": 1, "ocupadas": 0}}
```
Lo mismo que el desplegable «Diagnóstico del servidor» de Streamlit.

## Cambios respecto al borrador del orquestador (compatibles)

- `POST /conversaciones` responde `201` (no `200`); `POST …/turnos` añade `conversacion_id` y `eventos_url`.
- Eventos nuevos `espera` y `aviso` (de `src/chatbot/progreso.py`) y `token` (streaming de la redacción).
- `cola` solo para el modo diagnóstico; el backend ya no emite la etapa `progreso: en_cola` por la fila de turnos.
- `respuesta` añade `estado`, `detalles`, `cacheada` y `contrapregunta.opciones[].enlace_powerbi`.
- `GET /salud/listo` añadido para preparación (503 si no está listo).
- `error.codigo` del SSE: `error_motor`, `interrumpido`, `expirado`.

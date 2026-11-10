# Contrato consumido: API v1 del backend (vista del frontend)

Fuente de verdad en código: `frontend/lib/api/tipos.ts` (se reemplazará por tipos generados desde el OpenAPI
del backend FastAPI). Eventos de progreso: `specs/003-progreso-chat/contracts/eventos.md` (rama
`agente/ui-progreso`).

## Endpoints

| Método y ruta | Cuerpo | Respuesta |
|---|---|---|
| `POST /api/v1/conversaciones` | — | `{conversacion_id}` |
| `POST /api/v1/conversaciones/{id}/turnos` | `{mensaje, diagnostico, opcion_id?}` | `202 {turno_id}` · `429` (saturado) |
| `GET /api/v1/turnos/{turno_id}/eventos` | — | SSE (abajo); reconexión con `Last-Event-ID` |
| `GET /api/v1/conversaciones/{id}` | — | `{conversacion_id, turnos: TurnoGuardado[]}` *(supuesto)* |
| `GET /api/v1/conversaciones/{id}/exportar?formato=md` | — | `text/markdown` |
| `POST /api/v1/turnos/{turno_id}/calificacion` | `{valor: "buena"\|"mala", comentario?}` *(valor supuesto)* | `2xx` |
| `GET /api/v1/capacidades` | — | `{capacidades: [{titulo, descripcion}], ejemplos: [{texto, categoria?}]}` *(supuesto)* |
| `GET /api/v1/salud` | — | `{estado: "ok"\|"degradado", detalle?}` *(supuesto)*; cualquier fallo de red o no-2xx = caído |

## Eventos SSE

Cada evento lleva `id:` incremental (para `Last-Event-ID`), `event:` y `data:` JSON.

| Evento | Datos |
|---|---|
| `cola` | `{posicion, en_curso}` |
| `progreso` | `{etapa, frase, t}` — etapas: entendiendo, buscando_indicador, preparando_opciones, conectando_powerbi, consultando_powerbi, revisando_documentacion, redactando, en_cola, finalizando |
| `espera` | `{nivel, frase, t}` |
| `respuesta` | `{turno_id, texto_markdown, ruta, fuentes: [{titulo, tablero?, pagina?}], enlaces_powerbi: [{titulo, url}], contrapregunta?: {pregunta, opciones: [{id, texto, descripcion?}]}, degradada, aviso?, diagnostico?}` |
| `aviso` | `{motivo: "saturado"\|"sin_redaccion", texto}` (puede llegar tras `respuesta`) |
| `error` | `{mensaje, codigo}` |
| `fin` | `{}` |

## Supuestos del frontend (a confirmar con el agente de backend)

1. `TurnoGuardado` = `{turno_id, mensaje, opcion_id?, respuesta?: EventoRespuesta, avisos?: EventoAviso[],
   calificacion?: {valor, comentario?}}`; se usa para restaurar la conversación al recargar.
2. `diagnostico` es un objeto libre; si trae `dax` (texto), `razonamiento` (texto) o
   `tiempos: [{etapa, segundos}]` se muestran con formato propio, el resto como JSON.
3. `429` puede traer cabecera `Retry-After` (segundos); el frontend no muestra el número.
4. CORS: el backend debe permitir el origen del frontend (`http://localhost:3000` en desarrollo).

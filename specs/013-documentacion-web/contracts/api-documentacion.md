# Contrato API v1 — Documentación viva

Base: `/api/v1/documentacion`. JSON UTF-8. Mismos errores que el resto de la API
(`{"mensaje", "codigo"}`, ver `specs/006-api-backend/contracts/api-v1.md`). OpenAPI en `/api/v1/openapi.json`
(etiqueta `documentacion`).

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `grupo_no_encontrado` · `pagina_no_encontrada` · `propuesta_no_encontrada` | id inexistente (o propuesta expirada: viven 24 h) |
| 409 | `propuesta_en_curso` | se pide aclarar/aprobar/corregir mientras MedGemma prepara la propuesta |
| 409 | `propuesta_no_aprobable` | aprobar una propuesta que no está `lista` o cuyo resultado no cumple el formato |
| 409 | `propuesta_no_editable` | corregir operaciones de una propuesta que no está `lista` |
| 409 | `documento_modificado` | el archivo cambió desde que se hizo la propuesta (o no se pudo guardar) |
| 422 | `correccion_invalida` | la corrección de una operación no aplica o rompe el formato |
| 422 | `peticion_invalida` | cuerpo inválido (nota vacía, autor vacío, demasiado largo…) |

## Explorar

### `GET /grupos` → `200`
```json
{"grupos": [{"grupo": "tablero_tiempos_urgencias", "tablero": "Tiempos de urgencias", "paginas": 12}]}
```
Solo grupos con páginas `.md` (el diccionario `_diccionario*.md` no cuenta como página).

### `GET /grupos/{grupo}/paginas` → `200` · `404 grupo_no_encontrado`
```json
{"grupo": "tablero_tiempos_urgencias", "tablero": "Tiempos de urgencias",
 "paginas": [{"archivo": "_general.md", "pagina": "General", "nombre_funcional": "…", "bloque": "General",
              "valido": true, "general": true, "etiqueta": "General del tablero — …"}]}
```
La general primero. `etiqueta` es la de Streamlit (`etiqueta_pagina`): «Página — nombre funcional · bloque».

### `GET /grupos/{grupo}/paginas/{archivo}` → `200` · `404 pagina_no_encontrada`
```json
{"grupo": "…", "tablero": "…", "archivo": "consultas_dia.md", "ruta": "tablero_tiempos_urgencias/md/consultas_dia.md",
 "pagina": "CONSULTAS DIA", "interpretable": true, "valido": true, "errores_formato": [],
 "ficha": [{"dato": "Tablero", "valor": "…"}, {"dato": "Página", "valor": "CONSULTAS DIA"}, "… Nombre funcional, Bloque, Tablas, Versión, Última actualización"],
 "cuerpo": {"proposito": "Markdown", "secciones": [{"titulo": "Reglas de negocio", "entradas": [{"nombre": "Semáforo triage II", "texto": "Markdown"}]}]},
 "historial": [{"nombre": "2026-11-10 · v3 · Ana", "texto": "Se amplió…"}],
 "texto": "--- contenido .md completo ---"}
```
- `archivo` debe ser uno de los listados (no se aceptan rutas).
- `interpretable=false`: el `.md` no se pudo interpretar; `errores_formato` trae el motivo, `ficha`, `cuerpo`,
  `historial` van vacíos y `texto` trae el archivo tal cual.
- `valido=false` con `interpretable=true`: el documento se muestra y `errores_formato` lista los problemas.
- `historial`: el más reciente primero. Valores ausentes de la ficha: `"—"`.

## Propuestas (asíncronas: 202 + sondeo)

### `POST /propuestas` → `202` · `404 grupo_no_encontrado | pagina_no_encontrada`
```json
{"nota": "le subí el verde del semáforo de triage II a 20 minutos", "grupo": "tablero_tiempos_urgencias",
 "pagina": null, "cambios_pbip": ["Página CONSULTAS DIA: se cambió el semáforo…"], "autor": "Ana"}
```
`nota` 1–4000 caracteres (obligatoria); `pagina` = nombre de página o `null` (detectar); `cambios_pbip` ≤ 50
líneas de ≤ 500 caracteres; `autor` opcional (se propone al aprobar). Responde la **Propuesta** en estado
`preparando`. La genera `actualizador.proponer_cambio` (MedGemma por `call_llm`, propósito «documentación») en un
hilo del backend.

### `GET /propuestas/{id}` → `200` · `404 propuesta_no_encontrada`
Sondeo recomendado: cada 1 s mientras `estado == "preparando"` y mientras
`aprobacion.reindexacion.estado == "en_curso"`.

#### Propuesta
```json
{
  "propuesta_id": "32 hex", "grupo": "…", "tablero": "…",
  "estado": "preparando | lista | requiere_aclaracion | error | aprobada | descartada",
  "nota": "…", "pagina": "CONSULTAS DIA", "nombre_funcional": "…", "autor": "Ana", "cambios_pbip": [],
  "progreso": {"etapa": "leyendo_nota | eligiendo_pagina | redactando | revisando", "frase": "Leyendo tu nota", "espera": null},
  "como_se_eligio": "la nota la nombra o usa palabras que solo están en esa página",
  "resumen": "…", "dudas": [], "avisos": [], "errores": [],
  "operaciones": [{"indice": 0, "accion": "agregar | modificar | eliminar", "seccion": "Reglas de negocio",
                   "entrada": "Semáforo triage II", "descripcion": "Cambiar la entrada **«Semáforo triage II»** de **Reglas de negocio**",
                   "texto": "Verde de 0 a 20 minutos…", "texto_actual": "Verde de 0 a 15…", "editable": true}],
  "diff": {"agregadas": 1, "eliminadas": 1, "unificado": "--- antes/…",
           "bloques": [{"lineas": [{"tipo": "igual | sale | entra", "texto": "…"}]}]},
  "vista_previa": {"cuerpo": {"proposito": "…", "secciones": []}, "historial": []},
  "formato_valido": true, "errores_formato": [],
  "candidatas": [{"pagina": "CONSULTAS DIA", "etiqueta": "CONSULTAS DIA — … · Día"}],
  "tiempos": "preparada en 9.8 s · 2 llamadas a MedGemma (4.1 s + 5.2 s)",
  "detalle_tecnico": null,
  "puede_aprobar": true,
  "aprobacion": null,
  "creada": "iso", "actualizada": "iso"
}
```
- `progreso` solo en `preparando`. `etapa` es la etapa real (la llamada a MedGemma en curso); `frase` rota cada 8 s
  dentro de la etapa; `espera` aparece a los 10/25/50/90 s. Ninguna frase habla de colas, otras personas,
  saturación ni del servidor.
- `operaciones`, `diff`, `vista_previa` solo con operaciones válidas (`lista`, o `requiere_aclaracion` con dudas del
  modelo). `diff.bloques` = tramos cambiados con 1 línea de contexto (como el diff de Streamlit).
- `candidatas` (aclaración): páginas posibles, ya filtradas a las existentes; si la propuesta no trae, todas.
- `detalle_tecnico`: respuesta cruda del modelo (solo en `error`); nunca trazas de Python.
- `puede_aprobar`: `estado == "lista"`, con operaciones y resultado con formato válido.
- `aprobacion` (estado `aprobada`):
  `{"autor": "Ana", "version": 4, "fecha": "iso", "reindexacion": Reindexacion}`.

### `POST /propuestas/{id}/operaciones` → `200` · `409 propuesta_no_editable` · `422 correccion_invalida`
```json
{"textos": [{"indice": 0, "texto": "Verde de 0 a 20 minutos…"}]}
```
«Actualizar vista previa»: reaplica las operaciones con los textos corregidos sobre el texto «antes» y devuelve la
Propuesta con diff y validación al día (no llama a MedGemma). Las operaciones `eliminar` no se editan.

### `POST /propuestas/{id}/aclaracion` → `202` · `409 propuesta_en_curso | propuesta_no_aprobable`
```json
{"nota": "…precisada", "pagina": "CONSULTAS DIA"}
```
Vuelve a generar la propuesta (misma id, estado `preparando`). `pagina: null` = que MedGemma la detecte. No se
permite sobre una propuesta `aprobada`.

### `POST /propuestas/{id}/descartar` → `200`
Estado `descartada` («La documentación no cambió»).

### `POST /propuestas/{id}/aprobar` → `200` · `409 propuesta_no_aprobable | documento_modificado | propuesta_en_curso`
```json
{"autor": "Ana"}
```
Guarda con `actualizador.aplicar_propuesta` (revalida contra el archivo actual; versión e historial los pone el
sistema), deja la Propuesta en `aprobada` y lanza la reindexación del grupo (`aprobacion.reindexacion`).

## Reindexación

### Reindexacion
```json
{"grupo": "…", "estado": "sin_iniciar | en_curso | lista | error | no_disponible",
 "mensaje": "El asistente ya usa el texto nuevo: se reindexó Tiempos de urgencias (12 documentos, 85 fragmentos, 3.2 s) con la conexión del chat.",
 "documentos": 12, "chunks": 85, "segundos": 3.2, "conexion_compartida": true, "avisos": [],
 "iniciada": "iso", "terminada": "iso"}
```
- `en_curso`: espera a que el motor termine los turnos en curso y retiene sus instancias mientras reescribe el
  índice del grupo (reutiliza el cliente Qdrant y el modelo de embeddings del motor; luego recarga su corpus).
- `no_disponible`: el motor corre en otro proceso (Redis + `python -m backend.worker`) o todavía está arrancando;
  el cambio quedó guardado y el mensaje dice qué hacer.
- `error`: el `mensaje` empieza por «La reindexación falló:»; se puede reintentar.

### `POST /grupos/{grupo}/reindexar` → `202` · `404 grupo_no_encontrado`
Lanza (o reintenta) la reindexación del grupo; si ya hay una en curso devuelve esa. Responde la Reindexacion.

### `GET /grupos/{grupo}/reindexacion` → `200` · `404 grupo_no_encontrado`
Último estado de la reindexación del grupo (`sin_iniciar` si nunca se lanzó en este proceso).

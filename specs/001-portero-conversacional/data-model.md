# Data Model: Portero conversacional

## Clasificacion (inmutable)

| Campo | Tipo | Valores / regla |
|---|---|---|
| `tipo` | str | `charla` · `identidad` · `capacidades` |
| `subtipo` | str | charla: `saludo`, `agradecimiento`, `despedida`, `estado`; identidad: `identidad`; capacidades: `capacidades` |
| `confianza` | float | 1.0 si `motivo == "regla"`; similitud coseno si `motivo == "similitud"` |
| `motivo` | str | `regla` · `similitud` |

Ausencia de clasificación (`None`) = el mensaje sigue el flujo normal.

## Motivo de bloqueo (guardas)

`numero` · `periodo` · `dominio` · `largo` · `None` (no bloqueado). Una guarda activa impide
cualquier clasificación, incluida la de similitud.

## Caso del banco del portero (`tests/portero/banco_portero.json`)

```json
{"version": 1, "casos": [
  {"id": "C01", "texto": "hola", "esperado": "charla/saludo"},
  {"id": "D01", "texto": "¿y en octubre?", "esperado": null}
]}
```

- `id`: único; prefijo `C` = conversacional, `D` = pregunta real/ambigua.
- `esperado`: `"tipo/subtipo"` o `null`. Sin datos de pacientes.

## Catálogo de tableros (derivado, en memoria)

`(datos: list[str], documentacion: list[str])`
- `datos`: `semantic_model` de `source_registry.json` en formato título.
- `documentacion`: tableros documentados del índice RAG que no coinciden (nombre normalizado
  o grupo) con ningún modelo; se excluyen los que empiezan por «DICCIONARIO».
- Deduplicados y ordenados; un tablero en ambos va solo en `datos`.

## Resultado del turno conversacional

| Campo | Valor |
|---|---|
| `status` | `"success"` |
| `route` | `"conversacion"` |
| `answer` | texto fijo |
| `conversation_kind` | `"tipo/subtipo"` |
| `question` | mensaje original |
| `reasoning` | traza con «Mensaje conversacional» |

Transiciones de estado: ninguna. El turno no entra en `conversation_memory` ni cambia
`_last_success`; las contrapreguntas pendientes no se tocan (el portero no corre si existen).

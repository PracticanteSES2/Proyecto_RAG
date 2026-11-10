# Contrato: módulo `src/chatbot/portero.py` y ruta `conversacion`

## Funciones públicas

| Firma | Garantía |
|---|---|
| `normalizar(texto: str) -> str` | Minúsculas, sin tildes, sin signos, espacios colapsados. Nunca lanza con `str`. |
| `bloqueado_por_guardas(texto: str, vocabulario_dominio: frozenset[str]) -> str \| None` | `"numero"`, `"periodo"`, `"dominio"`, `"largo"` o `None`. |
| `clasificar(texto: str, vocabulario_dominio: frozenset[str] = frozenset(), similitud: SimilitudPortero \| None = None) -> Clasificacion \| None` | Guardas y lista de bloqueo antes que reglas y similitud; similitud solo con 3–8 palabras (umbral 0.80, margen 0.20 iniciales). `None` ante cualquier duda. |
| `vocabulario_dominio(project_root) -> frozenset[str]` | Palabras del catálogo (`vocabulary_for(...).targets`) sin palabras conversacionales; `frozenset()` si falla. |
| `class SimilitudPortero(modelo, umbral=UMBRAL, margen=MARGEN)` · `.mejor(texto) -> tuple[str, float, float] \| None` | Ejemplos precalculados una vez; `encode` que falla → inactiva (`None`). |
| `catalogo_tableros(router) -> tuple[list[str], list[str]]` | `(datos, documentacion)`; `([], [])` si `router` es `None` o falla. |
| `responder(c: Clasificacion, datos: list[str], documentacion: list[str]) -> str` | Texto fijo; capacidades con grupos no vacíos o texto genérico. |

## Contrato de integración con `QueryEngine.process()`

- Corre solo en turno de primer nivel sin `_pending_query_plan`, `_pending_dashboard_clarification`, `_pending_master_metric`, `awaiting_clarification` ni `_applying_deferred`.
- Cualquier excepción del portero → flujo actual intacto.
- No llama `_record_turn`; no cambia `_last_success`.
- Devuelve el resultado descrito en [data-model.md](../data-model.md#resultado-del-turno-conversacional).

## Contrato con la UI y el registro

- `app.py` muestra `answer` tal cual para `route == "conversacion"`, sin bloque de informe/métrica.
- `src/feedback/registro.py` guarda la respuesta sin modo estricto para `conversacion` (como `rag`).

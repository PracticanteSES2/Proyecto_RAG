# Implementation Plan: Portero de alcance

**Branch**: `agente/portero-alcance` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-portero-alcance/spec.md` · Primera entrega: [specs/001-portero-conversacional](../001-portero-conversacional/plan.md)

## Summary

`portero.clasificar` gana un segundo paso: si el mensaje no es charla, el módulo puro nuevo
`src/chatbot/portero_alcance.py` busca un **marcador de categoría** (regex sobre el mensaje
original normalizado y con la jerga de chat expandida) y luego aplica las **anulaciones**: toda
palabra del catálogo fuera del marcador (con tipeo de una letra), periodo, número o mención del
propio hospital devuelve el mensaje al flujo normal, salvo las tolerancias de cada categoría.
Sin marcador, una **similitud MiniLM** (ejemplos por categoría, precalculados en la misma
`SimilitudPortero`) con umbral y margen frente a las referencias de dominio y a los ejemplos de
charla actúa solo sobre mensajes «limpios» de 3 a 12 palabras. La respuesta es un texto fijo por
grupo de categorías (vaga → invitación + capacidades del catálogo). El motor pasa el mensaje
original, cambia el título del razonamiento y añade `stage`.

## Technical Context

**Language/Version**: Python 3.14.7 (`.venv`)

**Primary Dependencies**: las de la primera entrega (MiniLM ya cargado por `HybridRetriever`). Ninguna nueva.

**Storage**: banco ampliado `tests/portero/banco_portero.json` (casos `F*`/`N*`)

**Testing**: unittest; `tests/portero` (reglas, MiniLM real offline con skip, motor con `tests.sim.harness`) y `tests/routing`

**Target Platform**: Windows 11, app Streamlit local

**Performance Goals**: reglas < 5 ms/mensaje; similitud < 50 ms/mensaje

**Constraints**: 0 falsos positivos en todos los bancos reales; sin LLM; nunca tumba el turno; cambio mínimo en `query_engine.py`; sin tocar `app.py`, `src/ui/`, `src/llm/`, `runtime_stats.py`

**Scale/Scope**: 13 categorías; ~150 casos `F*` y ~80 `N*`; ~10 ejemplos de similitud por categoría

## Constitution Check

| Compuerta | Estado |
|---|---|
| Power BI / BD solo lectura; el portero no consulta nada | ✅ |
| Sin datos de pacientes (textos fijos; casos del banco inventados y genéricos) | ✅ |
| `.env` intocado; MiniLM solo desde la caché local (sin descargas) | ✅ |
| spec-kit + superpowers (spec, plan, tareas, TDD, verificación) | ✅ |
| Archivos de otros agentes intocados (app.py, src/ui, src/llm, runtime_stats, tools/doctor, docs, assets) | ✅ |
| `graphify update .` tras editar código | ⚠️ CLI no instalado en este entorno; lo corre el orquestador al integrar |

## Design

### Orden en `clasificar(texto, vocab, similitud, original=None)`

1. Charla/identidad/capacidades (primera entrega, sin cambios) sobre `texto` (normalizado por el motor).
2. Lista de bloqueo de la primera entrega («resumen», «como vamos»…) → flujo normal.
3. `portero_alcance.clasificar_alcance(original or texto, vocab, similitud)`:
   1. tope de 200 caracteres; vacío o solo signos → `sin_sentido`;
   2. tokens normalizados + jerga (`q`/`k`→que, `d`→de, `pa`→para, `nesecito`→necesito…);
   3. plantillas vagas de mensaje ENTERO (con saludo/muletilla opcional al inicio);
   4. marcadores por categoría (orden: clínico, otra institución, cálculo, programación,
      redacción, noticias, clima, deportes, recetas, entretenimiento, conocimiento);
   5. anulaciones (FR-003) con las palabras del marcador toleradas;
   6. sin sentido (todas las palabras son risa o tecleo al azar);
   7. similitud (FR-005).

Además: un mensaje que empieza como seguimiento («y …», «también …», «pero …») nunca es fuera de
alcance; «buenos días» no cuenta como periodo; años, fechas y rangos sueltos («2024», «10/2025»)
nunca son sin sentido ni cálculo. Otra institución no se anula por vocabulario del catálogo
(«¿cómo hace los triages el Santa Sofía?») sino por flujo entre instituciones (remisión, traslado,
convenio, aseguradora, prepagada, primera persona plural, «al/desde/hacia X», «pacientes de X»).

### Anulación «dominio»

`vocab` (catálogo) menos palabras genéricas del español que el catálogo arrastra («las», «una»,
«dos», «tiene», «sentido»…), comparando cada palabra fuera del marcador con tolerancia de una
letra (sustitución, inserción u omisión) en palabras de 5+ letras.

### Respuestas

| Grupo | Categorías | Texto |
|---|---|---|
| vaga | vago | «Claro, con gusto. Dime qué dato o tablero necesitas…» + capacidades |
| clínico | clinico | «No doy recomendaciones clínicas, diagnósticos ni dosis…» |
| institución | otra_institucion | «Solo tengo información de los tableros del Hospital Universitario de Caldas…» |
| redacción | redaccion, programacion | «No redacto correos, textos ni código…» |
| sin sentido | sin_sentido | «No entendí tu mensaje…» |
| general | calculo, noticias, clima, recetas, deportes, entretenimiento, conocimiento | «Eso está fuera de lo que puedo responder…» |

Todas terminan con qué SÍ puede hacer (ejemplo de pregunta y «¿qué puedes hacer?»).

### Motor (`query_engine.py`, cambio mínimo)

`_portero_turn`: `clasificar(text, vocabulary, similarity, original=message)`; título del
razonamiento «Mensaje fuera de alcance» (vaga: «Petición sin tema»; sin sentido: «Mensaje sin
contenido reconocible») con el `detalle`; el resultado añade `stage = "portero/<tipo>/<subtipo>"`
(el registro lo guarda como `etapa`). Los rechazos salen con `status = "not_found"`,
`route = "out_of_scope"` (la ruta que ya usan motor, app, evaluador y memoria) y, como esa ruta en
el flujo normal, borran el seguimiento (`_remember_success`) y se registran en la memoria
(`_record_turn`); vaga y sin sentido salen por `conversacion` sin tocar el contexto.

## Project Structure

```text
specs/002-portero-alcance/   spec.md · plan.md · tasks.md
src/chatbot/
├── portero_alcance.py       # NUEVO: marcadores, anulaciones, sin sentido, ejemplos, textos
├── portero.py               # clasificar(original=...), Clasificacion.detalle, responder, similitud de alcance
└── query_engine.py          # _portero_turn: original, título del razonamiento, stage
tests/portero/
├── banco_portero.json       # + casos F* (categoría) y N* (dominio difícil)
├── test_portero_alcance.py  # NUEVO: categorías, anulaciones, barrido de todos los bancos, textos
├── test_portero_minilm.py   # + similitud de alcance con MiniLM real (skip sin caché)
└── test_motor_portero.py    # + integración (ruta, razonamiento, sin búsquedas, stage)
```

## Complexity Tracking

Sin violaciones. Se reutilizan las rutas `out_of_scope` y `conversacion` en lugar de crear una
nueva para no tocar `app.py` ni el registro (otro agente trabaja en la UI); la categoría viaja en
`conversation_kind` y `stage`.

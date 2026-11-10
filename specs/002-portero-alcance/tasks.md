---
description: "Tareas del portero de alcance (segunda entrega)"
---

# Tasks: Portero de alcance

**Input**: `specs/002-portero-alcance/` (spec, plan) · Primera entrega: `specs/001-portero-conversacional/`

**Tests**: obligatorios (superpowers test-driven-development). Cada prueba se escribe y se ve fallar antes de implementar.

**Comando**: `.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests/portero -t .` (y `-s tests/routing`).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Ampliar `tests/portero/banco_portero.json` con casos `F*` (`esperado = "fuera_de_alcance/<categoría>"`, ≥8 por categoría con variantes, tipeos, sin tildes, mayúsculas, saludo delante) y casos `N*` (`esperado: null`) de dominio difíciles: «hazme un reporte de la ocupación de camas», antibióticos/farmacia, remisiones a otras instituciones, «qué significa NEDOCS», fórmula DAX, «hazme un reporte», «dame un resumen», «pq», «la 2». Sin datos de pacientes.

## Phase 2: Foundational

- [x] T002 Pruebas que fallan en `tests/portero/test_portero_alcance.py`: `Clasificacion.detalle` con valor por defecto; `clasificar(..., original=...)` usa el original para el alcance; los 5 ejemplos del usuario (SC-003).
- [x] T003 Crear `src/chatbot/portero_alcance.py` (normalización con jerga, plantillas vagas, marcadores, anulaciones, sin sentido) y conectarlo en `portero.clasificar` tras la charla y la lista de bloqueo.

## Phase 3: User Story 1 + 2 — Categorías generales y petición vaga (P1) 🎯 MVP

- [x] T004 [US1] Pruebas: cobertura por categoría de los `F*` solo con reglas (≥80 % por categoría, ≥90 % global); anulaciones por palabra del catálogo fuera del marcador (con tipeo), periodo, número y propio hospital; tolerancias de noticias/clima/deportes (periodo) y cálculo (número).
- [x] T005 [US2] Pruebas: plantillas vagas solo de mensaje entero; «hazme un reporte de» → vago y «hazme un reporte de la ocupación de camas», «hazme un reporte», «dame un resumen» → `None`.
- [x] T006 [US1/US2] Implementar marcadores y plantillas hasta verde.

## Phase 4: User Story 3 — Clínico y otra institución (P1)

- [x] T007 [US3] Pruebas: clínicos con dosis/edad/periodo → `clinico`; antibióticos/farmacia del banco → `None`; otra institución → `otra_institucion`; remisiones, «del/al/desde» antes del nombre, primera persona plural y mención del propio hospital → `None`.
- [x] T008 [US3] Implementar marcadores clínicos (verbo de consejo + contexto clínico, síntomas en primera persona, dosis para una persona) y de institución (lista de instituciones + «hospital/clínica san|santa …» + «otros hospitales»).

## Phase 5: User Story 4 — Sin sentido (P2)

- [x] T009 [US4] Pruebas y regla: vacío/solo signos, risa, tecleo al azar → `sin_sentido`; «pq», «x», «q», «bn», «la 2», siglas del catálogo → `None`.

## Phase 6: Blindaje — 0 falsos positivos

- [x] T010 Prueba `test_barrido_todos_los_bancos_sin_intercepciones` en `tests/portero/test_portero_alcance.py`: banco_real, holdout, holdout2 (con `turnos_extra`), multiturno, `tests/eval/questions.json` (todos los turnos `user`), `tests/eval/diccionario_preguntas.json` y `N*`/`D*` del banco → `None`, con el texto original y con el texto normalizado por `normalize_question`. Si falla, corregir la regla general, nunca añadir la frase como excepción.

## Phase 7: Similitud MiniLM de alcance

- [x] T011 Pruebas con modelo falso: la similitud de alcance actúa solo sobre umbral y margen, no salta anulaciones, solo 3–12 palabras, modelo que falla → solo reglas.
- [x] T012 Implementar `EJEMPLOS_ALCANCE` y `SimilitudPortero.mejor_alcance` (margen frente a referencias de dominio y ejemplos de charla); calibrar con MiniLM real en `tests/portero/test_portero_minilm.py` (banco + banco_real) y barrido ciego (holdouts, multiturno, eval, diccionario) = 0.

## Phase 8: Motor y respuestas

- [x] T013 Pruebas de `responder` por grupo (vaga incluye capacidades; clínico dice que no da recomendaciones clínicas; todas dicen qué sí puede hacer).
- [x] T014 Pruebas en `tests/portero/test_motor_portero.py`: «cuéntame un chiste» → ruta `conversacion`, `conversation_kind = "fuera_de_alcance/entretenimiento"`, `stage`, razonamiento «Mensaje fuera de alcance», sin búsquedas ni DAX; seguimiento intacto tras un turno fuera de alcance; contrapregunta pendiente → no actúa; «receta de arepas» se clasifica aunque el normalizador la cambie a «áreas».
- [x] T015 Cambio mínimo en `src/chatbot/query_engine.py` `_portero_turn`.

## Phase 9: Verificación

- [x] T016 Suites `tests/portero` y `tests/routing` en verde; `tests.feedback.test_registro` sin fallos.
- [ ] T017 Con permiso del usuario: bancos reales contra Power BI (`tests.real.correr_todo`) sin cambios de resultado; `graphify update .` al integrar.

## Resultados (2026-11-10)

- Banco `F*` solo reglas: 127/128 (vaga 16/16, cálculo 11/11, noticias 10/10, clima 8/8, recetas 8/8,
  deportes 8/8, entretenimiento 10/10, programación 7/7, redacción 10/10, conocimiento 7/8, clínico 13/13,
  otra institución 9/9, sin sentido 10/10). Único fallo: «quien escribió cien años de soledad» (periodo «años»).
- Falsos positivos: 0 en 574 textos reales (todos los bancos + evaluador + diccionario, sin los rechazos
  etiquetados), 0 en los 80 `N*` y 74 `D*`, con y sin MiniLM; barrido extra de ~4.900 literales de `tests/`:
  solo rechazos ya etiquetados y fragmentos de código.
- Rechazos etiquetados en los bancos (positivos ciegos): holdouts 4/6 antes de generalizar «mejor X para Y»
  (clínico) y «buscarv» (ofimática), 6/6 después; evaluador `g_fuera_alcance` 6/6 de los que no resuelve el motor.
- Ciego nuevo (43 frases no vistas): 34/43 antes de ajustar; 40/43 tras patrones generales (no ciego ya).
- Similitud: solo 7 preguntas reales llegan «limpias»; ninguna supera ni 0.70/0.05. Se fija 0.80/0.20.

## Dependencies & Execution Order

Phase 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9. T010 se corre tras cada fase con reglas nuevas.

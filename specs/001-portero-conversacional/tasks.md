---
description: "Tareas del portero conversacional"
---

# Tasks: Portero conversacional

**Input**: `specs/001-portero-conversacional/` (spec, plan, research, data-model, contracts, quickstart) · Plan TDD detallado: `docs/superpowers/plans/2026-11-09-portero-conversacional.md`

**Tests**: obligatorios (regla del proyecto: superpowers test-driven-development). Cada prueba se escribe y se ve fallar antes de implementar.

**Comando**: `.venv\Scripts\python.exe -X utf8 -m unittest <módulo>`. Tras cada fase con código: `graphify update .`.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Crear paquete de pruebas `tests/portero/__init__.py` (vacío)
- [x] T002 Crear `tests/portero/banco_portero.json` con formato `{"version": 1, "casos": [{"id", "texto", "esperado"}]}` (data-model.md): ≥60 casos `C*` con `esperado` = `"tipo/subtipo"` tomados de research.md D6 (con tipeos y signos) y ≥60 casos `D*` con `esperado: null` (seguimientos cortos, respuestas a contrapregunta «ninguna», «sí», «la primera», «la 2», «listo», «ok», «dale», «perfecto», saludo + pregunta, palabras sueltas de dominio, toda la lista de bloqueo de research.md D4, «ayuda con las cirugías»). Sin datos de pacientes.

## Phase 2: Foundational (bloquea todas las historias)

- [x] T003 Escribir pruebas que fallan en `tests/portero/test_portero.py`: `normalizar` (tildes, signos, mayúsculas, espacios), `bloqueado_por_guardas` (`"hola 2025"`→`"numero"`, `"buenas, en octubre"`→`"periodo"`, `"buenas, ocupación"`→`"dominio"` con vocab que contiene «ocupacion», 9+ palabras →`"largo"`, `"¿cómo estás hoy?"`→`None`), `vocabulario_dominio(PROJECT_ROOT)` no vacío y sin «hola»/«gracias»/«ayuda»
- [x] T004 Implementar en `src/chatbot/portero.py`: `@dataclass(frozen=True) Clasificacion(tipo, subtipo, confianza, motivo)` con `tipo` ∈ `charla`·`identidad`·`capacidades`, `subtipo` ∈ `saludo`·`agradecimiento`·`despedida`·`estado`·`identidad`·`capacidades`, `motivo` ∈ `regla`·`similitud`; `normalizar`; `bloqueado_por_guardas` (motivos `numero`·`periodo`·`dominio`·`largo`); `vocabulario_dominio(project_root)` = claves de `vocabulary_for(root).targets` normalizadas menos palabras conversacionales, `frozenset()` si falla; lista de bloqueo de research.md D4
- [x] T005 Correr `tests.portero.test_portero` → PASS; commit

## Phase 3: User Story 1 — Saludar y recibir respuesta natural (P1) 🎯 MVP

**Goal**: charla (saludo, agradecimiento, despedida, estado) respondida sin búsquedas.
**Independent Test**: «hola», «¿Cómo estás hoy?», «gracias», «chao» → ruta `conversacion`, 0 DAX, sin llamadas al buscador.

- [x] T006 [US1] Pruebas que fallan en `tests/portero/test_portero.py`: `test_saludos_basicos` (subtipos `saludo`, `estado`, `agradecimiento`, `despedida`, `motivo == "regla"`), tipeos («holaa», «grax», «graciass»), `test_banco_portero_cobertura_reglas` (aciertos ≥ 0.75 de los `C*`), `test_banco_portero_sin_falsos_positivos` (todos los `D*` → `None`, lista ids fallidos)
- [x] T007 [US1] Implementar reglas de coincidencia completa (research.md D6) con tipeo ≤1 en palabras de ≥4 letras y `clasificar(texto, vocabulario_dominio=frozenset(), similitud=None)` en `src/chatbot/portero.py`; «listo»/«ok»/«si»/«no»/«ninguna»/«dale»/«perfecto» solos → `None`
- [x] T008 [US1] Pruebas que fallan para `responder` de charla en `tests/portero/test_portero.py` (saludo/estado incluyen ejemplo de pregunta; agradecimiento «Con gusto…»; despedida breve) e implementar `responder(c, datos, documentacion) -> str` para `charla` en `src/chatbot/portero.py` (textos del plan, Task 2)
- [x] T009 [US1] Pruebas que fallan en `tests/portero/test_motor_portero.py` con `tests.sim.harness`: `test_hola_responde_sin_buscar` (ruta `conversacion`, buscador falso sin `search*`, 0 DAX, el razonamiento contiene «Mensaje conversacional» — FR-009), `test_portero_que_lanza_no_tumba_el_turno`, `test_sin_rag_answer_engine_usa_solo_reglas`
- [x] T010 [US1] Conectar en `src/chatbot/query_engine.py` `process()` (~L6576): solo `top_level` y sin `_pending_query_plan`/`_pending_dashboard_clarification`/`_pending_master_metric`/`awaiting_clarification`/`_applying_deferred` (comprobar antes de borrar `_deferred_context_message`); dentro de `_traced` con `_think("Mensaje conversacional", ...)`; resultado `{"status": "success", "route": "conversacion", "answer", "conversation_kind", "question"}`; sin `_record_turn` ni `_last_success`; excepción → flujo normal; vocabulario y similitud perezosos por motor
- [x] T011 [P] [US1] `app.py` `get_display_answer` (~L271): `route == "conversacion"` → `result["answer"]`, sin bloque de informe/métrica
- [x] T012 [P] [US1] `src/feedback/registro.py` `_respuesta` (~L253): `estricto=result.get("route") not in ("rag", "conversacion")`; prueba `test_ruta_conversacion_conserva_lista` en `tests/feedback/test_registro.py`
- [x] T013 [US1] Correr `tests.portero.test_portero tests.portero.test_motor_portero tests.feedback.test_registro` → PASS; commit; `graphify update .`

## Phase 4: User Story 2 — Saber qué puede hacer el asistente (P1)

**Goal**: identidad y capacidades; capacidades desde el catálogo en dos grupos.
**Independent Test**: «¿qué puedes hacer?» lista tableros del catálogo de fixtures en «**Datos**»/«**Documentación**» sin duplicados; «¿quién eres?» dice que no da recomendaciones clínicas.

- [x] T014 [P] [US2] Pruebas que fallan en `tests/portero/test_portero.py`: `clasificar("¿quién eres?").tipo == "identidad"`, `clasificar("¿qué puedes hacer?")`/`"ayuda"` → `capacidades`, `"ayuda con las cirugías"` → `None`; `test_catalogo_dos_grupos` (modelo «CIRUGIAS», docs «CIRUGIAS» y «TRIAGE» → `(["Cirugias"], ["Triage"])`, «DICCIONARIO X» excluido), `test_catalogo_sin_router` → `([], [])`, `test_respuesta_capacidades` (grupo vacío omitido; ambos vacíos → genérico), `test_respuesta_identidad_dice_no_clinico`
- [x] T015 [US2] Implementar reglas de identidad/capacidades, `catalogo_tableros(router)` («un tablero en ambos va solo en `datos`»; «se excluyen los que empiezan por "DICCIONARIO"»; deduplicados, orden alfabético, formato título) y textos de `responder` en `src/chatbot/portero.py`
- [x] T016 [US2] Prueba `test_que_puedes_hacer_lista_tableros_del_catalogo` en `tests/portero/test_motor_portero.py` y pasar `self.source_router` a `catalogo_tableros` en la conexión de `src/chatbot/query_engine.py`
- [x] T017 [US2] Correr `tests.portero.test_portero tests.portero.test_motor_portero` → PASS; commit

## Phase 5: User Story 3 — Las preguntas reales nunca se desvían (P1)

**Goal**: 0 intercepciones de preguntas reales; contrapreguntas y seguimientos intactos.
**Independent Test**: barrido de todos los bancos reales y casos `D*` → `None`.

- [x] T018 [P] [US3] `test_barrido_bancos_reales_sin_intercepciones` en `tests/portero/test_portero.py`: `pregunta` de `tests/real/banco_real.json`, `banco_holdout.json`, `banco_holdout2.json`, `turnos_extra` (quitar prefijo `texto: `) y `entrada` de los `turnos` de `banco_multiturno.json` → `None`. Holdouts/multi-turno: si fallan, corregir la regla general, nunca añadir la frase
- [x] T019 [P] [US3] Pruebas en `tests/portero/test_motor_portero.py`: `test_no_actua_con_contrapregunta_pendiente` («ninguna», «gracias» con contrapregunta abierta), `test_gracias_no_rompe_seguimiento` (dato → «gracias» → «¿y en octubre?» = seguimiento del mismo indicador), `test_saludo_mas_pregunta_va_a_datos`
- [x] T020 [US3] Corregir lo que falle en `src/chatbot/portero.py` / `src/chatbot/query_engine.py`; correr → PASS; commit

## Phase 6: User Story 1 (ampliación) — Variantes por similitud (FR-011)

- [x] T021 [US1] Pruebas que fallan con modelo falso en `tests/portero/test_portero.py`: `test_similitud_intercepta_solo_sobre_umbral_y_margen`, `test_similitud_no_salta_guardas`, `test_similitud_no_aplica_a_1_2_palabras`, `test_modelo_que_falla_deja_solo_reglas`
- [x] T022 [US1] Implementar `SimilitudPortero(modelo, umbral=UMBRAL, margen=MARGEN)` y `.mejor(texto)` en `src/chatbot/portero.py`: `normalize_embeddings=True`, producto punto, ejemplos y negativos precalculados; solo 3–8 palabras; `UMBRAL = 0.80`, `MARGEN = 0.20` iniciales; margen contra el máximo de dominio; `encode` que falla → inactiva
- [x] T023 [US1] `tests/portero/test_portero_minilm.py` con MiniLM real (skip si no carga): banco ≥90 % y 0 FP; `clasificar` con similitud < 50 ms de media por mensaje tras precalcular (SC-005); calibrar barriendo umbral 0.70–0.85 (paso 0.025) y margen 0.10–0.30 SOLO con banco del portero + `banco_real`, colchón 0.05; anotar valores y cifras en el docstring de `src/chatbot/portero.py`; luego barrido ciego una vez
- [x] T024 [US1] Conectar la similitud en `src/chatbot/query_engine.py` con `rag_answer_engine.retriever.model` (si no existe → `None`); correr todo `tests.portero` → PASS; commit; `graphify update .`

## Phase 7: Polish & verificación

- [x] T025 Regresión: `tests.sim.test_smoke`, `tests.feedback` y la suite unitaria existente → sin fallos nuevos
- [x] T026 Simulador con las 5 frases del caso real → ruta `conversacion`, 0 DAX; comprobar que el saludo aparece en `export_conversation_markdown` de `src/chatbot/conversation_export.py` con los mensajes de la app (FR-008); mostrar respuestas al usuario
- [x] T027 Revisión de seguridad/integridad y pruebas adversariales por subagentes; revisión final de la rama (superpowers requesting-code-review)
- [ ] T028 Con permiso del usuario: bancos reales (`$env:POWERBI_AUTH="device_code"; .venv\Scripts\python.exe -X utf8 -m tests.real.correr_todo`) y golden master (`-m tests.resolution.test_golden`) sin cambios de resultado

## Dependencies & Execution Order

- Phase 1 → Phase 2 → US1 (Phase 3) → US2 (Phase 4) → US3 (Phase 5) → Phase 6 → Phase 7.
- US2 reutiliza la conexión de T010; US3 prueba el conjunto de US1+US2; Phase 6 añade la similitud sobre reglas ya seguras.
- Paralelo: T011 ∥ T012 (archivos distintos); T018 ∥ T019.
- Constitución del proyecto sin rellenar: se usan como compuertas las reglas de CLAUDE.md (opcional más adelante: `/speckit-constitution`).

## Implementation Strategy

MVP = Phases 1–3 (charla por reglas conectada al motor). Luego capacidades (US2), blindaje (US3) y similitud (Phase 6). Mapeo con el plan superpowers: Task 1 ≈ T001–T007+T018; Task 2 ≈ T008, T014–T015, T021–T023; Task 3 ≈ T009–T012, T016, T019, T024; Task 4 ≈ Phase 7.

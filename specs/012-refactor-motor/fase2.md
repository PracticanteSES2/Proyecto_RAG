# Fase 2 — Partir `src/chatbot/query_engine.py` en mixins (guion listo para ejecutar)

Estado: **preparada, sin ejecutar**. Se ejecuta cuando los agentes que hoy editan `query_engine.py`
(portero, progreso, conversación, LLM) hayan integrado en `desarrollo`. Patrón ya probado en
`src/semantic/resolucion/` (README en `src/semantic/README_motor.md`). Plan general en
`docs/ARQUITECTURA.md` §10.

Medido el 2026-11-11 sobre `desarrollo` 1ac7ed5 (con la memoria por sesión integrada) + esta rama:
**7.490 líneas, `class QueryEngine(SesionMotorMixin)`, 174 métodos**; `_process` mide 735 líneas. La memoria por
sesión ya usa el patrón: el estado de conversación vive en `src/chatbot/sesion_motor.py` (`SesionMotorMixin`) y los
puntos de entrada públicos llevan `@con_sesion` (`select_clarification_option`, `process`).

## Reglas de la fase

1. **Mover sin cambiar.** Cada método pasa al mixin con su texto exacto (incluidos los atributos de clase
   que usa, como `_ANAPHORA_RE`). Nada de renombrar, reordenar parámetros ni «arreglar de paso».
2. **Un paso = un commit = un golden master.** Orden de lo más aislado a lo más acoplado (tabla de abajo).
3. **`QueryEngine` sigue siendo la misma clase pública**: `class QueryEngine(SesionMotorMixin, TrazasMixin, …)`
   (`SesionMotorMixin` queda primero, como hoy)
   en `src/chatbot/query_engine.py`. Las pruebas usan ~36 privados (`engine._query_plan_failure`,
   `engine._trace_plan`, …): siguen existiendo por herencia.
4. **Ningún mixin importa `src.chatbot.query_engine`** (ciclo). Cada mixin importa solo lo que usa.
5. **Ningún nombre repetido entre mixins** (el MRO escogería uno en silencio): se verifica con el guion B.
6. Meta: `query_engine.py` < 400 líneas (imports, `__init__`, `process`, `close` y la lista de mixins);
   cada mixin < 800 (aviso a 400).

## Paso 0 (antes de mover): normalización de `query_engine`

`QueryEngine._normalize_text` y la función local `plain` (dentro de `_options_matching_range`, con su `import unicodedata` local) son
equivalentes a `src.comun.texto.normalizar` y `src.comun.texto.plegar` (oráculos `o_business_filter` /
`o_ranking` y `o_fold_lento` de `tests/comun/test_texto.py`). Sustituir sus cuerpos por
`return normalizar(value)` / `plegar(value)` (conservar los nombres: las pruebas y los mixins los llaman) y el
bloque de `_anaphora` que pliega a mano por `plegar(...)`. Golden master idéntico. Esto quita
`import unicodedata` de `query_engine.py` antes de partirlo.

## Pasos (rangos del 2026-11-11, tras integrar la memoria por sesión; RECALCULARLOS con el guion A antes de cada paso)

| Paso | Módulo `src/chatbot/consulta/` | Clase | Líneas hoy | Contenido |
| --- | --- | --- | --- | --- |
| 1 | `trazas.py` | `TrazasMixin` | 174–506 | `_think`, `_activity`, `set_progress_listener`, `_on_powerbi_query`, `_traced`, `_plan_budget_response`, `_exploration_text`, `_server_snapshot`, `_think_degradation`, `_think_exploration`, `_metric_pages`, `_metric_where`, `_candidate_line`, `_filter_line`, `_trace_plan`, `_trace_dax` |
| 2 | `ejecucion_dax.py` | `EjecucionDaxMixin` | 512–682 | `_model_schema`, `_unknown_columns_message`, `_execute_dax`, `_DIMENSION_ALTERNATIVES`, `_dimension_listing`, `_unknown_columns_response` |
| 3 | `agrupado.py` | `AgrupadoMixin` | 1745–1989 | `_row_value`, `_format_grouped_answer`, `_BLANK_GROUP_SHARE`, `_group_cell`, `_mostly_blank_group`, `_blank_group_response`, `_is_blank_value`, `_apply_ranking`, `_data_until`, `_empty_plan_result` |
| 4 | `metrica_legada.py` | `MetricaLegadaMixin` | 1527–1739 | `_execute_legacy_metric` (213 líneas: partirla queda para después de la fase) |
| 5a | `maestra_contrapregunta.py` | `MaestraContrapreguntaMixin` | 688–1203 | `_normalize_text`, `_looks_like_new_question`, `_extract_value`, `_build_master_clarification_question`, `_match_clarification_option`, `_handle_pending_master_clarification`, `_resolve_filters`, `_get_master_clarification_options` |
| 5b | `maestra.py` | `MaestraMixin` | 1209–1521 | `_execute_master_metric` (313 líneas) |
| 6 | `plan.py` | `PlanMixin` | 1991–2412 | `_execute_query_plan`, `_listable_choice`, `_drop_listed_entity`, `_plan_explains_question`, `_listable_by_table`, `_detail_listing` |
| 7 | `opciones.py` | `OpcionesMixin` | 2418–3158 | `_CLARIFICATION_*`, `_clarification_context`, `_short_text`, `_choice_summary`, `_describe_choices`, `_finalize_choices`, `_TECHNICAL_LABEL_RE`, `_readable_label`, `_name_words`, `_equivalent_names`, `_same_computation`, `_named_table_words`, `_related_candidates`, `_build_clarification_choices`, variantes (`_VARIANT_MARKERS` … `_collapse_measure_variants`), rangos (`_RANGE_UNITS` … `_drop_dominated_options`), `_AGGREGATION_TEXT` … `_equivalent_measure_key`, `_NONE_LABEL`, `_NONE_CAPTION`, `_single_option_prompt` |
| 8a | `contrapregunta.py` | `ContrapreguntaMixin` | 3160–3644 | `_clarification_response`, `_query_plan_clarification`, `_search_alternatives`, `_unresolved_words_clarification`, `_run_selected_metric`, `select_clarification_option`, `_select_clarification_option`, `_match_query_plan_choice`, `_LOCATION_REPLY`, `_choice_by_location`, `_board_named_in_reply`, `_search_in_named_board`, `_board_phrase` |
| 8b | `respuestas_contrapregunta.py` | `RespuestasContrapreguntaMixin` | 3646–4110 | `_NONE_REPLY`, `_is_none_reply`, `_FULL_QUESTION_RE`, `_is_new_full_question`, `_REPLY_WORDS`, `_reply_adds_new_request`, `_defer_context_message`, `_MONTH_WORDS`, `_continue_query_plan`, `_qualifier_prompt`, `_resolution_prompt`, `_answer_single_option`, `_query_plan_failure`, `_examples_text`, `_metric_not_resolved_response` |
| 9 | `compuestas.py` | `CompuestasMixin` | 4117–4672 | `_fmt_es`, `_composite_*`, `_filter_identity`, `_own_filters_text`, `_execute_composite`, `_group_key`, `_composite_table_rows`, `_execute_composite_table`, `_handle_composite`, `_run_selected_composite`, `_run_query_plan` |
| 10 | `intencion.py` | `IntencionMixin` | 4675–5000 | `_INTENT_LLM_STAGES`, `_intent_encoder`, `_intent_llm_plan`, `_PAGES_IN_NOTE`, `_note_same_measure_pages`, `_FILTERED_PAGES_IN_NOTE`, `_same_measure_note`, `_pages_with_own_filters`, `_FOLLOWUP_MAX_WORDS`, `_BARE_FOLLOWUP_*`, `_is_temporal_filter`, `_pages_without_metrics`, `_descriptive_reason`, `_fallback_has_analytic_intent`, `_has_pending_clarification`, `_remember_success` |
| 11 | `seguimientos.py` | `SeguimientosMixin` | 5005–5668 | `_ANAPHORA_RE` … `_FOLLOWUP_FILLER`, `_parse_number`, `_anaphora`, `_same_number`, `_CONTEXT_WORDS`, `_without_period_phrases`, `_named_metric_words`, `_explained_by_plan`, años y periodo anterior, `_qualifier_swap_plan`, `_top_of_previous_group`, `_followup_plan` (246 líneas), `_note_breakdown_of_previous`, `_rewrite_request` |
| 12a | `contexto.py` | `ContextoMixin` | 5684–6189 | `_CONTEXT_SHORT_WORDS` … `_SAME_PERIOD_LAST_YEAR`, `_context_llm_provider`, interpretación, `_previous_turn`, `_run_followup`, tema y tablero (`_topic_subject` … `_topic_plan`), `_contextual_special`, `_SUBJECTLESS_WORDS` … `_replace_reference` |
| 12b | `comparacion.py` | `ComparacionMixin` | 6191–6621 | `_comparison_turn`, `_note_variation`, `_shift_filters_one_year`, `_return_to_topic`, `_numeric_after_documentation`, `_contextual_generic`, `_llm_rewrite_turn`, `_process_turn`, `_process_typed_turn`, `_with_interpretation`, `_check_requester_filter` |
| 13 | `portero.py` (en `consulta/`) | `PorteroMixin` | 6664–6746 | `warm_up_portero`, `_portero_resources`, `_portero_turn`, `_discard_stale_dashboard_clarification` — solo cuando el agente del portero haya cerrado |
| 14 | `turno.py` | `TurnoMixin` | 6748–7482 | `_process` (735 líneas): **último**. Primero se mueve entero (commit + golden); luego se parte en etapas con nombre (pendientes → seguimiento → contexto → tipo → plan → ejecución), cada una < 80 líneas, un commit y un golden por etapa |

Queda en `query_engine.py`: imports, `class QueryEngine(SesionMotorMixin, <mixins>)`, `__init__` (24–127),
`_RAG_HISTORY_TURNS`, `_call_rag`, `_accepts_history`, `_record_turn` (130–168), `process` (6623–6662, con
`@con_sesion`) y `close` (7488–7490). `reset` y `conversation_history` ya salieron a `SesionMotorMixin`.
`select_clarification_option` (3371, `@con_sesion`) va con su paso (8a) **conservando el decorador**.

## Cómo ejecutar cada paso

1. `git merge desarrollo` y recalcular rangos con el **guion A**. Si un método cambió de vecindario, se
   respeta su responsabilidad, no el número de línea.
2. Buscar parches de módulo: `rg "src\.chatbot\.query_engine\." tests tools` (hoy: ninguno). Si aparece
   `patch("src.chatbot.query_engine.X")` y `X` se usa dentro del método movido, el parche dejaría de surtir
   efecto: cambiar la ruta del parche al módulo del mixin en el mismo commit.
3. Mover con el **guion C** (corta el texto literal de los métodos y atributos de clase listados y los pega en
   `class <Mixin>:` dentro de `src/chatbot/consulta/<modulo>.py`).
4. Imports del mixin: `ruff check --select F821,F401 src/chatbot/consulta/<modulo>.py src/chatbot/query_engine.py`
   hasta cero (añadir al mixin lo que falte; quitar de `query_engine.py` lo que ya no use).
5. Añadir el mixin a la lista de bases de `QueryEngine` (orden: el del paso; los mixins no se pisan).
6. **Guion B** (colisiones y cobertura) en verde.
7. Pruebas del paso (columna «Pruebas» abajo) + `python -X utf8 -m tests.eval.test_eval`.
8. Golden master (ver abajo). Idéntico → commit `Fase 2 paso N: <Mixin> a src/chatbot/consulta/<modulo>.py`.
9. `python -X utf8 -m tools.doctor --verificar`; al final de la fase, `--actualizar-linea-base` (sin `--forzar`;
   si el doctor ve huellas «nuevas» solo por el cambio de archivo de funciones largas ya existentes, se
   justifica en el commit y se sube con `--forzar`, como prevé `docs/calidad/doctor.md`).

| Paso | Pruebas mínimas (además de `tests.eval.test_eval` y golden) |
| --- | --- |
| 1 trazas | `tests/export`, `tests/stability/test_stability`, `tests/progreso` |
| 2 ejecución DAX | `tests/detalle`, `tests/resolution/test_tmdl_real`, `tests/routing` |
| 3 agrupado | `tests/resolution/test_grouping`, `tests/redaccion` |
| 4 métrica legada | `tests/resolution/test_resolution`, `tests/resolution/test_indicador*` |
| 5 maestra | `tests/clarification`, `tests/resolution/test_filtros_tablero`, `tests/resolution/test_values` |
| 6 plan | `tests/detalle`, `tests/resolution/test_r*` |
| 7–8 opciones y contrapregunta | `tests/clarification`, `tests/selection`, `tests/resolution/test_contrapreguntas`, `test_r2_contrapreguntas` |
| 9 compuestas | `tests/resolution/test_r3`, `test_r9`, `tests/redaccion` |
| 10 intención | `tests/resolution/test_intencion_llm`, `tests/routing` |
| 11–12 seguimientos y contexto | `tests/context`, `tests/periods`, `tests/resolution/test_conversaciones_*` |
| 13 portero | `tests/portero` |
| 14 `_process` | todas las anteriores |

Corredor: las suites de `tests/` mezclan `unittest` y scripts (`python -m tests.<área>.<módulo>`); las que
levantan la app simulada usan Qdrant local en `%TEMP%`: correrlas con `SIM_CACHE_DIR` propio por proceso o en
serie (dos procesos sobre la misma copia fallan con «already accessed by another instance of Qdrant»).

## Golden master

- **Foto del día**: antes del primer paso, en un worktree aparte en el commit base,
  `SIM_CACHE_DIR=<carpeta propia> python -X utf8 -m tests.resolution.golden.capture --out <tmp>/foto_base --quiet`
  (~40 min). La foto versionada (`tests/resolution/golden/foto`) puede ser de otro día y diferir en fechas
  relativas: comparar contra la foto del mismo día.
- **Por paso**: `python -X utf8 -m tests.resolution.golden.capture --out <tmp>/foto_pasoN --compare <tmp>/foto_base --quiet`
  (o `GOLDEN_BANCOS=eval` para una pasada rápida intermedia y los tres bancos antes de cada commit).
- Una sola diferencia detiene la fase: se revierte el paso, no se regenera la foto.

## Guiones

**A. Rangos actuales por método**

```python
import ast; t = open("src/chatbot/query_engine.py", encoding="utf-8").read()
c = next(n for n in ast.parse(t).body if isinstance(n, ast.ClassDef) and n.name == "QueryEngine")
for m in c.body:
    nombre = m.name if hasattr(m, "name") else ast.unparse(m.targets[0]) if isinstance(m, ast.Assign) else "?"
    print(f"{m.lineno:5d}-{m.end_lineno:5d} {nombre}")
```

**B. Colisiones entre mixins y cobertura**

```python
import inspect
from src.chatbot.query_engine import QueryEngine
vistos = {}
for base in QueryEngine.__mro__[1:-1]:
    for nombre in vars(base):
        if not nombre.startswith("__"):
            assert nombre not in vistos, f"{nombre} en {vistos[nombre]} y {base.__name__}"
            vistos[nombre] = base.__name__
propios = {n for n in vars(QueryEngine) if not n.startswith("__")}
assert not propios & set(vistos), propios & set(vistos)
print(len(vistos), "miembros en mixins;", len(propios), "en QueryEngine")
```

**C. Mover métodos sin tocarlos**: localizar con `ast` (`lineno` del primer decorador o de la línea `def`/de la
asignación, `end_lineno`), cortar ese bloque literal (incluidas las líneas de comentario inmediatamente
anteriores que pertenezcan al bloque) y pegarlo en el mixin conservando la sangría de 4 espacios. Después,
`git diff --stat` debe mostrar el mismo número de líneas borradas en `query_engine.py` que añadidas en el mixin
(más imports y la cabecera de la clase), y `git diff --color-moved` no debe mostrar líneas modificadas.

## Riesgos

- `self.__class__` / `type(self)` dentro de métodos: siguen siendo `QueryEngine` (los mixins no se instancian solos).
- Atributos de clase consultados como `QueryEngine._X` desde fuera: se resuelven por herencia; verificar con
  `rg "QueryEngine\._"`.
- Imports perezosos dentro de métodos (`from src.chatbot import contextual_rewriter`): se mueven con el método.
- `@con_sesion` (de `src.chatbot.sesion_motor`) envuelve los puntos de entrada: el mixin que reciba un método
  decorado importa `con_sesion`; el guion C debe cortar desde la línea del decorador. Los mixins nuevos NO deben
  definir `__init__` ni atributos de estado de conversación (viven en `EstadoConversacion`, por sesión).
- Otros agentes: la fase toca un archivo muy concurrido; ejecutarla en una ventana sin ramas abiertas que lo editen.

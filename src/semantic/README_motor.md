# Motor de resolución (pregunta → plan → DAX → respuesta)

Mapa del flujo real tras 8 rondas de correcciones (r1–r8, auditoría del banco real y holdout) y de la
reorganización por etapas de `src/semantic/query_plan_builder.py` (rama `agente/refactor-motor`).

**Regla del refactor:** sin cambios de comportamiento. Se verifica con el *golden master*
(`tests/resolution/golden/`, `python -X utf8 -m tests.resolution.test_golden`): los tres bancos (simulador,
real y holdout) en el arnés realista con `--llm fake`, comparando por turno status, ruta, indicador, modelo,
filtros, agrupación, DAX normalizado, opciones de contrapregunta y respuesta.

## Estructura

`QueryPlanBuilder` (API pública intacta: `build`, `build_composite`, `looks_numeric`, `is_descriptive`,
`alternative_metrics`, `metric_words`, ... y los privados que usan `query_engine` y las pruebas) es ahora una
clase compuesta por *mixins*, uno por etapa. Los métodos se movieron **sin cambios** (solo
`QueryPlanBuilder._x` → `<Mixin>._x` en 5 llamadas a métodos estáticos). En `query_plan_builder.py`
quedan `__init__`, `build`, `_build_plan` (el orquestador), `_candidate_with_period`,
`_candidate_that_filters`, `_period_summary` y `_note`; también reexporta las funciones de `texto.py`
con los mismos nombres (`normalize_text`, `canonical_token`, `_alias_prefix`, `value_contradiction`...).

| Módulo (`src/semantic/resolucion/`) | Mixin | Etapa |
| --- | --- | --- |
| `texto.py` | (funciones) | 1. Normalizar: tokens, sinónimos, similitud, frases canónicas, dominios de valores |
| `tipo_pregunta.py` | `TipoPreguntaMixin` | 2. Clasificar el tipo: descriptiva / numérica / ranking de entidad / página con datos |
| `compuestas.py` | `CompuestasMixin` | 2. Compuestas: participación y coordinadas («X y Y») |
| `catalogo.py` | `CatalogoMixin` | Carga y enriquecimiento del catálogo (en `__init__`) |
| `tablero.py` | `TableroMixin` | 3. Elegir tablero y modelo |
| `indicador.py` | `IndicadorMixin` | 4. Elegir indicador: puntaje, sugerencias, indicador general, diccionario |
| `cobertura.py` | `CoberturaMixin` | 4. Cobertura de la pregunta y del periodo, desempates, nombres débiles |
| `homonimos.py` | `HomonimosMixin` | 4. Homónimos en varios tableros, palabras de las opciones |
| `calificativos.py` | `CalificativosMixin` | 4/5. Calificativos sin interpretar (otro indicador o valor aproximado) |
| `paginas.py` | `PaginasMixin` | 4. Páginas nombradas y contrapreguntas por página |
| `contrapregunta.py` | `ContrapreguntaMixin` | 4. Depuración final de opciones (`_refine_options`) |
| `dimensiones.py` | `DimensionesMixin` | 5/6. Dimensiones del indicador y relaciones |
| `filtros.py` | `FiltrosMixin` | 5. Filtros explícitos, implícitos y aproximados |
| `valores.py` | `ValoresMixin` | 5. Dominios de valores en Power BI (caché, precalentamiento) |
| `periodo.py` | `PeriodoMixin` | 5. Periodo y columna de fecha |
| `filtros_tablero.py` | `FiltrosTableroMixin` | 5. Filtros del visual/página/informe del indicador |
| `agrupacion.py` | `AgrupacionMixin` | 6. Agrupación, hermanos que se desglosan, ranking |

Para encontrar un método: `grep -n "def _nombre" src/semantic/resolucion/*.py`.

## Flujo real por etapas

### 0. Entrada (`src/chatbot/query_engine.py`)
- `QueryEngine.process` normaliza el lenguaje de chat UNA vez (`question_normalizer.normalize_question`:
  «x servicio», «q», tipeos contra el catálogo; r5, `tests/resolution/test_normalizacion.py`).
- `_process`: primero las contrapreguntas pendientes (`_continue_query_plan`, `_match_query_plan_choice`,
  `_select_clarification_option`), luego seguimientos y contexto (`_followup_plan`, `_contextual_special`).

### 1. Normalizar la pregunta
- `QueryPlanBuilder.build` → `canonical_phrases` (texto.py): sinónimos de frase, verbos progresivos y de
  distribución («cómo se distribuye») que no son indicador ni filtro.
- `_metric_business_question` (indicador.py) quita relleno, verbos de petición y el periodo;
  `_strip_board_mentions` (tablero.py) quita las palabras del tablero nombrado.

### 2. Clasificar el tipo
- `query_engine._dimension_listing` («lista de X» → valores de la columna; detail_list.py).
- `looks_numeric` / `is_descriptive` / `descriptive_reason` (tipo_pregunta.py; auditoría causa 6 y r5).
  Si no es numérica: analizador de intención (`intent_parser.py`) y RAG.
- `active_entity_question` / `_ranked_entity_metric` («qué antibióticos se están aplicando», r3 AB04).
- `build_composite` (compuestas.py): participaciones y coordinadas, antes del plan simple.

### 3. Elegir tablero y modelo
- `_source_context` (tablero.py) con `source_model_router.py`; `_refine_board_context`.
- Tablero nombrado sin ese indicador → `_named_board_rejection` (no se responde con otro tablero).

### 4. Elegir indicador (homónimos, cobertura, contrapreguntas)
- `_resolve_metric_flexible` → `_resolve_metric` (indicador.py): puntaje de nombre (`_phrase_score`),
  núcleo, peso de tokens, diccionario, `_general_indicator` (r2-indicador-2 BH09, r4 FC05/AC01),
  `_drop_priority_of_narrower_names`, `_break_metric_tie` (cobertura.py, r3 TU10),
  «cuántos X» → CANTIDAD/NÚMERO DE X y conteo implícito de identificador detrás (r7).
- Cobertura del periodo (`_metric_misses_period`, `_drop_uncovered_period`: r2, r5, r6 TU04).
- Página nombrada: `_named_page_refinement`, `_page_choices`, `_named_page_rejection` (paginas.py; r3 EP02).
- Homónimos: `_same_name_ambiguity`, `_homonyms_that_answer` (r2-contrapreguntas: solo compiten fuentes
  que responden la pregunta tal como está), `_homonym_tie_ambiguity` (r8 AI04).
- Calificativos: `_resolve_qualifiers`, `_qualifier_metric_switch`, `_promote_qualifier_metrics`.
- `_refine_options` (contrapregunta.py) depura las opciones del plan ambiguo; `_similar_name_ambiguity`.
- En `query_engine`: `_query_plan_clarification`, `_build_clarification_choices`, `_collapse_measure_variants`,
  `_drop_dominated_options`, `_unresolved_words_clarification`, `_resolution_prompt`,
  `_answer_single_option` (una sola opción razonable se responde: auditoría AI07), `option_describer.py`.

### 5. Filtros y periodo
- Dimensiones: `_metric_dimensions` / `_dimension_relation` (dimensiones.py).
- Periodo: `_periods_for_metric` → `_analyze_periods` (PeriodParser) y `_apply_temporal` /
  `_metric_date_fields` / `_best_date_field` (periodo.py; auditoría causa 3, r3 AI05).
- Filtros: `_detect_group_or_dimension_filter`, `_detect_explicit_dimension_filters`, `_resolve_value`,
  `_resolve_implicit_filter` / `_resolve_implicit_value` con `_spurious_value_reason` (auditoría causa 2),
  palabras de alcance `_scope_words`, tipo de medida `_measure_type_words`, `_counted_unit` (r2 FC04),
  `implied_words` (r5), `_fuzzy_qualifier_filters`.
- Filtros del tablero: `_apply_board_filter_context` al final de `build` (filtros_tablero.py; auditoría causa 1).

### 6. Agrupación y forma de respuesta
- `_detect_group_or_dimension_filter` (filtros.py), `_requested_group_tail`, `_group_field_in`,
  `_described_group_field` (agrupacion.py; auditoría TU12, r5), `_group_sibling_plan` (r2 BH18),
  `_detect_ranking`, `blank_group_alternative`.
- Forma: `answer_shape.py`, `detail_list.py`; en query_engine `_listable_choice`, `_detail_listing`.

### 7. Generar y validar el DAX
- `src/dax/query_plan_dax_generator.py`, `column_guard.py` (columnas contra el modelo),
  `query_engine._execute_query_plan` / `_execute_dax`.

### 8. Redactar
- `query_engine._format_grouped_answer`, `_empty_plan_result` («sin datos» con fecha de corte, r6),
  `_note_same_measure_pages`, `response_formatter.py`, `answer_synthesizer.py`, `business_terms.py` (r2-redaccion).

## Reglas duplicadas o contradictorias (no se cambiaron)

Encontradas al mover el código. Cambiarlas cambia el comportamiento (golden master), así que solo se
documentan con una propuesta; cada una debe ir en una ronda propia con su prueba y el banco real.

1. **Dos `_CALENDAR_TABLE_RE` en la misma clase.** La primera (filtros del tablero, estrecha: calendario,
   fecha, dates, LocalDateTable) nunca se usaba: la segunda (dimensiones, que además acepta «fechas»,
   «dim fecha», «medidas», «measures») la reemplazaba al crear la clase. `_visual_filter_clauses` y
   `_tables_filtering_metric` usan, sin saberlo, la ancha: una tabla «Medidas» se trata como calendario
   al decidir si un filtro de visual aplica. *Hecho:* se borró la primera (código muerto, sin cambio).
   *Propuesta:* decidir si los filtros del tablero deben excluir «Medidas» y, si no, separar dos nombres.
2. **Dos listas de terminaciones verbales `_VERB_ENDINGS`** con el mismo nombre: la de módulo (texto.py,
   conjugaciones y gerundios, para `_derived_noun_match`) y la de clase (cobertura.py, `aron/ieron/aban/
   ando/iendo`, para `_looks_like_verb`); además `_FINITE_VERB_ENDINGS`, `_PARTICIPLE_ENDINGS`,
   `COMMON_VERB_WORDS`, `_reflexive_verbs` (homonimos.py) y `request_phrases.py`. «¿Es verbo?» tiene
   al menos cuatro respuestas. *Propuesta:* un solo detector de verbos en texto.py con modos explícitos.
3. **Palabras de conteo con tres expresiones distintas:** `_COUNT_WORDS_RE` (indicador.py: «cuanto/
   cuanta» en singular y «numero/cantidad del»), `_COUNT_QUESTION_RE` (homonimos.py: solo plural y «de»),
   `_COUNTED_NOUN_RE` (cobertura.py: «cuántos X»). «¿cuánto tiempo...?» es conteo para una y no para otra.
   *Propuesta:* una constante en texto.py y decidir el singular a propósito.
4. **Palabras de alcance «hospital» duplicadas:** `_SCOPE_PLACE_WORDS` (hospital, institucion, clinica) y
   `_SCOPE_GROUP_WORDS` (además «entidad»), ambas en filtros.py. «en la entidad» no es alcance para
   `_scope_words` pero sí para la agrupación. *Propuesta:* una sola lista.
5. **«Por X» detectado dos veces en `_build_plan`:** una regex fija (servicio/especialidad/asegurador/eps/
   sexo/estado/tipo) y `_requested_group_tail` + `_GROUP_TAIL_RE` (general, con «y su respectiva X»).
   La fija es un subconjunto histórico. *Propuesta:* quedarse con la general (puede cambiar mensajes
   de `requested_dimension`).
6. **Normalizadores de texto distintos:** `normalize_text` (texto.py) conserva «%»;
   `QueryEngine._normalize_text`, `intent_parser.normalize_text`, `source_model_router.normalize_text` y
   otros ~15 `normalize/fold` de `src/` lo quitan o difieren en detalles. «%OCUPACION» se compara distinto
   según la etapa. Lematizadores también: `canonical_token`, `_stem_token`, `_value_word_forms/_key`.
   *Propuesta:* un módulo común de normalización con una opción explícita para «%».
7. **Cambio de candidato con criterios distintos:** `_candidate_with_period` mira los 3 primeros
   candidatos (cuenta también los de puntaje bajo) y se detiene (`break`) con la primera distancia mayor
   a 0,25; `_candidate_that_filters` salta (`continue`) hasta probar 3 válidos con distancia ≤ 0,35 y
   exige un único plan. *Propuesta:* un solo «siguiente candidato» con la distancia como parámetro.
8. **Página principal con dos significados:** `_PRINCIPAL_PAGE_RE` (filtros_tablero.py: nombre de página
   «inicio/resumen/portada») y `_PAGE_PRINCIPAL_RE` (paginas.py: etiqueta «total/número/cantidad»).
   No es un error, pero los nombres se confunden. *Propuesta:* renombrar (`_HOME_PAGE_RE`, `_TOTAL_LABEL_RE`).
9. **Contrapreguntas en dos capas.** Las opciones se depuran en `QueryPlanBuilder` (`_refine_options`,
   `_prune_unrelated_options`, `_count_question_options`, `_options_named_by_question`) y otra vez en
   `QueryEngine` (`_build_clarification_choices`, `_collapse_measure_variants`, `_drop_dominated_options`,
   `_options_matching_range`). Las regresiones cruzadas de r4/r8 vienen de reglas que se pisan entre
   capas. *Propuesta:* mover la depuración del motor de chat al mixin `contrapregunta.py` en pasos con
   golden master.

**Unificado (equivalente de verdad, golden idéntico):** el bloque de «valores implícitos» de
`_build_plan` estaba copiado dos veces (3 y 2 vueltas); ahora es `_add_implicit_filters(rondas, ...)`.

## Estado del refactor

Rama `agente/refactor-motor` (desde `desarrollo` 1d4740a), sin push. Hecho el 2026-11-03:

| Paso | Commit |
| --- | --- |
| Golden master (foto de los 3 bancos) | `e04a729`, `e21c7af` |
| 1. texto.py (+ borrado del `_CALENDAR_TABLE_RE` muerto) | `e8d63a1` |
| 2–17. Un mixin por commit (catalogo … calificativos) | ver `git log` |
| 18. `_add_implicit_filters` (bloque duplicado) | `1de5f2c` |

Tamaños: `query_plan_builder.py` pasó de 12 274 líneas (646 KB) a 930 (48 KB). El código movido quedó en
17 módulos de `resolucion/` de 257 a 1 384 líneas (el mayor, `indicador.py`).

Validación tras el último paso: golden master **idéntico** (0 diferencias en los 411 turnos, ni siquiera
en `dax_log`); simulador 130/164 sin cambios por caso; todas las suites en verde (las de la lista del
HANDOFF + `tests/docs_md`).

Tiempo por turno (golden master, 411 turnos, corridas alternadas sin otra carga, mismo día): original
0,875 s y 1,148 s de media (p95 2,27 / 2,97 s); refactor 0,939 s y 0,881 s (p95 2,26 / 2,14 s). La
diferencia está dentro del ruido entre corridas del mismo código: no es más lento.

Cómo se movió (reproducible): un script AST toma los miembros de la clase por nombre (con sus comentarios
y decoradores), los copia tal cual a `class XMixin:` y genera los imports desde el encabezado de
`query_plan_builder.py`; una comprobación con `symtable` verifica que ningún nombre global quede sin
definir (así se detectó que `alternative_metrics` usa `_SUGGESTION_LIMIT` como valor por defecto y debía
ir con él en `indicador.py`).

Siguientes pasos sugeridos (cada uno con golden master): partir `indicador.py` y `filtros.py` (los
mayores); llevar la depuración de opciones de `query_engine` a `contrapregunta.py` (regla 9); resolver
las reglas 1–8 en rondas propias.

Golden master: la foto depende del día (periodos relativos, datos del simulador hasta ayer). Si se
compara otro día, primero se toma una foto nueva con el código de referencia y luego se compara.

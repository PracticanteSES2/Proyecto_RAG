# RETOMAR — auditoría del banco real (WIP)

Corrida analizada: `C:\Users\ad6708\Documents\banco_real_out_base_db2f1af\` (commit db2f1af, 21/70 = 30 %).
Código de `src/` citado: el de **db2f1af** (líneas de ese commit). Nada se ejecutó contra Power BI en esta fase.

## 1. Auditoría de la verdad y del comparador

### Criterios
- **Verdad = la cifra que el usuario vería en el tablero**: medida del visual + filtros de visual + filtros de página (+ periodo pedido).
  Excepción: un filtro de página sobre **otra tabla** cuyo efecto es < 2 % se tolera (ver AC02).
- **Verdad discutible**: otra fuente real del mismo concepto responde la pregunta tal como está escrita → se acepta como alternativa.
- **Contrapregunta legítima** solo si varias fuentes pueden responder la pregunta TAL COMO ESTÁ (periodo incluido) con cifras distintas.
  No es legítima si la pregunta ya desambigua (p. ej. «ahorita», «mes pasado» frente a un tablero que solo trae el día), si las opciones repiten la misma columna o si es una confirmación de una sola opción.
- **Artefacto del runner**: el runner pulsó la primera opción porque `elegir` no coincidía con la etiqueta (el tablero va en la descripción corta del botón, no en la etiqueta).

### «filtro o periodo mal aplicado» (26)
| Veredicto | Casos |
|---|---|
| Falla real de filtro/periodo (18) | BH01, BH02, BH04, BH11, BH14, BH15, BH16, BH17, TU02, TU04, AI04, AC05, EP01, EP02, FM01, FC02, FC04, DI03 |
| Falla real pero mal clasificada: es indicador (2) | BH08 (EGRESOS EFECTIVOS HOY en vez de EGRESOS PROBABLES), TU03 (ninguna opción es el tiempo de triage) |
| Valor contaminado por el runner (4) | TU10, AI01, AI03, AI06 (TU10, AI01 y AI06 fallan igual por contrapregunta innecesaria; AI03 queda inconcluso) |
| Verdad discutible (2) | AI07 (el bot filtra por Calendario; la tarjeta usa el año de FechaSolicitud: 6.023 frente a 5.872), AC02 (filtro de página `EN_ESPERA[CCEESTADO] ≠ 2` sobre otra tabla, 1 %) |

### «contrapregunta innecesaria» (21, sin BH18)
| Veredicto | Casos |
|---|---|
| Innecesaria de verdad (15) | BH02, BH03, BH09, TU02, TU03, TU03b, TU05, TU08, TU10, TU13, AI06, AI07, AC02, AC05, LV01 |
| Legítima (6) | BH04, BH14, TU12, AI02, AI03, DI02 |
| Además, mal excusadas en el banco (2) | AI01, AI08: «mes pasado» y la opción EGRESOS del Briefing solo trae el día anterior, así que eran innecesarias |

### Otras correcciones de la verdad
- **BH05** (lista de áreas): el bot listó 34 áreas reales de `ULT_GESTION[AREA_SERVICIO]`. Es una fuente válida → se acepta (verdad discutible).
- **AI05**: el bot usó la tarjeta «Consultas urgencias» del TABLERO EPS (1.442), con su filtro de visual. Es correcta para ese tablero → alternativa aceptada.
- **EP03**: «cuántos pacientes observados hay» → la verdad útil es la del Briefing (68, estado actual); la tarjeta EPS (68.683) es todo el histórico. El bot acertó.

### Errores del comparador encontrados
- `run_banco.classify`: `_core_refs` toma `truth_dax.split("CALCULATE(")...split(",")[0]`, que sin CALCULATE devuelve `EVALUATE ROW("v"` → clasifica como filtro lo que es indicador (BH08).
- Las respuestas por RAG con cifras de la documentación se clasifican como «respuesta inventada» (FM03); deben ir a «indicador/enrutamiento».
- `run_real.pick_button` solo miraba la etiqueta. **YA CAMBIADO** (único cambio de código de esta fase) para buscar en este orden: etiqueta exacta → contenida en la etiqueta → contenida en la descripción corta.

### Recuento auditado (parcial)
Aciertos 25/67 (37 %). Correctos nuevos: BH05, AI05, EP03 y AI02 (contrapregunta legítima). Inconclusos por el runner: AI03, DI02 y TU12.

## 2. Fallas reales por causa raíz (archivo y función en db2f1af)
1. **Filtros de página/visual no aplicados («valor general»)**: `src/semantic/query_plan_builder.py::_visual_filter_clauses` (l.687) solo lee `filters["visual"]` e ignora los de página e informe. `_with_visual_filters` (l.723) solo actúa en `visual_aggregation` (nunca en medidas) y solo si todas las apariciones comparten filtros. `src/chatbot/query_engine.py::_note_same_measure_pages` (l.3973) responde entonces el valor sin filtros.
   Casos: BH01 (75 % frente a 92 %), BH02, BH04, BH15, TU02, AC05, DI03, FM01 (2.439 frente a 278), EP01, EP02, AC02.
2. **Filtros espurios por coincidencia parcial de palabras**: `query_plan_builder.py::_resolve_implicit_filter` (l.3255), `_resolve_implicit_value` (l.3434) y `_value_match_score` (l.2831).
   Casos: BH07 (`ASEGURADOR = INTERCONSULTAS SAS`), BH17 («total» → SALUD TOTAL EPS), FC04 («cuentas» → PERFIL CUENTAS), BH11 («pendientes»), BH16 («briefing»), FC02 («las 5 más altas»).
3. **Columna de fecha equivocada / tablero del día para periodos históricos**: `query_plan_builder.py::_best_date_field` (l.3631) premia cualquier columna FECHA sin comprobar que filtre la tabla de la medida; `_snapshot_table` y `_current_state_period` (l.3932–3956).
   Casos: TU04 y AI04 (TRIAGES filtrado por `CONSULTAS PRIORITARIAS[FECHA]` → sin datos), BH14 (EGRESOS por FECHA_INGRESO: 15 frente a 48), AI01, AI08, AI03 (`PROMEDIO_ESTANCIA[FECHA]` vacía).
4. **Contrapreguntas innecesarias**:
   - (a) verbos o adverbios tomados como filtro («momento», «duran», «demora»): `query_engine.py::_unresolved_words_clarification` (l.2675), alimentada por el leftover de `query_plan_builder.py::_build_plan` (l.8508). Casos BH09, TU13, AC05.
   - (b) opciones duplicadas (misma columna o expresión): `query_engine.py::_build_clarification_choices` (l.2431) y `_finalize_choices` (l.2385). Casos TU02, AC02, TU08, TU05.
   - (c) confirmación de una sola opción débil: `query_engine.py::_query_plan_failure` (l.3293). Casos AI07, FC05, LV01, AI06.
   - (d) no se descartan opciones que no pueden responder el periodo: TU10, AI01, AI08, BH02.
5. **Indicador equivocado**: `query_plan_builder.py::_resolve_metric` (l.1180) y `alternative_metrics` (l.1423).
   Casos: TU03/TU03b (tiempo de triage → conteos), TU06 (interconsultas → imágenes), AC03 (%INASISTENCIA → CITAS CON ASISTENCIA), BH08, BH09 (8 frente a 268), TU13, FC05 y LV01 (→ «Promedio Mensual Año Pasado» de Atenciones), DI01 (`metric_not_resolved` con la medida TOTAL_DEMANDA_INSATISFECHA existente).
6. **Preguntas de datos enviadas a RAG**: `query_plan_builder.py::looks_numeric` (l.4082) y el paso 3 de `query_engine.py::process` (l.5912). Casos FM03, AB04, LV02, LV03.
7. **Opciones mal rotuladas**:
   - `src/chatbot/option_describer.py::describe` / `_describe_one`: descripciones erróneas de MedGemma. BH03 «Cuenta las camas disponibles» para OCUPADAS; BH09 «unidad obstétrica» cuando la excluye; BH14 «Cuenta ingresos» para EGRESOS.
   - `src/semantic/visual_catalog_builder.py::_visual_title` (l.876): el título de una tabla se usa como indicador (BH03: «CAMAS OCUPADAS» = SUM(PACIENTE_ACOSTADO)).
8. **Agrupación ignorada**: `query_plan_builder.py::_requested_group_tail` (l.5241) no reconoce «y su respectiva especialidad». Casos TU12 y BH18.

## 3. Hecho en `agente/qa-real-2` (puntos 1–3 y 5 del pendiente)
- Banco: `build_banco.AJUSTES_AUDITORIA` (elegir y contrapreguntas), alternativas `{"modelo", "dax"}` (AI05 con la
  tarjeta EPS, AI07, AC02, LV01), EP03 en el Briefing, `lista_alternativa` en BH05 y `criterio` en cada caso.
  - AI06: `elegir = "Total Partos Dinamico"` (la etiqueta exacta «TOTAL PARTOS» es la del modelo CONSOLIDADO).
  - AI05: la tarjeta EPS es `CountNonNull(OID_TRIAGE)`, así que la alternativa usa COUNT (lo que ve el usuario), no DISTINCTCOUNT.
- Comparador (`run_banco.py`): `compute_truths`, `truth_core_expr` (núcleo de la medida), RAG en pregunta de datos →
  «indicador» con `detalle.enrutamiento = "rag"`, `choose_button` guarda `eleccion.modo` y los fallos con elección
  «defecto» quedan inconclusos (si la contrapregunta es legítima) o fallan solo por la contrapregunta.
- `auditoria.json` (veredicto, fallas, causas y huella de la respuesta por caso) y `auditoria.py`;
  `run_banco --reevaluar <resultados.json> --auditoria`.
- `correr_todo`: INFORME.md con tasa automática y auditada, por tablero, por causa raíz y `--comparar <resultado.json>`;
  `--informe <resultado.json>` rehace el informe de una corrida sin preguntar.
- Pruebas offline: `python -m tests.real.test_comparador`.

## 4. Pendiente (original)
1. Banco (`build_banco.py` y regenerar `banco_real.json`, sin `--valores`):
   - `elegir`: BH03 «GESTIÓN CAMAS», BH04 y BH14 «BRIEFING», TU05 «%ATENDIDO», TU10 «ATENCIÓN EN TRIAGE», TU12 «INTERCONSULTAS SOLICITADAS», AI01 y AI08 «Total Egresos», AI02 «TABLERO DE ATENCIONES», AI03 «INDICADORES», AI06 «TOTAL PARTOS», DI02 «conteo de OID».
   - `contrapregunta_aceptable`: True en BH04, BH14, TU12, AI02, AI03, DI02; False en AI01, AI08.
   - Alternativas con su propio modelo (`{"modelo", "dax"}`):
     - AI05: tarjeta EPS, `DISTINCTCOUNT(CONSULTA_URGENCIAS[OID_TRIAGE])` con su filtro y `'Calendario'[Fecha]`.
     - AI07: `COUNT(LABORATORIOS_PATOLOGICOS[Consecutivo])` filtrado por `'Calendario'[Date]` del año.
     - AC02: sin filtro de página.
   - EP03: pasar a BRIEFING, `DISTINCTCOUNT('PACIENTES OBSERVADOS'[PACNUMDOC])`.
   - BH05: aceptar una lista de una dimensión real de servicios o áreas (≥ 5 valores, DAX exitoso).
   - Guardar el criterio en cada caso (`criterio`).
2. Comparador (`run_banco.py`):
   - en `compute_truth`, alternativas con modelo propio;
   - arreglar el núcleo de expresión en `classify`;
   - RAG en pregunta numérica → indicador (enrutamiento), no «inventada»;
   - guardar en el resultado cómo se eligió el botón (elegir, página, modelo o primera por defecto) y marcar como inconcluso un fallo cuyo valor dependa de una elección por defecto.
3. Añadir `tests/real/auditoria.json` con el veredicto por caso de la corrida db2f1af y un `--auditoria` en `run_banco --reevaluar`.
4. Pedir al coordinador: `correr_todo --solo AI03,DI02,TU12,BH03,TU05,TU10,AI01,AI06,AI08` (inconclusos y elecciones corregidas).
5. Escribir `tests/real/INFORME.md`. Top 10 propuesto: BH01, FM01, BH07, BH17, TU04+AI04, BH14, TU03, BH09, TU12 (pregunta real del usuario), FC05+LV01. Incluir evidencia (pregunta, respuesta, verdad, DAX del bot frente al DAX de verdad) tomada de `resultado.json`.
6. Comparar con la segunda pasada del coordinador (código nuevo).

## 5. Holdout v1 (adf0fb0) — auditoría (`auditoria_holdout.json`)

Corrida: `C:\Users\ad6708\Documents\banco_holdout_out_v1_adf0fb0\` (19/50 automática). Auditadas las 31 fallas:
29 fallas reales (a), 2 no evaluables (b: H40 anafórica sin turno previo + PBIR de REFERENCIA vacío; H41 PBIR de
REFERENCIA vacío), 0 de comparador (c) y 0 contrapreguntas legítimas (d). **Tasa auditada: 19/48 (40 %).**
Re-evaluar: `correr_todo --banco tests/real/banco_holdout.json --informe <resultado.json> --out-informe <carpeta>`
(usa `auditoria_holdout.json`, no la del banco real). Banco: `elegir` de H12 («ATENCION HP») y H21 («30-120»).
Comparador: una respuesta por RAG a una pregunta de datos es enrutamiento aunque haya sondas DAX exitosas.

| Causa raíz (reglas GENERALES) | Casos | Dónde | Regla sugerida |
|---|---|---|---|
| 10 Lenguaje de chat sin normalizar | H02 H03 H10 H11 H24 H27b H29 H31 H35 H38 | no hay paso común: `query_plan_builder.normalize_text`, `question_kind.normalize_question`, `_GROUP_TAIL_RE`, `looks_numeric`, `period_parser` | Normalizar UNA vez al entrar (`QueryEngine.process`): x→por, q→que, pa→para, d→de, xq→porque; corregir tipeos contra el vocabulario del catálogo (distancia ≤ 2 en palabras ≥ 6 letras) antes de rutear |
| 4 Contrapregunta innecesaria | H03 H10 H12 H21 H22 H26 H28 H31 H33 H39 H43 H45 | `query_engine._unresolved_words_clarification`, `_build_clarification_choices`/`_finalize_choices`, `_query_plan_failure` | Palabras sobrantes que son verbos o que la página ya implica no son filtros; colapsar opciones de la misma medida base (agregación o variante de tiempo); usar filtros de visual de cada opción para elegir sola (rango, periodo); nunca confirmar una sola opción |
| 5 Indicador no resuelto o equivocado | H11 H12 H13 H24 H26 H32 H45 | `query_plan_builder._resolve_metric`, `_source_context` | Indexar como alias los títulos de visual, nombres de página y valores categóricos (ABORTO), y la documentación (mortalidad→%DEFUNCIONES); un tablero nombrado en la pregunta restringe la búsqueda |
| 6 Enrutamiento datos ↔ RAG | H02 H27b H29 H34 H38 | `query_plan_builder.looks_numeric`, `question_kind.descriptive_phrase` | Frase nominal/lista/agrupación sobre una página con indicadores = datos; RAG nunca devuelve cifras de datos; «por qué etapas/estados pasa» = descriptiva |
| 8 Agrupación ignorada | H09 H22 H28 H35 | `_requested_group_tail`, `_group_field_in` | «por/x/según <X>» busca X también en valores y descripciones de columnas (rango de horas→HORAS_SUMINISTRO, motivos→CCCDESCRI, día de la semana→DIA_SEMANA) antes de tratarlo como filtro |
| 3 Fuente sin cobertura del periodo | H05 H14 H15 | `_snapshot_table`, `_current_state_period` | Cobertura temporal por tabla (día anterior, próximas citas, 30 días) desde la documentación; descartar fuentes que no cubren el periodo; con «hoy» en un corte de ayer, responder el corte y avisarlo |
| 11 Filtro de la pregunta ignorado o reducido | H05 H20 | `_resolve_implicit_value` | Una palabra que coincide con varios valores (OBSTETRICA) filtra por todos; si no se aplica, decirlo; preferir el visual cuyo filtro coincide |
| 12 Periodo mal resuelto | H08 H10 | `period_parser` (mes sin año = todos los años) | Mes sin año = su ocurrencia más reciente (como ya se hace en comparaciones) |
| 2 Filtro espurio | H35 | `_value_match_score` | Una palabra de la agrupación no puede ser también valor de filtro |
| 13 RAG recupera otro indicador | H18 | `src/rag/ranking.py` | Priorizar el fragmento cuyo indicador coincide con el nombrado («% pendiente») y el tablero del contexto |

## 6. Ronda r6 (rama `agente/r6`, sin corrida real)

Reglas generales (pruebas en `tests/resolution/test_r6.py`, preguntas nuevas):
- **Cobertura (TU04)**: `table_coverage.covers` solo da la holgura de un día a periodos de 1–2 días; «este mes»
  el día 3 ya no lo trae la tabla «del día anterior» (TRIAGES del Briefing) → CANTIDAD DE TRIAGES de TIEMPOS URGENCIAS.
  `_named_page_refinement`: una página nombrada no arrastra a indicadores cuya tabla no trae el periodo.
- **Sin datos (AI01, AI08)**: `empty_result` también para tablas agrupadas vacías; la respuesta dice indicador,
  periodo y, si el último dato es anterior al periodo, «La fuente tiene datos hasta el dd/mm/aaaa»
  (`generate_data_until`, una consulta extra solo con resultado vacío). Comparador: verdad vacía (0 filas o valor
  en blanco, también en las alternativas) → acierto si dice claramente «no hay datos» sin filas; si no, falla
  `redaccion` (causa 14).
- **H20**: lo común a los valores de un filtro de inclusión de un visual nombra su indicador (Triages Gineco).
- **H05**: la página del indicador («urgencias») no elige un solo valor de una familia («obstétricos»).
- **H24**: un alias de dimensión tomado del título del indicador no cuenta como dimensión ni como encabezado.
- **H29**: «qué <entidades> se están <verbo>» → el gráfico del tablero por esa entidad, agrupado.

Pendientes del holdout v2 (no forzados):
- PBIP incompleto: H26, H39, H40, H41 (REFERENCIA: PBIR vacío), H43 (CVC: sin fecha en el modelo local),
  H13, H14, H15 (ATENCIONES: PARTOS_DRIVE/CONSULTAS_AMBULATORIAS sin visuales ni fecha en el PBIP local).
- H02 («cómo están repartidas las camas x estado»): en el simulador contrapregunta, en real fue a RAG (MedGemma);
  revisar con la corrida real.
- H09 (promedio de triage por día de la semana): `unsupported_filter`; falta revisar con datos reales de DIA_SEMANA.
- H11: en el simulador ya elige TIEMPO PROMEDIO PARA EL EGRESO con SUBGRUPO = URGENCIAS (igual que la verdad); validar.
- H18 (RAG trae RELACIÓN ACEPTADOS para «% pendiente de citas»): ranking del RAG, sin tocar.
- H27b («cirujias canceladas agosto vs septiembre»): elige TOTAL_CIRUGIAS/CANCELADAS de citas; la verdad es
  CIRUGÍAS de Demanda Insatisfecha con TIEMPO_CIRUGÍA > 45; sin tocar.

## 7. Ronda r7 (rama `agente/r7`, sin corrida real)

Reglas generales (pruebas en `tests/resolution/test_r7.py`, preguntas nuevas):
- **TU04 (causa en real)**: «cuántos triages» nunca coincidía con CANTIDAD DE TRIAGES (`_core_name_score` exigía
  dos palabras tras «cantidad de»), así que en el catálogo real solo competían TRIAGES (Demanda) y el «Recuento de
  PACNUMDOC» de TRIAGES ATENDIDOS (EPS), que explicaba «urgencias» por su filtro GASNOMBRE y su página. Ahora:
  (1) «cuántos/número de X» nombra «CANTIDAD/NÚMERO DE X» completo (no «TOTAL X» ni unidades genéricas:
  CANTIDAD DE PACIENTES); (2) el tablero del indicador
  explica un calificativo también en `_promote_qualifier_metrics` («urgencias» → TABLERO TIEMPOS URGENCIAS), como ya
  lo hacía el puntaje; (3) un conteo implícito de identificador («Recuento de <col. de documento/OID/ingreso>»,
  `_implicit_identifier_count`) va detrás de un indicador con nombre de negocio que explica lo mismo
  (`_qualifier_candidates` y `QueryEngine._drop_dominated_options`).
- **H05**: en la coincidencia aproximada (`_fuzzy_qualifier_filters`) una palabra común a varios valores
  («obstétricos»: URGENCIA OBSTETRICA y los demás …OBSTETRICA) filtra por todos (IN), como la verdad (CONTAINS).
  La regla de r6 (`_context_word_family`) no se aplicaba porque en real «urgencias» ya la consumía la página.
- **H09**: «por día de la semana» no es granularidad diaria (`period_parser._GRANULARITY_RES`); se agrupa por
  DIA_SEMANA. Encabezado sin la referencia nativa «Primera fecha: DIA_SEMANA».
- **H02**: el verbo de reparto («cómo están repartidas/distribuidas X por Y», «cómo se reparten») se quita en
  `canonical_phrases`: ya no es el «sustantivo principal» que descartaba CAMAS.

Pendientes del holdout v3 (no forzados):
- PBIP incompleto: H13, H14, H15 (ATENCIONES: PARTOS_DRIVE / CONSULTAS_AMBULATORIAS sin visuales ni fecha local),
  H26, H39, H40, H41 (REFERENCIA: PBIR vacío; H26 = REFERENCIA con CAUSA de no aceptación), H43 (CVC sin fecha).
  Igual que AI05/AI06 del banco de desarrollo.
- H18 (ranking del RAG trae RELACIÓN ACEPTADOS para «% pendiente de citas»); H27b («canceladas» = TIEMPO_CIRUGÍA > 45
  en Demanda Insatisfecha: definición del tablero que ningún nombre dice).
- H09: elige PROMEDIO_TRIAGE_2026 (ATENCIONES, AVERAGE de OPORTUNIDAD_TRIAGE[MIN] del año) en vez de TIEMPO PARA
  TRIAGE (TIEMPOS URGENCIAS); misma cifra si las dos tablas son la misma fuente. Validar en real (claves «lunes»
  frente a «1. LUNES»).

### Simulador frente a la data real (falsos positivos)
1. **Prueba de regla ≠ prueba del catálogo.** r6 validó TU04 con `_page_refinement_fixture`, que parchea
   `_page_choices`/`_metric_misses_period`; con el catálogo real CANTIDAD DE TRIAGES ni siquiera era candidato. El
   chat del simulador (`python -m tests.realistic.chat "..."`) sí reproducía la falla: validar cada caso del banco
   también por el chat, no solo por la prueba unitaria.
2. **Cobertura de fechas**: en el simulador `Calendario[FECHA]` de TIEMPOS URGENCIAS y `Calendario[Fecha]` del EPS
   van de 2024-01-03 a 2026-06-20 (la expresión `CALENDAR("2023-01-01", TODAY())` no llega a hoy), mientras que
   `TRIAGES[FECHA]` del Briefing llega a mañana. «Este mes»/«mes pasado» dan «no hay datos» en esos modelos aunque
   el indicador sea el equivocado (TU04 decía «No hay datos de Recuento de PACNUMDOC»): un caso que solo verifica
   estado/ruta pasa. Revisar `datagen._from_expression` (mapeo de columnas de CALENDAR).
3. **Dominios de valores**: el simulador genera valores sintéticos (TRIAGES[DESCRI_TRIGE] = TRIAGE I…V); en real
   son clasificaciones (URGENCIA OBSTETRICA, …). Las reglas de familias/valores (H05) no se pueden ejercer de punta a
   punta en el simulador: probarlas con dominios parcheados (test_r7) y en real.
4. **Catálogo distinto**: `catalog_patches.py` y los modelos sintéticos (`tests/realistic/synthetic_models`)
   agregan medidas (CAMAS sobre SERVICIOS × ESTADOS_CAM, «supuesto») y homónimos; cambian las ambigüedades (H02:
   en el simulador CAMAS frente a CamasFiltradas; en real «CAMAS en varios tableros»). Para comparar con real usar
   `SIM_PATCHES=0` / `SIM_SYNTHETIC=0`.
5. **Tablas «del día anterior»**: en el simulador tienen historia completa; la cobertura solo sale de la
   documentación (`table_coverage`), así que una regla de cobertura mal escrita no se nota en las cifras.

IDs a validar en real: `correr_todo --solo TU04,TU01,TU03,TU10,BH10,BH15,EP02,AI04` y holdout
`--banco tests/real/banco_holdout.json --solo H02,H05,H09,H20,H24,H29`.

## 8. Bancos nuevos y regresión periódica (rama `agente/qa-bancos`, sin corrida real)

- **Holdout 2** (`build_holdout2.py` → `banco_holdout2.json`, 50 casos G01–G50): escrito sin mirar `src/` ni las
  fallas, misma mezcla de tableros y tipos que el holdout. Verdad desde el PBIR; en los PBIP incompletos (REFERENCIA,
  CVC, MORBILIDAD y páginas de ATENCIONES sin visuales) desde el modelo y la documentación, marcado en `criterio`
  («PBIP local incompleto»). `similitud.py` verifica que no repite ni parafrasea los otros bancos (Jaccard de palabras
  de contenido + trigramas, y difflib); `test_bancos` lo exige.
  Correr: `correr_todo --banco tests/real/banco_holdout2.json` (salida en `out_holdout2/`).
- **Multiturno** (`build_multiturno.py` → `banco_multiturno.json`, 26 conversaciones, 71 turnos): periodo,
  agrupación, filtro, indicador, pronombres, corrección y clic en contrapregunta. Cada turno tiene su verdad DAX
  (marcadores nuevos `{INI_MES_ANTEPASADO}`, `{FIN_MES_ANTEPASADO}`, `{INI_SEMANA_PASADA}`, `{FIN_SEMANA_PASADA}`).
  `run_multiturno.py` usa el mismo sistema que `run_real`, calcula la verdad antes de cada turno, pulsa la opción de
  `elegir` si hay contrapregunta y evalúa cada turno con `run_banco.evaluate`. Informe: acierto por turno, por
  posición, por categoría, seguimientos (y seguimientos con el turno anterior correcto) y por conversación.
  Los primeros turnos reutilizan preguntas del banco de desarrollo a propósito: lo que se mide es el seguimiento.
- **Regresión periódica** (`tools/manual/regresion_real.py`): corre los cuatro bancos en serie, compara con
  `tests/real/linea_base/<banco>.json` (solo id, correcto, fallas y cifra) y escribe `var/out/regresion/REGRESION.md`.
  «Dato en vivo» = falla de cifra con la misma firma DAX (columnas, medidas y literales) que la verdad.
  `--aceptar` promueve la corrida; `--reusar <carpeta>` compara o acepta una corrida ya hecha. Salida 0/1/2.
  Programador de tareas: ver el docstring de `tools/manual/regresion_real.py` y `regresion_tarea.ps1` (la tarea NO se creó).
- Pendiente: primera corrida real y `--aceptar` para crear la línea base; auditar los fallos de holdout 2 y del
  multiturno (verdades de PBIP incompletos y valores supuestos: NUEVA EPS, SURA, ORTOPED, MEROPENEM, HOSPITAL).

## 9. Auditoría de holdout 2 y multiturno (rama `agente/qa-auditoria-2`, corridas de `desarrollo` antes del refactor)

Archivos: `auditoria_holdout2.json`, `auditoria_multiturno.json` (veredicto por turno, campo `origen`),
`consultas_auditoria.json` (DAX de solo lectura pendientes, Q01–Q07). `run_multiturno --reevaluar <copia> --auditoria
tests/real/auditoria_multiturno.json` aplica los veredictos auditados (por huella).

- **Holdout 2**: 9/49 → **10/49 (20 %)**. 41 auditados: a = 39, b = 1 (G15: verdad rota, columna TIPO_TRIAGE
  inexistente), c = 1 (G19: filtro de página de otra tabla < 2 %), d = 0. Verdades corregidas en `build_holdout2`
  (G15 sin el filtro obsoleto; G17/G19 con alternativa sin el filtro de EN_ESPERA). G31 («UCI») pendiente de Q01.
  Valores supuestos revisados: MEROPENEM y HOSPITAL(ARIO) existen (verdad no vacía); «UCI» probablemente no.
- **Multiturno**: turnos 41/70 → **43/66 (65 %)**, seguimientos 21/45 → **22/41 (54 %)**, conversaciones 7/25 →
  **9/24 (38 %)**. 30 auditados: a = 23 (15 de contexto, 8 de la pregunta suelta), b = 5 (NUEVA EPS supuesto en
  MT09.2, MT10.2, MT10.3; MT12.2 cardiología exacta; MT01.3 heredado del clic del runner), c = 1 (MT12.3: «0» = sin
  datos), d = 1 (MT20.1). `build_multiturno`: NUEVA EPS → «NUEVA EMPRESA PROMOTORA», alternativa exacta en MT12.2 y
  `elegir = TIEMPO PARA TRIAGE` en MT01.1. SURA y ORTOPED dan cifra (familias por CONTAINSSTRING).

Causas raíz (reglas generales; se da la función porque el código se está refactorizando):
| Causa | Casos | Dónde | Regla |
|---|---|---|---|
| Datos → RAG | G02 G11 G16 G18 G23 G29 G31 G34 G35 G39 G41 G42 (G26 al revés) | `query_plan_builder.looks_numeric`, `QueryEngine.process` | Comparación «X o Y», «por/según X», «top N», «qué día/servicio… más», página nombrada = datos; el RAG nunca da cifras ni listas de valores (G16, G29, MT19.3 inventaron) |
| Indicador no resuelto | G03 G04 G08 G10 G13 G14 G27 G32 G36 G40 G43 G44 G45 G47 MT16.1 | `_resolve_metric`, `alternative_metrics`, `_source_context` | Lematizar verbos/clíticos (asignarle, dispensarse, admitieron, salieron, altas); sinónimos (más caras→AUMENTÓ); un valor categórico (meropenem) o el nombre del tablero (naos, morbilidad) fija el tablero; preferir medidas usadas en visuales (G14) |
| Contrapregunta innecesaria | G03 G04 G06 G08 G14 G24 G25 G32 G37 G38 G40 G45 G46 G47 MT01.1 MT04.1 | `_unresolved_words_clarification`, `_build_clarification_choices`, `_query_plan_failure` | Descartar opciones que no aplican el filtro pedido o no cubren el periodo; nunca confirmar UNA opción; «diferentes» = DISTINCT |
| Filtro/agrupación espurios o negados | G17 G21 G24 G25 G26 G28 MT11.2 | `_resolve_implicit_value`, `_requested_group_tail`, `_value_match_score` | «por el paciente/los facturadores» (agente) no es desglose; «sin contar X» = NOT IN; «cuentas» no es PERFIL; palabra común a varios valores = familia |
| Filtros de página no aplicados | MT03.x MT04.x | `_visual_filter_clauses`, `_with_visual_filters` | Aplicar los filtros de página del indicador también en medidas |
| Contexto: seguimiento no detectado | MT06.2 MT07.3 MT08.2 MT08.3 MT09.3 MT17.3 MT19.3 MT23.2 MT24.3 | `contextual_rewriter.analyze`, `QueryEngine._followup_plan`, `_contextual_generic`, `_documentation_about_topic` | Mensaje corto tras datos («¿por X?», «¿cuál … más?», «¿y de mujeres?») se intenta PRIMERO como seguimiento; valor/columna/medida hermana de la tabla anterior = filtro o agrupación; la base es el último turno de DATOS aunque haya un RAG en medio |
| Contexto: periodo relativo | MT01.2 MT04.2 | `_followup_plan` / `_with_previous_year`, `period_parser` | «el mes/año/semana anterior (a ese)» se desplaza desde el periodo del turno anterior, no desde hoy |
| Contexto: elipsis de indicador | MT14.2 MT14.3 | `_ELLIPSIS_RE` + `_followup_plan` | «¿y el de X?» reemplaza el calificativo del indicador anterior y re-resuelve en el mismo tablero |
| Contexto: visual arrastrado | MT13.2 | `_followup_plan` | Si el valor nuevo tiene su propia tarjeta, usar sus filtros |
| Contexto: reescritura contaminada | MT17.2 | `LLMContextRewriter.build_messages/validate`, `conversation_memory.summarize_result` | El transcript no lleva rótulos de la respuesta («Filtros:»); `validate` rechaza palabras que solo están ahí |
| Fuera de alcance clínico | G50 | detector de alcance (`question_kind`) | Dosis/tratamiento se rechaza antes del Query Plan |

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

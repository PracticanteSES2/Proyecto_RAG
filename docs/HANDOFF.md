# Handoff — 2026-10-29 (pausa)

Estado para retomar el trabajo sobre el asistente administrativo (RAG + Power BI).
Rama de trabajo: `desarrollo` (local; **último push a GitHub: a0837b6**, lo de abajo NO está subido).

## Reglas que no cambian
- Power BI y bases de datos de **producción: solo lectura**. Nunca modificar tableros, modelos, workspaces ni BD.
  Nada de filas con datos de pacientes en salidas, logs o commits. Pocas consultas.
- `.env` lo edita solo el usuario. Los agentes en worktrees **no** deben cargarlo; las corridas reales se lanzan
  desde la raíz del checkout principal.

## Qué quedó hecho (en `desarrollo`, sin push)
| Tema | Dónde |
|---|---|
| Token de MedGemma desde `.env` (`MEDGEMMA_API_KEY`, Bearer) | `src/llm/medgemma_provider.py` |
| Power BI sin ventana: código de dispositivo, token en caché (`POWERBI_AUTH=device_code`) | `src/providers/powerbi_token.py` (`login` / `logout`), caché en `data/.powerbi_token_cache.bin` |
| Metadata REAL de los 43 modelos (sync del 2026-10-29) + catálogos y RAG regenerados | `data/` (no versionada; respaldos en `Documents/Proyecto_RAG_data_backup_20261029*`) |
| Columnas del DAX validadas contra el modelo; fecha de la tabla relacionada (causa `Calendario[Date]`: el PBIR de TIEMPOS URGENCIAS usa el nombre viejo de la jerarquía) | `src/dax/column_guard.py`, `query_engine._execute_dax` |
| «lista de X» → valores de la dimensión en Power BI; respaldo extractivo legible | `src/semantic/detail_list.py`, `query_engine._dimension_listing`, `src/rag/extractive.py` |
| Homónimo sin informe se descarta; «nivel/índice» no son filtro; «cada una / su respectiva X» agrupan | `src/semantic/query_plan_builder.py`, `request_phrases.py` |
| Botón «Abrir en Power BI ›» (43 modelos, 382 páginas) | `tools/sync_powerbi_links.py`, `src/providers/powerbi_links.py`, `app.py`, `data/catalog/report_links.json`; paso opcional en `update_rag.py` (`--skip-links`) |
| Banco REAL con verdad DAX (71 casos, 10 tableros) | `tests/real/` (`correr_todo.py`, `run_real.py`, `banco_real.json`) |
| 6 casos de las conversaciones del usuario en el banco del simulador | `tests/eval/questions.json` |

Todas las suites en verde (se corren por módulo: `python -m tests.<paquete>.<modulo>`; `tests/docs_md` con
`python -m unittest discover -s tests/docs_md -t .` y `DOCS_MD_SIN_APP=1`).

## Mediciones
- **Banco real, commit db2f1af (antes del arreglo de indicadores): 21/70 (30 %).** Fallas: filtro/periodo 26,
  contrapregunta innecesaria 21, indicador equivocado 17, agrupación 3, inventada 1.
  Salidas: `Documents/banco_real_out_base_db2f1af/`.
- **Segunda corrida (HEAD a9d26a4) detenida en 44/71: 12 OK, 31 MAL.** Log parcial: `Documents/banco_real_v2.log`.
  Patrón visto: «mes pasado» / «2025» → «No hay datos para esos filtros» cuando sí hay datos.
- Banco del simulador (`tests.eval.run --harness realistic --llm fake`): 117/158 con la data real (antes 113).

## Auditoría del banco real (rama `agente/qa-real`, commit 069b99a, WIP)
Recuento auditado de la corrida db2f1af: **25/67 (37 %)**, con 3 casos inconclusos (AI03, DI02, TU12).
Criterio: la verdad es la cifra que el usuario ve en el tablero (medida + filtros de visual y de página + periodo);
una contrapregunta solo es legítima si varias fuentes responden con cifras distintas.

Causas raíz de las fallas reales (líneas en db2f1af):
1. Filtros de página nunca aplicados; los de visual se pierden si el indicador está en varios visuales —
   `query_plan_builder._visual_filter_clauses` (~l.687), `_with_visual_filters` (~l.723),
   `query_engine._note_same_measure_pages` (~l.3973). Ej.: BH01 ocupación 75 % vs 92 %; FM01 2.439 vs 278.
2. Filtros espurios por coincidencia parcial («total»→SALUD TOTAL, «interconsultas»→INTERCONSULTAS SAS) —
   `_resolve_implicit_filter` (~l.3255), `_resolve_implicit_value` (~l.3434).
3. Columna de fecha equivocada — `_best_date_field` (~l.3631) (TRIAGES por CONSULTAS PRIORITARIAS[FECHA]).
4. Contrapreguntas innecesarias — `_unresolved_words_clarification` (~l.2675), `_build_clarification_choices`
   (~l.2431), `_query_plan_failure` (~l.3293).
5. Indicador equivocado — `_resolve_metric` (~l.1180) (TU03, AC03, BH08, BH09, FC05, LV01, DI01).
6. Preguntas de datos enviadas a RAG — `looks_numeric` (~l.4082) (FM03, AB04, LV02, LV03).
7. Opciones mal rotuladas — `option_describer`, `_visual_title`.
8. Agrupación ignorada — `_requested_group_tail` (~l.5241) (TU12).

Pendiente de esa rama (ver `tests/real/RETOMAR.md`):
- aplicar las correcciones del banco y del comparador;
- pedir la corrida `--solo AI03,DI02,TU12,BH03,TU05,TU10,AI01,AI06,AI08`;
- escribir `INFORME.md`.

## Actualización 2026-10-30
- Integradas en `desarrollo`: qa-real-2 (banco y comparador auditados), fix-filtros-tablero (+2), fix-contrapreguntas,
  fix-indicador-ruta, r2-indicador (lavandería, cobertura de periodo), r2-contrapreguntas, r2-redaccion
  (notas en lenguaje de negocio y unidades, `src/chatbot/business_terms.py`).
- **Banco real: 37 % (06c132f) → 66 % (ab0c94d) → 83 % (58/70).** Salidas en `Documents/banco_real_out_v5_*`;
  conversaciones legibles en `Documents/conversaciones_banco_real_v5.md`.
- Fallas restantes: contrapregunta (TU08, TU10, AI01, AI06, AI08, AC02), filtros de página (AI01, AI06, EP02, FC04;
  el PBIP local de ATENCIONES está incompleto: pedir el completo al propietario), espurios (TU06, TU10, AI05),
  indicador (BH09), ruta a RAG (AB04). En curso: agente `agente/r2-indicador-2` (BH09, BH18, TU06, FC04).
- La app se puede levantar sin ventana: `POWERBI_AUTH=device_code` en el entorno del proceso.

## Actualización 2026-10-30 (tarde)
- Integradas también: r2-indicador-2 (BH09, BH18, TU06, FC04), r3 (contrapreguntas por ventana «Día», comparaciones,
  filtro de mes, página nombrada, ranking, etiqueta BH18) y r4 (regresiones FC05/AC01/AC04; `_general_indicator`
  no cambia a una tarjeta cuyo nombre trae palabras que la pregunta no dice).
- **Banco real: 83 % → 90 % (r3) → 96 % (67/70, r4), sin regresiones.** Fallan solo AI01, AI05, AI06 (PBIP de
  ATENCIONES incompleto: pedir el completo al propietario). Salidas `Documents/banco_real_out_v7_*`.
- En curso: banco **holdout** (`tests/real/banco_holdout.json`, ~40 preguntas nuevas) para medir generalización.

## Actualización 2026-11-03
- Banco **holdout** (`tests/real/banco_holdout.json`, 50 preguntas nuevas, auditado en `auditoria_holdout.json`):
  40 % (v1) → 67 % (r5: normalización de chat `question_normalizer.py` + reglas generales) → **76 % (r6)**.
  Banco de desarrollo: **96 %** (67/70). Salidas `Documents/banco_*_out_v9_530eecc` y `banco_holdout_out_v3_530eecc`.
- Arreglos: cuelgue O(n²) en `value_contradiction` + presupuesto `PLAN_TIME_BUDGET_S` (`plan_budget.py`);
  privacidad: listados excluyen familiar/vocero/acudiente/contacto; respuestas «sin datos» con fecha de corte.
- Repo: `.pyc` ya no se versionan. `actualizar_proyecto.ps1` (propietario): pull + deps + .env + login de dispositivo
  si falta + `tools/update_rag.py`. Push a GitHub hasta `bfbd594`; lo posterior (r6) está solo en local.
- Botón «Abrir en Power BI» del propietario: requiere `data/catalog/report_links.json` (sync con sesión de
  dispositivo). Pendiente decisión del usuario: `POWERBI_AUTH=device_code` en su .env vs versionar el catálogo.
- En curso: `agente/r7` (TU04 en real: «Recuento de PACNUMDOC» del EPS le gana a CANTIDAD DE TRIAGES; holdout restante).

## Actualización 2026-11-03 (cierre)
- Rondas r6, r7 y r8 integradas: «sin datos» con fecha de corte; «cuántos X» → CANTIDAD/NÚMERO DE X; «Recuento de
  <identificador>» detrás de indicadores de negocio; homónimos empatados se resuelven con todos los tableros.
- **Banco real de desarrollo: 96 % (67/70)** — la única falla nueva (FM01) es dato en vivo: DAX del bot = DAX de verdad.
  Fallan AI05 y AI06 (PBIP de ATENCIONES incompleto). **Holdout: 80 % (39/49)**, desde 40 %.
- Divergencias simulador ↔ real documentadas en `tests/real/RETOMAR.md` §7 (validar siempre en real).
- Subido a GitHub (`desarrollo`). El propietario: `git stash` si tiene cambios, `git pull origin desarrollo`, y
  `powershell -ExecutionPolicy Bypass -File .ctualizar_proyecto.ps1` (hace el login con código si falta y
  genera los enlaces del botón).

## Actualización 2026-11-04 (cinco puntos)
- Refactor del motor por etapas (`src/semantic/resolucion/*`, mapa en `src/semantic/README_motor.md`; golden master
  `tests/resolution/test_golden.py`). Bancos nuevos: `banco_multiturno.json`, `banco_holdout2.json`, `tools/manual/regresion_real.py`.
  Diccionario: `docs_tableros/POR_CONFIRMAR.md` (145 preguntas para el propietario). r9: salvaguarda de cifras del RAG
  (`src/rag/grounding.py`), verbos/clíticos, contrapreguntas por filtro, NOT IN, seguimientos.
- Real (2026-11-04): desarrollo **96 %**, holdout 1 **80 %**, **holdout 2 22 %** (11/49), multiturno (sin auditar)
  turnos 70 %, seguimientos 67 %, conversaciones 50 %. Sin regresiones.
- Holdout 2 casi no mejoró en real: sus fallas son paráfrasis semánticas («especialidades que más operaron»,
  «pacientes internados repartidos por piso») y comparaciones entre periodos («subió o bajó de sept a oct»,
  «más rápido en junio o en julio»). El motor de reglas llega a su límite ahí; ver propuesta de usar el LLM para
  extraer la intención estructurada (indicador, filtros, periodos, comparación) y validarla con el catálogo.

## Portero conversacional (2026-11-09)
- Saludo, agradecimiento, despedida, estado, identidad y capacidades se responden con textos fijos por la ruta `conversacion`, sin buscar en la documentación ni en Power BI. Módulo `src/chatbot/portero.py`; pruebas en `tests/portero/`; spec en `specs/001-portero-conversacional/`.
- Nunca actúa con una contrapregunta o un plan pendiente; ante cualquier duda o fallo se desactiva solo (log de advertencia sin el texto del usuario) y el mensaje sigue el flujo normal.
- `build_system` precalienta el portero (MiniLM + catálogo): suma ~4–6 s al arranque en frío; el primer «hola» ya no paga ese costo.
- Pendiente (permiso del usuario): bancos reales y golden master (T028).

## Estructura del repositorio (2026-11-10)
- Arquitectura objetivo (monorepo FastAPI + Next.js + Redis; Streamlit congelado), capas, «dónde va cada cosa» y
  plan por fases para partir `query_engine.py`: `docs/ARQUITECTURA.md`. Reglas cortas en `CLAUDE.md`.
- Salidas de bancos y evaluadores ahora en `var/out/<suite>/` (ignorada), logs en `var/logs/`, temporales en
  `var/tmp/` (`src/comun/rutas.py`). Las carpetas viejas `tests/real/out*` y `tests/eval/out` siguen ignoradas.
- Este archivo se movió de la raíz a `docs/HANDOFF.md`.

## Pendiente (en orden)
1. Rama `agente/qa-real`: auditoría de la verdad y del comparador del banco real (ver `tests/real/RETOMAR.md`
   en esa rama). Integrarla cuando esté.
2. Repetir el banco real completo desde la raíz:
   `$env:POWERBI_AUTH="device_code"; .venv\Scripts\python.exe -X utf8 -m tests.real.correr_todo`
   (30–45 min; `--solo ID1,ID2` o `--tablero "X"` para parciales).
3. Ronda de correcciones por causa raíz, empezando por periodos («mes pasado», años) y contrapreguntas.
4. Decidir con el usuario el push a GitHub y avisar al propietario: agregar `MEDGEMMA_API_KEY` a su `.env`.

## Cómo arrancar
- App (desde la terminal del usuario, para el login interactivo): `.venv\Scripts\python.exe -m streamlit run app.py`
- Si el token de Power BI venció: `.venv\Scripts\python.exe -m src.providers.powerbi_token login`
  (el usuario escribe el código en https://login.microsoft.com/device con la cuenta del propietario).
- Pruebas por navegador: Playwright para Python con Edge (`channel="msedge"`); no hay Node para el MCP.

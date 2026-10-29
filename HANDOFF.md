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
| Botón «Abrir en Power BI ›» (43 modelos, 382 páginas) | `sync_powerbi_links.py`, `src/providers/powerbi_links.py`, `app.py`, `data/catalog/report_links.json`; paso opcional en `update_rag.py` (`--skip-links`) |
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

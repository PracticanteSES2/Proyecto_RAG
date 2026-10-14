# Arnés realista con Power BI simulado (`tests/realistic`)

Ejecuta el sistema REAL (`app.py` → `build_system()`, `HybridRetriever`, `PowerBIProvider`,
`QueryPlanBuilder`, `QueryEngine`...) con **todo real excepto Power BI**:

| Componente | En este arnés |
| --- | --- |
| Catálogos (`data/catalog`, `data/rag`), Qdrant y embeddings | **reales** (`data/` del checkout principal, copiado a una caché) |
| MedGemma (Ollama) | real con `llm="real"` (lee el `.env` con el `load_dotenv` de `app.py`) o el Ollama falso de `tests/sim` con `llm="fake"` |
| Power BI (XMLA / pyadomd / `clr`) | **simulador** `powerbi_sim` detrás de un cliente ADOMD falso: `PowerBIProvider` corre sin cambios |

`tests/sim` sigue igual (modelos pequeños, todo falso). Ambos comparten el cliente ADOMD falso
`tests/common/adomd.py`.

## Uso rápido (desde la raíz del repo)

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8    # PowerShell: $env:PYTHONDONTWRITEBYTECODE=1

# Chat por consola: respuesta de la UI, botones de contrapregunta y razonamiento
python -m tests.realistic.chat "¿Cuántos egresos hubo en 2025?"
python -m tests.realistic.chat "¿Cuántos egresos hubo en 2025?" --then 2 --dax   # pulsa el botón 2 y muestra la DAX
python -m tests.realistic.chat "cirugías realizadas en 2024" --then __none__     # «Ninguna de las anteriores»
python -m tests.realistic.chat "total atenciones" --llm real                     # MedGemma real
python -m tests.realistic.chat                                                   # modo interactivo

# App Streamlit real con Power BI simulado
python -m tests.realistic.run_app                  # o: streamlit run tests/realistic/run_app.py -- --llm real
python -m tests.realistic.run_app --llm real --port 8502

# Pruebas del simulador (sin data/, Qdrant ni Ollama)
python -m tests.realistic.test_powerbi_sim

# Banco de preguntas con este arnés
python -m tests.eval.run --harness realistic --llm fake
python -m tests.eval.run --harness realistic --llm real --case e_total_atenciones,i_opcion_por_boton
```

Latencia de Power BI real: `SIM_DAX_LATENCY_MS=500` (o `adomd.install(..., latency_ms=500)`) hace que el
simulador espere ese tiempo en cada consulta DAX (`dax_log[i]["latency_ms"]`). Para contar consultas por turno
en todo el banco sin esperar: `python -m tests.perf.medir_consultas --out antes.json [--frio]` y
`--comparar antes.json despues.json` (respuestas por caso, consultas/turno y tiempo estimado).

Modelo de coste (`powerbi_sim/cost.py`, `SIM_DAX_COST=1`): además de la latencia base, cada rama
`VALUES(T[c])` de una consulta de dominio cuesta según la cardinalidad «real» estimada de la columna
(identificadores y columnas casi únicas escalan con `SIM_DAX_ESCALA`; categóricas = sus valores del
simulador; `SIM_DAX_CARDINALIDAD="TABLA[COL]=N;..."` fija valores) y `COUNTROWS(VALUES())` es barato.
Calibrado con el turno real del propietario (lote de 9 columnas = 20,8 s). Con `SIM_DAX_LATENCY_MS > 0`
duerme ese coste (para ver el razonamiento en vivo); sin dormir, `dax_log[i]["cost_ms"]` lo registra y
`medir_consultas` lo suma. Un `CommandTimeout` menor que el coste cancela la consulta como ADOMD.

Opciones del chat: `--then` (repetible: número de botón, `__none__`/`ninguna` o texto), `--dax`,
`--no-reasoning`, `--no-synthetic`, `--no-patches`, `--excluir-sintetico SLUG`, `--powerbi-down`,
`--data-root RUTA`, `--culture es-CO|en-US|invariant`.

## API del arnés (igual que `tests/sim/harness.py`)

```python
from tests.realistic import harness
engine, cm, formatter, llm_status, powerbi_connection, dax_log = harness.build_engine(llm="fake")
result, ui = harness.ask(engine, cm, formatter, "¿Cuántas cirugías realizadas hubo en 2024?")
result, ui = harness.choose(engine, cm, formatter, option_id, label)   # botón (alias: ask_option)
harness.new_conversation(engine, cm)                                   # reset(full=True)
harness.run_case({"turns": ["...", "..."]}, engine, cm, formatter)
```

`result["_sim"]` trae `dax_log` (cada consulta: modelo, DAX, filas, resultado, error),
`type_mismatch`, `approximate` (medidas evaluadas con valor de respaldo), `errors`, `warnings`,
`exception`, `traceback` y `stdout`.

`build_engine(data_root=None, llm="fake"|"real"|"down", powerbi_up=True, synthetic=None, today=None,
culture="es-CO", net_types=True, default_model=None, env_file=None, tableros_root="auto")`:

- **data_root**: parámetro → `SIM_DATA_ROOT` → `<repo>/data` → `<checkout principal>/data` (en un
  `git worktree` se deduce de `.git`). Debe tener `catalog/source_registry.json`, `rag/`,
  `vector_db/qdrant` y `model_metadata/`.
- **Nunca se escribe en `data_root`**: se copia (sin `knowledge_chunks.json`/`semantic_knowledge.json`)
  a `%TEMP%/proyecto_rag_sim/<hash>/root/data` (o `SIM_CACHE_DIR`); Qdrant local crea su `.lock` en la copia.
  La caché se reconstruye sola cuando cambian `data/`, el overlay o `overlay.py`.
- **synthetic** (por defecto activado; `SIM_SYNTHETIC=0` lo desactiva): agrega los modelos sintéticos.
  **synthetic_exclude** (`SIM_SYNTHETIC_EXCLUDE=tablero_gestion_camas,...`) quita algunos.
- **patches** (por defecto activado; `SIM_PATCHES=0` lo desactiva): aplica `catalog_patches.py` (ver abajo).
- **llm="real"**: el `.env` del checkout principal se carga ejecutando el bloque `try/load_dotenv`
  de `app.py`. Si no existe, `llm_status["sim_note"]` lo dice y MedGemma queda `unavailable`. Si el
  servidor no responde, `llm_status["status"] != "ready"` (y la app sigue sin descripciones LLM).
  Las variables `POWERBI_*`, `ADOMD_PATH`, `IDENTITY_PATH` del `.env` se ignoran (gana el simulador).
  Nunca se imprimen valores del `.env`.
- `HF_HUB_OFFLINE=1` por defecto (el modelo de embeddings ya está en caché; pon `HF_HUB_OFFLINE=0`
  si hay que descargarlo).
- Qdrant local no admite dos clientes sobre la misma carpeta: no corras dos procesos del arnés
  (o la app y el arnés) sobre la misma caché a la vez.

## El simulador (`powerbi_sim/`)

| Módulo | Qué hace |
| --- | --- |
| `metadata.py` | Lee `data/model_metadata/<slug>/{tables,columns,measures,relationships}.csv` (INFO.VIEW.*; coma o `;`, cabeceras con o sin `[ ]`) y el overlay; nombre del modelo desde `model_registry.json` → `_metadata_sync.json` → slug. |
| `datagen.py` | Datos sintéticos deterministas (semilla por modelo/tabla/mes), 2023-01-01 → ayer. Calendarios con su expresión DAX real (`CALENDAR(...)`, `LocalDateTable_*`), dimensiones con claves 1..N o dominio, hechos por mes con FK sesgadas a las dimensiones, AÑO/MES coherentes con la fecha, ~1.5 % de blancos, columnas calculadas evaluadas con su DAX si es barata. |
| `domains.py` | Dominios en español clínico (especialidades, servicios, aseguradoras, triage, grupo etario MENORES/MAYORES DE EDAD, áreas de lavandería, códigos para columnas OID...). Cosecha literales de las propias medidas (`T[C] = "X"`, `IN {...}`, `SWITCH(SELECTEDVALUE(...))`), de `model_metadata/<slug>/_documented_values.json` (valores `CASE/IN` del SQL documentado y literales DAX, generado por `tools/local_data`) y, si existe `tableros/`, de los filtros de los `visual.json` (solo en memoria, no se versiona). Personas/documentos: siempre etiquetas sintéticas (`PACIENTE SIMULADO 00042`, `PROFESIONAL 07`). |
| `dax_parser.py` / `dax_eval.py` | Analizador y evaluador DAX con contexto de filtro, contexto de fila, transición de contexto, propagación por relaciones (1→N, ambas direcciones, 1:1, inactivas + `USERELATIONSHIP`), tabla expandida en `ALL(tabla)`. |
| `engine.py` | `PowerBISimulator`: workspace con todos los modelos; `execute(modelo, dax)` → columnas/filas + `approximate`, `type_mismatch`. |
| `adomd.py` | Lo conecta a `tests/common/adomd.py` (módulos `clr` y `Microsoft.AnalysisServices.AdomdClient`). |

### DAX soportado

- Consultas: `DEFINE MEASURE/VAR`, `EVALUATE`, `ORDER BY ... ASC|DESC`; `INFO.VIEW.TABLES/COLUMNS/MEASURES/RELATIONSHIPS()`
  (lo que usa `sync_powerbi_metadata.py`) y `DBSCHEMA_CATALOGS`.
- Tablas: `ROW`, `SUMMARIZECOLUMNS` (grupos de varias tablas, filtros, BLANK como grupo, quita filas en blanco),
  `SUMMARIZE`, `SELECTCOLUMNS`, `ADDCOLUMNS`, `TOPN` (con empates), `FILTER`, `VALUES`, `DISTINCT`, `ALL`,
  `ALLNOBLANKROW`, `REMOVEFILTERS`, `ALLEXCEPT`, `ALLSELECTED` (aprox.), `CALCULATETABLE`, `TREATAS` (también pares
  `{(2024, 11), (2025, 1)}`), `KEEPFILTERS`, `UNION`, `EXCEPT`, `INTERSECT`, `CROSSJOIN`, `GENERATE`, `GENERATESERIES`,
  `DATATABLE`, `CALENDAR`, `CALENDARAUTO`, `RELATEDTABLE`, constructores `{...}`.
- Contexto: `CALCULATE` (orden real: argumentos → transición → modificadores → filtros; reemplazo vs `KEEPFILTERS`;
  filtrar la fecha clave de un calendario quita los demás filtros del calendario, como DAX), `USERELATIONSHIP`,
  `SELECTEDVALUE`, `HASONEVALUE`, `ISFILTERED`, `ISCROSSFILTERED`, `RELATED`, `LOOKUPVALUE`.
- Agregaciones: `SUM`, `AVERAGE`, `MIN`, `MAX`, `COUNT`, `COUNTA`, `COUNTBLANK`, `COUNTROWS`, `DISTINCTCOUNT`,
  `MEDIAN` y las X (`SUMX`, `AVERAGEX`, `MINX`, `MAXX`, `COUNTX`, `MEDIANX`, `CONCATENATEX`, `RANKX`),
  `FIRSTNONBLANK/LASTNONBLANK`.
- Tiempo: `DATEADD`, `SAMEPERIODLASTYEAR` (meses completos, 29-feb), `PARALLELPERIOD`, `PREVIOUSMONTH/YEAR/QUARTER/DAY`,
  `NEXTMONTH/YEAR`, `DATESYTD/MTD/QTD`, `TOTALYTD/MTD/QTD`, `DATESBETWEEN`, `DATESINPERIOD`, `FIRSTDATE`, `LASTDATE`,
  `STARTOF/ENDOF MONTH/QUARTER/YEAR`, jerarquía automática `'T'[Fecha].[Año]`.
- Escalares: aritmética y comparación DAX (BLANK, texto sin mayúsculas), `IN`, `&&`, `||`, `NOT`, `VAR/RETURN`,
  `IF`, `SWITCH` (incl. `SWITCH(TRUE(), ...)`), `DIVIDE`, `COALESCE`, `ISBLANK`, `IFERROR`, fechas (`DATE`, `YEAR`,
  `MONTH`, `DAY`, `TODAY`, `NOW`, `EOMONTH`, `EDATE`, `DATEDIFF`, `WEEKDAY`...), texto (`FORMAT` con cultura es-ES,
  `LEFT`, `SEARCH`, `CONTAINSSTRING`, `UPPER`, `TRIM`...), matemáticas (`ROUND`, `INT`, `MOD`...).

### Aproximaciones

- Funciones no implementadas (`EARLIER`, `PATH*`, `WINDOW/OFFSET/INDEX`, `GROUPBY`, `CROSSFILTER`, estadísticas...)
  y cualquier fallo interno **dentro de una medida del modelo** ⇒ valor de respaldo determinista proporcional a las
  filas visibles de la tabla de la medida (respeta filtros): porcentaje, promedio, dinero o conteo según nombre/formato.
  Queda en `result["_sim"]["approximate"]` (`--dax` lo muestra con `~`).
  Con la metadata real de TABLERO DE ATENCIONES INSTITUCIONALES: 3 de 146 medidas.
- Si el mismo problema está en la DAX de la **consulta** (la que genera el chatbot) se devuelve error; si es una
  limitación del simulador el mensaje empieza con `[sim]`.
- `ALLSELECTED` usa los filtros de la consulta (`SUMMARIZECOLUMNS`) como contexto «seleccionado».
- Las columnas calculadas costosas (con `CALCULATE`, iteradores o medidas) se generan como datos sintéticos.
- La fila en blanco de las dimensiones (FK sin dimensión) no se materializa en `VALUES(dim[col])`.

### Errores como ADOMD

`AdomdErrorResponseException` con el texto de Power BI: `Query (L, C) Cannot find table 'X'.`,
`Column 'C' in table 'T' cannot be found or may not be used in this expression.`,
`The value for 'M' cannot be determined...`, `Failed to resolve name 'F'...`, `The syntax for 'x' is incorrect.`,
`DAX comparison operations do not support comparing values of type Text with values of type Integer...`,
`A single value for column ... cannot be determined...`, `The expression specified in the query is not a valid table
expression.`, base de datos inexistente al abrir la conexión y `AdomdConnectionException` con `powerbi_up=False`.
Comparar fecha con número no falla (como DAX) pero devuelve vacío y se registra `TYPE MISMATCH`; igual `TREATAS`
con un tipo distinto al de la columna.

### Tipos .NET

Como pythonnet: `System.DateTime` y `System.Decimal` llegan como objetos y `PowerBIProvider` los convierte con
`str()`, que usa la cultura de Windows (es-CO en el equipo del proyecto): `"1/01/2023 12:00:00 a. m."`, `"1234567,5"`.
`culture="en-US"|"invariant"` o `net_types=False` para comparar.

## Modelos sintéticos y redundancia

`tests/realistic/synthetic_models/` (versionado; se regenera con `python -m tests.realistic.build_synthetic_models`)
contiene 4 modelos con nombres reales del workspace y tablas/medidas inventadas que reutilizan nombres de los reales:

| Modelo | Tablas | Medidas redundantes |
| --- | --- | --- |
| CONSOLIDADO DE ATENCIONES INSTITUCIONALES | Calendario, ASEGURADORAS, DIM_SERVICIO, EGRESOS, CIRUGIAS, CONSULTA_URGENCIAS, PORCENTAJE_OCUPACIONAL | Total Atenciones, Total Egresos, Egresos, Cirugías realizadas, TOTAL_CIRUGIAS, Total_consultas_urgencias, % Ocupación, PROMEDIO_ESTANCIA |
| INFORMES EJECUTIVOS 2026 | Calendario, DIM_SEDE, FACT_INDICADORES, FACT_OCUPACION | Total Atenciones, Egresos, Cirugías realizadas, Consultas, % Ocupación |
| TABLERO GESTION CAMAS | Calendario, CAMAS, OCUPACION_DIARIA, EGRESOS, SOLICITUD_CAMAS | % Ocupación, Egresos, Total Egresos, Promedio Estancia, Giro Cama |
| TABLERO CONSULTA EXTERNA | Calendario, ASEGURADORAS, CONSULTAS_AMBULATORIAS | Total Consultas, Consultas, Total Atenciones, % Inasistencia |

`overlay.py` los integra con el pipeline real del proyecto en la copia de `data/`: metadata en `model_metadata/`,
manifiesto en `raw/<grupo>/`, PBIR mínimo (generado desde `source.json`) en `pbir/`, `PowerBICatalogManager.run()`
(catálogos técnico/visual/maestro), registros fusionados y chunks de su documentación embebidos en la copia de Qdrant.
Si el `data/` real ya trae un modelo con el mismo slug, gana el real.

Ejemplo: «¿Cuántos egresos hubo en 2025?» ofrece EGRESOS (BRIEFING HOSPITALARIO), Egresos (INFORMES EJECUTIVOS 2026),
Egresos (TABLERO GESTION CAMAS), Total Egresos (CONSOLIDADO...) y «Ninguna de las anteriores».

## Parches sobre modelos reales (`catalog_patches.py`)

El `data/` local es una instantánea más antigua que la del propietario. Para reproducir sus pruebas con usuarios del
hospital (2026-10-14) el overlay agrega a la COPIA de `data/` solo lo que su catálogo tiene y el local no:

| Modelo | Qué se agrega |
| --- | --- |
| BRIEFING HOSPITALARIO | %OCUPACION y CamasFiltradas en INICIO (visual «%OCUPACIÓN»: CamasFiltradas coincide por ese alias), %OCUPACION y la medida CAMAS en GESTIÓN CAMAS (la página local «GESTIÓN DE CAMAS» se renombra; matriz SERVICIOS × ESTADOS_CAM supuesta), visual «PACIENTES por ASEGURADORA» (DISTINCTCOUNT(ADNINGRESO) por TERNOMCOM) en INICIO y **filas fijas** de CAMAS DISPONIBLES (72 camas: HOSPITALIZACIÓN GENERAL, HOSPITALIZACIÓN INTERMEDIOS, UCI ADULTOS, PEDIATRÍA, GINECOBSTETRICIA, URGENCIAS) y PACIENTES X ASEGURADORA (43 pacientes, uno por cama ocupada, con su EPS) |
| DEMANDA INSATISFECHA | HOSPITALIZACIÓN = SUM(DEMANDA_INS) (CONSOLIDADO y SOLICITUD CAMAS), TOTAL_SOLICITUD_CAMAS, TERCEROS[TERNOMCOM] (la tabla local sigue llamándose SOLICITUD_CAMAS) |
| TABLERO EPS | %OCUPACIONALC (tabla %OCUPACIONAL) en TRIAGES ATENDIDOS, tarjeta «Ocupación de urgencias» |
| TABLERO FARMACIA | Solo **filas fijas** (sin tocar el informe ni reconstruir su catálogo): PRODUCTOS_VENCIDOS (5 productos, 79 unidades) y VENCIMIENTO_PRODUCTOS (3 con `mes <= 1`, el filtro de la tarjeta «0-30 DÍAS», y 3 con `mes` 2-4) para los listados de los casos `v_listado_*` |

Cómo: agrega filas a `model_metadata/<slug>/*.csv` de la copia, escribe `_sim_tables.json` y, si el parche
tiene páginas (`pages`/`rename_pages`), copia el PBIR original
(sin `.pbi`) a la caché, le agrega/renombra páginas y visuales y escribe `raw/<grupo>/manifest.json`:
`PowerBICatalogManager.run()` reconstruye los catálogos técnico/visual y las métricas maestras de esos grupos (el
resto del catálogo queda igual). Lo hecho queda en `data/catalog/patches_report.json` de la caché.

El modelo sintético TABLERO GESTION CAMAS («% Ocupación», «Camas disponibles») no existe en el catálogo del propietario
y cambia sus contrapreguntas (ofrece «Camas disponibles» y desvía «qué camas...» a su documentación): los casos del
hospital en `tests/eval/questions.json` lo quitan con `"arnes_opciones": {"excluir_sintetico": ["tablero_gestion_camas"]}`
(en el chat: `--excluir-sintetico tablero_gestion_camas`).

### Filas fijas en el simulador (`<slug>/_sim_tables.json`)

`{"tables": {"TABLA": {"columns": [...], "rows": [[...], ...]}}}` junto a la metadata de un modelo: esas tablas usan
exactamente esas filas (fechas `AAAA-MM-DD` o `today`, `today-3`, `today+2`); las columnas de datos que falten se
generan como siempre y las calculadas se evalúan con su DAX (ESTADOS_CAM, OCUPADAS, MOSTRAR). Así un detalle
(`SUMMARIZECOLUMNS('CAMAS DISPONIBLES'[SERVICIOS], 'CAMAS DISPONIBLES'[HCACODIGO], TREATAS({"DISPONIBLE"}, ...))`) y
su conteo filtrado coinciden (6 camas disponibles en HOSPITALIZACIÓN GENERAL: 403, 407, 411, 415, 419, 422).

## Garantías

- No modifica `src/`, `app.py` ni `data/` (todo se escribe en la caché temporal).
- No abre `tableros/*/.pbi/cache.abf`; de los PBIR solo lee literales de filtros (sin columnas de personas).
- El `.env` solo se carga con `llm="real"` y nunca se imprime.

# Evaluador del chatbot (`tests/eval`)

Banco de preguntas realistas + runner que ejecuta cada caso contra el chatbot (vía un arnés offline), evalúa
expectativas tolerantes y mide calidad y latencia. Produce `report.md` (legible) y `report.json` (completo).

| Archivo | Qué es |
| --- | --- |
| `questions.json` | Banco de ~120 casos en español (coloquial, sin tildes, con errores de tipeo, «necesito saber...») |
| `run.py` | Runner: `python -m tests.eval.run ...` |
| `expectations.py` | Traduce el bloque `expect` de cada turno en comprobaciones + prohibiciones por defecto |
| `quality.py` | Métricas de calidad (palabras clave, cifras sin respaldo, idioma, longitud, términos internos) y gancho de juez LLM |
| `report.py` | Escribe `report.md` / `report.json` |
| `test_eval.py` | Pruebas del propio evaluador |

## Cómo ejecutar (desde la raíz del repo)

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8      # PowerShell: $env:PYTHONDONTWRITEBYTECODE=1; $env:PYTHONIOENCODING="utf-8"

python -m tests.eval.run --harness sim                       # arnés tests/sim (fixtures pequeños)
python -m tests.eval.run --harness sim --solo-aplicables --strict   # solo los casos de sim; exit 1 si hay fallos nuevos
python -m tests.eval.run --harness realistic --llm fake      # arnés tests/realistic (datos reales, LLM falso)
python -m tests.eval.run --harness realistic --llm real      # ... con MedGemma real (Ollama local)
python -m tests.eval.run --harness sim --llm down            # LLM caído (RAG extractivo)
python -m tests.eval.run --category e_ambiguo --category i_multiturno
python -m tests.eval.run --case i_opcion_por_boton,c_sim_lav_antifluidos_ene2026
python -m tests.eval.run --list                              # lista casos (marca los xfail del arnés)
python -m tests.eval.run --out C:/ruta/fuera/del/repo        # carpeta de salida
python -m tests.eval.run --harness realistic --excluir-sintetico tablero_gestion_camas   # sin ese modelo sintético

python -m tests.eval.test_eval                               # pruebas del evaluador
```

`--case` admite patrones (`fnmatch`): `--case "v_*"`, `--case "*hospital*,v_*"`.

### Solo los casos del hospital y sus variantes (integración)

Los casos de la prueba con usuarios del hospital (2026-10-14: ids con `hospital` más
`d_pacientes_observados_por_aseguradora`) y sus variantes de generalidad (`v_*`, otros tableros con las mismas
formas de respuesta) se ejecutan juntos en ~2 grupos de motor:

```bash
python -m tests.eval.run --harness realistic --llm fake --quiet \
    --case "*hospital*,d_pacientes_observados_por_aseguradora,v_*" --out tests/eval/out/hospital
```

PowerShell: `python -m tests.eval.run --harness realistic --llm fake --quiet --case "*hospital*,d_pacientes_observados_por_aseguradora,v_*" --out tests/eval/out/hospital`.
El resumen final cuenta pasan / XFAIL / XPASS: un XPASS es un arreglo que ya funciona (quita su `xfail`).
Las variantes `v_*` se agrupan por forma de respuesta:

| Prefijo | Qué prueba |
| --- | --- |
| `v_escalar_*` | Un solo valor con palabras de alcance («en el hospital», «general», «institucional», «todo el hospital»): no son filtros |
| `v_agrupado_*` | «por X» / «detalle de M por X» con nombres en plural o flexionados (servicios, especialidades, aseguradoras) |
| `v_relacion_*` | La única columna válida para agrupar está en otra tabla relacionada; nunca una tabla sin relación (mismo valor en cada fila) |
| `v_sin_dimension_*` | La dimensión no existe para esa medida: debe decirlo nombrándola, sin tabla con valores repetidos |
| `v_listado_*` | «cuántos… y cuáles», «lista de…», «qué… están/hay»: total + listado con columnas de negocio, sin datos personales |
| `v_control_*` | Controles negativos: deben seguir siendo un solo valor aunque la tarjeta esté en una página «DETALLE…» |

Salida por defecto: `tests/eval/out/<arnés>-<fecha>/` (ignorada por git). Con datos reales el informe puede
contener cifras y nombres del modelo: no lo subas al repositorio ni lo compartas fuera.

El arnés se importa de forma perezosa: `--harness realistic` necesita `tests/realistic/harness.py` con la misma API
que `tests/sim/harness.py` (`build_engine(...)` → `(engine, cm, formatter, llm_status, powerbi_connection, dax_log)`,
`ask`, `new_conversation`). A `build_engine` solo se le pasan los argumentos que acepte (`llm`, `ollama_up`, `quiet`).

### Línea base con la data TMDL real (2026-10-29, `--llm fake`)

`data/` reconstruido con `tools/local_data` desde los PBIP de `tableros/` (15 modelos TMDL; los informes
sin visuales se completan con la documentación, ver `tools/local_data/README.md`). PowerShell, desde la raíz:

```powershell
$env:PYTHONDONTWRITEBYTECODE=1; $env:PYTHONIOENCODING="utf-8"
$env:SIM_DATA_ROOT="<ruta>\data"; $env:SIM_CACHE_DIR="<caché propia por corrida>"
python -X utf8 -m tests.eval.run --harness realistic --llm fake --out <carpeta fuera del repo>
```

| Data | Aplicables (158) |
| --- | --- |
| Anterior (respaldo 2026-10-28, metadata inferida) | 136 pasan, 21 fallan, 1 XFAIL (3 XPASS: los xfail de abajo) |
| TMDL real sin completar informes (`data/` del 2026-10-28) | 89 pasan, 68 fallan |
| **TMDL real + informes completados (línea base)** | **116 pasan, 38 fallan, 4 XFAIL** |

Regresiones frente a la data anterior (19), por causa:
- Varios indicadores con el mismo nombre o casi en el modelo real y el chatbot contrapregunta en vez de
  elegir el que pide la pregunta (`TRIAGES PEDIATRICOS 2025` frente a sus promedios, `CANCELADAS`, `MONTO
  FACTURADO POR ÁREA DE SERVICIO`, `PACIENTES por ASEGURADORA`, `PACIENTES OBSERVADOS` frente a `... POR MES`,
  tiempos de triage, «cantidad de pacientes» por especialidad). Afecta a `b_triages_pediatricos_2025`,
  `b/d_cirugias_canceladas_*`, `d_naos_por_servicio`, `d_hospital_pacientes_por_aseguradora`,
  `d_pacientes_observados_por_aseguradora`, `v_escalar_*`, `v_agrupado_facturado_por_areas`,
  `v_agrupado_pacientes_por_especialidad`, `v2_triage_por_eps_no_es_facturacion` y los
  `i_*especialidad*`/`i_ctx_propietario_mes_pasado`. Es un problema del resolutor de indicadores
  (`metric_resolver`/`query_engine`).
- Fuera de alcance (`g_consejo_clinico`, `g_codigo`): con los nombres de los visuales reales («PACIENTES»,
  «… POR DÍA», «PRODUCTOS POR DEBAJO DE INVENTARIO MINIMO») hay candidatos y se contrapregunta en vez de
  responder fuera de alcance.
- `i_hospital_camas_disponibles_boton`: el total (6) es correcto, pero no lista las camas.
  `h_participacion_nueva_eps`: vacío con ASEGURADORA = NUEVA EPS. `v_agrupado_referencia_por_especialidades`:
  va a RAG aunque la página inferida tiene «Cantidad de solicitudes» por GEEDESCRI.

XFAIL con el motivo verificado en el TMDL/PBIR real: `a_naos_pacientes_pendientes`, `a_cvc_compras_aumento`,
`i_ninguna_boton_y_elige` (con la data anterior salen como XPASS). MedGemma no respondía el 2026-10-29: no
hay línea base `--llm real`.

## Qué hace con cada caso

1. Conversación nueva (`harness.new_conversation`).
2. Cada turno es un texto (`harness.ask`, igual que `engine.process`) o la pulsación de un botón de la contrapregunta
   anterior (`engine.select_clarification_option(id, label)`, como `app.py`). Si el arnés define `ask_option` se usa
   esa función; si no, se envuelve el motor para que `harness.ask` ejecute la selección.
3. Mide la latencia del turno, evalúa las expectativas y las métricas de calidad y guarda el razonamiento completo
   (`format_reasoning_text(result["reasoning"], respuesta)`).
4. Un caso pasa si pasan todos sus turnos. Si un turno pide un botón que no apareció, el caso falla y los turnos
   siguientes se marcan como omitidos (el runner nunca se cae por un caso).

## Formato del banco (`questions.json`)

```json
{
  "id": "i_opcion_por_boton",
  "category": "i_multiturno",
  "tablero": "Atenciones Institucionales",
  "fuente": {"docx": "5 DOCUMENTACION TABLERO .../11 Documentacion Tablero Cirugias.docx", "seccion": "Cirugías realizadas"},
  "arneses": ["sim", "realistic"],
  "xfail": {"sim": "motivo del bug conocido"},
  "descripcion": "opcional",
  "turns": [
    {"user": "¿Cuántas cirugías realizadas hubo en 2024?",
     "expect": {"route": ["clarification"], "options_any": ["realizad"], "has_none_option": true}},
    {"button": 2, "expect": {"route": ["powerbi"], "metrics_any": ["realizad"], "filters": [{"year": 2024}]}}
  ]
}
```

- `fuente.docx`: relativo a `Documentacion/DOCUMENTACION TABLERO/` (no versionado). Las palabras clave salen de ahí.
- `arneses`: en qué arnés se espera que el caso funcione. Con `sim` solo apuntan a los fixtures de `tests/sim`
  (Atenciones/Quirúrgico/Lavandería falsos); el resto se ejecuta igual (vigila excepciones, «None», términos
  internos) pero su fallo es esperado y va en una sección aparte del informe.
- `xfail`: comportamiento deseado que hoy falla por un bug real del chatbot (como en `tests/sim/test_smoke.py`).
  No cuenta para `--strict`; si empieza a pasar sale como **XPASS**: quita la marca.
- Turnos: `{"user": "texto"}` o `{"button": ...}` con `1` (primer botón, 1-based), `"none"` («Ninguna de las
  anteriores»), un texto contenido en la etiqueta o `{"label_any": [...]}` / `{"id": "..."}`. Con `"opcional": true`
  el botón solo se pulsa si el turno anterior contrapreguntó («si contrapregunta, al elegir X la respuesta es Y»);
  si respondió directamente, el turno no aplica y no falla.
- `arnes_opciones`: `{"excluir_sintetico": ["tablero_gestion_camas"]}` quita modelos sintéticos del arnés realista para
  ese caso (los casos se agrupan por opciones y cada grupo construye su motor). Lo usan los casos del hospital
  (2026-10-14) para reproducir el catálogo del propietario.

Categorías: `a_kpi_simple`, `b_kpi_periodo`, `c_kpi_filtro`, `d_agrupado`, `e_ambiguo` (debe contrapreguntar),
`f_documental`, `g_fuera_alcance`, `h_compuesta`, `i_multiturno`.

### Expectativas (`expect`, todas opcionales y tolerantes)

| Clave | Significado |
| --- | --- |
| `route` | Tipos aceptables del turno: `powerbi`, `powerbi_empty`, `rag`, `clarification`, `out_of_scope`, `not_found`, `metric_not_resolved`, `unsupported_filter`, `powerbi_error`, `error` |
| `status` | Estados crudos aceptables (`result["status"]`) |
| `metrics_any` / `models_any` | Alguna etiqueta/id/medida, título de su visual, nombre con que coincidió o tabla de la medida (o modelo/informe/página) contiene alguno de los textos (sin tildes ni mayúsculas) |
| `filters` | Lista de `{"column": "SERVICIO", "value": "ANTIFLUIDOS"}` (columna opcional) o `{"year": 2026, "month": 1}` (`"year": "actual"`/`"anterior"` = año en curso/pasado). Acepta `AÑO`/`MES` enteros, el mes en texto (`NOMBRE_MES = 'abril'`, `MES = 'ABRIL'`), `date_range` o el DAX. Un filtro no aplicado pero declarado en la respuesta («No pude aplicar: ...») cuenta como válido salvo `"allow_declared_filters": false` |
| `group_by_any`, `result_type` | Agrupación (`servicio`, `turno`...; también la tabla de la columna) y `table`/`scalar` |
| `table_columns`, `table_min_rows` | Tabla de detalle: cada elemento (texto o lista de alternativas, p. ej. `["cama", "HCACODIGO"]`) está en algún encabezado de una tabla de la respuesta (markdown) o en las columnas del resultado; nº mínimo de filas |
| `numbers` | Cifras que deben aparecer en la respuesta (acepta 488,3 / 3.906,4 / 12,5 %) |
| `answer_any` / `answer_all` / `answer_none` | Textos en la respuesta mostrada |
| `keywords`, `min_keyword_coverage` | Palabras clave del docx que debe cubrir una respuesta documental (por defecto 50 %) |
| `options_any`, `options_all`, `min_options`, `has_none_option`, `prompt_any` | Contrapreguntas: algún botón contiene alguno de los textos / cada texto está en algún botón (p. ej. ofrece ambos tableros), nº de opciones, «Ninguna de las anteriores», texto de la pregunta |
| `filters_none` | Filtros que NO deben aplicarse (`{"value": "GENERAL"}`, `{"column": "SERVICIOS"}`): palabras de alcance como «general» o «del hospital» no son valores de una columna |
| `forbid` / `allow` | Agregar o quitar prohibiciones |

Las comprobaciones que no aplican (p. ej. la métrica de un turno que terminó en contrapregunta) se marcan «no aplica»
y no cuentan: el fallo ya lo reporta `route`.

### Prohibiciones

Siempre activas: `none_text` (la UI muestra «None»), `exception`, `internal_terms` (chunk, embedding, Qdrant, prompt,
Ollama...), `empty_answer`, `invented_numbers` (solo RAG: cifras de la respuesta que no están en las fuentes
recuperadas ni en la pregunta), `english` (respuestas largas que no parecen español) y `total_without_filter`
(dio un dato de Power BI sin aplicar ni avisar un filtro esperado). Opcionales: `numbers` (no debe dar cifras),
`powerbi_answer` (no debe responder con un dato), `generic_failure` (mensaje genérico de error) y `constant_table`
(tabla de 3 o más filas con el mismo valor en todas: se agrupó por una columna que no filtra la tabla de la medida).

## Métricas de calidad

Por turno (en `report.json` y en el detalle de cada fallo): longitud, cobertura de palabras clave, cifras sin respaldo
en las fuentes (posible alucinación), proporción de español, términos internos, nº de fuentes y modo de síntesis.
`report.md` agrega por categoría el % de casos y de comprobaciones que pasan, y la latencia media y p95.

### Juez LLM (opcional, desactivado)

`--judge paquete.modulo:funcion` carga una función `juez(caso, turno, result, ui) -> {"score": 0..1, "comment": str}`
que se llama en cada turno y se promedia en el informe. No hay ningún juez por defecto: nada se envía a un servicio
externo salvo que se implemente y se pida explícitamente (usar un LLM local).

## Cómo agregar un caso

1. Busca el indicador en el docx del tablero y anota archivo y sección en `fuente`.
2. Escribe la pregunta como la haría el personal (coloquial, sin tildes...) y expectativas tolerantes (listas).
3. Marca `arneses` (`["realistic"]` si depende de datos reales; agrega `"sim"` solo si los fixtures de `tests/sim`
   lo cubren).
4. Pruébalo: `python -m tests.eval.run --harness sim --case mi_caso` y revisa `report.md`.
5. Si describe un bug real que hoy falla, agrega `"xfail": {"<arnés>": "motivo"}`.

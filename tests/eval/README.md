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

python -m tests.eval.test_eval                               # pruebas del evaluador
```

Salida por defecto: `tests/eval/out/<arnés>-<fecha>/` (ignorada por git). Con datos reales el informe puede
contener cifras y nombres del modelo: no lo subas al repositorio ni lo compartas fuera.

El arnés se importa de forma perezosa: `--harness realistic` necesita `tests/realistic/harness.py` con la misma API
que `tests/sim/harness.py` (`build_engine(...)` → `(engine, cm, formatter, llm_status, powerbi_connection, dax_log)`,
`ask`, `new_conversation`). A `build_engine` solo se le pasan los argumentos que acepte (`llm`, `ollama_up`, `quiet`).

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
  anteriores»), un texto contenido en la etiqueta o `{"label_any": [...]}` / `{"id": "..."}`.

Categorías: `a_kpi_simple`, `b_kpi_periodo`, `c_kpi_filtro`, `d_agrupado`, `e_ambiguo` (debe contrapreguntar),
`f_documental`, `g_fuera_alcance`, `h_compuesta`, `i_multiturno`.

### Expectativas (`expect`, todas opcionales y tolerantes)

| Clave | Significado |
| --- | --- |
| `route` | Tipos aceptables del turno: `powerbi`, `powerbi_empty`, `rag`, `clarification`, `out_of_scope`, `not_found`, `metric_not_resolved`, `unsupported_filter`, `powerbi_error`, `error` |
| `status` | Estados crudos aceptables (`result["status"]`) |
| `metrics_any` / `models_any` | Alguna etiqueta/id/medida (o modelo/informe/página) contiene alguno de los textos (sin tildes ni mayúsculas) |
| `filters` | Lista de `{"column": "SERVICIO", "value": "ANTIFLUIDOS"}` (columna opcional) o `{"year": 2026, "month": 1}` (`"year": "actual"`/`"anterior"` = año en curso/pasado). Acepta `AÑO`/`MES` enteros, `date_range` o el DAX. Un filtro no aplicado pero declarado en la respuesta («No pude aplicar: ...») cuenta como válido salvo `"allow_declared_filters": false` |
| `group_by_any`, `result_type` | Agrupación (`servicio`, `turno`...) y `table`/`scalar` |
| `numbers` | Cifras que deben aparecer en la respuesta (acepta 488,3 / 3.906,4 / 12,5 %) |
| `answer_any` / `answer_all` / `answer_none` | Textos en la respuesta mostrada |
| `keywords`, `min_keyword_coverage` | Palabras clave del docx que debe cubrir una respuesta documental (por defecto 50 %) |
| `options_any`, `min_options`, `has_none_option`, `prompt_any` | Contrapreguntas: botones, nº de opciones, «Ninguna de las anteriores», texto de la pregunta |
| `forbid` / `allow` | Agregar o quitar prohibiciones |

Las comprobaciones que no aplican (p. ej. la métrica de un turno que terminó en contrapregunta) se marcan «no aplica»
y no cuentan: el fallo ya lo reporta `route`.

### Prohibiciones

Siempre activas: `none_text` (la UI muestra «None»), `exception`, `internal_terms` (chunk, embedding, Qdrant, prompt,
Ollama...), `empty_answer`, `invented_numbers` (solo RAG: cifras de la respuesta que no están en las fuentes
recuperadas ni en la pregunta), `english` (respuestas largas que no parecen español) y `total_without_filter`
(dio un dato de Power BI sin aplicar ni avisar un filtro esperado). Opcionales: `numbers` (no debe dar cifras),
`powerbi_answer` (no debe responder con un dato), `generic_failure` (mensaje genérico de error).

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

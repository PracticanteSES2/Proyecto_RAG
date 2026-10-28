# Documentación viva de tableros (`src/docs_md`)

Objetivo: que la documentación de cada tablero sea corta, estándar y se mantenga al día sin esfuerzo.
Quien cambia un tablero escribe una nota informal ("le subí el semáforo de egresos a 45 min");
MedGemma propone el cambio sobre la sección exacta del .md; una persona lo aprueba; el RAG se reindexa.

## Formato (un .md por página del tablero)

Ubicación: `docs_tableros/<source_group>/md/` (versionada en git), con el `manifest.json` del grupo en
`docs_tableros/<source_group>/`. `DOCS_MD_ROOT` cambia la raíz (pruebas); sin `docs_tableros/` se usa `data/raw`.
`_general.md` describe el tablero completo (bloque `General`, `pagina: GENERAL`, título `# GENERAL`; la ingesta lo publica con el nombre del informe); cada página de Power BI tiene su archivo.
La implementación de referencia es `formato.py` (`parsear`, `serializar`, `validar`, `aplicar_operaciones`).
Ejemplo completo: `tests/docs_md/fixtures/tablero_tiempos_urgencias/md/consultas_dia.md`.

Secciones y orden (las vacías se omiten, salvo Propósito e Historial):

| Página | General | Contenido |
|---|---|---|
| Propósito | Propósito | 2 a 4 líneas: qué muestra, para qué sirve, desde dónde se llega |
| Fuentes de datos | Fuentes de datos | una entrada por tabla u origen |
| Indicadores | — | una entrada por indicador: qué mide, unidad, cálculo (columna o DAX) |
| Visuales | — | una entrada por visual o grupo de visuales |
| — | Definiciones | términos y definiciones de tiempos compartidas por todo el tablero |
| Reglas de negocio | Reglas de negocio | filtros, exclusiones, semáforos, criterios |
| Observaciones | Observaciones | inconsistencias y puntos «Por confirmar» |
| Historial de cambios | Historial de cambios | lo escribe el sistema, nunca el modelo |

## Lineamientos de redacción (los sigue también MedGemma)

1. Cada entrada es `- **Nombre corto**: texto.` en una sola línea. El nombre identifica la entrada; no se repite en su sección.
2. Frases cortas, en español, en presente, terminadas en punto. Nada de adornos ("permite analizar el comportamiento…").
3. Todo tiempo dice su unidad (minutos u horas) y entre qué eventos se mide.
4. Los nombres técnicos van tal cual: páginas en MAYÚSCULAS como en Power BI, columnas como `TABLA[COLUMNA]`.
5. Una entrada por hecho. Si algo cambia, se modifica la entrada existente; no se agregan duplicados.
6. Lo que no se sabe se marca «Por confirmar»; no se inventa.
7. Sin datos de pacientes (nombres, documentos).

## Contratos entre módulos

| Módulo | Función | Responsable |
|---|---|---|
| `formato.py` | parsear / serializar / validar / aplicar_operaciones / diferencias | base (hecho) |
| `repositorio.py` | listar_tableros / listar_paginas / leer_pagina / guardar_pagina | base (hecho) |
| `actualizador.py` | proponer_cambio(nota, source_group, pagina=None, llm=None, cambios_pbip=None) -> Propuesta; aplicar_propuesta(propuesta, autor) | agente actualizador |
| `indexacion.py` | reindexar_grupo(source_group, qdrant_client=None, *, project_root=None, md_root=None, embedder=None, incremental=True) -> dict; cliente_qdrant_de_la_app() | agente ingesta (hecho) |
| `diccionario.py` | generar_esqueleto / cobertura / comparar_con_modelo (+ `uso.py`) | diccionario (hecho) |
| `pbip.py` | extraer_hechos / comparar / esqueleto (+ guardar_instantanea / cambios_desde_instantanea; acepta PBIP o .pbix PBIR) | agente pbip (hecho) |
| `src/ingestion` | leer `md/` y producir el JSON normalizado del RAG | agente ingesta |
| `pages/` (Streamlit) | ver documentación, proponer cambio, aprobar, reindexar | agente interfaz |

## Ingesta en el RAG (`ingesta.py`, `src/ingestion/document_parser.py`)

- Un grupo con páginas en `<raíz md>/<grupo>/md/*.md` se ingiere desde el .md y sus .docx
  (en `data/raw/<grupo>/`) se ignoran con aviso en consola. Los demás grupos siguen con .docx.
- Raíz md: `md_root` explícito, si no `DOCS_MD_ROOT`, si no `docs_tableros/` (`repositorio.raiz_documentos`).
  El `manifest.json` se busca junto a los .md y si no en `data/raw/<grupo>/`.
- Cada .md es un tablero del JSON normalizado (sin las heurísticas de los .docx): una cadena
  «Nombre: texto» por entrada, el historial en `other_sections` y las medidas citadas como `[Medida]`
  en Indicadores/Visuales como medidas documentadas. `_general.md` toma el nombre del informe del
  manifest (nunca «GENERAL») y sus alias.
- `reindexar_grupo` regenera solo los derivados del grupo y solo embebe los chunks que cambiaron.

Operaciones que devuelve MedGemma (JSON):

```json
{"pagina": "EGRESOS DIA",
 "operaciones": [{"accion": "modificar", "seccion": "Reglas de negocio",
                  "entrada": "Semáforo de egresos", "texto": "Verde de 0 a 45 minutos, ..."}],
 "resumen": "Se cambió el umbral verde del semáforo de egresos a 45 minutos.",
 "dudas": []}
```

`accion`: agregar | modificar | eliminar. `Propósito` solo admite `modificar` con el texto completo.
El historial y la versión los actualiza `aplicar_operaciones`.
En la llamada real cada operación trae además `antes` (copia del texto actual de la entrada): obliga al
modelo a distinguir el texto viejo del nuevo; el código lo ignora al aplicar.

## Actualizador (`actualizador.py`)

`proponer_cambio(nota, source_group, pagina=None, llm=None, cambios_pbip=None, raiz=None)` devuelve una
`Propuesta` con `estado`:

- **lista**: hay operaciones válidas; `despues` y `diff` muestran el resultado. Se aprueba con
  `aplicar_propuesta(propuesta, autor, raiz=None)`, que falla (`ErrorActualizacion`) si el archivo cambió
  desde la propuesta.
- **requiere_aclaracion**: `dudas` trae las preguntas (nota sin contenido, página dudosa con `candidatas`,
  valor anterior que no coincide con el documento, algo que la página no documenta, dudas del modelo).
  Si había operaciones, el `diff` sirve de vista previa, pero no se aplica.
- **error**: `errores` (MedGemma no respondió o no devolvió JSON válido tras un reintento).

`avisos` (no bloquean) le dicen a quien aprueba qué revisar: cifras que no están en la nota, textos que
pierden contenido, entradas relacionadas que no se tocaron y correcciones hechas por el código.
`llm_raw` guarda las respuestas crudas; `metodo_pagina` dice cómo se eligió la página.

Pruebas sin red: `python -m unittest tests.docs_md.test_actualizador`.
Evaluación con MedGemma real: `python -X utf8 -m tests.docs_md.eval_actualizador` (informe en
`tests/docs_md/out/`).

## Interfaz (`pages/1_Documentación.py` + `interfaz.py`)

`streamlit run app.py` muestra «Documentación» en la barra lateral (multipágina por carpeta `pages/`; app.py no cambia).
Modos: **Ver** (tablero, página, ficha, historial e indicador de formato) y **Proponer un cambio**
(nota + autor + página opcional + cambios PBIP → revisión con diff → Aprobar / Rechazar → reindexación).
Al reindexar se reutiliza el cliente de Qdrant del chat (`src.rag.retriever.active_retriever()`, alias `retriever_abierto`); si el chat
no está abierto, `reindexar_grupo` abre el suyo y debe cerrarlo al terminar.
Pruebas sin MedGemma ni Qdrant: `DOCS_MD_SERVICIOS=tests.docs_md.fakes_interfaz` y `DOCS_MD_ROOT=<copia de fixtures>`.

## Diccionario de variables (`diccionario.py`, `uso.py`)

Qué es cada tabla, medida y columna del modelo, para que el RAG no tenga que adivinarlo.
Un tablero tiene `docs_tableros/<grupo>/md/_diccionario.md` (si crece demasiado se reparte en
`_diccionario_<tema>.md`, p. ej. `_diccionario_columnas.md`; todo archivo que empieza por `_diccionario`
es del diccionario). Metadatos: `bloque: Diccionario`, `pagina: DICCIONARIO` (o `DICCIONARIO <TEMA>`).
No es una página: `repositorio.listar_paginas` no lo devuelve; `listar_diccionarios`, `leer_diccionario`,
`leer_pagina("DICCIONARIO")` y `guardar_pagina` sí lo manejan, y `aplicar_operaciones` lo edita como cualquier .md.

Secciones y orden: Propósito, Tablas, Medidas, Columnas calculadas, Columnas clave, Relaciones, Observaciones,
Historial de cambios. Cada entrada es UNA línea `- **Nombre**: texto.`:

| Sección | Nombre | Texto |
|---|---|---|
| Tablas | `TABLA` | qué representa. Origen: SQL/M/DAX resumido. Granularidad: ... Columnas principales: ... |
| Medidas | `[Medida]` | qué mide en lenguaje de negocio. Unidad: ... Tabla: T. Cálculo: `DAX en una línea`. Se usa en: PÁGINA › visual; ... |
| Columnas calculadas | `TABLA[COL]` | significado. Tipo: ... Cálculo: `DAX`. Se usa en: ... |
| Columnas clave (usadas en visuales, filtros o segmentadores) | `TABLA[COL]` | significado. Tipo: ... Valores: ... Se usa en: ... |
| Relaciones | `A[x] → B[y]` | cardinalidad, dirección del filtro, activa/inactiva |

Campos opcionales que reconoce la ingesta: `Clase:` (oculta, auxiliar), `Tipo:`, `Valores:`.

Reglas de redacción (además de los lineamientos generales):
1. El cálculo (DAX) va siempre literal, en una línea y entre comillas invertidas; el generador quita los comentarios.
2. Lo que no se sabe se marca «Por confirmar» (descripción, unidad, granularidad, valores); no se inventa.
3. «Se usa en» lista `PÁGINA › visual` (o `las medidas [A], [B]` si la usan otras medidas); lo genera el código.
4. Sin datos de pacientes: solo nombres de tablas, columnas, medidas y cálculos.
5. Al redactar una descripción se reemplaza el «Por confirmar.» inicial; el resto de la entrada se conserva.

### Cómo llega al RAG
`ingesta.documento_a_tablero`: Medidas -> `documented_measures` (table, name, expression, description),
Columnas calculadas -> `calculated_columns`, Tablas -> `data_sources`, Columnas clave y Relaciones ->
`other_sections` (con su encabezado), Observaciones -> `notes`. El «tablero» se llama `DICCIONARIO <TABLERO>` y lleva
`is_dictionary: true`: el enrutador no lo registra como página y `QueryPlanBuilder` no usa sus textos como
documentación de una página (no altera la resolución de métricas). Cada medida y columna produce su chunk
(`documented_measure` / `measure` si se enlaza con el modelo, `calculated_column`), así «¿qué mide X?» y
«¿cómo se calcula X?» recuperan nombre, descripción y DAX juntos.

### Comandos (desde la raíz del proyecto)
```
python -m src.docs_md.diccionario cobertura <grupo>|--todos [--json]   # qué falta documentar
python -m src.docs_md.diccionario esqueleto <grupo>                    # sin diccionario: lo imprime; con diccionario: simula --escribir
python -m src.docs_md.diccionario esqueleto <grupo> --escribir         # lo escribe sin pisar texto redactado
python -m src.docs_md.diccionario comparar <grupo>                     # entradas obsoletas / elementos nuevos
```
Las fuentes se leen en modo solo lectura: `data/model_metadata/<modelo>/*.csv` (INFO.VIEW, `;`) y el PBIP
`tableros/<carpeta>/` (nunca `.pbi/cache.abf`). La raíz que contiene `data/` y `tableros/` es `--raiz`, si no
`DOCS_MD_DATA_ROOT`, si no este repositorio (en un worktree: `DOCS_MD_DATA_ROOT=<checkout principal>`).
Los .md se escriben en `DOCS_MD_ROOT` o `docs_tableros/`.

La carpeta del PBIP (`carpeta_pbip`) sale del `pbir_path` del manifest si existe; si no, de la carpeta de
`tableros/` cuyo nombre, `.Report` o `.SemanticModel` coincide (en slug) con el grupo, el informe o el modelo del
manifest, y por último con la misma comparación sin palabras vacías (de, del, la, tablero...). Si dos carpetas
coinciden en un mismo paso no se elige ninguna.

- **Esqueleto**: determinista. Descripciones = Description del modelo o lo ya escrito en las páginas .md del grupo
  (Fuentes de datos, Indicadores con `Medida X = ...` o `[X]`), copiado completo (nunca se trunca con «…»); si no,
  «Por confirmar». Si el PBIP trae los nombres de las páginas, no se copian las notas «Nombre de página ... por
  confirmar». La descripción de una columna se toma de una entrada que la cita como `Tabla[Columna]`, o cuyo
  nombre es la columna y la tabla no deja duda (única en el modelo, o única entre las tablas que la entrada o la
  página nombran): nunca se copia a otra tabla con una columna del mismo nombre. La «Unidad» solo se hereda de una
  entrada que habla de esa medida y de ninguna otra, o de un formato de porcentaje; si no, «Por confirmar» (el tipo
  de dato no basta). El tipo de las columnas calculadas es el dataType explícito del TMDL o del CSV, salvo que diga
  texto y la columna se resuma con SUM/AVERAGE/MIN/MAX o tenga formato numérico (entonces «número»). Una relación
  que INFO.VIEW lista en los dos sentidos (uno a uno bidireccional) se escribe una vez. Si el PBIP no trae los
  visuales, «Se usa en» dice «sin dato (el PBIP no trae la definición de los visuales)». Marca medidas ocultas y
  auxiliares (las usan otras medidas pero ningún visual). En modelos grandes (más de 250 medidas, 150 columnas
  calculadas o 80 tablas) detalla solo lo usado en visuales, lo descrito y lo que alimenta a lo usado, y resume el
  resto por tabla en Observaciones; si hay más de 120 columnas, van a `_diccionario_columnas.md`.
- **`--escribir`**: conserva todo texto existente, agrega solo las entradas nuevas, marca «Obsoleta: ya no existe en el
  modelo.» las que ya no están y registra el cambio en el historial (versión +1). Dos corridas seguidas no cambian nada.
  Sin `--escribir`, si ya hay diccionario solo se lista lo que `--escribir` agregaría o marcaría.
- **Cobertura**: medidas, columnas clave, tablas, relaciones, páginas y visuales del modelo/PBIP que ningún .md nombra
  (nombres normalizados, sin tildes, mayúsculas ni espacios al inicio/fin). Del diccionario solo cuentan las entradas
  ya redactadas; informa cuántas empiezan por «Por confirmar» y cuántas lo mencionan en cualquier parte. Un grupo sin
  modelo ni PBIP no falla: dice «sin modelo disponible» y solo valida sus .md.
  - **Emparejamiento de páginas** (`emparejar_paginas`, uno a uno, en este orden): 1) `id_pagina` del .md (texto o
    lista) igual al id de la página en el PBIP; 2) `pagina` igual al nombre (si el PBIP repite el nombre, la k-ésima
    página va con «NOMBRE (k)», como las nombra `pbip.esqueleto`); 3) alias: `pagina_pbip` (texto o lista) o
    `nombre_funcional` igual al nombre, si un único .md lo declara; 4) «Duplicado de X» con el .md de X si en el PBIP
    no hay otra página X; 5) coincidencia de visuales: el .md que menciona el nombre de la página y nombra (por título
    o `Tabla[Columna]`) más visuales distintivos de ella (no segmentadores, documentados en ≤ 2 .md), sin empate y sin
    ser el mejor de otra página. Para dos páginas con el mismo nombre (p. ej. INTERCONSULTAS en tiempos de urgencias)
    lo seguro es poner `id_pagina` en cada .md.
  - **Visuales**: un visual de una página emparejada cuenta si su .md nombra su título, el nombre visible o la expresión
    de un campo (con o sin el nivel de jerarquía de fecha: «Calendario[Date] (Año)» o «Calendario[Date]»); un
    segmentador de fecha también cuenta si la página documenta su tabla y su columna de fecha.
- **Comparar** (`comparar_con_modelo`): obsoletas, nuevas, renombradas probables (mismo DAX) y cálculos que cambiaron;
  alimenta el flujo de actualización.
- `uso.uso_de_campos(hechos)` -> `{"Tabla[col]" | "[Medida]": [{"pagina","visual","tipo","titulo"}]}` desde `pbip.extraer_hechos`.

Pruebas: `python -m unittest tests.docs_md.test_diccionario tests.docs_md.test_diccionario_correcciones tests.docs_md.test_docs_tableros`
(sintéticas, sin red; `PbipRealesTest` se salta si no hay `tableros/`). El detector de datos personales de
`test_docs_tableros.posible_pii` ignora los identificadores técnicos (valor de `id_pagina`, «ReportSection…», ids
hexadecimales de 16+ caracteres con letras y GUID) antes de buscar documentos, teléfonos y correos; un número solo de
dígitos se sigue detectando.

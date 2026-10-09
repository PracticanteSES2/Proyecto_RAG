# tools/local_data — `data/` local sin Power BI

Reconstruye `data/` (la carpeta que usa `app.py`, ignorada por git) a partir
de fuentes **locales**, siguiendo el pipeline del propietario siempre que se
puede. Sirve para desarrollar y probar en una máquina sin acceso a Power BI
(sin ADOMD ni credenciales). No lee `.env` ni envía datos a ningún servicio.

## Uso

Desde la raíz del repo (o desde un worktree: se detecta el checkout principal
para leer `tableros/`, `Documentacion/` y escribir `data/`):

```bash
python -m tools.local_data.build_local_data              # build completo (con embeddings)
python -m tools.local_data.build_local_data --skip-index # sin recalcular Qdrant
python -m tools.local_data.smoke_local_data              # comprobación rápida
python -m tests.local_data.test_local_data               # pruebas offline
```

Opciones: `--project-root`, `--data-root` (carpeta que debe llamarse `data`;
por defecto `<raíz>/data`), `--docs-dir`, `--tableros-dir`, `--reference-zip`,
`--history-commit` (por defecto `3bf7b9f`), `--keep-backup`.

El `data/` anterior se renombra a `data.bak_<fecha>` antes de empezar; si algo
falla se borra lo construido y se restaura. Si todo va bien el respaldo se
elimina (salvo `--keep-backup`). Con `--skip-index` se copia el índice Qdrant
del respaldo.

## Qué hace

| Paso | Herramienta | Salida |
|---|---|---|
| 1 | `tmdl_to_metadata.py` (TMDL), `git show 3bf7b9f` (historial) o `infer_metadata.py` | `data/model_metadata/<slug>/{tables,columns,measures,relationships}.csv` + `_metadata_sync.json` |
| 1 | `build_local_data.py` | `data/catalog/model_registry.json` |
| 2 | `import_documentation_batch.py` (propietario) | `data/raw/<grupo>/*.docx` + `manifest.json`, `documentation_import_report.json` |
| 3 | `build_powerbi_catalogs.py` (propietario) | `data/catalog/<modelo>{,_normalized,_rag}.json`, `catalog/visuals/`, `source_registry.json`, `rag/visual_metrics_catalog.json`, `rag/master_metrics.json` |
| 4 | `ingest_rag.py` (propietario) | `processed/`, `semantic_documents/`, `catalog/semantic_knowledge.json`, `rag/knowledge_chunks.json`, `vector_db/qdrant` |
| 5 | `coverage_report.py` | `data/catalog/local_build_report.json` (también se imprime) |

Los módulos del propietario se importan tal cual; solo se redirigen sus
constantes de ruta (`PROJECT_ROOT`, `RAW_DIR`...) a la raíz elegida.

## Origen de la metadata de cada modelo

Prioridad: **TMDL > historial git > inferida**. El campo `source` de
`_metadata_sync.json` y de `model_registry.json` lo indica:

- `tmdl`: proyectos PBIP con `*.SemanticModel/definition` (ASIGNACION DE
  CITAS, TABLERO PERFIL DE MORBILIDAD). Metadata real. Nunca se abre
  `.pbi/cache.abf`.
- `git_history`: export real de INFO.VIEW del propietario guardado en el
  commit `3bf7b9f` (TABLERO DE ATENCIONES INSTITUCIONALES). Los CSV se copian
  byte a byte; solo se añade `_metadata_sync.json`.
- `inferred_from_report_and_documentation` / `inferred_from_report`: tableros
  con `*.Report` PBIR pero sin modelo. Tablas/columnas/medidas salen de las
  referencias Entity/Property de visuales y filtros; el DAX de las medidas y
  las columnas calculadas, de la documentación; los alias de SQL documentado
  solo se añaden cuando coinciden claramente con una tabla ya conocida.
- `inferred_from_documentation`: tableros con solo documentación. Medidas y
  columnas calculadas con su DAX, columnas citadas como `Tabla[Columna]` y
  alias de las consultas SQL (si no hay tabla identificable, se sintetiza una
  con el nombre del tablero; quedan listadas en `_metadata_sync.json`).

Los nombres y slugs de los modelos siguen `sync_powerbi_metadata.slugify`. Si
existe `OneDrive_1_9-10-2026.zip`, solo se leen los **nombres** de
`__data/model_metadata/*` para elegir el slug real (p. ej. `demanda_insatisfecha`
y no `tablero_demanda_insatisfecha`) y listar en el registro los modelos
remotos sin fuente local.

## Formato de los CSV

Idéntico al export real de INFO.VIEW guardado en `3bf7b9f`: separador `;`,
textos entre comillas, booleanos `True/False` y enteros sin comillas, CRLF
(también dentro de expresiones multilínea), UTF-8 sin BOM, columna oculta
`RowNumber-2662979B-...` por tabla, `LocalDateTable_*`/`DateTableTemplate_*`
incluidas (ocultas), `IsUnique=True` solo en el lado "uno" de las relaciones,
relaciones 1:1 listadas en ambos sentidos y formato estático de medidas en
`FormatStringDefinition` (`"0"`). Nota: `sync_powerbi_metadata.write_csv`
escribe en cambio coma + BOM; los lectores del proyecto aceptan ambos.

## Limitaciones

- IDs, `Model`, `TableStorage`/`ColumnStorage` y (en lo inferido) `LineageTag`
  son sintéticos; deterministas entre ejecuciones.
- En TMDL, las columnas calculadas sin `dataType` y el `DataType` de las
  medidas se infieren (heurística calibrada con el CSV real, ~85 %).
- Metadata inferida: sin relaciones, sin tablas de fecha automáticas, tipos
  heurísticos y medidas vistas solo en visuales sin expresión DAX. Validado
  contra la metadata real de Atenciones Institucionales: ~97 % de las medidas
  inferidas existen en el modelo real; ~75 % de las columnas caen en la tabla
  correcta.
- Los modelos que solo tiene el propietario en Power BI (unos 28 más) no se
  pueden reconstruir: aparecen en `remote_models_without_local_sources`.
- Las sinonimias de `cultures/*.tmdl` no forman parte de INFO.VIEW y no se
  exportan.

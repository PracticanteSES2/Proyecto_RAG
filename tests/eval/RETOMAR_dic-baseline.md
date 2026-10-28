# Retomar: agente dic-baseline (línea base del banco con la data TMDL real)

Rama: `agente/dic-baseline` (desde `desarrollo` 55b2e12). Sin push. Estado: PAUSA (2026-10-28).

Scratchpad (no versionado):
`C:\Users\ad6708\AppData\Local\Temp\claude\c--Users-ad6708-Documents-Proyecto-RAG\4b244146-c790-44cb-9bdf-44222364c716\scratchpad`
(abajo `$S`).

## Corridas hechas

Ninguna terminó: las dos se detuvieron por la pausa (llevaban ~15 min y no habían escrito `report.json`;
con `--quiet` no hay progreso por caso). No hay resultados nuevos; las cifras previas son las del coordinador
(153/158 data anterior; ~90/158 fake y 87/158 real con la data nueva).

Comandos exactos (PowerShell, desde la raíz del worktree):

```powershell
$S="<scratchpad>"; $env:PYTHONDONTWRITEBYTECODE=1; $env:PYTHONIOENCODING="utf-8"
# Data ANTERIOR: copia del respaldo (robocopy de C:\Users\ad6708\Documents\Proyecto_RAG_data_backup_20261028)
$env:SIM_DATA_ROOT="$S\old_data\data"; $env:SIM_CACHE_DIR="$S\cache_old"
C:\Users\ad6708\Documents\Proyecto_RAG\.venv\Scripts\python.exe -X utf8 -m tests.eval.run --harness realistic --llm fake --quiet --out "$S\out_old" *> "$S\run_old.log"
# Data NUEVA (solo lectura; el arnés copia a la caché)
$env:SIM_DATA_ROOT="C:\Users\ad6708\Documents\Proyecto_RAG\data"; $env:SIM_CACHE_DIR="$S\cache_new"
C:\Users\ad6708\Documents\Proyecto_RAG\.venv\Scripts\python.exe -X utf8 -m tests.eval.run --harness realistic --llm fake --quiet --out "$S\out_new" *> "$S\run_new.log"
```

Las cachés `$S\cache_old` y `$S\cache_new` ya están construidas (overlay + parches + Qdrant): la próxima corrida
arranca más rápido. `$S\cache_new\*\root\data\catalog\patches_report.json` confirma que los 4 parches se aplicaron.

## Hallazgos (sin corrida completa: clasificación PARCIAL, por inspección de metadata)

Conteo metadata (líneas CSV, viejo→nuevo): briefing T 28→95, M 40→82, R 1→59; demanda_insatisfecha T 5→76,
R 1→77; eps T 5→26; farmacia T 8→13; control_facturacion T 14→98; tiempos_urgencias T 13→63; lavandería igual.
`data/pbir/` ya no existe: los manifests apuntan con ruta RELATIVA `tableros/<X>/<X>.Report`
(`catalog_patches._original_report` la resuelve contra `data_root.parent`: OK con la data del checkout principal,
pero FALLA si se usa una copia de la data nueva fuera del checkout).

(a) Artefactos del simulador/banco (seguros):
- `catalog_patches.py` DEMANDA INSATISFECHA: parchea la tabla `SOLICITUD_CAMAS`, que ya no existe; el modelo real
  trae `'SOLICITUD DE CAMAS'` (con DEMANDA_INS, OID_TERCERO), `TERCEROS[OID/TERNOMCOM]` y su relación, y
  `CALENDARIO[TOTAL_SOLICITUD_CAMAS]`. El parche agrega columnas a una tabla inexistente, duplica TERCEROS y
  crea un `TOTAL_SOLICITUD_CAMAS` duplicado en otra tabla. No hay medida `HOSPITALIZACIÓN` en el modelo real
  (existe `SOLICITUD DE CAMAS[DEMANDA_INS_PM]`): revisar el PBIR real de la página «SOLICITUD CAMAS».
- `catalog_patches.py` TABLERO EPS: `%OCUPACIONAL[%OCUPACIONALC]` ya existe en el modelo real → el parche la duplica.
- `catalog_patches.py` BRIEFING: `CAMAS DISPONIBLES` real ya tiene %OCUPACION, CamasFiltradas, TOTAL_OCUPADAS y
  más columnas (HSUNOMBRE, EstadoNombre...); `PACIENTES X ASEGURADORA` real ya NO tiene FechaSalida,
  FECHA_EPICRISIS, FECHA_ORDEN_SALIDA, EGRESO_EFECTIVO_HOY (las filas fijas las siguen usando). Verificar si
  las páginas INICIO/GESTIÓN CAMAS del PBIR real ya tienen los visuales que el parche agrega (renombre de página).
(c) Diferencias legítimas probables:
- LAVANDERÍA: el PBIR real es «Página 1» con 0 visuales y el modelo tiene 0 medidas (antes había un PBIR
  inferido en `data/pbir/TABLERO LAVANDERIA.Report`). Afecta ~25 casos `*_lav_*`: sin medida ni visual no hay
  métrica «peso total». Decidir con el propietario: ¿el PBIP local está incompleto (el informe publicado sí
  tiene visuales según el docx)? Si es incompleto → (a): parche de páginas/visuales de lavandería en
  `catalog_patches.py` documentando que reproduce el informe publicado; si es real → (c) xfail/expectativa
  `metric_not_resolved` con motivo. Mismo análisis para los otros 6 informes que antes eran PBIR inferido:
  DEMANDA INSATISFECHA, ANTIBIOTICOS, CVC (visual_metrics 14,9 KB → 0,7 KB), EPS, NAOS, REFERENCIA.
(b) Problemas reales del chatbot: aún sin evidencia (requiere las corridas).

## Pasos pendientes

1. Repetir las dos corridas de arriba (en paralelo funcionan: cachés distintas) sin `--quiet` o con una
   corrida por categoría para ver progreso; esperar `report.json` en `$S\out_old` y `$S\out_new`.
2. `python -X utf8 $S\diff.py $S\out_old $S\out_new` lista regresiones con turnos fallidos y botones antes/después.
   `$S\meta.py <slug,...> tables|columns|measures|relationships [filtro]` compara metadata vieja/nueva.
3. Clasificar cada regresión a/b/c (pregunta, antes/después, causa).
4. (a) Reescribir los parches de DEMANDA INSATISFECHA/EPS/BRIEFING sobre las tablas reales (o quitarlos si el
   modelo ya los trae), ajustar `_sim_tables.json` a las columnas reales; decidir lavandería.
   Hacer que `catalog_patches._original_report` y el overlay resuelvan `pbir_path` relativo también contra el
   checkout principal (para correr con copias de la data nueva).
5. (b) Arreglos generales en `src/` fuera de retriever.py, chunk_builder.py, docs_md/ingesta.py,
   metric_resolver.py y src/chatbot/ (presentación), con pruebas.
6. (c) Actualizar expectativas/xfail con motivo tomado del TMDL.
7. Documentar la línea base nueva (comando + resultado) en `tests/eval/README.md`; si MedGemma responde, una
   corrida `--llm real` al final.

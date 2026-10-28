---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: OPORTUNIDAD URGENCIAS
nombre_funcional: Tiempo de espera para la consulta médica de urgencias
bloque: Histórico
tablas: [CONSULTA_URGENCIAS, Calendario, TERCERO]
actualizado: 2026-10-28
version: 2
---

# OPORTUNIDAD URGENCIAS

## Propósito
Muestra el tiempo promedio, en minutos, hasta la consulta médica de urgencias, mes a mes y comparando años. Se llega con el botón OPORTUNIDAD CONSULTA de la página URGENCIAS.

## Fuentes de datos
- **CONSULTA_URGENCIAS**: Ingresos por urgencias desde 2025-01-01 hasta hoy con su triage, fecha de admisión, primer folio con diagnóstico principal, clasificación, aseguradora agrupada (AGRUPA_ASEGURADORA), plan de beneficio, causa de ingreso, grupo de edad y tiempo calculado hasta la consulta.

## Indicadores
- **Tiempo calculado para la consulta**: Minutos hasta el primer folio. Columna TIEMPO_CONSULTA_CALCULADA: desde la admisión si el triage es II o no hay triage; desde la hora del triage en los demás casos.
- **Tiempo desde la admisión**: Columna tiempo_consulta = DATEDIFF(CONSULTA_URGENCIAS[FECHA_ADMISION], CONSULTA_URGENCIAS[FECHA_FOLIO], MINUTE).
- **Oportunidad del año en curso**: Cálculo: TIEMPO_OPORTUNIDAD_PRIORITARIAS_ACT = CALCULATE(AVERAGE(CONSULTA_URGENCIAS[tiempo_consulta]), YEAR(CONSULTA_URGENCIAS[FECHA_FOLIO]) = YEAR(TODAY())); existen versiones fijas para 2023, 2025 y 2026.
- **Promedio del gráfico**: Promedio de minutos por mes. Columna promediada por confirmar (tiempo_consulta o TIEMPO_CONSULTA_CALCULADA).

## Visuales
- **Segmentadores**: Clasificación Triage, ASEGURADOR, Año, Mes, Día y casillas MAYORES DE EDAD / MENORES DE EDAD.
- **Botones de vista**: GENERAL, URGENCIAS, OBSTETRICIA y OPORTUNIDAD DE ATENCIÓN EN TRIAGE II; destino del último por confirmar.
- **Gráfico de oportunidad**: Líneas «OPORTUNIDAD CONSULTAS MÉDICAS DE URGENCIAS (minutos)» con el promedio de minutos por mes, una línea por año.
- **Tabla de detalle anual**: Matriz del promedio de minutos por año (filas) y mes (columnas).
- **Botón de regreso**: Flecha que vuelve a URGENCIAS.

## Reglas de negocio
- **Inicio del tiempo**: Para triage II y para pacientes sin triage el tiempo se mide desde la admisión; para los demás, desde la hora del triage.
- **Tiempos válidos**: Solo entran consultas con folio dentro de las 24 horas siguientes a la admisión y con tiempo calculado de 1440 minutos o menos.
- **Ingresos excluidos**: Se excluyen las causas de ingreso 11 (cirugía programada) y 4 (enfermedad general pediatría), los ingresos con AINESTADO 2 o 4 y los que tienen AIINGCORCU = 1 (significado por confirmar).
- **Primer folio**: Se toma el primer folio del ingreso que tenga diagnóstico principal.

## Observaciones
- **Nombre de página**: En Power BI la página se llama OPORTUNIDAD URGENCIAS; la documentación del propietario la titula «OPORTUNIDAD CONSULTA URGENCIAS».
- **Dos consultas distintas**: «Tablero Urgencias» documenta una consulta anterior (desde 2023, tiempo desde el triage y, desde 2025-08-01, desde la admisión para triage II); «Oportunidad Consultas Urgencias» documenta la que coincide con el modelo actual.
- **Medidas con nombre PRIORITARIAS**: Las medidas de tiempo se llaman TIEMPO_OPORTUNIDAD_PRIORITARIAS aunque miden todas las consultas de urgencias, y promedian tiempo_consulta (desde la admisión), no el tiempo calculado.
- **Sin meta**: La documentación no define meta ni semáforo para este tiempo. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

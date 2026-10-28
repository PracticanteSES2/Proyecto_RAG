---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: CONSULTAS SIN TRIAGE
nombre_funcional: Ingresos de urgencias atendidos sin triage
bloque: Histórico
tablas: [CONSULTAS SIN TRIAGE, Calendario]
actualizado: 2026-10-20
version: 1
---

# CONSULTAS SIN TRIAGE

## Propósito
Muestra los ingresos de urgencias que se atienden sin clasificación de triage, mes a mes y comparando años, con su promedio mensual y su porcentaje. Se llega con el botón CONSULTAS SIN TRIAGE de la página URGENCIAS.

## Fuentes de datos
- **CONSULTAS SIN TRIAGE**: Ingresos por urgencias (AINURGCON = 0) del área 2 (urgencias) desde 2024-01-01 hasta hoy, con su triage si existe, hora de llegada, admisión, primer folio y clasificación; CLASIFICACION_TRIAGE vale SIN TRIAGE cuando el ingreso no tiene triage. Se une al Calendario por FECHA (fecha de admisión).

## Indicadores
- **Promedio mensual**: Ingresos del año en curso divididos entre el número del mes actual. Medida del modelo PROM_SIN_TRIAGE = DIVIDE(CALCULATE(COUNT('CONSULTAS SIN TRIAGE'[AINCONSEC]), YEAR('CONSULTAS SIN TRIAGE'[FECHA]) = YEAR(TODAY())), MONTH(TODAY())). Por confirmar.
- **Porcentaje sin triage**: Ingresos con clasificación SIN TRIAGE sobre el total de ingresos de la tabla. Medida del modelo %SIN_TR. Por confirmar.
- **Consultas por mes**: Número de ingresos por mes en el gráfico y la tabla. Medida por confirmar.

## Visuales
- **Segmentadores**: ASEGURADOR, Año y Mes.
- **Gráfico de consultas sin triage**: Líneas «CONSULTAS SIN TRIAGE» con el número por mes, una línea por año.
- **Tabla de detalle anual**: Matriz por año (filas) y mes (columnas).
- **Tarjetas**: «PROMEDIO MENSUAL» y «%CONSULTAS SIN TRIAGE».
- **Botón de regreso**: Flecha que vuelve a URGENCIAS.

## Reglas de negocio
- **Consulta sin triage**: Ingreso de urgencias sin registro de triage (CLASIFICACION_TRIAGE = SIN TRIAGE).
- **Ingresos excluidos**: No entran las cirugías programadas (causa de ingreso 11) ni los ingresos con AINESTADO 2 o 4.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Medidas no documentadas**: Ninguno de los dos documentos lista las medidas; las de las tarjetas salen del catálogo del modelo.
- **Gráfico frente a porcentaje**: En la captura el promedio mensual coincide con la suma del año del gráfico dividida entre los meses transcurridos, mientras el porcentaje sin triage es 17,59 %; eso sugiere que el gráfico cuenta todos los ingresos de urgencias y no solo los sin triage. Por confirmar.
- **Descripción distinta**: Un documento describe la página como consultas «con cita previa o en orden de llegada» sin revisión de gravedad; la consulta solo trae ingresos de urgencias.
- **Columna PRUEBA**: La fecha del primer folio se carga con el nombre PRUEBA.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.

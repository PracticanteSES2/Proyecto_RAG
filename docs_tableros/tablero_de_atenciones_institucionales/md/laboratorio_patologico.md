---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: LABORATORIO PATOLOGICO
nombre_funcional: Reportes de patología por mes
bloque: Histórico
tablas: [LABORATORIOS_PATOLOGICOS, Calendario]
actualizado: 2026-10-20
version: 1
---

# LABORATORIO PATOLOGICO

## Propósito
Muestra cuántos reportes de patología se generan cada mes, compara los años y da el total anual y el promedio mensual. Se llega con el botón LABORATORIO DE PATOLOGÍA de INICIO y desde aquí se abre LABORATORIOS PATOLOGICOS (por aseguradora). Página oculta en modo lectura.

## Fuentes de datos
- **LABORATORIOS_PATOLOGICOS**: Solicitudes de patología desde 2025-01-01 hasta hoy (por fecha de solicitud) con su primer resultado del laboratorio de patología en estado 1, 2 o 3; trae consecutivo del ingreso, fecha de solicitud, fecha de realizado, código y tipo de examen, resultado, aseguradora y categoría EPS. Se une al Calendario por FechaRealizado.

## Indicadores
- **Total laboratorios anual**: Reportes con fecha de solicitud en el año en curso. Cálculo: Count(LABORATORIOS_PATOLOGICOS[Consecutivo]) con filtro de fecha relativa «este año» sobre FechaSolicitud.
- **Promedio mensual**: Promedio de reportes por mes con datos del año elegido o, sin año elegido, del año cerrado. Medida Promedio_Laboratorio_pat, que promedia TOTAL_LABORATORIO_PAT = COUNTROWS(LABORATORIOS_PATOLOGICOS) solo en meses con reportes.
- **Reportes por mes**: Count(LABORATORIOS_PATOLOGICOS[Consecutivo]) en el gráfico y la tabla.

## Visuales
- **Segmentadores**: ASEGURADORA, Año, Mes y TIPO DE PATOLOGIA (TipoLaboratorio).
- **Gráfico de reportes por mes**: Líneas «TOTAL DE REPORTES DE PATOLOGÍA EN EL PERIODO», una línea por año.
- **Tabla de reportes**: Matriz de reportes por año (filas) y mes (columnas).
- **Tarjetas de reportes**: «PROMEDIO MENSUAL» y «TOTAL LABORATORIOS ANUAL».
- **Botón Asegurador**: Botón «ASEGURADOR» que abre LABORATORIOS PATOLOGICOS; el botón de casa vuelve a INICIO.

## Reglas de negocio
- **Un reporte por solicitud**: Cada solicitud de patología toma solo su primer resultado y su primera respuesta.
- **Estados válidos**: Solo entran resultados en estado 1, 2 o 3 (significado por confirmar).
- **Categoría EPS**: 125 medicina prepagada, 126 póliza, 127 particular, 122 plan complementario y el resto contributivo/subsidiada.

## Observaciones
- **Tarjetas de años distintos**: Sin año elegido, el total anual es del año en curso (por fecha de solicitud) y el promedio es del año cerrado (por fecha de realizado); en la captura no corresponden al mismo año.
- **Dos fechas**: El total anual filtra por FechaSolicitud y el gráfico y la tabla usan FechaRealizado (relación con el Calendario), por eso el total no coincide con la suma del año en la tabla.
- **Nombre de página**: En el PBIP se llama « LABORATORIO PATOLOGICO» (con un espacio al inicio); la documentación la llama LABORATORIO PATOLOGIA.
- **Nombre parecido**: La página de detalle se llama LABORATORIOS PATOLOGICOS; se distinguen por el plural.
- **Datos clínicos cargados**: La tabla carga el texto del resultado de patología y el nombre del paciente, que ningún visual documentado usa.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.

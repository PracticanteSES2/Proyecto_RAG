---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: LABORATORIO
nombre_funcional: Exámenes de laboratorio clínico por mes
bloque: Histórico
tablas: [LABORATORIOS, Calendario]
actualizado: 2026-10-28
version: 2
id_pagina: fffb5a516b88d93d2e75
---

# LABORATORIO

## Propósito
Muestra cuántos exámenes de laboratorio clínico se procesan cada mes, compara los años y da el total anual y el promedio mensual. Se llega con el botón LABORATORIO CLÍNICO de INDICADORES.

## Fuentes de datos
- **LABORATORIOS**: Servicios prestados en el área de laboratorio (área 15) desde 2025-01-01 hasta hoy, sin ingresos con AINESTADO 2 o 4; trae paciente, código y CUPS del examen, nombre del servicio, fecha de atención, tipo de ingreso (AMBULATORIO u HOSPITALARIO), vía de ingreso (URGENCIAS, CONSULTA EXTERNA u OTRO) y asegurador. Se une al Calendario por FECHA_ATENCION.

## Indicadores
- **Total de laboratorios**: Exámenes del año elegido o, sin año elegido, del año cerrado; con varios años suma cada año. Medida del modelo TOTAL_MUESTRAS (conteo de filas). Por confirmar que sea la de la tarjeta.
- **Laboratorios con CUPS**: Cálculo: TOTAL_LABORATORIO = COUNT(LABORATORIOS[CUPS]).
- **Promedio mensual**: Promedio de exámenes por mes del año elegido o del año cerrado. Medida del modelo Promedio_Laboratorio_Dinamico (promedia TOTAL_LABORATORIO por mes). Por confirmar que sea la de la tarjeta.

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y TIPO INGRESO.
- **Gráfico de laboratorios por mes**: Líneas tituladas «TOTAL DE IMÁGENES POR AÑO» que muestran los exámenes de laboratorio por mes, una línea por año.
- **Tarjetas de laboratorios**: «PROMEDIO MENSUAL» y «TOTAL LABORATORIOS ANUAL».
- **Tabla de detalle anual**: Matriz de exámenes por año (filas) y mes (columnas).
- **Botón Detalle**: Botón «DETALLE»; destino por confirmar.
- **Botón de inicio**: Botón de casa que vuelve a INDICADORES.

## Reglas de negocio
- **Examen de laboratorio**: Servicio prestado en el área de servicio 15; se cargan filas distintas por paciente, examen y fecha.
- **Periodo cargado**: Solo desde 2025-01-01.

## Observaciones
- **Nombre de página**: En Power BI la página se llama LABORATORIO; la documentación del propietario la titula «LABORATORIO CLÍNICO».
- **Texto copiado de imágenes**: El documento describe la página y el gráfico como «imágenes» y el botón como «Detalle Apoyo Diagnóstico»; la consulta y las tarjetas son de laboratorio.
- **Gráfico y tabla no cuadran**: En la captura el gráfico da valores menores que la tabla en todos los meses; las tarjetas cuadran con la tabla. Por confirmar qué medida usa cada visual.
- **Sección de imágenes por área**: El documento incluye «IMAGENES POR AREA» con la captura de la página ESPECIALIDAD IMAGENES; no se documenta una página de detalle de laboratorio.
- **Sin medidas documentadas**: El documento no lista medidas; las fórmulas salen del catálogo del modelo.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: PARTOS
nombre_funcional: Partos atendidos por mes y relación vaginales/cesáreas
bloque: Histórico
tablas: [PARTOS_DRIVE, Calendario]
actualizado: 2026-10-28
version: 2
---

# PARTOS

## Propósito
Muestra los partos atendidos cada mes en los últimos tres años, por tipo de parto, y la relación entre partos vaginales y cesáreas. Se llega desde el botón PARTOS de TRIAGES OBSTÉTRICOS y se vuelve con la flecha.

## Fuentes de datos
- **PARTOS_DRIVE**: Archivo Excel de gestantes (partos MSPS) que mantiene epidemiología en SharePoint; una fila por parto con documento, mes, año, tipo de parto, asegurador y datos de planificación y tamizaje. La fecha (FECHA_REAL) es el primer día del mes del parto.

## Indicadores
- **Relación partos vaginales / cesáreas**: Partos vaginales por cada cesárea. Cálculo: RELACIÓN = SUM(PARTOS_DRIVE[VAGINALES])/SUM(PARTOS_DRIVE[CESÁREAS]).
- **Total partos**: Número de partos del año seleccionado o, si no hay año, del año anterior cerrado. Medida Total_Partos_Dinamico (COUNTROWS de PARTOS_DRIVE quitando los demás filtros de calendario).
- **Promedio mensual de partos**: Promedio de partos por mes del año seleccionado o del año anterior cerrado. Medida Promedio_Partos_Dinamico.

## Visuales
- **Selector tipo de parto**: Botones «TIPO DE PARTO» que filtran la página; en la captura se ven CESÁREA, IVE y EXTRASES y hay más opciones con desplazamiento.
- **Gráfico de partos**: Líneas «PARTOS» con el conteo de partos (recuento de Documento) por mes, una línea por año.
- **Tabla de conteo de partos**: Matriz de partos por año (filas) y mes (columnas).
- **Tarjetas de partos**: «RELACIÓN PARTOS VAGINALES/CESAREAS», «TOTAL PARTOS» y «PROMEDIO MENSUAL PARTOS».
- **Botón de regreso**: Flecha que vuelve a TRIAGES OBSTÉTRICOS.

## Reglas de negocio
- **Tipo de parto**: VAGINALES vale 1 cuando el tipo es VAGINAL y CESÁREAS vale 1 cuando es CESÁREA (columnas calculadas).
- **Año por defecto**: Sin año seleccionado, las tarjetas de total y promedio muestran el año anterior cerrado.

## Observaciones
- **Nombre de página**: Coincide con la página PARTOS del PBIP.
- **Página documentada dos veces**: La documentación describe esta página en dos secciones («TABLERO PARTOS» y «TABLERO DE PARTOS») con la misma captura; aquí se unen.
- **Visuales rotos**: En las capturas tres visuales de la parte superior muestran «Corregir esto» (error de campo); por la documentación serían los filtros de aseguradora, año y mes. Por confirmar.
- **Tipos que no son parto**: El mismo archivo trae ABORTO e IVE, que se ven en la página ABORTOS. Por confirmar si el total de partos los excluye.
- **Medida con año fijo**: En el modelo existe también «Total Partos Dinámico» con el año 2025 escrito en la fórmula.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

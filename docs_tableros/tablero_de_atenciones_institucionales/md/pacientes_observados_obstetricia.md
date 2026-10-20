---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: PACIENTES OBSERVADOS OBSTETRICIA
nombre_funcional: Pacientes obstétricas en observación por mes
bloque: Histórico
tablas: [OBSERVADOS, Calendario, TERCERO]
actualizado: 2026-10-20
version: 1
---

# PACIENTES OBSERVADOS OBSTETRICIA

## Propósito
Muestra cuántas pacientes obstétricas quedan en observación cada mes y compara los años. Se llega desde el botón PACIENTES OBSERVADAS de TRIAGES OBSTÉTRICOS y se vuelve con la flecha. Es distinta de la página PACIENTES OBSERVADOS general de urgencias.

## Fuentes de datos
- **OBSERVADOS**: Ingresos de urgencias (AINTIPING = 1) que no son de consulta (AINURGCON = 0), de las áreas de servicio 2 (urgencias) y 42 (gineco-obstetricia), desde 2022-01-01 hasta hoy; trae asegurador, área, grupo de edad y el triage del ingreso (HCENTRIAGE).

## Indicadores
- **Observados por año**: Ingresos en observación de un año fijo. Cálculo: OBSERVADOS_2025 = CALCULATE(COUNT(OBSERVADOS[HCENTRIAGE]), YEAR(OBSERVADOS[fecha]) = 2025); igual para 2024.
- **Promedio pacientes observados**: Total del año dividido por los meses con datos hasta hoy. Medida Promedio_OBS_Dinamico: usa el año seleccionado o, si no hay, el año anterior cerrado, y solo cuenta meses con actividad.
- **Observados año actual**: Total de pacientes en observación del año en curso. Medida de la tarjeta por confirmar.

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y casillas MAYORES DE EDAD / MENORES DE EDAD.
- **Gráfico de observados por mes**: Líneas «PACIENTES OBSERVADOS POR MES» con el conteo mensual, una línea por año.
- **Tarjetas de observados**: «OBSERVADOS AÑO ACTUAL» y «PROMEDIO PACIENTES OBSERVADOS».
- **Tabla de detalle anual**: Matriz de pacientes observados por año (filas) y mes (columnas).
- **Botón de regreso**: Flecha que vuelve a TRIAGES OBSTÉTRICOS.

## Reglas de negocio
- **Paciente observado**: Ingreso por urgencias que no es consulta (AINURGCON = 0) en urgencias o gineco-obstetricia.
- **Grupo de edad**: MENORES DE EDAD si la edad al ingreso es menor de 18 años; si no, MAYORES DE EDAD.
- **Agrupación de aseguradoras**: NUEVA EPS, SURA, SANITAS y MALLAMAS se agrupan por nombre igual que en los triages; el resto conserva su nombre.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Filtro obstétrico no documentado**: La consulta incluye también el área 2 (urgencias); la documentación no dice qué filtro deja solo las pacientes obstétricas. Por confirmar.
- **Columna MENORES repetida**: La consulta calcula dos veces la columna MENORES; en el modelo quedan MENORES y MENORES2.
- **Tarjeta año actual**: Las medidas documentadas son de años fijos (2024 y 2025) o del año anterior cerrado; ninguna corresponde a «año actual». Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.

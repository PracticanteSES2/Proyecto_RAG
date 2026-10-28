---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: PACIENTES OBSERVADOS
nombre_funcional: Pacientes en observación de urgencias por mes
bloque: Histórico
tablas: [OBSERVADOS, Calendario]
actualizado: 2026-10-20
version: 1
---

# PACIENTES OBSERVADOS

## Propósito
Muestra cuántos pacientes ingresan a observación de urgencias cada mes, compara los años y da el total y los promedios mensual y diario. Se llega con el botón PACIENTES OBSERVADOS de la página URGENCIAS.

## Fuentes de datos
- **OBSERVADOS**: Ingresos desde 2022-01-01 hasta hoy de tipo ambulatorio (AINTIPING = 1) que entran por urgencias (AINURGCON = 0) en las áreas 2 (urgencias) y 42 (gineco-obstetricia), con documento, aseguradora agrupada, fecha de ingreso, triage asociado (HCENTRIAGE) y grupo de edad. Se une al Calendario por fecha.

## Indicadores
- **Total de observados**: Ingresos con triage del año elegido o, sin año elegido, del año cerrado. Medida del modelo TOTAL_OBS (conteo distinto de HCENTRIAGE). Por confirmar que sea la de la tarjeta.
- **Promedio mensual de observados**: Observados del año elegido (o del año cerrado) divididos entre los meses de ese año con actividad hasta hoy. Medida Promedio_OBS_Dinamico.
- **Promedio diario de observados**: Promedio de observados por día del mes elegido o, sin mes, de todo el año elegido o cerrado. Medida Promedio_OBS_Diario_Dinamico.
- **Observados por año fijo**: Cálculo: OBSERVADOS_2025 = CALCULATE(COUNT(OBSERVADOS[HCENTRIAGE]), YEAR(OBSERVADOS[fecha]) = 2025); igual para 2024.

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes, Día y casillas MENORES (MAYORES DE EDAD / MENORES DE EDAD).
- **Gráfico de observados por mes**: Líneas «PACIENTES OBSERVADOS POR MES» con el recuento de HCENTRIAGE por mes, una línea por año.
- **Tabla de detalle anual**: Matriz de observados por año (filas) y mes (columnas).
- **Tarjetas de observados**: «TOTAL OBSERVADOS», «PROMEDIO MENSUAL OBSERVADOS» y «PROMEDIO DIARIO OBSERVADOS» (en una versión anterior: «OBSERVADOS AÑO ACTUAL» y «PROMEDIO PACIENTES OBSERVADOS»).
- **Botón de regreso**: Flecha que vuelve a URGENCIAS.

## Reglas de negocio
- **Paciente observado**: Ingreso ambulatorio por urgencias en el área de urgencias o de gineco-obstetricia; solo cuenta si tiene triage asociado (HCENTRIAGE no vacío).
- **Grupo de edad**: MENORES DE EDAD si la edad al ingreso es menor de 18 años.
- **Año por defecto**: Sin año elegido, las tarjetas muestran el año cerrado (año anterior al actual).

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Dos documentos**: La página está documentada en «Tablero Urgencias» y en «Pacientes Observados» con medidas distintas (OBSERVADOS_2024/2025 frente a las medidas dinámicas); las capturas más recientes usan las dinámicas.
- **Conteo distinto**: TOTAL_OBS cuenta triages distintos y el gráfico y OBSERVADOS_20xx cuentan filas; los totales pueden diferir levemente.
- **Columna MENORES repetida**: La consulta calcula MENORES dos veces con fórmulas equivalentes.
- **Incluye gineco-obstetricia**: El área 42 entra en este conteo aunque la página está en el grupo de urgencias; existe además PACIENTES OBSERVADOS OBSTETRICIA.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.

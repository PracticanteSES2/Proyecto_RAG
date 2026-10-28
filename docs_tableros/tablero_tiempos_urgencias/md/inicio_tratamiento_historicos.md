---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: INICIO TRATAMIENTO HISTORICOS
nombre_funcional: Inicio de tratamiento, histórico
bloque: Histórico
tablas: [INICIO_TRAT_HIST]
actualizado: 2026-10-28
version: 2
---

# INICIO TRATAMIENTO HISTORICOS

## Propósito
Muestra por año y mes la cantidad de ingresos y el tiempo promedio para el inicio del tratamiento, medido entre la consulta (primer folio) y el ingreso por enfermería (inicio de la estancia). Es el equivalente histórico de INGRESOS DIA. Se llega desde RESUMEN y desde MAPA DE CALOR TRATAMIENTOS.

## Fuentes de datos
- **INICIO_TRAT_HIST**: Ingresos desde el 01/01/2023 con primer folio en urgencias e ingreso por enfermería; FECHA es la fecha de admisión; tabla en Import.

## Indicadores
- **Ingresos**: Número de filas con documento y tiempo menor que 241 minutos. CALCULATE(COUNT(INICIO_TRAT_HIST[DOCUMENTO]), INICIO_TRAT_HIST[TIEMPO_INGRESO] < 241).
- **Tiempo promedio para inicio de tratamiento**: Minutos entre el primer folio en urgencias y el inicio de la estancia (HESFECING). CALCULATE(AVERAGE(INICIO_TRAT_HIST[TIEMPO_INGRESO]), INICIO_TRAT_HIST[TIEMPO_INGRESO] < 241).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de admisión.
- **Gráfico de ingresos y tiempo por mes**: Columnas INGRESOS y línea TIEMPO PROMEDIO PARA INICIO DE TRATAMIENTO en minutos, por año y mes. Filtro: TIEMPO_INGRESO menor que 241; su filtro sobre CONSULTA_URGENCIAS[TIPO_TRIAGE] no tiene efecto.
- **Botones de navegación**: Llevan a RESUMEN (regreso) y a MAPA DE CALOR TRATAMIENTOS.
- **Nombres de campos**: Nombres de los campos en el informe: segmentadores de Calendario[FECHA] «Date Año», «Date Mes», «Date Día».

## Reglas de negocio
- **Límite de 4 horas**: Se excluyen del gráfico los tiempos de 241 minutos o más; los valores negativos no se excluyen.

## Observaciones
- **Conteo de ingresos**: Se cuentan filas con documento, no pacientes ni ingresos distintos. Por confirmar si debe ser un conteo distinto de ingresos.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

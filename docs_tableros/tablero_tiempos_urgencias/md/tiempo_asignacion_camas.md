---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TIEMPO ASIGNACIÓN CAMAS
nombre_funcional: Tiempo para asignación de camas, histórico
bloque: Histórico
tablas: [TIEMPO_PARA_EGRESO]
actualizado: 2026-10-28
version: 2
---

# TIEMPO ASIGNACIÓN CAMAS

## Propósito
Muestra por año y mes la cantidad de pacientes de urgencias con orden de salida y el tiempo promedio entre su admisión y el inicio de su primera estancia (asignación de cama). Ningún botón lleva a esta página; solo se ve en modo edición y su botón de regreso lleva a RESUMEN.

## Fuentes de datos
- **TIEMPO_PARA_EGRESO**: Órdenes de salida no anuladas desde el 01/01/2023, de todas las unidades; FECHA es la fecha de la orden de salida; tabla en Import.

## Indicadores
- **Pacientes**: Número de ingresos de urgencias con orden de salida. CALCULATE(DISTINCTCOUNT(TIEMPO_PARA_EGRESO[INGRESO]), TIEMPO_PARA_EGRESO[SUBGRUPO] = "URGENCIAS").
- **Tiempo para asignación de cama**: Minutos entre la admisión (FECHAINGRESO) y el inicio de la primera estancia (FECINGCAMA). CALCULATE(AVERAGE(TIEMPO_PARA_EGRESO[TIEMPO_ASIG_CAMA]), TIEMPO_PARA_EGRESO[SUBGRUPO] = "URGENCIAS").

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de la orden de salida.
- **Gráfico de pacientes y tiempo por mes**: Columnas PACIENTES y línea TIEMPO PARA ASIGNACIÓN DE CAMA en minutos, por año y mes. Filtro: SUBGRUPO = URGENCIAS.
- **Botón de regreso**: Lleva a RESUMEN.
- **Nombres de campos**: Nombres de los campos en el informe: segmentadores de Calendario[FECHA] «Date Año», «Date Mes», «Date Día».

## Reglas de negocio
- **Mes del indicador**: El mes corresponde a la fecha de la orden de salida, no a la de admisión.
- **Sin filtro de validez**: El gráfico no excluye egresos con VALIDADOR = -1.

## Observaciones
- **Página inaccesible**: En modo lectura no se puede abrir porque ningún botón lleva a ella. Por confirmar si debe agregarse un botón en RESUMEN o eliminarse.
- **Qué mide realmente**: En urgencias el inicio de la estancia coincide con el ingreso por enfermería, así que este tiempo incluye la espera de consulta y de ingreso. Por confirmar si la intención era medir la asignación de cama de hospitalización.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

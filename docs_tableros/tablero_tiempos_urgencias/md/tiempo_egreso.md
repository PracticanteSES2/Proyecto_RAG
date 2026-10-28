---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TIEMPO EGRESO
nombre_funcional: Tiempo para el egreso, histórico
bloque: Histórico
tablas: [TIEMPO_PARA_EGRESO]
actualizado: 2026-10-28
version: 2
---

# TIEMPO EGRESO

## Propósito
Muestra por año y mes la cantidad de egresos válidos de urgencias y el tiempo promedio entre el último folio y la orden de salida. Se llega desde RESUMEN.

## Fuentes de datos
- **TIEMPO_PARA_EGRESO**: Órdenes de salida no anuladas desde el 01/01/2023, de todas las unidades; FECHA es la fecha de la orden de salida; tabla en Import.

## Indicadores
- **Tiempo promedio para el egreso**: Minutos entre el último folio de historia clínica y la orden de salida, egresos válidos de urgencias. CALCULATE(AVERAGE(TIEMPO_PARA_EGRESO[TIEMPO_EGRESO_OK]), TIEMPO_PARA_EGRESO[SUBGRUPO] = "URGENCIAS", TIEMPO_PARA_EGRESO[VALIDADOR] <> -1).
- **Egresos válidos**: Número de ingresos de urgencias con tiempo válido. CALCULATE(DISTINCTCOUNT(TIEMPO_PARA_EGRESO[INGRESO]), TIEMPO_PARA_EGRESO[SUBGRUPO] = "URGENCIAS", TIEMPO_PARA_EGRESO[VALIDADOR] <> -1).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de la orden de salida.
- **Tarjeta tiempo para el egreso**: Tiempo promedio para el egreso en minutos, con SUBGRUPO = URGENCIAS y VALIDADOR distinto de -1.
- **Gráfico de egresos y tiempo por mes**: Columnas EGRESOS VÁLIDOS y línea TIEMPO PROMEDIO PARA EL EGRESO en minutos, por año y mes, con los mismos filtros que la tarjeta.
- **Botón de regreso**: Lleva a RESUMEN.
- **Nombres de campos**: Nombres de los campos en el informe: segmentadores de Calendario[FECHA] «Date Año», «Date Mes», «Date Día».

## Reglas de negocio
- **Egresos válidos**: Tiempo mayor que 0 y hasta 720 minutos; los demás tienen VALIDADOR = -1 y se excluyen.
- **Restricción a urgencias**: La tabla trae todas las unidades; cada visual filtra SUBGRUPO = URGENCIAS.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

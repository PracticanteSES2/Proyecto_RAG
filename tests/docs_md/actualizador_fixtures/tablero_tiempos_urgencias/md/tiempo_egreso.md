---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TIEMPO EGRESO
nombre_funcional: Tiempo para el egreso, histórico
bloque: Histórico
tablas: [TIEMPO_PARA_EGRESO]
actualizado: 2026-10-20
version: 1
---

# TIEMPO EGRESO

## Propósito
Muestra por año y mes la cantidad de egresos válidos de urgencias y el tiempo promedio entre el último folio y la orden de salida. Se llega desde RESUMEN.

## Fuentes de datos
- **TIEMPO_PARA_EGRESO**: Órdenes de salida no anuladas desde el 01/01/2023 de todas las unidades; tabla importada.

## Indicadores
- **Tiempo promedio para el egreso**: Minutos entre el último folio y la orden de salida, solo urgencias y tiempos válidos. CALCULATE(AVERAGE(TIEMPO_PARA_EGRESO[TIEMPO_EGRESO_OK]), TIEMPO_PARA_EGRESO[SUBGRUPO] = "URGENCIAS", TIEMPO_PARA_EGRESO[VALIDADOR] <> -1).
- **Egresos válidos**: Conteo distinto de ingresos con SUBGRUPO = URGENCIAS y VALIDADOR distinto de -1.

## Visuales
- **Segmentadores de fecha**: Año, mes y día de la tabla Calendario; filtran todos los visuales de la página.
- **Tarjeta tiempo promedio para el egreso**: Promedio de TIEMPO_EGRESO_OK en minutos con los filtros del indicador.
- **Gráfico de egresos por mes**: Gráfico combinado; columnas con los egresos válidos y línea con el tiempo promedio para el egreso en minutos por año y mes.
- **Botones de navegación**: Llevan a RESUMEN (regreso).

## Reglas de negocio
- **Restricción a urgencias**: La tabla trae todas las unidades; cada visual filtra SUBGRUPO = URGENCIAS.
- **Fecha de la tabla**: Es la fecha de la orden de salida.
- **Egreso válido**: Tiempo mayor que 0 y menor o igual a 720 minutos; los demás tienen VALIDADOR = -1.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.

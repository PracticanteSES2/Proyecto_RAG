---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: MAPA DE CALOR TRIAGE
nombre_funcional: Mapa de calor de tiempos de triage
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE]
actualizado: 2026-10-20
version: 1
---

# MAPA DE CALOR TRIAGE

## Propósito
Muestra el tiempo promedio para triage por día de la semana y hora del triage, con una escala de color de verde (menor tiempo) a rojo (mayor tiempo), y la distribución de triages por clasificación. Sirve para identificar los días y horas con más demora en triage y planear el personal. Se llega desde RESUMEN_D, TIEMPO TRIAGE y LLEGADAS.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages desde el 01/01/2023 con tramo horario y día de la semana; tabla importada.

## Visuales
- **Segmentadores de fecha**: Año, mes y día de la tabla Calendario; filtran todos los visuales de la página.
- **Mapa de calor de tiempos en triage**: Matriz con el tramo horario en filas, el día de la semana en columnas y el promedio de MIN en minutos como valor. Color en degradado de verde (mínimo) a rojo (máximo), sin umbrales fijos.
- **Gráfico circular por clasificación triage**: Torta con la cantidad de triages por DESCRI_TRIGE. Excluye las clasificaciones obstétricas y MUERTO.
- **Botones de navegación**: Llevan a RESUMEN (regreso), TIEMPO TRIAGE y LLEGADAS.

## Reglas de negocio
- **Tramo horario**: Hora del triage truncada a la hora en punto.
- **Día de la semana**: Se calcula sobre la fecha del triage con WEEKDAY(fecha, 2), donde 1 es lunes.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.

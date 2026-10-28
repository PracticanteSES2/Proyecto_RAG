---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: MAPA DE CALOR TRIAGE
nombre_funcional: Mapa de calor de tiempos de triage
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE]
actualizado: 2026-10-28
version: 2
---

# MAPA DE CALOR TRIAGE

## Propósito
Muestra el tiempo promedio para triage por día de la semana y hora del triage, con color de verde (menor tiempo) a rojo (mayor tiempo), y la distribución de triages por clasificación. Sirve para ver los días y horas con más demora en triage y planear el personal. Se llega desde RESUMEN_D, TIEMPO TRIAGE y LLEGADAS.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages desde el 01/01/2023, excepto el código UA; FECHA es la fecha del triage; tabla en Import.

## Indicadores
- **Tiempo promedio para triage**: Minutos entre la toma del turno y el registro del triage, por tramo horario y día de la semana. AVERAGE(OPORTUNIDAD_TRIAGE[MIN]).
- **Cantidad por clasificación**: Número de triages por clasificación. DISTINCTCOUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha del triage.
- **Mapa de calor de triage**: Matriz con filas tramo horario del triage (TramoHorario), columnas día de la semana (DIA_SEMANA) y valor el promedio de MIN en minutos.
- **Gráfico circular por clasificación**: Cantidad de triages por DESCRI_TRIGE, sin clasificaciones obstétricas ni MUERTO.
- **Botones de navegación**: Llevan a RESUMEN (regreso), a TIEMPO TRIAGE y a LLEGADAS.
- **Nombres de campos**: Nombres de los campos en el informe: segmentadores de Calendario[FECHA] «Date Año», «Date Mes», «Date Día».

## Reglas de negocio
- **Color del mapa de calor**: Degradado relativo a los valores mostrados, verde para el mínimo y rojo para el máximo; no hay umbrales fijos.
- **Tramo horario del triage**: Hora del triage truncada a la hora en punto.
- **Día de la semana del triage**: Se calcula sobre la fecha del triage, de 1. LUNES a 7. DOMINGO.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

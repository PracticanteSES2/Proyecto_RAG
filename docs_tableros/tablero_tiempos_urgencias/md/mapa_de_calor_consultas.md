---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: MAPA DE CALOR CONSULTAS
nombre_funcional: Mapa de calor del tiempo para consulta
bloque: Histórico
tablas: [CONSULTA_URGENCIAS]
actualizado: 2026-10-20
version: 1
---

# MAPA DE CALOR CONSULTAS

## Propósito
Muestra el tiempo promedio entre admisión y consulta por día de la semana y hora de inicio de la consulta, con color de verde a rojo. No estaba en la documentación versión 1. Se llega desde TIEMPO PARA CONSULTA.

## Fuentes de datos
- **CONSULTA_URGENCIAS**: Triages desde el 01/01/2023 con admisión no anulada y su primer folio; FECHA es la fecha de admisión; tabla en Import.

## Indicadores
- **Tiempo promedio para atención en consulta**: Minutos entre la admisión y el primer folio, por tramo horario y día de la semana. AVERAGE(CONSULTA_URGENCIAS[MINUTOS_CONSULTA]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de admisión.
- **Mapa de calor de consultas**: Matriz con filas tramo horario de la consulta (TramoHorario_CONSULTA, hora del primer folio), columnas día de la semana (DIA_SEMANA_CONSULTA) y valor el promedio de MINUTOS_CONSULTA. Filtro: día de la semana no vacío.
- **Botón de regreso**: Lleva a TIEMPO PARA CONSULTA.

## Reglas de negocio
- **Color del mapa de calor**: Degradado de verde (mínimo) a rojo (máximo) relativo a los valores mostrados.
- **Día de la semana de la consulta**: Se calcula sobre la fecha del primer folio, de 1. LUNES a 7. DOMINGO.

## Observaciones
- **Sin exclusión de clasificaciones**: A diferencia de TIEMPO PARA CONSULTA, esta matriz no excluye clasificaciones obstétricas ni MUERTO.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.

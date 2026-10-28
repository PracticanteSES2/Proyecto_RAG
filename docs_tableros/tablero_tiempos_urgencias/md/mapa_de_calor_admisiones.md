---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: MAPA DE CALOR ADMISIONES
nombre_funcional: Mapa de calor del tiempo entre triage y admisión
bloque: Histórico
tablas: [CONSULTA_URGENCIAS]
actualizado: 2026-10-28
version: 2
---

# MAPA DE CALOR ADMISIONES

## Propósito
Muestra el tiempo promedio entre triage y admisión por día de la semana y hora de la admisión, con color de verde a rojo. No estaba en la documentación versión 1. Se llega desde TIEMPO TRIAGE-ADMISION.

## Fuentes de datos
- **CONSULTA_URGENCIAS**: Triages desde el 01/01/2023 con admisión no anulada y su primer folio; FECHA es la fecha de admisión; tabla en Import.

## Indicadores
- **Tiempo promedio para admisión**: Minutos entre el registro del triage y la admisión, por tramo horario y día de la semana. AVERAGE(CONSULTA_URGENCIAS[MINUTOS_ADMISION]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de admisión.
- **Mapa de calor de admisiones**: Matriz con filas tramo horario de la admisión (TramoHorario_ADM), columnas día de la semana (DIA_SEMANA_CONSULTA) y valor el promedio de MINUTOS_ADMISION. Filtros: día de la semana no vacío y MINUTOS_ADMISION mayor o igual a 0.
- **Botón de regreso**: Lleva a TIEMPO TRIAGE-ADMISION.
- **Nombres de campos**: Nombres de los campos en el informe: segmentadores de Calendario[FECHA] «Date Año», «Date Mes», «Date Día».

## Reglas de negocio
- **Color del mapa de calor**: Degradado de verde (mínimo) a rojo (máximo) relativo a los valores mostrados.
- **Tiempos negativos excluidos**: Se excluyen las admisiones registradas antes que el triage.

## Observaciones
- **Día de la semana de la consulta**: El día se calcula sobre la fecha del primer folio (consulta), mientras que la hora es la de la admisión. Por confirmar si debería usarse la fecha de admisión.
- **Sin exclusión de clasificaciones**: A diferencia de TIEMPO TRIAGE-ADMISION, esta matriz no excluye clasificaciones obstétricas ni MUERTO.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: LLEGADAS
nombre_funcional: Mapa de calor de llegadas
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE]
actualizado: 2026-10-28
version: 2
---

# LLEGADAS

## Propósito
Muestra cuántos pacientes llegan al servicio por día de la semana y hora de llegada (hora del turno del digiturno), con color de verde a rojo. Sirve para reconocer los picos de demanda y anticipar la carga asistencial. Se llega desde MAPA DE CALOR TRIAGE.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages desde el 01/01/2023, excepto el código UA; FECHA es la fecha del triage; tabla en Import.

## Indicadores
- **Llegadas**: Número de triages con documento registrado y hora de llegada. COUNT(OPORTUNIDAD_TRIAGE[GPADOCUME]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha del triage.
- **Mapa de calor de llegadas**: Matriz con filas tramo horario de llegada (TramoHorario_Llegada), columnas día de la semana (DIA_SEMANA) y valor el número de llegadas. Filtro: hora de llegada no vacía.
- **Botón de regreso**: Lleva a MAPA DE CALOR TRIAGE.
- **Nombres de campos**: Nombres de los campos en el informe: segmentadores de Calendario[FECHA] «Date Año», «Date Mes», «Date Día».

## Reglas de negocio
- **Color del mapa de calor**: Degradado verde, amarillo y rojo relativo a los valores mostrados.
- **Conteo de triages**: Se cuentan triages, no pacientes distintos; un paciente con dos triages cuenta dos veces.
- **Solo con turno**: Solo cuentan los triages con turno de digiturno (con hora de llegada).

## Observaciones
- **Día de la semana del triage**: El día corresponde a la fecha del triage, no a la del turno; solo difieren si turno y triage caen en días distintos.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TIEMPO TRIAGE
nombre_funcional: Tiempo de triage histórico
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE]
actualizado: 2026-10-20
version: 1
---

# TIEMPO TRIAGE

## Propósito
Muestra por año y mes la cantidad de triages realizados y el tiempo promedio entre la toma del turno y el triage, para relacionar la demanda con la oportunidad. Se llega desde RESUMEN y desde MAPA DE CALOR TRIAGE.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages desde el 01/01/2023 con la hora del turno y la hora del triage; tabla importada.
- **Calendario**: Tabla de fechas del 01/01/2023 a hoy; se relaciona con OPORTUNIDAD_TRIAGE[FECHA].

## Indicadores
- **Cantidad de triages**: Conteo distinto de triages. DISTINCTCOUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE]).
- **Tiempo promedio para triage**: Minutos entre la toma del turno y el registro del triage. AVERAGE(OPORTUNIDAD_TRIAGE[MIN]).

## Visuales
- **Segmentadores de fecha**: Año, mes y día de la tabla Calendario; filtran todos los visuales de la página.
- **Segmentador tipo de triage**: Filtra por OPORTUNIDAD_TRIAGE[DESCRI_TRIGE]; excluye las clasificaciones obstétricas y MUERTO, de modo que solo se elige I, II, III, IV o V.
- **Gráfico de triages por mes**: Gráfico combinado; columnas con la cantidad de triages y línea con el tiempo promedio en minutos por año y mes.
- **Botones de navegación**: Llevan a RESUMEN (regreso) y a MAPA DE CALOR TRIAGE.

## Reglas de negocio
- **Triages incluidos**: OPORTUNIDAD_TRIAGE incluye todos los triages desde el 01/01/2023 excepto el código UA.
- **Sin tipo de triage elegido**: Si no se elige ningún tipo, el gráfico incluye todas las clasificaciones.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.

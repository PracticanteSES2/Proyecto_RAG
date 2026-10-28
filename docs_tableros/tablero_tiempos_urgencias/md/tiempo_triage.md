---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TIEMPO TRIAGE
nombre_funcional: Tiempo de triage histórico
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE]
actualizado: 2026-10-28
version: 2
---

# TIEMPO TRIAGE

## Propósito
Muestra por año y mes la cantidad de triages y el tiempo promedio entre la toma del turno y el triage, para relacionar la demanda con la oportunidad. Se llega desde RESUMEN y desde MAPA DE CALOR TRIAGE.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages desde el 01/01/2023, excepto el código UA; FECHA es la fecha del triage; tabla en Import.

## Indicadores
- **Cantidad de triages**: Número de triages. DISTINCTCOUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE]).
- **Tiempo promedio para triage**: Minutos entre la toma del turno en el digiturno y el registro del triage; los triages sin turno no cuentan. AVERAGE(OPORTUNIDAD_TRIAGE[MIN]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha del triage.
- **Segmentador tipo de triage**: Filtra por OPORTUNIDAD_TRIAGE[DESCRI_TRIGE]; la lista excluye las clasificaciones obstétricas y MUERTO, así que solo ofrece I, II, III, IV y V.
- **Gráfico de triages y tiempo por mes**: Columnas CANTIDAD DE TRIAGES y línea con el promedio de MIN en minutos, por año y mes.
- **Botones de navegación**: Llevan a RESUMEN (regreso) y a MAPA DE CALOR TRIAGE.
- **Nombres de campos**: Nombres de los campos en el informe: segmentadores de Calendario[FECHA] «Date Año», «Date Mes», «Date Día».

## Reglas de negocio
- **Sin selección de triage**: Si no se elige ningún tipo en el segmentador, el gráfico incluye todas las clasificaciones, también las obstétricas y MUERTO.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

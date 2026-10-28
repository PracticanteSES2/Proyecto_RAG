---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TIEMPO PARA CONSULTA
nombre_funcional: Tiempo para consulta, histórico
bloque: Histórico
tablas: [CONSULTA_URGENCIAS]
actualizado: 2026-10-20
version: 1
---

# TIEMPO PARA CONSULTA

## Propósito
Muestra por año y mes la cantidad de pacientes atendidos en consulta y el tiempo promedio entre la admisión y el inicio de la consulta. Se llega desde RESUMEN y desde MAPA DE CALOR CONSULTAS.

## Fuentes de datos
- **CONSULTA_URGENCIAS**: Triages desde el 01/01/2023 con admisión no anulada y su primer folio, excepto UA; FECHA es la fecha de admisión; tabla en Import.

## Indicadores
- **Cantidad de consultas**: Número de triages con admisión. DISTINCTCOUNT(CONSULTA_URGENCIAS[OID_TRIAGE]).
- **Tiempo promedio para atención en consulta**: Minutos entre la admisión y el primer folio de historia clínica. AVERAGE(CONSULTA_URGENCIAS[MINUTOS_CONSULTA]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de admisión.
- **Segmentador clasificación triage**: Filtra por CONSULTA_URGENCIAS[TIPO_TRIAGE].
- **Gráfico de consultas y tiempo por mes**: Columnas CANTIDAD y línea TIEMPO PROMEDIO PARA ATENCIÓN EN CONSULTA en minutos, por año y mes.
- **Botones de navegación**: Llevan a RESUMEN (regreso) y a MAPA DE CALOR CONSULTAS.

## Reglas de negocio
- **Clasificaciones excluidas**: El segmentador y el gráfico excluyen EMERGENCIA OBSTETRICA - I-G, MUERTO, NO URGENTE OBSTETRICA - IV-G, URGENCIA MEDICA OBSTETRICA - II-G y URGENCIA OBSTETRICA - III-G.
- **Triages sin folio**: Un triage con admisión cuenta aunque todavía no tenga folio de consulta; en ese caso no aporta tiempo al promedio.

## Observaciones
- **Criterio distinto al de RESUMEN**: La tarjeta de consulta de RESUMEN solo incluye triage I a V, mientras que esta página incluye también CONSULTA EXTERNA OBSTETRICA - V-G.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.

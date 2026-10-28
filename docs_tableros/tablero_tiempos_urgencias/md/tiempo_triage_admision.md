---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TIEMPO TRIAGE-ADMISION
nombre_funcional: Tiempo entre triage y admisión, histórico
bloque: Histórico
tablas: [CONSULTA_URGENCIAS]
actualizado: 2026-10-28
version: 2
---

# TIEMPO TRIAGE-ADMISION

## Propósito
Muestra por año y mes la cantidad de admisiones y el tiempo promedio entre el triage y la admisión, y la distribución de admisiones por tipo de triage. Se llega desde RESUMEN y desde MAPA DE CALOR ADMISIONES.

## Fuentes de datos
- **CONSULTA_URGENCIAS**: Triages desde el 01/01/2023 con admisión no anulada (estado distinto de 2 y 4) y su primer folio, excepto UA; FECHA es la fecha de admisión; tabla en Import.

## Indicadores
- **Admisiones**: Número de admisiones. DISTINCTCOUNT(CONSULTA_URGENCIAS[OID_ADMISION]).
- **Tiempo promedio para admisión**: Minutos entre el registro del triage y la admisión. AVERAGE(CONSULTA_URGENCIAS[MINUTOS_ADMISION]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de admisión.
- **Segmentador clasificación triage**: Filtra por CONSULTA_URGENCIAS[TIPO_TRIAGE].
- **Gráfico de admisiones y tiempo por mes**: Columnas ADMISIONES y línea TIEMPO PROMEDIO PARA ADMISION en minutos, por año y mes.
- **Gráfico circular admisiones por tipo triage**: Admisiones por TIPO_TRIAGE.
- **Botones de navegación**: Llevan a RESUMEN (regreso) y a MAPA DE CALOR ADMISIONES.
- **Nombres de campos**: Nombres de los campos en el informe: segmentadores de Calendario[FECHA] «Date Año», «Date Día».

## Reglas de negocio
- **Clasificaciones excluidas**: El segmentador y los dos gráficos excluyen EMERGENCIA OBSTETRICA - I-G, MUERTO, NO URGENTE OBSTETRICA - IV-G, URGENCIA MEDICA OBSTETRICA - II-G y URGENCIA OBSTETRICA - III-G.
- **V-G incluida**: La exclusión no incluye CONSULTA EXTERNA OBSTETRICA - V-G, que sí puede aparecer.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

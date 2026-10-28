---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: OBSERVACIÓN HISTORICO
nombre_funcional: Observación, histórico
bloque: Histórico
tablas: [OBSERV_HIST]
actualizado: 2026-10-28
version: 2
---

# OBSERVACIÓN HISTORICO

## Propósito
Muestra por año y mes la cantidad de pacientes que pasaron por observación y el tiempo promedio que permanecieron en ella. Se llega desde RESUMEN.

## Fuentes de datos
- **OBSERV_HIST**: Ingresos desde el 01/01/2023 con primer folio en urgencias, estancia iniciada y fin de observación definido; FECHA es la fecha de egreso; tabla en Import.

## Indicadores
- **Pacientes observados**: Número de ingresos que terminaron la observación. DISTINCTCOUNT(OBSERV_HIST[INGRESO]).
- **Tiempo en observación**: Minutos entre el inicio de la estancia y el fin de la observación (solicitud de hospitalización o egreso). AVERAGE(OBSERV_HIST[TIEMPO_OBSERVACION]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de egreso.
- **Gráfico de observados y tiempo por mes**: Columnas PACIENTES OBSERVADOS y línea TIEMPO EN OBSERVACIÓN en minutos, por año y mes. Sus filtros sobre CONSULTA_URGENCIAS e INICIO_TRAT_HIST no tienen efecto.
- **Botón de regreso**: Lleva a RESUMEN.
- **Nombres de campos**: Nombres de los campos en el informe: segmentadores de Calendario[FECHA] «Date Año», «Date Mes», «Date Día».

## Reglas de negocio
- **Fecha de la tabla**: El filtro por año y mes usa la fecha de egreso del paciente.

## Observaciones
- **Pacientes sin egreso**: Los pacientes cuya observación terminó con solicitud de hospitalización y aún no tienen egreso quedan sin fecha y no se ubican en ningún mes. Por confirmar si la fecha debería ser la del fin de la observación.
- **Filtro de 240 minutos sin efecto**: El visual parece pensado para excluir tiempos de más de 240 minutos (TIEMPO_INGRESO < 241), pero el filtro está sobre INICIO_TRAT_HIST y no se aplica.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

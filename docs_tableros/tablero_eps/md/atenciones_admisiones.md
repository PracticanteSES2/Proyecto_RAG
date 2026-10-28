---
tablero: TABLERO EPS
pagina: %ATENCIONES/ADMISIONES
nombre_funcional: Porcentaje de atenciones frente a admisiones por hora y día de la semana
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE, ADMISIONES_TRIAGE, ATENCIONES_DIA, Calendario]
actualizado: 2026-10-28
version: 2
id_pagina: ReportSection0b34ce4c5500371b02d0
---

# %ATENCIONES/ADMISIONES

## Propósito
Compara las atenciones (triages realizados) con las admisiones o llegadas a urgencias por tramo horario y día de la semana, para ver en qué horas el servicio responde menos a la demanda. Es histórica (desde 2022), con una tabla adicional del día en curso. Se llega con el botón %ATENCIONES de la página principal.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages desde el 2022-01-01 con tramo horario y día de la semana; excluye la clasificación UA.
- **ADMISIONES_TRIAGE**: Llegadas a triage desde el 2022-01-01; es el denominador de las admisiones.
- **ATENCIONES_DIA**: Por cada hora de hoy, triages realizados (HCNTRIAGE), llegadas (ADMISIONTRIAGE) y pendientes; se recalcula con cada actualización.

## Indicadores
- **Porcentaje de atenciones por tramo**: Relación entre atenciones y admisiones en cada hora y día de la semana. Unidad: porcentaje. Medida [%ATENCIONES] = triages distintos (OPORTUNIDAD_TRIAGE[OID_TRIAGE]) entre admisiones distintas (ADMISIONES_TRIAGE[Oid]).
- **Porcentaje de atendidos del día**: Atendidos de la hora sobre llegadas de la hora más pendientes acumulados. Unidad: porcentaje. Medida [%ATENDIDOS] = SUM(ATENCIONES_DIA[ATENDIDOS]) / (SUM(LLEGADAS) + SUM(PENDIENTES_ACUMULADOS)).
- **Pendientes por tramo**: Llegadas menos atendidos en la hora (PENDIENTES_TRAMO). Unidad: pacientes.
- **Pendientes acumulados**: Suma acumulada de pendientes desde el inicio del día; si es negativa se muestra 0 (PENDIENTES_ACUMULADOS). Unidad: pacientes.

## Visuales
- **Filtros de segmentación**: Listas de Año, Mes y Día (segmentadores «Fecha Año», «Fecha Mes» y «Fecha Día» de Calendario[Fecha]) y ASEGURADORA (OPORTUNIDAD_TRIAGE[ASEGURADORA]).
- **Matriz de porcentaje de atenciones**: Matriz «DIA_SEMANA» con OPORTUNIDAD_TRIAGE[DIA_SEMANA] y [TramoHorario] y la medida [%ATENCIONES]. Filas por tramo horario (12:00 a. m. a 11:00 p. m.) y columnas por día de la semana (1. LUNES a 7. DOMINGO) con totales; escala de color de rojo (porcentaje bajo) a verde (alto).
- **Tabla atención día actual**: Titulada «ATENCIÓN DÍA ACTUAL»; columnas TRAMO y %ATENDIDOS de cada hora de hoy, con total y color verde para valores altos.
- **Control de reproducción por mes**: Visual personalizado «MES» (OPORTUNIDAD_TRIAGE[MES]) con botones de reproducir, pausar, detener y avanzar que recorren los meses y animan la matriz.
- **Botones de navegación**: VOLVER regresa a la página principal; GRÁFICO DE DISPERSIÓN lleva a DISPERSIÓN GENERAL.

## Reglas de negocio
- **Tramo horario**: La hora del triage y de la llegada se trunca a la hora en punto para agrupar.
- **Llegadas y atendidos del día**: Solo cuentan registros con fecha de hoy; las horas sin llegadas o sin atenciones se completan con 0.
- **Piso de pendientes acumulados**: La consulta SQL corta el acumulado en 0 cuando la suma da negativa.

## Observaciones
- **Cruce solo por documento**: [%ATENCIONES] cruza triages y admisiones por documento del paciente, sin fecha ni tramo; por eso el total de la captura (107,48 %) supera 100 %. Por confirmar.
- **Valor «Infinito»**: En la tabla del día aparece «Infinito» en horas sin llegadas y valores mayores a 100 % cuando se atienden pacientes que llegaron en horas anteriores; la división no protege el denominador cero.
- **Denominador de %ATENDIDOS**: Suma las llegadas de la hora y los pendientes acumulados, que ya incluyen los de la propia hora. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

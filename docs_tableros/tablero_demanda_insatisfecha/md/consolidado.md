---
tablero: DEMANDA INSATISFECHA
pagina: CONSOLIDADO
nombre_funcional: Resumen de la demanda insatisfecha institucional
bloque: Histórico
tablas: [TRIAGE, TRIAGES_REALIZADOS, REFERENCIA, REFERENCIA_ACEPTADO, CIRUGÍAS, CIRUGIAS REALIZADAS, CITAS MEDICAS, CITAS_REALIZADAS, SOLICITUD DE CAMAS, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# CONSOLIDADO

## Propósito
Página de inicio del tablero. Resume la demanda insatisfecha total y por componente (triages, referencia, cirugías, citas canceladas y hospitalización), su evolución mensual, su distribución por asegurador y por tipo de servicio, y cinco indicadores normalizados por cada 100 o 1.000 eventos. Es de análisis histórico por año y mes. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **Tablas de componentes**: Usa las tablas de las páginas de detalle (TRIAGE, REFERENCIA, CIRUGÍAS, CITAS MEDICAS y SOLICITUD DE CAMAS); sus consultas se describen en cada página.
- **Tablas de eventos atendidos**: TRIAGES_REALIZADOS, REFERENCIA_ACEPTADO, CIRUGIAS REALIZADAS y CITAS_REALIZADAS sirven de denominador de los indicadores normalizados. Sus consultas no están documentadas.
- **CALENDARIO**: Tabla de fechas que alimenta los filtros de Año y Mes y donde se guardan las medidas consolidadas.

## Indicadores
- **Total demanda insatisfecha**: Suma de los cinco componentes. DAX: DISTINCTCOUNT(TRIAGE[OID]) + DISTINCTCOUNT(REFERENCIA[OID]) + COUNT('CIRUGÍAS'[PROCEDIMIENTO]) + DISTINCTCOUNT('CITAS MEDICAS'[OID]) + SUM('SOLICITUD DE CAMAS'[DEMANDA_INS]).
- **Promedio mensual**: Total demanda insatisfecha dividido por el número del mes actual. DAX: DIVIDE([TOTAL_DEMANDA_INSATISFECHA], MONTH(TODAY())).
- **Tarjetas por componente**: TRIAGES, REFERENCIA, CIRUGÍAS, CITAS CANCELADAS y HOSPITALIZACIÓN muestran el total de cada componente con el mismo cálculo que el total.
- **Participación por componente**: Medidas %TRIAGE, %REFERENCIA, %CIRUGIAS y %CITAS; cada una divide el total del componente entre [TOTAL_DEMANDA_INSATISFECHA].
- **No atendidos por cada 100 triages**: Medida RELACIÓN TRIAGES. DAX: (DISTINCTCOUNT(TRIAGE[OID]) / DISTINCTCOUNT(TRIAGES_REALIZADOS[OID])) * 100.
- **Canceladas por cada 1.000 citas asignadas**: Medida RELACIÓN CITAS. Citas canceladas entre citas realizadas distintas de ENFERMERIA, por 1.000. DAX: DIVIDE(DISTINCTCOUNT('CITAS MEDICAS'[OID]), CALCULATE(DISTINCTCOUNT(CITAS_REALIZADAS[OID]), CITAS_REALIZADAS[GEEDESCRI] <> "ENFERMERIA")) * 1000.
- **No aceptados por cada 100 aceptados**: Medida RELACIÓN ACEPTADOS. Pacientes no aceptados entre referencias aceptadas sin causa registrada, por 100. DAX: DIVIDE(DISTINCTCOUNT(REFERENCIA[OID]), CALCULATE(DISTINCTCOUNT(REFERENCIA_ACEPTADO[OID]), ISBLANK(REFERENCIA_ACEPTADO[CAUSA]))) * 100.
- **No oportunas por cada 100 oportunas**: Medida RELACIÓN CIRUGIAS. Cirugías de la tabla CIRUGÍAS entre cirugías realizadas con TIEMPO_CIRUGÍA_R de 45 o menos, por 100. DAX: DIVIDE(COUNT('CIRUGÍAS'[PROCEDIMIENTO]), CALCULATE(COUNT('CIRUGIAS REALIZADAS'[PROCEDIMIENTO]), 'CIRUGIAS REALIZADAS'[TIEMPO_CIRUGÍA_R] <= 45)) * 100.
- **No asignadas por cada 100 camas**: Medida RELACIÓN SOLICITUD CAMAS. DAX: DIVIDE(SUM('SOLICITUD DE CAMAS'[DEMANDA_INS]), DISTINCTCOUNT('SOLICITUD DE CAMAS'[Oid])) * 100.

## Visuales
- **Tarjetas superiores**: Siete tarjetas: TOTAL DEMANDA INSATISFECHA, PROMEDIO MENSUAL, TRIAGES, REFERENCIA, CIRUGÍAS, CITAS CANCELADAS y HOSPITALIZACIÓN.
- **Gráfico de barras mensual**: Columnas con la demanda insatisfecha total por mes (enero a diciembre).
- **Treemap por asegurador**: Titulado «DEMANDA INSATISFECHA por ASEGURADOR»; reparte el total según el asegurador del paciente.
- **Gráfico circular por tipo de servicio**: Participación porcentual de TRIAGES, CIRUGIAS, CITAS y REFERENCIA en el total.
- **Indicadores normalizados**: Cinco tarjetas a la derecha: NO ATENDIDOS / 100 TRIAGES, CANCELADAS / 1000 CITAS ASIGNADAS, NO ACEPTADOS / 100 ACEPTADOS, NO OPORTUNAS / 100 OPORTUNAS y NO ASIGNADAS/100 CAMAS ASIGNADAS.
- **Filtros y botones**: Segmentadores de Año y Mes y botones de navegación TRIAGES, REFERENCIA, CIRUGÍAS, AMBULATORIO y HOSPITALIZACIÓN (camas).

## Reglas de negocio
- **Componente hospitalización**: Cuenta solo las solicitudes de cama marcadas en la columna DEMANDA_INS (ver página SOLICITUD CAMAS).
- **Citas de enfermería**: Se excluyen del denominador de citas asignadas (GEEDESCRI distinto de ENFERMERIA).
- **Cirugía oportuna**: Para el indicador de cirugías, una cirugía realizada es oportuna si TIEMPO_CIRUGÍA_R es 45 o menos. Unidad del tiempo por confirmar.

## Observaciones
- **Hospitalización fuera del circular**: El gráfico circular no incluye hospitalización (camas), aunque sí suma en el total.
- **Etiqueta de camas**: La tarjeta dice «NO ASIGNADAS/100 CAMAS ASIGNADAS», pero el denominador son todas las solicitudes de cama, no solo las asignadas.
- **División sin DIVIDE**: RELACIÓN TRIAGES usa el operador / en lugar de DIVIDE; puede dar error si no hay triages realizados en el filtro.
- **Tablas de realizados**: Las consultas de TRIAGES_REALIZADOS, REFERENCIA_ACEPTADO, CIRUGIAS REALIZADAS y CITAS_REALIZADAS no están documentadas; por confirmar.
- **Promedio mensual**: Divide por el mes actual aunque el total incluya todos los años filtrados; con Año en «Todas» el promedio no corresponde a un promedio real por mes.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.

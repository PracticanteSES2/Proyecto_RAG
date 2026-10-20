---
tablero: DEMANDA INSATISFECHA
pagina: REFERENCIA
nombre_funcional: Pacientes de referencia no aceptados
bloque: Histórico
tablas: [REFERENCIA]
actualizado: 2026-10-20
version: 1
---

# REFERENCIA

## Propósito
Analiza los pacientes remitidos por otras instituciones que el hospital no aceptó: total, promedio mensual, evolución por mes y causa, y distribución por causa y por asegurador. Es de análisis histórico; se llega desde el botón REFERENCIA de CONSOLIDADO. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **REFERENCIA**: Solicitudes de recepción de pacientes (RECEPCIONES_DW) con llamada desde el 1 de enero de 2025 hasta hoy. Trae paciente, edad, fechas de llamada, llegada estimada, ingreso, aceptación y no aceptación, servicio, prestador, EPS, estado, causa de no aceptación (SEG_RECEPCIONES), especialidad y asegurador. FECHA es la fecha de la llamada.

## Indicadores
- **Pacientes no aceptados**: Número de solicitudes de referencia no aceptadas. DAX: DISTINCTCOUNT(REFERENCIA[OID]).
- **Promedio mensual**: Medida PROM_TRAMITES: solicitudes con llamada en el año en curso divididas por el número del mes actual. DAX: DIVIDE(CALCULATE(COUNT(REFERENCIA[OID]), YEAR(REFERENCIA[FECHALLAMADA]) = YEAR(TODAY())), MONTH(TODAY())).

## Visuales
- **Tarjetas**: NO ACEPTADOS y PROMEDIO MENSUAL.
- **Gráfico de columnas por año, mes y causa**: Titulado «PACIENTES NO ACEPTADOS por Año, Mes y CAUSA»; columnas agrupadas por causa para cada mes.
- **Gráfico circular por causa**: Titulado «NO ACEPTADOS por CAUSA»; participación de cada causa (por ejemplo supera la capacidad instalada, no disponibilidad de cama, no especialidad, no disponibilidad de equipos, menor de edad).
- **Gráfico de barras por asegurador**: Titulado «NO ACEPTADOS por ASEGURADOR»; cantidad de no aceptados por asegurador.
- **Filtros**: Segmentadores de Año, Mes y ASEGURADOR, y botón de inicio que vuelve a CONSOLIDADO.

## Reglas de negocio
- **Fecha de no aceptación**: Es la última fecha de edición en que la solicitud pasó al estado 3 (no aceptada) según HISTORICO_RECEPCIONES_DW; solo se llena si el estado actual es 3.
- **Fecha de aceptación vacía**: Si FECHAACEPTADO viene como texto vacío se deja nula.

## Observaciones
- **Filtro de no aceptados**: La consulta documentada no filtra por estado; por confirmar dónde se limita la tabla a los no aceptados (filtro de página, de visual o en Power Query).
- **Promedio mensual por confirmar**: La medida del promedio de esta página no está identificada en la documentación; PROM_TRAMITES es la candidata por su tabla y fecha.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.

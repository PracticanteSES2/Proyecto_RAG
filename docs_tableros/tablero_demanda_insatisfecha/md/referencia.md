---
tablero: DEMANDA INSATISFECHA
pagina: REFERENCIA
nombre_funcional: Pacientes de referencia no aceptados
bloque: Histórico
tablas: [REFERENCIA]
actualizado: 2026-10-28
version: 2
---

# REFERENCIA

## Propósito
Analiza los pacientes remitidos por otras instituciones que el hospital no aceptó: total, promedio mensual, evolución por mes y causa, y distribución por causa y por asegurador. Es de análisis histórico; se llega desde el botón REFERENCIA de CONSOLIDADO. Página oculta en Power BI (solo CONSOLIDADO es visible).

## Fuentes de datos
- **REFERENCIA**: Solicitudes de recepción de pacientes (RECEPCIONES_DW) con llamada desde el 1 de enero de 2025 hasta hoy. Trae paciente, edad, fechas de llamada, llegada estimada, ingreso, aceptación y no aceptación, servicio, prestador, EPS, estado, causa de no aceptación (SEG_RECEPCIONES), especialidad y asegurador. FECHA es la fecha de la llamada.

## Indicadores
- **Pacientes no aceptados**: Número de solicitudes de referencia no aceptadas. DAX: DISTINCTCOUNT(REFERENCIA[OID]).
- **Promedio mensual**: Medida PROM_TRAMITES, que usa la tarjeta PROMEDIO MENSUAL: solicitudes con llamada en el año en curso divididas por el número del mes actual. DAX: DIVIDE(CALCULATE(COUNT(REFERENCIA[OID]), YEAR(REFERENCIA[FECHALLAMADA]) = YEAR(TODAY())), MONTH(TODAY())). Unidad: solicitudes por mes.

## Visuales
- **Tarjetas**: NO ACEPTADOS y PROMEDIO MENSUAL.
- **Gráfico de columnas por año, mes y causa**: Titulado «PACIENTES NO ACEPTADOS por Año, Mes y CAUSA»; columnas agrupadas por causa para cada mes.
- **Gráfico circular por causa**: Titulado «NO ACEPTADOS por CAUSA»; participación de cada causa (por ejemplo supera la capacidad instalada, no disponibilidad de cama, no especialidad, no disponibilidad de equipos, menor de edad).
- **Gráfico de barras por asegurador**: Titulado «NO ACEPTADOS por ASEGURADOR»; cantidad de no aceptados por asegurador.
- **Filtros**: Segmentadores «Date Año» y «Date Mes» (CALENDARIO[Date]) y «ASEGURADOR» (REFERENCIA[nombreps]), y botón de inicio que vuelve a CONSOLIDADO.

## Reglas de negocio
- **Fecha de no aceptación**: Es la última fecha de edición en que la solicitud pasó al estado 3 (no aceptada) según HISTORICO_RECEPCIONES_DW; solo se llena si el estado actual es 3.
- **Fecha de aceptación vacía**: Si FECHAACEPTADO viene como texto vacío se deja nula.
- **Filtro de página**: Se excluyen las solicitudes con CAUSA vacía o con las causas «Aceptado por otra institución», «Es de menor complejidad», «No contratación» y «NO HABILITACIÓN»; lo que queda son los no aceptados por causas atribuibles al hospital.

## Observaciones
- **Asegurador distinto**: La página usa REFERENCIA[nombreps] como asegurador, mientras CONSOLIDADO usa TERCEROS[TERNOMCOM]; los nombres pueden no coincidir.
- **Conteo del promedio**: PROM_TRAMITES cuenta filas con COUNT y la tarjeta NO ACEPTADOS cuenta solicitudes distintas; si una solicitud tiene varias causas pueden diferir.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

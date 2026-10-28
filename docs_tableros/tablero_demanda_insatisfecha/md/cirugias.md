---
tablero: DEMANDA INSATISFECHA
pagina: CIRUGIAS
nombre_funcional: Cirugías dentro de la demanda insatisfecha
bloque: Histórico
tablas: [CIRUGÍAS]
actualizado: 2026-10-20
version: 1
---

# CIRUGIAS

## Propósito
Analiza las cirugías que el tablero suma como demanda insatisfecha: total, promedio mensual, distribución por mes y por asegurador. Es de análisis histórico; se llega desde el botón CIRUGÍAS de CONSOLIDADO. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **CIRUGÍAS**: Solicitudes de cirugía programada (TipoCirugiaOid = 1) cuya fecha de planeación es del 1 de enero de 2025 en adelante. Trae paciente, EPS, especialidad, procedimientos, médico, asegurador, estado actual y la primera fecha de cada estado quirúrgico (planeada, por autorizar, programado, en quirófano, cancelado, entre otros). FECHA es la fecha de planeación.

## Indicadores
- **Total cirugías**: Número de solicitudes con procedimiento registrado. DAX: COUNT('CIRUGÍAS'[PROCEDIMIENTO]).
- **Promedio mensual**: Cirugías planeadas en el año en curso divididas por el número del mes actual. Medida PROM_CIRUGÍAS: DIVIDE(CALCULATE(COUNT('CIRUGÍAS'[PROCEDIMIENTO]), YEAR('CIRUGÍAS'[Planeada]) = YEAR(TODAY())), MONTH(TODAY())).

## Visuales
- **Tarjetas**: TOTAL y PROMEDIO MENSUAL.
- **Gráfico de columnas por mes**: Titulado «CIRUGÍAS por Mes»; cantidad mensual de cirugías.
- **Treemap por asegurador**: Titulado «CIRUGÍAS por ASEGURADOR»; distribución por asegurador.
- **Filtros**: Segmentadores de Año, Mes y ASEGURADOR, y botón de inicio que vuelve a CONSOLIDADO.

## Reglas de negocio
- **Fechas de estado**: Para cada solicitud se toma la primera fecha en que pasó por cada estado (códigos EstadoQxOid 1, 36, 18, 24, 6, 23, 19, 5, 7, 9, 10, 11, 13 y 8) registrado desde 2025.
- **Procedimientos agrupados**: Los procedimientos de una solicitud se concatenan en una sola celda separados por « * »; cada solicitud cuenta una vez.
- **Médico**: Si el médico es el genérico (DoctorOId = 5000) se usa el nombre del médico que solicita.

## Observaciones
- **Criterio de demanda insatisfecha**: La documentación describe la página como «cirugías realizadas» y la consulta no filtra cirugías canceladas ni tardías; en CONSOLIDADO este conteo se usa como «no oportunas». Por confirmar qué cirugías deben contar como demanda insatisfecha.
- **Promedio mensual bajo**: En la captura de la documentación el promedio mensual muestra 1 con un total de miles; ocurre porque solo cuenta cirugías planeadas en el año en curso.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.

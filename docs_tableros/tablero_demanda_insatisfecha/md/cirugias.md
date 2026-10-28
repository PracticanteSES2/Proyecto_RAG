---
tablero: DEMANDA INSATISFECHA
pagina: CIRUGIAS
nombre_funcional: Cirugías dentro de la demanda insatisfecha
bloque: Histórico
tablas: [CIRUGÍAS]
actualizado: 2026-10-28
version: 2
---

# CIRUGIAS

## Propósito
Analiza las cirugías no oportunas que el tablero suma como demanda insatisfecha: las solicitudes de cirugía programada con más de 45 días de espera. Muestra total, promedio mensual, distribución por mes y por asegurador. Es de análisis histórico; se llega desde el botón CIRUGÍAS de CONSOLIDADO. Página oculta en Power BI (solo CONSOLIDADO es visible).

## Fuentes de datos
- **CIRUGÍAS**: Solicitudes de cirugía programada (TipoCirugiaOid = 1) cuya fecha de planeación es del 1 de enero de 2025 en adelante. Trae paciente, EPS, especialidad, procedimientos, médico, asegurador, estado actual y la primera fecha de cada estado quirúrgico (planeada, por autorizar, programado, en quirófano, cancelado, entre otros). FECHA es la fecha de planeación.

## Indicadores
- **Total cirugías**: Número de solicitudes con procedimiento registrado. DAX: COUNT('CIRUGÍAS'[PROCEDIMIENTO]).
- **Promedio mensual**: Cirugías planeadas en el año en curso divididas por el número del mes actual. Medida PROM_CIRUGÍAS: DIVIDE(CALCULATE(COUNT('CIRUGÍAS'[PROCEDIMIENTO]), YEAR('CIRUGÍAS'[Planeada]) = YEAR(TODAY())), MONTH(TODAY())).

## Visuales
- **Tarjetas**: TOTAL y PROMEDIO MENSUAL.
- **Gráfico de columnas por mes**: Titulado «CIRUGÍAS por Mes»; cantidad mensual de cirugías.
- **Treemap por asegurador**: Titulado «CIRUGÍAS por ASEGURADOR»; distribución por asegurador.
- **Filtros**: Segmentadores «Date Año» y «Date Mes» (CALENDARIO[Date]) y «ASEGURADOR» (CIRUGÍAS[TERNOMCOM]), y botón de inicio que vuelve a CONSOLIDADO.

## Reglas de negocio
- **Fechas de estado**: Para cada solicitud se toma la primera fecha en que pasó por cada estado (códigos EstadoQxOid 1, 36, 18, 24, 6, 23, 19, 5, 7, 9, 10, 11, 13 y 8) registrado desde 2025.
- **Procedimientos agrupados**: Los procedimientos de una solicitud se concatenan en una sola celda separados por « * »; cada solicitud cuenta una vez.
- **Médico**: Si el médico es el genérico (DoctorOId = 5000) se usa el nombre del médico que solicita.
- **Filtro de página**: Solo cuentan solicitudes con CIRUGÍAS[TIEMPO_CIRUGÍA] mayor de 45 días y se excluyen las especialidades ANESTESIOLOGIA y JUNTA MEDICA.
- **Tiempo de cirugía**: TIEMPO_CIRUGÍA son los días entre el estado «Paciente En Espera Programacion» y el estado «Paciente en Sala de Espera» (hasta hoy si aún no llega); queda en blanco si no hay fecha de espera de programación.

## Observaciones
- **Promedio mensual bajo**: En la captura de la documentación el promedio mensual muestra 1 con un total de miles; ocurre porque solo cuenta cirugías planeadas en el año en curso.
- **Cirugías canceladas**: La consulta y el filtro no excluyen cirugías canceladas; una solicitud cancelada tras más de 45 días de espera también cuenta. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.

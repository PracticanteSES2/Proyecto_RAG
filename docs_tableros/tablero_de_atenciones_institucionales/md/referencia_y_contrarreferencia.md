---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: REFERENCIA Y CONTRARREFERENCIA
nombre_funcional: Solicitudes de referencia por mes y estado de aceptación
bloque: Histórico
tablas: [REFERENCIA, ASEGURADORAS]
actualizado: 2026-10-20
version: 1
---

# REFERENCIA Y CONTRARREFERENCIA

## Propósito
Muestra cuántas solicitudes de referencia y contrarreferencia recibe el hospital cada mes y en qué estado quedan (aceptadas, no aceptadas, con ingreso, urgencia vital o trámite por SES). Desde aquí se abre MOTIVOS DE NO ACEPTACIÓN; desde qué botón se llega: por confirmar.

## Fuentes de datos
- **REFERENCIA**: Solicitudes de la tabla fact_referencia desde 2023-01-01 hasta hoy (por fecha de llamada), con fecha de llamada y de llegada, dependencia, prestador, médico, estado de aceptación (NOMBRE_ESTADO), causa (NOMBRE_CAUSA) y aseguradora agrupada del paciente. Se relaciona con ASEGURADORAS; no se relaciona con el Calendario.

## Indicadores
- **Solicitudes**: Número de solicitudes por mes, año y estado. Medida o columna contada por confirmar.
- **Distribución por estado**: Porcentaje de solicitudes en cada estado sobre el total.

## Visuales
- **Segmentadores**: ESTADO, ASEGURADORA, Año y Mes.
- **Gráfico de solicitudes por mes**: Columnas «SOLICITUDES por Mes, Año y ESTADO» agrupadas por mes y año, con una columna por estado (Aceptado, Con Ingreso, Es Urgencia Vital, No Aceptado y Tramite Por SES).
- **Tabla de detalle anual**: Matriz con año y, debajo, cada estado en filas, meses en columnas y totales.
- **Gráfico por estado**: Torta «SOLICITUDES por ESTADO» con el porcentaje de cada estado.
- **Botón Motivos no aceptación**: Abre MOTIVOS DE NO ACEPTACIÓN; el botón de casa vuelve a INICIO.

## Reglas de negocio
- **Estados de aceptación**: Aceptado, Con Ingreso, Es Urgencia Vital, No Aceptado y Tramite Por SES (catálogo DIM_ESTADOS_ACEPTACION).
- **Fecha de la solicitud**: La solicitud se ubica en el mes de la fecha de llamada (FECHALLAM).
- **Agrupación de aseguradoras**: NUEVA EPS, SURA (sin ARL SURA, seguros de vida ni Suramericana), SANITAS (sin Colsanitas ni Medisanitas) y MALLAMAS; el resto conserva su nombre.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Posibles duplicados**: La consulta une cada solicitud con todas sus causas; una solicitud con varias causas aparece varias veces y puede contarse de más si se cuentan filas. Por confirmar.
- **Aseguradora por documento**: La aseguradora se busca por el documento del paciente en la tabla de pacientes, no por la solicitud; es la aseguradora actual del paciente.
- **Sin relación con el Calendario**: La tabla no se une al Calendario; los segmentadores Año y Mes deben salir de la fecha de la propia tabla. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
